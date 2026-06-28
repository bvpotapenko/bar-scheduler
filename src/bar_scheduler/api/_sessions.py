"""Session management functions for the bar-scheduler API."""

from __future__ import annotations

from pathlib import Path

from bar_scheduler.core.equipment import compute_leff
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.domain.models import SessionResult
from bar_scheduler.io.serializers import dict_to_session_result, session_result_to_dict
from bar_scheduler.api._common import _require_store, _session_performance_metrics
from bar_scheduler.api._errors import SessionNotFoundError
from bar_scheduler.api._log_equipment import resolve_equipment_snapshot
from bar_scheduler.api.types import SessionInput


def _set_payload(set_in) -> dict:
    """JSON payload for one logged set (rir omitted when not reported)."""
    payload = {
        "actual_reps": set_in.reps,
        "rest_seconds_before": set_in.rest_seconds,
        "added_weight_kg": set_in.added_weight_kg,
    }
    if set_in.rir_reported is not None:
        payload["rir_reported"] = set_in.rir_reported
    return payload


def _build_session(exercise_id: str, session: SessionInput) -> SessionResult:
    """Build a SessionResult from validated SessionInput."""
    return dict_to_session_result(
        {
            "date": session.date,
            "bodyweight_kg": session.bodyweight_kg,
            "grip": session.grip,
            "session_type": session.session_type,
            "exercise_id": exercise_id,
            "completed_sets": [_set_payload(set_in) for set_in in session.sets],
            **({"notes": session.notes} if session.notes else {}),
        }
    )


def _cache_metrics(exercise_id: str, session_obj: SessionResult) -> None:
    """Compute and store per-session performance metrics at log time."""
    ex = get_exercise(exercise_id)
    snapshot = session_obj.equipment_snapshot
    assistance_kg = snapshot.assistance_kg if snapshot else 0.0
    leff_reps = [
        (
            compute_leff(
                ex.bw_fraction, session_obj.bodyweight_kg, cs.added_weight_kg, assistance_kg
            ),
            cs.actual_reps,
        )
        for cs in session_obj.completed_sets
        if cs.actual_reps
    ]
    session_obj.session_metrics = _session_performance_metrics(leff_reps)


def log_session(data_dir: Path, exercise_id: str, session: SessionInput) -> dict:
    """
    Append a training session to the history.

    ``session`` is a ``SessionInput`` with:

    - ``date``           -- ISO date string (YYYY-MM-DD)
    - ``session_type``   -- one of ``"S"``, ``"H"``, ``"E"``, ``"T"``, ``"TEST"``
    - ``bodyweight_kg``  -- float (> 0)
    - ``sets``           -- list of ``SetInput``
    - ``grip``           -- exercise-specific variant (default ``"neutral"``)
    - ``notes``          -- optional notes string

    Returns the serialised session dict. The equipment snapshot is read from
    the profile and attached automatically.
    """
    store = _require_store(data_dir, exercise_id)
    session_obj = _build_session(exercise_id, session)
    resolve_equipment_snapshot(store, exercise_id, session_obj)
    _cache_metrics(exercise_id, session_obj)
    store.history.append(session_obj)
    store.profile.update_fields(bodyweight_kg=session_obj.bodyweight_kg)
    return session_result_to_dict(session_obj)


def delete_session(data_dir: Path, exercise_id: str, index: int) -> None:
    """
    Delete the session at the given 1-based position in sorted history.

    Raises ``SessionNotFoundError`` if ``index`` is out of range.
    """
    store = _require_store(data_dir, exercise_id)
    sessions = store.history.load(exercise_id)
    zero_based = index - 1
    if zero_based < 0 or zero_based >= len(sessions):
        raise SessionNotFoundError(
            f"Session {index} not found (history has {len(sessions)} sessions)."
        )
    store.history.delete_at(exercise_id, zero_based)


def get_history(data_dir: Path, exercise_id: str) -> list[dict]:
    """
    Return the full session history as a list of dicts, sorted by date.

    Each dict includes a ``session_metrics`` key with pre-computed performance
    metrics (``volume_session``, ``avg_volume_set``, ``estimated_1rm``).
    For sessions logged before metrics caching was introduced, all values are
    ``None``.
    """
    store = _require_store(data_dir, exercise_id)
    sessions = store.history.load(exercise_id)
    history_list = []
    for session_rec in sessions:
        entry = session_result_to_dict(session_rec)
        if "session_metrics" not in entry:
            entry["session_metrics"] = {
                "volume_session": None,
                "avg_volume_set": None,
                "estimated_1rm": None,
            }
        history_list.append(entry)
    return history_list
