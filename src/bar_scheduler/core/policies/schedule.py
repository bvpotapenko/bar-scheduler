"""Calendar placement of session slots across a plan."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from types import MappingProxyType

from bar_scheduler.config.schedule_params import ScheduleConfig
from bar_scheduler.domain.models import SessionResult

_Slot = tuple[datetime, str]

# Fixed day offsets within each 7-day week (ensure required rest between sessions).
_DAY_OFFSETS: Mapping[int, tuple[int, ...]] = MappingProxyType(
    {
        1: (0,),
        2: (0, 3),
        3: (0, 2, 4),
        4: (0, 2, 4, 5),
        5: (0, 1, 2, 4, 5),
    }
)


def shift(date: datetime, days: int) -> datetime:
    """Return ``date`` moved by ``days`` (shared date helper)."""
    return date + timedelta(days=days)


def _rotated(schedule: list[str], start_rotation_idx: int) -> list[str]:
    """Rotate the weekly template so the plan continues the cycle from history."""
    if start_rotation_idx <= 0:
        return schedule
    return schedule[start_rotation_idx:] + schedule[:start_rotation_idx]


def _week_slots(base: datetime, schedule: list[str], offsets: list[int]) -> list[_Slot]:
    slots: list[_Slot] = []
    for offset, stype in zip(offsets, schedule):
        date = shift(base, offset)
        slots.append((date, stype))
    return slots


class ScheduleBuilder:
    """Weekly templates, rotation continuation, and per-day slot placement."""

    def __init__(self, cfg: ScheduleConfig) -> None:
        self._templates: dict[int, list[str]] = {
            1: list(cfg.SCHEDULE_1_DAYS),
            2: list(cfg.SCHEDULE_2_DAYS),
            3: list(cfg.SCHEDULE_3_DAYS),
            4: list(cfg.SCHEDULE_4_DAYS),
            5: list(cfg.SCHEDULE_5_DAYS),
        }

    def template(self, days_per_week: int) -> list[str]:
        """Weekly session-type template for the given frequency."""
        return list(self._templates.get(days_per_week, self._templates[3]))

    def next_type_index(self, history: list[SessionResult], schedule: list[str]) -> int:
        """Schedule index for the next planned session (resumes rotation from history)."""
        non_test = [sess for sess in history if sess.session_type != "TEST"]
        if not non_test:
            return 0
        last_type = non_test[-1].session_type
        if last_type in schedule:
            return (schedule.index(last_type) + 1) % len(schedule)
        return 0

    def session_days(
        self,
        start: datetime,
        days_per_week: int,
        num_weeks: int,
        start_rotation_idx: int = 0,
    ) -> list[_Slot]:
        """(date, session_type) slots across ``num_weeks``."""
        schedule = _rotated(self.template(days_per_week), start_rotation_idx)
        offsets = _DAY_OFFSETS.get(days_per_week, _DAY_OFFSETS[3])
        days: list[_Slot] = []
        for week in range(num_weeks):
            days.extend(_week_slots(shift(start, week * 7), schedule, offsets))
        return days
