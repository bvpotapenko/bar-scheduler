"""External load computation for all weighted session types.

Uses a Leff-based 1RM estimation (Epley formula) to derive appropriate
added weight for each session type.  This replaces the old linear TM-point
formula which produced unrealistically small weights when first crossing
the weight threshold.

Epley 1RM:      1RM_Leff = Leff × (1 + reps / 30)
Inverse:        Leff_target = 1RM_Leff × TM_FACTOR / (1 + target_reps / 30)
Added weight:   added = Leff_target − BW × bw_fraction

Session target reps (used for Epley inverse):
    S  →  5  reps  (~85 % 1RM)
    H  →  8  reps  (~78 % 1RM)
    E  → 12  reps  (~67 % 1RM)
    T  →  6  reps  (~83 % 1RM)
"""

from ..config import TM_FACTOR
from ..exercises.base import ExerciseDefinition

# Target reps per session type — used to invert the Epley formula
_SESSION_TARGET_REPS: dict[str, int] = {
    "S": 5,
    "H": 8,
    "E": 12,
    "T": 6,
    "TEST": 1,
}


def _apply_rounding(raw: float) -> float:
    """Round to nearest 0.5 kg."""
    return round(raw * 2) / 2


def _apply_cap(value: float, max_kg: float) -> float:
    """Clamp added weight to the exercise maximum."""
    return min(value, max_kg)


def _last_test_weight_bss(history: list, exercise: ExerciseDefinition) -> float:
    """
    Return the dumbbell weight from the most recent TEST session.

    Used for external_only exercises (BSS) where the prescribed load
    is carried forward from the last test.
    """
    test_hist = [
        s for s in history
        if s.session_type == "TEST" and s.exercise_id == exercise.exercise_id
    ]
    if not test_hist or not test_hist[-1].completed_sets:
        return 0.0
    weights = [
        s.added_weight_kg for s in test_hist[-1].completed_sets if s.added_weight_kg > 0
    ]
    return weights[-1] if weights else 0.0


def _estimate_effective_leff_1rm(history: list, bw_fraction: float) -> float | None:
    """
    Estimate Leff 1RM from all available historical sessions using Epley.

    1RM_Leff = Leff × (1 + reps / 30)

    Considers every recorded set across all session types — weighted sets
    naturally yield a more accurate 1RM than bodyweight-only sets because the
    heavier Leff pulls the estimate up.

    Returns:
        Maximum 1RM estimate found, or None if history is empty.
    """
    candidates: list[float] = []
    for session in history:
        assistance = (
            session.equipment_snapshot.assistance_kg
            if session.equipment_snapshot is not None
            else 0.0
        )
        for s in session.completed_sets:
            if not s.actual_reps or s.actual_reps < 1:
                continue
            leff = (
                session.bodyweight_kg * bw_fraction
                + (s.added_weight_kg or 0.0)
                - assistance
            )
            if leff > 0:
                candidates.append(leff * (1 + s.actual_reps / 30))
    return max(candidates) if candidates else None


def _calculate_added_weight(
    exercise: ExerciseDefinition,
    training_max: int,
    bodyweight_kg: float,
    history: list,
    session_type: str,
) -> float:
    """
    Calculate added weight for a session.

    For external_only exercises (BSS):
        Carry forward the weight from the last TEST session.

    For bw_plus_external exercises (pull_up, dip) when TM > threshold:
        1. Estimate Leff 1RM from all historical sets via Epley.
        2. If no usable history, fall back to a conservative TM-derived estimate.
        3. Invert Epley for the session's target reps to get the prescribed Leff.
        4. Subtract bw_contrib to get added weight; round to 0.5 kg; cap at max.

    When TM ≤ weight_tm_threshold: return 0.0 (bodyweight-only phase).

    Args:
        exercise: Exercise definition.
        training_max: Current training max (reps).
        bodyweight_kg: User's current bodyweight.
        history: Full exercise history for 1RM estimation.
        session_type: Session type string ("S", "H", "E", "T", "TEST").

    Returns:
        Added weight in kg (≥ 0, rounded to 0.5 kg).
    """
    if exercise.load_type == "external_only":
        return _last_test_weight_bss(history, exercise)

    if training_max <= exercise.weight_tm_threshold:
        return 0.0

    bw_contrib = bodyweight_kg * exercise.bw_fraction
    leff_1rm = _estimate_effective_leff_1rm(history, exercise.bw_fraction)

    if leff_1rm is None or leff_1rm <= bw_contrib:
        # No usable history — conservative estimate from TM via Epley inverse.
        # training_max ≈ TM_FACTOR × test_max_reps, so test_max ≈ TM / TM_FACTOR.
        leff_1rm = bw_contrib * (1 + training_max / (TM_FACTOR * 30))

    target_reps = _SESSION_TARGET_REPS.get(session_type, 8)
    leff_target = leff_1rm * TM_FACTOR / (1 + target_reps / 30)
    added = leff_target - bw_contrib

    return max(0.0, _apply_cap(_apply_rounding(added), exercise.max_added_weight_kg))


def estimate_prescription_weight(
    history: list,
    exercise: ExerciseDefinition,
    bodyweight_kg: float,
    at_reps: int,
) -> float:
    """
    Estimate the added weight prescription the planner would assign for `at_reps`.

    Uses the current Leff 1RM derived from history (same Epley formula as
    _calculate_added_weight) to project what weight would be prescribed if
    the session targeted `at_reps`. Returns 0.0 when no usable history exists.

    Used by plan_engine to evaluate whether a weighted goal has been reached.

    Args:
        history: Full exercise history for 1RM estimation.
        exercise: Exercise definition.
        bodyweight_kg: User's current bodyweight.
        at_reps: The rep target to project weight for (e.g. goal reps).

    Returns:
        Projected added weight in kg (≥ 0, rounded to 0.5 kg, capped at max).
    """
    if exercise.load_type == "external_only":
        return _last_test_weight_bss(history, exercise)

    bw_contrib = bodyweight_kg * exercise.bw_fraction
    leff_1rm = _estimate_effective_leff_1rm(history, exercise.bw_fraction)

    if leff_1rm is None or leff_1rm <= bw_contrib:
        return 0.0  # Not enough history to project

    leff_target = leff_1rm * TM_FACTOR / (1 + at_reps / 30)
    added = leff_target - bw_contrib
    return max(0.0, _apply_cap(_apply_rounding(added), exercise.max_added_weight_kg))
