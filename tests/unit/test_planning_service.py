"""Unit + integration tests for PlanningService.generate."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from bar_scheduler.containers import Container
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.services.plan_run import PlanRun
from bar_scheduler.core.services.planning_service import PlanningService
from bar_scheduler.domain.context import EquipmentConstraints, PlanRequest
from bar_scheduler.domain.models import UserProfile, UserState


# --- Orchestration with fakes (sequencing + weekly TM fold) ---


class _FakePrescriber:
    def __init__(self) -> None:
        self.tm_at_call: list[float] = []

    def prescribe(self, run, slot, progress):
        self.tm_at_call.append(progress.tm_float)
        return (slot[1], progress.tm_float)


class _FakeProgression:
    def weekly_delta(self, tm_float, goal, ctx) -> float:
        return 5.0


class _FakeRunFactory:
    def __init__(self, run: PlanRun) -> None:
        self._run = run

    def build(self, request) -> PlanRun:
        return self._run


def _fake_run(slots) -> PlanRun:
    return PlanRun(
        exercise=get_exercise("pull_up"),
        bodyweight_kg=80.0,
        equipment=EquipmentConstraints(),
        overtraining_level=0,
        history=[],
        effective_init=[],
        training_state=SimpleNamespace(initial_tm=13),
        goal=None,
        start=datetime(2026, 1, 5),
        slots=slots,
        first_monday=None,
        grip_selector=None,
        history_by_type={},
    )


def test_generate_calls_prescriber_once_per_slot_and_folds_tm_weekly():
    slots = [
        (datetime(2026, 1, 5), "S"),  # week 0
        (datetime(2026, 1, 7), "H"),  # week 0
        (datetime(2026, 1, 12), "S"),  # week 1 -> +5
    ]
    prescriber = _FakePrescriber()
    service = PlanningService(_FakeRunFactory(_fake_run(slots)), prescriber, _FakeProgression())

    plans = service.generate(PlanRequest(user_state=None, start_date="2026-01-05", exercise=None))

    assert plans == [("S", 13.0), ("H", 13.0), ("S", 18.0)]
    assert prescriber.tm_at_call == [13.0, 13.0, 18.0]  # delta applied once, at the week-1 slot


# --- Integration with the real container ---


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
        datetime.strptime(plan.date, "%Y-%m-%d")
        for plan in plans
        if plan.session_type == "TEST"
    ]
    for earlier, later in zip(test_dates, test_dates[1:]):
        assert (later - earlier).days >= 2  # TEST spacing invariant
