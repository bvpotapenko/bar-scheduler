"""Inject periodic TEST sessions and enforce minimum rest around them."""

from datetime import datetime

from bar_scheduler.core.policies.schedule import shift
from bar_scheduler.domain.models import SessionResult

_Slot = tuple[datetime, str]


def _find_last_test(history: list[SessionResult], plan_start: datetime, freq_weeks: int) -> datetime:
    """Most recent TEST date, or a synthetic baseline that triggers a test at week 1."""
    tests = [sess for sess in history if sess.session_type == "TEST"]
    if tests:
        return datetime.strptime(tests[-1].date, "%Y-%m-%d")
    return shift(plan_start, -freq_weeks * 7)


def _mark_tests(session_dates: list[_Slot], last_test: datetime, freq_weeks: int) -> list[_Slot]:
    """Replace each due slot with a TEST once a full cycle has elapsed."""
    marked: list[_Slot] = []
    for date, stype in session_dates:
        if (date - last_test).days >= freq_weeks * 7:
            marked.append((date, "TEST"))
            last_test = date
        else:
            marked.append((date, stype))
    return marked


def _gap_days(earlier: _Slot, later: _Slot) -> int:
    return (later[0] - earlier[0]).days


class TestSessionInserter:
    """Mark due slots as TEST, then enforce a minimum rest gap after each TEST."""

    __test__ = False  # not a pytest test class

    def __init__(self, test_spacing: int) -> None:
        self._gap = test_spacing + 1  # days a session must clear a preceding TEST by

    def insert(
        self,
        session_dates: list[_Slot],
        history: list[SessionResult],
        test_frequency_weeks: int,
        plan_start: datetime,
    ) -> list[_Slot]:
        """Mark due slots as TEST, then enforce spacing around all TEST sessions."""
        last_test = _find_last_test(history, plan_start, test_frequency_weeks)
        has_history_test = any(sess.session_type == "TEST" for sess in history)
        marked = _mark_tests(session_dates, last_test, test_frequency_weeks)
        pushed = self._push_after_historical(marked, last_test if has_history_test else None)
        return self._space_in_plan(pushed)

    def _push_after_historical(self, schedule: list[_Slot], historical: datetime | None) -> list[_Slot]:
        """Push early plan sessions that fall too soon after a historical TEST."""
        if historical is None:
            return schedule
        cutoff = shift(historical, self._gap)
        adjusted = list(schedule)
        for idx, (date, stype) in enumerate(adjusted):
            if date >= cutoff:
                break
            adjusted[idx] = (cutoff, stype)
        return adjusted

    def _space_in_plan(self, schedule: list[_Slot]) -> list[_Slot]:
        """Push the session following an in-plan TEST that is too close to it."""
        adjusted = list(schedule)
        for idx in range(len(adjusted) - 1):
            current = adjusted[idx]
            following = adjusted[idx + 1]
            if current[1] == "TEST" and _gap_days(current, following) < self._gap:
                new_date = shift(current[0], self._gap)
                adjusted[idx + 1] = (new_date, following[1])
        return adjusted
