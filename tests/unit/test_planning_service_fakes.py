"""Unit tests for PlanningService.generate orchestration (with fake policies)."""

from datetime import datetime
from types import SimpleNamespace

from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.services.plan_run import PlanRun
from bar_scheduler.core.services.planning_service import PlanningService
from bar_scheduler.domain.context import EquipmentConstraints, PlanRequest


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
