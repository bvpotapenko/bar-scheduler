"""Unit tests for the TrainingStateCalculator service."""

import pytest

from bar_scheduler.containers import Container
from bar_scheduler.domain.models import SessionResult, SetResult


@pytest.fixture
def calculator():
    return Container().training_state()


def _test_session(date: str, reps: int) -> SessionResult:
    return SessionResult(
        date=date,
        bodyweight_kg=80.0,
        grip="pronated",
        session_type="TEST",
        exercise_id="pull_up",
        completed_sets=[SetResult(target_reps=reps, actual_reps=reps, rest_seconds_before=180)],
    )


def test_empty_history_status_defaults(calculator):
    status = calculator.status([], 80.0)
    assert status.training_max == 1
    assert status.latest_test_max is None
    assert status.is_plateau is False


def test_empty_history_recovery_defaults(calculator):
    status = calculator.status([], 80.0)
    assert status.deload_recommended is False
    assert status.compliance_ratio == pytest.approx(1.0)
    assert status.fatigue_score == pytest.approx(0.0)


def test_baseline_drives_status_without_history(calculator):
    status = calculator.status([], 80.0, baseline_max=20)
    assert status.training_max == 18  # floor(0.9 * 20)
    assert status.latest_test_max == 20


def test_status_from_test_sessions(calculator):
    history = [_test_session("2026-01-01", 12), _test_session("2026-01-15", 16)]
    status = calculator.status(history, 80.0)
    assert status.latest_test_max == 16  # most recent test
    assert status.training_max == 14  # floor(0.9 * 16)
