"""Within-plan volume autoregulation from readiness z-score."""

from bar_scheduler.config.planning_params import ReadinessConfig
from bar_scheduler.domain.models import FitnessFatigueState

Volume = tuple[int, int]  # (sets, reps)


class AutoregulationPolicy:
    """Adjust planned (sets, reps) by readiness, once enough history exists."""

    def __init__(self, cfg: ReadinessConfig, min_sessions: int) -> None:
        self._cfg = cfg
        self._min_sessions = min_sessions

    def adjust(
        self,
        base: Volume,
        ff_state: FitnessFatigueState,
        history_sessions: int,
        sets_min: int = 1,
    ) -> Volume:
        """Reduce sets when readiness is low, add a rep when high, else unchanged."""
        if history_sessions < self._min_sessions:
            return base
        base_sets, base_reps = base
        z_score = ff_state.readiness_z_score()
        if z_score < self._cfg.READINESS_Z_LOW:
            reduced = int(base_sets * (1 - self._cfg.READINESS_VOLUME_REDUCTION))
            return (max(sets_min, reduced), base_reps)
        if z_score > self._cfg.READINESS_Z_HIGH:
            return (base_sets, base_reps + 1)
        return base
