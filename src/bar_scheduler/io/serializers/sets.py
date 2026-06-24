"""Set <-> dict conversion (SetResult and PlannedSet)."""

from typing import Any

from bar_scheduler.domain.models import PlannedSet, SetResult
from bar_scheduler.io.serializers.validators import validate_non_negative


def set_result_to_dict(set_result: SetResult) -> dict[str, Any]:
    """Convert a SetResult to a JSON-compatible dict (full form)."""
    return {
        "target_reps": set_result.target_reps,
        "actual_reps": set_result.actual_reps,
        "rest_seconds_before": set_result.rest_seconds_before,
        "added_weight_kg": set_result.added_weight_kg,
        "rir_target": set_result.rir_target,
        "rir_reported": set_result.rir_reported,
    }


def dict_to_set_result(raw: dict[str, Any]) -> SetResult:
    """Convert a dict to a SetResult, deriving the missing reps field.

    Compact forms: ``actual_reps`` only -> completed (target = actual);
    ``target_reps`` only -> planned (actual = None). Both present -> as-is.
    """
    actual_reps = raw.get("actual_reps")
    target_reps = raw.get("target_reps")
    if actual_reps is not None and target_reps is None:
        target_reps = actual_reps

    validate_non_negative(target_reps or 0, "target_reps")
    if actual_reps is not None:
        validate_non_negative(actual_reps, "actual_reps")
    validate_non_negative(raw.get("rest_seconds_before", 0), "rest_seconds_before")
    validate_non_negative(raw.get("added_weight_kg", 0), "added_weight_kg")

    return SetResult(
        target_reps=int(target_reps or 0),
        actual_reps=None if actual_reps is None else int(actual_reps),
        rest_seconds_before=int(raw.get("rest_seconds_before", 0)),
        added_weight_kg=float(raw.get("added_weight_kg", 0.0)),
        rir_target=int(raw.get("rir_target", 2)),
        rir_reported=(None if raw.get("rir_reported") is None else int(raw["rir_reported"])),
    )


def planned_set_to_dict(planned_set: PlannedSet) -> dict[str, Any]:
    """Convert a PlannedSet to a JSON-compatible dict."""
    return {
        "target_reps": planned_set.target_reps,
        "rest_seconds_before": planned_set.rest_seconds_before,
        "added_weight_kg": planned_set.added_weight_kg,
        "rir_target": planned_set.rir_target,
    }


def dict_to_planned_set(raw: dict[str, Any]) -> PlannedSet:
    """Convert a dict to a PlannedSet."""
    validate_non_negative(raw.get("target_reps", 0), "target_reps")
    validate_non_negative(raw.get("rest_seconds_before", 0), "rest_seconds_before")
    validate_non_negative(raw.get("added_weight_kg", 0), "added_weight_kg")
    validate_non_negative(raw.get("rir_target", 0), "rir_target")

    return PlannedSet(
        target_reps=int(raw["target_reps"]),
        rest_seconds_before=int(raw["rest_seconds_before"]),
        added_weight_kg=float(raw.get("added_weight_kg", 0.0)),
        rir_target=int(raw.get("rir_target", 2)),
    )


def completed_set_to_dict(set_rec: SetResult) -> dict[str, Any]:
    """Compact serializer for a completed set (only actual_reps; target == actual)."""
    row: dict[str, Any] = {
        "actual_reps": set_rec.actual_reps,
        "rest_seconds_before": set_rec.rest_seconds_before,
        "added_weight_kg": set_rec.added_weight_kg,
    }
    if set_rec.rir_reported is not None:
        row["rir_reported"] = set_rec.rir_reported
    return row


def planned_set_result_to_dict(set_rec: SetResult) -> dict[str, Any]:
    """Compact serializer for a planned set carried in a cached result (target only)."""
    return {
        "target_reps": set_rec.target_reps,
        "rest_seconds_before": set_rec.rest_seconds_before,
        "added_weight_kg": set_rec.added_weight_kg,
    }
