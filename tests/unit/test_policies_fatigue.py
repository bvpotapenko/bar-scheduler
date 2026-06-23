"""Unit tests for the FitnessFatigueModel policy."""

import pytest

from bar_scheduler.config.model_params import (
    EwmaMaxConfig,
    FitnessFatigueConfig,
    TrainingLoadConfig,
)
from bar_scheduler.core.policies.fatigue import FitnessFatigueModel
from bar_scheduler.domain.context import AthleteContext
from bar_scheduler.domain.models import SessionResult, SetResult


@pytest.fixture
def model() -> FitnessFatigueModel:
    return FitnessFatigueModel(FitnessFatigueConfig(), TrainingLoadConfig(), EwmaMaxConfig())


@pytest.fixture
def ctx() -> AthleteContext:
    return AthleteContext(reference_bodyweight_kg=80.0)


def _test_session(date: str, reps: int) -> SessionResult:
    return SessionResult(
        date=date, bodyweight_kg=80.0, grip="pronated", session_type="TEST", exercise_id="pull_up",
        completed_sets=[SetResult(target_reps=reps, actual_reps=reps, rest_seconds_before=180)],
    )


def test_empty_history_defaults_to_ten(model, ctx):
    state, loads = model.build([], ctx)
    assert state.m_hat == 10.0
    assert loads == []


def test_empty_history_uses_baseline(model, ctx):
    state, _ = model.build([], ctx, baseline_max=15)
    assert state.m_hat == 15.0


def test_single_test_session_state(model, ctx):
    state, loads = model.build([_test_session("2026-01-01", 10)], ctx)
    assert state.m_hat == 10.0  # observed == initial -> unchanged
    assert len(loads) == 1
    # hard reps 10*1.45 (rir 0 -> effort 1.45), load_stress 1.0, grip 1.0 -> 14.5
    assert loads[0][1] == pytest.approx(14.5)
    assert state.readiness() == pytest.approx(-7.25, abs=1e-3)


def test_fatigue_decays_over_rest_days(model, ctx):
    close = model.build([_test_session("2026-01-01", 10), _test_session("2026-01-02", 10)], ctx)[0]
    spaced = model.build([_test_session("2026-01-01", 10), _test_session("2026-01-20", 10)], ctx)[0]
    # More rest before the 2nd session -> more fatigue decayed -> higher readiness.
    assert spaced.readiness() > close.readiness()


@pytest.mark.parametrize(
    ("readiness", "mean", "expected"),
    [(0.0, 0.0, 20.0), (2.0, 0.0, 20.8), (-2.0, 0.0, 19.2)],
    ids=["neutral", "high-readiness", "low-readiness"],
)
def test_predicted_max(model, readiness, mean, expected):
    # C_READINESS default 0.02 -> 20 * (1 + 0.02*(R - R_bar))
    assert model.predicted_max(20.0, readiness, mean) == pytest.approx(expected)
