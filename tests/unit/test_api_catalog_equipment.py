"""Integration tests for the exercise-catalog and equipment api flows."""

import pytest

from bar_scheduler import api


def test_equipment_roundtrip(data_dir):
    api.update_equipment(
        data_dir,
        "pull_up",
        api.EquipmentInput(
            available_items=["BAR_ONLY", "MACHINE_ASSISTED"],
            available_machine_assistance_kg=[10, 20, 30],
        ),
    )
    current = api.get_current_equipment(data_dir, "pull_up")
    assert current["available_machine_assistance_kg"] == [10, 20, 30]
    assert current["recommended_item"] in ("BAR_ONLY", "MACHINE_ASSISTED")


def test_list_and_get_exercise_info():
    exercises = api.list_exercises()
    assert "pull_up" in exercises
    assert exercises["pull_up"]["bw_fraction"] == pytest.approx(1.0)
    details = api.get_exercise_info("pull_up")
    assert details["id"] == "pull_up"
    assert details["bw_fraction"] == pytest.approx(1.0)
