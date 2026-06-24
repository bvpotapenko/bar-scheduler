"""Unit tests for the TestSessionInserter."""

from datetime import datetime

from bar_scheduler.core.policies.test_inserter import TestSessionInserter

MON = datetime(2026, 1, 5)  # a Monday


def test_insert_marks_due_slot_as_test():
    # No TEST history -> first slot is one full cycle past synthetic baseline -> TEST.
    inserter = TestSessionInserter(test_spacing=1)
    wed = datetime(2026, 1, 7)
    slots = [(MON, "S"), (wed, "H")]
    inserted = inserter.insert(slots, history=[], test_frequency_weeks=3, plan_start=MON)
    assert inserted[0][1] == "TEST"


def test_insert_enforces_spacing_after_in_plan_test():
    inserter = TestSessionInserter(test_spacing=1)
    # Two adjacent slots; first becomes TEST, the next must move to >= spacing+1 days later.
    tue = datetime(2026, 1, 6)
    slots = [(MON, "S"), (tue, "H")]
    inserted = inserter.insert(slots, history=[], test_frequency_weeks=3, plan_start=MON)
    assert inserted[0][1] == "TEST"
    gap = inserted[1][0] - inserted[0][0]
    assert gap.days >= 2  # spacing(1) + 1
