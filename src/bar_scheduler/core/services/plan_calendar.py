"""Calendar placement for a plan: session slots plus TEST insertion."""

from dataclasses import dataclass
from datetime import datetime

from bar_scheduler.core.policies.schedule import ScheduleBuilder, shift
from bar_scheduler.core.policies.test_inserter import TestSessionInserter
from bar_scheduler.core.services.plan_run import HistoryWindow
from bar_scheduler.domain.context import PlanRequest

_Slot = tuple[datetime, str]


@dataclass(frozen=True)
class _Calendar:
    start: datetime
    slots: list[_Slot]
    first_monday: datetime | None


class PlanCalendar:
    """Place weekly session slots, then inject and space TEST sessions."""

    def __init__(self, schedule: ScheduleBuilder, test_inserter: TestSessionInserter) -> None:
        self._schedule = schedule
        self._test_inserter = test_inserter

    def build(self, request: PlanRequest, window: HistoryWindow, weeks: int) -> _Calendar:
        """Training start, dated slots, and the week-number anchor."""
        start = self._start(request)
        slots = self._slots(request, window, start, weeks)
        return _Calendar(start=start, slots=slots, first_monday=self._first_monday(request))

    def _start(self, request: PlanRequest) -> datetime:
        start = datetime.strptime(request.start_date, "%Y-%m-%d")
        if request.overtraining_rest_days > 0:
            return shift(start, request.overtraining_rest_days)
        return start

    def _slots(
        self, request: PlanRequest, window: HistoryWindow, start: datetime, weeks: int
    ) -> list[_Slot]:
        days = request.user_state.profile.days_for_exercise(request.exercise.exercise_id)
        template = self._schedule.template(days)
        rotation = self._schedule.next_type_index(window.effective_init, template)
        placed = self._schedule.session_days(start, days, weeks, rotation)
        return self._test_inserter.insert(
            placed, window.full, request.exercise.test_frequency_weeks, start
        )

    def _first_monday(self, request: PlanRequest) -> datetime | None:
        original = [
            sess
            for sess in request.user_state.history
            if sess.exercise_id == request.exercise.exercise_id
        ]
        if not original:
            return None
        first = datetime.strptime(original[0].date, "%Y-%m-%d")
        return shift(first, -first.weekday())
