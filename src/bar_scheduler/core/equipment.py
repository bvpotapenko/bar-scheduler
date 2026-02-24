"""
Equipment-aware load system.

Each exercise has a catalog of equipment options that affect the effective load
(Leff) applied to the working muscles.  The planner uses Leff — not raw
bodyweight — as the common unit for progression tracking across equipment changes.

Leff formula
------------
  Pull-up / Dip  :  Leff = BW × bw_fraction + added_weight_kg − assistance_kg
  BSS            :  Leff = BW × 0.71 + added_weight_kg   (bw_fraction=0.71)
  Weight belt    :  assistance_kg = 0; Leff grows via added_weight_kg as usual

Band assistance values are midpoint estimates:
  Light  (10–25 kg)  → 17 kg
  Medium (25–45 kg)  → 35 kg
  Heavy  (45–70 kg)  → 57 kg

References
----------
Bogdanis 1995 (PCr recovery), Harriss & Atkinson 2015 (band force curves),
user-spec v2026-02-24.
"""

from __future__ import annotations

from .models import EquipmentState, EquipmentSnapshot


# ---------------------------------------------------------------------------
# Equipment catalogs
# Each item: {label, assistance_kg}
#   assistance_kg > 0 → assistive (band/machine reduces Leff)
#   assistance_kg = None → user enters value (MACHINE_ASSISTED)
#   assistance_kg = 0 → neutral / additive (BAR_ONLY, WEIGHT_BELT, BSS items)
# ---------------------------------------------------------------------------

PULL_UP_EQUIPMENT: dict[str, dict] = {
    "BAR_ONLY": {
        "label": "Pull-up bar (bodyweight)",
        "assistance_kg": 0.0,
    },
    "BAND_LIGHT": {
        "label": "Resistance band – Light (~10–25 kg assistance)",
        "assistance_kg": 17.0,
    },
    "BAND_MEDIUM": {
        "label": "Resistance band – Medium (~25–45 kg assistance)",
        "assistance_kg": 35.0,
    },
    "BAND_HEAVY": {
        "label": "Resistance band – Heavy (~45–70 kg assistance)",
        "assistance_kg": 57.0,
    },
    "MACHINE_ASSISTED": {
        "label": "Assisted pull-up machine (direct kg offset)",
        "assistance_kg": None,  # user enters machine_assistance_kg
    },
    "WEIGHT_BELT": {
        "label": "Weight belt / vest (for added load)",
        "assistance_kg": 0.0,  # additive — weight comes from added_weight_kg
    },
}

DIP_EQUIPMENT: dict[str, dict] = {
    "PARALLEL_BARS": {
        "label": "Parallel bars (bodyweight)",
        "assistance_kg": 0.0,
    },
    "BAND_LIGHT": {
        "label": "Resistance band – Light (~10–25 kg assistance)",
        "assistance_kg": 17.0,
    },
    "BAND_MEDIUM": {
        "label": "Resistance band – Medium (~25–45 kg assistance)",
        "assistance_kg": 35.0,
    },
    "BAND_HEAVY": {
        "label": "Resistance band – Heavy (~45–70 kg assistance)",
        "assistance_kg": 57.0,
    },
    "MACHINE_ASSISTED": {
        "label": "Assisted dip machine (direct kg offset)",
        "assistance_kg": None,
    },
    "WEIGHT_BELT": {
        "label": "Weight belt / vest (for added load)",
        "assistance_kg": 0.0,
    },
}

# For BSS all items are either neutral or additive — no band-assist concept.
# ELEVATION_SURFACE is required for true Bulgarian Split Squat (rear foot
# elevated); without it the exercise degrades to a flat split squat.
BSS_EQUIPMENT: dict[str, dict] = {
    "BODYWEIGHT": {
        "label": "Bodyweight only",
        "assistance_kg": 0.0,
    },
    "DUMBBELLS": {
        "label": "Dumbbells / Kettlebells",
        "assistance_kg": 0.0,
    },
    "BARBELL": {
        "label": "Barbell (back or front rack)",
        "assistance_kg": 0.0,
    },
    "RESISTANCE_BAND": {
        "label": "Resistance band (added tension at the top)",
        "assistance_kg": 0.0,  # additive for BSS
    },
    "ELEVATION_SURFACE": {
        "label": "Bench / chair / box for rear foot",
        "assistance_kg": 0.0,
    },
}

# Map exercise_id → catalog
_CATALOGS: dict[str, dict[str, dict]] = {
    "pull_up": PULL_UP_EQUIPMENT,
    "dip": DIP_EQUIPMENT,
    "bss": BSS_EQUIPMENT,
}

# BSS elevation height options (cm)
BSS_ELEVATION_HEIGHTS: list[int] = [30, 45, 60]

# Band progression order: index 0 = most assistive → last = no band
BAND_PROGRESSION: list[str] = ["BAND_HEAVY", "BAND_MEDIUM", "BAND_LIGHT", "BAR_ONLY"]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_catalog(exercise_id: str) -> dict[str, dict]:
    """Return the equipment catalog for the given exercise."""
    return _CATALOGS.get(exercise_id, {})


def get_assistance_kg(
    item_id: str,
    exercise_id: str,
    machine_assistance_kg: float | None = None,
) -> float:
    """
    Return the assistance kg for an equipment item.

    Positive value = assistive (reduces Leff).
    Zero = neutral or additive.

    Args:
        item_id: Equipment item identifier (e.g. "BAND_MEDIUM")
        exercise_id: Exercise identifier (e.g. "pull_up")
        machine_assistance_kg: User-entered assistance for MACHINE_ASSISTED items

    Returns:
        Assistance in kg (≥ 0)
    """
    catalog = get_catalog(exercise_id)
    if item_id not in catalog:
        return 0.0
    a = catalog[item_id]["assistance_kg"]
    if a is None:
        # MACHINE_ASSISTED: user-entered value
        return float(machine_assistance_kg) if machine_assistance_kg is not None else 0.0
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
) -> EquipmentSnapshot:
    """
    Build an EquipmentSnapshot from the current EquipmentState.

    Used when logging a session to capture the equipment context.
    """
    a_kg = get_assistance_kg(
        state.active_item,
        state.exercise_id,
        state.machine_assistance_kg,
    )
    return EquipmentSnapshot(
        active_item=state.active_item,
        assistance_kg=a_kg,
        elevation_height_cm=state.elevation_height_cm,
    )


def bss_is_degraded(state: EquipmentState) -> bool:
    """
    Return True if BSS should degrade to split squat (no elevation surface).

    When ELEVATION_SURFACE is absent from available_items, the rear foot
    cannot be elevated and the exercise becomes a standard split squat.
    """
    return "ELEVATION_SURFACE" not in state.available_items


def get_next_band_step(item_id: str) -> str | None:
    """
    Return the next-less-assistive band class, or None if already unassisted.

    BAND_HEAVY → BAND_MEDIUM → BAND_LIGHT → BAR_ONLY → None
    """
    if item_id not in BAND_PROGRESSION:
        return None
    idx = BAND_PROGRESSION.index(item_id)
    next_idx = idx + 1
    if next_idx >= len(BAND_PROGRESSION):
        return None
    return BAND_PROGRESSION[next_idx]


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
    history: list,  # list[SessionResult] — avoid circular import
    exercise_id: str,
    session_params: dict,  # exercise.session_params
    n_sessions: int = 2,
) -> bool:
    """
    Return True if the last n_sessions suggest the user is ready to step down
    one band class (i.e. they are consistently hitting the reps_max ceiling).

    Criterion: last n non-TEST sessions of the exercise each have at least one
    set where actual_reps >= reps_max for that session type.

    Args:
        history: Full training history (any exercise mix)
        exercise_id: Exercise to check
        session_params: exercise.session_params dict
        n_sessions: How many consecutive sessions must hit the ceiling

    Returns:
        True if band progression is recommended
    """
    non_test = [
        s for s in history
        if s.session_type != "TEST" and s.exercise_id == exercise_id
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
            (s.actual_reps for s in session.completed_sets if s.actual_reps is not None),
            default=0,
        )
        if max_actual < reps_max:
            return False
    return True


def compute_equipment_adjustment(old_leff: float, new_leff: float) -> dict:
    """
    Compute rep adjustment factor when effective load changes between equipment.

    Rules:
      new/old ≥ 1.10 → reduce reps 20% (safety buffer for load increase)
      new/old ≤ 0.90 → increase reps proportionally (maintain stimulus)
      otherwise      → no adjustment

    Args:
        old_leff: Previous effective load in kg
        new_leff: New effective load in kg

    Returns:
        {"reps_factor": float, "description": str}
    """
    if old_leff <= 0:
        return {"reps_factor": 1.0, "description": "no previous Leff — no adjustment"}

    ratio = new_leff / old_leff

    if ratio >= 1.10:
        pct = round((ratio - 1) * 100)
        return {
            "reps_factor": 0.80,
            "description": f"Leff increased ~{pct}% → reducing reps by 20% as safety buffer",
        }
    elif ratio <= 0.90:
        factor = round(1.0 / ratio, 2)
        pct = round((factor - 1) * 100)
        return {
            "reps_factor": factor,
            "description": f"Leff decreased ~{round((1-ratio)*100)}% → increasing reps ~{pct}% to maintain stimulus",
        }
    else:
        return {"reps_factor": 1.0, "description": "minor Leff change (< 10%) — no adjustment"}
