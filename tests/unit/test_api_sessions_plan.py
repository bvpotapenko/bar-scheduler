"""Integration tests for the session-logging and planning api flows."""

from bar_scheduler import api


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


def test_overtraining_status(data_dir):
    status = api.get_overtraining_status(data_dir, "pull_up")
    assert status["level"] == 0  # two well-spaced sessions
