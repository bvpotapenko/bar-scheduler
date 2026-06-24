"""Unit tests for training-max derivation, history queries, and trend."""

import pytest

from bar_scheduler.core.math.history_queries import latest_test_max, session_max_reps
from bar_scheduler.core.math.training_max import training_max, training_max_from_baseline
from bar_scheduler.core.math.trend import linear_trend_max_reps
from bar_scheduler.domain.models import SessionResult, SetResult


def _test_session(reps: int, added: float = 0.0, bw: float = 80.0) -> SessionResult:
    return SessionResult(
        date="2026-01-01",
        bodyweight_kg=bw,
        grip="pronated",
        session_type="TEST",
        exercise_id="pull_up",
        completed_sets=[
            SetResult(
                target_reps=reps, actual_reps=reps, rest_seconds_before=180, added_weight_kg=added
            )
        ],
    )


@pytest.mark.parametrize(
    ("baseline", "expected"),
    [(20, 18), (10, 9), (1, 1)],
    ids=["20", "10", "min-floor"],
)
def test_training_max_from_baseline(baseline, expected):
    assert training_max_from_baseline(baseline) == expected


def test_training_max_no_history_is_one():
    assert training_max([]) == 1


def test_training_max_from_test_history():
    assert training_max([_test_session(20)]) == 18  # floor(0.9 * 20)


def test_session_and_latest_test_max():
    assert session_max_reps(_test_session(12)) == 12
    assert latest_test_max([_test_session(9), _test_session(12)]) == 12
    assert latest_test_max([]) is None


def test_linear_trend_slope_and_intercept():
    intercept, slope = linear_trend_max_reps([(0, 10), (7, 12)])
    assert slope == pytest.approx(2 / 7, abs=1e-4)
    assert intercept == pytest.approx(10.0, abs=1e-4)
