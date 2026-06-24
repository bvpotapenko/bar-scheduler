"""Training-progress data (test points + goal trajectories) for the API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bar_scheduler.core.config import TARGET_MAX_REPS
from bar_scheduler.core.exercises.base import ExerciseDefinition
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.math import history_queries
from bar_scheduler.domain.models import UserState
from bar_scheduler.io.user_store import UserStore
from bar_scheduler.api._common import _require_store
from bar_scheduler.api._trajectory import _build_base_trajectory, _load_trajectory_target
from bar_scheduler.api._trajectory_project import _TrajectoryBuilder

_session_max_reps = history_queries.session_max_reps


@dataclass(frozen=True)
class _ProgressInputs:
    store: UserStore
    exercise: ExerciseDefinition
    user_state: UserState

    @property
    def exercise_id(self) -> str:
        return self.exercise.exercise_id

    @property
    def bw_load(self) -> float:
        return self.user_state.profile.bodyweight_kg * self.exercise.bw_fraction

    @property
    def test_sessions(self) -> list:
        return history_queries.get_test_sessions(self.user_state.history)


def _load_progress(data_dir: Path, exercise_id: str) -> _ProgressInputs:
    store = _require_store(data_dir, exercise_id)
    return _ProgressInputs(
        store=store,
        exercise=get_exercise(exercise_id),
        user_state=store.load_user_state(exercise_id),
    )


def _data_points(test_sessions: list) -> list[dict]:
    return [
        {"date": sess.date, "max_reps": _session_max_reps(sess)}
        for sess in test_sessions
        if _session_max_reps(sess) > 0
    ]


def _trajectories(inputs: _ProgressInputs, traj_types: set[str]) -> dict:
    traj_target, target_weight_kg = _load_trajectory_target(
        inputs.store, inputs.exercise_id, inputs.bw_load, TARGET_MAX_REPS
    )
    base_pts = _build_base_trajectory(inputs.test_sessions, traj_target)
    return _TrajectoryBuilder(base_pts, inputs.bw_load, target_weight_kg).build(traj_types)


def get_progress_data(data_dir: Path, exercise_id: str, trajectory_types: str = "") -> dict:
    """
    Return raw data for plotting training progress.

    ``trajectory_types`` is a string of letters: ``z`` = BW reps trajectory,
    ``g`` = reps at goal weight, ``m`` = 1RM in added kg.

    Returns a dict with ``data_points`` (test-session max reps) and
    ``trajectory_z`` / ``trajectory_g`` / ``trajectory_m`` (each list or None).
    """
    inputs = _load_progress(data_dir, exercise_id)
    traj_types = set(trajectory_types.lower())
    result = {
        "data_points": _data_points(inputs.test_sessions),
        "trajectory_z": None,
        "trajectory_g": None,
        "trajectory_m": None,
    }
    if traj_types and inputs.test_sessions:
        result.update(_trajectories(inputs, traj_types))
    return result
