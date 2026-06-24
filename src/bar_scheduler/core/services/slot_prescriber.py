"""Build one :class:`SessionPlan` for a single calendar slot."""

from dataclasses import replace

from bar_scheduler.core.exercises.base import SessionTypeParams
from bar_scheduler.core.policies.load import LoadCalculator
from bar_scheduler.core.policies.sets import SetPrescriptor
from bar_scheduler.core.services.plan_run import PlanRun, Progress, context, week_number
from bar_scheduler.domain.context import AdaptationSignals
from bar_scheduler.domain.models import PlannedSet, SessionPlan

_Slot = tuple
_RECENT = 5  # same-type sessions fed to adaptive rest
_MILD_REST_BOOST_S = 30  # overtraining level 1
_HARD_REST_BOOST_S = 60  # overtraining level >= 2


def _overtraining_adjust(
    sets: list[PlannedSet], sparams: SessionTypeParams, level: int
) -> list[PlannedSet]:
    """Graduated density reduction: longer rest, fewer reps, drop a set."""
    rest_boost = _MILD_REST_BOOST_S if level == 1 else _HARD_REST_BOOST_S
    rep_deduct = 1 if level >= 3 else 0
    adjusted = [
        replace(
            planned,
            rest_seconds_before=min(sparams.rest_max, planned.rest_seconds_before + rest_boost),
            target_reps=max(sparams.reps_min, planned.target_reps - rep_deduct),
        )
        for planned in sets
    ]
    if level >= 2 and len(adjusted) > 2:
        return adjusted[:-1]
    return adjusted


class Prescriber:
    """Turn a slot into a prescribed session (sets, grip, assistance)."""

    def __init__(self, load: LoadCalculator, set_prescriptor: SetPrescriptor) -> None:
        self._load = load
        self._sets_policy = set_prescriptor

    def prescribe(self, run: PlanRun, slot: _Slot, progress: Progress) -> SessionPlan:
        """Prescribe one session, applying any overtraining density reduction."""
        training_max = int(progress.tm_float)
        ctx = context(run, slot[1], training_max)
        sets = self._sets(run, ctx, slot)
        adjusted = self._density(run, slot[1], sets, progress)
        return self._build_plan(run, slot, training_max, adjusted)

    def _sets(self, run: PlanRun, ctx, slot: _Slot) -> list[PlannedSet]:
        return self._sets_policy.prescribe(ctx, self._signals(run, slot))

    def _signals(self, run: PlanRun, slot: _Slot) -> AdaptationSignals:
        date_str = slot[0].strftime("%Y-%m-%d")
        same_type = run.history_by_type.get(slot[1], [])
        recent = [sess for sess in same_type if sess.date < date_str][-_RECENT:]
        return AdaptationSignals(
            ff_state=run.training_state.ff_state,
            history_sessions=len(run.effective_init),
            recent_same_type=tuple(recent),
            latest_test_max=run.training_state.latest_test_max,
        )

    def _density(
        self, run: PlanRun, session_type: str, sets: list[PlannedSet], progress: Progress
    ) -> list[PlannedSet]:
        if session_type == "TEST" or progress.density_left <= 0:
            return sets
        progress.density_left -= 1
        sparams = run.exercise.session_params[session_type]
        return _overtraining_adjust(sets, sparams, run.overtraining_level)

    def _build_plan(
        self, run: PlanRun, slot: _Slot, training_max: int, sets: list[PlannedSet]
    ) -> SessionPlan:
        date = slot[0]
        return SessionPlan(
            date=date.strftime("%Y-%m-%d"),
            grip=run.grip_selector.next_grip(slot[1]),
            session_type=slot[1],
            exercise_id=run.exercise.exercise_id,
            sets=sets,
            expected_tm=training_max,
            week_number=week_number(run, date),
            prescribed_assistance_kg=self._assistance(run, slot[1], training_max),
        )

    def _assistance(self, run: PlanRun, session_type: str, training_max: int) -> float | None:
        if not run.equipment.available_machine_assistance_kg:
            return None
        return self._load.machine_assistance(context(run, session_type, training_max))
