"""Unit tests for SetPrescriptor, RestAdvisor, and AutoregulationPolicy."""

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
from bar_scheduler.domain.models import FitnessFatigueState, SessionResult, SetResult


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


# --- AutoregulationPolicy ---


def test_autoreg_skipped_below_min_sessions():
    autoreg = AutoregulationPolicy(ReadinessConfig(), min_sessions=3)
    assert autoreg.adjust((4, 8), FitnessFatigueState(), history_sessions=2) == (4, 8)


def test_autoreg_reduces_sets_when_low_readiness():
    autoreg = AutoregulationPolicy(ReadinessConfig(), min_sessions=3)
    low = FitnessFatigueState(fitness=0.0, fatigue=5.0, readiness_mean=0.0, readiness_var=1.0)
    sets, reps = autoreg.adjust((4, 8), low, history_sessions=10, sets_min=1)
    assert sets < 4 and reps == 8  # z very negative -> fewer sets, reps unchanged


def test_autoreg_adds_rep_when_high_readiness():
    autoreg = AutoregulationPolicy(ReadinessConfig(), min_sessions=3)
    high = FitnessFatigueState(fitness=5.0, fatigue=0.0, readiness_mean=0.0, readiness_var=1.0)
    assert autoreg.adjust((4, 8), high, history_sessions=10) == (4, 9)


# --- RestAdvisor ---


def test_rest_midpoint_when_no_history():
    advisor = RestAdvisor(drop_off_threshold=0.35, readiness_z_low=-0.5)
    # pull_up S: rest_min 180, rest_max 300 -> midpoint 240
    assert advisor.recommend("S", [], None, get_exercise("pull_up")) == 240


def test_rest_increases_near_failure():
    advisor = RestAdvisor(drop_off_threshold=0.35, readiness_z_low=-0.5)
    near_failure = SessionResult(
        date="2026-01-01",
        bodyweight_kg=80.0,
        grip="pronated",
        session_type="S",
        exercise_id="pull_up",
        completed_sets=[
            SetResult(target_reps=5, actual_reps=5, rest_seconds_before=200, rir_reported=0)
        ],
    )
    assert advisor.recommend("S", [near_failure], None, get_exercise("pull_up")) == 270  # 240 + 30


# --- SetPrescriptor ---


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
