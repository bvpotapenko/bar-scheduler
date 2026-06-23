"""Inject periodic TEST sessions into a planned session schedule."""

from datetime import datetime, timedelta

from bar_scheduler.core.config import DAY_SPACING
from bar_scheduler.core.models import SessionResult


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
    test_hist = [sess for sess in history if sess.session_type == "TEST"]
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
    historical_test = (
        last_test if any(sess.session_type == "TEST" for sess in history) else None
    )

    scheduled: list[tuple[datetime, str]] = []
    for date, stype in session_dates:
        if (date - last_test).days >= test_frequency_weeks * 7:
            scheduled.append((date, "TEST"))
            last_test = date
        else:
            scheduled.append((date, stype))

    return _enforce_test_spacing(scheduled, DAY_SPACING["TEST"], historical_test)


def _enforce_test_spacing(
    schedule: list[tuple[datetime, str]],
    spacing: int,
    last_historical_test: datetime | None = None,
) -> list[tuple[datetime, str]]:
    """
    Ensure every session is at least `spacing + 1` days after any TEST session.

    Handles two cases:
    1. Historical TEST too close to early plan sessions (pushes them forward).
    2. In-plan TEST too close to the immediately following session.

    Args:
        schedule: (date, session_type) list, possibly containing TEST entries
        spacing: Minimum rest days after a TEST (DAY_SPACING["TEST"])
        last_historical_test: Date of most recent TEST in history, or None

    Returns:
        Adjusted schedule with spacing enforced
    """
    adjusted = list(schedule)

    # Push plan sessions that follow a historical TEST too closely.
    if last_historical_test is not None:
        cutoff = last_historical_test + timedelta(days=spacing + 1)
        for slot_idx, (slot_date, stype) in enumerate(adjusted):
            if slot_date < cutoff:
                adjusted[slot_idx] = (cutoff, stype)
            else:
                break

    # Enforce spacing between in-plan TEST and the session immediately after.
    for slot_idx, (slot_date, stype) in enumerate(adjusted):
        if stype == "TEST" and slot_idx + 1 < len(adjusted):
            next_date, next_type = adjusted[slot_idx + 1]
            if (next_date - slot_date).days <= spacing:
                adjusted[slot_idx + 1] = (slot_date + timedelta(days=spacing + 1), next_type)

    return adjusted
