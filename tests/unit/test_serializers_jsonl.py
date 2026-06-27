"""Tests for sessions_from_jsonl: the bulk JSONL history reader."""

import json

import pytest

from bar_scheduler.io.serializers import ValidationError, sessions_from_jsonl


def _line(date: str, exercise_id: str = "pull_up", session_type: str = "S") -> str:
    """One valid session as a compact JSON line."""
    return json.dumps(
        {
            "date": date,
            "bodyweight_kg": 80.0,
            "grip": "neutral",
            "session_type": session_type,
            "exercise_id": exercise_id,
            "completed_sets": [
                {"actual_reps": 5, "rest_seconds_before": 0, "added_weight_kg": 0.0}
            ],
        }
    )


def test_parses_each_line_in_file_order():
    sessions = sessions_from_jsonl([_line("2026-01-02"), _line("2026-01-01")])
    assert [sess.date for sess in sessions] == ["2026-01-02", "2026-01-01"]


def test_skips_blank_lines():
    sessions = sessions_from_jsonl(["", _line("2026-01-01"), "   \n"])
    assert len(sessions) == 1
    assert sessions[0].date == "2026-01-01"


def test_skips_legacy_profile_records():
    profile_line = json.dumps({"type": "profile", "height_cm": 180})
    sessions = sessions_from_jsonl([profile_line, _line("2026-01-01")])
    assert [sess.date for sess in sessions] == ["2026-01-01"]


def test_bad_json_raises_with_line_number():
    with pytest.raises(ValidationError, match="line 2"):
        sessions_from_jsonl([_line("2026-01-01"), "{not json"])


def test_invalid_session_raises_with_line_number():
    bad = json.dumps({"date": "2026-01-01", "session_type": "S"})  # missing grip/exercise_id
    with pytest.raises(ValidationError, match="line 1"):
        sessions_from_jsonl([bad])
