"""Unit tests for FitnessFatigueModel.predicted_max."""

import pytest

from bar_scheduler.config.model_params import (
    EwmaMaxConfig,
    FitnessFatigueConfig,
    TrainingLoadConfig,
)
from bar_scheduler.core.policies.fatigue import FitnessFatigueModel


@pytest.fixture
def model() -> FitnessFatigueModel:
    return FitnessFatigueModel(FitnessFatigueConfig(), TrainingLoadConfig(), EwmaMaxConfig())


@pytest.mark.parametrize(
    ("readiness", "mean", "expected"),
    [(0.0, 0.0, 20.0), (2.0, 0.0, 20.8), (-2.0, 0.0, 19.2)],
    ids=["neutral", "high-readiness", "low-readiness"],
)
def test_predicted_max(model, readiness, mean, expected):
    # C_READINESS default 0.02 -> 20 * (1 + 0.02*(R - R_bar))
    assert model.predicted_max(20.0, readiness, mean) == pytest.approx(expected)
