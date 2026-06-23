"""Unit tests for the domain value objects."""

import pytest

from bar_scheduler.domain import (
    EquipmentConstraints,
    LoadSpec,
    ProgressionGoal,
)
from bar_scheduler.domain.models import EquipmentState, ExerciseTarget


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (LoadSpec(bodyweight_kg=80.0), 80.0),  # full bodyweight, no extras
        (LoadSpec(bodyweight_kg=80.0, bw_fraction=0.0, added_load_kg=20.0), 20.0),  # external only
        (LoadSpec(bodyweight_kg=80.0, added_load_kg=10.0), 90.0),  # weighted pull-up
        (LoadSpec(bodyweight_kg=80.0, assistance_kg=30.0), 50.0),  # band-assisted
        (LoadSpec(bodyweight_kg=80.0, bw_fraction=0.71, added_load_kg=12.0), 68.8),  # BSS
    ],
    ids=["bodyweight", "external", "weighted", "assisted", "bss"],
)
def test_loadspec_effective_kg(spec, expected):
    assert spec.effective_kg == pytest.approx(expected)


def test_equipment_constraints_default_is_empty():
    eq = EquipmentConstraints()
    assert eq.available_weights_kg == ()
    assert not eq.available_weights_kg  # falsy → unconstrained, like legacy []/None


def test_equipment_constraints_from_state():
    state = EquipmentState(
        exercise_id="pull_up",
        available_items=["BAR_ONLY"],
        available_weights_kg=[5.0, 10.0],
        available_band_assistance_kg=[15.0, 30.0],
    )
    eq = EquipmentConstraints.from_state(state)
    assert eq.available_weights_kg == (5.0, 10.0)
    assert eq.available_band_assistance_kg == (15.0, 30.0)
    assert eq.available_machine_assistance_kg == ()


def test_equipment_constraints_from_none():
    assert EquipmentConstraints.from_state(None) == EquipmentConstraints()


def test_progression_goal_from_target_weighted():
    goal = ProgressionGoal.from_target(ExerciseTarget(reps=12, weight_kg=40.0), default_reps=30)
    assert goal.reps == 12
    assert goal.weight_kg == 40.0
    assert goal.is_weighted is True


def test_progression_goal_from_none_uses_default():
    goal = ProgressionGoal.from_target(None, default_reps=30)
    assert goal.reps == 30
    assert goal.is_weighted is False
