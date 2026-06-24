"""Unit tests for the SetPrescriptor."""

import pytest

from bar_scheduler.config.planning_params import ReadinessConfig
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.policies.autoregulation import AutoregulationPolicy
from bar_scheduler.core.policies.load import DEFAULT_SESSION_TARGET_REPS, LoadCalculator
from bar_scheduler.core.policies.rest import RestAdvisor
from bar_scheduler.core.policies.sets import SetPrescriptor
from bar_scheduler.domain.context import (
    AdaptationSignals,
    EquipmentConstraints,
    PrescriptionContext,
)
from bar_scheduler.domain.models import FitnessFatigueState


@pytest.fixture
def prescriptor() -> SetPrescriptor:
    load = LoadCalculator(tm_factor=0.9, session_target_reps=DEFAULT_SESSION_TARGET_REPS)
    rest = RestAdvisor(drop_off_threshold=0.35, readiness_z_low=-0.5)
    autoreg = AutoregulationPolicy(ReadinessConfig(), min_sessions=3)
    return SetPrescriptor(load, rest, autoreg, tm_factor=0.9)


def _ctx(stype: str, tm: int) -> PrescriptionContext:
    return PrescriptionContext(
        exercise=get_exercise("pull_up"),
        training_max=tm,
        bodyweight_kg=80.0,
        history=(),
        session_type=stype,
        equipment=EquipmentConstraints(),
    )


def _signals(**kw) -> AdaptationSignals:
    return AdaptationSignals(ff_state=FitnessFatigueState(), **kw)


def test_prescribe_strength_uses_fatigue_curve(prescriptor):
    sets = prescriptor.prescribe(_ctx("S", tm=12), _signals())
    # pull_up S sets_by_level mid level; descending reps per fatigue curve [1.0, 0.85, ...]
    assert len(sets) >= 1
    reps = [ps.target_reps for ps in sets]
    assert reps == sorted(reps, reverse=True)  # non-increasing decay
    assert sets[0].rest_seconds_before == 240  # S midpoint, no history


def test_prescribe_test_session_beats_last_result(prescriptor):
    sets = prescriptor.prescribe(_ctx("TEST", tm=9), _signals(latest_test_max=10))
    # round(9 / 0.9) + 1 = 11
    assert sets[0].target_reps == 11
