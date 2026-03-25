"""Equipment management functions for the bar-scheduler API."""
from __future__ import annotations

from pathlib import Path

from ..core.adaptation import get_training_status as _get_training_status
from ..core.exercises.registry import get_exercise
from ._common import _require_profile_store, _require_store


def update_equipment(
    data_dir: Path,
    exercise_id: str,
    *,
    available_items: list[str],
    machine_assistance_kg: float | None = None,
    elevation_height_cm: int | None = None,
    valid_from: str | None = None,
    available_weights_kg: list[float] | None = None,
) -> None:
    """
    Update the equipment available for an exercise.

    The planner auto-selects the appropriate item from ``available_items``
    based on the user's current training level — no manual ``active_item``
    required.

    ``available_weights_kg`` is an optional list of discrete dumbbell / plate
    weights (in kg) the user owns for this exercise.  When set, the planner
    floor-snaps weight prescriptions to the largest available weight ≤ the
    computed ideal.  Pass ``[]`` to revert to continuous 0.5 kg rounding.
    Pass ``None`` (default) to leave the value unchanged from the previous
    equipment entry.

    The previous entry is automatically closed (valid_until = yesterday).
    Raises ``ProfileNotFoundError`` / ``HistoryNotFoundError`` if not initialised.
    """
    from ..core.models import EquipmentState

    store = _require_store(data_dir, exercise_id)

    # Inherit available_weights_kg from the previous entry when not supplied
    if available_weights_kg is None:
        prev = store.load_current_equipment(exercise_id)
        inherited = prev.available_weights_kg if prev is not None else []
    else:
        inherited = list(available_weights_kg)

    state = EquipmentState(
        exercise_id=exercise_id,
        available_items=list(available_items),
        machine_assistance_kg=machine_assistance_kg,
        elevation_height_cm=elevation_height_cm,
        valid_from=valid_from or "",
        available_weights_kg=inherited,
    )
    store.update_equipment(state)


def get_current_equipment(data_dir: Path, exercise_id: str) -> dict | None:
    """
    Return the currently configured equipment for an exercise as a plain dict.

    Returns ``None`` if no equipment has been configured.  The dict includes
    computed fields: ``recommended_item`` (auto-selected from available_items
    based on current training level), ``assistance_kg`` (from catalog), and
    ``is_bss_degraded`` (True when ``ELEVATION_SURFACE`` is absent from
    ``available_items``).
    Raises ``ProfileNotFoundError`` if the profile has not been initialised.
    """
    from ..core.equipment import (
        get_assistance_kg as _get_assistance_kg,
        recommend_equipment_item,
    )

    store = _require_store(data_dir, exercise_id)
    state = store.load_current_equipment(exercise_id)
    if state is None:
        return None
    ex = get_exercise(exercise_id)
    user_state = store.load_user_state(exercise_id)
    current_tm = _get_training_status(
        user_state.history, user_state.current_bodyweight_kg
    ).training_max
    recommended = recommend_equipment_item(
        state.available_items, ex, current_tm, user_state.history[-10:]
    )
    return {
        "exercise_id": state.exercise_id,
        "recommended_item": recommended,
        "available_items": list(state.available_items),
        "machine_assistance_kg": state.machine_assistance_kg,
        "elevation_height_cm": state.elevation_height_cm,
        "assistance_kg": _get_assistance_kg(
            recommended, state.exercise_id, state.machine_assistance_kg
        ),
        "is_bss_degraded": "ELEVATION_SURFACE" not in state.available_items,
    }


def check_band_progression(
    data_dir: Path, exercise_id: str, n_sessions: int = 2
) -> bool:
    """
    Return ``True`` if the last ``n_sessions`` suggest the user is ready to
    step down one band class (consistently hitting the reps_max ceiling).

    Returns ``False`` if there is not enough history.
    Raises ``ProfileNotFoundError`` if the profile has not been initialised.
    Raises ``HistoryNotFoundError`` if the exercise has not been initialised.
    """
    from ..core.equipment import check_band_progression as _check

    store = _require_store(data_dir, exercise_id)
    history = store.load_history(exercise_id)
    ex = get_exercise(exercise_id)
    return _check(history, exercise_id, ex.session_params, n_sessions)


def compute_leff(
    bw_fraction: float,
    bodyweight_kg: float,
    added_weight_kg: float,
    assistance_kg: float = 0.0,
) -> float:
    """
    Compute effective load (Leff) in kg.

    ``Leff = BW × bw_fraction + added_weight_kg − assistance_kg`` (≥ 0).
    """
    from ..core.equipment import compute_leff as _compute_leff

    return _compute_leff(bw_fraction, bodyweight_kg, added_weight_kg, assistance_kg)


def compute_equipment_adjustment(old_leff: float, new_leff: float) -> dict:
    """
    Compute rep adjustment factor when effective load changes between equipment.

    Returns ``{"reps_factor": float, "description": str}``.
    """
    from ..core.equipment import compute_equipment_adjustment as _compute

    return _compute(old_leff, new_leff)


def get_assistance_kg(
    exercise_id: str,
    item_id: str,
    machine_assistance_kg: float | None = None,
) -> float:
    """
    Return the assistance in kg for an equipment item.

    Positive value = assistive (reduces Leff); zero = neutral or additive.
    """
    from ..core.equipment import get_assistance_kg as _get

    return _get(item_id, exercise_id, machine_assistance_kg)


def get_next_band_step(item_id: str, exercise_id: str) -> str | None:
    """
    Return the next-less-assistive item ID for the given exercise, or ``None``
    if ``item_id`` is already the last step in the progression.

    The progression order is defined per exercise in its YAML file
    (``assist_progression`` field).
    """
    from ..core.equipment import get_next_band_step as _get
    from ..core.exercises.registry import get_exercise

    try:
        ap = get_exercise(exercise_id).assist_progression
    except ValueError:
        ap = []
    return _get(item_id, ap)


def get_assist_progression(exercise_id: str) -> list[str]:
    """
    Return the ordered assist-progression list for the given exercise
    (most-assistive to unassisted).

    Empty list if the exercise has no assistive equipment progression.
    """
    from ..core.exercises.registry import get_exercise

    try:
        return list(get_exercise(exercise_id).assist_progression)
    except ValueError:
        return []
