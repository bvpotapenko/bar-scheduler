"""Policy interfaces (Protocols) the planning service depends on.

Each behavioral rule is a narrow, swappable contract. PlanningService
depends on these, not on concrete classes, so tests inject fakes and the DI
container wires the real implementations.
"""

from datetime import datetime
from typing import Protocol

from bar_scheduler.domain.context import PrescriptionContext


class LoadPolicy(Protocol):
    """Weight / assistance prescription (owns the Epley-inverse formula)."""

    def added_weight(self, ctx: PrescriptionContext) -> float: ...

    def machine_assistance(self, ctx: PrescriptionContext) -> float: ...

    def band_assistance(self, ctx: PrescriptionContext) -> float: ...


class GripPolicy(Protocol):
    """Variant/grip rotation across a plan."""

    def next_grip(self, session_type: str) -> str: ...


class SchedulePolicy(Protocol):
    """Calendar placement of session slots."""

    def session_days(
        self,
        start: datetime,
        days_per_week: int,
        num_weeks: int,
        start_rotation_idx: int = 0,
    ) -> list[tuple[datetime, str]]: ...
