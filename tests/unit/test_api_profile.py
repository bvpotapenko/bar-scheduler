"""Integration tests for the profile api flows on a temp data dir."""

import pytest

from bar_scheduler import api


def test_init_and_get_profile(tmp_path):
    api.init_profile(tmp_path, height_cm=175, bodyweight_kg=70.0)
    profile = api.get_profile(tmp_path)
    assert profile["height_cm"] == 175
    assert profile["current_bodyweight_kg"] == pytest.approx(70.0)
    assert profile["exercises_enabled"] == []


def test_init_twice_raises(tmp_path):
    api.init_profile(tmp_path, height_cm=175, bodyweight_kg=70.0)
    with pytest.raises(api.ProfileAlreadyExistsError):
        api.init_profile(tmp_path, height_cm=175, bodyweight_kg=70.0)


def test_update_profile_partial(data_dir):
    updated = api.update_profile(data_dir, bodyweight_kg=82.5)
    assert updated["current_bodyweight_kg"] == pytest.approx(82.5)
    assert updated["height_cm"] == 180  # unchanged


def test_update_profile_language_default_removes_key(data_dir):
    api.update_profile(data_dir, language="fr")
    assert api.get_profile(data_dir)["language"] == "fr"
    restored = api.update_profile(data_dir, language="en")
    assert "language" not in restored  # "en" is the omitted default


def test_update_profile_rejects_bad_values(data_dir):
    with pytest.raises(ValueError):
        api.update_profile(data_dir, height_cm=0)
