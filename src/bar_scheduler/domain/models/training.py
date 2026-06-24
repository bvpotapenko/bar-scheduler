"""Set and session training-data models (logged and planned)."""

from dataclasses import dataclass, field
from typing import Literal

from bar_scheduler.domain.models.equipment import EquipmentSnapshot

# Grip is a plain str to support non-pull-up variant names
# (e.g. "standard", "chest_lean" for dips; "deficit" for BSS).
Grip = str
SessionType = Literal["S", "H", "E", "T", "TEST"]


def _reject_negative(**fields: float | None) -> None:
    """Raise ValueError for any named field that is present and < 0."""
    for name, amount in fields.items():
        if amount is not None and amount < 0:
            raise ValueError(f"{name} must be non-negative")


@dataclass
class SetResult:
    """A single set; represents planned (actual_reps=None) and completed sets."""

    target_reps: int
    actual_reps: int | None  # None for planned/not-yet-completed sets
    rest_seconds_before: int
    added_weight_kg: float = 0.0
    rir_target: int = 2
    rir_reported: int | None = None

    def __post_init__(self) -> None:
        _reject_negative(
            target_reps=self.target_reps,
            actual_reps=self.actual_reps,
            rest_seconds_before=self.rest_seconds_before,
            added_weight_kg=self.added_weight_kg,
            rir_target=self.rir_target,
            rir_reported=self.rir_reported,
        )


@dataclass
class PlannedSet:
    """A planned set for a future session (actual_reps always None)."""

    target_reps: int
    rest_seconds_before: int
    added_weight_kg: float = 0.0
    rir_target: int = 2

    def __post_init__(self) -> None:
        _reject_negative(
            target_reps=self.target_reps,
            rest_seconds_before=self.rest_seconds_before,
            added_weight_kg=self.added_weight_kg,
            rir_target=self.rir_target,
        )

    def to_set_result(self) -> SetResult:
        """Convert to a SetResult with actual_reps=None."""
        return SetResult(
            target_reps=self.target_reps,
            actual_reps=None,
            rest_seconds_before=self.rest_seconds_before,
            added_weight_kg=self.added_weight_kg,
            rir_target=self.rir_target,
            rir_reported=None,
        )


def _validate_date(date_str: str) -> None:
    """Validate a date string is a real ISO YYYY-MM-DD date."""
    import re
    from datetime import datetime

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid date: {date_str}") from exc


@dataclass
class SessionResult:
    """A completed or partially completed training session."""

    date: str  # ISO format: YYYY-MM-DD
    bodyweight_kg: float
    grip: Grip  # exercise-specific variant string (e.g. "pronated", "standard")
    session_type: SessionType
    exercise_id: str
    equipment_snapshot: EquipmentSnapshot | None = None  # equipment context at log time
    planned_sets: list[SetResult] = field(default_factory=list)
    completed_sets: list[SetResult] = field(default_factory=list)
    notes: str | None = None
    # Cached at log time: volume_session, avg_volume_set, estimated_1rm.
    session_metrics: dict | None = None

    def __post_init__(self) -> None:
        _validate_date(self.date)
        if self.bodyweight_kg <= 0:
            raise ValueError("bodyweight_kg must be positive")
        # Grip validation is exercise-specific; not enforced here.
        if self.session_type not in ("S", "H", "E", "T", "TEST"):
            raise ValueError(f"Invalid session_type: {self.session_type}")


@dataclass
class SessionPlan:
    """A planned future training session (prescription, no completed data)."""

    date: str  # ISO format: YYYY-MM-DD
    grip: Grip
    session_type: SessionType
    exercise_id: str
    sets: list[PlannedSet] = field(default_factory=list)
    expected_tm: int = 0  # Expected training max after completing this session
    week_number: int = 1  # Week number in the plan (1-indexed)
    # Machine assistance for this session (None = not applicable).
    prescribed_assistance_kg: float | None = None

    def __post_init__(self) -> None:
        _validate_date(self.date)
        if self.session_type not in ("S", "H", "E", "T", "TEST"):
            raise ValueError(f"Invalid session_type: {self.session_type}")

    @property
    def total_reps(self) -> int:
        """Sum of target reps for all sets in this session."""
        return sum(planned_set.target_reps for planned_set in self.sets)

    def to_session_result(self, bodyweight_kg: float) -> SessionResult:
        """Convert to a SessionResult for logging."""
        return SessionResult(
            date=self.date,
            bodyweight_kg=bodyweight_kg,
            grip=self.grip,
            session_type=self.session_type,
            exercise_id=self.exercise_id,
            planned_sets=[planned_set.to_set_result() for planned_set in self.sets],
            completed_sets=[],
        )
