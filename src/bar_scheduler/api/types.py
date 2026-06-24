"""Public input types for the bar-scheduler API."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

SessionType = Literal["S", "H", "E", "T", "TEST"]


@dataclass
class SetInput:
    reps: int
    rest_seconds: int
    added_weight_kg: float = 0.0
    rir_reported: int | None = None

    def __post_init__(self) -> None:
        if self.reps < 1:
            raise ValueError("SetInput.reps must be >= 1")
        if self.rest_seconds < 0:
            raise ValueError("SetInput.rest_seconds must be >= 0")
        if self.added_weight_kg < 0:
            raise ValueError("SetInput.added_weight_kg must be >= 0")


@dataclass
class SessionInput:
    date: str  # YYYY-MM-DD
    session_type: SessionType
    bodyweight_kg: float
    sets: list[SetInput]
    grip: str = "neutral"
    notes: str = ""

    def __post_init__(self) -> None:
        from datetime import datetime

        try:
            datetime.strptime(self.date, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"SessionInput.date must be YYYY-MM-DD, got {self.date!r}")
        valid_types = {"S", "H", "E", "T", "TEST"}
        if self.session_type not in valid_types:
            raise ValueError(f"SessionInput.session_type must be one of {valid_types}")
        if self.bodyweight_kg <= 0:
            raise ValueError("SessionInput.bodyweight_kg must be > 0")


def _inherit_list(provided, prev, attr):
    """None inherits the previous list; [] clears; a list replaces."""
    if provided is None:
        return list(getattr(prev, attr)) if prev else []
    return list(provided)


@dataclass
class EquipmentInput:
    """Equipment configuration for one exercise.

    For each kg list, ``None`` inherits the previous value, ``[]`` clears it,
    and a list replaces it.
    """

    available_items: list[str]
    available_weights_kg: list[float] | None = None
    available_machine_assistance_kg: list[float] | None = None
    available_band_assistance_kg: list[float] | None = None

    def to_state(self, exercise_id: str, prev):
        """Build the persisted EquipmentState, inheriting unset lists from ``prev``."""
        from bar_scheduler.domain.models import EquipmentState

        return EquipmentState(
            exercise_id=exercise_id,
            available_items=list(self.available_items),
            available_weights_kg=_inherit_list(
                self.available_weights_kg, prev, "available_weights_kg"
            ),
            available_machine_assistance_kg=_inherit_list(
                self.available_machine_assistance_kg, prev, "available_machine_assistance_kg"
            ),
            available_band_assistance_kg=_inherit_list(
                self.available_band_assistance_kg, prev, "available_band_assistance_kg"
            ),
        )
