"""Unit tests for rep normalization, effort, and compliance math."""

import pytest

from bar_scheduler.core.math.compliance import compliance_ratio
from bar_scheduler.core.math.effort import estimate_rir_from_fraction
from bar_scheduler.core.math.normalization import (
    bodyweight_normalized_reps,
    effective_reps,
    rest_factor,
    standardized_reps,
)
from bar_scheduler.domain import LoadSpec
from bar_scheduler.domain.models import SetResult


def test_rest_factor_clamps_short_rest_to_floor():
    assert rest_factor(30) == pytest.approx(0.8)  # below floor -> clamped


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
