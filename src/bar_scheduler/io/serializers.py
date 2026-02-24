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
    Validate grip / variant name.

    Grip is now a plain ``str`` that can hold any exercise variant
    (e.g. "pronated", "standard", "front_foot_elevated").  The only
    requirement is that it is a non-empty string.

    Args:
        grip: Grip / variant string

    Returns:
        Validated grip

    Raises:
        ValidationError: If grip is empty or not a string
    """
    if not isinstance(grip, str) or not grip.strip():
        raise ValidationError(f"Invalid grip: {grip!r}. Must be a non-empty string.")
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

    Handles both old format (both target_reps and actual_reps) and new compact
    format (only one reps field):
      - completed set: only "actual_reps" present → target_reps = actual_reps
      - planned set:   only "target_reps" present → actual_reps = None
      - old format:    both present → use both as-is

    Args:
        data: Dict representation

    Returns:
        SetResult instance

    Raises:
        ValidationError: If data is invalid
    """
    actual_reps = data.get("actual_reps")
    target_reps = data.get("target_reps")

    # Compact new format: derive the missing field
    if actual_reps is not None and target_reps is None:
        target_reps = actual_reps   # completed set
    # planned set: actual_reps stays None

    validate_non_negative(target_reps or 0, "target_reps")
    if actual_reps is not None:
        validate_non_negative(actual_reps, "actual_reps")
    validate_non_negative(data.get("rest_seconds_before", 0), "rest_seconds_before")
    validate_non_negative(data.get("added_weight_kg", 0), "added_weight_kg")

    return SetResult(
        target_reps=int(target_reps or 0),
        actual_reps=int(actual_reps) if actual_reps is not None else None,
        rest_seconds_before=int(data.get("rest_seconds_before", 0)),
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


def _completed_set_to_dict(s: SetResult) -> dict[str, Any]:
    """Compact serializer for a completed set: only actual_reps (target is always equal)."""
    d: dict[str, Any] = {
        "actual_reps": s.actual_reps,
        "rest_seconds_before": s.rest_seconds_before,
        "added_weight_kg": s.added_weight_kg,
    }
    if s.rir_reported is not None:
        d["rir_reported"] = s.rir_reported
    return d


def _planned_set_result_to_dict(s: SetResult) -> dict[str, Any]:
    """Compact serializer for a planned set (from cache): only target_reps."""
    return {
        "target_reps": s.target_reps,
        "rest_seconds_before": s.rest_seconds_before,
        "added_weight_kg": s.added_weight_kg,
    }


def session_result_to_dict(session: SessionResult) -> dict[str, Any]:
    """
    Convert SessionResult to JSON-compatible dict.

    Uses compact per-set serialization:
      completed_sets → only actual_reps (target always equals actual)
      planned_sets   → only target_reps (actual is always None / not meaningful)

    Args:
        session: SessionResult to convert

    Returns:
        Dict representation
    """
    d: dict = {
        "date": session.date,
        "bodyweight_kg": session.bodyweight_kg,
        "grip": session.grip,
        "session_type": session.session_type,
        "exercise_id": session.exercise_id,
        "completed_sets": [_completed_set_to_dict(s) for s in session.completed_sets],
        "notes": session.notes,
    }
    # Only include planned_sets when non-empty (meaningful prescription data from cache)
    if session.planned_sets:
        d["planned_sets"] = [_planned_set_result_to_dict(s) for s in session.planned_sets]
    return d


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
        exercise_id=data.get("exercise_id", "pull_up"),
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
    d: dict[str, Any] = {
        "height_cm": profile.height_cm,
        "sex": profile.sex,
        "preferred_days_per_week": profile.preferred_days_per_week,
        "target_max_reps": profile.target_max_reps,
    }
    if profile.exercise_days:
        d["exercise_days"] = dict(profile.exercise_days)
    return d


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

    raw_exercise_days = data.get("exercise_days") or {}
    exercise_days = {k: int(v) for k, v in raw_exercise_days.items()}

    return UserProfile(
        height_cm=int(data["height_cm"]),
        sex=data["sex"],
        preferred_days_per_week=int(data.get("preferred_days_per_week", 3)),
        target_max_reps=int(data.get("target_max_reps", 30)),
        exercise_days=exercise_days,
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


_DEFAULT_REST_SECONDS = 180  # Used when rest is omitted from a set


def parse_compact_sets(s: str) -> list[tuple[int, float, int]] | None:
    """
    Try to parse a compact plan-style sets string.

    Format: [groups] [+Wkg] [/ Rs]
    Each group is either:
      NxM  (N reps × M sets, any x/X/× accepted)
      N    (1 set of N reps — bare integer)

    All sets in a compact expression share the same weight and rest.

    Examples:
        "5x4"                → 4 sets of 5 reps, BW, 180s rest
        "5x4 / 240s"         → 4 sets of 5 reps, BW, 240s rest
        "5x4 +0.5kg / 240s"  → 4 sets of 5 reps, +0.5 kg, 240s rest
        "4, 3x8 / 60s"       → 1 set of 4 + 8 sets of 3, BW, 60s rest
        "8, 7, 6, 5 / 60s"   → 4 individual sets [8,7,6,5] reps, BW, 60s rest

    Returns list of (reps, weight, rest) tuples, or None if format not recognised.
    Triggers on at least one 'x'/'×' OR a shared rest suffix '/ Ns'.
    """
    text = s.strip()

    # Require at least one 'x'/'×' OR a shared rest suffix '/ Ns' to be compact.
    # Per-set formats embed rest without a trailing 's' (e.g. "8@0/180"), so this is safe.
    has_x = bool(re.search(r"[xX×]", text))
    has_rest_suffix = bool(re.search(r"/\s*\d+\s*s\s*$", text))
    if not has_x and not has_rest_suffix:
        return None

    # Extract optional rest suffix:  / Ns
    rest = _DEFAULT_REST_SECONDS
    m = re.search(r"\s*/\s*(\d+)\s*s\s*$", text)
    if m:
        rest = int(m.group(1))
        text = text[: m.start()].strip()

    # Extract optional weight prefix on the right:  +W.Wkg
    weight = 0.0
    m = re.search(r"\+\s*([0-9]+(?:\.[0-9]+)?)\s*kg\s*$", text, re.IGNORECASE)
    if m:
        weight = float(m.group(1))
        text = text[: m.start()].strip()

    # Parse comma-separated groups
    groups = [g.strip() for g in text.split(",") if g.strip()]
    if not groups:
        return None

    result: list[tuple[int, float, int]] = []
    for group in groups:
        # NxM / N×M → N reps × M sets
        m = re.fullmatch(r"(\d+)\s*[xX×]\s*(\d+)", group)
        if m:
            n_reps = int(m.group(1))
            n_sets = int(m.group(2))
            if n_sets < 1 or n_reps < 0:
                return None
            for _ in range(n_sets):
                result.append((n_reps, weight, rest))
            continue
        # Bare integer → 1 set of N reps
        m = re.fullmatch(r"(\d+)", group)
        if m:
            result.append((int(m.group(1)), weight, rest))
            continue
        # Unknown group — not compact format
        return None

    return result if result else None


def parse_sets_string(sets_str: str) -> list[tuple[int, float, int]]:
    """
    Parse a sets string.

    Compact plan format (tried first):
        NxM [+Wkg] [/ Rs]   e.g. "4x5 +0.5kg / 240s"  → 4 sets of 5 reps
        N, MxK [/ Rs]        e.g. "4, 3x8 / 60s"        → 1×4 + 3×8 reps

    Per-set formats (comma-separated):
        reps@+kg/rest   e.g. "8@0/180"   canonical
        reps@+kg        e.g. "8@0"        rest defaults to 180 s
        reps kg rest    e.g. "8 0 180"    space-separated
        reps kg         e.g. "8 0"        space, rest defaults to 180 s
        reps            e.g. "8"          bare int, weight=0, rest=180 s

    Rest can be omitted from any set; defaults to 180 s.

    Args:
        sets_str: Sets string to parse

    Returns:
        List of (reps, added_weight_kg, rest_seconds) tuples

    Raises:
        ValidationError: If format is invalid
    """
    if not sets_str or not sets_str.strip():
        raise ValidationError("Sets string cannot be empty")

    # Try compact plan format first (e.g. "4x5 +0.5kg / 240s")
    compact = parse_compact_sets(sets_str.strip())
    if compact is not None:
        return compact

    sets: list[tuple[int, float, int]] = []
    parts = [p.strip() for p in sets_str.split(",") if p.strip()]

    for part in parts:
        # Try formats in priority order:
        # 1. reps@+weight/rest  (canonical with rest)
        # 2. reps@+weight       (canonical, rest omitted)
        # 3. reps weight rest   (space-separated)
        # 4. reps weight        (space-separated, rest omitted)
        # 5. reps               (bare integer, weight=0)
        match_at_rest = re.match(r"^(\d+)@\+?(-?\d+\.?\d*)/(\d+)$", part)
        match_at = re.match(r"^(\d+)@\+?(-?\d+\.?\d*)$", part)
        match_sp_rest = re.match(r"^(\d+)\s+(\+?-?\d+\.?\d*)\s+(\d+)$", part)
        match_sp = re.match(r"^(\d+)\s+(\+?-?\d+\.?\d*)$", part)
        match_bare = re.match(r"^(\d+)$", part)

        if match_at_rest:
            reps = int(match_at_rest.group(1))
            weight = float(match_at_rest.group(2))
            rest = int(match_at_rest.group(3))
        elif match_at:
            reps = int(match_at.group(1))
            weight = float(match_at.group(2))
            rest = _DEFAULT_REST_SECONDS
        elif match_sp_rest:
            reps = int(match_sp_rest.group(1))
            weight = float(match_sp_rest.group(2))
            rest = int(match_sp_rest.group(3))
        elif match_sp:
            reps = int(match_sp.group(1))
            weight = float(match_sp.group(2))
            rest = _DEFAULT_REST_SECONDS
        elif match_bare:
            reps = int(match_bare.group(1))
            weight = 0.0
            rest = _DEFAULT_REST_SECONDS
        else:
            raise ValidationError(
                f"Invalid set format: '{part}'.\n"
                f"Use: reps@weight/rest (e.g. 8@0/180), reps@weight (e.g. 6@+5),\n"
                f"     or space-separated: reps weight rest (e.g. 8 0 180)."
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
