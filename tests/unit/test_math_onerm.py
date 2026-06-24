"""Unit tests for the 1RM formulas and estimate_onerm."""

import pytest

from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.math.formulas import best_onerm_from_leff, epley_onerm
from bar_scheduler.core.math.onerm import estimate_onerm
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
    ("load", "reps", "expected"),
    [(100.0, 5, 116.6667), (90.0, 10, 120.0), (80.0, 0, 0.0)],
    ids=["5reps", "10reps", "zero-reps"],
)
def test_epley_onerm(load, reps, expected):
    assert epley_onerm(load, reps) == pytest.approx(expected, abs=1e-3)


def test_best_onerm_from_leff_strength_range():
    # reps<=5 -> avg(Brzycki, Lander); reps=1 -> avg(100, 101.389)
    assert best_onerm_from_leff(100.0, 1) == pytest.approx(100.69, abs=0.05)


def test_best_onerm_from_leff_zero_reps_is_none():
    assert best_onerm_from_leff(100.0, 0) is None


def test_estimate_onerm_reports_best_set():
    pull_up = get_exercise("pull_up")
    estimate = estimate_onerm(pull_up, 80.0, [_test_session(10)])
    assert estimate is not None
    assert estimate["best_reps"] == 10
    assert estimate["1rm_kg"] == pytest.approx(106.7, abs=0.1)  # epley(80, 10)
    assert estimate["recommended_formula"] == "brzycki+lander"


def test_estimate_onerm_no_usable_sets_is_none():
    empty = SessionResult(
        date="2026-01-01",
        bodyweight_kg=80.0,
        grip="pronated",
        session_type="S",
        exercise_id="pull_up",
        completed_sets=[],
    )
    assert estimate_onerm(get_exercise("pull_up"), 80.0, [empty]) is None
