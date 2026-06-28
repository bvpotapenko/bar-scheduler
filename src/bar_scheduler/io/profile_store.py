"""Persistence for the core ``UserProfile`` fields in profile.json."""

from pathlib import Path

from bar_scheduler.domain.models import UserProfile
from bar_scheduler.io.profile_document import ProfileDocument
from bar_scheduler.io.serializers import (
    ValidationError,
    dict_to_user_profile,
    user_profile_to_dict,
)


class ProfileStore:
    """Load/save the UserProfile and apply partial scalar-field updates."""

    def __init__(self, doc: ProfileDocument):
        self._doc = doc

    @property
    def path(self) -> Path:
        """Path of the underlying profile.json (for caller error messages)."""
        return self._doc.path

    def exists(self) -> bool:
        """Whether the profile.json file is present."""
        return self._doc.exists()

    def load(self) -> UserProfile | None:
        """Return the stored profile, or None when absent or invalid."""
        if not self._doc.exists():
            return None
        try:
            return dict_to_user_profile(self._doc.read())
        except ValidationError, KeyError:
            return None

    def save(self, profile: UserProfile) -> None:
        """Overwrite profile.json with ``profile``."""
        self._doc.write(user_profile_to_dict(profile))

    def update_fields(
        self,
        *,
        height_cm: int | None = None,
        bodyweight_kg: float | None = None,
        language: str | None = None,
    ) -> None:
        """Apply the provided fields, preserving all other document keys.

        ``language="en"`` removes the key (the omitted default). Raises
        ``ValidationError`` if the resulting profile is inconsistent.
        """
        with self._doc.mutate() as raw:
            if height_cm is not None:
                raw["height_cm"] = height_cm
            if bodyweight_kg is not None:
                raw["current_bodyweight_kg"] = bodyweight_kg
            if language == "en":
                raw.pop("language", None)
            elif language is not None:
                raw["language"] = language
            dict_to_user_profile(raw)  # validate before the write on context exit
