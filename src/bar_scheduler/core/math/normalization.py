"""Rep normalization: rest, bodyweight (via LoadSpec), and variant scaling."""

from bar_scheduler.core.config import (
    F_REST_MAX,
    F_REST_MIN,
    GAMMA_REST,
    REST_MIN_CLAMP,
    REST_REF_SECONDS,
)
from bar_scheduler.domain import LoadSpec


def rest_factor(rest_seconds: int) -> float:
    """F_rest(r) = clip((r/r_ref)^gamma, F_min, F_max). Short rest -> < 1."""
    rest_clamped = max(rest_seconds, REST_MIN_CLAMP)
    raw = (rest_clamped / REST_REF_SECONDS) ** GAMMA_REST
    return max(F_REST_MIN, min(F_REST_MAX, raw))


def effective_reps(actual_reps: int, rest_seconds: int) -> float:
    """Rest-normalized reps: reps / F_rest(rest)."""
    return actual_reps / rest_factor(rest_seconds)


def bodyweight_normalized_reps(reps: float, load: LoadSpec, reference_bodyweight_kg: float) -> float:
    """Scale reps by effective load relative to a reference bodyweight (linear)."""
    total_load = max(0.0, load.effective_kg)
    if reference_bodyweight_kg <= 0:
        return reps
    return reps * total_load / reference_bodyweight_kg


def grip_factor(grip: str, variant_factors: dict[str, float] | None = None) -> float:
    """Variant normalization factor (1.0 when unknown / not provided)."""
    if variant_factors is None:
        return 1.0
    return variant_factors.get(grip, 1.0)


def standardized_reps(
    actual_reps: int,
    rest_seconds: int,
    load: LoadSpec,
    reference_bodyweight_kg: float,
    variant_factor: float = 1.0,
) -> float:
    """Fully standardized reps = rest-normalized x bodyweight-normalized x variant."""
    rest_norm = effective_reps(actual_reps, rest_seconds)
    bw_norm = bodyweight_normalized_reps(rest_norm, load, reference_bodyweight_kg)
    return bw_norm * variant_factor
