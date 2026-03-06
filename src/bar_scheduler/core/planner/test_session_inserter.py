"""Inject periodic TEST sessions into a planned session schedule."""

from datetime import datetime, timedelta

from ..models import SessionResult


def _find_last_test(
    history: list[SessionResult],
    plan_start: datetime,
    test_frequency_weeks: int,
) -> datetime:
    """
    Return the date of the most recent TEST session, or a synthetic baseline.

    When no TEST history exists, returns a date that ensures the first
    scheduled session triggers a TEST (i.e. plan_start minus one full cycle).

    Args:
        history: Full training history
        plan_start: Plan start date
        test_frequency_weeks: TEST cycle length in weeks

    Returns:
        Effective last-test date
    """
    test_hist = [s for s in history if s.session_type == "TEST"]
    if test_hist:
        return datetime.strptime(test_hist[-1].date, "%Y-%m-%d")
    # Treat plan start as if a test was due right before (trigger at first week boundary)
    return plan_start - timedelta(days=test_frequency_weeks * 7)


def _insert_test_sessions(
    session_dates: list[tuple[datetime, str]],
    history: list[SessionResult],
    test_frequency_weeks: int,
    plan_start: datetime,
) -> list[tuple[datetime, str]]:
    """
    Insert TEST sessions at configured intervals.

    Replaces the regular session on the day a TEST becomes due.

    Args:
        session_dates: Original (date, session_type) list
        history: Training history
        test_frequency_weeks: How often to schedule a TEST
        plan_start: Plan start date (used as fallback for last_test calculation)

    Returns:
        Modified session list with TEST sessions injected
    """
    last_test = _find_last_test(history, plan_start, test_frequency_weeks)

    result: list[tuple[datetime, str]] = []
    for date, stype in session_dates:
        if (date - last_test).days >= test_frequency_weeks * 7:
            result.append((date, "TEST"))
            last_test = date
        else:
            result.append((date, stype))
    return result
