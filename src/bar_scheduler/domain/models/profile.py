"""User profile, goals, and aggregate state models."""

from dataclasses import dataclass, field

from bar_scheduler.domain.models.training import SessionResult


def _validate_exercise_days(exercise_days: dict) -> None:
    for ex_id, days in exercise_days.items():
        if days not in (1, 2, 3, 4, 5):
            raise ValueError(f"exercise_days[{ex_id!r}] must be 1-5, got {days}")


def _validate_exercise_targets(exercise_targets: dict) -> None:
    for ex_id, tgt in exercise_targets.items():
        if not isinstance(tgt, ExerciseTarget):
            raise ValueError(
                f"exercise_targets[{ex_id!r}] must be an ExerciseTarget, got {type(tgt)}",
            )


@dataclass
class ExerciseTarget:
    """User's personal goal for one exercise: reps, optionally at a weight."""

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

    ``exercise_days`` stores per-exercise training frequency in days/week.
    Every exercise in ``exercises_enabled`` must have an entry here.
    """

    height_cm: int
    bodyweight_kg: float
    exercise_days: dict = field(default_factory=dict)  # {exercise_id: days_per_week}
    exercise_targets: dict = field(default_factory=dict)  # {exercise_id: ExerciseTarget}
    exercises_enabled: list = field(default_factory=list)
    language: str = "en"  # ISO 639-1 code; "en" = English (default)

    def days_for_exercise(self, exercise_id: str) -> int:
        """Return training days per week for the given exercise."""
        return self.exercise_days[exercise_id]

    def target_for_exercise(self, exercise_id: str) -> ExerciseTarget | None:
        """Return the user's personal goal for the given exercise, or None if not set."""
        return self.exercise_targets.get(exercise_id)

    def is_exercise_enabled(self, exercise_id: str) -> bool:
        """Return True if the exercise is in the enabled list."""
        return exercise_id in self.exercises_enabled

    def __post_init__(self) -> None:
        if self.height_cm <= 0:
            raise ValueError("height_cm must be positive")
        if self.bodyweight_kg <= 0:
            raise ValueError("bodyweight_kg must be positive")
        _validate_exercise_days(self.exercise_days)
        _validate_exercise_targets(self.exercise_targets)
        if not self.language or not isinstance(self.language, str):
            raise ValueError("language must be a non-empty string, e.g. 'en'")


@dataclass
class UserState:
    """Complete user state: profile + history. Bodyweight via ``profile.bodyweight_kg``."""

    profile: UserProfile
    history: list[SessionResult] = field(default_factory=list)
