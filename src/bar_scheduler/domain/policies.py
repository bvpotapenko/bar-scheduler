"""Policy interfaces (Protocols) the planning service depends on.

Each behavioral rule is a narrow, swappable contract. PlanningService
depends on these, not on concrete classes, so tests inject fakes and the DI
container wires the real implementations.
"""

from datetime import datetime
from typing import Protocol

from bar_scheduler.domain.context import AdaptationSignals, PrescriptionContext
from bar_scheduler.domain.models import FitnessFatigueState, PlannedSet, SessionResult


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


class SetPolicy(Protocol):
    """Sets/reps/rest/weight prescription for one session slot."""

    def prescribe(
        self, ctx: PrescriptionContext, signals: AdaptationSignals
    ) -> list[PlannedSet]: ...


class RestPolicy(Protocol):
    """Adaptive rest duration in seconds."""

    def recommend(
        self,
        session_type: str,
        recent_sessions: list[SessionResult],
        ff_state: FitnessFatigueState | None,
        exercise,
    ) -> int: ...


class AutoregulationPolicy(Protocol):
    """Volume (sets, reps) adjustment from readiness."""

    def adjust(
        self,
        base: tuple[int, int],
        ff_state: FitnessFatigueState,
        history_sessions: int,
        sets_min: int = 1,
    ) -> tuple[int, int]: ...
