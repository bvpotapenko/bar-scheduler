"""
JSON serialization for training data models.

Handles conversion between dataclasses and JSON-compatible dicts.
"""

import json
import re
from datetime import datetime
from typing import Any

from ..core.models import (
    Grip,
    PlannedSet,
    SessionResult,
    SessionType,
    SetResult,
    UserProfile,
    UserState,
)


class ValidationError(Exception):
    """Raised when data validation fails."""

    pass


def validate_date(date_str: str) -> str:
    """
    Validate and normalize date string to ISO format.

    Args:
        date_str: Date string to validate

    Returns:
        Normalized YYYY-MM-DD string

    Raises:
        ValidationError: If date format is invalid
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        raise ValidationError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValidationError(f"Invalid date: {date_str}") from e

    return date_str


def validate_grip(grip: str) -> Grip:
    """
    Validate grip type.

    Args:
        grip: Grip string to validate

    Returns:
        Validated grip

    Raises:
        ValidationError: If grip is invalid
    """
    valid_grips = ("pronated", "supinated", "neutral")
    if grip not in valid_grips:
        raise ValidationError(f"Invalid grip: {grip}. Must be one of {valid_grips}")
    return grip  # type: ignore


def validate_session_type(session_type: str) -> SessionType:
    """
    Validate session type.

    Args:
        session_type: Session type string to validate

    Returns:
        Validated session type

    Raises:
        ValidationError: If session type is invalid
    """
    valid_types = ("S", "H", "E", "T", "TEST")
    if session_type not in valid_types:
        raise ValidationError(
            f"Invalid session_type: {session_type}. Must be one of {valid_types}"
        )
    return session_type  # type: ignore


def validate_non_negative(value: int | float, name: str) -> int | float:
    """
    Validate that a value is non-negative.

    Args:
        value: Value to validate
        name: Name for error message

    Returns:
        The value if valid

    Raises:
        ValidationError: If value is negative
    """
    if value < 0:
        raise ValidationError(f"{name} must be non-negative, got {value}")
    return value


def validate_positive(value: int | float, name: str) -> int | float:
    """
    Validate that a value is positive.

    Args:
        value: Value to validate
        name: Name for error message

    Returns:
        The value if valid

    Raises:
        ValidationError: If value is not positive
    """
    if value <= 0:
        raise ValidationError(f"{name} must be positive, got {value}")
    return value


def set_result_to_dict(set_result: SetResult) -> dict[str, Any]:
    """
    Convert SetResult to JSON-compatible dict.

    Args:
        set_result: SetResult to convert

    Returns:
        Dict representation
    """
    return {
        "target_reps": set_result.target_reps,
        "actual_reps": set_result.actual_reps,
        "rest_seconds_before": set_result.rest_seconds_before,
        "added_weight_kg": set_result.added_weight_kg,
        "rir_target": set_result.rir_target,
        "rir_reported": set_result.rir_reported,
    }


def dict_to_set_result(data: dict[str, Any]) -> SetResult:
    """
    Convert dict to SetResult.

    Args:
        data: Dict representation

    Returns:
        SetResult instance

    Raises:
        ValidationError: If data is invalid
    """
    validate_non_negative(data.get("target_reps", 0), "target_reps")
    if data.get("actual_reps") is not None:
        validate_non_negative(data["actual_reps"], "actual_reps")
    validate_non_negative(data.get("rest_seconds_before", 0), "rest_seconds_before")
    validate_non_negative(data.get("added_weight_kg", 0), "added_weight_kg")
    validate_non_negative(data.get("rir_target", 0), "rir_target")
    if data.get("rir_reported") is not None:
        validate_non_negative(data["rir_reported"], "rir_reported")

    return SetResult(
        target_reps=int(data["target_reps"]),
        actual_reps=int(data["actual_reps"]) if data.get("actual_reps") is not None else None,
        rest_seconds_before=int(data["rest_seconds_before"]),
        added_weight_kg=float(data.get("added_weight_kg", 0.0)),
        rir_target=int(data.get("rir_target", 2)),
        rir_reported=int(data["rir_reported"]) if data.get("rir_reported") is not None else None,
    )


def planned_set_to_dict(planned_set: PlannedSet) -> dict[str, Any]:
    """
    Convert PlannedSet to JSON-compatible dict.

    Args:
        planned_set: PlannedSet to convert

    Returns:
        Dict representation
    """
    return {
        "target_reps": planned_set.target_reps,
        "rest_seconds_before": planned_set.rest_seconds_before,
        "added_weight_kg": planned_set.added_weight_kg,
        "rir_target": planned_set.rir_target,
    }


def dict_to_planned_set(data: dict[str, Any]) -> PlannedSet:
    """
    Convert dict to PlannedSet.

    Args:
        data: Dict representation

    Returns:
        PlannedSet instance

    Raises:
        ValidationError: If data is invalid
    """
    validate_non_negative(data.get("target_reps", 0), "target_reps")
    validate_non_negative(data.get("rest_seconds_before", 0), "rest_seconds_before")
    validate_non_negative(data.get("added_weight_kg", 0), "added_weight_kg")
    validate_non_negative(data.get("rir_target", 0), "rir_target")

    return PlannedSet(
        target_reps=int(data["target_reps"]),
        rest_seconds_before=int(data["rest_seconds_before"]),
        added_weight_kg=float(data.get("added_weight_kg", 0.0)),
        rir_target=int(data.get("rir_target", 2)),
    )


def session_result_to_dict(session: SessionResult) -> dict[str, Any]:
    """
    Convert SessionResult to JSON-compatible dict.

    Args:
        session: SessionResult to convert

    Returns:
        Dict representation
    """
    return {
        "date": session.date,
        "bodyweight_kg": session.bodyweight_kg,
        "grip": session.grip,
        "session_type": session.session_type,
        "planned_sets": [set_result_to_dict(s) for s in session.planned_sets],
        "completed_sets": [set_result_to_dict(s) for s in session.completed_sets],
        "notes": session.notes,
    }


def dict_to_session_result(data: dict[str, Any]) -> SessionResult:
    """
    Convert dict to SessionResult.

    Args:
        data: Dict representation

    Returns:
        SessionResult instance

    Raises:
        ValidationError: If data is invalid
    """
    validate_date(data["date"])
    validate_positive(data.get("bodyweight_kg", 0), "bodyweight_kg")
    validate_grip(data["grip"])
    validate_session_type(data["session_type"])

    return SessionResult(
        date=data["date"],
        bodyweight_kg=float(data["bodyweight_kg"]),
        grip=data["grip"],
        session_type=data["session_type"],
        planned_sets=[dict_to_set_result(s) for s in data.get("planned_sets", [])],
        completed_sets=[dict_to_set_result(s) for s in data.get("completed_sets", [])],
        notes=data.get("notes"),
    )


def user_profile_to_dict(profile: UserProfile) -> dict[str, Any]:
    """
    Convert UserProfile to JSON-compatible dict.

    Args:
        profile: UserProfile to convert

    Returns:
        Dict representation
    """
    return {
        "height_cm": profile.height_cm,
        "sex": profile.sex,
        "preferred_days_per_week": profile.preferred_days_per_week,
        "target_max_reps": profile.target_max_reps,
    }


def dict_to_user_profile(data: dict[str, Any]) -> UserProfile:
    """
    Convert dict to UserProfile.

    Args:
        data: Dict representation

    Returns:
        UserProfile instance

    Raises:
        ValidationError: If data is invalid
    """
    validate_positive(data.get("height_cm", 0), "height_cm")

    if data.get("sex") not in ("male", "female"):
        raise ValidationError(f"Invalid sex: {data.get('sex')}. Must be 'male' or 'female'")

    if data.get("preferred_days_per_week") not in (3, 4):
        raise ValidationError(
            f"Invalid preferred_days_per_week: {data.get('preferred_days_per_week')}. Must be 3 or 4"
        )

    validate_positive(data.get("target_max_reps", 30), "target_max_reps")

    return UserProfile(
        height_cm=int(data["height_cm"]),
        sex=data["sex"],
        preferred_days_per_week=int(data.get("preferred_days_per_week", 3)),
        target_max_reps=int(data.get("target_max_reps", 30)),
    )


def session_to_json_line(session: SessionResult) -> str:
    """
    Serialize a session to a single JSON line.

    Args:
        session: SessionResult to serialize

    Returns:
        JSON string (single line, no trailing newline)
    """
    data = session_result_to_dict(session)
    return json.dumps(data, separators=(",", ":"))


def json_line_to_session(line: str) -> SessionResult:
    """
    Deserialize a JSON line to a SessionResult.

    Args:
        line: JSON string (single line)

    Returns:
        SessionResult instance

    Raises:
        ValidationError: If JSON is invalid or data validation fails
    """
    try:
        data = json.loads(line.strip())
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON: {e}") from e

    return dict_to_session_result(data)


def parse_sets_string(sets_str: str) -> list[tuple[int, float, int]]:
    """
    Parse a sets string in format: reps@+kg/rest,reps@+kg/rest,...

    Rest can be omitted for the last set (defaults to 0).

    Examples:
        "8@0/180,6@0/120,6@0/120,5@0/120"
        "6@0/60,5@0/60,6@0"  # last set without rest

    Args:
        sets_str: Sets string to parse

    Returns:
        List of (reps, added_weight_kg, rest_seconds) tuples

    Raises:
        ValidationError: If format is invalid
    """
    if not sets_str or not sets_str.strip():
        raise ValidationError("Sets string cannot be empty")

    sets: list[tuple[int, float, int]] = []
    parts = [p.strip() for p in sets_str.split(",") if p.strip()]

    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1

        # Parse: reps@weight/rest or reps@weight (rest optional for last set)
        # Weight can be: 0, +0, +5, +10.5, etc.
        match_with_rest = re.match(r"^(\d+)@\+?(-?\d+\.?\d*)/(\d+)$", part)
        match_no_rest = re.match(r"^(\d+)@\+?(-?\d+\.?\d*)$", part)

        if match_with_rest:
            reps = int(match_with_rest.group(1))
            weight = float(match_with_rest.group(2))
            rest = int(match_with_rest.group(3))
        elif match_no_rest and is_last:
            # Allow omitting rest for last set
            reps = int(match_no_rest.group(1))
            weight = float(match_no_rest.group(2))
            rest = 0
        else:
            raise ValidationError(
                f"Invalid set format: '{part}'. Expected format: reps@+kg/rest (e.g., 8@0/180 or 6@+5/120). "
                f"Rest can be omitted for the last set only."
            )

        if reps < 0:
            raise ValidationError(f"Reps must be non-negative: {reps}")
        if weight < 0:
            raise ValidationError(f"Weight must be non-negative: {weight}")
        if rest < 0:
            raise ValidationError(f"Rest must be non-negative: {rest}")

        sets.append((reps, weight, rest))

    if not sets:
        raise ValidationError("No valid sets found in sets string")

    return sets
