"""Unit tests for the grip and schedule policies."""

from datetime import datetime

import pytest

from bar_scheduler.config.schedule_params import ScheduleConfig
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.policies.grip import GripSelector
from bar_scheduler.core.policies.schedule import ScheduleBuilder
from bar_scheduler.core.policies.test_inserter import TestSessionInserter
from bar_scheduler.domain.models import SessionResult

MON = datetime(2026, 1, 5)  # a Monday


def _session(date: str, stype: str, grip: str = "pronated") -> SessionResult:
    return SessionResult(
        date=date, bodyweight_kg=80.0, grip=grip, session_type=stype, exercise_id="pull_up"
    )


# --- ScheduleBuilder ---


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (1, ["S"]),
        (2, ["S", "H"]),
        (3, ["S", "H", "E"]),
        (4, ["S", "H", "T", "E"]),
        (5, ["S", "H", "T", "E", "S"]),
    ],
    ids=["1d", "2d", "3d", "4d", "5d"],
)
def test_template(days, expected):
    assert ScheduleBuilder(ScheduleConfig()).template(days) == expected


def test_session_days_3day_offsets():
    builder = ScheduleBuilder(ScheduleConfig())
    days = builder.session_days(MON, days_per_week=3, num_weeks=1)
    assert days == [
        (datetime(2026, 1, 5), "S"),  # Mon
        (datetime(2026, 1, 7), "H"),  # Wed
        (datetime(2026, 1, 9), "E"),  # Fri
    ]


def test_session_days_two_weeks_count():
    days = ScheduleBuilder(ScheduleConfig()).session_days(MON, 4, num_weeks=2)
    assert len(days) == 8
    assert days[4][0] == datetime(2026, 1, 12)  # week 2 starts +7 days


def test_next_type_index_resumes_after_last_non_test():
    builder = ScheduleBuilder(ScheduleConfig())
    history = [_session("2026-01-05", "S"), _session("2026-01-07", "H")]
    assert builder.next_type_index(history, ["S", "H", "E"]) == 2  # after H -> E


def test_next_type_index_empty_history():
    assert ScheduleBuilder(ScheduleConfig()).next_type_index([], ["S", "H", "E"]) == 0


# --- TestSessionInserter ---


def test_insert_marks_due_slot_as_test():
    # No TEST history -> first slot is one full cycle past synthetic baseline -> TEST.
    inserter = TestSessionInserter(test_spacing=1)
    slots = [(datetime(2026, 1, 5), "S"), (datetime(2026, 1, 7), "H")]
    result = inserter.insert(slots, history=[], test_frequency_weeks=3, plan_start=MON)
    assert result[0][1] == "TEST"


def test_insert_enforces_spacing_after_in_plan_test():
    inserter = TestSessionInserter(test_spacing=1)
    # Two adjacent slots; first becomes TEST, the next must move to >= spacing+1 days later.
    slots = [(datetime(2026, 1, 5), "S"), (datetime(2026, 1, 6), "H")]
    result = inserter.insert(slots, history=[], test_frequency_weeks=3, plan_start=MON)
    assert result[0][1] == "TEST"
    assert (result[1][0] - result[0][0]).days >= 2  # spacing(1) + 1


# --- GripSelector ---


def test_grip_rotation_cycles_in_order():
    selector = GripSelector(get_exercise("pull_up"))
    selector.initialize_counts([])
    # pull_up S cycle is [pronated, neutral, supinated]
    assert [selector.next_grip("S") for _ in range(4)] == [
        "pronated",
        "neutral",
        "supinated",
        "pronated",
    ]


def test_grip_rotation_resumes_from_history():
    selector = GripSelector(get_exercise("pull_up"))
    selector.initialize_counts([_session("2026-01-05", "S", grip="pronated")])
    assert selector.next_grip("S") == "neutral"  # resumes after pronated


def test_grip_no_rotation_uses_primary():
    selector = GripSelector(get_exercise("dip"))  # has_variant_rotation False
    selector.initialize_counts([])
    assert selector.next_grip("S") == get_exercise("dip").primary_variant
