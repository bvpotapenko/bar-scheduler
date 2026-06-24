"""Base goal-trajectory computation for get_progress_data.

Projects training-max growth forward week-by-week from the latest TEST into a
base ``(date, bw_reps)`` curve. Re-projection into z/g/m series lives in
:mod:`bar_scheduler.api._trajectory_project`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from bar_scheduler.core.config import TM_FACTOR, expected_reps_per_week
from bar_scheduler.core.math import history_queries
from bar_scheduler.core.math.training_max import training_max_from_baseline

_session_max_reps = history_queries.session_max_reps
_HORIZON_WEEKS = 104
_EPLEY_REP_DENOM = 30  # reps term in the Epley 1RM relation

_BasePoints = list[tuple[datetime, float]]


def _safe_target(store, exercise_id: str):
    try:
        profile = store.load_profile()
    except Exception:
        return None
    return profile.target_for_exercise(exercise_id) if profile else None


def _weighted_traj_target(bw_load: float, target) -> int:
    full_load = bw_load + target.weight_kg
    one_rm = full_load * (1 + target.reps / _EPLEY_REP_DENOM)
    reps_at_bw = _EPLEY_REP_DENOM * (one_rm / bw_load - 1)
    return max(int(round(reps_at_bw)), 1)


def _load_trajectory_target(
    store, exercise_id: str, bw_load: float, default_target: int
) -> tuple[int, float]:
    """(trajectory_target_reps, target_weight_kg); defaults on missing goal/error."""
    target = _safe_target(store, exercise_id)
    if target is None:
        return default_target, 0.0
    if target.weight_kg <= 0:
        return target.reps, 0.0
    return _weighted_traj_target(bw_load, target), target.weight_kg


def _project_tm(
    start_dt: datetime, initial_tm: float, tm_target: int
) -> tuple[_BasePoints, datetime]:
    """Climb TM toward tm_target one week at a time; return points + end date."""
    points: _BasePoints = []
    cur_dt = start_dt
    tm_cur = initial_tm
    limit = start_dt + timedelta(weeks=_HORIZON_WEEKS)
    while tm_cur < tm_target and cur_dt <= limit:
        points.append((cur_dt, tm_cur / TM_FACTOR))
        gain = expected_reps_per_week(int(tm_cur), tm_target)
        tm_cur = min(tm_cur + gain, float(tm_target))
        cur_dt += timedelta(weeks=1)
    return points, cur_dt


def _build_base_trajectory(test_sessions: list, traj_target: int) -> _BasePoints:
    """(date, projected_bw_reps) points climbing toward ``traj_target`` reps."""
    start_dt = datetime.strptime(test_sessions[-1].date, "%Y-%m-%d")
    initial_tm = float(training_max_from_baseline(_session_max_reps(test_sessions[-1])))
    tm_target = int(traj_target * TM_FACTOR)
    points, end_dt = _project_tm(start_dt, initial_tm, tm_target)
    points.append((end_dt, float(traj_target)))
    return points
