"""Plateau detection and deload triggers (edit here to retune when to back off)."""

from datetime import datetime, timedelta

from bar_scheduler.config.planning_params import PlateauConfig
from bar_scheduler.core.math.compliance import weekly_compliance
from bar_scheduler.core.math.history_queries import (
    get_test_sessions,
    overall_max_reps,
    session_max_reps,
)
from bar_scheduler.core.math.trend import trend_slope_per_week
from bar_scheduler.core.policies.fatigue import FitnessFatigueModel
from bar_scheduler.domain.models import FitnessFatigueState, SessionResult

_UNDERPERFORMANCE_SESSIONS = 2


def _parse(session: SessionResult) -> datetime:
    return datetime.strptime(session.date, "%Y-%m-%d")


def _new_best_in_window(
    history: list[SessionResult], tests: list[SessionResult], window_days: int
) -> bool:
    """True if a TEST within the window matched or beat the all-time best."""
    cutoff = _parse(tests[-1]) - timedelta(days=window_days)
    best_ever = overall_max_reps(history)
    recent = [sess for sess in tests if _parse(sess) >= cutoff]
    return any(session_max_reps(sess) >= best_ever for sess in recent)


class PlateauDetector:
    """Plateau = flat trend AND no new best within the window."""

    def __init__(self, cfg: PlateauConfig) -> None:
        self._cfg = cfg

    def is_plateaued(self, history: list[SessionResult]) -> bool:
        tests = get_test_sessions(history)
        if len(tests) < 2:
            return False
        slope = trend_slope_per_week(history, self._cfg.TREND_WINDOW_DAYS)
        if slope >= self._cfg.PLATEAU_SLOPE_THRESHOLD:
            return False
        return not _new_best_in_window(history, tests, self._cfg.PLATEAU_WINDOW_DAYS)


class DeloadPolicy:
    """Recommend a deload from plateau+fatigue, underperformance, or low compliance."""

    def __init__(
        self, cfg: PlateauConfig, plateau: PlateauDetector, fatigue: FitnessFatigueModel
    ) -> None:
        self._cfg = cfg
        self._plateau = plateau
        self._fatigue = fatigue

    def should_deload(self, history: list[SessionResult], ff_state: FitnessFatigueState) -> bool:
        if not history:
            return False
        fatigued = ff_state.readiness_z_score() < self._cfg.FATIGUE_Z_THRESHOLD
        if self._plateau.is_plateaued(history) and fatigued:
            return True
        if self._underperforming(history, ff_state):
            return True
        return weekly_compliance(history, weeks_back=1) < self._cfg.COMPLIANCE_THRESHOLD

    def fatigue_score(self, history: list[SessionResult], ff_state: FitnessFatigueState) -> float:
        """Relative gap between actual and readiness-adjusted predicted max (<0 = under)."""
        tests = get_test_sessions(history)
        if not tests:
            return 0.0
        predicted = self._predicted(ff_state)
        if predicted == 0:
            return 0.0
        return (session_max_reps(tests[-1]) - predicted) / predicted

    def _predicted(self, ff_state: FitnessFatigueState) -> float:
        return self._fatigue.predicted_max(
            ff_state.m_hat, ff_state.readiness(), ff_state.readiness_mean
        )

    def _underperforming(self, history: list[SessionResult], ff_state: FitnessFatigueState) -> bool:
        strength = [sess for sess in history if sess.session_type == "S"]
        if len(strength) < _UNDERPERFORMANCE_SESSIONS:
            return False
        threshold = self._predicted(ff_state) * (1 - self._cfg.UNDERPERFORMANCE_THRESHOLD)
        recent = strength[-_UNDERPERFORMANCE_SESSIONS:]
        return all(session_max_reps(sess) < threshold for sess in recent)
