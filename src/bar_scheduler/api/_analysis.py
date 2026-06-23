"""Analysis functions for the bar-scheduler API."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from bar_scheduler.core.adaptation import get_training_status as _get_training_status
from bar_scheduler.core.adaptation import overtraining_severity
from bar_scheduler.core.config import TM_FACTOR, expected_reps_per_week
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.equipment import compute_leff
from bar_scheduler.core.metrics import (
    best_onerm_from_leff,
    blended_onerm_added,
    estimate_onerm,
    get_test_sessions,
    session_max_reps as _session_max_reps,
    training_max_from_baseline,
)
from bar_scheduler.api._common import _require_store


def get_training_status(data_dir: Path, exercise_id: str) -> dict:
    """
    Return current training status metrics.

    Includes training_max, latest_test_max, trend, plateau flag, deload
    recommendation, and fitness-fatigue state.
    """
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)
    status = _get_training_status(user_state.history, user_state.profile.bodyweight_kg)
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
    return estimate_onerm(exercise, user_state.profile.bodyweight_kg, user_state.history)


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
        for sess in sessions:
            sess_dt = datetime.strptime(sess.date, "%Y-%m-%d")
            ago = (latest - sess_dt).days // 7
            if ago < weeks:
                reps = sum(
                    sr.actual_reps for sr in sess.completed_sets if sr.actual_reps is not None
                )
                if ago not in weekly:
                    # Compute week start (Monday)
                    monday = sess_dt - timedelta(days=sess_dt.weekday())
                    weekly[ago] = {
                        "total_reps": 0,
                        "week_start": monday.strftime("%Y-%m-%d"),
                    }
                weekly[ago]["total_reps"] += reps

    weekly_data = []
    for week_ago in range(weeks - 1, -1, -1):
        if week_ago == 0:
            label = "This week"
        elif week_ago == 1:
            label = "Last week"
        else:
            label = f"{week_ago} weeks ago"
        week_entry = weekly.get(week_ago, {})
        weekly_data.append(
            {
                "label": label,
                "week_start": week_entry.get("week_start"),
                "total_reps": week_entry.get("total_reps", 0),
            }
        )

    return {"weeks": weekly_data}


def _load_trajectory_target(
    store: object,
    exercise_id: str,
    bw_load: float,
    default_target: int,
) -> tuple[int, float]:
    """Load goal-derived trajectory target; returns defaults on any error."""
    try:
        profile = store.load_profile()  # type: ignore[union-attr]
    except Exception:
        return default_target, 0.0
    ex_target = profile.target_for_exercise(exercise_id) if profile else None
    if ex_target is None:
        return default_target, 0.0
    target_weight = ex_target.weight_kg
    if target_weight > 0:
        full_load = bw_load + target_weight
        one_rm = full_load * (1 + ex_target.reps / 30)
        traj_target = max(int(round(30 * (one_rm / bw_load - 1))), 1)
    else:
        traj_target = ex_target.reps
    return traj_target, target_weight


def _build_base_trajectory(
    test_sessions: list,
    bw_load: float,
    traj_target: int,
) -> list[tuple[datetime, float]]:
    """Build (date, projected_bw_reps) trajectory from the latest test session."""
    latest_test = test_sessions[-1]
    start_dt = datetime.strptime(latest_test.date, "%Y-%m-%d")
    initial_tm = training_max_from_baseline(_session_max_reps(latest_test))
    tm_target = int(traj_target * TM_FACTOR)
    cur_dt, tm_cur = start_dt, float(initial_tm)
    base_pts: list[tuple[datetime, float]] = []
    while tm_cur < tm_target and cur_dt <= start_dt + timedelta(weeks=104):
        base_pts.append((cur_dt, tm_cur / TM_FACTOR))
        tm_cur = min(
            tm_cur + expected_reps_per_week(int(tm_cur), tm_target),
            float(tm_target),
        )
        cur_dt += timedelta(weeks=1)
    base_pts.append((cur_dt, float(traj_target)))
    return base_pts


def _build_traj_g(
    base_pts: list[tuple[datetime, float]],
    bw_load: float,
    target_weight_kg: float,
) -> list[dict]:
    """Build goal-weight trajectory from base BW trajectory."""
    if target_weight_kg > 0:
        load_ratio = bw_load / (bw_load + target_weight_kg)
        pts_g = [
            (pt_dt, max(0.0, load_ratio * proj + 30.0 * (load_ratio - 1.0)))
            for pt_dt, proj in base_pts
        ]
    else:
        pts_g = list(base_pts)
    return [
        {
            "date": pt_dt.strftime("%Y-%m-%d"),
            "projected_goal_reps": round(goal_reps, 2),
        }
        for pt_dt, goal_reps in pts_g
    ]


def _build_traj_m(
    base_pts: list[tuple[datetime, float]],
    bw_load: float,
) -> list[dict] | None:
    """Build 1RM-added-kg trajectory from base BW trajectory."""
    m_pts = []
    for pt_dt, proj_reps in base_pts:
        rep_count = min(int(round(proj_reps)), 20)
        added = blended_onerm_added(bw_load, max(rep_count, 1))
        if added is not None:
            m_pts.append(
                {
                    "date": pt_dt.strftime("%Y-%m-%d"),
                    "projected_1rm_added_kg": round(added, 2),
                }
            )
    return m_pts or None


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
    from bar_scheduler.core.config import TARGET_MAX_REPS

    exercise_def = get_exercise(exercise_id)
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)

    sessions = user_state.history
    test_sessions = get_test_sessions(sessions)

    data_points = [
        {"date": sess.date, "max_reps": _session_max_reps(sess)}
        for sess in test_sessions
        if _session_max_reps(sess) > 0
    ]

    traj_types = set(trajectory_types.lower())
    traj_z = None
    traj_g = None
    traj_m = None

    if traj_types and test_sessions:
        bw = user_state.profile.bodyweight_kg
        bw_load = bw * exercise_def.bw_fraction
        traj_target, target_weight_kg = _load_trajectory_target(
            store, exercise_id, bw_load, TARGET_MAX_REPS
        )
        base_pts = _build_base_trajectory(test_sessions, bw_load, traj_target)

        if "z" in traj_types and base_pts:
            traj_z = [
                {
                    "date": pt_dt.strftime("%Y-%m-%d"),
                    "projected_bw_reps": round(bw_reps, 2),
                }
                for pt_dt, bw_reps in base_pts
            ]

        if "g" in traj_types and base_pts:
            traj_g = _build_traj_g(base_pts, bw_load, target_weight_kg)

        if "m" in traj_types and base_pts and bw_load > 0:
            traj_m = _build_traj_m(base_pts, bw_load)

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
        user_state.profile.bodyweight_kg,
        target.weight_kg,
        0.0,
    )
    onerm_est = best_onerm_from_leff(goal_leff, target.reps)
    return {
        "goal_reps": target.reps,
        "goal_weight_kg": target.weight_kg,
        "goal_leff": round(goal_leff, 2),
        "estimated_1rm": None if onerm_est is None else round(onerm_est, 2),
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
