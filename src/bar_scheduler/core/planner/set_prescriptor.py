"""Set and rep prescription for each session type."""

from ..adaptation import apply_autoregulation
from ..config import MIN_SESSIONS_FOR_AUTOREG, endurance_volume_multiplier
from ..exercises.base import ExerciseDefinition, SessionTypeParams
from ..models import PlannedSet, SessionResult, SessionType
from .load_calculator import _calculate_added_weight
from .rest_advisor import calculate_adaptive_rest


def _calculate_rep_targets(
    training_max: int,
    params: SessionTypeParams,
) -> tuple[int, int, int]:
    """
    Compute low, high, and target reps per set from TM and session params.

    Returns:
        (reps_low, reps_high, target_reps)
    """
    reps_low = max(params.reps_min, int(training_max * params.reps_fraction_low))
    reps_high = min(params.reps_max, int(training_max * params.reps_fraction_high))
    target_reps = (reps_low + reps_high) // 2
    target_reps = max(params.reps_min, min(params.reps_max, target_reps))
    return reps_low, reps_high, target_reps


def _build_endurance_sets(
    training_max: int,
    params: SessionTypeParams,
    rest: int,
    target_reps: int,
    added_weight: float = 0.0,
) -> list[PlannedSet]:
    """
    Build the descending-ladder set list for an Endurance session.

    Total volume target = kE(TM) × TM; reps decrease by 1 each set
    (floored at reps_min) until accumulated ≥ target or sets_max reached.
    """
    total_target = int(endurance_volume_multiplier(training_max) * training_max)
    current_reps = target_reps
    accumulated = 0
    sets: list[PlannedSet] = []

    while accumulated < total_target and len(sets) < params.sets_max:
        actual_reps = max(params.reps_min, current_reps)
        sets.append(
            PlannedSet(
                target_reps=actual_reps,
                rest_seconds_before=rest,
                added_weight_kg=added_weight,
                rir_target=params.rir_target,
            )
        )
        accumulated += actual_reps
        current_reps = max(params.reps_min, current_reps - 1)

    return sets


def _build_strength_sets(
    adj_sets: int,
    adj_reps: int,
    rest: int,
    added_weight: float,
    params: SessionTypeParams,
) -> list[PlannedSet]:
    """Build uniform sets for a Strength session (with added weight)."""
    return [
        PlannedSet(
            target_reps=adj_reps,
            rest_seconds_before=rest,
            added_weight_kg=added_weight,
            rir_target=params.rir_target,
        )
        for _ in range(adj_sets)
    ]


def _build_standard_sets(
    adj_sets: int,
    adj_reps: int,
    rest: int,
    params: SessionTypeParams,
    added_weight: float = 0.0,
) -> list[PlannedSet]:
    """Build uniform sets for H, T, and TEST sessions."""
    return [
        PlannedSet(
            target_reps=adj_reps,
            rest_seconds_before=rest,
            added_weight_kg=added_weight,
            rir_target=params.rir_target,
        )
        for _ in range(adj_sets)
    ]


def calculate_set_prescription(
    session_type: SessionType,
    training_max: int,
    ff_state,
    bodyweight_kg: float,
    exercise: ExerciseDefinition,
    history: list[SessionResult] | None = None,
    history_sessions: int = 0,
    recent_same_type: list[SessionResult] | None = None,
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

    Returns:
        List of PlannedSet
    """
    params = exercise.session_params[session_type]

    reps_low, reps_high, target_reps = _calculate_rep_targets(training_max, params)

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

    # Added weight applies to all session types; 0.0 when in BW-only phase
    added_weight = _calculate_added_weight(
        exercise, training_max, bodyweight_kg, history or [], session_type
    )

    if session_type == "E":
        return _build_endurance_sets(training_max, params, rest, target_reps, added_weight)

    if session_type == "S":
        return _build_strength_sets(adj_sets, adj_reps, rest, added_weight, params)

    # H, T, TEST
    return _build_standard_sets(adj_sets, adj_reps, rest, params, added_weight)
