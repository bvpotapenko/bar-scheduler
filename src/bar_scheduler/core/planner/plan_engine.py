"""
Plan generation orchestrator.

Coordinates all planning submodules to produce a deterministic multi-week
training plan.  Contains no domain rules itself -- delegates to specialised
components for schedule construction, state computation, load calculation,
set prescription, grip rotation, test injection, and trace formatting.
"""

from dataclasses import replace as _dc_replace
from datetime import datetime, timedelta
from typing import Generator

from bar_scheduler.core.adaptation import get_training_status
from bar_scheduler.core.config import (
    DEFAULT_PLAN_WEEKS,
    DELTA_PROGRESSION_MIN,
    MAX_PLAN_WEEKS,
    MIN_PLAN_WEEKS,
    estimate_weeks_to_target,
    expected_reps_per_week,
)
from bar_scheduler.core.exercises.base import ExerciseDefinition
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.models import (
    SessionPlan,
    SessionResult,
    SetResult,
    UserState,
)
from bar_scheduler.core.planner.grip_selector import _init_grip_counts, _next_grip
from bar_scheduler.core.planner.load_calculator import (
    calculate_machine_assistance,
    estimate_prescription_weight,
)
from bar_scheduler.core.planner.schedule_builder import (
    calculate_session_days,
    get_next_session_type_index,
    get_schedule_template,
)
from bar_scheduler.core.planner.set_prescriptor import calculate_set_prescription
from bar_scheduler.core.planner.test_session_inserter import _insert_test_sessions
from bar_scheduler.core.planner.training_state_calculator import compute_training_state


def create_synthetic_test_session(
    date: str,
    bodyweight_kg: float,
    baseline_max: int,
    exercise_id: str,
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


def _compute_week_prog(
    tm_float: float,
    weighted_goal: bool,
    exercise_target: object,
    user_target: int,
    history: list,
    exercise: object,
    bodyweight_kg: float,
    available_weights_kg: list[float] | None,
) -> float:
    """Return how many TM reps to add this week."""
    if not weighted_goal:
        return expected_reps_per_week(int(tm_float), user_target)
    # For weighted goals: stop only when BOTH rep AND weight targets are met.
    # When TM already exceeds goal reps, expected_reps_per_week returns 0,
    # but we use DELTA_PROGRESSION_MIN as a floor so TM keeps growing,
    # driving higher Epley 1RM and thus higher weight prescription.
    assert exercise_target is not None  # weighted_goal implies this
    current_weight = estimate_prescription_weight(
        history, exercise, bodyweight_kg, exercise_target.reps,  # type: ignore[union-attr]
        available_weights_kg=available_weights_kg,
    )
    goal_met = (
        int(tm_float) >= exercise_target.reps  # type: ignore[union-attr]
        and current_weight >= exercise_target.weight_kg  # type: ignore[union-attr]
    )
    if goal_met:
        return 0.0
    return max(
        DELTA_PROGRESSION_MIN,
        expected_reps_per_week(int(tm_float), user_target),
    )


def _apply_overtraining_adjust(
    sets: list,
    sess_params: object,
    overtraining_level: int,
) -> list:
    """Apply graduated density reduction for overtraining recovery."""
    rest_boost = 30 if overtraining_level == 1 else 60
    rep_deduct = 1 if overtraining_level >= 3 else 0
    adjusted = [
        _dc_replace(
            ps,
            rest_seconds_before=min(  # type: ignore[union-attr]
                sess_params.rest_max, ps.rest_seconds_before + rest_boost
            ),
            target_reps=max(  # type: ignore[union-attr]
                sess_params.reps_min, ps.target_reps - rep_deduct
            ),
        )
        for ps in sets
    ]
    if overtraining_level >= 2 and len(adjusted) > 2:
        adjusted = adjusted[:-1]  # drop one set, floor at 2
    return adjusted


def _plan_core(
    user_state: UserState,
    start_date: str,
    exercise: ExerciseDefinition,
    weeks_ahead: int | None = None,
    baseline_max: int | None = None,
    overtraining_level: int = 0,
    overtraining_rest_days: int = 0,
    history_init_cutoff: str | None = None,
    available_weights_kg: list[float] | None = None,
    available_machine_assistance_kg: list[float] | None = None,
) -> Generator[SessionPlan, None, None]:
    """
    Core plan generator -- single source of truth for all plan logic.

    Yields SessionPlan for every planned session.

    When overtraining_rest_days > 0 the training start is shifted forward
    by that many days (without persisting to the store), so the next session
    falls after adequate recovery.

    Raises ValueError if there is no history and no baseline_max.
    """
    # Filter history: this exercise only
    history = [sess for sess in user_state.history if sess.exercise_id == exercise.exercise_id]

    if not history and baseline_max is None:
        raise ValueError("No history available. Please provide baseline_max or log a TEST session.")

    if not history:
        today = datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=1)
        synthetic = create_synthetic_test_session(
            today.strftime("%Y-%m-%d"),
            user_state.profile.bodyweight_kg,
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
    history_for_init = [sess for sess in history if sess.date < cutoff]
    effective_init = history_for_init if history_for_init else history

    status, initial_tm, ff_state, _, _ = compute_training_state(
        user_state, history, history_for_init, exercise, baseline_max
    )

    tm_float = float(initial_tm)
    days_per_week = user_state.profile.days_for_exercise(exercise.exercise_id)

    exercise_target = user_state.profile.target_for_exercise(exercise.exercise_id)
    if exercise_target is None:
        user_target = int(exercise.target_value)
    else:
        user_target = exercise_target.reps
    weighted_goal = exercise_target is not None and exercise_target.weight_kg > 0

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
    session_dates = calculate_session_days(start, days_per_week, weeks_ahead, start_rotation_idx)

    session_dates = _insert_test_sessions(
        session_dates, history, exercise.test_frequency_weeks, start
    )

    # Stable week-number anchor: first session in ALL history for this exercise
    original_history = [sess for sess in user_state.history if sess.exercise_id == exercise.exercise_id]
    first_date: datetime | None = (
        datetime.strptime(original_history[0].date, "%Y-%m-%d") if original_history else None
    )
    # Display weeks are anchored to the Monday of the week containing first_date
    # so that Mon-Sun calendar weeks stay together (e.g. Mon 03.02 and Wed 03.04
    # are both "week 3", not split across week 2 / week 3).
    first_monday: datetime | None = (
        None if first_date is None else first_date - timedelta(days=first_date.weekday())
    )

    # Grip rotation: initialise from pre-plan history (effective_init) so that
    # logging sessions during the plan period does not shift grip assignments.
    grip_counts = _init_grip_counts(effective_init, exercise)
    # Pre-index FULL history by session type for per-slot date-filtered lookups.
    # The filter (date < slot_date) is applied at read time in the loop below,
    # allowing future slots to benefit from sessions logged mid-plan while
    # keeping current/past slot prescriptions stable.
    history_by_type: dict[str, list] = {}
    for sess in history:
        history_by_type.setdefault(sess.session_type, []).append(sess)

    current_plan_week_idx = 0
    # Overtraining protection: how many upcoming sessions still need adjustment
    density_sessions_left = overtraining_level  # level = number of sessions to affect

    for date, session_type in session_dates:
        date_str = date.strftime("%Y-%m-%d")
        session_week_idx = (date - start).days // 7

        # Apply weekly TM progression exactly once per calendar-week boundary
        if session_week_idx > current_plan_week_idx:
            tm_float += _compute_week_prog(
                tm_float, weighted_goal, exercise_target, user_target,
                history, exercise, user_state.profile.bodyweight_kg,
                available_weights_kg,
            )
            current_plan_week_idx = session_week_idx

        current_tm = int(tm_float)

        # Grip selection
        if exercise.has_variant_rotation:
            grip = _next_grip(session_type, grip_counts, exercise)
        else:
            grip = exercise.primary_variant

        week_num = (
            session_week_idx + 1
            if first_monday is None
            else (date - first_monday).days // 7 + 1
        )

        sess_params = exercise.session_params[session_type]

        # Only sessions strictly before this slot's date: logging at D must not
        # change adaptive rest for D or any earlier slot.
        recent_same_type = [hs for hs in history_by_type.get(session_type, []) if hs.date < date_str][
            -5:
        ]

        if available_machine_assistance_kg:
            prescribed_assistance = calculate_machine_assistance(
                exercise,
                current_tm,
                user_state.profile.bodyweight_kg,
                history,
                session_type,
                available_machine_assistance_kg=available_machine_assistance_kg,
            )
        else:
            prescribed_assistance = None
        expected_tm_after = int(tm_float)

        # --- Build the plan entry ---
        sets = calculate_set_prescription(
            session_type,  # type: ignore
            current_tm,
            ff_state,
            user_state.profile.bodyweight_kg,
            exercise=exercise,
            history=history,
            history_sessions=len(effective_init),
            recent_same_type=recent_same_type,
            available_weights_kg=available_weights_kg,
            latest_test_max=status.latest_test_max,
        )

        # Overtraining protection: adjust the first density_sessions_left sessions
        if density_sessions_left > 0 and session_type != "TEST":
            sets = _apply_overtraining_adjust(sets, sess_params, overtraining_level)
            density_sessions_left -= 1

        plan = SessionPlan(
            date=date_str,
            grip=grip,
            session_type=session_type,  # type: ignore
            exercise_id=exercise.exercise_id,
            sets=sets,
            expected_tm=expected_tm_after,
            week_number=week_num,
            prescribed_assistance_kg=prescribed_assistance,
        )

        yield plan


def generate_plan(
    user_state: UserState,
    start_date: str,
    exercise: ExerciseDefinition,
    weeks_ahead: int | None = None,
    baseline_max: int | None = None,
    overtraining_level: int = 0,
    overtraining_rest_days: int = 0,
    history_init_cutoff: str | None = None,
    available_weights_kg: list[float] | None = None,
    available_machine_assistance_kg: list[float] | None = None,
) -> list[SessionPlan]:
    """
    Generate a deterministic training plan with progressive overload.

    Args:
        user_state: Current user state with profile and history
        start_date: Start date for the plan (ISO format)
        exercise: ExerciseDefinition to parameterise the plan
        weeks_ahead: Number of weeks to plan (None = estimate)
        baseline_max: Baseline max if no history
        overtraining_level: Graduated overtraining protection level (0=none, 1-3)
        overtraining_rest_days: Days to shift training start forward for recovery
                                (computed from overtraining severity; NOT saved to store)
        available_weights_kg: Discrete weights the user owns for this exercise;
                              empty = continuous 0.5 kg rounding.
        available_machine_assistance_kg: Discrete machine assistance levels available;
                              empty / None = no machine assistance planning.

    Returns:
        List of SessionPlan for the planning horizon
    """
    return [
        plan
        for plan in _plan_core(
            user_state,
            start_date,
            exercise,
            weeks_ahead=weeks_ahead,
            baseline_max=baseline_max,
            overtraining_level=overtraining_level,
            overtraining_rest_days=overtraining_rest_days,
            history_init_cutoff=history_init_cutoff,
            available_weights_kg=available_weights_kg,
            available_machine_assistance_kg=available_machine_assistance_kg,
        )
    ]


def estimate_plan_completion_date(
    user_state: UserState,
    exercise_id: str,
    baseline_max: int | None = None,
) -> str | None:
    """
    Estimate when the user might reach their target reps goal.

    Args:
        user_state: Current user state
        baseline_max: Baseline max if no history
        exercise_id: Which exercise's target to use

    Returns:
        Estimated completion date (ISO format) or None if target not set or reached
    """
    exercise_target = user_state.profile.target_for_exercise(exercise_id)
    if exercise_target is None:
        return None

    history = [sess for sess in user_state.history if sess.exercise_id == exercise_id]
    status = get_training_status(
        user_state.history,
        user_state.profile.bodyweight_kg,
        baseline_max,
    )

    tm = status.training_max

    if exercise_target.weight_kg > 0:
        # Weighted goal: check both rep and weight dimensions.
        current_weight = estimate_prescription_weight(
            history,
            get_exercise(exercise_id),
            user_state.profile.bodyweight_kg,
            exercise_target.reps,
        )
        if tm >= exercise_target.reps and current_weight >= exercise_target.weight_kg:
            return None
    elif tm >= exercise_target.reps:
        return None

    weeks = estimate_weeks_to_target(tm, exercise_target.reps)
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
        stype = plan.session_type.ljust(4)
        grip_padded = plan.grip.ljust(8)
        if plan.sets:
            reps_list = [ps.target_reps for ps in plan.sets]
            weight = plan.sets[0].added_weight_kg
            rest = plan.sets[0].rest_seconds_before

            if all(rep == reps_list[0] for rep in reps_list):
                sets_str = f"{len(reps_list)}x({reps_list[0]}@+{weight:.1f})"
            else:
                reps_str = ",".join(str(rep) for rep in reps_list)
                sets_str = f"({reps_str})@+{weight:.1f}"

            sets_padded = sets_str.ljust(24)
            lines.append(f"  {plan.date} {stype} {grip_padded} {sets_padded} rest {rest}s")
        else:
            lines.append(f"  {plan.date} {stype} {grip_padded} (no sets)")

    return "\n".join(lines)
