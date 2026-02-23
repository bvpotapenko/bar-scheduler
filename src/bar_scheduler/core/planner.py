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
    DROP_OFF_THRESHOLD,
    MAX_ADDED_WEIGHT_KG,
    MAX_PLAN_WEEKS,
    MIN_PLAN_WEEKS,
    MIN_SESSIONS_FOR_AUTOREG,
    READINESS_VOLUME_REDUCTION,
    READINESS_Z_HIGH,
    READINESS_Z_LOW,
    SCHEDULE_3_DAYS,
    SCHEDULE_4_DAYS,
    SESSION_PARAMS,
    TM_FACTOR,
    WEEKLY_HARD_SETS_MIN,
    WEIGHT_INCREMENT_FRACTION_PER_TM,
    WEIGHT_TM_THRESHOLD,
    endurance_volume_multiplier,
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


def get_next_session_type_index(
    history: list[SessionResult],
    schedule: list[str],
) -> int:
    """
    Return the schedule index for the next planned session.

    Looks at the last non-TEST session in history to determine where
    the rotation left off, then returns the next index in the cycle.

    TEST sessions are skipped because they are not part of the regular
    S/H/T/E rotation.

    Args:
        history: Training history (sorted chronologically)
        schedule: Session type schedule (e.g. ["S", "H", "T", "E"])

    Returns:
        Index into schedule for the first planned session
    """
    non_test = [s for s in history if s.session_type != "TEST"]
    if not non_test:
        return 0
    last_type = non_test[-1].session_type
    if last_type in schedule:
        return (schedule.index(last_type) + 1) % len(schedule)
    return 0


def calculate_session_days(
    start_date: datetime,
    days_per_week: int,
    num_weeks: int,
    start_rotation_idx: int = 0,
) -> list[tuple[datetime, str]]:
    """
    Calculate dates and session types for a training block.

    Distributes sessions throughout the week with required rest days.

    Args:
        start_date: First day of the plan
        days_per_week: 3 or 4 training days
        num_weeks: Number of weeks to plan
        start_rotation_idx: Index into the schedule to start from (for
            continuing the S/H/T/E rotation after history). Default 0.

    Returns:
        List of (date, session_type) tuples
    """
    schedule = get_schedule_template(days_per_week)
    # Rotate schedule so the plan continues the S/H/T/E cycle from history.
    if start_rotation_idx > 0:
        schedule = schedule[start_rotation_idx:] + schedule[:start_rotation_idx]
    sessions: list[tuple[datetime, str]] = []

    # Fixed day offsets within each 7-day week:
    #   3-day: Mon(0), Wed(2), Fri(4) — 1 rest day between sessions
    #   4-day: Mon(0), Tue(1), Thu(3), Sat(5) — compact with 1 rest before T
    if days_per_week == 4:
        day_offsets = [0, 1, 3, 5]
    else:
        day_offsets = [0, 2, 4]

    for week in range(num_weeks):
        week_start = start_date + timedelta(days=week * 7)
        for i, session_type in enumerate(schedule):
            session_date = week_start + timedelta(days=day_offsets[i])
            sessions.append((session_date, session_type))

    return sessions


def calculate_adaptive_rest(
    session_type: SessionType,
    recent_sessions: list[SessionResult],
    ff_state,
) -> int:
    """
    Calculate adaptive rest based on recent same-type session performance and readiness.

    Adjustments from midpoint:
    - Any set with RIR <= 1: +30s (session was near failure)
    - Drop-off > DROP_OFF_THRESHOLD: +15s (within-session fatigue)
    - Readiness z-score < READINESS_Z_LOW: +30s (low readiness)
    - All sets RIR >= 3: -15s (session felt easy)
    Clamped to [rest_min, rest_max].

    Args:
        session_type: Session type
        recent_sessions: Last few sessions of this same type from history
        ff_state: Fitness-fatigue state

    Returns:
        Recommended rest in seconds
    """
    params = SESSION_PARAMS[session_type]
    rest = (params.rest_min + params.rest_max) // 2

    if not recent_sessions:
        return rest

    last = recent_sessions[-1]
    sets = [s for s in last.completed_sets if s.actual_reps is not None]

    if not sets:
        return rest

    # RIR analysis
    rirs = [s.rir_reported for s in sets if s.rir_reported is not None]
    if rirs:
        if any(r <= 1 for r in rirs):
            rest += 30  # any set near failure
        elif all(r >= 3 for r in rirs):
            rest -= 15  # all sets easy

    # Drop-off analysis: compare first vs last set reps
    reps_list = [s.actual_reps for s in sets if s.actual_reps is not None]
    if len(reps_list) >= 2 and reps_list[0] > 0:
        drop_off = (reps_list[0] - reps_list[-1]) / reps_list[0]
        if drop_off > DROP_OFF_THRESHOLD:
            rest += 15

    # Readiness z-score
    if ff_state is not None:
        readiness = ff_state.fitness - ff_state.fatigue
        readiness_var = max(ff_state.readiness_var, 0.01)
        import math
        z = (readiness - ff_state.readiness_mean) / math.sqrt(readiness_var)
        if z < READINESS_Z_LOW:
            rest += 30

    return max(params.rest_min, min(params.rest_max, rest))


def calculate_set_prescription(
    session_type: SessionType,
    training_max: int,
    ff_state,
    bodyweight_kg: float,
    history_sessions: int = 0,
    recent_same_type: list[SessionResult] | None = None,
) -> list[PlannedSet]:
    """
    Calculate set prescription for a session.

    Args:
        session_type: Type of session (S, H, E, T, TEST)
        training_max: Current training max
        ff_state: Fitness-fatigue state for autoregulation
        bodyweight_kg: Current bodyweight
        history_sessions: Number of sessions in history (for autoregulation gating)
        recent_same_type: Recent sessions of the same type (for adaptive rest)

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

    # Apply autoregulation only when we have enough history to properly
    # calibrate the fitness-fatigue model
    if history_sessions >= MIN_SESSIONS_FOR_AUTOREG:
        adj_sets, adj_reps = apply_autoregulation(base_sets, target_reps, ff_state)
    else:
        adj_sets, adj_reps = base_sets, target_reps

    # Adaptive rest based on recent same-type sessions and readiness
    rest = calculate_adaptive_rest(session_type, recent_same_type or [], ff_state)

    sets: list[PlannedSet] = []

    if session_type == "E":
        # Endurance: descending ladder
        total_target = int(endurance_volume_multiplier(training_max) * training_max)
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
        # Weight = bodyweight × 1% per TM point above threshold, rounded to 0.5 kg
        added_weight = 0.0
        if training_max > WEIGHT_TM_THRESHOLD:
            points_above = training_max - WEIGHT_TM_THRESHOLD
            raw = bodyweight_kg * WEIGHT_INCREMENT_FRACTION_PER_TM * points_above
            added_weight = round(raw * 2) / 2  # round to nearest 0.5 kg
            added_weight = min(added_weight, MAX_ADDED_WEIGHT_KG)

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
    """Return next grip for session_type and increment counts[session_type] in-place."""
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
    # Always start from training_max = floor(0.9 × test_max) per TM_FACTOR.
    # This is the conventional conservative base; prescriptions build from here.
    tm = status.training_max
    if tm <= 1 and baseline_max is not None:
        tm = int(baseline_max * TM_FACTOR) or baseline_max

    # Track TM as float for fractional progression.
    # Neither tm_float nor uncapped_tm_float is capped at target — prescriptions
    # continue past the target so users can progress beyond it.
    # The target is only used for estimating plan length.
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

    # Calculate session dates, resuming the S/H/T/E rotation from history.
    start = datetime.strptime(start_date, "%Y-%m-%d")
    schedule = get_schedule_template(user_state.profile.preferred_days_per_week)
    start_rotation_idx = get_next_session_type_index(history, schedule)
    session_dates = calculate_session_days(
        start,
        user_state.profile.preferred_days_per_week,
        weeks_ahead,
        start_rotation_idx=start_rotation_idx,
    )

    # Compute cumulative week offset from the very first session in history.
    # This ensures week_number in planned sessions reflects continuous training
    # weeks rather than resetting to 1 on every plan regeneration.
    original_history = user_state.history  # pre-synthetic
    if original_history:
        first_date = datetime.strptime(original_history[0].date, "%Y-%m-%d")
        week_offset = (start - first_date).days // 7
    else:
        week_offset = 0

    # Generate sessions with progressive TM
    plans: list[SessionPlan] = []
    ff_state = status.fitness_fatigue_state

    # Grip rotation: initialise counters from history so planned sessions
    # continue the rotation seamlessly from where history left off.
    grip_counts = _init_grip_counts(history)

    # Weekly progression tracking: apply progression once per calendar week
    # (not per session-count cycle) to avoid multiplying by sessions/week.
    current_plan_week_idx = 0  # Calendar week index within this plan (0-based)

    for date, session_type in session_dates:
        date_str = date.strftime("%Y-%m-%d")

        # Calendar week index within this plan (0 = first plan week)
        session_week_idx = (date - start).days // 7

        # Apply progression exactly once when entering a new calendar week
        if session_week_idx > current_plan_week_idx:
            progression = expected_reps_per_week(int(tm_float))
            tm_float += progression
            uncapped_tm_float += progression
            current_plan_week_idx = session_week_idx

        # Use integer TM for prescriptions
        current_tm = int(tm_float)

        # Select grip via rotation (advances counter for this session type)
        grip = _next_grip(session_type, grip_counts)  # type: ignore

        # Calculate sets based on current TM
        recent_same_type = [s for s in history if s.session_type == session_type][-5:]
        sets = calculate_set_prescription(
            session_type,  # type: ignore
            current_tm,
            ff_state,
            user_state.current_bodyweight_kg,
            history_sessions=len(history),
            recent_same_type=recent_same_type,
        )

        # All sessions in the same calendar week show the same expected_tm.
        # Progression is applied at week boundaries, not fractionally per session.
        expected_tm_after = int(uncapped_tm_float)

        plan = SessionPlan(
            date=date_str,
            grip=grip,
            session_type=session_type,  # type: ignore
            sets=sets,
            expected_tm=expected_tm_after,
            week_number=week_offset + session_week_idx + 1,  # cumulative from first history session
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
    initial_tm = status.training_max
    if initial_tm <= 1 and baseline_max is not None:
        initial_tm = int(baseline_max * TM_FACTOR) or baseline_max

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
    schedule = get_schedule_template(days_per_week)
    start_rotation_idx = get_next_session_type_index(history, schedule)
    session_dates = calculate_session_days(start, days_per_week, weeks_ahead, start_rotation_idx)

    # Cumulative week offset from first history session
    original_history = user_state.history
    if original_history:
        first_date = datetime.strptime(original_history[0].date, "%Y-%m-%d")
        week_offset = (start - first_date).days // 7
    else:
        week_offset = 0

    grip_counts = _init_grip_counts(history)
    grip_history_counts = dict(grip_counts)
    current_plan_week_idx = 0  # calendar week index within plan
    weekly_log: list[tuple[int, float, float, float]] = []  # (week, prog, tm_before, tm_after)

    TYPE_NAMES = {
        "S": "Strength", "H": "Hypertrophy", "E": "Endurance",
        "T": "Technique", "TEST": "Max Test",
    }

    for date, session_type in session_dates:
        date_str = date.strftime("%Y-%m-%d")
        session_week_idx = (date - start).days // 7

        if session_week_idx > current_plan_week_idx:
            prog = expected_reps_per_week(int(tm_float))
            old_tm = tm_float
            tm_float += prog
            weekly_log.append((week_offset + session_week_idx, prog, old_tm, tm_float))
            current_plan_week_idx = session_week_idx

        current_tm = int(tm_float)
        count_before = grip_counts.get(session_type, 0)
        grip = _next_grip(session_type, grip_counts)
        cycle = _GRIP_CYCLE.get(session_type, ["pronated"])

        week_num = week_offset + session_week_idx + 1
        expected_tm_after = int(tm_float)  # same for all sessions in same week

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
        has_autoreg = len(history) >= MIN_SESSIONS_FOR_AUTOREG

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
            f"  ·  Week {week_num}[/bold cyan]"
        )
        L.append(rule)

        # SESSION TYPE
        L.append("\n[bold]SESSION TYPE[/bold]")
        L.append(f"  {days_per_week}-day schedule template: [cyan]{' → '.join(schedule)}[/cyan] (repeating weekly).")
        L.append(f"  Week {week_num} → [magenta]{session_type}[/magenta].")

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
            L.append(f"  Autoregulation: [dim]off[/dim] (need ≥ {MIN_SESSIONS_FOR_AUTOREG} sessions, have {len(history)}).")
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
            ke = endurance_volume_multiplier(current_tm)
            total_target = int(ke * current_tm)
            L.append("\n[bold]VOLUME (Endurance — descending ladder)[/bold]")
            L.append(
                f"  kE(TM={current_tm}) = 3.0 + 2.0 × clip(({current_tm}-5)/25, 0, 1) = {ke:.2f}."
            )
            L.append(
                f"  Total target = kE × TM = {ke:.2f} × {current_tm} = {total_target} reps."
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
        next_week_tm = tm_float + expected_reps_per_week(current_tm)
        L.append(f"\n[bold]EXPECTED TM AFTER: {expected_tm_after}[/bold]")
        L.append(f"  TM is updated once per calendar week boundary.")
        L.append(f"  Current TM (this week): int({tm_float:.2f}) = {current_tm}.")
        L.append(
            f"  Next week's TM ≈ {tm_float:.2f} + {expected_reps_per_week(current_tm):.2f}"
            f" = {next_week_tm:.2f} → int = {int(next_week_tm)}."
        )
        L.append(
            f"  → [bold green]{expected_tm_after}[/bold green] (this week's TM, shown consistently"
            f" for all sessions in week {week_num})."
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
