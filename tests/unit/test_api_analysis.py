"""Integration tests for the analysis api flows (volume, progress, goals)."""

import pytest

from bar_scheduler import api


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
    assert metrics["goal_weight_kg"] == pytest.approx(10.0)
    assert metrics["goal_leff"] == pytest.approx(90.0)  # 80 bw + 10 added
