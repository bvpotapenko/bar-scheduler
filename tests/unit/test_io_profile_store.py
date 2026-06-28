"""Tests for ProfileStore: UserProfile load/save + partial field updates."""

import pytest

from bar_scheduler.domain.models import UserProfile
from bar_scheduler.io.profile_document import ProfileDocument
from bar_scheduler.io.profile_store import ProfileStore
from bar_scheduler.io.serializers import ValidationError


def _store(tmp_path) -> ProfileStore:
    return ProfileStore(ProfileDocument(tmp_path / "profile.json"))


def test_save_then_load_roundtrips(tmp_path):
    store = _store(tmp_path)
    store.save(UserProfile(height_cm=180, bodyweight_kg=80.0, language="ru"))
    loaded = store.load()
    assert (loaded.height_cm, loaded.language) == (180, "ru")
    assert loaded.bodyweight_kg == pytest.approx(80.0)


def test_load_missing_returns_none(tmp_path):
    assert _store(tmp_path).load() is None


def test_update_fields_changes_values_and_preserves_satellites(tmp_path):
    store = _store(tmp_path)
    store.save(UserProfile(height_cm=180, bodyweight_kg=80.0))
    with ProfileDocument(tmp_path / "profile.json").mutate() as raw:
        raw["plan_start_dates"] = {"pull_up": "2026-01-01"}

    store.update_fields(height_cm=190, bodyweight_kg=82.0)

    reloaded = ProfileDocument(tmp_path / "profile.json").read()
    assert reloaded["height_cm"] == 190
    assert reloaded["current_bodyweight_kg"] == pytest.approx(82.0)
    assert reloaded["plan_start_dates"] == {"pull_up": "2026-01-01"}


def test_update_language_en_pops_key(tmp_path):
    store = _store(tmp_path)
    store.save(UserProfile(height_cm=180, bodyweight_kg=80.0, language="ru"))
    store.update_fields(language="en")
    assert "language" not in ProfileDocument(tmp_path / "profile.json").read()


def test_update_fields_validates_consistency(tmp_path):
    store = _store(tmp_path)  # no profile on disk -> read() is {}
    with pytest.raises(ValidationError):
        store.update_fields(language="ru")  # height_cm missing -> invalid
