"""Exercise lookup surface.

Backed by a lazy :class:`ExerciseRepository`: definitions load on first use,
per exercise, not all at import time. Listing helpers exist for callers that
genuinely need every exercise (e.g. the public ``list_exercises`` API).
"""

from bar_scheduler.core.exercises.base import ExerciseDefinition
from bar_scheduler.core.exercises.repository import ExerciseRepository

_repository = ExerciseRepository()


def get_exercise(exercise_id: str) -> ExerciseDefinition:
    """Return the ExerciseDefinition for ``exercise_id`` (raises ValueError if unknown)."""
    return _repository.get(exercise_id)


def list_exercise_ids() -> list[str]:
    """All available exercise ids (cheap — no full parse)."""
    return _repository.list_available()


def all_exercises() -> list[ExerciseDefinition]:
    """Every available ExerciseDefinition (parses all — use only for listing)."""
    return [_repository.get(eid) for eid in _repository.list_available()]
