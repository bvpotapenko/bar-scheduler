"""FI + Nuzzo fresh-max estimation math (reps -> %1RM tables)."""

from bar_scheduler.core.math.interpolation import extrapolate_linear, interpolate

# Nuzzo 2024 reps~%1RM bench-press regression: (pct_onerm, mean_reps, sd).
NUZZO_BENCH_TABLE: list[tuple[int, float, float]] = [
    (100, 1.0, 0.0),
    (95, 3.0, 1.5),
    (90, 5.3, 2.0),
    (85, 7.7, 2.5),
    (80, 11.0, 4.0),
    (75, 13.4, 5.0),
    (70, 17.0, 6.0),
    (65, 21.0, 7.5),
    (60, 25.0, 9.0),
    (55, 29.7, 9.5),
    (50, 35.0, 10.0),
]
# Bogdanis 1995 PCr resynthesis: (rest_seconds, fraction_recovered).
PCR_RECOVERY: list[tuple[int, float]] = [
    (0, 0.0),
    (10, 0.25),
    (30, 0.5),
    (60, 0.75),
    (90, 0.87),
    (120, 0.93),
    (180, 0.97),
    (240, 0.99),
    (300, 1.0),
]

# (reps, pct) ascending by reps, and (rest, fraction) for table interpolation.
_REPS_TO_PCT = [(reps, float(pct)) for pct, reps, _sd in NUZZO_BENCH_TABLE]
_PCR_POINTS = [(float(rest), frac) for rest, frac in PCR_RECOVERY]


def _reps_to_pct(reps_to_failure: float) -> float:
    """Inverse Nuzzo lookup: reps-to-failure -> %1RM fraction (0-1)."""
    if reps_to_failure >= _REPS_TO_PCT[-1][0]:
        return max(0.1, extrapolate_linear(_REPS_TO_PCT, reps_to_failure)) / 100.0
    return interpolate(_REPS_TO_PCT, reps_to_failure) / 100.0


def fi_max_estimate(first_reps: int, rest_before_first: int, fi_reps: float) -> int:
    """FI-method fresh max: R1 corrected for PCr, scaled up when FI is low."""
    effective_rest = rest_before_first if rest_before_first > 0 else 180
    pcr_factor = max(interpolate(_PCR_POINTS, effective_rest), 0.50)
    fi_adjustment = max(0.0, 0.35 - fi_reps) * 0.6
    return round((first_reps / pcr_factor) * (1.0 + fi_adjustment))


def nuzzo_max_estimate(first_reps: int, rirs: list[int | None], fi_reps: float) -> int:
    """Nuzzo-method fresh max via the inverted reps~%1RM lookup."""
    rir1 = rirs[0]
    if rir1 is None:
        rir1 = max(0, round((0.35 - fi_reps) * 8))
    reps_to_failure = first_reps + rir1
    pct = _reps_to_pct(float(reps_to_failure))
    return round(reps_to_failure / pct) if pct > 0 else reps_to_failure
