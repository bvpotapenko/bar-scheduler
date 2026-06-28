"""Tests for the UserStore facade: composition + load_user_state."""

import pytest

from bar_scheduler.domain.models import UserProfile
from bar_scheduler.io.equipment_store import EquipmentStore
from bar_scheduler.io.history_store import HistoryStore
from bar_scheduler.io.profile_store import ProfileStore
from bar_scheduler.io.serializers import dict_to_session_result
from bar_scheduler.io.user_store import UserStore


def _session(date: str):
    return dict_to_session_result(
        {
            "date": date,
            "bodyweight_kg": 80.0,
            "grip": "neutral",
            "session_type": "S",
            "exercise_id": "pull_up",
            "completed_sets": [
                {"actual_reps": 5, "rest_seconds_before": 0, "added_weight_kg": 0.0}
            ],
        }
    )


def test_facade_exposes_typed_substores(tmp_path):
    store = UserStore(tmp_path)
    assert isinstance(store.profile, ProfileStore)
    assert isinstance(store.history, HistoryStore)
    assert isinstance(store.equipment, EquipmentStore)


def test_load_user_state_combines_profile_and_history(tmp_path):
    store = UserStore(tmp_path)
    store.profile.save(UserProfile(height_cm=180, bodyweight_kg=80.0))
    store.history.init("pull_up")
    store.history.append(_session("2026-01-01"))

    state = store.load_user_state("pull_up")
    assert state.profile.height_cm == 180
    assert [sess.date for sess in state.history] == ["2026-01-01"]


def test_load_user_state_raises_when_profile_missing(tmp_path):
    store = UserStore(tmp_path)
    store.history.init("pull_up")
    with pytest.raises(FileNotFoundError):
        store.load_user_state("pull_up")
