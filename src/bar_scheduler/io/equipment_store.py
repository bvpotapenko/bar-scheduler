"""Persistence for the current per-exercise equipment in profile.json."""

from bar_scheduler.domain.models import EquipmentState
from bar_scheduler.io.profile_document import ProfileDocument
from bar_scheduler.io.serializers import dict_to_equipment_state, equipment_state_to_dict


class EquipmentStore:
    """Load/overwrite the current EquipmentState for an exercise."""

    def __init__(self, doc: ProfileDocument):
        self._doc = doc

    def load(self, exercise_id: str) -> EquipmentState | None:
        """Current equipment for ``exercise_id``, or None if none configured."""
        raw = self._doc.read().get("equipment", {}).get(exercise_id)
        if raw is None:
            return None
        try:
            return dict_to_equipment_state(raw)
        except (KeyError, TypeError):
            return None

    def save(self, state: EquipmentState) -> None:
        """Overwrite the current equipment for ``state.exercise_id``."""
        if not self._doc.exists():
            return
        with self._doc.mutate() as raw:
            raw.setdefault("equipment", {})[state.exercise_id] = equipment_state_to_dict(state)
