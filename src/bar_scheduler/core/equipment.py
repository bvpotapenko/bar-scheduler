"""
Equipment-aware load system.

Each exercise has a catalog of equipment options that affect the effective load
(Leff) applied to the working muscles.  The planner uses Leff -- not raw
bodyweight -- as the common unit for progression tracking across equipment changes.

Equipment data (catalogs) lives in per-exercise YAML files
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
    available_band_assistance_kg: list[float] | None = None,
) -> float:
    """
    Return the assistance kg for an equipment item.

    Positive value = assistive (reduces Leff).
    Zero = neutral or additive.

    For items with ``assistance_kg: null`` (MACHINE_ASSISTED, BAND_SET),
    returns the maximum value from the corresponding available list as a
    conservative fallback (used when no target Leff is known, e.g. for
    historical snapshots where the assistance was already resolved at log time).

    Args:
        item_id: Equipment item identifier (e.g. "BAND_SET")
        exercise_id: Exercise identifier (e.g. "pull_up")
        available_machine_assistance_kg: Discrete machine assistance levels
        available_band_assistance_kg: Discrete band resistance values

    Returns:
        Assistance in kg (≥ 0)
    """
    catalog = get_catalog(exercise_id)
    if item_id not in catalog:
        return 0.0
    a = catalog[item_id]["assistance_kg"]
    if a is None:
        if item_id == "BAND_SET":
            return max(available_band_assistance_kg) if available_band_assistance_kg else 0.0
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
    by ``calculate_machine_assistance()`` / ``calculate_band_assistance()`` so the
    snapshot reflects the actual prescription rather than a generic fallback.
    """
    if override_assistance_kg is not None:
        a_kg = override_assistance_kg
    else:
        a_kg = get_assistance_kg(
            active_item,
            state.exercise_id,
            state.available_machine_assistance_kg,
            state.available_band_assistance_kg,
        )
    return EquipmentSnapshot(
        active_item=active_item,
        assistance_kg=a_kg,
    )


def recommend_equipment_item(
    available_items: list[str],
    exercise: ExerciseDefinition,
    current_tm: int,
) -> str:
    """
    Auto-select the most appropriate equipment item for the next session.

    Selection priority:
    1. WEIGHT_BELT — when TM is above the weight threshold and user has one.
    2. Assisted items — MACHINE_ASSISTED, then BAND_SET (same ceiling-snap model,
       no automatic step-down; user updates available_items to graduate).
    3. Fallback — first item in the exercise catalog that the user has.

    Args:
        available_items: Items the user owns (from EquipmentState).
        exercise: ExerciseDefinition for the current exercise.
        current_tm: Current training max (reps).

    Returns:
        Item ID string (e.g. "WEIGHT_BELT", "BAND_SET", "BAR_ONLY").
    """
    catalog = get_catalog(exercise.exercise_id)

    # 1. Weighted phase: use WEIGHT_BELT when TM has crossed the weight threshold
    if (
        current_tm > exercise.weight_tm_threshold
        and "WEIGHT_BELT" in available_items
        and "WEIGHT_BELT" in catalog
    ):
        return "WEIGHT_BELT"

    # 2. Assisted items: MACHINE_ASSISTED and BAND_SET use the same model
    for candidate in ("MACHINE_ASSISTED", "BAND_SET"):
        if candidate in available_items and candidate in catalog:
            return candidate

    # 3. Fallback: first item in the exercise catalog that the user has
    for item in catalog:
        if item in available_items:
            return item

    return "BAR_ONLY"


def bss_is_degraded(state: EquipmentState) -> bool:
    """
    Return True if BSS should degrade to split squat (no elevation surface).

    When ELEVATION_SURFACE is absent from available_items, the rear foot
    cannot be elevated and the exercise becomes a standard split squat.
    """
    return "ELEVATION_SURFACE" not in state.available_items


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
