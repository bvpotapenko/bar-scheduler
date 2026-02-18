"""
Adaptation rules: plateau detection, fatigue assessment, and deload triggers.

Implements the logic for determining when to adjust training volume
based on performance trends and recovery state.
"""

from datetime import datetime, timedelta

from .config import (
    COMPLIANCE_THRESHOLD,
    DELOAD_VOLUME_REDUCTION,
    FATIGUE_Z_THRESHOLD,
    PLATEAU_SLOPE_THRESHOLD,
    PLATEAU_WINDOW_DAYS,
    READINESS_VOLUME_REDUCTION,
    READINESS_Z_HIGH,
    READINESS_Z_LOW,
    TREND_WINDOW_DAYS,
    UNDERPERFORMANCE_THRESHOLD,
    WEEKLY_HARD_SETS_MAX,
    WEEKLY_HARD_SETS_MIN,
    WEEKLY_VOLUME_INCREASE_RATE,
)
from .metrics import (
    get_test_sessions,
    overall_max_reps,
    session_compliance,
    session_max_reps,
    trend_slope_per_week,
    weekly_compliance,
)
from .models import FitnessFatigueState, SessionResult, TrainingStatus
from .physiology import build_fitness_fatigue_state, predicted_max_with_readiness


def detect_plateau(history: list[SessionResult]) -> bool:
    """
    Detect if athlete is in a performance plateau.

    Plateau = (slope < threshold) AND (no new best in window_days)

    Args:
        history: Training history

    Returns:
        True if plateau detected
    """
    if not history:
        return False

    test_sessions = get_test_sessions(history)
    if len(test_sessions) < 2:
        return False

    # Check slope
    slope = trend_slope_per_week(history, TREND_WINDOW_DAYS)
    if slope >= PLATEAU_SLOPE_THRESHOLD:
        return False

    # Check for new best in window
    latest_date = datetime.strptime(test_sessions[-1].date, "%Y-%m-%d")
    cutoff = latest_date - timedelta(days=PLATEAU_WINDOW_DAYS)

    best_ever = overall_max_reps(history)

    recent_tests = [
        s for s in test_sessions if datetime.strptime(s.date, "%Y-%m-%d") >= cutoff
    ]

    for session in recent_tests:
        if session_max_reps(session) >= best_ever:
            return False  # New best in window

    return True


def calculate_fatigue_score(
    history: list[SessionResult],
    ff_state: FitnessFatigueState,
) -> float:
    """
    Calculate fatigue score from recent performance vs prediction.

    Compares actual max to predicted max adjusted for readiness.

    Args:
        history: Training history
        ff_state: Current fitness-fatigue state

    Returns:
        Fatigue score (negative = underperforming, positive = overperforming)
    """
    test_sessions = get_test_sessions(history)
    if not test_sessions:
        return 0.0

    latest = test_sessions[-1]
    actual_max = session_max_reps(latest)

    # Predicted max with readiness adjustment
    predicted = predicted_max_with_readiness(
        ff_state.m_hat,
        ff_state.readiness(),
        ff_state.readiness_mean,
    )

    if predicted == 0:
        return 0.0

    # Return relative difference (positive = overperforming)
    return (actual_max - predicted) / predicted


def check_underperformance(
    history: list[SessionResult],
    ff_state: FitnessFatigueState,
    consecutive_required: int = 2,
) -> bool:
    """
    Check for consecutive underperformance in strength sessions.

    Underperformance = actual < predicted * (1 - threshold)

    Args:
        history: Training history
        ff_state: Current fitness-fatigue state
        consecutive_required: Number of consecutive sessions needed

    Returns:
        True if underperforming
    """
    # Get recent S (strength) sessions
    strength_sessions = [s for s in history if s.session_type == "S"]

    if len(strength_sessions) < consecutive_required:
        return False

    recent = strength_sessions[-consecutive_required:]

    predicted = predicted_max_with_readiness(
        ff_state.m_hat,
        ff_state.readiness(),
        ff_state.readiness_mean,
    )

    threshold_max = predicted * (1 - UNDERPERFORMANCE_THRESHOLD)

    for session in recent:
        actual_max = session_max_reps(session)
        if actual_max >= threshold_max:
            return False  # At least one session was OK

    return True


def should_deload(
    history: list[SessionResult],
    ff_state: FitnessFatigueState,
) -> bool:
    """
    Determine if a deload is recommended.

    Deload triggers:
    1. Plateau AND low readiness z-score
    2. Two consecutive strength sessions with large underperformance
    3. Low compliance ratio

    Args:
        history: Training history
        ff_state: Current fitness-fatigue state

    Returns:
        True if deload recommended
    """
    if not history:
        return False

    # Check readiness z-score
    z = ff_state.readiness_z_score()

    # Trigger 1: Plateau with fatigue
    if detect_plateau(history) and z < FATIGUE_Z_THRESHOLD:
        return True

    # Trigger 2: Consecutive underperformance
    if check_underperformance(history, ff_state):
        return True

    # Trigger 3: Low compliance
    compliance = weekly_compliance(history, weeks_back=1)
    if compliance < COMPLIANCE_THRESHOLD:
        return True

    return False


def calculate_volume_adjustment(
    history: list[SessionResult],
    ff_state: FitnessFatigueState,
    current_weekly_sets: int,
) -> int:
    """
    Calculate recommended weekly hard sets based on adaptation state.

    Args:
        history: Training history
        ff_state: Current fitness-fatigue state
        current_weekly_sets: Current planned weekly sets

    Returns:
        Recommended weekly hard sets
    """
    if should_deload(history, ff_state):
        # Deload: reduce volume significantly
        new_sets = int(current_weekly_sets * (1 - DELOAD_VOLUME_REDUCTION))
        return max(WEEKLY_HARD_SETS_MIN, new_sets)

    z = ff_state.readiness_z_score()
    compliance = weekly_compliance(history, weeks_back=1) if history else 1.0

    if z < READINESS_Z_LOW:
        # Low readiness: reduce volume
        new_sets = int(current_weekly_sets * (1 - READINESS_VOLUME_REDUCTION))
        return max(WEEKLY_HARD_SETS_MIN, new_sets)

    if z > READINESS_Z_HIGH and compliance > 0.9:
        # High readiness and good compliance: allow increase
        new_sets = int(current_weekly_sets * (1 + WEEKLY_VOLUME_INCREASE_RATE))
        return min(WEEKLY_HARD_SETS_MAX, new_sets)

    # Normal range: maintain
    return current_weekly_sets


def get_training_status(
    history: list[SessionResult],
    current_bodyweight_kg: float,
    baseline_max: int | None = None,
) -> TrainingStatus:
    """
    Build comprehensive training status from history.

    Args:
        history: Training history
        current_bodyweight_kg: Current bodyweight
        baseline_max: Baseline max if no test history

    Returns:
        TrainingStatus with all metrics
    """
    from .metrics import latest_test_max, training_max

    # Build fitness-fatigue state
    ff_state = build_fitness_fatigue_state(
        history, current_bodyweight_kg, baseline_max
    )

    # Get test max
    test_max = latest_test_max(history)
    if test_max is None and baseline_max is not None:
        test_max = baseline_max

    # Calculate training max
    tm = training_max(history)
    if tm == 1 and baseline_max is not None:
        from .metrics import training_max_from_baseline

        tm = training_max_from_baseline(baseline_max)

    # Calculate trend
    slope = trend_slope_per_week(history, TREND_WINDOW_DAYS)

    # Check plateau
    is_plateau = detect_plateau(history)

    # Check deload
    deload = should_deload(history, ff_state)

    # Calculate compliance
    compliance = weekly_compliance(history, weeks_back=1) if history else 1.0

    # Calculate fatigue score
    fatigue = calculate_fatigue_score(history, ff_state)

    return TrainingStatus(
        training_max=tm,
        latest_test_max=test_max,
        trend_slope=slope,
        is_plateau=is_plateau,
        deload_recommended=deload,
        compliance_ratio=compliance,
        fatigue_score=fatigue,
        fitness_fatigue_state=ff_state,
    )


def apply_autoregulation(
    base_sets: int,
    base_reps: int,
    ff_state: FitnessFatigueState,
) -> tuple[int, int]:
    """
    Apply autoregulation adjustments to planned volume.

    Based on readiness z-score:
    - z < -1.0: reduce volume
    - z > 1.0: allow progression
    - otherwise: use base plan

    Args:
        base_sets: Base number of sets
        base_reps: Base reps per set
        ff_state: Current fitness-fatigue state

    Returns:
        Tuple of (adjusted_sets, adjusted_reps)
    """
    z = ff_state.readiness_z_score()

    if z < READINESS_Z_LOW:
        # Reduce sets, keep reps
        adjusted_sets = max(3, int(base_sets * (1 - READINESS_VOLUME_REDUCTION)))
        return (adjusted_sets, base_reps)

    if z > READINESS_Z_HIGH:
        # Allow small progression: +1 rep on some sets
        adjusted_reps = base_reps + 1
        return (base_sets, adjusted_reps)

    # Normal: use base
    return (base_sets, base_reps)
