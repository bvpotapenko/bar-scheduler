"""Variant / grip rotation management for plan generation."""

from ..exercises.base import ExerciseDefinition
from ..models import Grip, SessionResult, SessionType


def _init_grip_counts(
    history: list[SessionResult],
    exercise: ExerciseDefinition,
) -> dict[str, int]:
    """
    Determine grip rotation position from history.

    Finds the last recorded grip per session type and returns the position
    immediately after it in the cycle.  This is position-aware: if a deviant
    grip was logged the rotation resumes from the correct next position rather
    than restarting from the beginning.

    Returns empty dict when the exercise has no variant rotation.
    """
    if not exercise.has_variant_rotation:
        return {}
    last_grip_by_type: dict[str, str] = {}
    for s in history:
        if s.exercise_id == exercise.exercise_id:
            last_grip_by_type[s.session_type] = s.grip
    counts: dict[str, int] = {}
    for session_type, last_grip in last_grip_by_type.items():
        cycle = exercise.grip_cycles.get(session_type, [exercise.primary_variant])
        try:
            counts[session_type] = cycle.index(last_grip) + 1
        except ValueError:
            # Logged grip not in cycle (deviant entry); fall back to total count
            counts[session_type] = sum(
                1 for s in history
                if s.exercise_id == exercise.exercise_id and s.session_type == session_type
            )
    return counts


def _next_grip(
    session_type: str,
    counts: dict[str, int],
    exercise: ExerciseDefinition,
) -> str:
    """Return next grip/variant for session_type and increment counts in-place."""
    cycle = exercise.grip_cycles.get(session_type, [exercise.primary_variant])
    grip = cycle[counts.get(session_type, 0) % len(cycle)]
    counts[session_type] = counts.get(session_type, 0) + 1
    return grip


def select_grip(
    session_type: SessionType,
    history: list[SessionResult],
    exercise: ExerciseDefinition,
) -> Grip:
    """
    Select appropriate grip/variant for a session (one-off lookup).

    For plan generation use GripSelector or _init_grip_counts + _next_grip instead.

    Args:
        session_type: Session type
        history: Training history for alternation
        exercise: ExerciseDefinition with grip_cycles

    Returns:
        Selected grip/variant
    """
    cycle = exercise.grip_cycles.get(session_type, [exercise.primary_variant])
    count = sum(1 for s in history if s.session_type == session_type)
    return cycle[count % len(cycle)]  # type: ignore


class GripSelector:
    """
    Stateful grip/variant rotation manager for a single plan generation pass.

    Maintains per-session-type counts across the plan, ensuring deterministic
    rotation that continues seamlessly from history.
    """

    def __init__(self, exercise: ExerciseDefinition) -> None:
        self.exercise = exercise
        self.counts: dict[str, int] = {}

    def initialize_counts(self, history: list[SessionResult]) -> None:
        """Seed rotation counts from training history."""
        self.counts = _init_grip_counts(history, self.exercise)

    def history_snapshot(self) -> dict[str, int]:
        """Return a snapshot of the current counts (used by trace builder)."""
        return dict(self.counts)

    def next_grip(self, session_type: str) -> str:
        """
        Return the next grip for session_type and advance the internal counter.

        Args:
            session_type: One of S, H, E, T, TEST

        Returns:
            Grip/variant name
        """
        return _next_grip(session_type, self.counts, self.exercise)
