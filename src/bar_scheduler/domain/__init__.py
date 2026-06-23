"""Domain layer: pure value objects and the shared data model.

``bar_scheduler.domain.models`` holds the dataclasses; this package root
re-exports the planning value objects for convenient import.
"""

from bar_scheduler.domain.context import (
    EquipmentConstraints,
    LoadSpec,
    PlanRequest,
    PrescriptionContext,
    ProgressionGoal,
)

__all__ = [
    "EquipmentConstraints",
    "LoadSpec",
    "PlanRequest",
    "PrescriptionContext",
    "ProgressionGoal",
]
