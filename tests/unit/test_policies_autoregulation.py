"""Unit tests for the AutoregulationPolicy."""

from bar_scheduler.config.planning_params import ReadinessConfig
from bar_scheduler.core.policies.autoregulation import AutoregulationPolicy
from bar_scheduler.domain.models import FitnessFatigueState

START = (4, 8)  # (sets, reps) before autoregulation


def test_autoreg_skipped_below_min_sessions():
    autoreg = AutoregulationPolicy(ReadinessConfig(), min_sessions=3)
    assert autoreg.adjust(START, FitnessFatigueState(), history_sessions=2) == START


def test_autoreg_reduces_sets_when_low_readiness():
    autoreg = AutoregulationPolicy(ReadinessConfig(), min_sessions=3)
    low = FitnessFatigueState(fitness=0.0, fatigue=5.0, readiness_mean=0.0, readiness_var=1.0)
    sets, reps = autoreg.adjust(START, low, history_sessions=10, sets_min=1)
    assert sets < 4 and reps == 8  # z very negative -> fewer sets, reps unchanged


def test_autoreg_adds_rep_when_high_readiness():
    autoreg = AutoregulationPolicy(ReadinessConfig(), min_sessions=3)
    high = FitnessFatigueState(fitness=5.0, fatigue=0.0, readiness_mean=0.0, readiness_var=1.0)
    assert autoreg.adjust(START, high, history_sessions=10) == (4, 9)
