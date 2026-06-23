"""Weight and assistance prescription (owns the Epley-inverse load formula).

Inverts a Leff 1RM estimate for the session's target reps:
    leff_target = leff_onerm * tm_factor / (1 + target_reps / 30)
added weight = leff_target - bodyweight_share; assistance = bodyweight_share - leff_target.
"""

from bar_scheduler.core.math.leff import (
    estimate_effective_leff_onerm,
    last_test_weight,
    resolve_leff_onerm,
)
from bar_scheduler.core.math.snapping import (
    apply_cap,
    ceiling_snap_assistance,
    expand_dual_dumbbell_totals,
    snap_added,
    snap_to_available,
)
from bar_scheduler.domain.context import PrescriptionContext

# Target reps per session type, used to invert the Epley formula.
DEFAULT_SESSION_TARGET_REPS: dict[str, int] = {"S": 5, "H": 8, "E": 12, "T": 6, "TEST": 1}


def _epley_invert(leff_onerm: float, target_reps: int, tm_factor: float) -> float:
    return leff_onerm * tm_factor / (1 + target_reps / 30)


def _carry_weight(ctx: PrescriptionContext) -> float:
    """Carry the last TEST weight forward (external_only with bodyweight share)."""
    last = last_test_weight(ctx.history, ctx.exercise)
    available = ctx.equipment.available_weights_kg
    if available and last > 0:
        snap_list = (
            expand_dual_dumbbell_totals(list(available))
            if ctx.exercise.dual_dumbbell
            else list(available)
        )
        return snap_to_available(last, snap_list)
    return last


def _added_external_zero_bw(
    ctx: PrescriptionContext, tm_factor: float, target: int
) -> float | None:
    """Purely external load (e.g. incline DB press); None falls through to carry."""
    if ctx.exercise.bw_fraction != 0.0:
        return None
    leff_onerm = estimate_effective_leff_onerm(ctx.history, 0.0)
    if not leff_onerm:
        return None
    leff_target = _epley_invert(leff_onerm, target, tm_factor)
    added = max(0.0, apply_cap(leff_target, ctx.exercise.max_added_weight_kg))
    return snap_added(added, ctx.equipment.available_weights_kg, ctx.exercise.dual_dumbbell)


def _added_bw_plus_external(ctx: PrescriptionContext, tm_factor: float, target: int) -> float:
    """Pull-up / dip: bodyweight share plus added weight above the TM threshold."""
    if ctx.training_max <= ctx.exercise.weight_tm_threshold:
        return 0.0
    bw_contrib = ctx.bodyweight_kg * ctx.exercise.bw_fraction
    leff_onerm = resolve_leff_onerm(
        ctx.history,
        ctx.exercise.bw_fraction,
        bw_contrib,
        ctx.training_max,
        bw_contrib,
    )
    leff_target = _epley_invert(leff_onerm, target, tm_factor)
    added = max(0.0, apply_cap(leff_target - bw_contrib, ctx.exercise.max_added_weight_kg))
    return snap_added(added, ctx.equipment.available_weights_kg, ctx.exercise.dual_dumbbell)


def _variable_assistance(
    ctx: PrescriptionContext,
    tm_factor: float,
    target: int,
    available: tuple[float, ...],
) -> float:
    """Machine/band assistance needed to bring effective load to the target."""
    if not available or ctx.training_max > ctx.exercise.weight_tm_threshold:
        return 0.0
    bw_contrib = ctx.bodyweight_kg * ctx.exercise.bw_fraction
    leff_onerm = resolve_leff_onerm(
        ctx.history,
        ctx.exercise.bw_fraction,
        bw_contrib,
        ctx.training_max,
        0.0,
    )
    needed = max(0.0, bw_contrib - _epley_invert(leff_onerm, target, tm_factor))
    if needed <= 0.0:
        return 0.0
    return ceiling_snap_assistance(needed, list(available))


class LoadCalculator:
    """Prescribes added weight and machine/band assistance for a session."""

    def __init__(self, tm_factor: float, session_target_reps: dict[str, int]) -> None:
        self._tm_factor = tm_factor
        self._targets = session_target_reps

    def _target(self, session_type: str) -> int:
        return self._targets.get(session_type, 8)

    def added_weight(self, ctx: PrescriptionContext) -> float:
        """Added weight for this session (0.0 below the weight threshold)."""
        target = self._target(ctx.session_type)
        if ctx.exercise.load_type == "external_only":
            zero_bw = _added_external_zero_bw(ctx, self._tm_factor, target)
            return _carry_weight(ctx) if zero_bw is None else zero_bw
        return _added_bw_plus_external(ctx, self._tm_factor, target)

    def machine_assistance(self, ctx: PrescriptionContext) -> float:
        """Machine assistance, ceiling-snapped to available levels (0.0 if none/weighted)."""
        target = self._target(ctx.session_type)
        return _variable_assistance(
            ctx, self._tm_factor, target, ctx.equipment.available_machine_assistance_kg
        )

    def band_assistance(self, ctx: PrescriptionContext) -> float:
        """Band assistance, ceiling-snapped to available bands (0.0 if none/weighted)."""
        target = self._target(ctx.session_type)
        return _variable_assistance(
            ctx, self._tm_factor, target, ctx.equipment.available_band_assistance_kg
        )

    def weight_at_reps(self, ctx: PrescriptionContext, at_reps: int) -> float:
        """Project the added weight that would be prescribed at ``at_reps`` (goal check)."""
        exercise = ctx.exercise
        if exercise.load_type == "external_only":
            return _carry_weight(ctx)
        bw_contrib = ctx.bodyweight_kg * exercise.bw_fraction
        leff_onerm = estimate_effective_leff_onerm(ctx.history, exercise.bw_fraction)
        if leff_onerm is None or leff_onerm <= bw_contrib:
            return 0.0
        leff_target = _epley_invert(leff_onerm, at_reps, self._tm_factor)
        added = max(0.0, apply_cap(leff_target - bw_contrib, exercise.max_added_weight_kg))
        return snap_added(added, ctx.equipment.available_weights_kg, exercise.dual_dumbbell)
