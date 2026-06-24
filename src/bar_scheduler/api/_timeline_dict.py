"""Serialize a TimelineEntry to a JSON-friendly dict (per-aspect extractors)."""

from __future__ import annotations

from bar_scheduler.api._common import _session_performance_metrics
from bar_scheduler.core.equipment import compute_leff
from bar_scheduler.core.exercises.base import ExerciseDefinition
from bar_scheduler.core.timeline import TimelineEntry


def _set_dict(reps: int, weight_kg: float, rest_s: int) -> dict:
    return {"reps": reps, "weight_kg": weight_kg, "rest_s": rest_s}


def _prescribed_sets(entry: TimelineEntry) -> list[dict] | None:
    """Prescribed sets: from the matched session's plan, else the planned entry."""
    if entry.actual is not None and entry.actual.planned_sets:
        sets = entry.actual.planned_sets
    elif entry.planned is not None and entry.planned.sets:
        sets = entry.planned.sets
    else:
        return None
    return [_set_dict(ps.target_reps, ps.added_weight_kg, ps.rest_seconds_before) for ps in sets]


def _actual_sets(entry: TimelineEntry) -> list[dict] | None:
    """Completed sets (reps actually performed), or None for future sessions."""
    if entry.actual is None:
        return None
    return [
        _set_dict(cs.actual_reps, cs.added_weight_kg, cs.rest_seconds_before)
        for cs in entry.actual.completed_sets
        if cs.actual_reps is not None
    ]


def _type_and_grip(entry: TimelineEntry) -> tuple[str, str]:
    if entry.actual:
        return entry.actual.session_type, entry.actual.grip
    if entry.planned:
        return entry.planned.session_type, entry.planned.grip
    return "", ""


def _session_metrics(
    entry: TimelineEntry, exercise: ExerciseDefinition | None, current_bw: float | None
) -> dict | None:
    """Cached metrics for completed sessions; computed from prescription otherwise."""
    if entry.actual is not None:
        return entry.actual.session_metrics
    if entry.planned is None or exercise is None or current_bw is None:
        return None
    leff_reps = [
        (compute_leff(exercise.bw_fraction, current_bw, ps.added_weight_kg, 0.0), ps.target_reps)
        for ps in entry.planned.sets
        if ps.target_reps > 0
    ]
    return _session_performance_metrics(leff_reps) if leff_reps else None


def _timeline_entry_to_dict(
    entry: TimelineEntry,
    exercise: ExerciseDefinition | None = None,
    current_bw: float | None = None,
) -> dict:
    """Serialise a TimelineEntry to a JSON-friendly dict."""
    plan_type, plan_grip = _type_and_grip(entry)
    return {
        "date": entry.date,
        "week": entry.week_number,
        "type": plan_type,
        "grip": plan_grip,
        "status": entry.status,
        "id": entry.actual_id,
        "expected_tm": entry.planned.expected_tm if entry.planned else None,
        "prescribed_sets": _prescribed_sets(entry),
        "actual_sets": _actual_sets(entry),
        "track_b": entry.track_b,
        "session_metrics": _session_metrics(entry, exercise, current_bw),
        "prescribed_assistance_kg": (
            entry.planned.prescribed_assistance_kg if entry.planned else None
        ),
    }
