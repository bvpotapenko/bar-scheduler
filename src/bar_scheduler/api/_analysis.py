"""Analysis endpoints for the bar-scheduler API."""

from __future__ import annotations

from pathlib import Path

from bar_scheduler.containers import container
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.equipment import compute_leff
from bar_scheduler.core.math import formulas, onerm
from bar_scheduler.api._common import _require_store

_EMPTY_GOAL = {
    "goal_reps": None,
    "goal_weight_kg": None,
    "goal_leff": None,
    "estimated_1rm": None,
    "volume_set": None,
}


def get_training_status(data_dir: Path, exercise_id: str) -> dict:
    """
    Return current training status metrics.

    Includes training_max, latest_test_max, trend, plateau flag, deload
    recommendation, and fitness-fatigue state.
    """
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)
    status = container.training_state().status(
        user_state.history, user_state.profile.bodyweight_kg
    )
    ff = status.fitness_fatigue_state
    return {
        "training_max": status.training_max,
        "latest_test_max": status.latest_test_max,
        "trend_slope_per_week": round(status.trend_slope, 4),
        "is_plateau": status.is_plateau,
        "deload_recommended": status.deload_recommended,
        "readiness_z_score": round(ff.readiness_z_score(), 4),
        "fitness": round(ff.fitness, 4),
        "fatigue": round(ff.fatigue, 4),
    }


def get_onerepmax_data(data_dir: Path, exercise_id: str) -> dict | None:
    """
    Estimate 1-rep max using multiple formulas.

    Returns ``None`` if there is not enough history data. Otherwise returns a
    dict with ``formulas`` (epley/brzycki/lander/lombardi/blended values in kg),
    ``recommended_formula``, ``best_reps``, ``best_added_weight_kg``,
    ``effective_load_kg``, and ``best_date``.
    """
    exercise = get_exercise(exercise_id)
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)
    return onerm.estimate_onerm(exercise, user_state.profile.bodyweight_kg, user_state.history)


def _goal_metrics(bw_fraction: float, bodyweight_kg: float, target) -> dict:
    """Goal performance metrics (Leff, implied 1RM, single-set volume)."""
    goal_leff = compute_leff(bw_fraction, bodyweight_kg, target.weight_kg, 0.0)
    onerm_est = formulas.best_onerm_from_leff(goal_leff, target.reps)
    return {
        "goal_reps": target.reps,
        "goal_weight_kg": target.weight_kg,
        "goal_leff": round(goal_leff, 2),
        "estimated_1rm": None if onerm_est is None else round(onerm_est, 2),
        "volume_set": round(goal_leff * target.reps, 2),
    }


def get_goal_metrics(data_dir: Path, exercise_id: str) -> dict:
    """
    Return performance metrics for the user's goal for this exercise.

    All fields are ``None`` when no goal has been set via ``set_exercise_target``.
    Otherwise: ``goal_reps``, ``goal_weight_kg``, ``goal_leff`` (effective load),
    ``estimated_1rm`` (Leff kg), and ``volume_set`` (goal_leff × goal_reps).
    """
    exercise = get_exercise(exercise_id)
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)
    target = user_state.profile.target_for_exercise(exercise_id)
    if target is None:
        return dict(_EMPTY_GOAL)
    return _goal_metrics(exercise.bw_fraction, user_state.profile.bodyweight_kg, target)


def get_overtraining_status(data_dir: Path, exercise_id: str) -> dict:
    """
    Return the current overtraining severity assessment.

    Returns a dict with ``level`` (0–3), ``description``, and
    ``extra_rest_days``. Level 0 = no issue; level 3 = severe.
    """
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)
    return container.overtraining().severity(
        user_state.history, user_state.profile.days_for_exercise(exercise_id)
    )
