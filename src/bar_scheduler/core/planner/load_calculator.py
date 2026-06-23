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

from bar_scheduler.core.config import TM_FACTOR
from bar_scheduler.core.exercises.base import ExerciseDefinition
from bar_scheduler.core.metrics import best_onerm_from_leff

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


def _apply_cap(load_kg: float, max_kg: float) -> float:
    """Clamp added weight to the exercise maximum."""
    return min(load_kg, max_kg)


def _expand_dual_dumbbell_totals(available: list[float]) -> list[float]:
    """Return all achievable totals for a dual-dumbbell exercise.

    Includes single-DB weights and all same/mixed pairs, since the user is
    assumed to own at least two of each dumbbell in their set. For example,
    [8, 10, 16] -> [8, 10, 16, 18, 20, 24, 26, 32].
    """
    totals: set[float] = set(available)
    for idx, weight_a in enumerate(available):
        for weight_b in available[idx:]:
            totals.add(weight_a + weight_b)
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
    below = [wt for wt in available if wt <= weight_kg]
    return max(below) if below else min(available)


def _last_test_weight_bss(history: list, exercise: ExerciseDefinition) -> float:
    """
    Return the dumbbell weight from the most recent TEST session.

    Used for external_only exercises (BSS) where the prescribed load
    is carried forward from the last test.
    """
    test_hist = [
        sess
        for sess in history
        if sess.session_type == "TEST" and sess.exercise_id == exercise.exercise_id
    ]
    if not test_hist or not test_hist[-1].completed_sets:
        return 0.0
    weights = [
        sess_set.added_weight_kg
        for sess_set in test_hist[-1].completed_sets
        if sess_set.added_weight_kg > 0
    ]
    return weights[-1] if weights else 0.0


def _estimate_effective_leff_onerm(history: list, bw_fraction: float) -> float | None:
    """
    Estimate Leff 1RM from all available historical sessions.

    Uses a rep-range-aware formula blend (Brzycki/Lander for low reps,
    Lombardi/Epley for high reps) so the estimate does not plateau for
    athletes with high bodyweight rep capacity (TM > 12).

    Considers every recorded set across all session types — weighted sets
    naturally yield a more accurate 1RM than bodyweight-only sets because the
    heavier Leff pulls the estimate up.

    Returns:
        Maximum 1RM estimate found, or None if history is empty.
    """
    candidates: list[float] = []
    for session in history:
        assistance = session.equipment_snapshot.assistance_kg if session.equipment_snapshot else 0.0
        for set_rec in session.completed_sets:
            if not set_rec.actual_reps or set_rec.actual_reps < 1:
                continue
            leff = (
                session.bodyweight_kg * bw_fraction + (set_rec.added_weight_kg or 0.0) - assistance
            )
            if leff > 0:
                estimate = best_onerm_from_leff(leff, set_rec.actual_reps)
                if estimate is not None:
                    candidates.append(estimate)
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
            leff_onerm_hist = _estimate_effective_leff_onerm(history, 0.0)
            if leff_onerm_hist:
                target_reps = _SESSION_TARGET_REPS.get(session_type, 8)
                leff_target = leff_onerm_hist * TM_FACTOR / (1 + target_reps / 30)
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
        last_wt = _last_test_weight_bss(history, exercise)
        if available_weights_kg and last_wt > 0:
            snap_list = (
                _expand_dual_dumbbell_totals(available_weights_kg)
                if exercise.dual_dumbbell
                else available_weights_kg
            )
            last_wt = _snap_to_available(last_wt, snap_list)
        return last_wt

    if training_max <= exercise.weight_tm_threshold:
        return 0.0

    bw_contrib = bodyweight_kg * exercise.bw_fraction
    leff_onerm_hist = _estimate_effective_leff_onerm(history, exercise.bw_fraction)
    # TM-derived fallback: estimate 1RM from bodyweight-only reps equal to TM.
    # Uses rep-range-aware blend so the estimate grows correctly beyond TM=12.
    leff_onerm_tm = best_onerm_from_leff(bw_contrib, training_max) or bw_contrib

    if leff_onerm_hist is None or leff_onerm_hist <= bw_contrib:
        leff_onerm = leff_onerm_tm
    else:
        # Take max: history wins early (accurate current baseline); TM-derived
        # takes over as the plan projects forward and TM grows beyond baseline.
        leff_onerm = max(leff_onerm_hist, leff_onerm_tm)

    target_reps = _SESSION_TARGET_REPS.get(session_type, 8)
    leff_target = leff_onerm * TM_FACTOR / (1 + target_reps / 30)
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
    above = [avail for avail in available if avail >= assistance_kg]
    return min(above) if above else max(available)


def _calculate_variable_assistance(
    exercise: ExerciseDefinition,
    training_max: int,
    bodyweight_kg: float,
    history: list,
    session_type: str,
    available_kg: list[float],
) -> float:
    """Shared logic for machine and band assistance calculation."""
    if not available_kg:
        return 0.0

    if training_max > exercise.weight_tm_threshold:
        return 0.0

    bw_contrib = bodyweight_kg * exercise.bw_fraction
    leff_onerm_hist = _estimate_effective_leff_onerm(history, exercise.bw_fraction)
    leff_onerm_tm = best_onerm_from_leff(bw_contrib, training_max) or bw_contrib

    if leff_onerm_hist is None or leff_onerm_hist <= 0:
        leff_onerm = leff_onerm_tm
    else:
        leff_onerm = max(leff_onerm_hist, leff_onerm_tm)

    target_reps = _SESSION_TARGET_REPS.get(session_type, 8)
    leff_target = leff_onerm * TM_FACTOR / (1 + target_reps / 30)

    needed = max(0.0, bw_contrib - leff_target)
    if needed <= 0.0:
        return 0.0

    return _ceiling_snap_assistance(needed, available_kg)


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

    The result is ceiling-snapped to the available list (smallest available ≥ ideal).
    Returns 0.0 when the list is empty, TM is in the weighted phase, or no assistance
    is needed.
    """
    return _calculate_variable_assistance(
        exercise,
        training_max,
        bodyweight_kg,
        history,
        session_type,
        available_machine_assistance_kg,
    )


def calculate_band_assistance(
    exercise: ExerciseDefinition,
    training_max: int,
    bodyweight_kg: float,
    history: list,
    session_type: str,
    available_band_assistance_kg: list[float],
) -> float:
    """
    Calculate the band assistance to prescribe for a session.

    Identical logic to ``calculate_machine_assistance`` but operates on the
    user's declared band resistance values.  The result is ceiling-snapped to
    the smallest available band ≥ the computed ideal.
    Returns 0.0 when the list is empty, TM is in the weighted phase, or no
    assistance is needed.
    """
    return _calculate_variable_assistance(
        exercise,
        training_max,
        bodyweight_kg,
        history,
        session_type,
        available_band_assistance_kg,
    )


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
        last_wt = _last_test_weight_bss(history, exercise)
        if available_weights_kg and last_wt > 0:
            snap_list = (
                _expand_dual_dumbbell_totals(available_weights_kg)
                if exercise.dual_dumbbell
                else available_weights_kg
            )
            last_wt = _snap_to_available(last_wt, snap_list)
        return last_wt

    bw_contrib = bodyweight_kg * exercise.bw_fraction
    leff_onerm = _estimate_effective_leff_onerm(history, exercise.bw_fraction)

    if leff_onerm is None or leff_onerm <= bw_contrib:
        return 0.0  # Not enough history to project

    leff_target = leff_onerm * TM_FACTOR / (1 + at_reps / 30)
    added = leff_target - bw_contrib
    added = max(0.0, _apply_cap(added, exercise.max_added_weight_kg))

    if available_weights_kg:
        return _snap_to_available(added, available_weights_kg)
    return _apply_rounding(added)
