"""Unit tests for the split pure-math modules."""

import pytest

from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.math.compliance import compliance_ratio
from bar_scheduler.core.math.effort import estimate_rir_from_fraction
from bar_scheduler.core.math.formulas import best_onerm_from_leff, epley_onerm
from bar_scheduler.core.math.history_queries import latest_test_max, session_max_reps
from bar_scheduler.core.math.normalization import (
    bodyweight_normalized_reps,
    effective_reps,
    rest_factor,
    standardized_reps,
)
from bar_scheduler.core.math.onerm import estimate_onerm
from bar_scheduler.core.math.training_max import training_max, training_max_from_baseline
from bar_scheduler.core.math.trend import linear_trend_max_reps
from bar_scheduler.domain import LoadSpec
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


def test_rest_factor_clamps_short_rest_to_floor():
    assert rest_factor(30) == pytest.approx(0.80)  # below floor -> clamped


def test_effective_reps_reference_rest_is_identity():
    assert effective_reps(10, 180) == pytest.approx(10.0)  # F_rest(180) == 1.0


def test_bodyweight_normalized_reps_equal_bodyweight():
    spec = LoadSpec(bodyweight_kg=80.0)
    assert bodyweight_normalized_reps(10.0, spec, 80.0) == pytest.approx(10.0)


def test_standardized_reps_uses_loadspec_and_variant_factor():
    spec = LoadSpec(bodyweight_kg=80.0)
    # reference rest, equal bodyweight, variant 1.0 -> reps unchanged
    assert standardized_reps(10, 180, spec, 80.0, variant_factor=1.0) == pytest.approx(10.0)


@pytest.mark.parametrize(
    ("reps", "est_max", "expected"),
    [(8, 12, 4), (15, 12, 0), (10, 13, 3)],
    ids=["under", "over-clamped", "normal"],
)
def test_estimate_rir_from_fraction(reps, est_max, expected):
    assert estimate_rir_from_fraction(reps, est_max) == expected


def test_compliance_ratio_partial():
    planned = [SetResult(target_reps=10, actual_reps=None, rest_seconds_before=180)]
    completed = [SetResult(target_reps=10, actual_reps=8, rest_seconds_before=180)]
    assert compliance_ratio(planned, completed) == pytest.approx(0.8)


def test_session_and_latest_test_max():
    assert session_max_reps(_test_session(12)) == 12
    assert latest_test_max([_test_session(9), _test_session(12)]) == 12
    assert latest_test_max([]) is None


def test_linear_trend_slope_and_intercept():
    intercept, slope = linear_trend_max_reps([(0, 10), (7, 12)])
    assert slope == pytest.approx(2 / 7, abs=1e-4)
    assert intercept == pytest.approx(10.0, abs=1e-4)


def test_estimate_onerm_reports_best_set():
    pull_up = get_exercise("pull_up")
    result = estimate_onerm(pull_up, 80.0, [_test_session(10)])
    assert result is not None
    assert result["best_reps"] == 10
    assert result["1rm_kg"] == pytest.approx(106.7, abs=0.1)  # epley(80, 10)
    assert result["recommended_formula"] == "brzycki+lander"


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
