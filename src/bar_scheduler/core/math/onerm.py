"""1RM estimation from session history (best-set selection + formula report)."""

from bar_scheduler.core.math.formulas import (
    blended_onerm_added,
    brzycki_onerm,
    epley_onerm,
    lander_onerm,
    lombardi_onerm,
)
from bar_scheduler.domain.models import SessionResult, SetResult

# Best 1RM as (epley_estimate, session, set, effective_load_kg).
_BestSet = tuple[float, SessionResult, SetResult, float]


def _session_assistance(session: SessionResult) -> float:
    """Assistance kg recorded on the session's equipment snapshot (0.0 if none)."""
    snap = session.equipment_snapshot
    return snap.assistance_kg if snap is not None else 0.0


def _recommended_formula(reps: int) -> str:
    """Name of the most accurate 1RM formula for the given rep count."""
    if reps <= 10:
        return "brzycki+lander"
    if reps <= 20:
        return "blended"
    return "epley (unreliable above 20 reps)"


def _usable_eff_load(exercise, bodyweight_kg: float, assistance_kg: float, sr: SetResult) -> float | None:
    """Effective load for a set, or None if it cannot seed a 1RM estimate."""
    if sr.actual_reps is None or sr.actual_reps <= 0:
        return None
    if exercise.load_type == "external_only" and sr.added_weight_kg <= 0:
        return None
    eff_load = bodyweight_kg * exercise.bw_fraction + sr.added_weight_kg - assistance_kg
    return eff_load if eff_load > 0 else None


def _scan_session(exercise, bodyweight_kg: float, session: SessionResult, best: _BestSet | None) -> _BestSet | None:
    """Update ``best`` with the strongest Epley set in one session."""
    assistance_kg = _session_assistance(session)
    for sr in session.completed_sets:
        eff_load = _usable_eff_load(exercise, bodyweight_kg, assistance_kg, sr)
        if eff_load is None:
            continue
        est = epley_onerm(eff_load, sr.actual_reps)
        if best is None or est > best[0]:
            best = (est, session, sr, eff_load)
    return best


def _formula_breakdown(eff_load: float, reps: int, est: float) -> dict:
    """All five 1RM formulas for the best set (None where unreliable)."""
    blended_added = blended_onerm_added(eff_load, reps)
    return {
        "epley": round(est, 1),
        "brzycki": round(brzycki_onerm(eff_load, reps), 1) if reps < 37 else None,
        "lander": round(lander_onerm(eff_load, reps), 1) if reps < 37 else None,
        "lombardi": round(lombardi_onerm(eff_load, reps), 1),
        "blended": None if blended_added is None else round(eff_load + blended_added, 1),
    }


def _onerm_report(exercise, bodyweight_kg: float, best: _BestSet) -> dict:
    est, session, sr, eff_load = best
    reps = sr.actual_reps
    return {
        "1rm_kg": round(est, 1),
        "best_reps": reps,
        "best_added_weight_kg": sr.added_weight_kg,
        "best_date": session.date,
        "effective_load_kg": round(eff_load, 1),
        "onerm_includes_bodyweight": exercise.onerm_includes_bodyweight,
        "bodyweight_kg": bodyweight_kg,
        "bw_fraction": exercise.bw_fraction,
        "explanation": exercise.onerm_explanation,
        "formulas": _formula_breakdown(eff_load, reps, est),
        "recommended_formula": _recommended_formula(reps),
    }


def estimate_onerm(
    exercise,  # ExerciseDefinition; untyped to avoid a circular import
    bodyweight_kg: float,
    history: list[SessionResult],
    window_sessions: int = 5,
) -> dict | None:
    """Estimate 1RM for any exercise from the best recent set.

    The best set is chosen by Epley; all formulas are then reported for it.
    Returns None when no usable set exists in the window.
    """
    best: _BestSet | None = None
    for session in history[-window_sessions:]:
        best = _scan_session(exercise, bodyweight_kg, session, best)
    if best is None:
        return None
    return _onerm_report(exercise, bodyweight_kg, best)
