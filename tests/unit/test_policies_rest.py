"""Unit tests for the RestAdvisor."""

from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.policies.rest import RestAdvisor
from bar_scheduler.domain.models import SessionResult, SetResult


def test_rest_midpoint_when_no_history():
    advisor = RestAdvisor(drop_off_threshold=0.35, readiness_z_low=-0.5)
    # pull_up S: rest_min 180, rest_max 300 -> midpoint 240
    assert advisor.recommend("S", [], None, get_exercise("pull_up")) == 240


def test_rest_increases_near_failure():
    advisor = RestAdvisor(drop_off_threshold=0.35, readiness_z_low=-0.5)
    near_failure = SessionResult(
        date="2026-01-01",
        bodyweight_kg=80.0,
        grip="pronated",
        session_type="S",
        exercise_id="pull_up",
        completed_sets=[
            SetResult(target_reps=5, actual_reps=5, rest_seconds_before=200, rir_reported=0)
        ],
    )
    assert advisor.recommend("S", [near_failure], None, get_exercise("pull_up")) == 270  # 240 + 30
