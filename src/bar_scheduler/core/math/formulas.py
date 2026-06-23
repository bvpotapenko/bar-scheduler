"""1RM estimation formulas (pure; load is total effective kg)."""


def epley_onerm(total_load_kg: float, reps: int) -> float:
    """1RM = w * (1 + reps/30)  (Epley)."""
    if reps <= 0:
        return 0.0
    return total_load_kg * (1 + reps / 30)


def lombardi_onerm(total_load_kg: float, reps: int) -> float:
    """1RM = w * r^0.10  (Lombardi; handles higher-rep sets better than Epley)."""
    if reps <= 0:
        return 0.0
    return total_load_kg * (reps**0.10)


def brzycki_onerm(total_load_kg: float, reps: int) -> float:
    """1RM = w / (1.0278 - 0.0278 * r)  (Brzycki; accurate for r <= 10)."""
    if reps <= 0:
        return 0.0
    denom = 1.0278 - 0.0278 * reps
    if denom <= 0:
        return float("inf")
    return total_load_kg / denom


def lander_onerm(total_load_kg: float, reps: int) -> float:
    """1RM = 100 * w / (101.3 - 2.67123 * r)  (Lander; accurate for r <= 10)."""
    if reps <= 0:
        return 0.0
    denom = 101.3 - 2.67123 * reps
    if denom <= 0:
        return float("inf")
    return (100.0 * total_load_kg) / denom


def _blend(load: float, reps: int, formulas: tuple) -> float:
    """Mean of the given 1RM formulas at (load, reps)."""
    return sum(formula(load, reps) for formula in formulas) / len(formulas)


def best_onerm_from_leff(leff: float, reps: int) -> float | None:
    """
    Rep-range-aware total 1RM estimate in Leff units (works for any set).

        r <= 5   -> avg(Brzycki, Lander)
        r <= 10  -> avg(Brzycki, Lander, Epley)
        r > 10   -> avg(Lombardi, Epley)
    """
    if reps <= 0:
        return None
    if reps <= 5:
        return _blend(leff, reps, (brzycki_onerm, lander_onerm))
    if reps <= 10:
        return _blend(leff, reps, (brzycki_onerm, lander_onerm, epley_onerm))
    return _blend(leff, reps, (lombardi_onerm, epley_onerm))


def blended_onerm_added(bw_load_kg: float, reps: int) -> float | None:
    """Rep-range-aware 1RM returning ADDED kg only (total - bw_load); None if r>20."""
    if reps <= 0 or reps > 20:
        return None
    total = best_onerm_from_leff(bw_load_kg, reps)
    return max(0.0, total - bw_load_kg)
