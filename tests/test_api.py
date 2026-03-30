"""Tests for the public API layer (src/bar_scheduler/api/api.py)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from bar_scheduler.api import (
    HistoryNotFoundError,
    ProfileAlreadyExistsError,
    ProfileNotFoundError,
    check_band_progression,
    compute_equipment_adjustment,
    compute_leff,
    delete_exercise_history,
    disable_exercise,
    enable_exercise,
    get_assistance_kg,
    get_assist_progression,
    get_current_equipment,
    get_data_dir,
    get_exercise_info,
    get_history,
    get_next_band_step,
    get_overtraining_status,
    get_plan,
    get_plan_weeks,
    get_profile,
    init_profile,
    list_exercises,
    log_session,
    parse_compact_sets,
    parse_sets_string,
    set_exercise_days,
    set_exercise_target,
    set_plan_start_date,
    set_plan_weeks,
    training_max_from_baseline,
    update_bodyweight,
    update_equipment,
    update_height,
    update_profile,
)
from bar_scheduler.api.types import SessionInput, SetInput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init(tmp_path: Path, exercises=None, days_per_week=3, **kwargs) -> dict:
    """Shorthand for initialising a minimal profile with optional exercises."""
    if exercises is None:
        exercises = ["pull_up"]
    valid_keys = {"height_cm", "bodyweight_kg", "language"}
    profile_kwargs = {k: v for k, v in kwargs.items() if k in valid_keys}
    profile_kwargs.setdefault("height_cm", 180)
    profile_kwargs.setdefault("bodyweight_kg", 80.0)
    init_profile(tmp_path, **profile_kwargs)
    for ex in exercises:
        enable_exercise(tmp_path, ex, days_per_week=days_per_week)
    return get_profile(tmp_path)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _test_session(date: str | None = None) -> SessionInput:
    return SessionInput(
        date=date or _today(),
        session_type="TEST",
        bodyweight_kg=80.0,
        grip="pronated",
        sets=[SetInput(reps=12, rest_seconds=180)],
    )


# ---------------------------------------------------------------------------
# TestInitProfile
# ---------------------------------------------------------------------------


class TestInitProfile:
    def test_returns_correct_dict(self, tmp_path):
        result = _init(tmp_path)
        assert result["height_cm"] == 180
        assert result["current_bodyweight_kg"] == 80.0
        assert "pull_up" in result["exercises_enabled"]

    def test_empty_exercises_creates_profile_only(self, tmp_path):
        result = _init(tmp_path, exercises=[])
        assert (tmp_path / "profile.json").exists()
        assert not (tmp_path / "pull_up_history.jsonl").exists()
        assert result["exercises_enabled"] == []

    def test_exercises_defaults_to_empty_on_bare_init(self, tmp_path):
        result = init_profile(tmp_path, height_cm=175, bodyweight_kg=80.0)
        assert result["exercises_enabled"] == []
        assert not (tmp_path / "pull_up_history.jsonl").exists()

    def test_already_exists_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ProfileAlreadyExistsError):
            _init(tmp_path)

    def test_already_exists_does_not_overwrite(self, tmp_path):
        _init(tmp_path, height_cm=180)
        with pytest.raises(ProfileAlreadyExistsError):
            init_profile(tmp_path, height_cm=999, bodyweight_kg=60.0)
        # Original profile unchanged
        assert get_profile(tmp_path)["height_cm"] == 180

    def test_unknown_exercise_raises(self, tmp_path):
        init_profile(tmp_path, height_cm=180, bodyweight_kg=80.0)
        with pytest.raises(ValueError):
            enable_exercise(tmp_path, "unknown_exercise", days_per_week=3)

    def test_language_stored_in_profile(self, tmp_path):
        init_profile(tmp_path, height_cm=180, bodyweight_kg=80.0, language="ru")
        raw = json.loads((tmp_path / "profile.json").read_text())
        assert raw.get("language") == "ru"

    def test_default_language_not_stored(self, tmp_path):
        _init(tmp_path)
        raw = json.loads((tmp_path / "profile.json").read_text())
        # "en" is omitted for backward compat (see user_profile_to_dict)
        assert "language" not in raw

    def test_init_profile_no_exercises_param(self, tmp_path):
        """init_profile creates a bare profile; exercises added via enable_exercise."""
        result = init_profile(tmp_path, height_cm=175, bodyweight_kg=70.0)
        assert result["exercises_enabled"] == []
        assert result.get("exercise_days", {}) == {}


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
    def test_partial_update_preserves_other_fields(self, tmp_path):
        _init(tmp_path, height_cm=182)
        update_profile(tmp_path, height_cm=184)
        assert get_profile(tmp_path)["height_cm"] == 184

    def test_preserves_plan_start_dates_key(self, tmp_path):
        """Surgical update must not wipe plan_start_dates."""
        _init(tmp_path)
        profile_path = tmp_path / "profile.json"
        raw = json.loads(profile_path.read_text())
        raw["plan_start_dates"] = {"pull_up": "2026-01-01"}
        profile_path.write_text(json.dumps(raw))

        update_profile(tmp_path, height_cm=180)

        raw2 = json.loads(profile_path.read_text())
        assert raw2.get("plan_start_dates", {}).get("pull_up") == "2026-01-01"

    def test_raises_profile_not_found(self, tmp_path):
        with pytest.raises(ProfileNotFoundError):
            update_profile(tmp_path, height_cm=180)

    def test_update_height_cm(self, tmp_path):
        _init(tmp_path, height_cm=180)
        result = update_profile(tmp_path, height_cm=182)
        assert result["height_cm"] == 182

    def test_invalid_height_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ValueError):
            update_profile(tmp_path, height_cm=0)

    def test_update_bodyweight_via_update_profile(self, tmp_path):
        _init(tmp_path)
        update_profile(tmp_path, bodyweight_kg=82.5)
        assert get_profile(tmp_path)["current_bodyweight_kg"] == 82.5

    def test_update_language_via_update_profile(self, tmp_path):
        _init(tmp_path)
        update_profile(tmp_path, language="de")
        assert get_profile(tmp_path)["language"] == "de"

    def test_update_multiple_fields_at_once(self, tmp_path):
        _init(tmp_path, height_cm=180)
        result = update_profile(tmp_path, height_cm=185, bodyweight_kg=82.0)
        assert result["height_cm"] == 185
        assert result["current_bodyweight_kg"] == 82.0

    def test_invalid_bodyweight_raises(self, tmp_path):
        _init(tmp_path)
        with pytest.raises(ValueError):
            update_profile(tmp_path, bodyweight_kg=0)


class TestUpdateHeight:
    def test_updates_height(self, tmp_path):
        _init(tmp_path, height_cm=180)
        result = update_height(tmp_path, height_cm=182)
        assert result["height_cm"] == 182

    def test_raises_profile_not_found(self, tmp_path):
        with pytest.raises(ProfileNotFoundError):
            update_height(tmp_path, height_cm=180)


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
        enable_exercise(tmp_path, "pull_up", days_per_week=3)
        assert "pull_up" in get_profile(tmp_path)["exercises_enabled"]
        assert (tmp_path / "pull_up_history.jsonl").exists()

    def test_enable_sets_exercise_days(self, tmp_path):
        _init(tmp_path, exercises=[])
        enable_exercise(tmp_path, "pull_up", days_per_week=4)
        assert get_profile(tmp_path)["exercise_days"]["pull_up"] == 4

    def test_enable_idempotent(self, tmp_path):
        _init(tmp_path)
        enable_exercise(tmp_path, "pull_up", days_per_week=3)
        enable_exercise(tmp_path, "pull_up", days_per_week=3)
        assert get_profile(tmp_path)["exercises_enabled"].count("pull_up") == 1

    def test_disable_removes_from_list(self, tmp_path):
        _init(tmp_path)
        disable_exercise(tmp_path, "pull_up")
        assert "pull_up" not in get_profile(tmp_path)["exercises_enabled"]

    def test_disable_noop_when_not_enabled(self, tmp_path):
        _init(tmp_path, exercises=[])
        disable_exercise(tmp_path, "pull_up")  # should not raise
        assert get_profile(tmp_path)["exercises_enabled"] == []

    def test_enable_unknown_exercise_raises(self, tmp_path):
        _init(tmp_path, exercises=[])
        with pytest.raises(ValueError):
            enable_exercise(tmp_path, "fantasy_ex", days_per_week=3)

    def test_enable_exercise_requires_days_per_week(self, tmp_path):
        """days_per_week is a required keyword-only argument."""
        _init(tmp_path, exercises=[])
        with pytest.raises(TypeError):
            enable_exercise(tmp_path, "pull_up")  # missing days_per_week


# ---------------------------------------------------------------------------
# TestListExercises
# ---------------------------------------------------------------------------


class TestListExercises:
    def test_contains_pull_up(self):
        assert "pull_up" in list_exercises()


# ---------------------------------------------------------------------------
# TestEndToEnd
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_init_log_get_plan(self, tmp_path):
        _init(tmp_path)
        log_session(tmp_path, "pull_up", _test_session())
        plan = get_plan(tmp_path, "pull_up")
        assert "sessions" in plan
        assert "status" in plan
        assert plan["status"]["training_max"] == 10  # floor(0.9 * 12)

    def test_full_profile_lifecycle(self, tmp_path):
        _init(tmp_path, height_cm=175, bodyweight_kg=65.0)
        set_exercise_target(tmp_path, "pull_up", reps=20)
        set_exercise_days(tmp_path, "pull_up", 4)

        enable_exercise(tmp_path, "dip", days_per_week=3)
        assert "dip" in get_profile(tmp_path)["exercises_enabled"]
        assert (tmp_path / "dip_history.jsonl").exists()

        disable_exercise(tmp_path, "dip")
        assert "dip" not in get_profile(tmp_path)["exercises_enabled"]
        assert (tmp_path / "dip_history.jsonl").exists()  # file preserved

        p = get_profile(tmp_path)
        assert p["exercise_targets"]["pull_up"]["reps"] == 20

    def test_get_overtraining_status_after_init(self, tmp_path):
        _init(tmp_path)
        ot = get_overtraining_status(tmp_path, "pull_up")
        assert "level" in ot
        assert ot["level"] == 0

    def test_get_history_empty_after_init(self, tmp_path):
        _init(tmp_path)
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
    def test_uninitialised_exercise_raises(self, tmp_path):
        _init(tmp_path, exercises=[])
        with pytest.raises(HistoryNotFoundError):
            update_equipment(tmp_path, "pull_up", available_items=["BAR_ONLY"])


# ---------------------------------------------------------------------------
# TestGetDataDir
# ---------------------------------------------------------------------------


class TestGetDataDir:
    def test_returns_path_in_home(self):
        result = get_data_dir()
        assert result == Path.home() / ".bar-scheduler"


# ---------------------------------------------------------------------------
# TestGetExerciseInfo
# ---------------------------------------------------------------------------


class TestGetExerciseInfo:
    def test_known_id_returns_dict(self):
        info = get_exercise_info("pull_up")
        assert info["id"] == "pull_up"
        assert "bw_fraction" in info
        assert "onerm_includes_bodyweight" in info
        assert "display_name" in info

    def test_unknown_id_raises(self):
        with pytest.raises(ValueError):
            get_exercise_info("unicorn")

    def test_consistent_with_list_exercises(self):
        info = get_exercise_info("pull_up")
        match = list_exercises()["pull_up"]
        for key in match:
            assert info[key] == match[key]


# ---------------------------------------------------------------------------
# TestTrainingMaxFromBaseline
# ---------------------------------------------------------------------------


class TestTrainingMaxFromBaseline:
    def test_baseline_10(self):
        assert training_max_from_baseline(10) == 9

    def test_baseline_1(self):
        assert training_max_from_baseline(1) == 1  # floor(0.9) = 0, but min is 1


# ---------------------------------------------------------------------------
# TestLogSessionEquipmentAutoAttach
# ---------------------------------------------------------------------------


class TestLogSessionEquipmentAutoAttach:
    def test_auto_attaches_snapshot_when_equipment_set(self, tmp_path):
        _init(tmp_path)
        update_equipment(tmp_path, "pull_up", available_items=["BAR_ONLY"])
        result = log_session(tmp_path, "pull_up", _test_session())
        assert result["equipment_snapshot"] is not None
        assert result["equipment_snapshot"]["active_item"] == "BAR_ONLY"

    def test_no_snapshot_when_no_equipment_configured(self, tmp_path):
        _init(tmp_path)
        result = log_session(tmp_path, "pull_up", _test_session())
        assert result.get("equipment_snapshot") is None

    def test_auto_attaches_band_snapshot(self, tmp_path):
        _init(tmp_path)
        update_equipment(
            tmp_path, "pull_up", available_items=["BAR_ONLY", "BAND_SET"],
            available_band_assistance_kg=[20.0],
        )
        result = log_session(tmp_path, "pull_up", _test_session())
        assert result["equipment_snapshot"] is not None
        assert result["equipment_snapshot"]["active_item"] in ("BAR_ONLY", "BAND_SET")


# ---------------------------------------------------------------------------
# TestPlanConfig
# ---------------------------------------------------------------------------


class TestPlanConfig:
    def test_set_and_get_plan_weeks(self, tmp_path):
        _init(tmp_path)
        set_plan_weeks(tmp_path, 6)
        assert get_plan_weeks(tmp_path) == 6

    def test_plan_weeks_default_none(self, tmp_path):
        _init(tmp_path)
        assert get_plan_weeks(tmp_path) is None

    def test_set_plan_start_date_missing_profile_raises(self, tmp_path):
        with pytest.raises(ProfileNotFoundError):
            set_plan_start_date(tmp_path, "pull_up", "2026-01-01")


# ---------------------------------------------------------------------------
# TestPlanCache
# ---------------------------------------------------------------------------


class TestPlanCache:
    def test_cache_hit_skips_generate_plan(self, tmp_path):
        _init(tmp_path)
        log_session(tmp_path, "pull_up", _test_session())
        from unittest.mock import patch
        import bar_scheduler.api._plan as plan_mod

        with patch.object(
            plan_mod, "generate_plan", wraps=plan_mod.generate_plan
        ) as mock_gen:
            get_plan(tmp_path, "pull_up")
            get_plan(tmp_path, "pull_up")
        assert mock_gen.call_count == 1

    def test_history_change_invalidates_cache(self, tmp_path):
        _init(tmp_path)
        log_session(tmp_path, "pull_up", _test_session())
        from unittest.mock import patch
        import bar_scheduler.api._plan as plan_mod

        with patch.object(
            plan_mod, "generate_plan", wraps=plan_mod.generate_plan
        ) as mock_gen:
            get_plan(tmp_path, "pull_up")
            log_session(tmp_path, "pull_up", _test_session("2026-02-10"))
            get_plan(tmp_path, "pull_up")
        assert mock_gen.call_count == 2

    def test_profile_change_invalidates_cache(self, tmp_path):
        _init(tmp_path)
        log_session(tmp_path, "pull_up", _test_session())
        from unittest.mock import patch
        import bar_scheduler.api._plan as plan_mod
        from bar_scheduler.api import update_profile

        with patch.object(
            plan_mod, "generate_plan", wraps=plan_mod.generate_plan
        ) as mock_gen:
            get_plan(tmp_path, "pull_up")
            update_profile(tmp_path, bodyweight_kg=85.0)
            get_plan(tmp_path, "pull_up")
        assert mock_gen.call_count == 2


# ---------------------------------------------------------------------------
# TestDeleteExerciseHistory
# ---------------------------------------------------------------------------


class TestDeleteExerciseHistory:
    def test_deletes_jsonl_file(self, tmp_path):
        _init(tmp_path)
        log_session(tmp_path, "pull_up", _test_session())
        jsonl = tmp_path / "pull_up_history.jsonl"
        assert jsonl.exists()
        delete_exercise_history(tmp_path, "pull_up")
        assert not jsonl.exists()


# ---------------------------------------------------------------------------
# TestGetCurrentEquipment
# ---------------------------------------------------------------------------


class TestGetCurrentEquipment:
    def test_returns_dict_with_expected_keys(self, tmp_path):
        _init(tmp_path)
        update_equipment(tmp_path, "pull_up", available_items=["BAR_ONLY"])
        eq = get_current_equipment(tmp_path, "pull_up")
        assert eq is not None
        for key in (
            "exercise_id",
            "recommended_item",
            "available_items",
            "assistance_kg",
            "is_bss_degraded",
        ):
            assert key in eq
        assert eq["recommended_item"] == "BAR_ONLY"
        assert isinstance(eq["is_bss_degraded"], bool)


# ---------------------------------------------------------------------------
# TestCheckBandProgression
# ---------------------------------------------------------------------------


class TestCheckBandProgression:
    def test_returns_false_with_no_history(self, tmp_path):
        _init(tmp_path)
        assert check_band_progression(tmp_path, "pull_up") is False


# ---------------------------------------------------------------------------
# TestEquipmentComputations
# ---------------------------------------------------------------------------


class TestEquipmentComputations:
    def test_compute_leff_basic(self):
        assert compute_leff(1.0, 80.0, 0.0, 0.0) == 80.0

    def test_compute_leff_with_assistance(self):
        assert compute_leff(1.0, 80.0, 0.0, 8.0) == 72.0

    def test_equipment_adjustment_load_increase(self):
        result = compute_equipment_adjustment(70.0, 80.0)
        assert result["reps_factor"] == 0.80
        assert "description" in result

    def test_get_next_band_step(self):
        assert get_next_band_step("BAND_SET", "pull_up") == "BAR_ONLY"
        assert get_next_band_step("BAR_ONLY", "pull_up") is None

    def test_get_assist_progression(self):
        bp = get_assist_progression("pull_up")
        assert "BAND_SET" in bp
        assert "BAR_ONLY" in bp
        assert bp.index("BAND_SET") < bp.index("BAR_ONLY")

    def test_get_assistance_kg_band_set(self):
        kg = get_assistance_kg("pull_up", "BAND_SET", available_band_assistance_kg=[20.0])
        assert kg == 20.0


# ---------------------------------------------------------------------------
# TestMachineAssistanceList
# ---------------------------------------------------------------------------


class TestMachineAssistanceList:
    def test_update_equipment_stores_machine_assistance_list(self, tmp_path):
        _init(tmp_path)
        update_equipment(
            tmp_path,
            "pull_up",
            available_items=["MACHINE_ASSISTED", "BAR_ONLY"],
            available_machine_assistance_kg=[10.0, 15.0, 20.0, 25.0, 30.0],
        )
        eq = get_current_equipment(tmp_path, "pull_up")
        assert eq is not None
        assert eq["available_machine_assistance_kg"] == [10.0, 15.0, 20.0, 25.0, 30.0]
        assert isinstance(eq["recommended_assistance_kg"], float)
        assert "machine_assistance_kg" not in eq

    def test_get_current_equipment_recommended_assistance_is_from_list(self, tmp_path):
        _init(tmp_path)
        update_equipment(
            tmp_path,
            "pull_up",
            available_items=["MACHINE_ASSISTED", "BAR_ONLY"],
            available_machine_assistance_kg=[10.0, 20.0, 30.0],
        )
        eq = get_current_equipment(tmp_path, "pull_up")
        assert eq["recommended_assistance_kg"] in [10.0, 20.0, 30.0]

    def test_log_session_snapshot_captures_prescribed_assistance(self, tmp_path):
        _init(tmp_path)
        update_equipment(
            tmp_path,
            "pull_up",
            available_items=["MACHINE_ASSISTED", "BAR_ONLY"],
            available_machine_assistance_kg=[10.0, 20.0, 30.0],
        )
        result = log_session(tmp_path, "pull_up", _test_session())
        snap = result["equipment_snapshot"]
        assert snap is not None
        assert snap["active_item"] == "MACHINE_ASSISTED"
        assert snap["assistance_kg"] in [10.0, 20.0, 30.0]

    def test_plan_includes_prescribed_assistance_kg_below_threshold(self, tmp_path):
        _init(tmp_path)
        update_equipment(
            tmp_path,
            "pull_up",
            available_items=["MACHINE_ASSISTED", "BAR_ONLY"],
            available_machine_assistance_kg=[10.0, 20.0, 30.0],
        )
        # Log a TEST session at low reps to keep TM below weight threshold (9)
        log_session(
            tmp_path,
            "pull_up",
            SessionInput(
                date=_today(),
                session_type="TEST",
                bodyweight_kg=80.0,
                grip="pronated",
                sets=[SetInput(reps=5, rest_seconds=180)],
            ),
        )
        plan = get_plan(tmp_path, "pull_up")
        future = [s for s in plan["sessions"] if s["status"] in ("next", "planned")]
        assert len(future) > 0
        # All future sessions should have prescribed_assistance_kg from the list or 0
        for s in future:
            val = s.get("prescribed_assistance_kg")
            assert val is None or val in [0.0, 10.0, 20.0, 30.0]
        # At least one session should have assistance > 0 (TM is below weight threshold)
        assisted = [s for s in future if (s.get("prescribed_assistance_kg") or 0) > 0]
        assert len(assisted) > 0

    def test_machine_assistance_inherits_from_previous_entry(self, tmp_path):
        _init(tmp_path)
        update_equipment(
            tmp_path,
            "pull_up",
            available_items=["MACHINE_ASSISTED", "BAR_ONLY"],
            available_machine_assistance_kg=[10.0, 20.0, 30.0],
        )
        # Update equipment without specifying available_machine_assistance_kg -> inherits
        update_equipment(
            tmp_path,
            "pull_up",
            available_items=["MACHINE_ASSISTED", "BAR_ONLY", "WEIGHT_BELT"],
        )
        eq = get_current_equipment(tmp_path, "pull_up")
        assert eq["available_machine_assistance_kg"] == [10.0, 20.0, 30.0]

    def test_machine_assistance_cleared_with_empty_list(self, tmp_path):
        _init(tmp_path)
        update_equipment(
            tmp_path,
            "pull_up",
            available_items=["MACHINE_ASSISTED", "BAR_ONLY"],
            available_machine_assistance_kg=[10.0, 20.0, 30.0],
        )
        update_equipment(
            tmp_path,
            "pull_up",
            available_items=["BAR_ONLY"],
            available_machine_assistance_kg=[],
        )
        eq = get_current_equipment(tmp_path, "pull_up")
        assert eq["available_machine_assistance_kg"] == []


# ---------------------------------------------------------------------------
# TestExerciseInfoExtended
# ---------------------------------------------------------------------------


class TestExerciseInfoExtended:
    def test_session_params_in_info(self):
        info = get_exercise_info("pull_up")
        assert "session_params" in info
        assert "S" in info["session_params"]
        assert info["session_params"]["S"]["reps_min"] == 4



# ---------------------------------------------------------------------------
# TestParseSets
# ---------------------------------------------------------------------------


class TestParseSets:
    def test_parse_sets_string_basic(self):
        result = parse_sets_string("8")
        assert len(result) == 1
        reps, weight, rest = result[0]
        assert reps == 8

    def test_parse_sets_string_compact(self):
        # "3×5" = 5 sets of 3 reps (sets×reps format)
        result = parse_sets_string("3×5/120s")
        assert len(result) == 5
        assert all(r == 3 for r, _, _ in result)

    def test_parse_compact_sets_returns_none_for_bare_int(self):
        assert parse_compact_sets("8") is None

    def test_parse_compact_sets_recognises_compact(self):
        result = parse_compact_sets("3×5/120s")
        assert result is not None
        assert len(result) == 5


# ---------------------------------------------------------------------------
# Regression tests — new behaviour added in this cleanup
# ---------------------------------------------------------------------------


class TestProfileCleanup:
    def test_days_for_exercise_raises_for_unregistered_exercise(self, tmp_path):
        """days_for_exercise raises KeyError when exercise not in exercise_days."""
        from bar_scheduler.core.models import UserProfile

        profile = UserProfile(
            height_cm=175, bodyweight_kg=80.0, exercise_days={"pull_up": 3}
        )
        with pytest.raises(KeyError):
            profile.days_for_exercise("dip")


class TestEquipmentAutoSelection:
    def test_recommend_weight_belt_above_threshold(self):
        """WEIGHT_BELT is preferred when TM > weight_tm_threshold."""
        from bar_scheduler.core.equipment import recommend_equipment_item
        from bar_scheduler.core.exercises.registry import get_exercise

        exercise = get_exercise("pull_up")  # threshold=9
        result = recommend_equipment_item(["BAR_ONLY", "WEIGHT_BELT"], exercise, 10, [])
        assert result == "WEIGHT_BELT"

    def test_recommend_bar_only_below_threshold(self):
        """BAR_ONLY returned when TM <= weight_tm_threshold."""
        from bar_scheduler.core.equipment import recommend_equipment_item
        from bar_scheduler.core.exercises.registry import get_exercise

        exercise = get_exercise("pull_up")  # threshold=9
        result = recommend_equipment_item(["BAR_ONLY", "WEIGHT_BELT"], exercise, 9, [])
        assert result == "BAR_ONLY"

    def test_recommend_band_step_down_when_ready(self):
        """Steps down from BAND_SET to BAR_ONLY after 2 ceiling sessions."""
        from bar_scheduler.core.equipment import recommend_equipment_item
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.models import (
            EquipmentSnapshot,
            SessionResult,
            SetResult,
        )

        exercise = get_exercise("pull_up")
        snap = EquipmentSnapshot(active_item="BAND_SET", assistance_kg=20.0)
        # S session hitting reps_max=6
        s1 = SessionResult(
            date="2026-01-01",
            bodyweight_kg=80.0,
            grip="pronated",
            session_type="S",
            exercise_id="pull_up",
            completed_sets=[SetResult(6, 6, 180)],
            equipment_snapshot=snap,
        )
        # H session hitting reps_max=12
        s2 = SessionResult(
            date="2026-01-08",
            bodyweight_kg=80.0,
            grip="pronated",
            session_type="H",
            exercise_id="pull_up",
            completed_sets=[SetResult(12, 12, 150)],
            equipment_snapshot=snap,
        )
        result = recommend_equipment_item(
            ["BAND_SET", "BAR_ONLY"], exercise, 5, [s1, s2]
        )
        assert result == "BAR_ONLY"


class TestWeightPrescriptionEpley:
    def test_weight_prescription_from_leff_1rm_s_session(self):
        """
        BW TEST at 20 reps, BW=81.7 kg, dip exercise -> S prescription = 21.5 kg.

        Leff 1RM from TEST: 75.164 * (1 + 20/30) = 125.273
        leff_target for S (5 reps): 125.273 * 0.9 / (1 + 5/30) = 96.64
        added = 96.64 - 75.164 = 21.47 -> rounded to 21.5
        """
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.models import SessionResult, SetResult
        from bar_scheduler.core.planner.load_calculator import _calculate_added_weight

        exercise = get_exercise("dip")
        bw = 81.7
        test_session = SessionResult(
            date="2026-01-01",
            bodyweight_kg=bw,
            grip="standard",
            session_type="TEST",
            exercise_id="dip",
            completed_sets=[SetResult(20, 20, 180)],
        )
        result = _calculate_added_weight(exercise, 18, bw, [test_session], "S")
        assert result == 21.5

    def test_weight_prescription_from_leff_1rm_h_session(self):
        """
        Same input, H session (target_reps=8) gives lower Leff target -> smaller added weight.

        leff_target for H (8 reps): 125.273 * 0.9 / (1 + 8/30) = 89.0
        added = 89.0 - 75.164 = 13.84 -> rounded to 14.0
        """
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.models import SessionResult, SetResult
        from bar_scheduler.core.planner.load_calculator import _calculate_added_weight

        exercise = get_exercise("dip")
        bw = 81.7
        test_session = SessionResult(
            date="2026-01-01",
            bodyweight_kg=bw,
            grip="standard",
            session_type="TEST",
            exercise_id="dip",
            completed_sets=[SetResult(20, 20, 180)],
        )
        result = _calculate_added_weight(exercise, 18, bw, [test_session], "H")
        assert result == 14.0

    def test_weight_prescription_no_history_conservative_fallback(self):
        """No history -> positive float from conservative estimate, not zero."""
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.planner.load_calculator import _calculate_added_weight

        exercise = get_exercise("pull_up")
        result = _calculate_added_weight(exercise, 10, 80.0, [], "S")
        assert result > 0.0
        assert result == 4.5  # conservative fallback value

    def test_weight_at_threshold_is_zero(self, tmp_path):
        """TM <= threshold -> added weight = 0."""
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.planner.load_calculator import _calculate_added_weight

        exercise = get_exercise("pull_up")  # threshold=9
        assert _calculate_added_weight(exercise, 9, 80.0, [], "S") == 0.0
        assert _calculate_added_weight(exercise, 8, 80.0, [], "H") == 0.0


# ---------------------------------------------------------------------------
# Equipment catalog loaded from YAML (not hardcoded Python constants)
# ---------------------------------------------------------------------------


class TestEquipmentFromYaml:
    """Verify that equipment catalogs are read from per-exercise YAML files."""

    def test_get_catalog_pull_up_has_bar_only(self):
        from bar_scheduler.core.equipment import get_catalog

        catalog = get_catalog("pull_up")
        assert "BAR_ONLY" in catalog
        assert catalog["BAR_ONLY"]["assistance_kg"] == 0.0

    def test_get_catalog_pull_up_has_band_set(self):
        from bar_scheduler.core.equipment import get_catalog

        catalog = get_catalog("pull_up")
        assert "BAND_SET" in catalog
        assert catalog["BAND_SET"]["assistance_kg"] is None
        assert catalog["BAND_SET"]["requires_weight_declaration"] is True

    def test_get_catalog_pull_up_machine_assisted_none(self):
        """MACHINE_ASSISTED has assistance_kg=None (user-entered)."""
        from bar_scheduler.core.equipment import get_catalog

        catalog = get_catalog("pull_up")
        assert "MACHINE_ASSISTED" in catalog
        assert catalog["MACHINE_ASSISTED"]["assistance_kg"] is None
        assert catalog["MACHINE_ASSISTED"]["requires_weight_declaration"] is True

    def test_get_catalog_dip_has_parallel_bars(self):
        from bar_scheduler.core.equipment import get_catalog

        catalog = get_catalog("dip")
        assert "PARALLEL_BARS" in catalog
        assert catalog["PARALLEL_BARS"]["assistance_kg"] == 0.0

    def test_get_catalog_unknown_exercise_returns_empty(self):
        from bar_scheduler.core.equipment import get_catalog

        assert get_catalog("unknown_exercise") == {}

    def test_assist_progression_pull_up_from_yaml(self):
        """assist_progression is loaded from YAML, not a hardcoded Python constant."""
        from bar_scheduler.core.exercises.registry import get_exercise

        ex = get_exercise("pull_up")
        ap = ex.assist_progression
        assert ap[0] == "BAND_SET"
        assert ap[-1] == "BAR_ONLY"

    def test_assist_progression_bss_is_empty(self):
        """BSS has no assist_progression (no fixed-assistance equipment)."""
        from bar_scheduler.core.exercises.registry import get_exercise

        ex = get_exercise("bss")
        assert ex.assist_progression == []

    def test_get_assist_progression_api(self):
        ap = get_assist_progression("pull_up")
        assert "BAND_SET" in ap
        assert "BAR_ONLY" in ap
        assert ap.index("BAND_SET") < ap.index("BAR_ONLY")

    def test_get_assist_progression_unknown_returns_empty(self):
        assert get_assist_progression("unknown_exercise") == []

    def test_get_equipment_catalog_shape(self):
        """get_equipment_catalog returns default_item, assist_progression, items."""
        from bar_scheduler.api import get_equipment_catalog

        cat = get_equipment_catalog("pull_up")
        assert cat["default_item"] == "BAR_ONLY"
        assert cat["assist_progression"] == ["BAND_SET", "BAR_ONLY"]
        assert "BAR_ONLY" in cat["items"]
        assert "BAND_SET" in cat["items"]
        assert cat["items"]["BAR_ONLY"]["requires_weight_declaration"] is False
        assert cat["items"]["BAND_SET"]["requires_weight_declaration"] is True
        assert cat["items"]["BAND_SET"]["assistance_kg"] is None

    def test_get_equipment_catalog_unknown_returns_empty(self):
        from bar_scheduler.api import get_equipment_catalog

        cat = get_equipment_catalog("unknown_exercise")
        assert cat == {"default_item": "", "assist_progression": [], "items": {}}

    def test_get_exercise_info_has_default_item(self):
        info = get_exercise_info("pull_up")
        assert info["default_item"] == "BAR_ONLY"

    def test_default_item_dip(self):
        info = get_exercise_info("dip")
        assert info["default_item"] == "PARALLEL_BARS"

    def test_default_item_incline_db_press(self):
        info = get_exercise_info("incline_db_press")
        assert info["default_item"] == "DUMBBELLS"

    def test_update_equipment_band_assistance_kg(self, tmp_path):
        _init(tmp_path)
        update_equipment(
            tmp_path, "pull_up",
            available_items=["BAND_SET", "BAR_ONLY"],
            available_band_assistance_kg=[10.0, 20.0, 30.0],
        )
        eq = get_current_equipment(tmp_path, "pull_up")
        assert eq["available_band_assistance_kg"] == [10.0, 20.0, 30.0]

    def test_get_current_equipment_band_set_recommended_assistance(self, tmp_path):
        """BAND_SET recommended_assistance_kg is computed when user has declared bands."""
        _init(tmp_path)
        update_equipment(
            tmp_path, "pull_up",
            available_items=["BAND_SET", "BAR_ONLY"],
            available_band_assistance_kg=[10.0, 20.0, 30.0],
        )
        eq = get_current_equipment(tmp_path, "pull_up")
        assert eq["recommended_item"] == "BAND_SET"
        assert eq["recommended_assistance_kg"] >= 0.0


# ---------------------------------------------------------------------------
# TestGetGoalMetrics
# ---------------------------------------------------------------------------


class TestGetGoalMetrics:
    """get_goal_metrics public API."""

    def test_no_goal_returns_none_fields(self, tmp_path):
        from bar_scheduler.api import get_goal_metrics

        _init(tmp_path)
        log_session(tmp_path, "pull_up", _test_session())
        result = get_goal_metrics(tmp_path, "pull_up")
        assert result["goal_reps"] is None
        assert result["goal_weight_kg"] is None
        assert result["goal_leff"] is None
        assert result["estimated_1rm"] is None
        assert result["volume_set"] is None

    def test_bodyweight_goal_returns_correct_volume(self, tmp_path):
        from bar_scheduler.api import get_goal_metrics, set_exercise_target

        _init(tmp_path, bodyweight_kg=80.0)
        set_exercise_target(tmp_path, "pull_up", reps=10)
        result = get_goal_metrics(tmp_path, "pull_up")
        assert result["goal_reps"] == 10
        assert result["goal_weight_kg"] == 0.0
        # pull_up bw_fraction=1.0, BW=80 -> goal_leff=80.0
        assert result["goal_leff"] == pytest.approx(80.0, abs=0.01)
        # volume_set = 80 × 10 = 800
        assert result["volume_set"] == pytest.approx(800.0, abs=0.01)
        # estimated_1rm must be a float > goal_leff for 10 reps
        assert isinstance(result["estimated_1rm"], float)
        assert result["estimated_1rm"] > 80.0

    def test_weighted_goal_uses_added_weight(self, tmp_path):
        from bar_scheduler.api import get_goal_metrics, set_exercise_target

        _init(tmp_path, bodyweight_kg=80.0)
        set_exercise_target(tmp_path, "pull_up", reps=5, weight_kg=20.0)
        result = get_goal_metrics(tmp_path, "pull_up")
        # goal_leff = 1.0×80 + 20 = 100
        assert result["goal_leff"] == pytest.approx(100.0, abs=0.01)
        assert result["volume_set"] == pytest.approx(500.0, abs=0.01)  # 100 × 5

    def test_requires_exercise_id(self):
        import inspect
        from bar_scheduler.api import get_goal_metrics

        sig = inspect.signature(get_goal_metrics)
        assert sig.parameters["exercise_id"].default is inspect.Parameter.empty


# ---------------------------------------------------------------------------
# TestSessionMetricsCached
# ---------------------------------------------------------------------------


class TestSessionMetricsCached:
    """session_metrics are computed and cached at log_session time."""

    def test_volume_session_equals_leff_times_reps(self, tmp_path):
        # BW=80, bw_fraction=1.0 -> leff=80, 1 set of 8 reps -> volume = 640
        _init(tmp_path, bodyweight_kg=80.0)
        log_session(
            tmp_path,
            "pull_up",
            SessionInput(
                date=_today(),
                session_type="S",
                bodyweight_kg=80.0,
                grip="pronated",
                sets=[SetInput(reps=8, rest_seconds=180)],
            ),
        )
        history = get_history(tmp_path, "pull_up")
        m = history[0]["session_metrics"]
        assert m["volume_session"] == pytest.approx(640.0, abs=0.01)
        assert m["avg_volume_set"] == pytest.approx(640.0, abs=0.01)

    def test_avg_volume_set_divides_by_n_sets(self, tmp_path):
        # 2 sets of 8 reps at BW=80 -> volume=1280, avg=640
        _init(tmp_path, bodyweight_kg=80.0)
        log_session(
            tmp_path,
            "pull_up",
            SessionInput(
                date=_today(),
                session_type="S",
                bodyweight_kg=80.0,
                grip="pronated",
                sets=[
                    SetInput(reps=8, rest_seconds=180),
                    SetInput(reps=8, rest_seconds=180),
                ],
            ),
        )
        history = get_history(tmp_path, "pull_up")
        m = history[0]["session_metrics"]
        assert m["volume_session"] == pytest.approx(1280.0, abs=0.01)
        assert m["avg_volume_set"] == pytest.approx(640.0, abs=0.01)

    def test_get_history_old_record_returns_none_metrics(self, tmp_path):
        """Records without session_metrics field return None for all metric fields."""
        import json

        _init(tmp_path, bodyweight_kg=80.0)
        from bar_scheduler.io.user_store import UserStore

        store = UserStore(tmp_path)
        # Write a bare JSONL record with no session_metrics
        raw = {
            "date": _today(),
            "bodyweight_kg": 80.0,
            "grip": "pronated",
            "session_type": "S",
            "exercise_id": "pull_up",
            "completed_sets": [{"actual_reps": 5, "rest_seconds_before": 180}],
        }
        with open(store.history_path("pull_up"), "w") as f:
            f.write(json.dumps(raw) + "\n")
        history = get_history(tmp_path, "pull_up")
        m = history[0]["session_metrics"]
        assert m["volume_session"] is None
        assert m["avg_volume_set"] is None
        assert m["estimated_1rm"] is None


# ---------------------------------------------------------------------------
# TestLogSessionTyped
# ---------------------------------------------------------------------------


class TestLogSessionTyped:
    """Regression: log_session accepts SessionInput / SetInput."""

    def test_session_input_round_trips(self, tmp_path):
        _init(tmp_path, bodyweight_kg=80.0)
        si = SessionInput(
            date=_today(),
            session_type="S",
            bodyweight_kg=80.0,
            grip="pronated",
            sets=[
                SetInput(reps=5, rest_seconds=180),
                SetInput(reps=4, rest_seconds=180, added_weight_kg=5.0, rir_reported=1),
            ],
        )
        result = log_session(tmp_path, "pull_up", si)
        assert result["date"] == _today()
        assert result["session_type"] == "S"
        assert len(result["completed_sets"]) == 2
        assert result["completed_sets"][1]["added_weight_kg"] == 5.0
        assert result["completed_sets"][1]["rir_reported"] == 1
        assert result["session_metrics"]["volume_session"] is not None

    def test_log_session_updates_profile_bodyweight(self, tmp_path):
        _init(tmp_path, bodyweight_kg=81.7)
        si = SessionInput(
            date=_today(),
            session_type="S",
            bodyweight_kg=83.0,
            sets=[SetInput(reps=10, rest_seconds=0)],
        )
        log_session(tmp_path, "pull_up", si)
        assert get_profile(tmp_path)["current_bodyweight_kg"] == 83.0


class TestPlanCacheCompat:
    def test_legacy_list_cache_is_ignored(self, tmp_path):
        """Old *_plan_cache.json files stored a raw list; load_plan_result_cache must
        return None rather than crashing with AttributeError."""
        import json
        from bar_scheduler.io.user_store import UserStore

        store = UserStore(tmp_path)
        path = tmp_path / "pull_up_plan_cache.json"
        path.write_text(json.dumps([{"date": "2025-01-01"}]))
        assert store.load_plan_result_cache("pull_up") is None
