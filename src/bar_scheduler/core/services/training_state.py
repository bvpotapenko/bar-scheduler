"""Initial training-state computation at plan-generation time.

Composes the fatigue model, plateau detector, and deload policy into a single
:class:`~bar_scheduler.domain.models.TrainingStatus` (and a baseline-adjusted
initial TM). Replaces the old ``adaptation.get_training_status`` +
``training_state_calculator.compute_training_state``.
"""

from bar_scheduler.core.math.compliance import weekly_compliance
from bar_scheduler.core.math.history_queries import latest_test_max
from bar_scheduler.core.math.training_max import training_max, training_max_from_baseline
from bar_scheduler.core.math.trend import trend_slope_per_week
from bar_scheduler.core.policies.fatigue import FitnessFatigueModel
from bar_scheduler.core.policies.plateau import DeloadPolicy, PlateauDetector
from bar_scheduler.core.services.plan_run import HistoryWindow
from bar_scheduler.domain.context import AthleteContext
from bar_scheduler.domain.models import FitnessFatigueState, SessionResult, TrainingStatus
from bar_scheduler.domain.results import TrainingState

History = list[SessionResult]


class TrainingStateCalculator:
    """Derive training status and the initial training max from history."""

    def __init__(
        self,
        fatigue: FitnessFatigueModel,
        plateau: PlateauDetector,
        deload: DeloadPolicy,
        trend_window_days: int,
    ) -> None:
        self._fatigue = fatigue
        self._plateau = plateau
        self._deload = deload
        self._trend_window = trend_window_days

    def status(
        self, history: History, bodyweight_kg: float, baseline_max: int | None = None
    ) -> TrainingStatus:
        """Full training status: TM, test max, trend, plateau, deload, fatigue."""
        ff_state = self._ff_state(history, bodyweight_kg, baseline_max)
        return TrainingStatus(
            training_max=self._tm(history, baseline_max),
            latest_test_max=self._test_max(history, baseline_max),
            trend_slope=trend_slope_per_week(history, self._trend_window),
            is_plateau=self._plateau.is_plateaued(history),
            deload_recommended=self._deload.should_deload(history, ff_state),
            compliance_ratio=weekly_compliance(history, weeks_back=1) if history else 1.0,
            fatigue_score=self._deload.fatigue_score(history, ff_state),
            fitness_fatigue_state=ff_state,
        )

    def compute(
        self, window: HistoryWindow, bodyweight_kg: float, baseline_max: int | None
    ) -> TrainingState:
        """Initial state from the pre-plan window, with a baseline TM fallback."""
        status = self.status(window.effective_init, bodyweight_kg, baseline_max)
        initial_tm = status.training_max
        if initial_tm <= 1 and baseline_max is not None:
            initial_tm = training_max_from_baseline(baseline_max)
        return TrainingState(status=status, initial_tm=initial_tm)

    def _ff_state(
        self, history: History, bodyweight_kg: float, baseline_max: int | None
    ) -> FitnessFatigueState:
        ctx = AthleteContext(reference_bodyweight_kg=bodyweight_kg)
        state, _ = self._fatigue.build(history, ctx, baseline_max)
        return state

    def _tm(self, history: History, baseline_max: int | None) -> int:
        tm = training_max(history)
        if tm == 1 and baseline_max is not None:
            return training_max_from_baseline(baseline_max)
        return tm

    def _test_max(self, history: History, baseline_max: int | None) -> int | None:
        test_max = latest_test_max(history)
        if test_max is None and baseline_max is not None:
            return baseline_max
        return test_max
