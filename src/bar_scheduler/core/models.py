"""
Data models for the pull-up planner.

All core dataclasses representing training data, sessions, and plans.
"""

from dataclasses import dataclass, field
from typing import Literal

# Type aliases for enums
Grip = Literal["pronated", "supinated", "neutral"]
SessionType = Literal["S", "H", "E", "T", "TEST"]
Sex = Literal["male", "female"]


@dataclass
class SetResult:
    """
    A single set within a training session.

    Can represent both planned sets (actual_reps=None) and completed sets.
    """

    target_reps: int
    actual_reps: int | None  # None for planned/not-yet-completed sets
    rest_seconds_before: int
    added_weight_kg: float = 0.0
    rir_target: int = 2
    rir_reported: int | None = None

    def __post_init__(self) -> None:
        """Validate set data."""
        if self.target_reps < 0:
            raise ValueError("target_reps must be non-negative")
        if self.actual_reps is not None and self.actual_reps < 0:
            raise ValueError("actual_reps must be non-negative")
        if self.rest_seconds_before < 0:
            raise ValueError("rest_seconds_before must be non-negative")
        if self.added_weight_kg < 0:
            raise ValueError("added_weight_kg must be non-negative")
        if self.rir_target < 0:
            raise ValueError("rir_target must be non-negative")
        if self.rir_reported is not None and self.rir_reported < 0:
            raise ValueError("rir_reported must be non-negative")


@dataclass
class PlannedSet:
    """
    A planned set for a future session.

    Same structure as SetResult but actual_reps is always None.
    """

    target_reps: int
    rest_seconds_before: int
    added_weight_kg: float = 0.0
    rir_target: int = 2

    def __post_init__(self) -> None:
        """Validate planned set data."""
        if self.target_reps < 0:
            raise ValueError("target_reps must be non-negative")
        if self.rest_seconds_before < 0:
            raise ValueError("rest_seconds_before must be non-negative")
        if self.added_weight_kg < 0:
            raise ValueError("added_weight_kg must be non-negative")
        if self.rir_target < 0:
            raise ValueError("rir_target must be non-negative")

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


@dataclass
class SessionResult:
    """
    A completed or partially completed training session.

    Contains both planned sets and what was actually performed.
    """

    date: str  # ISO format: YYYY-MM-DD
    bodyweight_kg: float
    grip: Grip
    session_type: SessionType
    planned_sets: list[SetResult] = field(default_factory=list)
    completed_sets: list[SetResult] = field(default_factory=list)
    notes: str | None = None

    def __post_init__(self) -> None:
        """Validate session data."""
        # Validate date format
        self._validate_date(self.date)

        if self.bodyweight_kg <= 0:
            raise ValueError("bodyweight_kg must be positive")

        if self.grip not in ("pronated", "supinated", "neutral"):
            raise ValueError(f"Invalid grip: {self.grip}")

        if self.session_type not in ("S", "H", "E", "T", "TEST"):
            raise ValueError(f"Invalid session_type: {self.session_type}")

    @staticmethod
    def _validate_date(date_str: str) -> None:
        """Validate date string is ISO format YYYY-MM-DD."""
        import re

        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")

        # Also check it's a valid date
        from datetime import datetime

        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"Invalid date: {date_str}") from e


@dataclass
class SessionPlan:
    """
    A planned future training session.

    Contains the prescription for sets but no completed data.
    """

    date: str  # ISO format: YYYY-MM-DD
    grip: Grip
    session_type: SessionType
    sets: list[PlannedSet] = field(default_factory=list)
    expected_tm: int = 0  # Expected training max after completing this session
    week_number: int = 1  # Week number in the plan (1-indexed)

    def __post_init__(self) -> None:
        """Validate session plan data."""
        SessionResult._validate_date(self.date)

    @property
    def total_reps(self) -> int:
        """Sum of target reps for all sets in this session."""
        return sum(s.target_reps for s in self.sets)

        if self.grip not in ("pronated", "supinated", "neutral"):
            raise ValueError(f"Invalid grip: {self.grip}")

        if self.session_type not in ("S", "H", "E", "T", "TEST"):
            raise ValueError(f"Invalid session_type: {self.session_type}")

    def to_session_result(self, bodyweight_kg: float) -> SessionResult:
        """Convert to a SessionResult for logging."""
        return SessionResult(
            date=self.date,
            bodyweight_kg=bodyweight_kg,
            grip=self.grip,
            session_type=self.session_type,
            planned_sets=[s.to_set_result() for s in self.sets],
            completed_sets=[],
        )


@dataclass
class UserProfile:
    """
    User profile with physical characteristics and preferences.
    """

    height_cm: int
    sex: Sex
    preferred_days_per_week: int = 3  # 3 or 4
    target_max_reps: int = 30

    def __post_init__(self) -> None:
        """Validate profile data."""
        if self.height_cm <= 0:
            raise ValueError("height_cm must be positive")

        if self.sex not in ("male", "female"):
            raise ValueError(f"Invalid sex: {self.sex}")

        if self.preferred_days_per_week not in (3, 4):
            raise ValueError("preferred_days_per_week must be 3 or 4")

        if self.target_max_reps <= 0:
            raise ValueError("target_max_reps must be positive")


@dataclass
class UserState:
    """
    Complete user state including profile, current bodyweight, and history.
    """

    profile: UserProfile
    current_bodyweight_kg: float
    history: list[SessionResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate user state."""
        if self.current_bodyweight_kg <= 0:
            raise ValueError("current_bodyweight_kg must be positive")


@dataclass
class FitnessFatigueState:
    """
    State of the fitness-fatigue impulse response model.
    """

    fitness: float = 0.0  # G(t) - slow decay fitness
    fatigue: float = 0.0  # H(t) - fast decay fatigue
    m_hat: float = 10.0  # Estimated standardized max
    sigma_m: float = 1.5  # Uncertainty in max estimate
    readiness_mean: float = 0.0  # Rolling mean of readiness
    readiness_var: float = 1.0  # Rolling variance of readiness

    def readiness(self) -> float:
        """Calculate current readiness R(t) = G(t) - H(t)."""
        return self.fitness - self.fatigue

    def readiness_z_score(self) -> float:
        """Calculate readiness z-score for autoregulation."""
        if self.readiness_var <= 0:
            return 0.0
        import math

        std = math.sqrt(self.readiness_var)
        if std == 0:
            return 0.0
        return (self.readiness() - self.readiness_mean) / std


@dataclass
class TrainingStatus:
    """
    Current training status derived from history analysis.
    """

    training_max: int
    latest_test_max: int | None
    trend_slope: float  # reps per week
    is_plateau: bool
    deload_recommended: bool
    compliance_ratio: float
    fatigue_score: float
    fitness_fatigue_state: FitnessFatigueState
