"""Unit tests for the overtraining-severity assessment."""

from datetime import datetime

import pytest

from bar_scheduler.core.services.overtraining import OvertrainingDetector
from bar_scheduler.domain.models import SessionResult, SetResult


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


_REF = datetime(2026, 1, 7)


def test_empty_history_is_level_zero():
    assert _severity([]) == {
        "level": 0,
        "sessions": 0,
        "span_days": 0,
        "extra_rest_days": 0,
        "description": "",
    }


def test_single_recent_session_is_level_zero():
    result = _severity([_session("2026-01-06")], 3, _REF)
    assert result["level"] == 0
    assert result["sessions"] == 0  # <2 in window -> zero stats


def test_three_sessions_in_three_days_is_moderate():
    history = [_session("2026-01-05"), _session("2026-01-06"), _session("2026-01-07")]
    result = _severity(history, 3, _REF)
    # expected (3-1)*(7/3)=4.667 days, actual span 2 -> extra round(2.667)=3 -> level 2
    assert result["level"] == 2
    assert result["sessions"] == 3
    assert result["span_days"] == 2
    assert result["extra_rest_days"] == 3
    assert result["description"] == "3 sessions in 3 days"


def test_well_spaced_sessions_are_level_zero():
    history = [_session("2026-01-01"), _session("2026-01-07")]
    result = _severity(history, 3, _REF)
    assert result["level"] == 0
    assert result["extra_rest_days"] == 0


def test_sessions_outside_window_are_ignored():
    # 2025-12-30 falls before the 7-day window (cutoff 2026-01-01).
    history = [_session("2025-12-30"), _session("2026-01-07")]
    result = _severity(history, 3, _REF)
    assert result["sessions"] == 0  # only one in window -> zero stats
    assert result["level"] == 0


@pytest.mark.parametrize(
    ("days_per_week", "expected_level"),
    [(1, 3), (7, 0)],
    ids=["low-frequency-severe", "high-frequency-none"],
)
def test_frequency_drives_severity(days_per_week, expected_level):
    history = [_session("2026-01-05"), _session("2026-01-06"), _session("2026-01-07")]
    assert _severity(history, days_per_week, _REF)["level"] == expected_level
