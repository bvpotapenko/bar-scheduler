"""Unit tests for the MaxEstimator policy and table interpolation."""

import pytest

from bar_scheduler.core.math.interpolation import extrapolate_linear, interpolate
from bar_scheduler.core.policies.max_estimation import MaxEstimator
from bar_scheduler.domain.results import MaxEstimate


@pytest.fixture
def estimator() -> MaxEstimator:
    return MaxEstimator()


# --- interpolation ---


@pytest.mark.parametrize(
    ("x", "expected"),
    [(0.0, 0.0), (5.0, 5.0), (2.5, 2.5), (-1.0, 0.0), (11.0, 10.0)],
    ids=["low-end", "high-end", "midpoint", "below-clamp", "above-clamp"],
)
def test_interpolate_line(x, expected):
    points = [(0.0, 0.0), (10.0, 10.0)]
    assert interpolate(points, x) == pytest.approx(expected)


def test_interpolate_uneven_points():
    points = [(0.0, 0.0), (2.0, 10.0)]  # slope 5
    assert interpolate(points, 1.0) == pytest.approx(5.0)


def test_extrapolate_linear_beyond_table():
    points = [(0.0, 0.0), (10.0, 10.0)]  # slope 1
    assert extrapolate_linear(points, 15.0) == pytest.approx(15.0)


# --- MaxEstimator ---


def test_fewer_than_two_valid_sets_returns_none(estimator):
    assert estimator.estimate([10], [180]) is None
    assert estimator.estimate([10, 0], [180, 120]) is None  # second set has 0 reps


def test_returns_typed_estimate(estimator):
    result = estimator.estimate([10, 8, 7], [180, 150, 150], [2, 1, 1])
    assert isinstance(result, MaxEstimate)
    assert result.fi_est >= 10  # never below the first set
    assert result.nuzzo_est > 0
    assert 0.0 <= result.fi_reps <= 1.0


def test_high_drop_off_raises_fatigue_index(estimator):
    # Big drop from set 1 to later sets -> high FI (near failure).
    result = estimator.estimate([12, 6, 5], [180, 150, 150])
    assert result.fi_reps == pytest.approx(1.0 - (5.5 / 12), abs=1e-3)


def test_confidence_levels(estimator):
    high = estimator.estimate([10, 9, 8, 7], [180, 150, 150, 150], [2, 2, 1, 1])
    medium = estimator.estimate([10, 8], [180, 150])
    assert high.confidence == "high"  # >=4 sets + RIR known
    assert medium.confidence == "medium"  # >=2 sets, no RIR
