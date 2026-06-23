"""Session and plan <-> dict conversion, plus JSONL line helpers."""

import json
from typing import Any

from bar_scheduler.domain.models import PlannedSet, SessionPlan, SessionResult
from bar_scheduler.io.serializers.equipment import (
    dict_to_equipment_snapshot,
    equipment_snapshot_to_dict,
)
from bar_scheduler.io.serializers.sets import (
    completed_set_to_dict,
    dict_to_set_result,
    planned_set_result_to_dict,
)
from bar_scheduler.io.serializers.validators import (
    ValidationError,
    validate_date,
    validate_grip,
    validate_positive,
    validate_session_type,
)


def session_result_to_dict(session: SessionResult) -> dict[str, Any]:
    """Convert a SessionResult to a compact JSON-compatible dict."""
    row: dict[str, Any] = {
        "date": session.date,
        "bodyweight_kg": session.bodyweight_kg,
        "grip": session.grip,
        "session_type": session.session_type,
        "exercise_id": session.exercise_id,
        "completed_sets": [completed_set_to_dict(sr) for sr in session.completed_sets],
        "notes": session.notes,
    }
    if session.planned_sets:
        row["planned_sets"] = [planned_set_result_to_dict(sr) for sr in session.planned_sets]
    if session.equipment_snapshot is not None:
        row["equipment_snapshot"] = equipment_snapshot_to_dict(session.equipment_snapshot)
    if session.session_metrics is not None:
        row["session_metrics"] = session.session_metrics
    return row


def dict_to_session_result(raw: dict[str, Any]) -> SessionResult:
    """Convert a dict to a SessionResult, validating required fields."""
    validate_date(raw["date"])
    validate_positive(raw.get("bodyweight_kg", 0), "bodyweight_kg")
    validate_grip(raw["grip"])
    validate_session_type(raw["session_type"])
    if "exercise_id" not in raw:
        raise ValidationError("Missing required field: exercise_id")

    eq_data = raw.get("equipment_snapshot")
    equipment_snapshot = dict_to_equipment_snapshot(eq_data) if eq_data else None

    return SessionResult(
        date=raw["date"],
        bodyweight_kg=float(raw["bodyweight_kg"]),
        grip=raw["grip"],
        session_type=raw["session_type"],
        exercise_id=raw["exercise_id"],
        equipment_snapshot=equipment_snapshot,
        planned_sets=[dict_to_set_result(sd) for sd in raw.get("planned_sets", [])],
        completed_sets=[dict_to_set_result(sd) for sd in raw.get("completed_sets", [])],
        notes=raw.get("notes"),
        session_metrics=raw.get("session_metrics"),
    )


def session_to_json_line(session: SessionResult) -> str:
    """Serialize a session to a single compact JSON line (no trailing newline)."""
    return json.dumps(session_result_to_dict(session), separators=(",", ":"))


def json_line_to_session(line: str) -> SessionResult:
    """Deserialize a single JSON line to a SessionResult."""
    try:
        raw = json.loads(line.strip())
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON: {exc}") from exc
    return dict_to_session_result(raw)


def session_plan_to_dict(plan: SessionPlan) -> dict[str, Any]:
    """Convert a SessionPlan to a JSON-compatible dict."""
    return {
        "date": plan.date,
        "grip": plan.grip,
        "session_type": plan.session_type,
        "exercise_id": plan.exercise_id,
        "sets": [
            {
                "target_reps": ps.target_reps,
                "rest_seconds_before": ps.rest_seconds_before,
                "added_weight_kg": ps.added_weight_kg,
                "rir_target": ps.rir_target,
            }
            for ps in plan.sets
        ],
        "expected_tm": plan.expected_tm,
        "week_number": plan.week_number,
        "prescribed_assistance_kg": plan.prescribed_assistance_kg,
    }


def dict_to_session_plan(raw: dict[str, Any]) -> SessionPlan:
    """Parse a SessionPlan from a dict."""
    return SessionPlan(
        date=raw["date"],
        grip=raw["grip"],
        session_type=raw["session_type"],
        exercise_id=raw["exercise_id"],
        sets=[
            PlannedSet(
                target_reps=sd["target_reps"],
                rest_seconds_before=sd["rest_seconds_before"],
                added_weight_kg=sd.get("added_weight_kg", 0.0),
                rir_target=sd.get("rir_target", 2),
            )
            for sd in raw.get("sets", [])
        ],
        expected_tm=raw.get("expected_tm", 0),
        week_number=raw.get("week_number", 1),
        prescribed_assistance_kg=raw.get("prescribed_assistance_kg"),
    )
