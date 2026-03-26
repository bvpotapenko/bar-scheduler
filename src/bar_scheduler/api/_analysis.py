"""Analysis functions for the bar-scheduler API."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from ..core.adaptation import get_training_status as _get_training_status
from ..core.adaptation import overtraining_severity
from ..core.config import TM_FACTOR, expected_reps_per_week
from ..core.exercises.registry import get_exercise
from ..core.equipment import compute_leff
from ..core.metrics import (
    best_1rm_from_leff,
    blended_1rm_added,
    estimate_1rm,
    get_test_sessions,
    session_max_reps as _session_max_reps,
    training_max_from_baseline,
)
from ._common import _require_store


def get_training_status(data_dir: Path, exercise_id: str) -> dict:
    """
    Return current training status metrics.

    Includes training_max, latest_test_max, trend, plateau flag, deload
    recommendation, and fitness-fatigue state.
    """
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)
    status = _get_training_status(
        user_state.history, user_state.current_bodyweight_kg
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
    return estimate_1rm(
        exercise, user_state.current_bodyweight_kg, user_state.history
    )


def get_volume_data(
    data_dir: Path,
    exercise_id: str,
    weeks: int = 4,
) -> dict:
    """
    Return weekly rep volume for the last ``weeks`` weeks.

    Returns a dict with a ``"weeks"`` list, each element being:
    ``{"label": str, "week_start": str|None, "total_reps": int}``.
    Week 0 = current week, week 1 = last week, etc.
    """
    store = _require_store(data_dir, exercise_id)
    sessions = store.load_history(exercise_id)

    weekly: dict[int, dict] = {}
    if sessions:
        latest = datetime.strptime(sessions[-1].date, "%Y-%m-%d")
        for s in sessions:
            s_dt = datetime.strptime(s.date, "%Y-%m-%d")
            ago = (latest - s_dt).days // 7
            if ago < weeks:
                reps = sum(
                    sr.actual_reps
                    for sr in s.completed_sets
                    if sr.actual_reps is not None
                )
                if ago not in weekly:
                    # Compute week start (Monday)
                    monday = s_dt - timedelta(days=s_dt.weekday())
                    weekly[ago] = {
                        "total_reps": 0,
                        "week_start": monday.strftime("%Y-%m-%d"),
                    }
                weekly[ago]["total_reps"] += reps

    result = []
    for i in range(weeks - 1, -1, -1):
        label = "This week" if i == 0 else ("Last week" if i == 1 else f"{i} weeks ago")
        entry = weekly.get(i, {})
        result.append(
            {
                "label": label,
                "week_start": entry.get("week_start"),
                "total_reps": entry.get("total_reps", 0),
            }
        )

    return {"weeks": result}


def get_progress_data(
    data_dir: Path,
    exercise_id: str,
    trajectory_types: str = "",
) -> dict:
    """
    Return raw data for plotting training progress.

    ``trajectory_types`` is a string of letters: ``z`` = BW reps trajectory,
    ``g`` = reps at goal weight, ``m`` = 1RM in added kg.

    Returns a dict with:
    - ``data_points`` -- list of ``{"date": str, "max_reps": int}`` from TEST sessions
    - ``trajectory_z`` -- projected BW reps over time (or ``None``)
    - ``trajectory_g`` -- projected reps at goal weight (or ``None``)
    - ``trajectory_m`` -- projected 1RM added kg over time (or ``None``)
    """
    from ..core.config import TARGET_MAX_REPS

    exercise_def = get_exercise(exercise_id)
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)

    sessions = user_state.history
    test_sessions = get_test_sessions(sessions)

    data_points = [
        {"date": s.date, "max_reps": _session_max_reps(s)}
        for s in test_sessions
        if _session_max_reps(s) > 0
    ]

    traj_types = set(trajectory_types.lower())
    traj_z = None
    traj_g = None
    traj_m = None

    if traj_types and test_sessions:
        bw = user_state.current_bodyweight_kg
        bw_load = bw * exercise_def.bw_fraction
        traj_target = TARGET_MAX_REPS
        target_weight_kg = 0.0

        try:
            profile = store.load_profile()
            ex_target = (
                profile.target_for_exercise(exercise_id) if profile else None
            )
            if ex_target is not None:
                target_weight_kg = ex_target.weight_kg
                if ex_target.weight_kg > 0:
                    full_load = bw_load + ex_target.weight_kg
                    one_rm = full_load * (1 + ex_target.reps / 30)
                    traj_target = max(int(round(30 * (one_rm / bw_load - 1))), 1)
                else:
                    traj_target = ex_target.reps
        except Exception:
            pass

        # Build base trajectory points
        base_pts: list[tuple[datetime, float]] = []
        latest_test = test_sessions[-1]
        start_dt = datetime.strptime(latest_test.date, "%Y-%m-%d")
        initial_tm = training_max_from_baseline(_session_max_reps(latest_test))
        tm_target = int(traj_target * TM_FACTOR)
        d, tm_f = start_dt, float(initial_tm)
        while tm_f < tm_target and d <= start_dt + timedelta(weeks=104):
            base_pts.append((d, tm_f / TM_FACTOR))
            tm_f = min(
                tm_f + expected_reps_per_week(int(tm_f), tm_target),
                float(tm_target),
            )
            d += timedelta(weeks=1)
        base_pts.append((d, float(traj_target)))

        if "z" in traj_types and base_pts:
            traj_z = [
                {
                    "date": pt.strftime("%Y-%m-%d"),
                    "projected_bw_reps": round(val, 2),
                }
                for pt, val in base_pts
            ]

        if "g" in traj_types and base_pts:
            if target_weight_kg > 0:
                f = bw_load / (bw_load + target_weight_kg)
                pts_g = [
                    (dt_, max(0.0, f * z + 30.0 * (f - 1.0))) for dt_, z in base_pts
                ]
            else:
                pts_g = list(base_pts)
            traj_g = [
                {
                    "date": pt.strftime("%Y-%m-%d"),
                    "projected_goal_reps": round(val, 2),
                }
                for pt, val in pts_g
            ]

        if "m" in traj_types and base_pts and bw_load > 0:
            m_pts = []
            for pt, reps in base_pts:
                r = min(int(round(reps)), 20)
                added = blended_1rm_added(bw_load, max(r, 1))
                if added is not None:
                    m_pts.append(
                        {
                            "date": pt.strftime("%Y-%m-%d"),
                            "projected_1rm_added_kg": round(added, 2),
                        }
                    )
            traj_m = m_pts or None

    return {
        "data_points": data_points,
        "trajectory_z": traj_z,
        "trajectory_g": traj_g,
        "trajectory_m": traj_m,
    }


def get_goal_metrics(data_dir: Path, exercise_id: str) -> dict:
    """
    Return performance metrics for the user's goal for this exercise.

    All fields are ``None`` when no goal has been set via ``set_exercise_target``.

    Returns a dict with:
    - ``goal_reps`` -- target reps (``int | None``)
    - ``goal_weight_kg`` -- target added weight (``float | None``)
    - ``goal_leff`` -- effective load at goal (``float | None``)
    - ``estimated_1rm`` -- 1RM implied by achieving the goal, in Leff kg (``float | None``)
    - ``volume_set`` -- ``goal_leff × goal_reps``, a single set at goal spec (``float | None``)
    """
    exercise = get_exercise(exercise_id)
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)

    target = user_state.profile.target_for_exercise(exercise_id)
    if target is None:
        return {
            "goal_reps": None,
            "goal_weight_kg": None,
            "goal_leff": None,
            "estimated_1rm": None,
            "volume_set": None,
        }

    goal_leff = compute_leff(
        exercise.bw_fraction,
        user_state.current_bodyweight_kg,
        target.weight_kg,
        0.0,
    )
    est_1rm = best_1rm_from_leff(goal_leff, target.reps)
    return {
        "goal_reps": target.reps,
        "goal_weight_kg": target.weight_kg,
        "goal_leff": round(goal_leff, 2),
        "estimated_1rm": round(est_1rm, 2) if est_1rm is not None else None,
        "volume_set": round(goal_leff * target.reps, 2),
    }


def get_overtraining_status(data_dir: Path, exercise_id: str) -> dict:
    """
    Return the current overtraining severity assessment.

    Returns a dict with ``level`` (0–3), ``description``, and
    ``extra_rest_days``. Level 0 = no issue; level 3 = severe.
    """
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)
    return overtraining_severity(
        user_state.history, user_state.profile.days_for_exercise(exercise_id)
    )


