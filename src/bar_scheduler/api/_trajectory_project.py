"""Re-project a base (date, bw-reps) curve into the requested trajectory series."""

from __future__ import annotations

from functools import partial

from bar_scheduler.core.math import formulas

_MAX_PROJECTION_REPS = 20


def _identity(reps: float) -> float:
    return reps


def _goal_reps(reps: float, ratio: float, offset: float) -> float:
    """Project bodyweight reps to reps-at-goal-weight via the load ratio."""
    return max(0.0, ratio * reps + offset)


class _TrajectoryBuilder:
    """Build the z/g/m trajectory series from a shared base bw-reps curve."""

    def __init__(self, base_pts: list, bw_load: float, target_weight_kg: float) -> None:
        self._base = base_pts
        self._bw_load = bw_load
        self._target_weight = target_weight_kg

    def build(self, traj_types: set[str]) -> dict:
        """Return {trajectory_z, trajectory_g, trajectory_m}; None when not requested."""
        return {
            "trajectory_z": self._z() if "z" in traj_types else None,
            "trajectory_g": self._g() if "g" in traj_types else None,
            "trajectory_m": self._m() if "m" in traj_types and self._bw_load > 0 else None,
        }

    def _z(self) -> list[dict] | None:
        return self._rows("projected_bw_reps", _identity)

    def _g(self) -> list[dict] | None:
        if self._target_weight <= 0:
            return self._rows("projected_goal_reps", _identity)
        ratio = self._bw_load / (self._bw_load + self._target_weight)
        offset = 30.0 * (ratio - 1.0)
        return self._rows("projected_goal_reps", partial(_goal_reps, ratio=ratio, offset=offset))

    def _m(self) -> list[dict] | None:
        return self._rows("projected_1rm_added_kg", self._added)

    def _added(self, reps: float) -> float | None:
        rep_count = max(min(int(round(reps)), _MAX_PROJECTION_REPS), 1)
        return formulas.blended_onerm_added(self._bw_load, rep_count)

    def _rows(self, key: str, value_fn) -> list[dict] | None:
        rows = []
        for pt_dt, reps in self._base:
            value = value_fn(reps)
            if value is not None:
                date_str = pt_dt.strftime("%Y-%m-%d")
                rows.append({"date": date_str, key: round(value, 2)})
        return rows or None
