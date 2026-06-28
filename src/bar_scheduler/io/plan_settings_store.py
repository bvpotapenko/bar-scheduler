"""Persistence for planner anchors stored in profile.json.

Owns the per-exercise ``plan_start_dates`` map and the global ``plan_weeks``
horizon. Setters are no-ops when no profile exists yet (the api guards first).
"""

from bar_scheduler.io.profile_document import ProfileDocument


class PlanSettingsStore:
    """Read/write the plan start anchors and the saved plan horizon."""

    def __init__(self, doc: ProfileDocument):
        self._doc = doc

    def plan_start_date(self, exercise_id: str) -> str | None:
        """ISO start anchor for ``exercise_id``, or None if unset."""
        return self._doc.read().get("plan_start_dates", {}).get(exercise_id)

    def save_plan_start_date(self, exercise_id: str, date: str) -> None:
        """Persist the per-exercise plan start anchor."""
        if not self._doc.exists():
            return
        with self._doc.mutate() as raw:
            raw.setdefault("plan_start_dates", {})[exercise_id] = date

    def plan_weeks(self) -> int | None:
        """Last user-chosen plan horizon in weeks, or None if never set."""
        weeks = self._doc.read().get("plan_weeks")
        return None if weeks is None else int(weeks)

    def save_plan_weeks(self, weeks: int) -> None:
        """Persist the chosen plan horizon so later runs reuse it."""
        if not self._doc.exists():
            return
        with self._doc.mutate() as raw:
            raw["plan_weeks"] = weeks
