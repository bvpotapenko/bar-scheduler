"""Unit tests for TrainingStateCalculator.compute (init-window handling)."""

import pytest

from bar_scheduler.containers import Container
from bar_scheduler.core.services.plan_run import HistoryWindow
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


def test_compute_uses_effective_init_window(calculator):
    early = _test_session("2026-01-01", 10)
    late = _test_session("2026-02-01", 20)  # logged after the cutoff -> excluded from init
    window = HistoryWindow(full=[early, late], for_init=[early])
    state = calculator.compute(window, 80.0, baseline_max=None)
    assert state.initial_tm == 9  # floor(0.9 * 10), from pre-cutoff session only
    assert state.latest_test_max == 10
    assert state.ff_state is state.status.fitness_fatigue_state


def test_compute_baseline_fallback_when_no_history(calculator):
    window = HistoryWindow(full=[], for_init=[])
    state = calculator.compute(window, 80.0, baseline_max=20)
    assert state.initial_tm == 18  # floor(0.9 * 20)
