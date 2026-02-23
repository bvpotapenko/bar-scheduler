"""
Exercise definitions for bar-scheduler.

Each exercise is described by an ExerciseDefinition object that
parameterises the shared planning engine.
"""

from .base import ExerciseDefinition, SessionTypeParams
from .registry import EXERCISE_REGISTRY, get_exercise

__all__ = [
    "ExerciseDefinition",
    "SessionTypeParams",
    "EXERCISE_REGISTRY",
    "get_exercise",
]
