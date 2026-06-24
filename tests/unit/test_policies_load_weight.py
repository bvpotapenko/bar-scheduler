"""Unit tests for LoadCalculator added-weight prescription."""

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


def test_added_weight_zero_below_threshold(calc):
    # pull_up weight_tm_threshold = 9; tm 9 -> bodyweight-only phase.
    history = [_test_session("pull_up", 9)]
    ctx = _ctx("pull_up", tm=9, stype="S", history=history)
    assert calc.added_weight(ctx) == pytest.approx(0.0)


def test_added_weight_above_threshold_rounds_to_half_kg(calc):
    history = [_test_session("pull_up", 10)]
    ctx = _ctx("pull_up", tm=10, stype="S", history=history)
    # leff 1RM ~106.9; invert at 5 reps -> ~82.4; minus bw 80 -> ~2.4; round 0.5 -> 2.5
    assert calc.added_weight(ctx) == pytest.approx(2.5)


def test_added_weight_snaps_to_available_weights(calc):
    equip = EquipmentConstraints(available_weights_kg=(2.0, 5.0, 10.0))
    history = [_test_session("pull_up", 10)]
    ctx = _ctx("pull_up", tm=10, stype="S", history=history, equip=equip)
    assert calc.added_weight(ctx) == pytest.approx(2.0)  # floor-snap 2.4 -> 2.0


def test_external_only_carries_last_test_weight(calc):
    # bss is external_only with a bodyweight share -> carry last TEST added weight.
    history = [_test_session("bss", 8, added=12.0)]
    ctx = _ctx("bss", tm=12, stype="S", history=history)
    assert calc.added_weight(ctx) == pytest.approx(12.0)
