"""Unit tests for the MaxEstimator policy."""

import pytest

from bar_scheduler.core.policies.max_estimation import MaxEstimator
from bar_scheduler.domain.results import MaxEstimate


@pytest.fixture
def estimator() -> MaxEstimator:
    return MaxEstimator()


def test_fewer_than_two_valid_sets_returns_none(estimator):
    assert estimator.estimate([10], [180]) is None
    assert estimator.estimate([10, 0], [180, 120]) is None  # second set has 0 reps


def test_returns_typed_estimate(estimator):
    reps = [10, 8, 7]
    rests = [180, 150, 150]
    rirs = [2, 1, 1]
    estimate = estimator.estimate(reps, rests, rirs)
    assert isinstance(estimate, MaxEstimate)
    assert estimate.fi_est >= 10  # never below the first set
    assert estimate.nuzzo_est > 0
    assert 0 <= estimate.fi_reps <= 1


def test_high_drop_off_raises_fatigue_index(estimator):
    # Big drop from set 1 to later sets -> high FI (near failure).
    estimate = estimator.estimate([12, 6, 5], [180, 150, 150])
    assert estimate.fi_reps == pytest.approx(1.0 - (5.5 / 12), abs=1e-3)


def test_confidence_levels(estimator):
    high_reps = [10, 9, 8, 7]
    high_rests = [180, 150, 150, 150]
    high_rirs = [2, 2, 1, 1]
    high = estimator.estimate(high_reps, high_rests, high_rirs)
    medium = estimator.estimate([10, 8], [180, 150])
    assert high.confidence == "high"  # >=4 sets + RIR known
    assert medium.confidence == "medium"  # >=2 sets, no RIR
