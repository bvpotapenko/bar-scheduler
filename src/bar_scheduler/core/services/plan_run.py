"""Per-plan run state and the small helpers that read it.

``PlanRun`` is the immutable bundle assembled once per plan (history, calendar,
initial state, rotation). ``Progress`` is the only mutable accumulator carried
through the generation loop.
"""

from dataclasses import dataclass
from datetime import datetime

from bar_scheduler.core.exercises.base import ExerciseDefinition
from bar_scheduler.core.policies.grip import GripSelector
from bar_scheduler.domain.context import (
    EquipmentConstraints,
    PrescriptionContext,
    ProgressionGoal,
)
from bar_scheduler.domain.models import SessionResult
from bar_scheduler.domain.results import TrainingState

_Slot = tuple[datetime, str]


@dataclass(frozen=True)
class HistoryWindow:
    """Full exercise history split by the plan-stability cutoff.

    ``for_init`` are the pre-plan sessions used for initial state (TM, FF,
    rotation); ``full`` includes mid-plan sessions used for week anchoring and
    TEST scheduling. ``effective_init`` falls back to ``full`` for new users.
    """

    full: list[SessionResult]
    for_init: list[SessionResult]

    @property
    def effective_init(self) -> list[SessionResult]:
        return self.for_init or self.full


@dataclass(frozen=True)
class PlanRun:
    """Everything fixed for one plan generation pass."""

    exercise: ExerciseDefinition
    bodyweight_kg: float
    equipment: EquipmentConstraints
    overtraining_level: int
    history: list[SessionResult]
    effective_init: list[SessionResult]
    training_state: TrainingState
    goal: ProgressionGoal
    start: datetime
    slots: list[_Slot]
    first_monday: datetime | None
    grip_selector: GripSelector
    history_by_type: dict[str, list[SessionResult]]


@dataclass
class Progress:
    """Mutable accumulators advanced as the plan loop walks the slots."""

    tm_float: float
    week_idx: int
    density_left: int


def context(run: PlanRun, session_type: str, training_max: int) -> PrescriptionContext:
    """Build the prescription context for one slot from the run."""
    return PrescriptionContext(
        exercise=run.exercise,
        training_max=training_max,
        bodyweight_kg=run.bodyweight_kg,
        history=tuple(run.history),
        session_type=session_type,
        equipment=run.equipment,
    )


def week_number(run: PlanRun, date: datetime) -> int:
    """Display week number, anchored to the first-session Monday (or plan start)."""
    anchor = run.first_monday or run.start
    return (date - anchor).days // 7 + 1
