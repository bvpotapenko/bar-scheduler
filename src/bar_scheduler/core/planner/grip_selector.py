"""Variant / grip rotation management for plan generation."""

from ..exercises.base import ExerciseDefinition
from ..exercises.registry import get_exercise
from ..models import Grip, SessionResult, SessionType

PULL_UP = get_exercise("pull_up")


def _init_grip_counts(
    history: list[SessionResult],
    exercise: ExerciseDefinition = PULL_UP,
) -> dict[str, int]:
    """
    Count past sessions of each type from history for grip rotation.

    Only counts sessions for the specified exercise so that a dip plan
    doesn't inherit pull-up grip rotation counts.
    Returns empty dict when the exercise has no variant rotation.
    """
    if not exercise.has_variant_rotation:
        return {}
    counts: dict[str, int] = {}
    for s in history:
        if s.exercise_id == exercise.exercise_id and s.session_type != "REST":
            counts[s.session_type] = counts.get(s.session_type, 0) + 1
    return counts


def _next_grip(
    session_type: str,
    counts: dict[str, int],
    exercise: ExerciseDefinition = PULL_UP,
) -> str:
    """Return next grip/variant for session_type and increment counts in-place."""
    cycle = exercise.grip_cycles.get(session_type, [exercise.primary_variant])
    grip = cycle[counts.get(session_type, 0) % len(cycle)]
    counts[session_type] = counts.get(session_type, 0) + 1
    return grip


def select_grip(
    session_type: SessionType,
    history: list[SessionResult],
    exercise: ExerciseDefinition = PULL_UP,
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
