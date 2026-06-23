"""Fitness-fatigue impulse-response model (two-timescale Banister family).

Replaces physiology.build_fitness_fatigue_state with a config-injected model:
    G(t) = G(t-1)*e^(-d/tau_G) + k_G*w(t)   (fitness, slow decay)
    H(t) = H(t-1)*e^(-d/tau_H) + k_H*w(t)   (fatigue, fast decay)
    R(t) = G(t) - H(t)                       (readiness)
"""

import math
from dataclasses import replace
from datetime import datetime

from bar_scheduler.config.model_params import (
    EwmaMaxConfig,
    FitnessFatigueConfig,
    TrainingLoadConfig,
)
from bar_scheduler.core.math.history_queries import get_test_sessions, session_max_reps
from bar_scheduler.core.math.training_load import session_training_load
from bar_scheduler.domain.context import AthleteContext
from bar_scheduler.domain.models import FitnessFatigueState, SessionResult

BuildResult = tuple[FitnessFatigueState, list[tuple[str, float]]]
_READINESS_SMOOTHING = 0.1
_INITIAL_READINESS_VAR = 10.0  # wide, to avoid extreme early z-scores


def _ewma(prev: float, sample: float, alpha: float) -> float:
    """Exponentially-weighted moving average update."""
    return (1 - alpha) * prev + alpha * sample


def _decay_impulse(prev: float, tau: float, gain: float, load: float) -> float:
    """One-day decay of ``prev`` plus a training impulse: prev*e^(-1/tau) + gain*load."""
    return prev * math.exp(-1 / tau) + gain * load


def _initial_state(
    history: list[SessionResult],
    baseline_max: int | None,
    ewma: EwmaMaxConfig,
) -> FitnessFatigueState:
    tests = get_test_sessions(history)
    initial = session_max_reps(tests[0]) if tests else (baseline_max or 10)
    return FitnessFatigueState(
        m_hat=float(initial),
        sigma_m=ewma.INITIAL_SIGMA_M,
        readiness_mean=0.0,
        readiness_var=_INITIAL_READINESS_VAR,
    )


def _decayed(state: FitnessFatigueState, days: int, ff: FitnessFatigueConfig) -> FitnessFatigueState:
    fitness = state.fitness * math.exp(-days / ff.TAU_FITNESS)
    fatigue = state.fatigue * math.exp(-days / ff.TAU_FATIGUE)
    return replace(state, fitness=fitness, fatigue=fatigue)


def _updated(state: FitnessFatigueState, load: float, ff: FitnessFatigueConfig) -> FitnessFatigueState:
    new_fit = _decay_impulse(state.fitness, ff.TAU_FITNESS, ff.K_FITNESS, load)
    new_fat = _decay_impulse(state.fatigue, ff.TAU_FATIGUE, ff.K_FATIGUE, load)
    readiness = new_fit - new_fat
    mean = _ewma(state.readiness_mean, readiness, _READINESS_SMOOTHING)
    var = _ewma(state.readiness_var, (readiness - mean) ** 2, _READINESS_SMOOTHING)
    return replace(state, fitness=new_fit, fatigue=new_fat, readiness_mean=mean, readiness_var=var)


def _with_max(state: FitnessFatigueState, observed: int, ewma: EwmaMaxConfig) -> FitnessFatigueState:
    residual_sq = (observed - state.m_hat) ** 2
    new_m_hat = _ewma(state.m_hat, observed, ewma.ALPHA_MHAT)
    new_var = _ewma(state.sigma_m**2, residual_sq, ewma.BETA_SIGMA)
    return replace(state, m_hat=new_m_hat, sigma_m=math.sqrt(max(0.01, new_var)))


class FitnessFatigueModel:
    """Build fitness-fatigue state from history; predict readiness-adjusted max."""

    def __init__(
        self,
        ff: FitnessFatigueConfig,
        load: TrainingLoadConfig,
        ewma: EwmaMaxConfig,
    ) -> None:
        self._ff = ff
        self._load = load
        self._ewma = ewma

    def build(
        self,
        history: list[SessionResult],
        ctx: AthleteContext,
        baseline_max: int | None = None,
    ) -> BuildResult:
        """Process history chronologically into (state, per-session loads)."""
        state = _initial_state(history, baseline_max, self._ewma)
        loads: list[tuple[str, float]] = []
        prev_date: datetime | None = None
        for session in history:
            state, load = self._advance(state, session, prev_date, ctx)
            loads.append((session.date, load))
            prev_date = datetime.strptime(session.date, "%Y-%m-%d")
        return state, loads

    def _advance(
        self,
        state: FitnessFatigueState,
        session: SessionResult,
        prev_date: datetime | None,
        ctx: AthleteContext,
    ) -> tuple[FitnessFatigueState, float]:
        curr = datetime.strptime(session.date, "%Y-%m-%d")
        days_since = 1 if prev_date is None else (curr - prev_date).days
        if days_since > 1:
            state = _decayed(state, days_since - 1, self._ff)
        load = session_training_load(session, int(state.m_hat), ctx, self._load)
        state = _updated(state, load, self._ff)
        if session.session_type == "TEST":
            state = self._apply_test(state, session)
        return state, load

    def _apply_test(self, state: FitnessFatigueState, session: SessionResult) -> FitnessFatigueState:
        observed = session_max_reps(session)
        return _with_max(state, observed, self._ewma) if observed > 0 else state

    def predicted_max(self, base_max: float, readiness: float, mean_readiness: float) -> float:
        """M_pred = M_base * (1 + c_R * (R - R_bar))."""
        return base_max * (1 + self._ff.C_READINESS * (readiness - mean_readiness))
