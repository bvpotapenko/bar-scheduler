"""
Equipment-aware load system.

Each exercise has a catalog of equipment options that affect the effective load
(Leff) applied to the working muscles.  The planner uses Leff -- not raw
bodyweight -- as the common unit for progression tracking across equipment changes.

Equipment data (catalogs, assist_progression) lives in per-exercise YAML files
(src/bar_scheduler/exercises/<id>.yaml) and is loaded via the exercise registry.
Use get_catalog(exercise_id) or get_exercise(exercise_id).equipment directly.

Leff formula
------------
  Pull-up / Dip  :  Leff = BW × bw_fraction + added_weight_kg − assistance_kg
  BSS            :  Leff = BW × 0.71 + added_weight_kg   (bw_fraction=0.71)
  Weight belt    :  assistance_kg = 0; Leff grows via added_weight_kg as usual

Band assistance values are midpoint estimates:
  Light  (10–25 kg)  -> 17 kg
  Medium (25–45 kg)  -> 35 kg
  Heavy  (45–70 kg)  -> 57 kg

References
----------
Bogdanis 1995 (PCr recovery), Harriss & Atkinson 2015 (band force curves),
user-spec v2026-02-24.
"""

from __future__ import annotations

from .exercises.base import ExerciseDefinition
from .exercises.registry import get_exercise
from .models import EquipmentState, EquipmentSnapshot


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_catalog(exercise_id: str) -> dict[str, dict]:
    """Return the equipment catalog for the given exercise.

    The catalog is loaded from the per-exercise YAML file via the exercise
    registry.  Returns {} for unknown exercise IDs.
    """
    try:
        return get_exercise(exercise_id).equipment
    except ValueError:
        return {}


def get_assistance_kg(
    item_id: str,
    exercise_id: str,
    available_machine_assistance_kg: list[float] | None = None,
) -> float:
    """
    Return the assistance kg for an equipment item.

    Positive value = assistive (reduces Leff).
    Zero = neutral or additive.

    For MACHINE_ASSISTED items, returns the maximum value from
    ``available_machine_assistance_kg`` as a conservative fallback (used
    when no target Leff is known, e.g. for historical snapshots where the
    assistance was already resolved at log time).

    Args:
        item_id: Equipment item identifier (e.g. "BAND_MEDIUM")
        exercise_id: Exercise identifier (e.g. "pull_up")
        available_machine_assistance_kg: Discrete assistance levels available

    Returns:
        Assistance in kg (≥ 0)
    """
    catalog = get_catalog(exercise_id)
    if item_id not in catalog:
        return 0.0
    a = catalog[item_id]["assistance_kg"]
    if a is None:
        # MACHINE_ASSISTED: use max of available list (conservative fallback)
        return (
            max(available_machine_assistance_kg)
            if available_machine_assistance_kg
            else 0.0
        )
    return float(a)


def compute_leff(
    bw_fraction: float,
    bodyweight_kg: float,
    added_weight_kg: float,
    assistance_kg: float = 0.0,
) -> float:
    """
    Compute effective load (Leff) in kg.

    Leff = BW × bw_fraction + added_weight_kg − assistance_kg

    Args:
        bw_fraction: Fraction of BW that counts as load (e.g. 1.0 pull-up, 0.71 BSS)
        bodyweight_kg: User's bodyweight
        added_weight_kg: External load added (belt, dumbbells)
        assistance_kg: Assistive force subtracted from load (band, machine)

    Returns:
        Effective load in kg (clamped to ≥ 0)
    """
    leff = bodyweight_kg * bw_fraction + added_weight_kg - assistance_kg
    return max(0.0, leff)


def snapshot_from_state(
    state: EquipmentState,
    active_item: str,
    override_assistance_kg: float | None = None,
) -> EquipmentSnapshot:
    """
    Build an EquipmentSnapshot from the current EquipmentState.

    ``active_item`` is provided explicitly (recommended by ``recommend_equipment_item``).
    Used when logging a session to capture the equipment context.

    ``override_assistance_kg`` bypasses catalog lookup — pass the value computed
    by ``calculate_machine_assistance()`` so the snapshot reflects the actual
    prescription rather than a generic fallback.
    """
    if override_assistance_kg is not None:
        a_kg = override_assistance_kg
    else:
        a_kg = get_assistance_kg(
            active_item,
            state.exercise_id,
            state.available_machine_assistance_kg,
        )
    return EquipmentSnapshot(
        active_item=active_item,
        assistance_kg=a_kg,
    )


def recommend_equipment_item(
    available_items: list[str],
    exercise: ExerciseDefinition,
    current_tm: int,
    recent_history: list,  # list[SessionResult]
) -> str:
    """
    Auto-select the most appropriate equipment item for the next session.

    Selection priority:
    1. WEIGHT_BELT — when TM is above the weight threshold and user has one.
    2. Current assist level from history — step down if check_band_progression passes.
    3. Initial selection — MACHINE_ASSISTED first, then follow assist_progression
       from most-assistive onward.
    4. Fallback — first item in the exercise catalog that the user has.

    Args:
        available_items: Items the user owns (from EquipmentState).
        exercise: ExerciseDefinition for the current exercise.
        current_tm: Current training max (reps).
        recent_history: Recent sessions used for assist-progression check.

    Returns:
        Item ID string (e.g. "WEIGHT_BELT", "BAND_MEDIUM", "BAR_ONLY").
    """
    catalog = get_catalog(exercise.exercise_id)
    assist_progression = exercise.assist_progression

    # 1. Weighted phase: use WEIGHT_BELT when TM has crossed the weight threshold
    if (
        current_tm > exercise.weight_tm_threshold
        and "WEIGHT_BELT" in available_items
        and "WEIGHT_BELT" in catalog
    ):
        return "WEIGHT_BELT"

    # 2. Assist progression: find last item used and check if ready to step down
    last_assist: str | None = None
    for session in reversed(recent_history):
        snap = getattr(session, "equipment_snapshot", None)
        if snap and snap.active_item in assist_progression:
            last_assist = snap.active_item
            break

    if last_assist is not None and last_assist in available_items:
        if check_band_progression(
            recent_history, exercise.exercise_id, exercise.session_params
        ):
            next_item = get_next_band_step(last_assist, assist_progression)
            if (
                next_item is not None
                and next_item in available_items
                and next_item in catalog
            ):
                return next_item
        return last_assist

    # 3. Initial selection: MACHINE_ASSISTED first, then most-assistive in progression
    candidates = ["MACHINE_ASSISTED"] + list(assist_progression)
    for candidate in candidates:
        if candidate in available_items and candidate in catalog:
            return candidate

    # 4. Fallback: first item in the exercise catalog that the user has
    for item in catalog:
        if item in available_items:
            return item

    return list(assist_progression)[-1] if assist_progression else "BAR_ONLY"


def bss_is_degraded(state: EquipmentState) -> bool:
    """
    Return True if BSS should degrade to split squat (no elevation surface).

    When ELEVATION_SURFACE is absent from available_items, the rear foot
    cannot be elevated and the exercise becomes a standard split squat.
    """
    return "ELEVATION_SURFACE" not in state.available_items


def get_next_band_step(item_id: str, assist_progression: list[str]) -> str | None:
    """
    Return the next-less-assistive item in the progression, or None if already at the end.

    Args:
        item_id: Current equipment item ID.
        assist_progression: Ordered list from most-assistive to unassisted
                            (from ExerciseDefinition.assist_progression).

    Returns:
        Next item ID, or None if item_id is already the last step (unassisted).
    """
    if item_id not in assist_progression:
        return None
    idx = assist_progression.index(item_id)
    next_idx = idx + 1
    if next_idx >= len(assist_progression):
        return None
    return assist_progression[next_idx]


def machine_to_nearest_band(machine_kg: float) -> str:
    """
    Map a machine assistance value to the nearest band class.

    Used when switching from MACHINE_ASSISTED to band assistance.
    """
    if machine_kg >= 45.0:
        return "BAND_HEAVY"
    elif machine_kg >= 25.0:
        return "BAND_MEDIUM"
    elif machine_kg >= 10.0:
        return "BAND_LIGHT"
    return "BAR_ONLY"


def check_band_progression(
    history: list,  # list[SessionResult] -- avoid circular import
    exercise_id: str,
    session_params: dict,  # exercise.session_params
    n_sessions: int = 2,
) -> bool:
    """
    Return True if the last n_sessions suggest the user is ready to step down
    one assist level (i.e. they are consistently hitting the reps_max ceiling).

    Criterion: last n non-TEST sessions of the exercise each have at least one
    set where actual_reps >= reps_max for that session type.

    Args:
        history: Full training history (any exercise mix)
        exercise_id: Exercise to check
        session_params: exercise.session_params dict
        n_sessions: How many consecutive sessions must hit the ceiling

    Returns:
        True if assist step-down is recommended
    """
    non_test = [
        s for s in history if s.session_type != "TEST" and s.exercise_id == exercise_id
    ]
    if len(non_test) < n_sessions:
        return False

    recent = non_test[-n_sessions:]
    for session in recent:
        stype = session.session_type
        if stype not in session_params:
            continue
        reps_max = session_params[stype].reps_max
        max_actual = max(
            (
                s.actual_reps
                for s in session.completed_sets
                if s.actual_reps is not None
            ),
            default=0,
        )
        if max_actual < reps_max:
            return False
    return True


def compute_equipment_adjustment(old_leff: float, new_leff: float) -> dict:
    """
    Compute rep adjustment factor when effective load changes between equipment.

    Rules:
      new/old ≥ 1.10 -> reduce reps 20% (safety buffer for load increase)
      new/old ≤ 0.90 -> increase reps proportionally (maintain stimulus)
      otherwise      -> no adjustment

    Args:
        old_leff: Previous effective load in kg
        new_leff: New effective load in kg

    Returns:
        {"reps_factor": float, "description": str}
    """
    if old_leff <= 0:
        return {"reps_factor": 1.0, "description": "no previous Leff -- no adjustment"}

    ratio = new_leff / old_leff

    if ratio >= 1.10:
        pct = round((ratio - 1) * 100)
        return {
            "reps_factor": 0.80,
            "description": f"Leff increased ~{pct}% -> reducing reps by 20% as safety buffer",
        }
    elif ratio <= 0.90:
        factor = round(1.0 / ratio, 2)
        pct = round((factor - 1) * 100)
        return {
            "reps_factor": factor,
            "description": f"Leff decreased ~{round((1-ratio)*100)}% -> increasing reps ~{pct}% to maintain stimulus",
        }
    else:
        return {
            "reps_factor": 1.0,
            "description": "minor Leff change (< 10%) -- no adjustment",
        }
