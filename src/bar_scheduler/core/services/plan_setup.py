"""Assemble a :class:`PlanRun` from a :class:`PlanRequest` using the policies."""

from datetime import datetime

from bar_scheduler.config.schedule_params import PlanHorizonConfig
from bar_scheduler.core.policies.grip import GripSelector
from bar_scheduler.core.policies.progression import ProgressionPolicy
from bar_scheduler.core.policies.schedule import shift
from bar_scheduler.core.services.plan_calendar import PlanCalendar
from bar_scheduler.core.services.plan_run import HistoryWindow, PlanRun
from bar_scheduler.core.services.training_state import TrainingStateCalculator
from bar_scheduler.domain.context import PlanRequest, ProgressionGoal
from bar_scheduler.domain.models import SessionResult, SetResult
from bar_scheduler.domain.results import TrainingState

History = list[SessionResult]
_TEST_REST_SECONDS = 180


def _history_by_type(history: History) -> dict[str, History]:
    """Index sessions by type for per-slot date-filtered lookups."""
    indexed: dict[str, History] = {}
    for sess in history:
        indexed.setdefault(sess.session_type, []).append(sess)
    return indexed


def _baseline_set(baseline_max: int) -> SetResult:
    """The single all-out set of a synthetic baseline TEST."""
    return SetResult(
        target_reps=baseline_max,
        actual_reps=baseline_max,
        rest_seconds_before=_TEST_REST_SECONDS,
        added_weight_kg=0.0,
        rir_target=0,
        rir_reported=0,
    )


def create_synthetic_test_session(request: PlanRequest) -> SessionResult:
    """A one-set TEST dated the day before the plan start, for new athletes."""
    test_set = _baseline_set(request.baseline_max)
    prior = shift(datetime.strptime(request.start_date, "%Y-%m-%d"), -1)
    return SessionResult(
        date=prior.strftime("%Y-%m-%d"),
        bodyweight_kg=request.user_state.profile.bodyweight_kg,
        grip="pronated",
        session_type="TEST",
        exercise_id=request.exercise.exercise_id,
        planned_sets=[test_set],
        completed_sets=[test_set],
        notes="Synthetic baseline test",
    )


class RunFactory:
    """Build the per-plan :class:`PlanRun` (history split, state, calendar)."""

    def __init__(
        self,
        training_state: TrainingStateCalculator,
        progression: ProgressionPolicy,
        calendar: PlanCalendar,
        horizon: PlanHorizonConfig,
    ) -> None:
        self._training_state = training_state
        self._progression = progression
        self._calendar = calendar
        self._horizon = horizon

    def build(self, request: PlanRequest) -> PlanRun:
        """Assemble the run, raising ValueError when no history and no baseline."""
        window = self._window(request)
        bodyweight = request.user_state.profile.bodyweight_kg
        state = self._training_state.compute(window, bodyweight, request.baseline_max)
        goal = self._goal(request)
        calendar = self._calendar.build(request, window, self._weeks(request, state, goal))
        return PlanRun(
            exercise=request.exercise,
            bodyweight_kg=bodyweight,
            equipment=request.equipment,
            overtraining_level=request.overtraining_level,
            history=window.full,
            effective_init=window.effective_init,
            training_state=state,
            goal=goal,
            start=calendar.start,
            slots=calendar.slots,
            first_monday=calendar.first_monday,
            grip_selector=self._grip_selector(window, request),
            history_by_type=_history_by_type(window.full),
        )

    def _window(self, request: PlanRequest) -> HistoryWindow:
        history = self._exercise_history(request)
        cutoff = request.history_init_cutoff or request.start_date
        for_init = [sess for sess in history if sess.date < cutoff]
        return HistoryWindow(full=history, for_init=for_init)

    def _exercise_history(self, request: PlanRequest) -> History:
        exercise_id = request.exercise.exercise_id
        history = [sess for sess in request.user_state.history if sess.exercise_id == exercise_id]
        if history:
            return history
        if request.baseline_max is None:
            raise ValueError("No history available. Provide baseline_max or log a TEST session.")
        return [create_synthetic_test_session(request)]

    def _goal(self, request: PlanRequest) -> ProgressionGoal:
        target = request.user_state.profile.target_for_exercise(request.exercise.exercise_id)
        return ProgressionGoal.from_target(target, int(request.exercise.target_value))

    def _weeks(self, request: PlanRequest, state: TrainingState, goal: ProgressionGoal) -> int:
        horizon = self._horizon
        if request.weeks_ahead is None:
            estimated = self._progression.weeks_to_target(state.initial_tm, goal.reps)
            return max(horizon.MIN_PLAN_WEEKS, min(horizon.DEFAULT_PLAN_WEEKS, estimated))
        return max(horizon.MIN_PLAN_WEEKS, min(horizon.MAX_PLAN_WEEKS, request.weeks_ahead))

    def _grip_selector(self, window: HistoryWindow, request: PlanRequest) -> GripSelector:
        selector = GripSelector(request.exercise)
        selector.initialize_counts(window.effective_init)
        return selector
