"""Immutable value objects threaded through planning.

These replace the repeated 5-10 argument groups that made the planner hard
to read: a single context object carries "the situation we are prescribing
for", so policy methods take one argument instead of six.
"""

from __future__ import annotations

from dataclasses import dataclass

from bar_scheduler.core.exercises.base import ExerciseDefinition
from bar_scheduler.domain.models import (
    EquipmentState,
    ExerciseTarget,
    SessionResult,
    UserState,
)


@dataclass(frozen=True)
class EquipmentConstraints:
    """Discrete equipment the athlete owns, used to snap prescriptions.

    Empty tuples mean "unconstrained" (continuous 0.5 kg rounding / no
    assistance), matching the legacy empty-list / ``None`` behaviour.
    """

    available_weights_kg: tuple[float, ...] = ()
    available_machine_assistance_kg: tuple[float, ...] = ()
    available_band_assistance_kg: tuple[float, ...] = ()

    @classmethod
    def from_state(cls, state: EquipmentState | None) -> EquipmentConstraints:
        """Build from a persisted :class:`EquipmentState` (or empty if None)."""
        if state is None:
            return cls()
        return cls(
            available_weights_kg=tuple(state.available_weights_kg),
            available_machine_assistance_kg=tuple(state.available_machine_assistance_kg),
            available_band_assistance_kg=tuple(state.available_band_assistance_kg),
        )


@dataclass(frozen=True)
class LoadSpec:
    """The components of effective load (Leff) for one set.

    ``effective_kg`` = bodyweight share + added weight - assistance. Replaces
    the 5-argument "load calculation" group spread across the math functions.
    """

    bodyweight_kg: float
    bw_fraction: float = 1.0
    added_load_kg: float = 0.0
    assistance_kg: float = 0.0

    @property
    def effective_kg(self) -> float:
        return self.bodyweight_kg * self.bw_fraction + self.added_load_kg - self.assistance_kg


@dataclass(frozen=True)
class ProgressionGoal:
    """The athlete's goal for one exercise: reps, optionally at a weight."""

    reps: int
    weight_kg: float = 0.0

    @property
    def is_weighted(self) -> bool:
        return self.weight_kg > 0

    @classmethod
    def from_target(cls, target: ExerciseTarget | None, default_reps: int) -> ProgressionGoal:
        """Build from a user :class:`ExerciseTarget`, falling back to a default."""
        if target is None:
            return cls(reps=default_reps)
        return cls(reps=target.reps, weight_kg=target.weight_kg)


@dataclass(frozen=True)
class PrescriptionContext:
    """Everything a policy needs to prescribe load/sets for one session slot."""

    exercise: ExerciseDefinition
    training_max: int
    bodyweight_kg: float
    history: tuple[SessionResult, ...]
    session_type: str
    equipment: EquipmentConstraints = EquipmentConstraints()


@dataclass(frozen=True)
class PlanRequest:
    """Inputs to a single plan generation, collapsing the old 10-arg signature."""

    user_state: UserState
    start_date: str
    exercise: ExerciseDefinition
    weeks_ahead: int | None = None
    baseline_max: int | None = None
    overtraining_level: int = 0
    overtraining_rest_days: int = 0
    history_init_cutoff: str | None = None
    equipment: EquipmentConstraints = EquipmentConstraints()
