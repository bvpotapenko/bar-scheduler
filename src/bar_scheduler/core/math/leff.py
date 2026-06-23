"""Effective-load (Leff) 1RM estimation from history."""

from bar_scheduler.core.exercises.base import ExerciseDefinition
from bar_scheduler.core.math.formulas import best_onerm_from_leff
from bar_scheduler.domain.models import SessionResult, SetResult

History = list[SessionResult]


def _set_leff_onerm(
    session: SessionResult,
    sr: SetResult,
    bw_fraction: float,
    assistance: float,
) -> float | None:
    """1RM estimate from one completed set, or None if it cannot seed one."""
    if not sr.actual_reps or sr.actual_reps < 1:
        return None
    leff = session.bodyweight_kg * bw_fraction + (sr.added_weight_kg or 0.0) - assistance
    if leff <= 0:
        return None
    return best_onerm_from_leff(leff, sr.actual_reps)


def _session_leff_onerms(session: SessionResult, bw_fraction: float) -> list[float]:
    snap = session.equipment_snapshot
    assistance = snap.assistance_kg if snap is not None else 0.0
    estimates: list[float] = []
    for sr in session.completed_sets:
        est = _set_leff_onerm(session, sr, bw_fraction, assistance)
        if est is not None:
            estimates.append(est)
    return estimates


def estimate_effective_leff_onerm(history: History, bw_fraction: float) -> float | None:
    """Max Leff 1RM across every recorded set, or None if history has none."""
    candidates: list[float] = []
    for session in history:
        candidates.extend(_session_leff_onerms(session, bw_fraction))
    return max(candidates) if candidates else None


def resolve_leff_onerm(
    history: History,
    bw_fraction: float,
    bw_contrib: float,
    training_max: int,
    hist_floor: float,
) -> float:
    """Blend a history-derived estimate with a TM-derived one (history wins when above floor)."""
    hist = estimate_effective_leff_onerm(history, bw_fraction)
    tm_derived = best_onerm_from_leff(bw_contrib, training_max) or bw_contrib
    if hist is None or hist <= hist_floor:
        return tm_derived
    return max(hist, tm_derived)


def _is_test_for(sess: SessionResult, exercise_id: str) -> bool:
    return sess.session_type == "TEST" and sess.exercise_id == exercise_id


def _positive_added_weights(sets: list[SetResult]) -> list[float]:
    return [sr.added_weight_kg for sr in sets if sr.added_weight_kg > 0]


def last_test_weight(history: History, exercise: ExerciseDefinition) -> float:
    """Added weight carried forward from the most recent TEST session (0.0 if none)."""
    tests = [sess for sess in history if _is_test_for(sess, exercise.exercise_id)]
    if not tests or not tests[-1].completed_sets:
        return 0.0
    weights = _positive_added_weights(tests[-1].completed_sets)
    return weights[-1] if weights else 0.0
