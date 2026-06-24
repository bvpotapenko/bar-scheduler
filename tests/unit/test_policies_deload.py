"""Unit tests for the DeloadPolicy."""

import pytest

from bar_scheduler.config.model_params import (
    EwmaMaxConfig,
    FitnessFatigueConfig,
    TrainingLoadConfig,
)
from bar_scheduler.config.planning_params import PlateauConfig
from bar_scheduler.core.policies.fatigue import FitnessFatigueModel
from bar_scheduler.core.policies.plateau import DeloadPolicy, PlateauDetector
from bar_scheduler.domain.models import FitnessFatigueState, SessionResult, SetResult


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
