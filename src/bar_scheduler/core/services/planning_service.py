"""Plan generation orchestrator.

Sequences the policy layer to produce a deterministic multi-week plan. Holds no
training rules itself: setup is delegated to :class:`RunFactory`, per-slot
prescription to :class:`Prescriber`, and weekly TM growth to ProgressionPolicy.
"""

from typing import Iterator

from bar_scheduler.core.policies.progression import ProgressionPolicy
from bar_scheduler.core.services.plan_run import PlanRun, Progress, context
from bar_scheduler.core.services.plan_setup import RunFactory
from bar_scheduler.core.services.slot_prescriber import Prescriber
from bar_scheduler.domain.context import PlanRequest
from bar_scheduler.domain.models import SessionPlan

_Slot = tuple


class PlanningService:
    """Generate a full training plan from a :class:`PlanRequest`."""

    def __init__(
        self,
        run_factory: RunFactory,
        prescriber: Prescriber,
        progression: ProgressionPolicy,
    ) -> None:
        self._run_factory = run_factory
        self._prescriber = prescriber
        self._progression = progression

    def generate(self, request: PlanRequest) -> list[SessionPlan]:
        """Return one :class:`SessionPlan` per planned session, in date order."""
        return list(self._iter(self._run_factory.build(request)))

    def _iter(self, run: PlanRun) -> Iterator[SessionPlan]:
        progress = Progress(
            tm_float=float(run.training_state.initial_tm),
            week_idx=0,
            density_left=run.overtraining_level,
        )
        for slot in run.slots:
            self._advance_week(run, progress, slot)
            yield self._prescriber.prescribe(run, slot, progress)

    def _advance_week(self, run: PlanRun, progress: Progress, slot: _Slot) -> None:
        week_idx = (slot[0] - run.start).days // 7
        if week_idx > progress.week_idx:
            progress.tm_float += self._weekly_delta(run, progress.tm_float, slot)
            progress.week_idx = week_idx

    def _weekly_delta(self, run: PlanRun, tm_float: float, slot: _Slot) -> float:
        ctx = context(run, slot[1], int(tm_float))
        return self._progression.weekly_delta(tm_float, run.goal, ctx)
