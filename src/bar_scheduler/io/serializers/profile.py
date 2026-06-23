"""User profile and exercise-target <-> dict conversion."""

from typing import Any

from bar_scheduler.domain.models import ExerciseTarget, UserProfile
from bar_scheduler.io.serializers.validators import validate_positive


def exercise_target_to_dict(target: ExerciseTarget) -> dict[str, Any]:
    """Serialize an ExerciseTarget; omits weight_kg when zero."""
    row: dict[str, Any] = {"reps": target.reps}
    if target.weight_kg > 0:
        row["weight_kg"] = target.weight_kg
    return row


def dict_to_exercise_target(raw: dict[str, Any]) -> ExerciseTarget:
    """Deserialize an ExerciseTarget from a dict."""
    return ExerciseTarget(
        reps=int(raw["reps"]),
        weight_kg=float(raw.get("weight_kg", 0.0)),
    )


def user_profile_to_dict(profile: UserProfile) -> dict[str, Any]:
    """Convert a UserProfile to a JSON-compatible dict (omits defaults)."""
    row: dict[str, Any] = {
        "height_cm": profile.height_cm,
        "current_bodyweight_kg": profile.bodyweight_kg,
        "exercises_enabled": list(profile.exercises_enabled),
    }
    if profile.exercise_days:
        row["exercise_days"] = dict(profile.exercise_days)
    if profile.exercise_targets:
        row["exercise_targets"] = {
            ex_id: exercise_target_to_dict(tgt) for ex_id, tgt in profile.exercise_targets.items()
        }
    if profile.language != "en":
        row["language"] = profile.language
    return row


def _parse_targets(raw: dict[str, Any]) -> dict[str, ExerciseTarget]:
    """Deserialize the exercise_targets mapping (empty when absent)."""
    targets: dict[str, ExerciseTarget] = {}
    for ex_id, tgt in (raw.get("exercise_targets") or {}).items():
        targets[ex_id] = dict_to_exercise_target(tgt)
    return targets


def dict_to_user_profile(raw: dict[str, Any]) -> UserProfile:
    """Convert a dict to a UserProfile."""
    validate_positive(raw.get("height_cm", 0), "height_cm")
    validate_positive(raw.get("current_bodyweight_kg", 0), "current_bodyweight_kg")
    raw_days = raw.get("exercise_days") or {}
    exercise_days = {ex_id: int(days) for ex_id, days in raw_days.items()}

    return UserProfile(
        height_cm=int(raw["height_cm"]),
        bodyweight_kg=float(raw["current_bodyweight_kg"]),
        exercise_days=exercise_days,
        exercise_targets=_parse_targets(raw),
        exercises_enabled=list(raw.get("exercises_enabled", [])),
        language=str(raw.get("language", "en")),
    )
