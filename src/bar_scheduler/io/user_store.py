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
            raise FileNotFoundError(f"Profile not found: {self.profile.path}. Run 'init' first.")
        return UserState(profile=profile, history=self.history.load(exercise_id))

    # -- TEMP migration delegators (Stage 9 -> deleted in Stage 11) ---------
    # Keep the old flat surface working while api is rewired cluster by
    # cluster to the sub-stores above. These cause a transient WPS214 on this
    # file only; removed once no api module calls them.

    @property
    def profile_path(self) -> Path:
        return self.profile.path

    def load_profile(self):
        return self.profile.load()

    def save_profile(self, profile) -> None:
        self.profile.save(profile)

    def update_bodyweight(self, bodyweight_kg: float) -> None:
        self.profile.update_fields(bodyweight_kg=bodyweight_kg)

    def update_language(self, lang: str) -> None:
        self.profile.update_fields(language=lang)

    def exists(self, exercise_id: str) -> bool:
        return self.history.exists(exercise_id)

    def history_path(self, exercise_id: str) -> Path:
        return self.history.path(exercise_id)

    def init_exercise(self, exercise_id: str) -> None:
        self.history.init(exercise_id)

    def load_history(self, exercise_id: str):
        return self.history.load(exercise_id)

    def append_session(self, session) -> None:
        self.history.append(session)

    def delete_session_at(self, exercise_id: str, index: int) -> None:
        self.history.delete_at(exercise_id, index)

    def get_plan_start_date(self, exercise_id: str):
        return self.plan.plan_start_date(exercise_id)

    def set_plan_start_date(self, exercise_id: str, date: str) -> None:
        self.plan.save_plan_start_date(exercise_id, date)

    def get_plan_weeks(self):
        return self.plan.plan_weeks()

    def set_plan_weeks(self, weeks: int) -> None:
        self.plan.save_plan_weeks(weeks)

    def load_current_equipment(self, exercise_id: str):
        return self.equipment.load(exercise_id)

    def update_equipment(self, new_state) -> None:
        self.equipment.save(new_state)

    def load_plan_result_cache(self, exercise_id: str):
        return self.plan_cache.load(exercise_id)

    def save_plan_result_cache(self, exercise_id: str, plans: list[dict]) -> None:
        self.plan_cache.save(exercise_id, plans)

    def _input_files_mtime(self, exercise_id: str) -> float:
        paths = [self.profile.path, self.history.path(exercise_id)]
        return max((path.stat().st_mtime for path in paths if path.exists()), default=0.0)
