"""Training-max progression toward the athlete's goal (difficulty curve)."""

from bar_scheduler.config.planning_params import ProgressionConfig
from bar_scheduler.core.policies.load import LoadCalculator
from bar_scheduler.domain.context import PrescriptionContext, ProgressionGoal

_MAX_PROJECTION_WEEKS = 208  # safety cap for weeks-to-target iteration


class ProgressionPolicy:
    """How fast TM grows per week, slowing toward the goal (edit here to retune)."""

    def __init__(self, cfg: ProgressionConfig, load: LoadCalculator) -> None:
        self._cfg = cfg
        self._load = load

    def reps_per_week(self, training_max: int, target: int) -> float:
        """Expected reps gained per week; slows non-linearly toward target."""
        if training_max >= target:
            return 0.0
        fraction_to_goal = 1 - training_max / target
        span = self._cfg.DELTA_PROGRESSION_MAX - self._cfg.DELTA_PROGRESSION_MIN
        return self._cfg.DELTA_PROGRESSION_MIN + span * fraction_to_goal**self._cfg.ETA_PROGRESSION

    def weeks_to_target(self, current_max: int, target: int) -> int:
        """Estimate weeks to reach target by iterating the weekly rate."""
        if current_max >= target:
            return 0
        projected = float(current_max)
        weeks = 0
        while projected < target and weeks < _MAX_PROJECTION_WEEKS:
            rate = self.reps_per_week(int(projected), target)
            if rate <= 0:
                break
            projected += rate
            weeks += 1
        return min(weeks, _MAX_PROJECTION_WEEKS)

    def weekly_delta(
        self, tm_float: float, goal: ProgressionGoal, ctx: PrescriptionContext
    ) -> float:
        """TM reps to add this week. Weighted goals keep growing TM until both met."""
        training_max = int(tm_float)
        if not goal.is_weighted:
            return self.reps_per_week(training_max, goal.reps)
        current_weight = self._load.weight_at_reps(ctx, goal.reps)
        if training_max >= goal.reps and current_weight >= goal.weight_kg:
            return 0.0
        return max(self._cfg.DELTA_PROGRESSION_MIN, self.reps_per_week(training_max, goal.reps))
