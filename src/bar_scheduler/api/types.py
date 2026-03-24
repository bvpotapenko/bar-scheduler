"""Public input types for the bar-scheduler API."""
from __future__ import annotations
from dataclasses import dataclass, field
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
    date: str            # YYYY-MM-DD
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
