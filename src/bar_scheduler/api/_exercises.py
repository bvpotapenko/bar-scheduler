"""Exercise management functions for the bar-scheduler API."""
from __future__ import annotations

import json
from pathlib import Path

from ..core.exercises.registry import get_exercise
from ..io.user_store import UserStore
from ..io.serializers import exercise_target_to_dict
from ._common import _require_profile_store


def list_exercises() -> list[dict]:
    """
    Return metadata for all registered exercises.

    Returns a list of dicts with keys: ``id``, ``display_name``,
    ``muscle_group``, ``variants``, ``primary_variant``,
    ``has_variant_rotation``.
    """
    from ..core.exercises.registry import EXERCISE_REGISTRY

    import dataclasses

    return [
        {
            "id": ex.exercise_id,
            "display_name": ex.display_name,
            "muscle_group": ex.muscle_group,
            "variants": list(ex.variants),
            "primary_variant": ex.primary_variant,
            "has_variant_rotation": ex.has_variant_rotation,
            "bw_fraction": ex.bw_fraction,
            "onerm_includes_bodyweight": ex.onerm_includes_bodyweight,
            "session_params": {k: dataclasses.asdict(v) for k, v in ex.session_params.items()},
            "onerm_explanation": ex.onerm_explanation,
        }
        for ex in EXERCISE_REGISTRY.values()
    ]


def get_exercise_info(exercise_id: str) -> dict:
    """
    Return metadata for a single exercise by ID.

    Same shape as one item from ``list_exercises()``.
    Raises ``ValueError`` for unknown IDs.
    """
    import dataclasses

    ex = get_exercise(exercise_id)
    return {
        "id": ex.exercise_id,
        "display_name": ex.display_name,
        "muscle_group": ex.muscle_group,
        "variants": list(ex.variants),
        "primary_variant": ex.primary_variant,
        "has_variant_rotation": ex.has_variant_rotation,
        "bw_fraction": ex.bw_fraction,
        "onerm_includes_bodyweight": ex.onerm_includes_bodyweight,
        "session_params": {k: dataclasses.asdict(v) for k, v in ex.session_params.items()},
        "onerm_explanation": ex.onerm_explanation,
    }


def get_equipment_catalog(exercise_id: str) -> dict[str, dict]:
    """
    Return the equipment catalog for an exercise.

    Keys are item IDs (e.g. ``"BAR_ONLY"``, ``"BAND_LIGHT"``); values are
    dicts with at least ``"assistance_kg"``.  Returns ``{}`` for unknown IDs.
    """
    from ..core.equipment import get_catalog
    return get_catalog(exercise_id)


def set_exercise_target(
    data_dir: Path,
    exercise_id: str,
    reps: int,
    weight_kg: float = 0.0,
) -> None:
    """
    Set the user's personal goal for an exercise.

    ``reps`` is the target rep count (must be > 0).
    ``weight_kg`` is additional load on top of bodyweight (0 = bodyweight-only goal).
    Raises ``ValueError`` for unknown ``exercise_id`` or invalid values.
    """
    from ..core.models import ExerciseTarget

    get_exercise(exercise_id)
    target = ExerciseTarget(
        reps=reps, weight_kg=weight_kg
    )  # validates reps > 0, weight >= 0

    store = _require_profile_store(data_dir)
    with open(store.profile_path) as f:
        data = json.load(f)

    if "exercise_targets" not in data:
        data["exercise_targets"] = {}
    data["exercise_targets"][exercise_id] = exercise_target_to_dict(target)

    with open(store.profile_path, "w") as f:
        json.dump(data, f, indent=2)


def set_exercise_days(
    data_dir: Path,
    exercise_id: str,
    days_per_week: int,
) -> None:
    """
    Set per-exercise training frequency.

    ``days_per_week`` must be 1–5.
    Raises ``ValueError`` for unknown ``exercise_id`` or out-of-range days.
    """
    get_exercise(exercise_id)
    if days_per_week not in (1, 2, 3, 4, 5):
        raise ValueError(f"days_per_week must be 1–5, got {days_per_week}")

    store = _require_profile_store(data_dir)
    with open(store.profile_path) as f:
        data = json.load(f)

    if "exercise_days" not in data:
        data["exercise_days"] = {}
    data["exercise_days"][exercise_id] = days_per_week

    with open(store.profile_path, "w") as f:
        json.dump(data, f, indent=2)


def enable_exercise(data_dir: Path, exercise_id: str, *, days_per_week: int) -> None:
    """
    Add an exercise to the user's active list and create its history file.

    ``days_per_week`` (1–5) sets the training frequency for this exercise.
    Raises ``ValueError`` for unknown ``exercise_id`` or out-of-range days.
    Raises ``ProfileNotFoundError`` if the profile has not been initialised.
    """
    get_exercise(exercise_id)
    if days_per_week not in (1, 2, 3, 4, 5):
        raise ValueError(f"days_per_week must be 1–5, got {days_per_week}")

    store = _require_profile_store(data_dir)

    with open(store.profile_path) as f:
        data = json.load(f)

    enabled = list(data.get("exercises_enabled", []))
    if exercise_id not in enabled:
        enabled.append(exercise_id)
        data["exercises_enabled"] = enabled

    if "exercise_days" not in data:
        data["exercise_days"] = {}
    data["exercise_days"][exercise_id] = days_per_week

    with open(store.profile_path, "w") as f:
        json.dump(data, f, indent=2)

    UserStore(data_dir).init_exercise(
        exercise_id
    )  # create JSONL if missing (idempotent)


def disable_exercise(data_dir: Path, exercise_id: str) -> None:
    """
    Remove an exercise from the user's active list.

    No-op if the exercise is not currently enabled.
    The history file is preserved (data is never deleted automatically).
    Raises ``ProfileNotFoundError`` if the profile has not been initialised.
    """
    store = _require_profile_store(data_dir)

    with open(store.profile_path) as f:
        data = json.load(f)

    enabled = list(data.get("exercises_enabled", []))
    if exercise_id in enabled:
        enabled.remove(exercise_id)
        data["exercises_enabled"] = enabled
        with open(store.profile_path, "w") as f:
            json.dump(data, f, indent=2)


def delete_exercise_history(data_dir: Path, exercise_id: str) -> None:
    """
    Delete the history JSONL file for an exercise.

    No-op if the file does not exist.  The profile (exercises_enabled list,
    equipment history, plan anchors) is not modified — call
    ``disable_exercise`` separately if you also want to remove the exercise
    from the active list.
    Raises ``ProfileNotFoundError`` if the profile has not been initialised.
    """
    store = _require_profile_store(data_dir)
    store.history_path(exercise_id).unlink(missing_ok=True)
