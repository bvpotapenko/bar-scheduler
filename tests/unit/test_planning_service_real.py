"""Integration tests for PlanningService with the real DI container."""

from datetime import datetime

import pytest

from bar_scheduler.containers import Container
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.domain.context import EquipmentConstraints, PlanRequest
from bar_scheduler.domain.models import UserProfile, UserState


@pytest.fixture
def request_new_user() -> PlanRequest:
    profile = UserProfile(
        height_cm=180,
        bodyweight_kg=80.0,
        exercise_days={"pull_up": 3},
        exercises_enabled=["pull_up"],
    )
    return PlanRequest(
        user_state=UserState(profile=profile, history=[]),
        start_date="2026-01-05",
        exercise=get_exercise("pull_up"),
        weeks_ahead=4,
        baseline_max=15,
        equipment=EquipmentConstraints(),
    )


def test_real_plan_starts_at_baseline_tm_and_grows(request_new_user):
    plans = Container().planning_service().generate(request_new_user)
    assert plans, "expected a non-empty plan"
    assert all(plan.exercise_id == "pull_up" for plan in plans)
    assert plans[0].expected_tm == 13  # floor(0.9 * 15)
    assert plans[-1].expected_tm >= plans[0].expected_tm  # TM never regresses
    assert plans[0].week_number == 1


def test_real_plan_is_deterministic(request_new_user):
    first = Container().planning_service().generate(request_new_user)
    second = Container().planning_service().generate(request_new_user)
    signature = [(plan.date, plan.session_type, plan.expected_tm) for plan in first]
    assert signature == [(plan.date, plan.session_type, plan.expected_tm) for plan in second]


def test_real_plan_spaces_test_sessions(request_new_user):
    plans = Container().planning_service().generate(request_new_user)
    test_dates = [
        datetime.strptime(plan.date, "%Y-%m-%d") for plan in plans if plan.session_type == "TEST"
    ]
    for earlier, later in zip(test_dates, test_dates[1:]):
        assert (later - earlier).days >= 2  # TEST spacing invariant
