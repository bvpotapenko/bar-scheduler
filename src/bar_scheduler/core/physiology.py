"""Transitional facade for the fitness-fatigue model.

The model now lives in :mod:`bar_scheduler.core.policies.fatigue`. These
functions wrap a default-configured FitnessFatigueModel so existing callers
(adaptation) keep working until they are rewired to the injected policy.
"""

from bar_scheduler.config import load_model_config
from bar_scheduler.core.policies.fatigue import BuildResult, FitnessFatigueModel
from bar_scheduler.domain.context import AthleteContext
from bar_scheduler.domain.models import SessionResult

_cfg = load_model_config()
_MODEL = FitnessFatigueModel(_cfg.fitness_fatigue, _cfg.training_load, _cfg.ewma_max)


def build_fitness_fatigue_state(
    history: list[SessionResult],
    reference_bodyweight_kg: float,
    baseline_max: int | None = None,
    bw_fraction: float = 1.0,
    variant_factors: dict[str, float] | None = None,
) -> BuildResult:
    """Build (FitnessFatigueState, session_loads) from history."""
    ctx = AthleteContext(reference_bodyweight_kg, bw_fraction, variant_factors)
    return _MODEL.build(history, ctx, baseline_max)


def predicted_max_with_readiness(base_max: float, readiness: float, mean_readiness: float) -> float:
    """Adjust a base max prediction by readiness deviation."""
    return _MODEL.predicted_max(base_max, readiness, mean_readiness)
