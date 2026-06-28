"""Persistence for the exercise roster in profile.json.

Owns ``exercises_enabled``, ``exercise_days`` and ``exercise_targets`` — the
sections the api previously hand-edited with raw json reads/writes.
"""

from bar_scheduler.domain.models import ExerciseTarget
from bar_scheduler.io.profile_document import ProfileDocument
from bar_scheduler.io.serializers import exercise_target_to_dict


class ExerciseRosterStore:
    """Add/remove enabled exercises and edit their per-exercise settings."""

    def __init__(self, doc: ProfileDocument):
        self._doc = doc

    def enable(self, exercise_id: str, days_per_week: int) -> None:
        """Add ``exercise_id`` to the active list and set its weekly frequency."""
        with self._doc.mutate() as raw:
            enabled = raw.setdefault("exercises_enabled", [])
            if exercise_id not in enabled:
                enabled.append(exercise_id)
            raw.setdefault("exercise_days", {})[exercise_id] = days_per_week

    def disable(self, exercise_id: str) -> None:
        """Remove ``exercise_id`` from the active list (no-op if absent)."""
        with self._doc.mutate() as raw:
            enabled = raw.get("exercises_enabled", [])
            if exercise_id in enabled:
                enabled.remove(exercise_id)

    def set_target(self, exercise_id: str, target: ExerciseTarget) -> None:
        """Store the user's goal for ``exercise_id``."""
        with self._doc.mutate() as raw:
            raw.setdefault("exercise_targets", {})[exercise_id] = exercise_target_to_dict(target)

    def set_days(self, exercise_id: str, days_per_week: int) -> None:
        """Set the weekly training frequency for ``exercise_id``."""
        with self._doc.mutate() as raw:
            raw.setdefault("exercise_days", {})[exercise_id] = days_per_week
