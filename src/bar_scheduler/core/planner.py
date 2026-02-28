"""
Plan generation for bar-scheduler.

Generates deterministic multi-week training plans based on
current status, history, and adaptation rules.  The plan is
parameterised by an ExerciseDefinition so the same engine works
for pull-ups, dips, BSS, and any future exercise.
"""

from dataclasses import dataclass
from typing import Any, Generator
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
    MAX_PLAN_WEEKS,
    MIN_PLAN_WEEKS,
    MIN_SESSIONS_FOR_AUTOREG,
    READINESS_VOLUME_REDUCTION,
    READINESS_Z_HIGH,
    READINESS_Z_LOW,
    SCHEDULE_1_DAY,
    SCHEDULE_2_DAYS,
    SCHEDULE_3_DAYS,
    SCHEDULE_4_DAYS,
    SCHEDULE_5_DAYS,
    TM_FACTOR,
    WEEKLY_HARD_SETS_MIN,
    endurance_volume_multiplier,
    estimate_weeks_to_target,
    expected_reps_per_week,
)
from .exercises.base import ExerciseDefinition, SessionTypeParams
from .exercises.registry import get_exercise

PULL_UP = get_exercise("pull_up")
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


@dataclass
class _SessionTrace:
    """
    All intermediate values from _plan_core() for one session.

    Consumed by _format_explain() to produce the step-by-step explanation
    without any re-computation or divergence from the plan.
    """

    # Identity
    date_str: str
    session_type: str
    session_week_idx: int
    week_num: int
    week_offset: int
    weeks_ahead: int

    # Grip / variant
    grip: str
    cycle: list
    count_before: int       # grip count before this session (history + prior plan)
    hist_count: int         # grip count from history only

    # Training max
    initial_tm: int
    current_tm: int
    tm_float: float
    weekly_log: list        # [(abs_week_idx, prog, tm_before, tm_after), ...]

    # Sets / reps
    base_sets: int
    base_reps: int
    adj_sets: int
    adj_reps: int
    has_autoreg: bool
    z_score: float
    reps_low: int
    reps_high: int

    # Weight
    added_weight: float
    last_test_weight: float

    # Rest
    adj_rest: int
    recent_same_type: list  # last 5 same-type history sessions

    # Expected TM
    expected_tm_after: int

    # Plan context
    history: list           # filtered exercise history (non-REST)
    history_len: int
    days_per_week: int
    user_target: int
    schedule: list

    # Typed config objects
    params: SessionTypeParams
    exercise: ExerciseDefinition
    ff_state: Any           # FitnessFatigueState

    # Overtraining shift (0 = not shifted)
    overtraining_shift_days: int = 0
    overtraining_level: int = 0


def get_schedule_template(days_per_week: int) -> list[str]:
    """
    Get the weekly session type schedule.

    Args:
        days_per_week: 1–5 days per week

    Returns:
        List of session types for the week
    """
    if days_per_week == 1:
        return SCHEDULE_1_DAY.copy()
    if days_per_week == 2:
        return SCHEDULE_2_DAYS.copy()
    if days_per_week == 4:
        return SCHEDULE_4_DAYS.copy()
    if days_per_week == 5:
        return SCHEDULE_5_DAYS.copy()
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
    non_test = [s for s in history if s.session_type not in ("TEST", "REST")]
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
    #   1-day: Mon(0)
    #   2-day: Mon(0), Thu(3) — evenly spaced
    #   3-day: Mon(0), Wed(2), Fri(4) — 1 rest day between sessions
    #   4-day: Mon(0), Tue(1), Thu(3), Sat(5) — compact with 1 rest before T
    #   5-day: Mon(0), Tue(1), Wed(2), Fri(4), Sat(5) — midweek rest Thu
    if days_per_week == 1:
        day_offsets = [0]
    elif days_per_week == 2:
        day_offsets = [0, 3]
    elif days_per_week == 4:
        day_offsets = [0, 1, 3, 5]
    elif days_per_week == 5:
        day_offsets = [0, 1, 2, 4, 5]
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
    exercise: ExerciseDefinition = PULL_UP,
) -> int:
    """
    Calculate adaptive rest based on recent same-type session performance and readiness.

    Adjustments from midpoint:
    - Any set with RIR <= 1: +30s (session was near failure)
    - Drop-off > DROP_OFF_THRESHOLD: +15s (within-session fatigue)
    - Readiness z-score < READINESS_Z_LOW: +30s (low readiness)
    - All sets RIR >= 3: -15s (session felt easy)
    - Avg actual rest across sessions < rest_min*0.85: -20s (user rests short)
    - Avg actual rest across sessions > rest_max*1.10: +20s (user needs more rest)
    Clamped to [rest_min, rest_max].

    Args:
        session_type: Session type
        recent_sessions: Last few sessions of this same type from history
        ff_state: Fitness-fatigue state
        exercise: ExerciseDefinition with session params

    Returns:
        Recommended rest in seconds
    """
    params = exercise.session_params[session_type]
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

    # Rest-adherence signal: if the user consistently rests well outside the
    # prescribed range across recent sessions, shift the prescription toward
    # their actual pattern. rest_seconds_before=0 means first set — excluded.
    actual_rests = [
        s.rest_seconds_before
        for session in recent_sessions
        for s in session.completed_sets
        if s.rest_seconds_before > 0
    ]
    if len(actual_rests) >= 3:
        avg_actual = sum(actual_rests) / len(actual_rests)
        if avg_actual < params.rest_min * 0.85:
            rest -= 20  # user consistently rests short → lower prescription
        elif avg_actual > params.rest_max * 1.10:
            rest += 20  # user needs more rest than max → raise prescription

    return max(params.rest_min, min(params.rest_max, rest))


def _calculate_added_weight(
    exercise: ExerciseDefinition,
    training_max: int,
    bodyweight_kg: float,
    last_test_weight: float = 0.0,
) -> float:
    """
    Calculate added weight for a Strength session.

    For bw_plus_external exercises:
        added = (BW × bw_fraction) × weight_increment_fraction × (TM - threshold)
        rounded to nearest 0.5 kg, capped at max_added_weight_kg.

    For external_only exercises (BSS):
        Use the dumbbell weight from the last TEST session (last_test_weight).

    Args:
        exercise: Exercise definition
        training_max: Current training max
        bodyweight_kg: Current bodyweight
        last_test_weight: Added weight from last TEST session (used for BSS)

    Returns:
        Added weight in kg
    """
    if exercise.load_type == "external_only":
        return last_test_weight

    if training_max <= exercise.weight_tm_threshold:
        return 0.0

    pts = training_max - exercise.weight_tm_threshold
    eff_bw = bodyweight_kg * exercise.bw_fraction
    raw = eff_bw * exercise.weight_increment_fraction * pts
    rounded = round(raw * 2) / 2  # nearest 0.5 kg
    return min(rounded, exercise.max_added_weight_kg)


def _insert_test_sessions(
    session_dates: list[tuple[datetime, str]],
    history: list[SessionResult],
    test_frequency_weeks: int,
    plan_start: datetime,
) -> list[tuple[datetime, str]]:
    """
    Insert TEST sessions at configured intervals.

    Replaces the regular session on the day a TEST becomes due.

    Args:
        session_dates: Original (date, session_type) list
        history: Training history
        test_frequency_weeks: How often to schedule a TEST
        plan_start: Plan start date (used as fallback for last_test calculation)

    Returns:
        Modified session list with TEST sessions injected
    """
    test_hist = [s for s in history if s.session_type == "TEST"]
    if test_hist:
        last_test = datetime.strptime(test_hist[-1].date, "%Y-%m-%d")
    else:
        # Treat plan start as if test was due right before (trigger at first week boundary)
        last_test = plan_start - timedelta(days=test_frequency_weeks * 7)

    result: list[tuple[datetime, str]] = []
    for date, stype in session_dates:
        if (date - last_test).days >= test_frequency_weeks * 7:
            result.append((date, "TEST"))
            last_test = date
        else:
            result.append((date, stype))
    return result


def calculate_set_prescription(
    session_type: SessionType,
    training_max: int,
    ff_state,
    bodyweight_kg: float,
    history_sessions: int = 0,
    recent_same_type: list[SessionResult] | None = None,
    exercise: ExerciseDefinition = PULL_UP,
    last_test_weight: float = 0.0,
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
        exercise: ExerciseDefinition with session params and weight formula
        last_test_weight: Added weight from last TEST session (used for BSS)

    Returns:
        List of PlannedSet
    """
    params = exercise.session_params[session_type]

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
    rest = calculate_adaptive_rest(session_type, recent_same_type or [], ff_state, exercise)

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
        added_weight = _calculate_added_weight(exercise, training_max, bodyweight_kg, last_test_weight)
        for _ in range(adj_sets):
            sets.append(
                PlannedSet(
                    target_reps=adj_reps,
                    rest_seconds_before=rest,
                    added_weight_kg=added_weight,
                    rir_target=params.rir_target,
                )
            )

    else:
        # H, T, TEST: bodyweight sets (no added weight)
        for _ in range(adj_sets):
            sets.append(
                PlannedSet(
                    target_reps=adj_reps,
                    rest_seconds_before=rest,
                    added_weight_kg=0.0,
                    rir_target=params.rir_target,
                )
            )

    return sets


def select_grip(
    session_type: SessionType,
    history: list[SessionResult],
    exercise: ExerciseDefinition = PULL_UP,
) -> Grip:
    """
    Select appropriate grip/variant for a session (one-off lookup).

    For plan generation use _init_grip_counts + _next_grip instead.

    Args:
        session_type: Session type
        history: Training history for alternation
        exercise: ExerciseDefinition with grip_cycles

    Returns:
        Selected grip/variant
    """
    cycle = exercise.grip_cycles.get(session_type, [exercise.primary_variant])
    count = sum(1 for s in history if s.session_type == session_type)
    return cycle[count % len(cycle)]  # type: ignore


def _init_grip_counts(
    history: list[SessionResult],
    exercise: ExerciseDefinition = PULL_UP,
) -> dict[str, int]:
    """
    Count past sessions of each type from history for grip rotation.

    Only counts sessions for the specified exercise so that a dip plan
    doesn't inherit pull-up grip rotation counts.
    Returns empty dict when the exercise has no variant rotation.
    """
    if not exercise.has_variant_rotation:
        return {}
    counts: dict[str, int] = {}
    for s in history:
        if s.exercise_id == exercise.exercise_id and s.session_type != "REST":
            counts[s.session_type] = counts.get(s.session_type, 0) + 1
    return counts


def _next_grip(
    session_type: str,
    counts: dict[str, int],
    exercise: ExerciseDefinition = PULL_UP,
) -> str:
    """Return next grip/variant for session_type and increment counts in-place."""
    cycle = exercise.grip_cycles.get(session_type, [exercise.primary_variant])
    grip = cycle[counts.get(session_type, 0) % len(cycle)]
    counts[session_type] = counts.get(session_type, 0) + 1
    return grip


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

    # Filter history: this exercise only, REST records excluded
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

    status = get_training_status(history, user_state.current_bodyweight_kg, baseline_max)
    initial_tm = status.training_max
    if initial_tm <= 1 and baseline_max is not None:
        initial_tm = int(baseline_max * TM_FACTOR) or baseline_max

    ff_state = status.fitness_fatigue_state
    z_score = ff_state.readiness_z_score()

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
    start_rotation_idx = get_next_session_type_index(history, schedule)
    session_dates = calculate_session_days(
        start, days_per_week, weeks_ahead, start_rotation_idx
    )
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

    # Grip rotation: initialise from history so the plan continues seamlessly
    grip_counts = _init_grip_counts(history, exercise)
    grip_history_counts = dict(grip_counts)   # snapshot of history-only counts

    # Pre-index history by session type for O(1) lookup in the loop
    history_by_type: dict[str, list] = {}
    for s in history:
        history_by_type.setdefault(s.session_type, []).append(s)

    # BSS: carry dumbbell weight from the last TEST session
    last_test_weight = 0.0
    if exercise.load_type == "external_only":
        test_hist = [s for s in history if s.session_type == "TEST"]
        if test_hist and test_hist[-1].completed_sets:
            weights = [
                s.added_weight_kg for s in test_hist[-1].completed_sets
                if s.added_weight_kg > 0
            ]
            if weights:
                last_test_weight = weights[-1]

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
        has_autoreg = len(history) >= MIN_SESSIONS_FOR_AUTOREG

        if has_autoreg:
            adj_sets, adj_reps = apply_autoregulation(base_sets, base_reps, ff_state)
        else:
            adj_sets, adj_reps = base_sets, base_reps

        recent_same_type = history_by_type.get(session_type, [])[-5:]
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
            history_sessions=len(history),
            recent_same_type=recent_same_type,
            exercise=exercise,
            last_test_weight=last_test_weight,
        )

        # Overtraining protection: adjust the first density_sessions_left sessions
        if density_sessions_left > 0 and session_type not in ("TEST", "REST"):
            rest_boost = 30 if overtraining_level == 1 else 60
            from dataclasses import replace as _dc_replace
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


def _format_explain(trace: _SessionTrace, bodyweight_kg: float) -> str:
    """
    Format a _SessionTrace into a Rich-markup step-by-step explanation.

    Pure formatter: no computation, no side-effects.
    All values come from the trace built by _plan_core().
    """
    import math as _math

    TYPE_NAMES = {
        "S": "Strength", "H": "Hypertrophy", "E": "Endurance",
        "T": "Technique", "TEST": "Max Test",
    }

    ex = trace.exercise
    params = trace.params
    session_type = trace.session_type
    type_name = TYPE_NAMES.get(session_type, session_type)
    rest_mid = (params.rest_min + params.rest_max) // 2
    rule = "─" * 54
    L: list[str] = []

    # Header
    L.append(
        f"[bold cyan]{type_name} ({session_type})"
        f"  ·  {trace.date_str}"
        f"  ·  Week {trace.week_num}[/bold cyan]"
    )
    L.append(rule)

    # OVERTRAINING SHIFT NOTICE
    if trace.overtraining_shift_days > 0:
        L.append(
            f"\n[yellow]⚠ Session shifted +{trace.overtraining_shift_days} day(s) "
            f"(overtraining level {trace.overtraining_level}/3 detected). "
            f"Original plan start was pushed forward to allow recovery.[/yellow]"
        )

    # SESSION TYPE
    L.append("\n[bold]SESSION TYPE[/bold]")
    L.append(
        f"  {trace.days_per_week}-day schedule template: "
        f"[cyan]{' → '.join(trace.schedule)}[/cyan] (repeating weekly)."
    )
    L.append(f"  Week {trace.week_num} → [magenta]{session_type}[/magenta].")

    # GRIP
    L.append(f"\n[bold]GRIP: {trace.grip}[/bold]")
    if ex.has_variant_rotation:
        cycle_str = " → ".join(trace.cycle)
        plan_count = trace.count_before - trace.hist_count
        L.append(
            f"  {session_type} sessions rotate: [cyan]{cycle_str}[/cyan]"
            f" ({len(trace.cycle)}-step cycle)."
        )
        L.append(f"  In history: {trace.hist_count} {session_type} session(s).")
        if plan_count > 0:
            L.append(
                f"  In this plan before {trace.date_str}: {plan_count} {session_type} session(s)."
            )
        L.append(f"  Total before this session: {trace.count_before}.")
        L.append(
            f"  {trace.count_before} mod {len(trace.cycle)}"
            f" = [bold]{trace.count_before % len(trace.cycle)}[/bold]"
            f" → [green]{trace.grip}[/green]."
        )
    else:
        L.append(f"  Always uses primary variant (no rotation for {ex.display_name}).")

    # TRAINING MAX
    L.append(f"\n[bold]TRAINING MAX: {trace.current_tm}[/bold]")
    test_sessions = [s for s in trace.history if s.session_type == "TEST"]
    if test_sessions:
        latest_test = max(test_sessions, key=lambda s: s.date)
        latest_max = max(
            (s.actual_reps for s in latest_test.completed_sets if s.actual_reps),
            default=0,
        )
        tm_from_test = int(TM_FACTOR * latest_max)
        L.append(f"  Latest TEST: {latest_max} reps on {latest_test.date}.")
        L.append(f"  Starting TM = floor({TM_FACTOR} × {latest_max}) = {tm_from_test}.")
    else:
        L.append(f"  Starting TM: {trace.initial_tm}.")
    if trace.weekly_log:
        L.append("  Progression by week:")
        for wk, prog, before, after in trace.weekly_log:
            L.append(
                f"    Week {wk}: TM {before:.2f} + {prog:.2f} = [bold]{after:.2f}[/bold]"
                f" (int = {int(after)})"
            )
    else:
        L.append("  No weekly progression yet (first week of plan).")
    L.append(
        f"  → TM for this session: int({trace.tm_float:.2f})"
        f" = [bold green]{trace.current_tm}[/bold green]."
    )

    # SETS
    L.append(f"\n[bold]SETS: {trace.adj_sets}[/bold]")
    L.append(
        f"  {session_type} config: sets [{params.sets_min}–{params.sets_max}]."
        f"  Base = ({params.sets_min}+{params.sets_max})//2 = {trace.base_sets}."
    )
    L.append(
        f"  How the range is used: the midpoint ({trace.base_sets}) is the operational target."
        f"  Autoregulation can only reduce sets (never push above midpoint)."
        f"  High readiness adds +1 rep/set rather than adding more sets."
    )
    L.append(
        f"  Readiness z-score: {trace.z_score:+.2f}"
        f"  (thresholds: low={READINESS_Z_LOW}, high=+{READINESS_Z_HIGH})."
    )
    if not trace.has_autoreg:
        L.append(
            f"  Autoregulation: [dim]off[/dim]"
            f" (need ≥ {MIN_SESSIONS_FOR_AUTOREG} sessions, have {trace.history_len})."
        )
    elif trace.z_score < READINESS_Z_LOW:
        L.append(
            f"  z < {READINESS_Z_LOW} → reduce by {int(READINESS_VOLUME_REDUCTION*100)}%:"
            f" max(3, {int(trace.base_sets*(1-READINESS_VOLUME_REDUCTION))})"
            f" = [bold]{trace.adj_sets}[/bold]."
        )
    elif trace.z_score > READINESS_Z_HIGH:
        L.append(f"  z > +{READINESS_Z_HIGH} → sets unchanged, +1 rep (see Reps).")
    else:
        L.append(f"  z in [{READINESS_Z_LOW}, +{READINESS_Z_HIGH}] → no change.")
    L.append(f"  → [bold green]{trace.adj_sets} sets[/bold green].")

    # REPS
    L.append(f"\n[bold]REPS PER SET: {trace.adj_reps}[/bold]")
    L.append(
        f"  {session_type} config:"
        f" fraction [{params.reps_fraction_low}–{params.reps_fraction_high}]"
        f" of TM, clamped to [{params.reps_min}–{params.reps_max}]."
    )
    L.append(
        f"  Low  = max({params.reps_min}, int({trace.current_tm} × {params.reps_fraction_low}))"
        f" = max({params.reps_min}, {int(trace.current_tm * params.reps_fraction_low)})"
        f" = {trace.reps_low}."
    )
    L.append(
        f"  High = min({params.reps_max}, int({trace.current_tm} × {params.reps_fraction_high}))"
        f" = min({params.reps_max}, {int(trace.current_tm * params.reps_fraction_high)})"
        f" = {trace.reps_high}."
    )
    L.append(
        f"  Target = ({trace.reps_low}+{trace.reps_high})//2"
        f" = {(trace.reps_low + trace.reps_high) // 2},"
        f" clamped to [{params.reps_min}–{params.reps_max}] → {trace.base_reps}."
    )
    if trace.has_autoreg and trace.z_score > READINESS_Z_HIGH:
        L.append(
            f"  High readiness (z={trace.z_score:+.2f} > +{READINESS_Z_HIGH})"
            f" → +1 rep → {trace.adj_reps}."
        )
    L.append(f"  → [bold green]{trace.adj_reps} reps/set[/bold green].")

    # WEIGHT (S) or VOLUME (E)
    if session_type == "S":
        L.append(f"\n[bold]ADDED WEIGHT: {trace.added_weight:.1f} kg[/bold]")
        thr = ex.weight_tm_threshold
        frac = ex.weight_increment_fraction
        bwf = ex.bw_fraction
        if ex.load_type == "external_only":
            L.append(
                f"  External-load exercise — dumbbell weight from last TEST session"
                f" ({trace.last_test_weight:.1f} kg)."
            )
        elif trace.current_tm > thr:
            eff_bw = bodyweight_kg * bwf
            raw_w = eff_bw * frac * (trace.current_tm - thr)
            rounded = round(raw_w * 2) / 2
            L.append(
                f"  TM = {trace.current_tm} > {thr} → BW×{bwf}×{frac}×(TM−{thr})"
                f" = {eff_bw:.1f}×{frac}×{trace.current_tm - thr} = {raw_w:.2f} kg."
            )
            L.append(
                f"  Rounded to nearest 0.5 kg: {rounded:.1f} kg."
                f"  Cap at {ex.max_added_weight_kg:.0f} kg"
                f" → [bold green]{trace.added_weight:.1f} kg[/bold green]."
            )
        else:
            L.append(f"  TM = {trace.current_tm} ≤ {thr} → bodyweight only (0 kg added).")
    elif session_type == "E":
        ke = endurance_volume_multiplier(trace.current_tm)
        total_target = int(ke * trace.current_tm)
        L.append("\n[bold]VOLUME (Endurance — descending ladder)[/bold]")
        L.append(
            f"  kE(TM={trace.current_tm}) = 3.0 + 2.0"
            f" × clip(({trace.current_tm}-5)/25, 0, 1) = {ke:.2f}."
        )
        L.append(
            f"  Total target = kE × TM = {ke:.2f} × {trace.current_tm} = {total_target} reps."
        )
        L.append(
            f"  Starting at {trace.base_reps} reps/set, decreasing by 1 each set"
            f" (min {params.reps_min})."
        )
        L.append(
            f"  Stops when accumulated ≥ {total_target} reps"
            f" or {params.sets_max} sets reached."
        )

    # REST — rebuild rest_adj_notes from trace.recent_same_type using the same
    # logic as calculate_adaptive_rest() so the display stays in sync.
    rest_adj_notes: list[str] = []
    same_type_sessions = trace.recent_same_type
    if same_type_sessions:
        last_same = same_type_sessions[-1]
        sets_done = [s for s in last_same.completed_sets if s.actual_reps is not None]
        if sets_done:
            rirs = [s.rir_reported for s in sets_done if s.rir_reported is not None]
            if rirs:
                if any(r <= 1 for r in rirs):
                    rest_adj_notes.append("RIR ≤ 1 in a set → +30 s")
                elif all(r >= 3 for r in rirs):
                    rest_adj_notes.append("all sets RIR ≥ 3 → −15 s")
            reps_done = [s.actual_reps for s in sets_done if s.actual_reps is not None]
            if len(reps_done) >= 2 and reps_done[0] > 0:
                drop = (reps_done[0] - reps_done[-1]) / reps_done[0]
                if drop > DROP_OFF_THRESHOLD:
                    rest_adj_notes.append(
                        f"drop-off {drop:.0%} > {int(DROP_OFF_THRESHOLD*100)}% → +15 s"
                    )
    if trace.ff_state is not None:
        readiness_val = trace.ff_state.fitness - trace.ff_state.fatigue
        readiness_var_val = max(trace.ff_state.readiness_var, 0.01)
        z_rest = (
            (readiness_val - trace.ff_state.readiness_mean)
            / _math.sqrt(readiness_var_val)
        )
        if z_rest < READINESS_Z_LOW:
            rest_adj_notes.append(
                f"readiness z={z_rest:+.2f} < {READINESS_Z_LOW} → +30 s"
            )
    # Rest-adherence signal (Phase 3 addition)
    actual_rests = [
        s.rest_seconds_before
        for session in same_type_sessions
        for s in session.completed_sets
        if s.rest_seconds_before > 0
    ]
    if len(actual_rests) >= 3:
        avg_actual = sum(actual_rests) / len(actual_rests)
        if avg_actual < params.rest_min * 0.85:
            rest_adj_notes.append(
                f"avg actual rest {avg_actual:.0f} s"
                f" < {params.rest_min}×0.85={params.rest_min * 0.85:.0f} s → −20 s"
            )
        elif avg_actual > params.rest_max * 1.10:
            rest_adj_notes.append(
                f"avg actual rest {avg_actual:.0f} s"
                f" > {params.rest_max}×1.10={params.rest_max * 1.10:.0f} s → +20 s"
            )

    L.append(f"\n[bold]REST: {trace.adj_rest} s[/bold]")
    L.append(
        f"  {session_type} config: rest [{params.rest_min}–{params.rest_max}] s."
        f"  Base = ({params.rest_min}+{params.rest_max})//2 = {rest_mid} s."
    )
    if same_type_sessions and rest_adj_notes:
        L.append(
            f"  Adjustments from last {session_type} session"
            f" ({same_type_sessions[-1].date}):"
        )
        for note in rest_adj_notes:
            L.append(f"    {note}")
        L.append(
            f"  Clamped to [{params.rest_min}–{params.rest_max}] s → {trace.adj_rest} s."
        )
    elif not same_type_sessions:
        L.append(f"  No previous {session_type} session found → using midpoint.")
    else:
        L.append(
            f"  No adjustments needed from last {session_type} session → midpoint unchanged."
        )
    L.append(f"  → [bold green]{trace.adj_rest} s[/bold green].")

    # EXPECTED TM AFTER
    next_week_prog = expected_reps_per_week(trace.current_tm, trace.user_target)
    next_week_tm = trace.tm_float + next_week_prog
    L.append(f"\n[bold]EXPECTED TM AFTER: {trace.expected_tm_after}[/bold]")
    L.append(f"  TM is updated once per calendar week boundary.")
    L.append(
        f"  Current TM (this week): int({trace.tm_float:.2f}) = {trace.current_tm}."
    )
    L.append(
        f"  Next week's TM ≈ {trace.tm_float:.2f} + {next_week_prog:.2f}"
        f" = {next_week_tm:.2f} → int = {int(next_week_tm)}."
    )
    L.append(
        f"  → [bold green]{trace.expected_tm_after}[/bold green]"
        f" (this week's TM, shown consistently for all sessions in week {trace.week_num})."
    )

    return "\n".join(L)


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
