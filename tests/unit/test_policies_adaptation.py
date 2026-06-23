"""Unit tests for ProgressionPolicy, PlateauDetector, and DeloadPolicy."""

import pytest

from bar_scheduler.config.model_params import (
    EwmaMaxConfig,
    FitnessFatigueConfig,
    TrainingLoadConfig,
)
from bar_scheduler.config.planning_params import PlateauConfig, ProgressionConfig
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.policies.fatigue import FitnessFatigueModel
from bar_scheduler.core.policies.load import DEFAULT_SESSION_TARGET_REPS, LoadCalculator
from bar_scheduler.core.policies.plateau import DeloadPolicy, PlateauDetector
from bar_scheduler.core.policies.progression import ProgressionPolicy
from bar_scheduler.domain.context import EquipmentConstraints, PrescriptionContext, ProgressionGoal
from bar_scheduler.domain.models import FitnessFatigueState, SessionResult, SetResult


@pytest.fixture
def progression() -> ProgressionPolicy:
    load = LoadCalculator(tm_factor=0.9, session_target_reps=DEFAULT_SESSION_TARGET_REPS)
    return ProgressionPolicy(ProgressionConfig(), load)


def _test(date: str, reps: int) -> SessionResult:
    return SessionResult(
        date=date,
        bodyweight_kg=80.0,
        grip="pronated",
        session_type="TEST",
        exercise_id="pull_up",
        completed_sets=[SetResult(target_reps=reps, actual_reps=reps, rest_seconds_before=180)],
    )


def _ctx() -> PrescriptionContext:
    return PrescriptionContext(
        exercise=get_exercise("pull_up"),
        training_max=10,
        bodyweight_kg=80.0,
        history=(),
        session_type="S",
        equipment=EquipmentConstraints(),
    )


# --- ProgressionPolicy ---


def test_reps_per_week_slows_toward_target(progression):
    assert progression.reps_per_week(10, 30) == pytest.approx(0.681, abs=1e-3)
    assert progression.reps_per_week(30, 30) == 0.0  # at/over target -> no progression


def test_weeks_to_target_positive_and_bounded(progression):
    weeks = progression.weeks_to_target(10, 15)
    assert 0 < weeks < 50


def test_weekly_delta_unweighted_goal(progression):
    delta = progression.weekly_delta(10.0, ProgressionGoal(reps=20), _ctx())
    assert delta == pytest.approx(progression.reps_per_week(10, 20))


def test_weekly_delta_weighted_goal_not_met_keeps_growing(progression):
    # Empty history -> projected weight 0 < goal weight -> keep progressing (>= DELTA min).
    delta = progression.weekly_delta(12.0, ProgressionGoal(reps=10, weight_kg=20.0), _ctx())
    assert delta >= ProgressionConfig().DELTA_PROGRESSION_MIN


# --- PlateauDetector ---


@pytest.fixture
def detector() -> PlateauDetector:
    return PlateauDetector(PlateauConfig())


def test_plateau_when_flat_below_best(detector):
    history = [_test("2025-12-01", 12), _test("2026-01-01", 10), _test("2026-01-15", 10)]
    assert detector.is_plateaued(history) is True


def test_no_plateau_when_improving(detector):
    assert detector.is_plateaued([_test("2026-01-01", 10), _test("2026-01-15", 12)]) is False


def test_no_plateau_with_single_test(detector):
    assert detector.is_plateaued([_test("2026-01-01", 10)]) is False


# --- DeloadPolicy ---


@pytest.fixture
def deload() -> DeloadPolicy:
    cfg = PlateauConfig()
    fatigue = FitnessFatigueModel(FitnessFatigueConfig(), TrainingLoadConfig(), EwmaMaxConfig())
    return DeloadPolicy(cfg, PlateauDetector(cfg), fatigue)


def test_deload_on_low_compliance(deload):
    low = SessionResult(
        date="2026-01-15",
        bodyweight_kg=80.0,
        grip="pronated",
        session_type="S",
        exercise_id="pull_up",
        planned_sets=[SetResult(target_reps=20, actual_reps=None, rest_seconds_before=180)],
        completed_sets=[SetResult(target_reps=20, actual_reps=5, rest_seconds_before=180)],
    )
    assert deload.should_deload([low], FitnessFatigueState()) is True


def test_no_deload_without_history(deload):
    assert deload.should_deload([], FitnessFatigueState()) is False
