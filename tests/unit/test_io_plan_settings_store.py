"""Tests for PlanSettingsStore: plan anchors and horizon in profile.json."""

from bar_scheduler.io.plan_settings_store import PlanSettingsStore
from bar_scheduler.io.profile_document import ProfileDocument


def _store(tmp_path) -> PlanSettingsStore:
    doc = ProfileDocument(tmp_path / "profile.json")
    doc.write({"height_cm": 180, "current_bodyweight_kg": 80.0})
    return PlanSettingsStore(doc)


def test_plan_start_date_roundtrips_per_exercise(tmp_path):
    store = _store(tmp_path)
    store.save_plan_start_date("pull_up", "2026-01-01")
    store.save_plan_start_date("dip", "2026-02-02")
    assert store.plan_start_date("pull_up") == "2026-01-01"
    assert store.plan_start_date("dip") == "2026-02-02"


def test_plan_start_date_none_when_unset(tmp_path):
    assert _store(tmp_path).plan_start_date("pull_up") is None


def test_save_is_noop_when_profile_missing(tmp_path):
    store = PlanSettingsStore(ProfileDocument(tmp_path / "profile.json"))
    store.save_plan_start_date("pull_up", "2026-01-01")
    assert store.plan_start_date("pull_up") is None
    assert (tmp_path / "profile.json").exists() is False


def test_plan_weeks_roundtrips(tmp_path):
    store = _store(tmp_path)
    store.save_plan_weeks(6)
    assert store.plan_weeks() == 6


def test_plan_weeks_none_when_unset(tmp_path):
    assert _store(tmp_path).plan_weeks() is None
