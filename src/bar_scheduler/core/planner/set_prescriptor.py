"""Set and rep prescription for each session type."""

from bar_scheduler.core.adaptation import apply_autoregulation
from bar_scheduler.core.config import MIN_SESSIONS_FOR_AUTOREG, TM_FACTOR
from bar_scheduler.core.exercises.base import ExerciseDefinition, SessionTypeParams
from bar_scheduler.core.models import PlannedSet, SessionResult, SessionType
from bar_scheduler.core.planner.load_calculator import _calculate_added_weight
from bar_scheduler.core.planner.rest_advisor import calculate_adaptive_rest


def _classify_level(
    latest_test_max: int | None,
    level_thresholds: list[int] | None,
) -> int:
    """
    Return level index (0-indexed int) from latest test max and exercise thresholds.

    Algorithm: levels are 0..N where N = len(level_thresholds).
    Returns the first index i where test_max <= level_thresholds[i], else N (highest level).
    Returns the middle level when either arg is None (fallback for exercises without data).

    Per Strength Level database (4.8M+ lifts):
      pull-up thresholds: [4, 13, 24]  → 4 levels (0–3)
      dip thresholds:     [7, 19, 33]  → 4 levels (0–3)
    """
    if latest_test_max is None or not level_thresholds:
        num_levels = len(level_thresholds) if level_thresholds else 2
        return max(0, (num_levels - 1) // 2)
    for level_idx, threshold in enumerate(level_thresholds):
        if latest_test_max <= threshold:
            return level_idx
    return len(level_thresholds)  # highest level


def _calculate_rep_targets(
    training_max: int,
    sparams: SessionTypeParams,
) -> tuple[int, int, int]:
    """
    Compute low, high, and target reps per set from TM and session params.

    Returns:
        (reps_low, reps_high, target_reps)
    """
    reps_low = max(sparams.reps_min, int(training_max * sparams.reps_fraction_low))
    reps_high = min(sparams.reps_max, int(training_max * sparams.reps_fraction_high))
    target_reps = (reps_low + reps_high) // 2
    target_reps = max(sparams.reps_min, min(sparams.reps_max, target_reps))
    return reps_low, reps_high, target_reps


def _build_endurance_sets(
    num_sets: int,
    sparams: SessionTypeParams,
    rest: int,
    target_reps: int,
    added_weight: float = 0.0,
) -> list[PlannedSet]:
    """Build the descending-ladder set list for an Endurance session."""
    current_reps = target_reps
    sets: list[PlannedSet] = []

    while len(sets) < num_sets:
        actual_reps = max(sparams.reps_min, current_reps)
        sets.append(
            PlannedSet(
                target_reps=actual_reps,
                rest_seconds_before=rest,
                added_weight_kg=added_weight,
                rir_target=sparams.rir_target,
            )
        )
        current_reps = max(sparams.reps_min, current_reps - 1)

    return sets


def _build_strength_sets(
    adj_sets: int,
    adj_reps: int,
    rest: int,
    added_weight: float,
    sparams: SessionTypeParams,
    exercise: ExerciseDefinition,
) -> list[PlannedSet]:
    """Build sets for a Strength session with per-set rep decay."""
    curve = exercise.set_fatigue_curve
    sets = []
    for set_idx in range(adj_sets):
        factor = curve[set_idx] if set_idx < len(curve) else curve[-1]
        reps = max(1, round(adj_reps * factor))
        sets.append(
            PlannedSet(
                target_reps=reps,
                rest_seconds_before=rest,
                added_weight_kg=added_weight,
                rir_target=sparams.rir_target,
            )
        )
    return sets


def _build_standard_sets(
    adj_sets: int,
    adj_reps: int,
    rest: int,
    sparams: SessionTypeParams,
    exercise: ExerciseDefinition,
    added_weight: float = 0.0,
) -> list[PlannedSet]:
    """Build sets for H, T, and TEST sessions with per-set rep decay."""
    curve = exercise.set_fatigue_curve
    sets = []
    for set_idx in range(adj_sets):
        factor = curve[set_idx] if set_idx < len(curve) else curve[-1]
        reps = max(1, round(adj_reps * factor))
        sets.append(
            PlannedSet(
                target_reps=reps,
                rest_seconds_before=rest,
                added_weight_kg=added_weight,
                rir_target=sparams.rir_target,
            )
        )
    return sets


def calculate_set_prescription(
    session_type: SessionType,
    training_max: int,
    ff_state,
    bodyweight_kg: float,
    exercise: ExerciseDefinition,
    history: list[SessionResult] | None = None,
    history_sessions: int = 0,
    recent_same_type: list[SessionResult] | None = None,
    available_weights_kg: list[float] | None = None,
    latest_test_max: int | None = None,
) -> list[PlannedSet]:
    """
    Calculate set prescription for a session.

    Added weight is computed for every session type (S, H, E, T) when TM is
    above the exercise's weight threshold.  When TM ≤ threshold the weight is
    0.0 and behaviour is identical to the old bodyweight-only path.

    Args:
        session_type: Type of session (S, H, E, T, TEST)
        training_max: Current training max
        ff_state: Fitness-fatigue state for autoregulation
        bodyweight_kg: Current bodyweight
        exercise: ExerciseDefinition with session params and weight formula
        history: Full exercise history used for Leff-1RM estimation
        history_sessions: Number of sessions in history (for autoregulation gating)
        recent_same_type: Recent sessions of the same type (for adaptive rest)
        available_weights_kg: Discrete weights the user owns; empty = continuous rounding.
        latest_test_max: Most recent test max reps (for level classification).

    Returns:
        List of PlannedSet
    """
    sparams = exercise.session_params[session_type]

    reps_low, reps_high, target_reps = _calculate_rep_targets(training_max, sparams)

    # TEST sessions: target is to beat the previous result by 1 rep, not to stop at TM.
    # TM = floor(0.9 × last_test), so round(TM / TM_FACTOR) ≈ last_test.
    # Adding 1 anchors the athlete above their last result; rir_target=0 signals max effort.
    # When there is no prior test, use params.reps_max ("do your absolute max").
    if session_type == "TEST":
        if latest_test_max is None:
            target_reps = sparams.reps_max
        else:
            target_reps = round(training_max / TM_FACTOR) + 1

    # Level-based set count when exercise defines thresholds and session has sets_by_level
    if sparams.sets_by_level is not None and exercise.level_thresholds is not None:
        level = _classify_level(latest_test_max, exercise.level_thresholds)
        level_idx = min(level, len(sparams.sets_by_level) - 1)
        base_sets = sparams.sets_by_level[level_idx]
    else:
        base_sets = (sparams.sets_min + sparams.sets_max) // 2

    # Apply autoregulation only when we have enough history to properly
    # calibrate the fitness-fatigue model
    if history_sessions >= MIN_SESSIONS_FOR_AUTOREG:
        adj_sets, adj_reps = apply_autoregulation(
            base_sets, target_reps, ff_state, sets_min=sparams.sets_min
        )
    else:
        adj_sets, adj_reps = base_sets, target_reps

    # Adaptive rest based on recent same-type sessions and readiness
    rest = calculate_adaptive_rest(session_type, recent_same_type or [], ff_state, exercise)

    # Added weight applies to all session types; 0.0 when in BW-only phase
    added_weight = _calculate_added_weight(
        exercise,
        training_max,
        bodyweight_kg,
        history or [],
        session_type,
        available_weights_kg=available_weights_kg,
    )

    if session_type == "E":
        return _build_endurance_sets(adj_sets, sparams, rest, target_reps, added_weight)

    if session_type == "S":
        return _build_strength_sets(adj_sets, adj_reps, rest, added_weight, sparams, exercise)

    # H, T, TEST
    return _build_standard_sets(adj_sets, adj_reps, rest, sparams, exercise, added_weight)
