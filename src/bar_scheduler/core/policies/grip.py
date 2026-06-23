"""Variant/grip rotation across a plan (deterministic; no config needed)."""

from bar_scheduler.core.exercises.base import ExerciseDefinition
from bar_scheduler.domain.models import SessionResult


def _resume_index(
    history: list[SessionResult],
    exercise: ExerciseDefinition,
    session_type: str,
    last_grip: str,
) -> int:
    """Cycle position to resume from after ``last_grip`` for this session type."""
    cycle = exercise.grip_cycles.get(session_type, [exercise.primary_variant])
    if last_grip in cycle:
        return cycle.index(last_grip) + 1
    # Deviant grip not in cycle: fall back to total count of this type.
    return sum(
        1
        for sess in history
        if sess.exercise_id == exercise.exercise_id and sess.session_type == session_type
    )


def _init_grip_counts(history: list[SessionResult], exercise: ExerciseDefinition) -> dict[str, int]:
    """Seed per-session-type rotation counts from history."""
    if not exercise.has_variant_rotation:
        return {}
    last_by_type: dict[str, str] = {}
    for sess in history:
        if sess.exercise_id == exercise.exercise_id:
            last_by_type[sess.session_type] = sess.grip
    return {
        stype: _resume_index(history, exercise, stype, grip) for stype, grip in last_by_type.items()
    }


class GripSelector:
    """Stateful grip rotation for one plan pass; continues seamlessly from history."""

    def __init__(self, exercise: ExerciseDefinition) -> None:
        self._exercise = exercise
        self._counts: dict[str, int] = {}

    def initialize_counts(self, history: list[SessionResult]) -> None:
        """Seed rotation counts from training history."""
        self._counts = _init_grip_counts(history, self._exercise)

    def next_grip(self, session_type: str) -> str:
        """Return the next grip for ``session_type`` and advance the counter."""
        if not self._exercise.has_variant_rotation:
            return self._exercise.primary_variant
        cycle = self._exercise.grip_cycles.get(session_type, [self._exercise.primary_variant])
        index = self._counts.get(session_type, 0)
        self._counts[session_type] = index + 1
        return cycle[index % len(cycle)]
