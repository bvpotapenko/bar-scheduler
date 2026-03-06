"""
Plan generation orchestrator.

Coordinates all planning submodules to produce a deterministic multi-week
training plan.  Contains no domain rules itself — delegates to specialised
components for schedule construction, state computation, load calculation,
set prescription, grip rotation, test injection, and trace formatting.
"""

from dataclasses import replace as _dc_replace
from datetime import datetime, timedelta
from typing import Generator

from ..adaptation import get_training_status
from ..config import (
    DEFAULT_PLAN_WEEKS,
    MAX_PLAN_WEEKS,
    MIN_PLAN_WEEKS,
    MIN_SESSIONS_FOR_AUTOREG,
    estimate_weeks_to_target,
    expected_reps_per_week,
)
from ..exercises.base import ExerciseDefinition
from ..exercises.registry import get_exercise
from ..metrics import training_max_from_baseline
from ..models import (
    PlannedSet,
    SessionPlan,
    SessionResult,
    SessionType,
    SetResult,
    TrainingStatus,
    UserState,
)
from .grip_selector import GripSelector, _init_grip_counts, _next_grip
from .load_calculator import _calculate_added_weight
from .rest_advisor import calculate_adaptive_rest
from .schedule_builder import (
    calculate_session_days,
    get_next_session_type_index,
    get_schedule_template,
)
from .session_trace_builder import _format_explain
from .set_prescriptor import calculate_set_prescription
from .test_session_inserter import _insert_test_sessions
from .training_state_calculator import compute_training_state
from .types import _SessionTrace

PULL_UP = get_exercise("pull_up")


def create_synthetic_test_session(
    date: str,
    bodyweight_kg: float,
    baseline_max: int,
    exercise_id: str = "pull_up",
) -> SessionResult:
    """
    Create a synthetic TEST session for initialization.

    Args:
        date: Session date (ISO format)
        bodyweight_kg: Bodyweight
        baseline_max: Baseline max reps
        exercise_id: Exercise identifier

    Returns:
        Synthetic session result
    """
    test_set = SetResult(
        target_reps=baseline_max,
        actual_reps=baseline_max,
        rest_seconds_before=180,
        added_weight_kg=0.0,
        rir_target=0,
        rir_reported=0,
    )

    return SessionResult(
        date=date,
        bodyweight_kg=bodyweight_kg,
        grip="pronated",
        session_type="TEST",
        exercise_id=exercise_id,
        planned_sets=[test_set],
        completed_sets=[test_set],
        notes="Synthetic baseline test",
    )


def _plan_core(
    user_state: UserState,
    start_date: str,
    weeks_ahead: int | None = None,
    baseline_max: int | None = None,
    exercise: ExerciseDefinition | None = None,
    overtraining_level: int = 0,
    overtraining_rest_days: int = 0,
    history_init_cutoff: str | None = None,
) -> Generator[tuple[SessionPlan, _SessionTrace], None, None]:
    """
    Core plan generator — single source of truth for all plan logic.

    Yields (SessionPlan, _SessionTrace) for every planned session.
    Both generate_plan() and explain_plan_entry() delegate here so that
    the explanation is guaranteed to reflect the actual plan.

    When overtraining_rest_days > 0 the training start is shifted forward
    by that many days (without persisting to the store), so the next session
    falls after adequate recovery.  The shift is reported in the trace so
    explain_plan_entry() can explain it.

    Raises ValueError if there is no history and no baseline_max.
    """
    if exercise is None:
        exercise = PULL_UP

    # Filter history: this exercise only, REST records excluded (full span of all dates)
    history = [
        s for s in user_state.history
        if s.exercise_id == exercise.exercise_id and s.session_type != "REST"
    ]

    if not history and baseline_max is None:
        raise ValueError(
            "No history available. Please provide baseline_max or log a TEST session."
        )

    if not history:
        today = datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=1)
        synthetic = create_synthetic_test_session(
            today.strftime("%Y-%m-%d"),
            user_state.current_bodyweight_kg,
            baseline_max,  # type: ignore
            exercise.exercise_id,
        )
        history = [synthetic]

    # Plan-stability invariant: prescription(slot D) = f(history where date < D, profile).
    # Use only pre-plan sessions for initial state computation (TM, ff_state, rotation,
    # grip counts). This ensures logging a session on or after plan_start does not
    # retroactively change prescriptions for plan_start or earlier slots.
    #
    # history_init_cutoff separates the "history cutoff" from the "plan calendar anchor":
    # - On backward skip, plan_start retreats but the cutoff stays at the old plan_start
    #   so the initial state (TM, rotation, grip) does not change.
    # - When None (unit tests, direct calls), falls back to start_date.
    # Fall back to full history only when no pre-plan sessions exist (e.g., brand-new user).
    cutoff = history_init_cutoff or start_date
    history_for_init = [s for s in history if s.date < cutoff]
    effective_init = history_for_init if history_for_init else history

    status, initial_tm, ff_state, z_score, last_test_weight = compute_training_state(
        user_state, history, history_for_init, exercise, baseline_max
    )

    tm_float = float(initial_tm)
    user_target = int(exercise.target_value)
    days_per_week = user_state.profile.days_for_exercise(exercise.exercise_id)

    if weeks_ahead is None:
        estimated = estimate_weeks_to_target(initial_tm, user_target)
        weeks_ahead = max(MIN_PLAN_WEEKS, min(DEFAULT_PLAN_WEEKS, estimated))
    else:
        weeks_ahead = max(MIN_PLAN_WEEKS, min(MAX_PLAN_WEEKS, weeks_ahead))

    start = datetime.strptime(start_date, "%Y-%m-%d")
    # Apply overtraining recovery shift: push training start forward without
    # modifying plan_start_date in the store.
    if overtraining_rest_days > 0:
        start = start + timedelta(days=overtraining_rest_days)
    schedule = get_schedule_template(days_per_week)
    start_rotation_idx = get_next_session_type_index(effective_init, schedule)
    session_dates = calculate_session_days(
        start, days_per_week, weeks_ahead, start_rotation_idx
    )

    # REST records do not consume a rotation slot. Remove any REST-covered dates
    # from the planned calendar and reassign session types so the sequence is
    # continuous (e.g. resting on the H slot makes the next planned day H, not T).
    rest_covered = {
        s.date for s in user_state.history
        if s.exercise_id == exercise.exercise_id and s.session_type == "REST"
    }
    if rest_covered:
        schedule_rotated = schedule[start_rotation_idx:] + schedule[:start_rotation_idx]
        sched_len = len(schedule)
        remaining = [(d, t) for d, t in session_dates if d.strftime("%Y-%m-%d") not in rest_covered]
        session_dates = [(d, schedule_rotated[i % sched_len]) for i, (d, t) in enumerate(remaining)]

    session_dates = _insert_test_sessions(
        session_dates, history, exercise.test_frequency_weeks, start
    )

    # Stable week-number anchor: first real (non-REST) session in ALL history
    original_history = [
        s for s in user_state.history
        if s.exercise_id == exercise.exercise_id and s.session_type != "REST"
    ]
    first_date: datetime | None = (
        datetime.strptime(original_history[0].date, "%Y-%m-%d") if original_history else None
    )
    week_offset = (start - first_date).days // 7 if first_date is not None else 0
    # Display weeks are anchored to the Monday of the week containing first_date
    # so that Mon-Sun calendar weeks stay together (e.g. Mon 03.02 and Wed 03.04
    # are both "week 3", not split across week 2 / week 3).
    first_monday: datetime | None = (
        first_date - timedelta(days=first_date.weekday()) if first_date is not None else None
    )

    # Grip rotation: initialise from pre-plan history (effective_init) so that
    # logging sessions during the plan period does not shift grip assignments.
    grip_counts = _init_grip_counts(effective_init, exercise)
    grip_history_counts = dict(grip_counts)   # snapshot of history-only counts

    # Pre-index FULL history by session type for per-slot date-filtered lookups.
    # The filter (date < slot_date) is applied at read time in the loop below,
    # allowing future slots to benefit from sessions logged mid-plan while
    # keeping current/past slot prescriptions stable.
    history_by_type: dict[str, list] = {}
    for s in history:
        history_by_type.setdefault(s.session_type, []).append(s)

    current_plan_week_idx = 0
    weekly_log: list[tuple[int, float, float, float]] = []
    # Overtraining protection: how many upcoming sessions still need adjustment
    density_sessions_left = overtraining_level  # level = number of sessions to affect

    for date, session_type in session_dates:
        date_str = date.strftime("%Y-%m-%d")
        session_week_idx = (date - start).days // 7

        # Apply weekly TM progression exactly once per calendar-week boundary
        if session_week_idx > current_plan_week_idx:
            prog = expected_reps_per_week(int(tm_float), user_target)
            old_tm = tm_float
            tm_float += prog
            weekly_log.append((week_offset + session_week_idx, prog, old_tm, tm_float))
            current_plan_week_idx = session_week_idx

        current_tm = int(tm_float)

        # Grip selection
        count_before = grip_counts.get(session_type, 0)
        if exercise.has_variant_rotation:
            grip = _next_grip(session_type, grip_counts, exercise)
        else:
            grip = exercise.primary_variant
        cycle = exercise.grip_cycles.get(session_type, [exercise.primary_variant])

        week_num = (
            (date - first_monday).days // 7 + 1 if first_monday is not None
            else session_week_idx + 1
        )

        # --- Compute trace values (pure math, cheap) ---
        params = exercise.session_params[session_type]
        reps_low = max(params.reps_min, int(current_tm * params.reps_fraction_low))
        reps_high = min(params.reps_max, int(current_tm * params.reps_fraction_high))
        base_reps = max(params.reps_min, min(params.reps_max, (reps_low + reps_high) // 2))
        base_sets = (params.sets_min + params.sets_max) // 2
        has_autoreg = len(effective_init) >= MIN_SESSIONS_FOR_AUTOREG

        from ..adaptation import apply_autoregulation
        if has_autoreg:
            adj_sets, adj_reps = apply_autoregulation(base_sets, base_reps, ff_state)
        else:
            adj_sets, adj_reps = base_sets, base_reps

        # Only sessions strictly before this slot's date: logging at D must not
        # change adaptive rest for D or any earlier slot.
        recent_same_type = [
            s for s in history_by_type.get(session_type, [])
            if s.date < date_str
        ][-5:]
        adj_rest = calculate_adaptive_rest(session_type, recent_same_type, ff_state, exercise)
        added_weight = _calculate_added_weight(
            exercise, current_tm, user_state.current_bodyweight_kg, last_test_weight
        )
        expected_tm_after = int(tm_float)

        # --- Build the plan entry ---
        sets = calculate_set_prescription(
            session_type,  # type: ignore
            current_tm,
            ff_state,
            user_state.current_bodyweight_kg,
            history_sessions=len(effective_init),
            recent_same_type=recent_same_type,
            exercise=exercise,
            last_test_weight=last_test_weight,
        )

        # Overtraining protection: adjust the first density_sessions_left sessions
        if density_sessions_left > 0 and session_type not in ("TEST", "REST"):
            rest_boost = 30 if overtraining_level == 1 else 60
            adjusted_sets = []
            for ps in sets:
                new_rest = min(params.rest_max, ps.rest_seconds_before + rest_boost)
                new_reps = max(params.reps_min, ps.target_reps - (1 if overtraining_level >= 3 else 0))
                adjusted_sets.append(_dc_replace(ps, rest_seconds_before=new_rest, target_reps=new_reps))
            if overtraining_level >= 2 and len(adjusted_sets) > 2:
                adjusted_sets = adjusted_sets[:-1]  # drop one set, floor at 2
            sets = adjusted_sets
            density_sessions_left -= 1

        plan = SessionPlan(
            date=date_str,
            grip=grip,
            session_type=session_type,  # type: ignore
            exercise_id=exercise.exercise_id,
            sets=sets,
            expected_tm=expected_tm_after,
            week_number=week_num,
        )

        trace = _SessionTrace(
            date_str=date_str,
            session_type=session_type,
            session_week_idx=session_week_idx,
            week_num=week_num,
            week_offset=week_offset,
            weeks_ahead=weeks_ahead,
            grip=grip,
            cycle=list(cycle),
            count_before=count_before,
            hist_count=grip_history_counts.get(session_type, 0),
            initial_tm=initial_tm,
            current_tm=current_tm,
            tm_float=tm_float,
            weekly_log=list(weekly_log),    # snapshot at yield time
            base_sets=base_sets,
            base_reps=base_reps,
            adj_sets=adj_sets,
            adj_reps=adj_reps,
            has_autoreg=has_autoreg,
            z_score=z_score,
            reps_low=reps_low,
            reps_high=reps_high,
            added_weight=added_weight,
            last_test_weight=last_test_weight,
            adj_rest=adj_rest,
            recent_same_type=recent_same_type,
            expected_tm_after=expected_tm_after,
            history=history,
            history_len=len(history),
            days_per_week=days_per_week,
            user_target=user_target,
            schedule=list(schedule),
            params=params,
            exercise=exercise,
            ff_state=ff_state,
            overtraining_shift_days=overtraining_rest_days,
            overtraining_level=overtraining_level,
        )

        yield plan, trace


def generate_plan(
    user_state: UserState,
    start_date: str,
    weeks_ahead: int | None = None,
    baseline_max: int | None = None,
    exercise: ExerciseDefinition | None = None,
    overtraining_level: int = 0,
    overtraining_rest_days: int = 0,
    history_init_cutoff: str | None = None,
) -> list[SessionPlan]:
    """
    Generate a deterministic training plan with progressive overload.

    Args:
        user_state: Current user state with profile and history
        start_date: Start date for the plan (ISO format)
        weeks_ahead: Number of weeks to plan (None = estimate)
        baseline_max: Baseline max if no history
        exercise: ExerciseDefinition to parameterise the plan (default: PULL_UP)
        overtraining_level: Graduated overtraining protection level (0=none, 1-3)
        overtraining_rest_days: Days to shift training start forward for recovery
                                (computed from overtraining severity; NOT saved to store)

    Returns:
        List of SessionPlan for the planning horizon
    """
    return [plan for plan, _ in _plan_core(
        user_state, start_date, weeks_ahead, baseline_max, exercise,
        overtraining_level, overtraining_rest_days,
        history_init_cutoff=history_init_cutoff,
    )]


def explain_plan_entry(
    user_state: UserState,
    plan_start_date: str,
    target_date: str,
    weeks_ahead: int | None = None,
    baseline_max: int | None = None,
    exercise: ExerciseDefinition | None = None,
    overtraining_level: int = 0,
    overtraining_rest_days: int = 0,
    history_init_cutoff: str | None = None,
) -> str:
    """
    Generate a step-by-step Rich-markup explanation of a planned session.

    Delegates to _plan_core() so the explanation is guaranteed to match
    the plan produced by generate_plan() exactly.

    For dates within the plan horizon that are not training sessions, returns
    a rest-day explanation.  For past dates found in history, returns a brief
    session summary.

    Args:
        user_state: Current user state
        plan_start_date: Start date of the plan (ISO)
        target_date: Date of the session to explain (ISO)
        weeks_ahead: Plan horizon (None = estimate)
        baseline_max: Baseline max if no history
        exercise: ExerciseDefinition (default: PULL_UP)
        overtraining_level: Level from overtraining_severity() (for shift notice)
        overtraining_rest_days: Days the plan start was shifted forward
        history_init_cutoff: Cutoff date for effective_init (stable across backward skips)

    Returns:
        Rich-markup string ready for console.print()
    """
    if exercise is None:
        exercise = PULL_UP
    last_weeks_ahead: int | None = None
    try:
        for plan, trace in _plan_core(
            user_state, plan_start_date, weeks_ahead, baseline_max, exercise,
            overtraining_level, overtraining_rest_days,
            history_init_cutoff=history_init_cutoff,
        ):
            last_weeks_ahead = trace.weeks_ahead
            if plan.date == target_date:
                return _format_explain(trace, user_state.current_bodyweight_kg)
    except ValueError as exc:
        return f"[yellow]{exc}[/yellow]"

    # Fallback 1: date is within the plan horizon → scheduled rest day
    try:
        start_dt  = datetime.strptime(plan_start_date, "%Y-%m-%d")
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        end_dt    = start_dt + timedelta(weeks=(last_weeks_ahead or 4))
        if start_dt <= target_dt <= end_dt:
            return (
                f"[dim]Rest day  ·  {target_date}[/dim]\n"
                "  No training session is scheduled for this date.\n"
                "  This is a planned rest day within the training horizon."
            )
    except ValueError:
        pass

    # Fallback 2: past date found in history → brief session summary
    ex_id = exercise.exercise_id if exercise else "pull_up"
    past_sessions = [
        s for s in user_state.history
        if s.date == target_date and s.exercise_id == ex_id
    ]
    if past_sessions:
        lines = [f"[dim]Historical sessions on {target_date}:[/dim]"]
        for s in past_sessions:
            total_reps = sum(st.actual_reps or 0 for st in s.completed_sets)
            rir_str = ""
            if s.completed_sets and s.completed_sets[-1].rir_reported is not None:
                rir_str = f"  RIR≈{s.completed_sets[-1].rir_reported}"
            lines.append(
                f"  {s.session_type}  ·  {total_reps} total reps"
                f"  ·  {s.bodyweight_kg} kg BW{rir_str}"
            )
        return "\n".join(lines)

    # Fallback 3: outside plan horizon
    horizon = f"{last_weeks_ahead}-week " if last_weeks_ahead is not None else ""
    return (
        f"[yellow]No planned session found for {target_date}.[/yellow]\n"
        f"Is this date within the {horizon}plan horizon starting {plan_start_date}?"
    )


def estimate_plan_completion_date(
    user_state: UserState,
    baseline_max: int | None = None,
    exercise_id: str = "pull_up",
) -> str | None:
    """
    Estimate when the user might reach their target reps goal.

    Args:
        user_state: Current user state
        baseline_max: Baseline max if no history
        exercise_id: Which exercise's target to use

    Returns:
        Estimated completion date (ISO format) or None if target reached
    """
    status = get_training_status(
        user_state.history,
        user_state.current_bodyweight_kg,
        baseline_max,
    )

    tm = status.training_max
    target = user_state.profile.target_for_exercise(exercise_id).reps

    if tm >= target:
        return None

    weeks = estimate_weeks_to_target(tm, target)
    estimated_date = datetime.now() + timedelta(weeks=weeks)

    return estimated_date.strftime("%Y-%m-%d")


def format_plan_summary(plans: list[SessionPlan]) -> str:
    """
    Create a text summary of the plan.

    Args:
        plans: List of session plans

    Returns:
        Formatted string summary
    """
    if not plans:
        return "No sessions planned."

    lines = []
    current_week = None

    for plan in plans:
        date = datetime.strptime(plan.date, "%Y-%m-%d")
        week_num = date.isocalendar()[1]

        if current_week != week_num:
            if current_week is not None:
                lines.append("")
            lines.append(f"Week {week_num}:")
            current_week = week_num

        # Format sets
        if plan.sets:
            reps_list = [s.target_reps for s in plan.sets]
            weight = plan.sets[0].added_weight_kg
            rest = plan.sets[0].rest_seconds_before

            if all(r == reps_list[0] for r in reps_list):
                sets_str = f"{len(reps_list)}x({reps_list[0]}@+{weight:.1f})"
            else:
                reps_str = ",".join(str(r) for r in reps_list)
                sets_str = f"({reps_str})@+{weight:.1f}"

            lines.append(
                f"  {plan.date} {plan.session_type:4} {plan.grip:8} {sets_str:24} rest {rest}s"
            )
        else:
            lines.append(f"  {plan.date} {plan.session_type:4} {plan.grip:8} (no sets)")

    return "\n".join(lines)
