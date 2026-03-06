"""External load computation for Strength sessions."""

from ..exercises.base import ExerciseDefinition
from ..exercises.registry import get_exercise

PULL_UP = get_exercise("pull_up")


def _apply_rounding(raw: float) -> float:
    """Round to nearest 0.5 kg."""
    return round(raw * 2) / 2


def _apply_cap(value: float, max_kg: float) -> float:
    """Clamp added weight to the exercise maximum."""
    return min(value, max_kg)


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
    rounded = _apply_rounding(raw)
    return _apply_cap(rounded, exercise.max_added_weight_kg)
