"""Domain data models — the shared dataclasses for the whole library."""

from bar_scheduler.domain.models.equipment import EquipmentSnapshot, EquipmentState
from bar_scheduler.domain.models.profile import (
    ExerciseTarget,
    UserProfile,
    UserState,
)
from bar_scheduler.domain.models.state import FitnessFatigueState, TrainingStatus
from bar_scheduler.domain.models.training import (
    Grip,
    PlannedSet,
    SessionPlan,
    SessionResult,
    SessionType,
    SetResult,
)

__all__ = [
    "Grip",
    "SessionType",
    "SetResult",
    "PlannedSet",
    "SessionResult",
    "SessionPlan",
    "EquipmentSnapshot",
    "EquipmentState",
    "ExerciseTarget",
    "UserProfile",
    "UserState",
    "FitnessFatigueState",
    "TrainingStatus",
]
