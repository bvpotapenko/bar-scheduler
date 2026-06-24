"""1RM estimation formulas (pure; load is total effective kg)."""

# Published formula coefficients, named to keep the math readable.
_EPLEY_REP_DENOM = 30
_LOMBARDI_EXPONENT = 0.1
_BRZYCKI_A = 1.0278
_BRZYCKI_B = 0.0278
_LANDER_A = 101.3
_LANDER_B = 2.67123
_LANDER_SCALE = 100.0
_MAX_ADDED_REPS = 20


def epley_onerm(total_load_kg: float, reps: int) -> float:
    """1RM = w * (1 + reps/30)  (Epley)."""
    if reps <= 0:
        return 0.0
    return total_load_kg * (1 + reps / _EPLEY_REP_DENOM)


def lombardi_onerm(total_load_kg: float, reps: int) -> float:
    """1RM = w * r^0.1  (Lombardi; handles higher-rep sets better than Epley)."""
    if reps <= 0:
        return 0.0
    return total_load_kg * (reps**_LOMBARDI_EXPONENT)


def brzycki_onerm(total_load_kg: float, reps: int) -> float:
    """1RM = w / (1.0278 - 0.0278 * r)  (Brzycki; accurate for r <= 10)."""
    if reps <= 0:
        return 0.0
    denom = _BRZYCKI_A - _BRZYCKI_B * reps
    if denom <= 0:
        return float("inf")
    return total_load_kg / denom


def lander_onerm(total_load_kg: float, reps: int) -> float:
    """1RM = 100 * w / (101.3 - 2.67123 * r)  (Lander; accurate for r <= 10)."""
    if reps <= 0:
        return 0.0
    denom = _LANDER_A - _LANDER_B * reps
    if denom <= 0:
        return float("inf")
    return (_LANDER_SCALE * total_load_kg) / denom


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
    if reps <= 0 or reps > _MAX_ADDED_REPS:
        return None
    total = best_onerm_from_leff(bw_load_kg, reps)
    return max(0.0, total - bw_load_kg)
