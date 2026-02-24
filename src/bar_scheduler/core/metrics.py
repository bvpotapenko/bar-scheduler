"""
Pure metric computation functions.

All functions are pure and typed for testability.
See docs/training_model.md for formula explanations.
"""

import math
from typing import Sequence

from .config import (
    F_REST_MAX,
    F_REST_MIN,
    GAMMA_BW,
    GAMMA_REST,
    REST_MIN_CLAMP,
    REST_REF_SECONDS,
    TM_FACTOR,
)
from .models import SessionResult, SetResult


def rest_factor(rest_seconds: int) -> float:
    """
    Calculate rest normalization factor F_rest(r).

    F_rest(r) = clip((r/r_ref)^gamma_r, F_min, F_max)

    When rest < reference, F_rest < 1, making normalized reps higher
    (short rest makes reps "harder").

    Args:
        rest_seconds: Rest time between sets in seconds

    Returns:
        Rest normalization factor (0.80 to 1.05)
    """
    # Clamp rest to avoid issues with very short rests
    r = max(rest_seconds, REST_MIN_CLAMP)
    raw = (r / REST_REF_SECONDS) ** GAMMA_REST
    return max(F_REST_MIN, min(F_REST_MAX, raw))


def effective_reps(actual_reps: int, rest_seconds: int) -> float:
    """
    Calculate rest-normalized reps (effective reps).

    reps* = reps / F_rest(rest)

    This gives "credit" for reps done with shorter rest.

    Args:
        actual_reps: Number of reps performed
        rest_seconds: Rest time before this set

    Returns:
        Rest-normalized rep count
    """
    f_rest = rest_factor(rest_seconds)
    return actual_reps / f_rest


def bodyweight_normalized_reps(
    reps: float,
    session_bodyweight_kg: float,
    reference_bodyweight_kg: float,
    added_load_kg: float = 0.0,
    bw_fraction: float = 1.0,
    assistance_kg: float = 0.0,
) -> float:
    """
    Normalize reps for bodyweight differences, accounting for band/machine assistance.

    Leff = BW × bw_fraction + added_load − assistance_kg
    L_rel = Leff / bw_ref
    reps** = reps* * L_rel^gamma_bw

    Args:
        reps: Input reps (may be rest-normalized)
        session_bodyweight_kg: Bodyweight at time of session
        reference_bodyweight_kg: Reference bodyweight for comparison
        added_load_kg: Added external load (belt, dumbbells)
        bw_fraction: Fraction of BW that is the working load
        assistance_kg: Band/machine assistance subtracted from load (≥ 0)

    Returns:
        Bodyweight-normalized rep count
    """
    effective_bw = session_bodyweight_kg * bw_fraction
    total_load = max(0.0, effective_bw + added_load_kg - assistance_kg)
    if reference_bodyweight_kg <= 0:
        return reps
    l_rel = total_load / reference_bodyweight_kg
    return reps * (l_rel ** GAMMA_BW)


def grip_factor(grip: str, variant_factors: dict[str, float] | None = None) -> float:
    """
    Get variant normalization factor.

    Args:
        grip: Variant/grip name (e.g. "pronated", "standard")
        variant_factors: Exercise-specific normalization map; defaults to 1.0 for any grip

    Returns:
        Normalization factor (typically close to 1.0)
    """
    if variant_factors is None:
        return 1.0
    return variant_factors.get(grip, 1.0)


def standardized_reps(
    actual_reps: int,
    rest_seconds: int,
    session_bodyweight_kg: float,
    reference_bodyweight_kg: float,
    added_load_kg: float = 0.0,
    grip: str = "pronated",
    variant_factors: dict[str, float] | None = None,
    bw_fraction: float = 1.0,
    assistance_kg: float = 0.0,
) -> float:
    """
    Calculate fully standardized reps accounting for rest, bodyweight, grip/variant,
    and band/machine assistance.

    reps_std = reps** * F_variant

    Args:
        actual_reps: Raw rep count
        rest_seconds: Rest before set
        session_bodyweight_kg: Bodyweight at session
        reference_bodyweight_kg: Reference bodyweight
        added_load_kg: Added external load
        grip: Grip/variant name
        variant_factors: Per-variant normalization factors (from ExerciseDefinition)
        bw_fraction: Fraction of BW that is the working load
        assistance_kg: Band/machine assistance subtracted from load

    Returns:
        Fully standardized rep count
    """
    # Step 1: Rest normalization
    rest_norm = effective_reps(actual_reps, rest_seconds)

    # Step 2: Bodyweight normalization (includes assistance)
    bw_norm = bodyweight_normalized_reps(
        rest_norm, session_bodyweight_kg, reference_bodyweight_kg,
        added_load_kg, bw_fraction, assistance_kg,
    )

    # Step 3: Variant/grip normalization
    return bw_norm * grip_factor(grip, variant_factors)


def session_max_reps(session: SessionResult) -> int:
    """
    Get the maximum actual reps across completed bodyweight-only sets.

    Args:
        session: Completed session result

    Returns:
        Max reps from bodyweight-only sets, or 0 if none
    """
    bw_only_sets = [
        s for s in session.completed_sets if s.actual_reps is not None and s.added_weight_kg == 0
    ]

    if not bw_only_sets:
        return 0

    return max(s.actual_reps for s in bw_only_sets)  # type: ignore


def session_total_reps(session: SessionResult) -> int:
    """
    Get total reps across all completed sets.

    Args:
        session: Completed session result

    Returns:
        Sum of actual reps
    """
    return sum(s.actual_reps for s in session.completed_sets if s.actual_reps is not None)


def session_avg_rest(session: SessionResult) -> float:
    """
    Get average rest time across completed sets.

    Args:
        session: Completed session result

    Returns:
        Average rest in seconds
    """
    if not session.completed_sets:
        return 0.0

    return sum(s.rest_seconds_before for s in session.completed_sets) / len(session.completed_sets)


def get_test_sessions(history: list[SessionResult]) -> list[SessionResult]:
    """
    Get all TEST type sessions from history.

    Args:
        history: List of sessions

    Returns:
        List of TEST sessions only
    """
    return [s for s in history if s.session_type == "TEST"]


def latest_test_max(history: list[SessionResult]) -> int | None:
    """
    Get the max reps from the most recent TEST session.

    Args:
        history: List of sessions sorted by date

    Returns:
        Max reps or None if no tests
    """
    test_sessions = get_test_sessions(history)
    if not test_sessions:
        return None

    # Assume history is sorted by date, get latest
    latest = test_sessions[-1]
    return session_max_reps(latest)


def overall_max_reps(history: list[SessionResult]) -> int:
    """
    Get the highest max reps from any TEST session.

    Args:
        history: List of sessions

    Returns:
        Highest test max ever recorded, or 0
    """
    test_sessions = get_test_sessions(history)
    if not test_sessions:
        return 0

    return max(session_max_reps(s) for s in test_sessions)


def training_max(history: list[SessionResult]) -> int:
    """
    Calculate training max (TM) from history.

    TM = floor(0.9 * latest_test_max), minimum 1.

    Args:
        history: List of sessions

    Returns:
        Training max, or 1 if no history
    """
    test_max = latest_test_max(history)
    if test_max is None or test_max == 0:
        return 1

    tm = int(test_max * TM_FACTOR)
    return max(1, tm)


def training_max_from_baseline(baseline_max: int) -> int:
    """
    Calculate training max from a baseline max value.

    Args:
        baseline_max: User-provided baseline max reps

    Returns:
        Training max
    """
    tm = int(baseline_max * TM_FACTOR)
    return max(1, tm)


def epley_1rm(total_load_kg: float, reps: int) -> float:
    """
    Estimate 1RM using Epley formula.

    1RM = weight * (1 + reps/30)

    Args:
        total_load_kg: Total load (bodyweight + added weight)
        reps: Reps performed

    Returns:
        Estimated 1RM in kg
    """
    if reps <= 0:
        return 0.0
    return total_load_kg * (1 + reps / 30)


def estimate_pullup_1rm(
    history: list[SessionResult],
    current_bodyweight_kg: float,
    window_sessions: int = 5,
) -> float | None:
    """
    Estimate pull-up 1RM from recent weighted sets (legacy, pull-up specific).

    Uses median of recent weighted set estimates via Epley formula.

    Args:
        history: List of sessions
        current_bodyweight_kg: Current bodyweight
        window_sessions: Number of recent sessions to consider

    Returns:
        Estimated 1RM or None if insufficient data
    """
    weighted_estimates: list[float] = []

    for session in history[-window_sessions:]:
        for set_result in session.completed_sets:
            if set_result.added_weight_kg > 0 and set_result.actual_reps is not None:
                total_load = session.bodyweight_kg + set_result.added_weight_kg
                estimate = epley_1rm(total_load, set_result.actual_reps)
                weighted_estimates.append(estimate)

    if not weighted_estimates:
        return None

    sorted_estimates = sorted(weighted_estimates)
    n = len(sorted_estimates)
    if n % 2 == 0:
        return (sorted_estimates[n // 2 - 1] + sorted_estimates[n // 2]) / 2
    return sorted_estimates[n // 2]


def estimate_1rm(
    exercise,  # ExerciseDefinition — avoid circular import by not type-hinting here
    bodyweight_kg: float,
    history: list[SessionResult],
    window_sessions: int = 5,
) -> dict | None:
    """
    Estimate 1RM for any exercise using the Epley formula.

    For BW-based exercises (bw_fraction > 0):
        effective_load = BW × bw_fraction + added_weight
    For external-only exercises (bw_fraction == 0):
        effective_load = added_weight

    Best set = set with highest Epley estimate across last window_sessions.

    Args:
        exercise: ExerciseDefinition with bw_fraction and load_type
        bodyweight_kg: Current bodyweight in kg
        history: Training history
        window_sessions: Number of recent sessions to scan

    Returns:
        Dict with keys: 1rm_kg, best_reps, best_added_weight_kg, best_date,
        effective_load_kg, onerm_includes_bodyweight, explanation.
        Returns None if no usable sets found.
    """
    best_1rm = 0.0
    best_info: dict | None = None

    for session in history[-window_sessions:]:
        # Extract assistance_kg from session's equipment snapshot if available
        assistance_kg = 0.0
        if session.equipment_snapshot is not None:
            assistance_kg = session.equipment_snapshot.assistance_kg

        for s in session.completed_sets:
            if s.actual_reps is None or s.actual_reps <= 0:
                continue
            # For external_only exercises (BSS), require actual added load
            # but include bw_fraction × BW in Leff per the spec formula
            if exercise.load_type == "external_only":
                if s.added_weight_kg <= 0:
                    continue
                eff_load = max(
                    0.0,
                    bodyweight_kg * exercise.bw_fraction
                    + s.added_weight_kg
                    - assistance_kg,
                )
            else:
                eff_load = max(
                    0.0,
                    bodyweight_kg * exercise.bw_fraction
                    + s.added_weight_kg
                    - assistance_kg,
                )

            if eff_load <= 0:
                continue

            est = epley_1rm(eff_load, s.actual_reps)
            if est > best_1rm:
                best_1rm = est
                best_info = {
                    "1rm_kg": round(est, 1),
                    "best_reps": s.actual_reps,
                    "best_added_weight_kg": s.added_weight_kg,
                    "best_date": session.date,
                    "effective_load_kg": round(eff_load, 1),
                    "onerm_includes_bodyweight": exercise.onerm_includes_bodyweight,
                    "bodyweight_kg": bodyweight_kg,
                    "bw_fraction": exercise.bw_fraction,
                    "explanation": exercise.onerm_explanation,
                }

    return best_info


def linear_trend_max_reps(
    test_points: Sequence[tuple[int, int]],
) -> tuple[float, float]:
    """
    Calculate linear regression for max reps over time.

    Uses least squares: y = a + b*x where x is day index.

    Args:
        test_points: List of (day_index, reps) tuples

    Returns:
        Tuple (intercept a, slope b)
    """
    if len(test_points) < 2:
        if len(test_points) == 1:
            return (float(test_points[0][1]), 0.0)
        return (0.0, 0.0)

    n = len(test_points)
    sum_x = sum(p[0] for p in test_points)
    sum_y = sum(p[1] for p in test_points)
    sum_xy = sum(p[0] * p[1] for p in test_points)
    sum_x2 = sum(p[0] ** 2 for p in test_points)

    # Avoid division by zero
    denominator = n * sum_x2 - sum_x**2
    if abs(denominator) < 1e-10:
        return (sum_y / n if n > 0 else 0.0, 0.0)

    b = (n * sum_xy - sum_x * sum_y) / denominator
    a = (sum_y - b * sum_x) / n

    return (a, b)


def trend_slope_per_week(
    history: list[SessionResult],
    window_days: int = 21,
) -> float:
    """
    Calculate trend slope in reps per week from TEST sessions.

    Args:
        history: List of sessions
        window_days: Days to look back

    Returns:
        Slope in reps per week
    """
    from datetime import datetime, timedelta

    test_sessions = get_test_sessions(history)
    if len(test_sessions) < 2:
        return 0.0

    # Filter to window
    if test_sessions:
        latest_date = datetime.strptime(test_sessions[-1].date, "%Y-%m-%d")
        cutoff = latest_date - timedelta(days=window_days)

        filtered = [
            s for s in test_sessions if datetime.strptime(s.date, "%Y-%m-%d") >= cutoff
        ]
    else:
        filtered = []

    if len(filtered) < 2:
        return 0.0

    # Convert to day indices
    base_date = datetime.strptime(filtered[0].date, "%Y-%m-%d")
    points = [
        ((datetime.strptime(s.date, "%Y-%m-%d") - base_date).days, session_max_reps(s))
        for s in filtered
    ]

    _, slope_per_day = linear_trend_max_reps(points)

    # Convert to per week
    return slope_per_day * 7


def compliance_ratio(
    planned_sets: list[SetResult],
    completed_sets: list[SetResult],
) -> float:
    """
    Calculate compliance ratio: actual/planned reps.

    Args:
        planned_sets: Sets that were planned
        completed_sets: Sets that were completed

    Returns:
        Ratio of actual to planned reps (0.0 to 1.0+)
    """
    planned_total = sum(s.target_reps for s in planned_sets)
    actual_total = sum(s.actual_reps for s in completed_sets if s.actual_reps is not None)

    if planned_total == 0:
        return 1.0 if actual_total == 0 else float("inf")

    return actual_total / planned_total


def session_compliance(session: SessionResult) -> float:
    """
    Calculate compliance ratio for a single session.

    Args:
        session: Session with planned and completed sets

    Returns:
        Compliance ratio
    """
    return compliance_ratio(session.planned_sets, session.completed_sets)


def weekly_compliance(history: list[SessionResult], weeks_back: int = 1) -> float:
    """
    Calculate compliance ratio for recent weeks.

    Args:
        history: List of sessions
        weeks_back: Number of weeks to look back

    Returns:
        Average compliance ratio
    """
    from datetime import datetime, timedelta

    if not history:
        return 1.0

    latest_date = datetime.strptime(history[-1].date, "%Y-%m-%d")
    cutoff = latest_date - timedelta(days=weeks_back * 7)

    recent = [s for s in history if datetime.strptime(s.date, "%Y-%m-%d") >= cutoff]

    if not recent:
        return 1.0

    ratios = [session_compliance(s) for s in recent]
    return sum(ratios) / len(ratios)


def drop_off_ratio(session: SessionResult) -> float:
    """
    Calculate within-session drop-off.

    D = 1 - mean(last_2_sets_reps) / first_set_reps

    High drop-off indicates accumulated fatigue.

    Args:
        session: Completed session

    Returns:
        Drop-off ratio (0 to 1, higher = more fatigue)
    """
    completed = [s for s in session.completed_sets if s.actual_reps is not None]

    if len(completed) < 2:
        return 0.0

    first_reps = completed[0].actual_reps
    if first_reps == 0:
        return 0.0

    # Get last 2 sets
    last_two = completed[-2:]
    mean_last = sum(s.actual_reps for s in last_two) / 2  # type: ignore

    return 1 - (mean_last / first_reps)  # type: ignore


def estimate_rir_from_fraction(actual_reps: int, estimated_max: int) -> int:
    """
    Estimate RIR from rep fraction of estimated max.

    RIR_hat = clip(M_hat - reps, 0, 5)

    Args:
        actual_reps: Reps performed
        estimated_max: Estimated max reps

    Returns:
        Estimated RIR (0 to 5)
    """
    rir = estimated_max - actual_reps
    return max(0, min(5, rir))


def predict_set_reps(
    fresh_capacity: int,
    set_number: int,
    rest_seconds: int,
    rir_target: int = 2,
    lambda_decay: float = 0.08,
    q_recovery: float = 0.3,
    tau_recovery: float = 60.0,
) -> int:
    """
    Predict reps for a set given within-session fatigue.

    reps_pred = floor((p - RIR) * e^(-lambda*(j-1)) * Q_rest(r))

    where Q_rest(r) = 1 - q * e^(-r/tau_r)

    Args:
        fresh_capacity: Fresh max reps (p)
        set_number: Set number (1-indexed)
        rest_seconds: Rest before this set
        rir_target: Target RIR
        lambda_decay: Within-session decay rate
        q_recovery: Rest recovery parameter
        tau_recovery: Rest recovery time constant

    Returns:
        Predicted reps
    """
    # Rest recovery factor
    q_rest = 1 - q_recovery * math.exp(-rest_seconds / tau_recovery)

    # Decay factor
    decay = math.exp(-lambda_decay * (set_number - 1))

    # Predicted reps
    reps = (fresh_capacity - rir_target) * decay * q_rest

    return max(0, int(reps))
