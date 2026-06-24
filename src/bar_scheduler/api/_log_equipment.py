"""Resolve the equipment snapshot attached to a session at log time."""

from __future__ import annotations

from bar_scheduler.containers import container
from bar_scheduler.core.equipment import recommend_equipment_item, snapshot_from_state
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.domain.context import EquipmentConstraints, PrescriptionContext
from bar_scheduler.api._common import _assistance_for_item


def _equip_decision(exercise_id, ustate, session_type, eq_state):
    """Return (recommended_item, prescription context) for the current state."""
    ex = get_exercise(exercise_id)
    current_tm = container.training_state().status(
        ustate.history, ustate.profile.bodyweight_kg
    ).training_max
    active_item = recommend_equipment_item(eq_state.available_items, ex, current_tm)
    ctx = PrescriptionContext(
        exercise=ex,
        training_max=current_tm,
        bodyweight_kg=ustate.profile.bodyweight_kg,
        history=tuple(s for s in ustate.history if s.exercise_id == exercise_id),
        session_type=session_type,
        equipment=EquipmentConstraints.from_state(eq_state),
    )
    return active_item, ctx


def resolve_equipment_snapshot(store, exercise_id, session_obj) -> None:
    """Attach the auto-resolved equipment snapshot to ``session_obj`` (if unset)."""
    if session_obj.equipment_snapshot is not None:
        return
    eq_state = store.load_current_equipment(exercise_id)
    if eq_state is None:
        return
    ustate = store.load_user_state(exercise_id)
    active_item, ctx = _equip_decision(exercise_id, ustate, session_obj.session_type, eq_state)
    override = _assistance_for_item(active_item, eq_state, ctx)
    session_obj.equipment_snapshot = snapshot_from_state(
        eq_state, active_item, override_assistance_kg=override
    )
