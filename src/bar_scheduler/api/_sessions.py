"""Session management functions for the bar-scheduler API."""
from __future__ import annotations

from pathlib import Path

from ..core.adaptation import get_training_status as _get_training_status
from ..core.exercises.registry import get_exercise
from ..io.serializers import session_result_to_dict
from ._common import (
    SessionNotFoundError,
    _require_store,
)


def log_session(data_dir: Path, exercise_id: str, session: dict) -> dict:
    """
    Append a training session to the history.

    ``session`` must be a dict with fields matching ``SessionResult``
    (see ``io/serializers.py``).  The most important required fields are:

    - ``date``             -- ISO date string (YYYY-MM-DD)
    - ``bodyweight_kg``    -- float
    - ``grip``             -- exercise-specific variant string
    - ``session_type``     -- one of ``"S"``, ``"H"``, ``"E"``, ``"T"``, ``"TEST"``
    - ``exercise_id``      -- exercise identifier (must match the ``exercise_id`` arg)
    - ``completed_sets``   -- list of set dicts

    Returns the serialised ``SessionResult`` dict that was persisted.
    If no ``equipment_snapshot`` is provided, the current equipment for the
    exercise is read from the profile and attached automatically.
    """
    from ..core.equipment import recommend_equipment_item, snapshot_from_state
    from ..io.serializers import dict_to_session_result

    store = _require_store(data_dir, exercise_id)
    session_obj = dict_to_session_result(session)
    if session_obj.equipment_snapshot is None:
        eq_state = store.load_current_equipment(exercise_id)
        if eq_state is not None:
            ex = get_exercise(exercise_id)
            ustate = store.load_user_state(exercise_id)
            current_tm = _get_training_status(
                ustate.history, ustate.current_bodyweight_kg
            ).training_max
            active_item = recommend_equipment_item(
                eq_state.available_items, ex, current_tm, ustate.history[-10:]
            )
            session_obj.equipment_snapshot = snapshot_from_state(eq_state, active_item)
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
    """
    store = _require_store(data_dir, exercise_id)
    sessions = store.load_history(exercise_id)
    return [session_result_to_dict(s) for s in sessions]
