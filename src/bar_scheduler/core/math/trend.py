"""Linear trend of max reps over time (OLS)."""

import statistics
from datetime import datetime, timedelta
from typing import Sequence

from bar_scheduler.core.math.history_queries import get_test_sessions, session_max_reps
from bar_scheduler.domain.models import SessionResult


def _ols(xs: list[int], ys: list[int]) -> tuple[float, float]:
    """Ordinary least squares (>= 2 points); returns (intercept, slope)."""
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    var_x = statistics.variance(xs)
    if var_x < 1e-10:
        return (mean_y, 0.0)
    slope = statistics.covariance(xs, ys) / var_x
    return (mean_y - slope * mean_x, slope)


def linear_trend_max_reps(test_points: Sequence[tuple[int, int]]) -> tuple[float, float]:
    """Least-squares (intercept, slope) for (day_index, reps) points."""
    if len(test_points) < 2:
        if len(test_points) == 1:
            return (float(test_points[0][1]), 0.0)
        return (0.0, 0.0)
    xs = [point[0] for point in test_points]
    ys = [point[1] for point in test_points]
    return _ols(xs, ys)


def _parse(session: SessionResult) -> datetime:
    return datetime.strptime(session.date, "%Y-%m-%d")


def _recent_test_points(history: list[SessionResult], window_days: int) -> list[tuple[int, int]]:
    """(day_index, max_reps) for TEST sessions within the window."""
    tests = get_test_sessions(history)
    if len(tests) < 2:
        return []
    cutoff = _parse(tests[-1]) - timedelta(days=window_days)
    recent = [sess for sess in tests if _parse(sess) >= cutoff]
    if len(recent) < 2:
        return []
    base = _parse(recent[0])
    return [((_parse(sess) - base).days, session_max_reps(sess)) for sess in recent]


def trend_slope_per_week(history: list[SessionResult], window_days: int = 21) -> float:
    """Trend slope in reps per week from recent TEST sessions (0.0 if < 2)."""
    points = _recent_test_points(history, window_days)
    if len(points) < 2:
        return 0.0
    _, slope_per_day = linear_trend_max_reps(points)
    return slope_per_day * 7
