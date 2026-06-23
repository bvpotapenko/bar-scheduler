"""Equipment data models."""

from dataclasses import dataclass, field


@dataclass
class EquipmentSnapshot:
    """
    Minimal equipment context stored on each logged session.

    Captured at log time from the current EquipmentState so that past
    sessions can be re-analysed with the correct effective load even after
    the user changes equipment later.

    assistance_kg > 0 means the equipment is assistive (band/machine reduces
    the effective load).  For additive items (weight belt, dumbbells) this is
    0; the load contribution comes from SetResult.added_weight_kg instead.
    """

    active_item: str  # e.g. "BAND_SET", "BAR_ONLY"
    assistance_kg: float  # kg of assistance subtracted from Leff


@dataclass
class EquipmentState:
    """
    Per-exercise equipment configuration.

    Stored as a single current entry per exercise in profile.json.
    Updating equipment overwrites the previous state.
    """

    exercise_id: str
    available_items: list[str]  # all items the user owns / has access to
    available_weights_kg: list[float] = field(default_factory=list)
    # Discrete dumbbell / plate weights the user owns. Empty = continuous
    # (0.5 kg rounding); when set, planner floor-snaps to the largest ≤ ideal.
    available_machine_assistance_kg: list[float] = field(default_factory=list)
    # Discrete machine assistance levels; planner ceiling-snaps to smallest ≥ ideal.
    available_band_assistance_kg: list[float] = field(default_factory=list)
    # Discrete band resistance values; same ceiling-snap model as machine.
