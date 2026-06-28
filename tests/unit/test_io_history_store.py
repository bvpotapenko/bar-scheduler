"""Tests for HistoryStore: the per-exercise JSONL history file."""

import pytest

from bar_scheduler.io.history_store import HistoryStore
from bar_scheduler.io.serializers import dict_to_session_result


def _session(date: str, session_type: str = "S", reps: int = 5):
    return dict_to_session_result(
        {
            "date": date,
            "bodyweight_kg": 80.0,
            "grip": "neutral",
            "session_type": session_type,
            "exercise_id": "pull_up",
            "completed_sets": [
                {"actual_reps": reps, "rest_seconds_before": 0, "added_weight_kg": 0.0}
            ],
        }
    )


def test_init_creates_empty_loadable_file(tmp_path):
    store = HistoryStore(tmp_path)
    store.init("pull_up")
    assert store.exists("pull_up") is True
    assert store.load("pull_up") == []


def test_load_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        HistoryStore(tmp_path).load("pull_up")


def test_append_keeps_date_order(tmp_path):
    store = HistoryStore(tmp_path)
    store.init("pull_up")
    for date in ("2026-01-03", "2026-01-01", "2026-01-02"):
        store.append(_session(date))
    assert [sess.date for sess in store.load("pull_up")] == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
    ]


def test_append_same_date_and_type_replaces(tmp_path):
    store = HistoryStore(tmp_path)
    store.init("pull_up")
    store.append(_session("2026-01-01", reps=5))
    store.append(_session("2026-01-01", reps=8))
    sessions = store.load("pull_up")
    assert len(sessions) == 1
    assert sessions[0].completed_sets[0].actual_reps == 8


def test_append_same_date_different_type_keeps_both(tmp_path):
    store = HistoryStore(tmp_path)
    store.init("pull_up")
    store.append(_session("2026-01-01", session_type="S"))
    store.append(_session("2026-01-01", session_type="H"))
    assert len(store.load("pull_up")) == 2


def test_delete_at_removes_and_raises_out_of_range(tmp_path):
    store = HistoryStore(tmp_path)
    store.init("pull_up")
    store.append(_session("2026-01-01"))
    store.append(_session("2026-01-02"))
    store.delete_at("pull_up", 0)
    assert [sess.date for sess in store.load("pull_up")] == ["2026-01-02"]
    with pytest.raises(IndexError):
        store.delete_at("pull_up", 5)
