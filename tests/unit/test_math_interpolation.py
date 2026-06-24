"""Unit tests for the shared table interpolation helpers."""

import pytest

from bar_scheduler.core.math.interpolation import extrapolate_linear, interpolate


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        (0.0, 0.0),
        (5.0, 5.0),
        (2.5, 2.5),
        (-1.0, 0.0),
        (11.0, 10.0),
    ],
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
