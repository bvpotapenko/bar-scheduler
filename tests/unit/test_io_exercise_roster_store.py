"""Tests for ExerciseRosterStore: the enabled/days/targets section of profile.json."""

from bar_scheduler.domain.models import ExerciseTarget
from bar_scheduler.io.exercise_roster_store import ExerciseRosterStore
from bar_scheduler.io.profile_document import ProfileDocument


def _store(tmp_path) -> ExerciseRosterStore:
    doc = ProfileDocument(tmp_path / "profile.json")
    doc.write({"height_cm": 180, "current_bodyweight_kg": 80.0, "exercises_enabled": ["pull_up"]})
    return ExerciseRosterStore(doc)


def _raw(tmp_path) -> dict:
    return ProfileDocument(tmp_path / "profile.json").read()


def test_enable_adds_to_roster_sets_days_and_preserves_keys(tmp_path):
    _store(tmp_path).enable("dip", days_per_week=3)
    raw = _raw(tmp_path)
    assert raw["exercises_enabled"] == ["pull_up", "dip"]
    assert raw["exercise_days"]["dip"] == 3
    assert raw["height_cm"] == 180


def test_enable_is_idempotent(tmp_path):
    store = _store(tmp_path)
    store.enable("dip", days_per_week=3)
    store.enable("dip", days_per_week=4)
    raw = _raw(tmp_path)
    assert raw["exercises_enabled"] == ["pull_up", "dip"]
    assert raw["exercise_days"]["dip"] == 4


def test_disable_removes_from_roster(tmp_path):
    _store(tmp_path).disable("pull_up")
    assert _raw(tmp_path)["exercises_enabled"] == []


def test_set_target_persists(tmp_path):
    _store(tmp_path).set_target("pull_up", ExerciseTarget(reps=15))
    assert _raw(tmp_path)["exercise_targets"]["pull_up"] == {"reps": 15}


def test_set_days_updates(tmp_path):
    _store(tmp_path).set_days("pull_up", days_per_week=4)
    assert _raw(tmp_path)["exercise_days"]["pull_up"] == 4
