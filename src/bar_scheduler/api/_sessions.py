"""Session management functions for the bar-scheduler API."""

from __future__ import annotations

from pathlib import Path

from bar_scheduler.containers import container
from bar_scheduler.core.equipment import compute_leff
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.math.formulas import best_onerm_from_leff
from bar_scheduler.domain.context import EquipmentConstraints, PrescriptionContext
from bar_scheduler.io.serializers import session_result_to_dict
from bar_scheduler.api._common import (
    SessionNotFoundError,
    _assistance_for_item,
    _require_store,
)
from bar_scheduler.api.types import SessionInput


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
    from bar_scheduler.core.equipment import recommend_equipment_item, snapshot_from_state
    from bar_scheduler.io.serializers import dict_to_session_result

    store = _require_store(data_dir, exercise_id)
    session_obj = dict_to_session_result(
        {
            "date": session.date,
            "bodyweight_kg": session.bodyweight_kg,
            "grip": session.grip,
            "session_type": session.session_type,
            "exercise_id": exercise_id,
            "completed_sets": [
                {
                    "actual_reps": set_in.reps,
                    "rest_seconds_before": set_in.rest_seconds,
                    "added_weight_kg": set_in.added_weight_kg,
                    **(
                        {} if set_in.rir_reported is None else {"rir_reported": set_in.rir_reported}
                    ),
                }
                for set_in in session.sets
            ],
            **({"notes": session.notes} if session.notes else {}),
        }
    )
    if session_obj.equipment_snapshot is None:
        eq_state = store.load_current_equipment(exercise_id)
        if eq_state is not None:
            ex = get_exercise(exercise_id)
            ustate = store.load_user_state(exercise_id)
            current_tm = container.training_state().status(
                ustate.history, ustate.profile.bodyweight_kg
            ).training_max
            active_item = recommend_equipment_item(eq_state.available_items, ex, current_tm)
            ctx = PrescriptionContext(
                exercise=ex,
                training_max=current_tm,
                bodyweight_kg=ustate.profile.bodyweight_kg,
                history=tuple(s for s in ustate.history if s.exercise_id == exercise_id),
                session_type=session_obj.session_type,
                equipment=EquipmentConstraints.from_state(eq_state),
            )
            override_assistance = _assistance_for_item(active_item, eq_state, ctx)
            session_obj.equipment_snapshot = snapshot_from_state(
                eq_state, active_item, override_assistance_kg=override_assistance
            )
    # Compute and cache performance metrics at log time.
    ex = get_exercise(exercise_id)
    assistance_kg = (
        session_obj.equipment_snapshot.assistance_kg if session_obj.equipment_snapshot else 0.0
    )
    leff_reps = [
        (
            compute_leff(
                ex.bw_fraction,
                session_obj.bodyweight_kg,
                completed_set.added_weight_kg,
                assistance_kg,
            ),
            completed_set.actual_reps,
        )
        for completed_set in session_obj.completed_sets
        if completed_set.actual_reps
    ]
    volumes = [leff * reps for leff, reps in leff_reps]
    count = len(volumes)
    volume_session = sum(volumes)
    avg_volume_set = volume_session / count if count > 0 else 0.0
    best_onerm: float | None = None
    for leff, reps in leff_reps:
        est = best_onerm_from_leff(leff, reps)
        if est is None:
            continue
        if best_onerm is None or est > best_onerm:
            best_onerm = est
    session_obj.session_metrics = {
        "volume_session": round(volume_session, 2),
        "avg_volume_set": round(avg_volume_set, 2),
        "estimated_1rm": None if best_onerm is None else round(best_onerm, 2),
    }

    store.append_session(session_obj)
    store.update_bodyweight(session_obj.bodyweight_kg)
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
