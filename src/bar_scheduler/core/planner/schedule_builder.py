"""Schedule construction: weekly templates, rotation, and session date calculation."""

from datetime import datetime, timedelta

from ..config import (
    SCHEDULE_1_DAYS,
    SCHEDULE_2_DAYS,
    SCHEDULE_3_DAYS,
    SCHEDULE_4_DAYS,
    SCHEDULE_5_DAYS,
)
from ..models import SessionResult


def get_schedule_template(days_per_week: int) -> list[str]:
    """
    Get the weekly session type schedule.

    Args:
        days_per_week: 1–5 days per week

    Returns:
        List of session types for the week
    """
    if days_per_week == 1:
        return SCHEDULE_1_DAYS.copy()
    if days_per_week == 2:
        return SCHEDULE_2_DAYS.copy()
    if days_per_week == 4:
        return SCHEDULE_4_DAYS.copy()
    if days_per_week == 5:
        return SCHEDULE_5_DAYS.copy()
    return SCHEDULE_3_DAYS.copy()


def get_next_session_type_index(
    history: list[SessionResult],
    schedule: list[str],
) -> int:
    """
    Return the schedule index for the next planned session.

    Looks at the last non-TEST session in history to determine where
    the rotation left off, then returns the next index in the cycle.

    TEST sessions are skipped because they are not part of the regular
    S/H/T/E rotation.

    Args:
        history: Training history (sorted chronologically)
        schedule: Session type schedule (e.g. ["S", "H", "T", "E"])

    Returns:
        Index into schedule for the first planned session
    """
    non_test = [s for s in history if s.session_type != "TEST"]
    if not non_test:
        return 0
    last_type = non_test[-1].session_type
    if last_type in schedule:
        return (schedule.index(last_type) + 1) % len(schedule)
    return 0


def calculate_session_days(
    start_date: datetime,
    days_per_week: int,
    num_weeks: int,
    start_rotation_idx: int = 0,
) -> list[tuple[datetime, str]]:
    """
    Calculate dates and session types for a training block.

    Distributes sessions throughout the week with required rest days.

    Args:
        start_date: First day of the plan
        days_per_week: 3 or 4 training days
        num_weeks: Number of weeks to plan
        start_rotation_idx: Index into the schedule to start from (for
            continuing the S/H/T/E rotation after history). Default 0.

    Returns:
        List of (date, session_type) tuples
    """
    schedule = get_schedule_template(days_per_week)
    # Rotate schedule so the plan continues the S/H/T/E cycle from history.
    if start_rotation_idx > 0:
        schedule = schedule[start_rotation_idx:] + schedule[:start_rotation_idx]
    sessions: list[tuple[datetime, str]] = []

    # Fixed day offsets within each 7-day week:
    #   1-day: Mon(0)
    #   2-day: Mon(0), Thu(3) -- evenly spaced
    #   3-day: Mon(0), Wed(2), Fri(4) -- 1 rest day between sessions
    #   4-day: Mon(0), Tue(1), Thu(3), Sat(5) -- compact with 1 rest before T
    #   5-day: Mon(0), Tue(1), Wed(2), Fri(4), Sat(5) -- midweek rest Thu
    if days_per_week == 1:
        day_offsets = [0]
    elif days_per_week == 2:
        day_offsets = [0, 3]
    elif days_per_week == 4:
        day_offsets = [0, 1, 3, 5]
    elif days_per_week == 5:
        day_offsets = [0, 1, 2, 4, 5]
    else:
        day_offsets = [0, 2, 4]

    for week in range(num_weeks):
        week_start = start_date + timedelta(days=week * 7)
        for i, session_type in enumerate(schedule):
            session_date = week_start + timedelta(days=day_offsets[i])
            sessions.append((session_date, session_type))

    return sessions
