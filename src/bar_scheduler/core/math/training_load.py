"""Per-session training-load impulse (w(t)) for the fitness-fatigue model.

w(t) = sum over sets of  hard_reps * load_stress * variant_stress.
Rest stress is intentionally excluded (short rest is already credited via
rest-normalized effective reps; including it would double-count fatigue).
"""

from bar_scheduler.config.model_params import TrainingLoadConfig
from bar_scheduler.core.math.effort import estimate_rir_from_fraction
from bar_scheduler.domain.context import AthleteContext, LoadSpec
from bar_scheduler.domain.models import SessionResult, SetResult


def rir_effort_multiplier(rir: int, a_rir: float) -> float:
    """E_rir = clip(1 + a*(3 - rir), 0.5, ...); lower RIR -> more fatigue."""
    return max(0.5, 1.0 + a_rir * (3 - rir))


def load_stress_multiplier(load: LoadSpec, reference_bodyweight_kg: float, gamma_load: float) -> float:
    """S_load = (Leff / BW_ref) ^ gamma_load."""
    total = max(0.0, load.effective_kg)
    return (total / reference_bodyweight_kg) ** gamma_load


def grip_stress_multiplier(grip: str, variant_factors: dict[str, float] | None) -> float:
    """Per-variant stress factor (1.0 when not provided)."""
    if variant_factors is None:
        return 1.0
    return variant_factors.get(grip, 1.0)


def set_hard_reps(reps: int, rir: int | None, estimated_max: int, a_rir: float) -> float:
    """Effective hard reps for a set: reps * effort(rir)."""
    if rir is None:
        rir = estimate_rir_from_fraction(reps, estimated_max)
    return reps * rir_effort_multiplier(rir, a_rir)


def _set_load(
    session: SessionResult,
    sr: SetResult,
    estimated_max: int,
    ctx: AthleteContext,
    cfg: TrainingLoadConfig,
) -> float:
    snap = session.equipment_snapshot
    spec = LoadSpec(
        bodyweight_kg=session.bodyweight_kg,
        bw_fraction=ctx.bw_fraction,
        added_load_kg=sr.added_weight_kg,
        assistance_kg=snap.assistance_kg if snap is not None else 0.0,
    )
    hard = set_hard_reps(sr.actual_reps, sr.rir_reported, estimated_max, cfg.A_RIR)
    s_load = load_stress_multiplier(spec, ctx.reference_bodyweight_kg, cfg.GAMMA_LOAD)
    return hard * s_load * grip_stress_multiplier(session.grip, ctx.variant_factors)


def session_training_load(
    session: SessionResult,
    estimated_max: int,
    ctx: AthleteContext,
    cfg: TrainingLoadConfig,
) -> float:
    """Total training-load impulse for a completed session."""
    total = 0.0
    for sr in session.completed_sets:
        if sr.actual_reps is not None:
            total += _set_load(session, sr, estimated_max, ctx, cfg)
    return total
