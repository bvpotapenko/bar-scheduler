"""Integration tests for the public API main flows on a temp data dir.

These lock the observable behaviour of the api functions so the Stage 8
complexity refactors cannot silently change outputs.
"""

import pytest

import bar_scheduler.api as api


@pytest.fixture
def data_dir(tmp_path):
    """A profile with pull_up enabled and one TEST + one S session logged."""
    api.init_profile(tmp_path, height_cm=180, bodyweight_kg=80.0)
    api.enable_exercise(tmp_path, "pull_up", days_per_week=3)
    api.log_session(
        tmp_path,
        "pull_up",
        api.SessionInput(
            date="2026-01-04",
            session_type="TEST",
            bodyweight_kg=80.0,
            sets=[api.SetInput(reps=12, rest_seconds=180, added_weight_kg=0.0)],
        ),
    )
    api.log_session(
        tmp_path,
        "pull_up",
        api.SessionInput(
            date="2026-01-06",
            session_type="S",
            bodyweight_kg=80.0,
            sets=[
                api.SetInput(reps=5, rest_seconds=180, added_weight_kg=0.0),
                api.SetInput(reps=4, rest_seconds=180, added_weight_kg=0.0),
            ],
        ),
    )
    return tmp_path


def test_init_and_get_profile(tmp_path):
    api.init_profile(tmp_path, height_cm=175, bodyweight_kg=70.0)
    profile = api.get_profile(tmp_path)
    assert profile["height_cm"] == 175
    assert profile["current_bodyweight_kg"] == 70.0
    assert profile["exercises_enabled"] == []


def test_init_twice_raises(tmp_path):
    api.init_profile(tmp_path, height_cm=175, bodyweight_kg=70.0)
    with pytest.raises(api.ProfileAlreadyExistsError):
        api.init_profile(tmp_path, height_cm=175, bodyweight_kg=70.0)


def test_update_profile_partial(data_dir):
    updated = api.update_profile(data_dir, bodyweight_kg=82.5)
    assert updated["current_bodyweight_kg"] == 82.5
    assert updated["height_cm"] == 180  # unchanged


def test_update_profile_language_default_removes_key(data_dir):
    api.update_profile(data_dir, language="fr")
    assert api.get_profile(data_dir)["language"] == "fr"
    restored = api.update_profile(data_dir, language="en")
    assert "language" not in restored  # "en" is the omitted default


def test_update_profile_rejects_bad_values(data_dir):
    with pytest.raises(ValueError):
        api.update_profile(data_dir, height_cm=0)


def test_log_session_computes_metrics(data_dir):
    history = api.get_history(data_dir, "pull_up")
    assert len(history) == 2
    s_session = history[1]
    assert len(s_session["completed_sets"]) == 2
    assert s_session["session_metrics"]["volume_session"] > 0


def test_get_plan_starts_at_baseline_tm(data_dir):
    plan = api.get_plan(data_dir, "pull_up", weeks_ahead=4)
    assert plan["status"]["training_max"] == 10  # floor(0.9 * 12)
    future = [s for s in plan["sessions"] if s["expected_tm"]]
    tms = [s["expected_tm"] for s in future]
    assert tms == sorted(tms)  # TM never regresses across the plan


def test_get_training_status(data_dir):
    status = api.get_training_status(data_dir, "pull_up")
    assert status["training_max"] == 10
    assert status["latest_test_max"] == 12


def test_volume_data_shape(data_dir):
    vol = api.get_volume_data(data_dir, "pull_up", weeks=4)
    assert len(vol["weeks"]) == 4
    assert all("total_reps" in wk for wk in vol["weeks"])
    assert sum(wk["total_reps"] for wk in vol["weeks"]) > 0


def test_progress_data_has_test_points(data_dir):
    progress = api.get_progress_data(data_dir, "pull_up", trajectory_types="z")
    assert progress["data_points"] == [{"date": "2026-01-04", "max_reps": 12}]
    assert progress["trajectory_z"] is not None


def test_goal_metrics_none_without_target(data_dir):
    metrics = api.get_goal_metrics(data_dir, "pull_up")
    assert metrics == {
        "goal_reps": None,
        "goal_weight_kg": None,
        "goal_leff": None,
        "estimated_1rm": None,
        "volume_set": None,
    }


def test_goal_metrics_with_target(data_dir):
    api.set_exercise_target(data_dir, "pull_up", reps=20, weight_kg=10.0)
    metrics = api.get_goal_metrics(data_dir, "pull_up")
    assert metrics["goal_reps"] == 20
    assert metrics["goal_weight_kg"] == 10.0
    assert metrics["goal_leff"] == pytest.approx(90.0)  # 80 bw + 10 added


def test_equipment_roundtrip(data_dir):
    api.update_equipment(
        data_dir,
        "pull_up",
        api.EquipmentInput(
            available_items=["BAR_ONLY", "MACHINE_ASSISTED"],
            available_machine_assistance_kg=[10, 20, 30],
        ),
    )
    current = api.get_current_equipment(data_dir, "pull_up")
    assert current["available_machine_assistance_kg"] == [10, 20, 30]
    assert current["recommended_item"] in ("BAR_ONLY", "MACHINE_ASSISTED")


def test_overtraining_status(data_dir):
    status = api.get_overtraining_status(data_dir, "pull_up")
    assert status["level"] == 0  # two well-spaced sessions


def test_list_and_get_exercise_info():
    exercises = api.list_exercises()
    assert "pull_up" in exercises
    assert exercises["pull_up"]["bw_fraction"] == 1.0
    info = api.get_exercise_info("pull_up")
    assert info["id"] == "pull_up"
    assert info["bw_fraction"] == 1.0
