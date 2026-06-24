"""Unit tests for the PlateauDetector."""

import pytest

from bar_scheduler.config.planning_params import PlateauConfig
from bar_scheduler.core.policies.plateau import PlateauDetector
from bar_scheduler.domain.models import SessionResult, SetResult


@pytest.fixture
def detector() -> PlateauDetector:
    return PlateauDetector(PlateauConfig())


def _test(date: str, reps: int) -> SessionResult:
    return SessionResult(
        date=date,
        bodyweight_kg=80.0,
        grip="pronated",
        session_type="TEST",
        exercise_id="pull_up",
        completed_sets=[SetResult(target_reps=reps, actual_reps=reps, rest_seconds_before=180)],
    )


def test_plateau_when_flat_below_best(detector):
    flat = [_test("2026-01-01", 10), _test("2026-01-15", 10)]
    history = [_test("2025-12-01", 12), *flat]
    assert detector.is_plateaued(history) is True


def test_no_plateau_when_improving(detector):
    improving = [_test("2026-01-01", 10), _test("2026-01-15", 12)]
    assert detector.is_plateaued(improving) is False


def test_no_plateau_with_single_test(detector):
    assert detector.is_plateaued([_test("2026-01-01", 10)]) is False
