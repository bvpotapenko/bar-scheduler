"""
Data models for bar-scheduler.

All core dataclasses representing training data, sessions, and plans.
Grip/variant values are exercise-specific strings; validation is delegated
to ExerciseDefinition rather than enforced at the model level.
"""

from dataclasses import dataclass, field
from typing import ClassVar, Literal

# Grip is now a plain str to support non-pull-up variant names
# (e.g. "standard", "chest_lean" for dips; "deficit" for BSS).
Grip = str
SessionType = Literal["S", "H", "E", "T", "TEST", "REST"]
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
class EquipmentSnapshot:
    """
    Minimal equipment context stored on each logged session.

    Captured at log time from the current EquipmentState so that past
    sessions can be re-analysed with the correct effective load even after
    the user changes equipment later.

    assistance_kg > 0 means the equipment is assistive (band/machine reduces
    the effective load).  For additive items (weight belt, dumbbells) this is
    0; the load contribution comes from SetResult.added_weight_kg instead.
    """

    active_item: str                    # e.g. "BAND_MEDIUM", "BAR_ONLY"
    assistance_kg: float                # kg of assistance subtracted from Leff
    elevation_height_cm: int | None = None  # BSS ELEVATION_SURFACE height


@dataclass
class EquipmentState:
    """
    Per-exercise equipment state for one time period.

    Stored as an append-only list in profile.json.  When equipment changes,
    the current entry's valid_until is set and a new entry is appended.
    """

    exercise_id: str
    available_items: list[str]          # all items the user owns / has access to
    active_item: str                    # item currently used for training
    machine_assistance_kg: float | None = None  # only for MACHINE_ASSISTED items
    elevation_height_cm: int | None = None      # only for BSS ELEVATION_SURFACE
    valid_from: str = ""                # ISO date of this entry
    valid_until: str | None = None      # None = still current


@dataclass
class SessionResult:
    """
    A completed or partially completed training session.

    Contains both planned sets and what was actually performed.
    """

    date: str  # ISO format: YYYY-MM-DD
    bodyweight_kg: float
    grip: Grip  # exercise-specific variant string (e.g. "pronated", "standard")
    session_type: SessionType
    exercise_id: str = "pull_up"
    equipment_snapshot: EquipmentSnapshot | None = None  # equipment context at log time
    planned_sets: list[SetResult] = field(default_factory=list)
    completed_sets: list[SetResult] = field(default_factory=list)
    notes: str | None = None

    def __post_init__(self) -> None:
        """Validate session data."""
        # Validate date format
        self._validate_date(self.date)

        if self.bodyweight_kg <= 0:
            raise ValueError("bodyweight_kg must be positive")

        # Grip validation is exercise-specific; not enforced here.

        if self.session_type not in ("S", "H", "E", "T", "TEST", "REST"):
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
    grip: Grip  # exercise-specific variant string
    session_type: SessionType
    exercise_id: str = "pull_up"
    sets: list[PlannedSet] = field(default_factory=list)
    expected_tm: int = 0  # Expected training max after completing this session
    week_number: int = 1  # Week number in the plan (1-indexed)

    def __post_init__(self) -> None:
        """Validate session plan data."""
        SessionResult._validate_date(self.date)
        # Grip validation is exercise-specific; not enforced here.
        if self.session_type not in ("S", "H", "E", "T", "TEST", "REST"):
            raise ValueError(f"Invalid session_type: {self.session_type}")

    @property
    def total_reps(self) -> int:
        """Sum of target reps for all sets in this session."""
        return sum(s.target_reps for s in self.sets)

    def to_session_result(self, bodyweight_kg: float) -> SessionResult:
        """Convert to a SessionResult for logging."""
        return SessionResult(
            date=self.date,
            bodyweight_kg=bodyweight_kg,
            grip=self.grip,
            session_type=self.session_type,
            exercise_id=self.exercise_id,
            planned_sets=[s.to_set_result() for s in self.sets],
            completed_sets=[],
        )


@dataclass
class ExerciseTarget:
    """
    User's personal goal for one exercise.

    Either reps-only (``weight_kg=0``) or reps-at-weight, e.g.
    "12 BSS reps @ 40 kg" or "20 pull-ups + 10 kg vest".
    """

    reps: int
    weight_kg: float = 0.0

    def __post_init__(self) -> None:
        if self.reps <= 0:
            raise ValueError("ExerciseTarget.reps must be positive")
        if self.weight_kg < 0:
            raise ValueError("ExerciseTarget.weight_kg must be non-negative")

    def __str__(self) -> str:
        if self.weight_kg > 0:
            return f"{self.reps} reps @ {self.weight_kg:.1f} kg"
        return f"{self.reps} reps"


@dataclass
class UserProfile:
    """
    User profile with physical characteristics and preferences.

    ``exercise_days`` stores per-exercise overrides for training days per week
    (e.g. {"pull_up": 3, "dip": 4, "bss": 3}).  Exercises absent from the dict
    fall back to ``preferred_days_per_week``.

    ``exercises_enabled`` lists which exercises are active (default: all three).
    ``max_session_duration_minutes`` is used in plan display notes.
    ``rest_preference`` ("short" | "normal" | "long") biases adaptive rest.
    ``injury_notes`` is a free-text field for the user's own records.
    """

    height_cm: int
    sex: Sex
    preferred_days_per_week: int = 3  # global fallback (3 or 4)
    exercise_days: dict = field(default_factory=dict)   # {exercise_id: days_per_week}
    exercise_targets: dict = field(default_factory=dict)  # {exercise_id: ExerciseTarget}
    exercises_enabled: list = field(default_factory=lambda: ["pull_up", "dip", "bss"])
    max_session_duration_minutes: int = 60
    rest_preference: str = "normal"  # "short" | "normal" | "long"
    injury_notes: str = ""

    # Per-exercise default goals used when the user hasn't set an explicit target.
    _TARGET_DEFAULTS: ClassVar[dict[str, tuple[int, float]]] = {
        "pull_up": (30, 0.0),
        "dip":     (40, 0.0),
        "bss":     (20, 0.0),
    }

    def days_for_exercise(self, exercise_id: str) -> int:
        """Return training days per week for the given exercise."""
        return self.exercise_days.get(exercise_id, self.preferred_days_per_week)

    def target_for_exercise(self, exercise_id: str) -> ExerciseTarget:
        """Return the user's personal goal for the given exercise.

        Falls back to sensible per-exercise defaults when the user hasn't
        configured an explicit target (pull_up→30, dip→40, bss→20, all weight=0).
        """
        if exercise_id in self.exercise_targets:
            return self.exercise_targets[exercise_id]
        reps, weight = self._TARGET_DEFAULTS.get(exercise_id, (30, 0.0))
        return ExerciseTarget(reps=reps, weight_kg=weight)

    def is_exercise_enabled(self, exercise_id: str) -> bool:
        """Return True if the exercise is in the enabled list."""
        return exercise_id in self.exercises_enabled

    def __post_init__(self) -> None:
        """Validate profile data."""
        if self.height_cm <= 0:
            raise ValueError("height_cm must be positive")

        if self.sex not in ("male", "female"):
            raise ValueError(f"Invalid sex: {self.sex}")

        if self.rest_preference not in ("short", "normal", "long"):
            raise ValueError(
                f"Invalid rest_preference: {self.rest_preference!r}. "
                "Must be 'short', 'normal', or 'long'."
            )

        if self.preferred_days_per_week not in (3, 4):
            raise ValueError("preferred_days_per_week must be 3 or 4")

        for ex_id, days in self.exercise_days.items():
            if days not in (3, 4):
                raise ValueError(
                    f"exercise_days[{ex_id!r}] must be 3 or 4, got {days}"
                )

        for ex_id, tgt in self.exercise_targets.items():
            if not isinstance(tgt, ExerciseTarget):
                raise ValueError(
                    f"exercise_targets[{ex_id!r}] must be an ExerciseTarget, got {type(tgt)}"
                )


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
