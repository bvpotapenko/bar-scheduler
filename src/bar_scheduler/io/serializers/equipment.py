"""Equipment snapshot/state <-> dict conversion."""

from typing import Any

from bar_scheduler.domain.models import EquipmentSnapshot, EquipmentState


def equipment_snapshot_to_dict(snapshot: EquipmentSnapshot) -> dict[str, Any]:
    """Serialize an EquipmentSnapshot to a compact dict."""
    return {
        "active_item": snapshot.active_item,
        "assistance_kg": snapshot.assistance_kg,
    }


def dict_to_equipment_snapshot(raw: dict[str, Any]) -> EquipmentSnapshot:
    """Deserialize an EquipmentSnapshot from a dict."""
    return EquipmentSnapshot(
        active_item=str(raw.get("active_item", "")),
        assistance_kg=float(raw.get("assistance_kg", 0.0)),
    )


def equipment_state_to_dict(state: EquipmentState) -> dict[str, Any]:
    """Serialize an EquipmentState for storage in profile.json (omits empty lists)."""
    row: dict[str, Any] = {
        "exercise_id": state.exercise_id,
        "available_items": list(state.available_items),
    }
    if state.available_weights_kg:
        row["available_weights_kg"] = list(state.available_weights_kg)
    if state.available_machine_assistance_kg:
        row["available_machine_assistance_kg"] = list(state.available_machine_assistance_kg)
    if state.available_band_assistance_kg:
        row["available_band_assistance_kg"] = list(state.available_band_assistance_kg)
    return row


def dict_to_equipment_state(raw: dict[str, Any]) -> EquipmentState:
    """Deserialize an EquipmentState from a profile.json dict."""
    return EquipmentState(
        exercise_id=str(raw.get("exercise_id", "")),
        available_items=list(raw.get("available_items", [])),
        available_weights_kg=[float(wt) for wt in raw.get("available_weights_kg", [])],
        available_machine_assistance_kg=[
            float(wt) for wt in raw.get("available_machine_assistance_kg", [])
        ],
        available_band_assistance_kg=[
            float(wt) for wt in raw.get("available_band_assistance_kg", [])
        ],
    )
