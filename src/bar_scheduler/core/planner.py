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
    SCHEDULE_3_DAYS,
    SCHEDULE_4_DAYS,
    SESSION_PARAMS,
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
) -> list[PlannedSet]:
    """
    Calculate set prescription for a session.

    Args:
        session_type: Type of session (S, H, E, T, TEST)
        training_max: Current training max
        ff_state: Fitness-fatigue state for autoregulation
        bodyweight_kg: Current bodyweight

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

    # Apply autoregulation
    adj_sets, adj_reps = apply_autoregulation(base_sets, target_reps, ff_state)

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
        # Only add weight if training max is high enough
        added_weight = 0.0
        if training_max >= 10:
            # Add modest weight to bring reps into target range
            added_weight = 5.0 if training_max >= 12 else 2.5

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


def select_grip(session_type: SessionType, history: list[SessionResult]) -> Grip:
    """
    Select appropriate grip for a session.

    - S: pronated (standard)
    - H: alternate between neutral and pronated
    - E: pronated
    - T: pronated
    - TEST: pronated

    Args:
        session_type: Session type
        history: Training history for alternation

    Returns:
        Selected grip
    """
    if session_type in ("S", "E", "T", "TEST"):
        return "pronated"

    # H sessions: alternate
    h_sessions = [s for s in history if s.session_type == "H"]
    if h_sessions and h_sessions[-1].grip == "pronated":
        return "neutral"

    return "pronated"


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

    # Determine initial training max
    tm = status.training_max
    if tm <= 1 and baseline_max is not None:
        tm = training_max_from_baseline(baseline_max)

    # Track TM as float for fractional progression
    tm_float = float(tm)
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

    for date, session_type in session_dates:
        date_str = date.strftime("%Y-%m-%d")

        # Track week transitions and apply progression
        sessions_in_week += 1
        if sessions_in_week > sessions_per_week:
            sessions_in_week = 1
            current_week += 1
            # Apply weekly progression to TM
            progression = expected_reps_per_week(int(tm_float))
            tm_float = min(tm_float + progression, float(target))

        # Use integer TM for prescriptions
        current_tm = int(tm_float)

        # Select grip
        grip = select_grip(session_type, history)  # type: ignore

        # Calculate sets based on current TM
        sets = calculate_set_prescription(
            session_type,  # type: ignore
            current_tm,
            ff_state,
            user_state.current_bodyweight_kg,
        )

        # Calculate expected TM after this session (assuming completion)
        # TM increases gradually within the week too
        sessions_done_in_week = sessions_in_week
        week_fraction = sessions_done_in_week / sessions_per_week
        week_progression = expected_reps_per_week(current_tm)
        expected_tm_after = int(min(tm_float + week_progression * week_fraction, float(target)))

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
