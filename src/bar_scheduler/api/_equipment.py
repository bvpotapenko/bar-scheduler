"""Equipment management functions for the bar-scheduler API."""

from __future__ import annotations

from pathlib import Path

from bar_scheduler.containers import container
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.domain.context import EquipmentConstraints, PrescriptionContext
from bar_scheduler.api._common import _assistance_for_item, _require_store
from bar_scheduler.api.types import EquipmentInput


def update_equipment(data_dir: Path, exercise_id: str, equipment: EquipmentInput) -> None:
    """
    Update the equipment available for an exercise.

    ``equipment`` is an :class:`EquipmentInput`. The planner auto-selects the
    appropriate item from ``available_items`` based on the user's current
    training level. For each kg list, ``None`` inherits the previous value,
    ``[]`` clears it, and a list floor/ceiling-snaps prescriptions to it.

    Raises ``ProfileNotFoundError`` / ``HistoryNotFoundError`` if not initialised.
    """
    store = _require_store(data_dir, exercise_id)
    prev = store.load_current_equipment(exercise_id)
    store.update_equipment(equipment.to_state(exercise_id, prev))


def _recommended_assistance(ex, state, user_state) -> tuple[str, float]:
    """Recommended item plus its prescribed assistance (H-session reference)."""
    current_tm = container.training_state().status(
        user_state.history, user_state.profile.bodyweight_kg
    ).training_max
    from bar_scheduler.core.equipment import recommend_equipment_item

    recommended = recommend_equipment_item(state.available_items, ex, current_tm)
    ctx = PrescriptionContext(
        exercise=ex,
        training_max=current_tm,
        bodyweight_kg=user_state.profile.bodyweight_kg,
        history=tuple(s for s in user_state.history if s.exercise_id == state.exercise_id),
        session_type="H",
        equipment=EquipmentConstraints.from_state(state),
    )
    return recommended, _assistance_for_item(recommended, state, ctx) or 0.0


def _equipment_dict(state, recommended: str, recommended_assistance_kg: float) -> dict:
    """Assemble the get_current_equipment response dict."""
    from bar_scheduler.core.equipment import get_assistance_kg as _get_assistance_kg

    return {
        "exercise_id": state.exercise_id,
        "recommended_item": recommended,
        "available_items": list(state.available_items),
        "available_machine_assistance_kg": list(state.available_machine_assistance_kg),
        "available_band_assistance_kg": list(state.available_band_assistance_kg),
        "assistance_kg": _get_assistance_kg(
            recommended,
            state.exercise_id,
            state.available_machine_assistance_kg,
            state.available_band_assistance_kg,
        ),
        "recommended_assistance_kg": recommended_assistance_kg,
        "is_bss_degraded": "ELEVATION_SURFACE" not in state.available_items,
    }


def get_current_equipment(data_dir: Path, exercise_id: str) -> dict | None:
    """
    Return the currently configured equipment for an exercise as a plain dict.

    Returns ``None`` if no equipment has been configured.  The dict includes
    computed fields: ``recommended_item`` (auto-selected from available_items
    based on current training level), ``assistance_kg`` (from catalog),
    ``recommended_assistance_kg`` (machine assistance prescribed for the next
    session; 0.0 when not applicable), and ``is_bss_degraded`` (True when
    ``ELEVATION_SURFACE`` is absent from ``available_items``).
    Raises ``ProfileNotFoundError`` if the profile has not been initialised.
    """
    store = _require_store(data_dir, exercise_id)
    state = store.load_current_equipment(exercise_id)
    if state is None:
        return None
    user_state = store.load_user_state(exercise_id)
    recommended, assistance = _recommended_assistance(get_exercise(exercise_id), state, user_state)
    return _equipment_dict(state, recommended, assistance)


def compute_leff(
    bw_fraction: float,
    bodyweight_kg: float,
    added_weight_kg: float,
    assistance_kg: float = 0.0,
) -> float:
    """
    Compute effective load (Leff) in kg.

    ``Leff = BW × bw_fraction + added_weight_kg − assistance_kg`` (≥ 0).
    """
    from bar_scheduler.core.equipment import compute_leff as _compute_leff

    return _compute_leff(bw_fraction, bodyweight_kg, added_weight_kg, assistance_kg)


def compute_equipment_adjustment(old_leff: float, new_leff: float) -> dict:
    """
    Compute rep adjustment factor when effective load changes between equipment.

    Returns ``{"reps_factor": float, "description": str}``.
    """
    from bar_scheduler.core.equipment import compute_equipment_adjustment as _compute

    return _compute(old_leff, new_leff)


def get_assistance_kg(
    exercise_id: str,
    item_id: str,
    available_machine_assistance_kg: list[float] | None = None,
    available_band_assistance_kg: list[float] | None = None,
) -> float:
    """
    Return the assistance in kg for an equipment item.

    Positive value = assistive (reduces Leff); zero = neutral or additive.

    For MACHINE_ASSISTED items, pass ``available_machine_assistance_kg`` to get
    the maximum available assistance (conservative fallback).
    For BAND_SET items, pass ``available_band_assistance_kg`` similarly.
    """
    from bar_scheduler.core.equipment import get_assistance_kg as _get

    machine_list = list(available_machine_assistance_kg) if available_machine_assistance_kg else []
    band_list = list(available_band_assistance_kg) if available_band_assistance_kg else []
    return _get(item_id, exercise_id, machine_list, band_list)
