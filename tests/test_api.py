"""Tests for the public API layer (src/bar_scheduler/api/api.py)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from bar_scheduler.api.api import (
    HistoryNotFoundError,
    ProfileAlreadyExistsError,
    ProfileNotFoundError,
    disable_exercise,
    enable_exercise,
    get_history,
    get_overtraining_status,
    get_plan,
    get_profile,
    init_profile,
    list_exercises,
    list_languages,
    log_session,
    set_exercise_days,
    set_exercise_target,
    update_bodyweight,
    update_equipment,
    update_profile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init(tmp_path: Path, **kwargs) -> dict:
    """Shorthand for initialising a minimal pull-up profile."""
    defaults = dict(
        height_cm=180,
        sex="male",
        bodyweight_kg=80.0,
        exercises=["pull_up"],
    )
    defaults.update(kwargs)
    return init_profile(tmp_path, **defaults)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _test_session(date: str | None = None) -> dict:
    return {
        "date": date or _today(),
        "bodyweight_kg": 80.0,
        "grip": "pronated",
        "session_type": "TEST",
        "exercise_id": "pull_up",
        "completed_sets": [{"actual_reps": 12, "rest_seconds_before": 180}],
    }


# ---------------------------------------------------------------------------
# TestInitProfile
# ---------------------------------------------------------------------------

class TestInitProfile:
    def test_creates_profile_json(self, tmp_path):
        _init(tmp_path)
        assert (tmp_path / "profile.json").exists()

    def test_creates_jsonl_for_each_exercise(self, tmp_path):
        init_profile(tmp_path, height_cm=180, sex="male", bodyweight_kg=80.0,
                     exercises=["pull_up", "dip"])
        assert (tmp_path / "pull_up_history.jsonl").exists()
        assert (tmp_path / "dip_history.jsonl").exists()

    def test_returns_correct_dict(self, tmp_path):
        result = _init(tmp_path)
        assert result["height_cm"] == 180
        assert result["sex"] == "male"
        assert result["current_bodyweight_kg"] == 80.0
        assert "pull_up" in result["exercises_enabled"]

    def test_empty_exercises_creates_profile_only(self, tmp_path):
        result = init_profile(tmp_path, height_cm=175, sex="female", bodyweight_kg=65.0,
                              exercises=[])
        assert (tmp_path / "profile.json").exists()
        assert not (tmp_path / "pull_up_history.jsonl").exists()
        assert result["exercises_enabled"] == []

    def test_already_exists_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ProfileAlreadyExistsError):
            _init(tmp_path)

    def test_already_exists_does_not_overwrite(self, tmp_path):
        _init(tmp_path, height_cm=180)
        with pytest.raises(ProfileAlreadyExistsError):
            init_profile(tmp_path, height_cm=999, sex="female", bodyweight_kg=60.0,
                         exercises=[])
        # Original profile unchanged
        assert get_profile(tmp_path)["height_cm"] == 180

    def test_unknown_exercise_raises_before_writing(self, tmp_path):
        with pytest.raises(ValueError):
            init_profile(tmp_path, height_cm=180, sex="male", bodyweight_kg=80.0,
                         exercises=["unknown_exercise"])
        assert not (tmp_path / "profile.json").exists()

    def test_invalid_sex_raises(self, tmp_path):
        with pytest.raises(ValueError):
            init_profile(tmp_path, height_cm=180, sex="robot", bodyweight_kg=80.0,
                         exercises=[])

    def test_language_stored_in_profile(self, tmp_path):
        init_profile(tmp_path, height_cm=180, sex="male", bodyweight_kg=80.0,
                     exercises=[], language="ru")
        raw = json.loads((tmp_path / "profile.json").read_text())
        assert raw.get("language") == "ru"

    def test_default_language_not_stored(self, tmp_path):
        _init(tmp_path)
        raw = json.loads((tmp_path / "profile.json").read_text())
        # "en" is omitted for backward compat (see user_profile_to_dict)
        assert "language" not in raw


# ---------------------------------------------------------------------------
# TestGetProfile
# ---------------------------------------------------------------------------

class TestGetProfile:
    def test_returns_none_before_init(self, tmp_path):
        assert get_profile(tmp_path) is None

    def test_returns_dict_after_init(self, tmp_path):
        _init(tmp_path)
        p = get_profile(tmp_path)
        assert isinstance(p, dict)
        assert p["height_cm"] == 180

    def test_includes_current_bodyweight_kg(self, tmp_path):
        _init(tmp_path, bodyweight_kg=75.5)
        assert get_profile(tmp_path)["current_bodyweight_kg"] == 75.5


# ---------------------------------------------------------------------------
# TestUpdateProfile
# ---------------------------------------------------------------------------

class TestUpdateProfile:
    def test_update_preferred_days_per_week(self, tmp_path):
        _init(tmp_path)
        result = update_profile(tmp_path, preferred_days_per_week=4)
        assert result["preferred_days_per_week"] == 4

    def test_update_rest_preference(self, tmp_path):
        _init(tmp_path)
        result = update_profile(tmp_path, rest_preference="short")
        assert result["rest_preference"] == "short"

    def test_update_max_session_duration(self, tmp_path):
        _init(tmp_path)
        result = update_profile(tmp_path, max_session_duration_minutes=45)
        assert result["max_session_duration_minutes"] == 45

    def test_update_injury_notes(self, tmp_path):
        _init(tmp_path)
        result = update_profile(tmp_path, injury_notes="sore shoulder")
        assert result["injury_notes"] == "sore shoulder"

    def test_partial_update_preserves_other_fields(self, tmp_path):
        _init(tmp_path, height_cm=182)
        update_profile(tmp_path, preferred_days_per_week=4)
        assert get_profile(tmp_path)["height_cm"] == 182

    def test_preserves_plan_start_dates_key(self, tmp_path):
        """Surgical update must not wipe plan_start_dates."""
        _init(tmp_path)
        # Inject a plan_start_dates key directly
        profile_path = tmp_path / "profile.json"
        raw = json.loads(profile_path.read_text())
        raw["plan_start_dates"] = {"pull_up": "2026-01-01"}
        profile_path.write_text(json.dumps(raw))

        update_profile(tmp_path, injury_notes="test")

        raw2 = json.loads(profile_path.read_text())
        assert raw2.get("plan_start_dates", {}).get("pull_up") == "2026-01-01"

    def test_raises_profile_not_found(self, tmp_path):
        with pytest.raises(ProfileNotFoundError):
            update_profile(tmp_path, preferred_days_per_week=3)

    def test_invalid_rest_preference_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ValueError):
            update_profile(tmp_path, rest_preference="turbo")

    def test_invalid_days_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ValueError):
            update_profile(tmp_path, preferred_days_per_week=6)

    def test_update_height_cm(self, tmp_path):
        _init(tmp_path, height_cm=180)
        result = update_profile(tmp_path, height_cm=182)
        assert result["height_cm"] == 182

    def test_update_sex(self, tmp_path):
        _init(tmp_path, sex="male")
        result = update_profile(tmp_path, sex="female")
        assert result["sex"] == "female"

    def test_invalid_sex_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ValueError):
            update_profile(tmp_path, sex="robot")

    def test_invalid_height_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ValueError):
            update_profile(tmp_path, height_cm=0)


# ---------------------------------------------------------------------------
# TestSetExerciseTarget
# ---------------------------------------------------------------------------

class TestSetExerciseTarget:
    def test_set_reps_only(self, tmp_path):
        _init(tmp_path)
        set_exercise_target(tmp_path, "pull_up", reps=20)
        p = get_profile(tmp_path)
        assert "pull_up" in p.get("exercise_targets", {})
        assert p["exercise_targets"]["pull_up"]["reps"] == 20

    def test_set_reps_and_weight(self, tmp_path):
        _init(tmp_path)
        set_exercise_target(tmp_path, "pull_up", reps=10, weight_kg=10.0)
        targets = get_profile(tmp_path)["exercise_targets"]
        assert targets["pull_up"]["reps"] == 10
        assert targets["pull_up"]["weight_kg"] == 10.0

    def test_overwrites_existing_target(self, tmp_path):
        _init(tmp_path)
        set_exercise_target(tmp_path, "pull_up", reps=15)
        set_exercise_target(tmp_path, "pull_up", reps=20)
        assert get_profile(tmp_path)["exercise_targets"]["pull_up"]["reps"] == 20

    def test_unknown_exercise_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ValueError):
            set_exercise_target(tmp_path, "unknown_ex", reps=10)

    def test_zero_reps_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ValueError):
            set_exercise_target(tmp_path, "pull_up", reps=0)

    def test_negative_weight_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ValueError):
            set_exercise_target(tmp_path, "pull_up", reps=10, weight_kg=-1.0)


# ---------------------------------------------------------------------------
# TestSetExerciseDays
# ---------------------------------------------------------------------------

class TestSetExerciseDays:
    def test_set_days(self, tmp_path):
        _init(tmp_path)
        set_exercise_days(tmp_path, "pull_up", 4)
        p = get_profile(tmp_path)
        assert p.get("exercise_days", {}).get("pull_up") == 4

    def test_override_existing(self, tmp_path):
        _init(tmp_path)
        set_exercise_days(tmp_path, "pull_up", 4)
        set_exercise_days(tmp_path, "pull_up", 2)
        assert get_profile(tmp_path)["exercise_days"]["pull_up"] == 2

    def test_out_of_range_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ValueError):
            set_exercise_days(tmp_path, "pull_up", 6)
        with pytest.raises(ValueError):
            set_exercise_days(tmp_path, "pull_up", 0)

    def test_unknown_exercise_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ValueError):
            set_exercise_days(tmp_path, "unicorn", 3)


# ---------------------------------------------------------------------------
# TestEnableDisableExercise
# ---------------------------------------------------------------------------

class TestEnableDisableExercise:
    def test_enable_adds_to_list_and_creates_jsonl(self, tmp_path):
        _init(tmp_path, exercises=[])
        enable_exercise(tmp_path, "pull_up")
        assert "pull_up" in get_profile(tmp_path)["exercises_enabled"]
        assert (tmp_path / "pull_up_history.jsonl").exists()

    def test_enable_idempotent(self, tmp_path):
        _init(tmp_path)
        enable_exercise(tmp_path, "pull_up")
        enable_exercise(tmp_path, "pull_up")
        assert get_profile(tmp_path)["exercises_enabled"].count("pull_up") == 1

    def test_disable_removes_from_list(self, tmp_path):
        _init(tmp_path)
        disable_exercise(tmp_path, "pull_up")
        assert "pull_up" not in get_profile(tmp_path)["exercises_enabled"]

    def test_disable_does_not_delete_jsonl(self, tmp_path):
        _init(tmp_path)
        jsonl = tmp_path / "pull_up_history.jsonl"
        assert jsonl.exists()
        disable_exercise(tmp_path, "pull_up")
        assert jsonl.exists()

    def test_disable_noop_when_not_enabled(self, tmp_path):
        _init(tmp_path, exercises=[])
        disable_exercise(tmp_path, "pull_up")  # should not raise
        assert get_profile(tmp_path)["exercises_enabled"] == []

    def test_enable_unknown_exercise_raises(self, tmp_path):
        _init(tmp_path, exercises=[])
        with pytest.raises(ValueError):
            enable_exercise(tmp_path, "fantasy_ex")


# ---------------------------------------------------------------------------
# TestListExercises
# ---------------------------------------------------------------------------

class TestListExercises:
    def test_returns_list(self):
        result = list_exercises()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_contains_pull_up(self):
        ids = [e["id"] for e in list_exercises()]
        assert "pull_up" in ids

    def test_has_required_keys(self):
        for ex in list_exercises():
            assert "id" in ex
            assert "display_name" in ex
            assert "muscle_group" in ex
            assert "variants" in ex
            assert "primary_variant" in ex
            assert "has_variant_rotation" in ex

    def test_no_data_dir_needed(self):
        # Just verifying it takes no positional args
        result = list_exercises()
        assert result is not None


# ---------------------------------------------------------------------------
# TestListLanguages
# ---------------------------------------------------------------------------

class TestListLanguages:
    def test_returns_list_including_en(self):
        langs = list_languages()
        assert isinstance(langs, list)
        assert "en" in langs

    def test_no_data_dir_needed(self):
        result = list_languages()
        assert result is not None


# ---------------------------------------------------------------------------
# TestEndToEnd
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_init_log_get_plan(self, tmp_path):
        init_profile(tmp_path, height_cm=180, sex="male", bodyweight_kg=80.0,
                     exercises=["pull_up"])

        log_session(tmp_path, "pull_up", _test_session())

        plan = get_plan(tmp_path, "pull_up")
        assert "sessions" in plan
        assert "status" in plan
        assert plan["status"]["training_max"] == 10  # floor(0.9 * 12)

    def test_full_profile_lifecycle(self, tmp_path):
        init_profile(tmp_path, height_cm=175, sex="female", bodyweight_kg=65.0,
                     exercises=["pull_up"])

        update_profile(tmp_path, preferred_days_per_week=4, rest_preference="short")
        set_exercise_target(tmp_path, "pull_up", reps=20)
        set_exercise_days(tmp_path, "pull_up", 4)

        enable_exercise(tmp_path, "dip")
        assert "dip" in get_profile(tmp_path)["exercises_enabled"]
        assert (tmp_path / "dip_history.jsonl").exists()

        disable_exercise(tmp_path, "dip")
        assert "dip" not in get_profile(tmp_path)["exercises_enabled"]
        assert (tmp_path / "dip_history.jsonl").exists()  # file preserved

        p = get_profile(tmp_path)
        assert p["preferred_days_per_week"] == 4
        assert p["exercise_targets"]["pull_up"]["reps"] == 20

    def test_get_overtraining_status_after_init(self, tmp_path):
        init_profile(tmp_path, height_cm=180, sex="male", bodyweight_kg=80.0,
                     exercises=["pull_up"])
        ot = get_overtraining_status(tmp_path, "pull_up")
        assert "level" in ot
        assert ot["level"] == 0

    def test_get_history_empty_after_init(self, tmp_path):
        init_profile(tmp_path, height_cm=180, sex="male", bodyweight_kg=80.0,
                     exercises=["pull_up"])
        assert get_history(tmp_path, "pull_up") == []


# ---------------------------------------------------------------------------
# TestUpdateBodyweight
# ---------------------------------------------------------------------------

class TestUpdateBodyweight:
    def test_updates_bodyweight(self, tmp_path):
        _init(tmp_path, bodyweight_kg=80.0)
        update_bodyweight(tmp_path, 82.5)
        assert get_profile(tmp_path)["current_bodyweight_kg"] == 82.5

    def test_raises_profile_not_found(self, tmp_path):
        with pytest.raises(ProfileNotFoundError):
            update_bodyweight(tmp_path, 80.0)

    def test_zero_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ValueError):
            update_bodyweight(tmp_path, 0)

    def test_negative_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ValueError):
            update_bodyweight(tmp_path, -5.0)


# ---------------------------------------------------------------------------
# TestUpdateEquipment
# ---------------------------------------------------------------------------

class TestUpdateEquipment:
    def test_sets_equipment(self, tmp_path):
        _init(tmp_path)
        # No exception — exercise JSONL exists (created by init)
        update_equipment(
            tmp_path, "pull_up",
            active_item="BAR_ONLY",
            available_items=["BAR_ONLY"],
        )

    def test_uninitialised_exercise_raises(self, tmp_path):
        _init(tmp_path, exercises=[])
        with pytest.raises(HistoryNotFoundError):
            update_equipment(
                tmp_path, "pull_up",
                active_item="BAR_ONLY",
                available_items=["BAR_ONLY"],
            )
