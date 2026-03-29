"""Session management functions for the bar-scheduler API."""
from __future__ import annotations

from pathlib import Path

from ..core.adaptation import get_training_status as _get_training_status
from ..core.equipment import compute_leff
from ..core.exercises.registry import get_exercise
from ..core.metrics import best_1rm_from_leff
from ..io.serializers import session_result_to_dict
from ._common import (
    SessionNotFoundError,
    _require_store,
)
from .types import SessionInput


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
    from ..core.equipment import recommend_equipment_item, snapshot_from_state
    from ..core.planner.load_calculator import calculate_machine_assistance
    from ..io.serializers import dict_to_session_result

    store = _require_store(data_dir, exercise_id)
    session_obj = dict_to_session_result({
        "date": session.date,
        "bodyweight_kg": session.bodyweight_kg,
        "grip": session.grip,
        "session_type": session.session_type,
        "exercise_id": exercise_id,
        "completed_sets": [
            {
                "actual_reps": s.reps,
                "rest_seconds_before": s.rest_seconds,
                "added_weight_kg": s.added_weight_kg,
                **({"rir_reported": s.rir_reported} if s.rir_reported is not None else {}),
            }
            for s in session.sets
        ],
        **({"notes": session.notes} if session.notes else {}),
    })
    if session_obj.equipment_snapshot is None:
        eq_state = store.load_current_equipment(exercise_id)
        if eq_state is not None:
            ex = get_exercise(exercise_id)
            ustate = store.load_user_state(exercise_id)
            current_tm = _get_training_status(
                ustate.history, ustate.profile.bodyweight_kg
            ).training_max
            active_item = recommend_equipment_item(
                eq_state.available_items, ex, current_tm, ustate.history[-10:]
            )
            # For machine-assisted exercises with a discrete assistance list,
            # compute the prescribed assistance level rather than using a fixed value.
            override_assistance: float | None = None
            if (
                active_item == "MACHINE_ASSISTED"
                and eq_state.available_machine_assistance_kg
            ):
                history = [s for s in ustate.history if s.exercise_id == exercise_id]
                override_assistance = calculate_machine_assistance(
                    ex,
                    current_tm,
                    ustate.profile.bodyweight_kg,
                    history,
                    session_obj.session_type,
                    available_machine_assistance_kg=eq_state.available_machine_assistance_kg,
                )
            session_obj.equipment_snapshot = snapshot_from_state(
                eq_state, active_item, override_assistance_kg=override_assistance
            )
    # Compute and cache performance metrics at log time.
    ex = get_exercise(exercise_id)
    assistance_kg = (
        session_obj.equipment_snapshot.assistance_kg
        if session_obj.equipment_snapshot is not None
        else 0.0
    )
    leff_reps = [
        (
            compute_leff(
                ex.bw_fraction,
                session_obj.bodyweight_kg,
                s.added_weight_kg,
                assistance_kg,
            ),
            s.actual_reps,
        )
        for s in session_obj.completed_sets
        if s.actual_reps is not None and s.actual_reps > 0
    ]
    volumes = [leff * reps for leff, reps in leff_reps]
    n = len(volumes)
    volume_session = sum(volumes)
    avg_volume_set = volume_session / n if n > 0 else 0.0
    best_1rm: float | None = None
    for leff, reps in leff_reps:
        est = best_1rm_from_leff(leff, reps)
        if est is not None and (best_1rm is None or est > best_1rm):
            best_1rm = est
    session_obj.session_metrics = {
        "volume_session": round(volume_session, 2),
        "avg_volume_set": round(avg_volume_set, 2),
        "estimated_1rm": round(best_1rm, 2) if best_1rm is not None else None,
    }

    store.append_session(session_obj)
    return session_result_to_dict(session_obj)


def delete_session(data_dir: Path, exercise_id: str, index: int) -> None:
    """
    Delete the session at the given 1-based position in sorted history.

    Raises ``SessionNotFoundError`` if ``index`` is out of range.
    """
    store = _require_store(data_dir, exercise_id)
    sessions = store.load_history(exercise_id)
    zero_based = index - 1
    if zero_based < 0 or zero_based >= len(sessions):
        raise SessionNotFoundError(
            f"Session {index} not found (history has {len(sessions)} sessions)."
        )
    store.delete_session_at(exercise_id, zero_based)


def get_history(data_dir: Path, exercise_id: str) -> list[dict]:
    """
    Return the full session history as a list of dicts, sorted by date.

    Each dict includes a ``session_metrics`` key with pre-computed performance
    metrics (``volume_session``, ``avg_volume_set``, ``estimated_1rm``).
    For sessions logged before metrics caching was introduced, all values are
    ``None``.
    """
    store = _require_store(data_dir, exercise_id)
    sessions = store.load_history(exercise_id)
    result = []
    for s in sessions:
        d = session_result_to_dict(s)
        if "session_metrics" not in d:
            d["session_metrics"] = {
                "volume_session": None,
                "avg_volume_set": None,
                "estimated_1rm": None,
            }
        result.append(d)
    return result
