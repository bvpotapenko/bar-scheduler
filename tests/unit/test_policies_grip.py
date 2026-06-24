"""Unit tests for the GripSelector."""

from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.policies.grip import GripSelector
from bar_scheduler.domain.models import SessionResult


def _session(date: str, stype: str, grip: str = "pronated") -> SessionResult:
    return SessionResult(
        date=date, bodyweight_kg=80.0, grip=grip, session_type=stype, exercise_id="pull_up"
    )


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
