"""Shared exceptions and private helpers for the bar-scheduler API."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from ..core.equipment import compute_leff
from ..core.exercises.base import ExerciseDefinition
from ..core.metrics import best_1rm_from_leff
from ..core.models import SessionResult
from ..core.timeline import TimelineEntry
from ..io.user_store import UserStore


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class ProfileNotFoundError(FileNotFoundError):
    """Raised when profile.json does not exist."""


class HistoryNotFoundError(FileNotFoundError):
    """Raised when the JSONL history file does not exist."""


class SessionNotFoundError(IndexError):
    """Raised when a session index is out of range."""


class ProfileAlreadyExistsError(FileExistsError):
    """Raised when init_profile is called on an already-initialized directory."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_profile_store(data_dir: Path) -> UserStore:
    """Return a UserStore, raising ProfileNotFoundError if profile.json is missing."""
    store = UserStore(data_dir)
    if not store.profile_path.exists():
        raise ProfileNotFoundError(
            f"Profile not found at {store.profile_path}. Call init_profile() first."
        )
    return store


def _require_store(data_dir: Path, exercise_id: str) -> UserStore:
    """Return a UserStore, raising typed errors when profile or history files are missing."""
    store = _require_profile_store(data_dir)
    if not store.exists(exercise_id):
        raise HistoryNotFoundError(
            f"History file not found at {store.history_path(exercise_id)}. Call init_profile() first."
        )
    return store


def _resolve_plan_start(
    store: UserStore, exercise_id: str, history: list[SessionResult]
) -> str:
    plan_start = store.get_plan_start_date(exercise_id)
    if plan_start is None:
        if history:
            first_dt = datetime.strptime(history[0].date, "%Y-%m-%d")
            plan_start = (first_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            plan_start = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return plan_start


def _total_weeks(plan_start_date: str, weeks_ahead: int = 4) -> int:
    from ..core.config import MAX_PLAN_WEEKS

    plan_start_dt = datetime.strptime(plan_start_date, "%Y-%m-%d")
    weeks_since_start = max(0, (datetime.now() - plan_start_dt).days // 7)
    return max(2, min(weeks_since_start + weeks_ahead, MAX_PLAN_WEEKS * 3))


def _session_performance_metrics(
    sets_leff_reps: list[tuple[float, int]],
) -> dict:
    """Compute volume_session, avg_volume_set, estimated_1rm from (leff, reps) pairs."""
    volumes = [leff * reps for leff, reps in sets_leff_reps]
    n = len(volumes)
    volume_session = sum(volumes)
    avg_volume_set = volume_session / n if n > 0 else 0.0
    best_1rm: float | None = None
    for leff, reps in sets_leff_reps:
        est = best_1rm_from_leff(leff, reps)
        if est is not None and (best_1rm is None or est > best_1rm):
            best_1rm = est
    return {
        "volume_session": round(volume_session, 2),
        "avg_volume_set": round(avg_volume_set, 2),
        "estimated_1rm": round(best_1rm, 2) if best_1rm is not None else None,
    }


def _timeline_entry_to_dict(
    e: TimelineEntry,
    exercise: ExerciseDefinition | None = None,
    current_bw: float | None = None,
) -> dict:
    """Serialise a TimelineEntry to a JSON-friendly dict."""
    planned_sets = None
    if e.actual is not None and e.actual.planned_sets:
        planned_sets = [
            {
                "reps": s.target_reps,
                "weight_kg": s.added_weight_kg,
                "rest_s": s.rest_seconds_before,
            }
            for s in e.actual.planned_sets
        ]
    elif e.planned is not None and e.planned.sets:
        planned_sets = [
            {
                "reps": s.target_reps,
                "weight_kg": s.added_weight_kg,
                "rest_s": s.rest_seconds_before,
            }
            for s in e.planned.sets
        ]

    actual_sets = None
    if e.actual is not None:
        actual_sets = [
            {
                "reps": s.actual_reps,
                "weight_kg": s.added_weight_kg,
                "rest_s": s.rest_seconds_before,
            }
            for s in e.actual.completed_sets
            if s.actual_reps is not None
        ]

    plan_type = (
        e.actual.session_type
        if e.actual
        else (e.planned.session_type if e.planned else "")
    )
    plan_grip = e.actual.grip if e.actual else (e.planned.grip if e.planned else "")

    # Performance metrics for this session.
    # For completed sessions: use cached session_metrics (None if old record).
    # For planned/future sessions: compute from prescribed sets if exercise/BW available.
    session_metrics: dict | None = None
    if e.actual is not None:
        session_metrics = e.actual.session_metrics
    elif e.planned is not None and exercise is not None and current_bw is not None:
        leff_reps = [
            (compute_leff(exercise.bw_fraction, current_bw, s.added_weight_kg, 0.0), s.target_reps)
            for s in e.planned.sets
            if s.target_reps > 0
        ]
        if leff_reps:
            session_metrics = _session_performance_metrics(leff_reps)

    return {
        "date": e.date,
        "week": e.week_number,
        "type": plan_type,
        "grip": plan_grip,
        "status": e.status,
        "id": e.actual_id,
        "expected_tm": e.planned.expected_tm if e.planned else None,
        "prescribed_sets": planned_sets,
        "actual_sets": actual_sets,
        "track_b": e.track_b,
        "session_metrics": session_metrics,
        "prescribed_assistance_kg": (
            e.planned.prescribed_assistance_kg if e.planned is not None else None
        ),
    }
