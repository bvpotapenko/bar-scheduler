"""Tests for EquipmentStore: the equipment section of profile.json."""

import pytest

from bar_scheduler.domain.models import EquipmentState
from bar_scheduler.io.equipment_store import EquipmentStore
from bar_scheduler.io.profile_document import ProfileDocument


def _store(tmp_path, *, seeded: bool = True) -> EquipmentStore:
    doc = ProfileDocument(tmp_path / "profile.json")
    if seeded:
        doc.write({"height_cm": 180, "current_bodyweight_kg": 80.0})
    return EquipmentStore(doc)


def _state(item_ids: list[str], bands: list[float]) -> EquipmentState:
    return EquipmentState(
        exercise_id="pull_up",
        available_items=item_ids,
        available_weights_kg=[],
        available_machine_assistance_kg=[],
        available_band_assistance_kg=bands,
    )


def test_save_then_load_roundtrips(tmp_path):
    store = _store(tmp_path)
    store.save(_state(["BAR_ONLY", "BAND_SET"], [10.0, 20.0]))
    loaded = store.load("pull_up")
    assert loaded.available_items == ["BAR_ONLY", "BAND_SET"]
    assert loaded.available_band_assistance_kg == pytest.approx([10.0, 20.0])


def test_load_none_when_unset(tmp_path):
    assert _store(tmp_path).load("pull_up") is None


def test_save_overwrites_previous(tmp_path):
    store = _store(tmp_path)
    store.save(_state(["BAR_ONLY"], []))
    store.save(_state(["WEIGHT_BELT"], []))
    assert store.load("pull_up").available_items == ["WEIGHT_BELT"]


def test_save_noop_when_profile_missing(tmp_path):
    store = _store(tmp_path, seeded=False)
    store.save(_state(["BAR_ONLY"], []))
    assert store.load("pull_up") is None
    assert (tmp_path / "profile.json").exists() is False
