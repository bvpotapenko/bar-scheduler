"""Exercise management functions for the bar-scheduler API."""

from __future__ import annotations

from pathlib import Path

from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.api._common import _require_profile_store


def set_exercise_target(
    data_dir: Path,
    exercise_id: str,
    reps: int,
    weight_kg: float = 0.0,
) -> None:
    """
    Set the user's personal goal for an exercise.

    ``reps`` is the target rep count (must be > 0).
    ``weight_kg`` is additional load on top of bodyweight (0 = bodyweight-only goal).
    Raises ``ValueError`` for unknown ``exercise_id`` or invalid values.
    """
    from bar_scheduler.domain.models import ExerciseTarget

    get_exercise(exercise_id)
    target = ExerciseTarget(reps=reps, weight_kg=weight_kg)  # validates reps > 0, weight >= 0

    store = _require_profile_store(data_dir)
    store.roster.set_target(exercise_id, target)


def set_exercise_days(
    data_dir: Path,
    exercise_id: str,
    days_per_week: int,
) -> None:
    """
    Set per-exercise training frequency.

    ``days_per_week`` must be 1–5.
    Raises ``ValueError`` for unknown ``exercise_id`` or out-of-range days.
    """
    get_exercise(exercise_id)
    if days_per_week not in (1, 2, 3, 4, 5):
        raise ValueError(f"days_per_week must be 1–5, got {days_per_week}")

    store = _require_profile_store(data_dir)
    store.roster.set_days(exercise_id, days_per_week)


def enable_exercise(data_dir: Path, exercise_id: str, *, days_per_week: int) -> None:
    """
    Add an exercise to the user's active list and create its history file.

    ``days_per_week`` (1–5) sets the training frequency for this exercise.
    Raises ``ValueError`` for unknown ``exercise_id`` or out-of-range days.
    Raises ``ProfileNotFoundError`` if the profile has not been initialised.
    """
    get_exercise(exercise_id)
    if days_per_week not in (1, 2, 3, 4, 5):
        raise ValueError(f"days_per_week must be 1–5, got {days_per_week}")

    store = _require_profile_store(data_dir)
    store.roster.enable(exercise_id, days_per_week)
    store.history.init(exercise_id)  # create JSONL if missing (idempotent)


def disable_exercise(data_dir: Path, exercise_id: str) -> None:
    """
    Remove an exercise from the user's active list.

    No-op if the exercise is not currently enabled.
    The history file is preserved (data is never deleted automatically).
    Raises ``ProfileNotFoundError`` if the profile has not been initialised.
    """
    store = _require_profile_store(data_dir)
    store.roster.disable(exercise_id)


def delete_exercise_history(data_dir: Path, exercise_id: str) -> None:
    """
    Delete the history JSONL file for an exercise.

    No-op if the file does not exist.  The profile (exercises_enabled list,
    equipment history, plan anchors) is not modified — call
    ``disable_exercise`` separately if you also want to remove the exercise
    from the active list.
    Raises ``ProfileNotFoundError`` if the profile has not been initialised.
    """
    store = _require_profile_store(data_dir)
    store.history.path(exercise_id).unlink(missing_ok=True)
