"""Composition facade over a user's data directory.

``UserStore`` wires the focused stores (profile, roster, plan settings,
equipment, history, plan cache) onto one ``data_dir`` and adds the single
cross-store read, ``load_user_state``. Callers reach a concern through its
store, e.g. ``store.history.load(exercise_id)``.
"""

from pathlib import Path

from bar_scheduler.domain.models import UserState
from bar_scheduler.io.equipment_store import EquipmentStore
from bar_scheduler.io.exercise_roster_store import ExerciseRosterStore
from bar_scheduler.io.history_store import HistoryStore
from bar_scheduler.io.plan_cache_store import PlanCacheStore
from bar_scheduler.io.plan_settings_store import PlanSettingsStore
from bar_scheduler.io.profile_document import ProfileDocument
from bar_scheduler.io.profile_store import ProfileStore


class UserStore:
    """A user's persistence, composed from one store per concern."""

    def __init__(self, data_dir: str | Path):
        doc = ProfileDocument(Path(data_dir) / "profile.json")
        self.profile = ProfileStore(doc)
        self.roster = ExerciseRosterStore(doc)
        self.plan = PlanSettingsStore(doc)
        self.equipment = EquipmentStore(doc)
        self.history = HistoryStore(Path(data_dir))
        self.plan_cache = PlanCacheStore(Path(data_dir))

    def load_user_state(self, exercise_id: str) -> UserState:
        """Combine the profile and an exercise's history into a UserState.

        Raises ``FileNotFoundError`` when no profile exists.
        """
        profile = self.profile.load()
        if profile is None:
            path = self.profile.path
            raise FileNotFoundError(f"Profile not found: {path}. Run 'init' first.")
        return UserState(profile=profile, history=self.history.load(exercise_id))
