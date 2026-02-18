"""
Plan generation for pull-up training.

Generates deterministic multi-week training plans based on
current status, history, and adaptation rules.
"""

from datetime import datetime, timedelta

from .adaptation import (
    apply_autoregulation,
    calculate_volume_adjustment,
    get_training_status,
)
from .config import (
    DAY_SPACING,
    DEFAULT_PLAN_WEEKS,
    MAX_PLAN_WEEKS,
    MIN_PLAN_WEEKS,
    READINESS_VOLUME_REDUCTION,
    READINESS_Z_HIGH,
    READINESS_Z_LOW,
    SCHEDULE_3_DAYS,
    SCHEDULE_4_DAYS,
    SESSION_PARAMS,
    TM_FACTOR,
    WEEKLY_HARD_SETS_MIN,
    estimate_weeks_to_target,
    expected_reps_per_week,
)
from .metrics import training_max_from_baseline
from .models import (
    Grip,
    PlannedSet,
    SessionPlan,
    SessionResult,
    SessionType,
    SetResult,
    TrainingStatus,
    UserState,
)


def get_schedule_template(days_per_week: int) -> list[str]:
    """
    Get the weekly session type schedule.

    Args:
        days_per_week: 3 or 4 days per week

    Returns:
        List of session types for the week
    """
    if days_per_week == 4:
        return SCHEDULE_4_DAYS.copy()
    return SCHEDULE_3_DAYS.copy()


def calculate_session_days(
    start_date: datetime,
    days_per_week: int,
    num_weeks: int,
) -> list[tuple[datetime, str]]:
    """
    Calculate dates and session types for a training block.

    Distributes sessions throughout the week with required rest days.

    Args:
        start_date: First day of the plan
        days_per_week: 3 or 4 training days
        num_weeks: Number of weeks to plan

    Returns:
        List of (date, session_type) tuples
    """
    schedule = get_schedule_template(days_per_week)
    sessions: list[tuple[datetime, str]] = []

    current_date = start_date

    for week in range(num_weeks):
        for i, session_type in enumerate(schedule):
            sessions.append((current_date, session_type))

            # Calculate rest days after this session
            min_rest = DAY_SPACING.get(session_type, 1)

            # For 3-day schedules: S-rest-H-rest-E-rest-rest
            # For 4-day schedules: S-rest-H-T-rest-E-rest
            if days_per_week == 3:
                # Simple pattern: every other day, with extra rest on weekends
                if i < len(schedule) - 1:
                    rest_days = max(min_rest, 2)  # At least 2 days between
                else:
                    rest_days = 2  # End of week
            else:
                # 4-day: more compact
                if session_type == "T":
                    rest_days = 1  # T can be followed quickly
                elif i < len(schedule) - 1:
                    rest_days = max(min_rest, 1)
                else:
                    rest_days = 2  # End of week

            current_date = current_date + timedelta(days=rest_days + 1)

    return sessions


def calculate_set_prescription(
    session_type: SessionType,
    training_max: int,
    ff_state,
    bodyweight_kg: float,
    history_sessions: int = 0,
) -> list[PlannedSet]:
    """
    Calculate set prescription for a session.

    Args:
        session_type: Type of session (S, H, E, T, TEST)
        training_max: Current training max
        ff_state: Fitness-fatigue state for autoregulation
        bodyweight_kg: Current bodyweight
        history_sessions: Number of sessions in history (for autoregulation gating)

    Returns:
        List of PlannedSet
    """
    params = SESSION_PARAMS[session_type]

    # Calculate target reps per set
    reps_low = max(params.reps_min, int(training_max * params.reps_fraction_low))
    reps_high = min(params.reps_max, int(training_max * params.reps_fraction_high))
    target_reps = (reps_low + reps_high) // 2
    target_reps = max(params.reps_min, min(params.reps_max, target_reps))

    # Calculate number of sets (middle of range)
    base_sets = (params.sets_min + params.sets_max) // 2

    # Apply autoregulation only when we have enough history (5+ sessions)
    # to properly calibrate the fitness-fatigue model
    if history_sessions >= 5:
        adj_sets, adj_reps = apply_autoregulation(base_sets, target_reps, ff_state)
    else:
        adj_sets, adj_reps = base_sets, target_reps

    # Calculate rest (middle of range)
    rest = (params.rest_min + params.rest_max) // 2

    sets: list[PlannedSet] = []

    if session_type == "E":
        # Endurance: descending ladder
        total_target = training_max * 3  # Total reps target
        current_reps = target_reps
        accumulated = 0

        while accumulated < total_target and len(sets) < params.sets_max:
            actual_reps = max(params.reps_min, current_reps)
            sets.append(
                PlannedSet(
                    target_reps=actual_reps,
                    rest_seconds_before=rest,
                    added_weight_kg=0.0,
                    rir_target=params.rir_target,
                )
            )
            accumulated += actual_reps
            current_reps = max(params.reps_min, current_reps - 1)

    elif session_type == "S":
        # Strength: potentially weighted
        # Weight increases 0.5 kg per TM point above 9, capped at 10 kg
        added_weight = 0.0
        if training_max > 9:
            raw = (training_max - 9) * 0.5
            added_weight = round(raw * 2) / 2  # round to nearest 0.5 kg
            added_weight = min(added_weight, 10.0)

        for i in range(adj_sets):
            sets.append(
                PlannedSet(
                    target_reps=adj_reps,
                    rest_seconds_before=rest,
                    added_weight_kg=added_weight,
                    rir_target=params.rir_target,
                )
            )

    else:
        # H, T, TEST: bodyweight sets
        for i in range(adj_sets):
            sets.append(
                PlannedSet(
                    target_reps=adj_reps,
                    rest_seconds_before=rest,
                    added_weight_kg=0.0,
                    rir_target=params.rir_target,
                )
            )

    return sets


# Grip rotation cycles per session type.
# E and TEST are always pronated for consistency/safety.
_GRIP_CYCLE: dict[str, list[str]] = {
    "S": ["pronated", "neutral", "supinated"],
    "H": ["pronated", "neutral", "supinated"],
    "T": ["pronated", "neutral"],
    "E": ["pronated"],
    "TEST": ["pronated"],
}


def select_grip(session_type: SessionType, history: list[SessionResult]) -> Grip:
    """
    Select appropriate grip for a session (used for one-off lookups).

    For plan generation use _init_grip_counts + _next_grip instead.

    Args:
        session_type: Session type
        history: Training history for alternation

    Returns:
        Selected grip
    """
    cycle = _GRIP_CYCLE.get(session_type, ["pronated"])
    count = sum(1 for s in history if s.session_type == session_type)
    return cycle[count % len(cycle)]  # type: ignore


def _init_grip_counts(history: list[SessionResult]) -> dict[str, int]:
    """Count past sessions of each type from history (for grip rotation)."""
    counts: dict[str, int] = {}
    for s in history:
        counts[s.session_type] = counts.get(s.session_type, 0) + 1
    return counts


def _next_grip(session_type: str, counts: dict[str, int]) -> str:
    """Return next grip for session_type and advance the counter."""
    cycle = _GRIP_CYCLE.get(session_type, ["pronated"])
    grip = cycle[counts.get(session_type, 0) % len(cycle)]
    counts[session_type] = counts.get(session_type, 0) + 1
    return grip


def create_synthetic_test_session(
    date: str,
    bodyweight_kg: float,
    baseline_max: int,
) -> SessionResult:
    """
    Create a synthetic TEST session for initialization.

    Args:
        date: Session date (ISO format)
        bodyweight_kg: Bodyweight
        baseline_max: Baseline max reps

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
        planned_sets=[test_set],
        completed_sets=[test_set],
        notes="Synthetic baseline test",
    )


def generate_plan(
    user_state: UserState,
    start_date: str,
    weeks_ahead: int | None = None,
    baseline_max: int | None = None,
) -> list[SessionPlan]:
    """
    Generate a deterministic training plan with progressive overload.

    Args:
        user_state: Current user state with profile and history
        start_date: Start date for the plan (ISO format)
        weeks_ahead: Number of weeks to plan (None = estimate)
        baseline_max: Baseline max if no history

    Returns:
        List of SessionPlan for the planning horizon
    """
    # Handle empty history
    history = user_state.history.copy()

    if not history and baseline_max is None:
        raise ValueError(
            "No history available. Please provide baseline_max or log a TEST session."
        )

    # If no history, create synthetic test
    if not history:
        today = datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=1)
        synthetic = create_synthetic_test_session(
            today.strftime("%Y-%m-%d"),
            user_state.current_bodyweight_kg,
            baseline_max,  # type: ignore
        )
        history = [synthetic]

    # Get training status
    status = get_training_status(
        history,
        user_state.current_bodyweight_kg,
        baseline_max,
    )

    # Determine initial training max.
    # Start from the latest test max (not floor(0.9 × test_max)) so the plan
    # immediately prescribes at the user's proven level and grows beyond it.
    # status.training_max = floor(0.9 × test_max) is the conventional "safe"
    # starting point, but it causes the plan to spend several weeks just
    # catching back up to the user's actual performance ceiling.
    tm = status.latest_test_max or status.training_max
    if tm <= 1 and baseline_max is not None:
        tm = baseline_max

    # Track TM as float for fractional progression.
    # tm_float is capped at target (drives prescriptions).
    # uncapped_tm_float is NOT capped — used for the Exp column so it
    # continues projecting beyond the user's goal instead of flatting at target.
    tm_float = float(tm)
    uncapped_tm_float = float(tm)
    target = user_state.profile.target_max_reps

    # Determine plan length
    if weeks_ahead is None:
        # Estimate based on progression
        estimated = estimate_weeks_to_target(tm, target)
        weeks_ahead = max(MIN_PLAN_WEEKS, min(DEFAULT_PLAN_WEEKS, estimated))
    else:
        weeks_ahead = max(MIN_PLAN_WEEKS, min(MAX_PLAN_WEEKS, weeks_ahead))

    # Calculate session dates
    start = datetime.strptime(start_date, "%Y-%m-%d")
    session_dates = calculate_session_days(
        start,
        user_state.profile.preferred_days_per_week,
        weeks_ahead,
    )

    # Generate sessions with progressive TM
    plans: list[SessionPlan] = []
    ff_state = status.fitness_fatigue_state
    current_week = 0
    sessions_in_week = 0
    sessions_per_week = user_state.profile.preferred_days_per_week

    # Grip rotation: initialise counters from history so planned sessions
    # continue the rotation seamlessly from where history left off.
    grip_counts = _init_grip_counts(history)

    for date, session_type in session_dates:
        date_str = date.strftime("%Y-%m-%d")

        # Track week transitions and apply progression
        sessions_in_week += 1
        if sessions_in_week > sessions_per_week:
            sessions_in_week = 1
            current_week += 1
            # Apply weekly progression to TM
            progression = expected_reps_per_week(int(tm_float))
            tm_float = min(tm_float + progression, float(target))  # capped for prescriptions
            uncapped_tm_float += progression                        # uncapped for Exp display

        # Use integer TM for prescriptions
        current_tm = int(tm_float)

        # Select grip via rotation (advances counter for this session type)
        grip = _next_grip(session_type, grip_counts)  # type: ignore

        # Calculate sets based on current TM
        sets = calculate_set_prescription(
            session_type,  # type: ignore
            current_tm,
            ff_state,
            user_state.current_bodyweight_kg,
            history_sessions=len(history),
        )

        # Calculate expected TM after this session (assuming completion).
        # Uses uncapped_tm_float so the projection continues past the goal.
        sessions_done_in_week = sessions_in_week
        week_fraction = sessions_done_in_week / sessions_per_week
        week_progression = expected_reps_per_week(current_tm)
        expected_tm_after = int(uncapped_tm_float + week_progression * week_fraction)

        plan = SessionPlan(
            date=date_str,
            grip=grip,
            session_type=session_type,  # type: ignore
            sets=sets,
            expected_tm=expected_tm_after,
            week_number=current_week + 1,
        )
        plans.append(plan)

    return plans


def explain_plan_entry(
    user_state: UserState,
    plan_start_date: str,
    target_date: str,
    weeks_ahead: int | None = None,
    baseline_max: int | None = None,
) -> str:
    """
    Generate a step-by-step Rich-markup explanation of a planned session.

    Re-runs the generate_plan() loop, stops at target_date, and formats
    every intermediate value with its source formula.

    Args:
        user_state: Current user state
        plan_start_date: Start date of the plan (ISO)
        target_date: Date of the session to explain (ISO)
        weeks_ahead: Plan horizon (None = estimate)
        baseline_max: Baseline max if no history

    Returns:
        Rich-markup string ready for console.print()
    """
    history = user_state.history.copy()

    if not history and baseline_max is None:
        return "[yellow]No history available. Run 'init --baseline-max N' first.[/yellow]"

    if not history:
        start_dt = datetime.strptime(plan_start_date, "%Y-%m-%d")
        synthetic = create_synthetic_test_session(
            (start_dt - timedelta(days=1)).strftime("%Y-%m-%d"),
            user_state.current_bodyweight_kg,
            baseline_max,  # type: ignore
        )
        history = [synthetic]

    status = get_training_status(history, user_state.current_bodyweight_kg, baseline_max)
    initial_tm = status.latest_test_max or status.training_max
    if initial_tm <= 1 and baseline_max is not None:
        initial_tm = baseline_max

    ff_state = status.fitness_fatigue_state
    z_score = ff_state.readiness_z_score()

    tm_float = float(initial_tm)
    user_target = user_state.profile.target_max_reps
    days_per_week = user_state.profile.preferred_days_per_week

    if weeks_ahead is None:
        estimated = estimate_weeks_to_target(initial_tm, user_target)
        weeks_ahead = max(MIN_PLAN_WEEKS, min(DEFAULT_PLAN_WEEKS, estimated))
    else:
        weeks_ahead = max(MIN_PLAN_WEEKS, min(MAX_PLAN_WEEKS, weeks_ahead))

    start = datetime.strptime(plan_start_date, "%Y-%m-%d")
    session_dates = calculate_session_days(start, days_per_week, weeks_ahead)
    schedule = get_schedule_template(days_per_week)

    grip_counts = _init_grip_counts(history)
    grip_history_counts = dict(grip_counts)
    sessions_in_week = 0
    current_week = 0
    sessions_per_week = days_per_week
    weekly_log: list[tuple[int, float, float, float]] = []  # (week, prog, tm_before, tm_after)

    TYPE_NAMES = {
        "S": "Strength", "H": "Hypertrophy", "E": "Endurance",
        "T": "Technique", "TEST": "Max Test",
    }

    for date, session_type in session_dates:
        date_str = date.strftime("%Y-%m-%d")
        sessions_in_week += 1

        if sessions_in_week > sessions_per_week:
            sessions_in_week = 1
            current_week += 1
            prog = expected_reps_per_week(int(tm_float))
            old_tm = tm_float
            tm_float = min(tm_float + prog, float(user_target))
            weekly_log.append((current_week, prog, old_tm, tm_float))

        current_tm = int(tm_float)
        count_before = grip_counts.get(session_type, 0)
        grip = _next_grip(session_type, grip_counts)
        cycle = _GRIP_CYCLE.get(session_type, ["pronated"])

        week_num = current_week + 1
        week_fraction = sessions_in_week / sessions_per_week
        week_prog = expected_reps_per_week(current_tm)
        expected_tm_after = int(min(tm_float + week_prog * week_fraction, float(user_target)))

        if date_str != target_date:
            continue

        # ── Found the target session — build explanation ────────────────────
        params = SESSION_PARAMS[session_type]
        type_name = TYPE_NAMES.get(session_type, session_type)

        reps_low = max(params.reps_min, int(current_tm * params.reps_fraction_low))
        reps_high = min(params.reps_max, int(current_tm * params.reps_fraction_high))
        base_reps = (reps_low + reps_high) // 2
        base_reps = max(params.reps_min, min(params.reps_max, base_reps))
        base_sets = (params.sets_min + params.sets_max) // 2
        rest = (params.rest_min + params.rest_max) // 2
        has_autoreg = len(history) >= 5

        adj_sets = base_sets
        adj_reps = base_reps
        if has_autoreg:
            if z_score < READINESS_Z_LOW:
                adj_sets = max(3, int(base_sets * (1 - READINESS_VOLUME_REDUCTION)))
            elif z_score > READINESS_Z_HIGH:
                adj_reps = base_reps + 1

        added_weight = 0.0
        if session_type == "S" and current_tm > 9:
            raw_w = (current_tm - 9) * 0.5
            added_weight = round(raw_w * 2) / 2
            added_weight = min(added_weight, 10.0)

        rule = "─" * 54
        L: list[str] = []

        # Header
        L.append(
            f"[bold cyan]{type_name} ({session_type})"
            f"  ·  {date_str}"
            f"  ·  Week {week_num}, session {sessions_in_week}/{sessions_per_week}[/bold cyan]"
        )
        L.append(rule)

        # SESSION TYPE
        L.append("\n[bold]SESSION TYPE[/bold]")
        L.append(f"  {days_per_week}-day schedule template: [cyan]{' → '.join(schedule)}[/cyan] (repeating weekly).")
        L.append(f"  Week {week_num}, slot {sessions_in_week}/{sessions_per_week} → [magenta]{session_type}[/magenta].")

        # GRIP
        hist_count = grip_history_counts.get(session_type, 0)
        plan_count = count_before - hist_count
        cycle_str = " → ".join(cycle)
        L.append(f"\n[bold]GRIP: {grip}[/bold]")
        L.append(f"  {session_type} sessions rotate: [cyan]{cycle_str}[/cyan] ({len(cycle)}-step cycle).")
        L.append(f"  In history: {hist_count} {session_type} session(s).")
        if plan_count > 0:
            L.append(f"  In this plan before {date_str}: {plan_count} {session_type} session(s).")
        L.append(f"  Total before this session: {count_before}.")
        L.append(
            f"  {count_before} mod {len(cycle)} = [bold]{count_before % len(cycle)}[/bold]"
            f" → [green]{grip}[/green]."
        )

        # TRAINING MAX
        L.append(f"\n[bold]TRAINING MAX: {current_tm}[/bold]")
        test_sessions = [s for s in history if s.session_type == "TEST"]
        if test_sessions:
            latest_test = max(test_sessions, key=lambda s: s.date)
            latest_max = max(
                (s.actual_reps for s in latest_test.completed_sets if s.actual_reps),
                default=0,
            )
            tm_from_test = int(TM_FACTOR * latest_max)
            L.append(f"  Latest TEST: {latest_max} reps on {latest_test.date}.")
            L.append(
                f"  Starting TM = floor({TM_FACTOR} × {latest_max}) = {tm_from_test}."
            )
        else:
            L.append(f"  Starting TM: {initial_tm}.")
        if weekly_log:
            L.append("  Progression by week:")
            for wk, prog, before, after in weekly_log:
                L.append(
                    f"    Week {wk}: TM {before:.2f} + {prog:.2f} = [bold]{after:.2f}[/bold]"
                    f" (int = {int(after)})"
                )
        else:
            L.append("  No weekly progression yet (first week of plan).")
        L.append(f"  → TM for this session: int({tm_float:.2f}) = [bold green]{current_tm}[/bold green].")

        # SETS
        L.append(f"\n[bold]SETS: {adj_sets}[/bold]")
        L.append(
            f"  {session_type} config: sets [{params.sets_min}–{params.sets_max}]."
            f"  Base = ({params.sets_min}+{params.sets_max})//2 = {base_sets}."
        )
        L.append(
            f"  Readiness z-score: {z_score:+.2f}"
            f"  (thresholds: low={READINESS_Z_LOW}, high=+{READINESS_Z_HIGH})."
        )
        if not has_autoreg:
            L.append(f"  Autoregulation: [dim]off[/dim] (need ≥ 5 sessions, have {len(history)}).")
        elif z_score < READINESS_Z_LOW:
            L.append(
                f"  z < {READINESS_Z_LOW} → reduce by {int(READINESS_VOLUME_REDUCTION*100)}%:"
                f" max(3, {int(base_sets*(1-READINESS_VOLUME_REDUCTION))}) = [bold]{adj_sets}[/bold]."
            )
        elif z_score > READINESS_Z_HIGH:
            L.append(f"  z > +{READINESS_Z_HIGH} → sets unchanged, +1 rep (see Reps).")
        else:
            L.append(f"  z in [{READINESS_Z_LOW}, +{READINESS_Z_HIGH}] → no change.")
        L.append(f"  → [bold green]{adj_sets} sets[/bold green].")

        # REPS
        L.append(f"\n[bold]REPS PER SET: {adj_reps}[/bold]")
        L.append(
            f"  {session_type} config: fraction [{params.reps_fraction_low}–{params.reps_fraction_high}]"
            f" of TM, clamped to [{params.reps_min}–{params.reps_max}]."
        )
        L.append(
            f"  Low  = max({params.reps_min}, int({current_tm} × {params.reps_fraction_low}))"
            f" = max({params.reps_min}, {int(current_tm * params.reps_fraction_low)}) = {reps_low}."
        )
        L.append(
            f"  High = min({params.reps_max}, int({current_tm} × {params.reps_fraction_high}))"
            f" = min({params.reps_max}, {int(current_tm * params.reps_fraction_high)}) = {reps_high}."
        )
        L.append(
            f"  Target = ({reps_low}+{reps_high})//2 = {(reps_low+reps_high)//2},"
            f" clamped to [{params.reps_min}–{params.reps_max}] → {base_reps}."
        )
        if has_autoreg and z_score > READINESS_Z_HIGH:
            L.append(f"  High readiness (z={z_score:+.2f} > +{READINESS_Z_HIGH}) → +1 rep → {adj_reps}.")
        L.append(f"  → [bold green]{adj_reps} reps/set[/bold green].")

        # WEIGHT (S) or VOLUME (E)
        if session_type == "S":
            L.append(f"\n[bold]ADDED WEIGHT: {added_weight:.1f} kg[/bold]")
            if current_tm > 9:
                raw_w = (current_tm - 9) * 0.5
                rounded = round(raw_w * 2) / 2
                L.append(f"  TM = {current_tm} > 9 → ({current_tm} − 9) × 0.5 = {raw_w:.1f} kg.")
                L.append(
                    f"  Rounded to nearest 0.5 kg: {rounded:.1f} kg."
                    f"  Cap at 10 kg → [bold green]{added_weight:.1f} kg[/bold green]."
                )
            else:
                L.append(f"  TM = {current_tm} ≤ 9 → bodyweight only (0 kg added).")
        elif session_type == "E":
            total_target = current_tm * 3
            L.append("\n[bold]VOLUME (Endurance — descending ladder)[/bold]")
            L.append(
                f"  Total target = TM × 3 = {current_tm} × 3 = {total_target} reps."
            )
            L.append(
                f"  Starting at {base_reps} reps/set, decreasing by 1 each set"
                f" (min {params.reps_min})."
            )
            L.append(
                f"  Stops when accumulated ≥ {total_target} reps or {params.sets_max} sets reached."
            )

        # REST
        L.append(f"\n[bold]REST: {rest} s[/bold]")
        L.append(
            f"  {session_type} config: rest [{params.rest_min}–{params.rest_max}] s."
            f"  rest = ({params.rest_min}+{params.rest_max})//2 = {rest} s."
        )

        # EXPECTED TM AFTER
        L.append(f"\n[bold]EXPECTED TM AFTER: {expected_tm_after}[/bold]")
        L.append(
            f"  Session {sessions_in_week}/{sessions_per_week} in week"
            f" → fraction = {week_fraction:.2f}."
        )
        L.append(f"  Progression rate at TM {current_tm}: {week_prog:.2f} reps/week.")
        L.append(f"  Δ TM = {week_prog:.2f} × {week_fraction:.2f} = {week_prog*week_fraction:.2f} reps.")
        L.append(
            f"  → int(min({tm_float:.2f} + {week_prog*week_fraction:.2f}, {user_target}))"
            f" = [bold green]{expected_tm_after}[/bold green]."
        )

        return "\n".join(L)

    return (
        f"[yellow]No planned session found for {target_date}.[/yellow]\n"
        f"Is this date within the {weeks_ahead}-week plan horizon starting {plan_start_date}?"
    )


def estimate_plan_completion_date(
    user_state: UserState,
    baseline_max: int | None = None,
) -> str | None:
    """
    Estimate when the user might reach their target.

    Args:
        user_state: Current user state
        baseline_max: Baseline max if no history

    Returns:
        Estimated completion date (ISO format) or None if target reached
    """
    status = get_training_status(
        user_state.history,
        user_state.current_bodyweight_kg,
        baseline_max,
    )

    tm = status.training_max
    target = user_state.profile.target_max_reps

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
