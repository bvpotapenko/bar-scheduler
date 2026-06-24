"""Unit tests for the overtraining 7-day window and frequency sensitivity."""

from datetime import datetime

import pytest

from bar_scheduler.core.services.overtraining import OvertrainingDetector
from bar_scheduler.domain.models import SessionResult, SetResult

_REF = datetime(2026, 1, 7)


def _severity(history, days_per_week=3, reference_date=None) -> dict:
    return OvertrainingDetector().severity(history, days_per_week, reference_date)


def _session(date: str) -> SessionResult:
    return SessionResult(
        date=date,
        bodyweight_kg=80.0,
        grip="pronated",
        session_type="S",
        exercise_id="pull_up",
        completed_sets=[SetResult(target_reps=5, actual_reps=5, rest_seconds_before=120)],
    )


def test_sessions_outside_window_are_ignored():
    # 2025-12-30 falls before the 7-day window (cutoff 2026-01-01).
    history = [_session("2025-12-30"), _session("2026-01-07")]
    assessment = _severity(history, 3, _REF)
    assert assessment["sessions"] == 0  # only one in window -> zero stats
    assert assessment["level"] == 0


@pytest.mark.parametrize(
    ("days_per_week", "expected_level"),
    [(1, 3), (7, 0)],
    ids=["low-frequency-severe", "high-frequency-none"],
)
def test_frequency_drives_severity(days_per_week, expected_level):
    history = [_session("2026-01-05"), _session("2026-01-06"), _session("2026-01-07")]
    assert _severity(history, days_per_week, _REF)["level"] == expected_level
