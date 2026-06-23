"""
Exercise definitions for bar-scheduler.

Each exercise is described by an ExerciseDefinition object that
parameterises the shared planning engine.
"""

from bar_scheduler.core.exercises.base import ExerciseDefinition, SessionTypeParams
from bar_scheduler.core.exercises.registry import (
    all_exercises,
    get_exercise,
    list_exercise_ids,
)
from bar_scheduler.core.exercises.repository import ExerciseRepository

__all__ = [
    "ExerciseDefinition",
    "SessionTypeParams",
    "ExerciseRepository",
    "get_exercise",
    "list_exercise_ids",
    "all_exercises",
]
