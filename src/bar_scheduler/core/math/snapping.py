"""Snapping prescribed loads/assistance to discrete available equipment."""


def apply_rounding(raw: float) -> float:
    """Round to nearest 0.5 kg."""
    return round(raw * 2) / 2


def apply_cap(load_kg: float, max_kg: float) -> float:
    """Clamp to the exercise maximum."""
    return min(load_kg, max_kg)


def expand_dual_dumbbell_totals(available: list[float]) -> list[float]:
    """All achievable totals for a dual-dumbbell set (singles + same/mixed pairs).

    e.g. [8, 10, 16] -> [8, 10, 16, 18, 20, 24, 26, 32].
    """
    totals: set[float] = set(available)
    for idx, weight_a in enumerate(available):
        for weight_b in available[idx:]:
            totals.add(weight_a + weight_b)
    return sorted(totals)


def snap_to_available(weight_kg: float, available: list[float]) -> float:
    """Floor-snap to the largest available <= weight_kg (smallest if below all)."""
    below = [wt for wt in available if wt <= weight_kg]
    return max(below) if below else min(available)


def ceiling_snap_assistance(assistance_kg: float, available: list[float]) -> float:
    """Ceiling-snap to the smallest available >= assistance_kg (largest if above all)."""
    above = [avail for avail in available if avail >= assistance_kg]
    return min(above) if above else max(available)


def snap_added(added: float, available: tuple[float, ...], dual_dumbbell: bool) -> float:
    """Snap an added-weight prescription to available weights, or round to 0.5 kg."""
    if not available:
        return apply_rounding(added)
    snap_list = expand_dual_dumbbell_totals(list(available)) if dual_dumbbell else list(available)
    return snap_to_available(added, snap_list)
