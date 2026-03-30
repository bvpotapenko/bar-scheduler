"""External load computation for all weighted session types.

Uses a Leff-based 1RM estimation (Epley formula) to derive appropriate
added weight for each session type.  This replaces the old linear TM-point
formula which produced unrealistically small weights when first crossing
the weight threshold.

Epley 1RM:      1RM_Leff = Leff × (1 + reps / 30)
Inverse:        Leff_target = 1RM_Leff × TM_FACTOR / (1 + target_reps / 30)
Added weight:   added = Leff_target − BW × bw_fraction

Session target reps (used for Epley inverse):
    S  ->  5  reps  (~85 % 1RM)
    H  ->  8  reps  (~78 % 1RM)
    E  -> 12  reps  (~67 % 1RM)
    T  ->  6  reps  (~83 % 1RM)
"""

from ..config import TM_FACTOR
from ..exercises.base import ExerciseDefinition

# Target reps per session type — used to invert the Epley formula
_SESSION_TARGET_REPS: dict[str, int] = {
    "S": 5,
    "H": 8,
    "E": 12,
    "T": 6,
    "TEST": 1,
}


def _apply_rounding(raw: float) -> float:
    """Round to nearest 0.5 kg."""
    return round(raw * 2) / 2


def _apply_cap(value: float, max_kg: float) -> float:
    """Clamp added weight to the exercise maximum."""
    return min(value, max_kg)


def _expand_dual_dumbbell_totals(available: list[float]) -> list[float]:
    """Return all achievable totals for a dual-dumbbell exercise.

    Includes single-DB weights and all same/mixed pairs, since the user is
    assumed to own at least two of each dumbbell in their set. For example,
    [8, 10, 16] -> [8, 10, 16, 18, 20, 24, 26, 32].
    """
    totals: set[float] = set(available)
    for i, a in enumerate(available):
        for b in available[i:]:
            totals.add(a + b)
    return sorted(totals)


def _snap_to_available(weight_kg: float, available: list[float]) -> float:
    """Floor-snap weight_kg to the largest available weight ≤ weight_kg.

    If the prescription is below all available weights (e.g. a new user whose
    first session starts lighter than the smallest dumbbell), return the
    smallest available weight so they always train with real equipment.

    Args:
        weight_kg: The ideally computed weight.
        available: Sorted or unsorted list of available weights (e.g. [2, 4, ..., 32]).

    Returns:
        The snapped weight from the available list.
    """
    below = [w for w in available if w <= weight_kg]
    return max(below) if below else min(available)


def _last_test_weight_bss(history: list, exercise: ExerciseDefinition) -> float:
    """
    Return the dumbbell weight from the most recent TEST session.

    Used for external_only exercises (BSS) where the prescribed load
    is carried forward from the last test.
    """
    test_hist = [
        s
        for s in history
        if s.session_type == "TEST" and s.exercise_id == exercise.exercise_id
    ]
    if not test_hist or not test_hist[-1].completed_sets:
        return 0.0
    weights = [
        s.added_weight_kg for s in test_hist[-1].completed_sets if s.added_weight_kg > 0
    ]
    return weights[-1] if weights else 0.0


def _estimate_effective_leff_1rm(history: list, bw_fraction: float) -> float | None:
    """
    Estimate Leff 1RM from all available historical sessions using Epley.

    1RM_Leff = Leff × (1 + reps / 30)

    Considers every recorded set across all session types — weighted sets
    naturally yield a more accurate 1RM than bodyweight-only sets because the
    heavier Leff pulls the estimate up.

    Returns:
        Maximum 1RM estimate found, or None if history is empty.
    """
    candidates: list[float] = []
    for session in history:
        assistance = (
            session.equipment_snapshot.assistance_kg
            if session.equipment_snapshot is not None
            else 0.0
        )
        for s in session.completed_sets:
            if not s.actual_reps or s.actual_reps < 1:
                continue
            leff = (
                session.bodyweight_kg * bw_fraction
                + (s.added_weight_kg or 0.0)
                - assistance
            )
            if leff > 0:
                candidates.append(leff * (1 + s.actual_reps / 30))
    return max(candidates) if candidates else None


def _calculate_added_weight(
    exercise: ExerciseDefinition,
    training_max: int,
    bodyweight_kg: float,
    history: list,
    session_type: str,
    available_weights_kg: list[float] | None = None,
) -> float:
    """
    Calculate added weight for a session.

    For external_only exercises with bw_fraction=0 (e.g. incline_db_press):
        Use Leff 1RM estimated from all historical sets via Epley, then invert
        for the session's target reps.  This lets the prescription adapt to
        performance from any session type, not only TEST sessions.

    For external_only exercises with bw_fraction>0 (e.g. BSS):
        Carry forward the weight from the last TEST session.

    For bw_plus_external exercises (pull_up, dip) when TM > threshold:
        1. Estimate Leff 1RM from all historical sets via Epley.
        2. If no usable history, fall back to a conservative TM-derived estimate.
        3. Invert Epley for the session's target reps to get the prescribed Leff.
        4. Subtract bw_contrib to get added weight; round to 0.5 kg; cap at max.

    When TM ≤ weight_tm_threshold: return 0.0 (bodyweight-only phase).

    When ``available_weights_kg`` is non-empty the result is floor-snapped to
    the largest available weight ≤ the computed ideal (instead of 0.5 kg rounding).

    Args:
        exercise: Exercise definition.
        training_max: Current training max (reps).
        bodyweight_kg: User's current bodyweight.
        history: Full exercise history for 1RM estimation.
        session_type: Session type string ("S", "H", "E", "T", "TEST").
        available_weights_kg: Discrete weights the user owns; empty = continuous.

    Returns:
        Added weight in kg (≥ 0, snapped or rounded to available increment).
    """
    if exercise.load_type == "external_only":
        if exercise.bw_fraction == 0.0:
            # Purely external load (e.g. incline_db_press): derive weight from
            # the best Leff 1RM seen across all history, not just TEST sessions.
            leff_1rm_hist = _estimate_effective_leff_1rm(history, 0.0)
            if leff_1rm_hist:
                target_reps = _SESSION_TARGET_REPS.get(session_type, 8)
                leff_target = leff_1rm_hist * TM_FACTOR / (1 + target_reps / 30)
                added = max(0.0, _apply_cap(leff_target, exercise.max_added_weight_kg))
                if available_weights_kg:
                    snap_list = (
                        _expand_dual_dumbbell_totals(available_weights_kg)
                        if exercise.dual_dumbbell
                        else available_weights_kg
                    )
                    return _snap_to_available(added, snap_list)
                return _apply_rounding(added)
        # BSS or no history: carry forward last TEST weight
        w = _last_test_weight_bss(history, exercise)
        if available_weights_kg and w > 0:
            snap_list = (
                _expand_dual_dumbbell_totals(available_weights_kg)
                if exercise.dual_dumbbell
                else available_weights_kg
            )
            w = _snap_to_available(w, snap_list)
        return w

    if training_max <= exercise.weight_tm_threshold:
        return 0.0

    bw_contrib = bodyweight_kg * exercise.bw_fraction
    leff_1rm_hist = _estimate_effective_leff_1rm(history, exercise.bw_fraction)
    # TM-derived estimate grows with TM, driving plan weight progression.
    # training_max ≈ TM_FACTOR × test_max_reps, so test_max ≈ TM / TM_FACTOR.
    leff_1rm_tm = bw_contrib * (1 + training_max / (TM_FACTOR * 30))

    if leff_1rm_hist is None or leff_1rm_hist <= bw_contrib:
        leff_1rm = leff_1rm_tm
    else:
        # Take max: history wins early (accurate current baseline); TM-derived
        # takes over as the plan projects forward and TM grows beyond baseline.
        leff_1rm = max(leff_1rm_hist, leff_1rm_tm)

    target_reps = _SESSION_TARGET_REPS.get(session_type, 8)
    leff_target = leff_1rm * TM_FACTOR / (1 + target_reps / 30)
    added = leff_target - bw_contrib
    added = max(0.0, _apply_cap(added, exercise.max_added_weight_kg))

    if available_weights_kg:
        return _snap_to_available(added, available_weights_kg)
    return _apply_rounding(added)


def _ceiling_snap_assistance(assistance_kg: float, available: list[float]) -> float:
    """Ceiling-snap assistance to the smallest available value ≥ assistance_kg.

    If all available values are below the ideal (user can't provide enough
    assistance), return the maximum available as the best approximation.
    """
    above = [a for a in available if a >= assistance_kg]
    return min(above) if above else max(available)


def calculate_machine_assistance(
    exercise: ExerciseDefinition,
    training_max: int,
    bodyweight_kg: float,
    history: list,
    session_type: str,
    available_machine_assistance_kg: list[float],
) -> float:
    """
    Calculate the machine assistance to prescribe for a session.

    Mirrors _calculate_added_weight but for the assistive side: when the
    target Leff is below the bodyweight contribution the user needs external
    assistance.  The result is ceiling-snapped to the available list (smallest
    available ≥ ideal) so the session remains achievable.

    Returns 0.0 when:
    - ``available_machine_assistance_kg`` is empty, or
    - TM > ``exercise.weight_tm_threshold`` (user is in the weighted phase), or
    - the computed target Leff already ≥ bw_contribution (no assistance needed).

    Args:
        exercise: Exercise definition.
        training_max: Current training max (reps).
        bodyweight_kg: User's current bodyweight.
        history: Full exercise history for 1RM estimation.
        session_type: Session type string ("S", "H", "E", "T", "TEST").
        available_machine_assistance_kg: Discrete assistance levels the user can set.

    Returns:
        Assistance in kg (≥ 0, ceiling-snapped to available list).
    """
    if not available_machine_assistance_kg:
        return 0.0

    if training_max > exercise.weight_tm_threshold:
        return 0.0

    bw_contrib = bodyweight_kg * exercise.bw_fraction
    leff_1rm_hist = _estimate_effective_leff_1rm(history, exercise.bw_fraction)
    leff_1rm_tm = bw_contrib * (1 + training_max / (TM_FACTOR * 30))

    if leff_1rm_hist is None or leff_1rm_hist <= 0:
        leff_1rm = leff_1rm_tm
    else:
        leff_1rm = max(leff_1rm_hist, leff_1rm_tm)

    target_reps = _SESSION_TARGET_REPS.get(session_type, 8)
    leff_target = leff_1rm * TM_FACTOR / (1 + target_reps / 30)

    needed = max(0.0, bw_contrib - leff_target)
    if needed <= 0.0:
        return 0.0

    return _ceiling_snap_assistance(needed, available_machine_assistance_kg)


def estimate_prescription_weight(
    history: list,
    exercise: ExerciseDefinition,
    bodyweight_kg: float,
    at_reps: int,
    available_weights_kg: list[float] | None = None,
) -> float:
    """
    Estimate the added weight prescription the planner would assign for `at_reps`.

    Uses the current Leff 1RM derived from history (same Epley formula as
    _calculate_added_weight) to project what weight would be prescribed if
    the session targeted `at_reps`. Returns 0.0 when no usable history exists.

    Used by plan_engine to evaluate whether a weighted goal has been reached.

    Args:
        history: Full exercise history for 1RM estimation.
        exercise: Exercise definition.
        bodyweight_kg: User's current bodyweight.
        at_reps: The rep target to project weight for (e.g. goal reps).
        available_weights_kg: Discrete weights the user owns; empty = continuous.

    Returns:
        Projected added weight in kg (≥ 0, snapped or rounded to available increment).
    """
    if exercise.load_type == "external_only":
        w = _last_test_weight_bss(history, exercise)
        if available_weights_kg and w > 0:
            snap_list = (
                _expand_dual_dumbbell_totals(available_weights_kg)
                if exercise.dual_dumbbell
                else available_weights_kg
            )
            w = _snap_to_available(w, snap_list)
        return w

    bw_contrib = bodyweight_kg * exercise.bw_fraction
    leff_1rm = _estimate_effective_leff_1rm(history, exercise.bw_fraction)

    if leff_1rm is None or leff_1rm <= bw_contrib:
        return 0.0  # Not enough history to project

    leff_target = leff_1rm * TM_FACTOR / (1 + at_reps / 30)
    added = leff_target - bw_contrib
    added = max(0.0, _apply_cap(added, exercise.max_added_weight_kg))

    if available_weights_kg:
        return _snap_to_available(added, available_weights_kg)
    return _apply_rounding(added)
