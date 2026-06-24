"""Unit tests for LoadCalculator machine/band assistance and projection."""

import pytest

from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.policies.load import DEFAULT_SESSION_TARGET_REPS, LoadCalculator
from bar_scheduler.domain.context import EquipmentConstraints, PrescriptionContext
from bar_scheduler.domain.models import SessionResult, SetResult

BW = 80.0


@pytest.fixture
def calc() -> LoadCalculator:
    return LoadCalculator(tm_factor=0.9, session_target_reps=DEFAULT_SESSION_TARGET_REPS)


def _test_session(
    exercise_id: str, reps: int, added: float = 0.0, bw: float = 80.0
) -> SessionResult:
    return SessionResult(
        date="2026-01-01",
        bodyweight_kg=bw,
        grip="pronated",
        session_type="TEST",
        exercise_id=exercise_id,
        completed_sets=[
            SetResult(
                target_reps=reps, actual_reps=reps, rest_seconds_before=180, added_weight_kg=added
            )
        ],
    )


def _ctx(exercise_id, tm, stype, history=(), equip=None):
    return PrescriptionContext(
        exercise=get_exercise(exercise_id),
        training_max=tm,
        bodyweight_kg=BW,
        history=tuple(history),
        session_type=stype,
        equipment=equip or EquipmentConstraints(),
    )


def test_machine_assistance_ceiling_snaps(calc):
    equip = EquipmentConstraints(available_machine_assistance_kg=(10.0, 20.0, 30.0, 40.0))
    ctx = _ctx("pull_up", tm=5, stype="S", equip=equip)
    # needed ~10.2 -> ceiling-snap to 20.0
    assert calc.machine_assistance(ctx) == pytest.approx(20.0)


def test_machine_assistance_zero_when_weighted_phase(calc):
    equip = EquipmentConstraints(available_machine_assistance_kg=(10.0, 20.0))
    ctx = _ctx("pull_up", tm=20, stype="S", equip=equip)  # tm > threshold
    assert calc.machine_assistance(ctx) == pytest.approx(0.0)


def test_band_assistance_zero_when_no_bands(calc):
    ctx = _ctx("pull_up", tm=5, stype="S")
    assert calc.band_assistance(ctx) == pytest.approx(0.0)


def test_weight_at_reps_projection_positive(calc):
    history = [_test_session("pull_up", 12, added=10.0)]
    ctx = _ctx("pull_up", tm=10, stype="S", history=history)
    # at goal reps 8, with a strong weighted history, expect a positive projection.
    assert calc.weight_at_reps(ctx, at_reps=8) > 0
