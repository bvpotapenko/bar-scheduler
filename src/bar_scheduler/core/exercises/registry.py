"""
Exercise registry.

All supported exercises are registered here.  Use get_exercise() to
look up an ExerciseDefinition by its exercise_id string.
"""

from .base import ExerciseDefinition
from .bss import BSS
from .dip import DIP
from .pull_up import PULL_UP

EXERCISE_REGISTRY: dict[str, ExerciseDefinition] = {
    "pull_up": PULL_UP,
    "dip": DIP,
    "bss": BSS,
}


def get_exercise(exercise_id: str) -> ExerciseDefinition:
    """
    Return the ExerciseDefinition for the given exercise_id.

    Args:
        exercise_id: One of "pull_up", "dip", "bss"

    Returns:
        ExerciseDefinition for the requested exercise

    Raises:
        ValueError: If exercise_id is not in the registry
    """
    if exercise_id not in EXERCISE_REGISTRY:
        valid = ", ".join(EXERCISE_REGISTRY)
        raise ValueError(f"Unknown exercise '{exercise_id}'. Valid IDs: {valid}")
    return EXERCISE_REGISTRY[exercise_id]
