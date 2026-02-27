"""
Exercise registry.

All supported exercises are registered here.  Use get_exercise() to
look up an ExerciseDefinition by its exercise_id string.

Exercises are loaded from per-exercise YAML files in the bundled
``src/bar_scheduler/exercises/`` directory at import time.  If YAML
loading fails for any reason (missing PyYAML, parse error, missing
field), a RuntimeError is raised — the application cannot start without
valid exercise definitions.

User overrides: place matching files in ``~/.bar-scheduler/exercises/``.
"""

from .base import ExerciseDefinition


def _build_registry() -> dict[str, ExerciseDefinition]:
    from .loader import load_exercises_from_yaml

    loaded = load_exercises_from_yaml()
    if not loaded:
        raise RuntimeError(
            "bar-scheduler: no exercise definitions could be loaded from YAML. "
            "Check that src/bar_scheduler/exercises/*.yaml files are present and valid."
        )
    return loaded


EXERCISE_REGISTRY: dict[str, ExerciseDefinition] = _build_registry()


def get_exercise(exercise_id: str) -> ExerciseDefinition:
    """
    Return the ExerciseDefinition for the given exercise_id.

    Args:
        exercise_id: One of "pull_up", "dip", "bss" (or any exercise in the registry)

    Returns:
        ExerciseDefinition for the requested exercise

    Raises:
        ValueError: If exercise_id is not in the registry
    """
    if exercise_id not in EXERCISE_REGISTRY:
        valid = ", ".join(EXERCISE_REGISTRY)
        raise ValueError(f"Unknown exercise '{exercise_id}'. Valid IDs: {valid}")
    return EXERCISE_REGISTRY[exercise_id]
