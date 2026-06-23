"""Profile management functions for the bar-scheduler API."""

from __future__ import annotations

import json
from pathlib import Path

from bar_scheduler.io.user_store import UserStore
from bar_scheduler.io.serializers import (
    dict_to_user_profile,
    user_profile_to_dict,
)
from bar_scheduler.api._common import (
    ProfileAlreadyExistsError,
    _require_profile_store,
)


def init_profile(
    data_dir: Path,
    height_cm: int,
    bodyweight_kg: float,
    *,
    language: str = "en",
) -> dict:
    """
    Create a new user profile in ``data_dir``.

    Creates a bare profile with no exercises.  Use ``enable_exercise()`` to
    add exercises with their per-exercise training frequency.

    Raises ``ProfileAlreadyExistsError`` if profile.json already exists.
    Raises ``ValueError`` for invalid field values.
    Returns the profile dict (same shape as ``get_profile()``).
    """
    from bar_scheduler.core.models import UserProfile

    profile_path = data_dir / "profile.json"
    if profile_path.exists():
        raise ProfileAlreadyExistsError(
            f"Profile already exists at {profile_path}. Use update_profile() to change fields."
        )

    profile = UserProfile(
        height_cm=height_cm,
        bodyweight_kg=bodyweight_kg,
        language=language,
    )

    store = UserStore(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    store.save_profile(profile)

    return get_profile(data_dir)


def get_profile(data_dir: Path) -> dict | None:
    """
    Return the current user profile as a dict, or None if not initialised.

    The dict includes all UserProfile fields including ``current_bodyweight_kg``.
    """
    store = UserStore(data_dir)
    profile = store.load_profile()
    if profile is None:
        return None
    return user_profile_to_dict(profile)


def update_bodyweight(data_dir: Path, bodyweight_kg: float) -> None:
    """Update the current bodyweight in profile.json."""
    if bodyweight_kg <= 0:
        raise ValueError("bodyweight_kg must be positive")
    store = _require_profile_store(data_dir)
    store.update_bodyweight(bodyweight_kg)


def update_language(data_dir: Path, lang: str) -> None:
    """
    Set the display language preference stored in profile.json.

    Passing ``"en"`` removes the key (restores default). Any ISO 639-1 code
    is accepted — validation of supported languages is the client's
    responsibility.
    """
    if not lang:
        raise ValueError("lang must be a non-empty string")
    store = _require_profile_store(data_dir)
    store.update_language(lang)


def update_height(data_dir: Path, *, height_cm: int) -> dict:
    """
    Update the user's height in cm.

    Returns the updated profile dict.
    Raises ``ProfileNotFoundError`` if not yet initialised.
    Raises ``ValueError`` if ``height_cm`` is not positive.
    """
    return update_profile(data_dir, height_cm=height_cm)


def update_profile(
    data_dir: Path,
    *,
    height_cm: int | None = None,
    bodyweight_kg: float | None = None,
    language: str | None = None,
) -> dict:
    """
    Update one or more top-level profile fields.

    Only the fields you pass are changed; all others (including exercise data,
    ``plan_start_dates``, ``equipment``, etc.) are preserved.

    Returns the updated profile dict (same shape as ``get_profile()``).
    Raises ``ProfileNotFoundError`` if not yet initialised.
    Raises ``ValueError`` for invalid field values.
    """
    if height_cm is not None and height_cm <= 0:
        raise ValueError(f"height_cm must be positive, got {height_cm}")
    if bodyweight_kg is not None and bodyweight_kg <= 0:
        raise ValueError(f"bodyweight_kg must be positive, got {bodyweight_kg}")
    if language is not None and not language:
        raise ValueError("language must be a non-empty string")

    store = _require_profile_store(data_dir)
    with open(store.profile_path) as fp:
        raw = json.load(fp)

    if height_cm is not None:
        raw["height_cm"] = height_cm
    if bodyweight_kg is not None:
        raw["current_bodyweight_kg"] = bodyweight_kg
    if language is not None:
        if language == "en":
            raw.pop("language", None)
        else:
            raw["language"] = language

    dict_to_user_profile(raw)  # validate -- raises ValidationError if inconsistent

    with open(store.profile_path, "w") as fp:
        json.dump(raw, fp, indent=2)

    return get_profile(data_dir)
