"""
Track B between-test max estimator.

Uses two independent methods:

  FI Method — Pekünlü & Atalağ 2013 (PMC3827769):
    Fatigue Index characterises within-session fatigue profile.
    FI_reps = 1 − mean(R₂…Rₙ) / R₁
    High FI → person was working close to failure.
    Low FI  → person had reserve (RIR > 0).

  Nuzzo Method — Nuzzo et al. 2024 (PMC10933212):
    REPS~%1RM meta-regression bench press table inverted.
    If you can do R reps at failure, the table says R corresponds to
    roughly X% of your 1RM capacity.  Because bodyweight is fixed,
    "1RM capacity" maps to your fresh single-set maximum.
    nuzzo_est = reps_to_failure / pct_1rm_fraction

  PCr recovery — Bogdanis et al. 1995 (J Appl Physiol 78(2):782-791):
    Table of PCr resynthesis fraction as a function of rest duration.
    Used to adjust estimates for incomplete inter-set recovery.

See docs/references/max_estimation.md for full citations and formulae.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Nuzzo 2024 — REPS~%1RM meta-regression (bench press)
# Table: (pct_1rm, mean_reps, sd_reps)
# Source: PMC10933212, Table 2 / Fig 3 weighted mean regression
# ---------------------------------------------------------------------------
NUZZO_BENCH_TABLE: list[tuple[int, float, float]] = [
    (100,  1.0,  0.0),
    ( 95,  3.0,  1.5),
    ( 90,  5.3,  2.0),
    ( 85,  7.7,  2.5),
    ( 80, 11.0,  4.0),
    ( 75, 13.4,  5.0),
    ( 70, 17.0,  6.0),
    ( 65, 21.0,  7.5),
    ( 60, 25.0,  9.0),
    ( 55, 29.7,  9.5),
    ( 50, 35.0, 10.0),
]

# ---------------------------------------------------------------------------
# Bogdanis 1995 — PCr resynthesis during recovery
# Table: (rest_seconds, fraction_recovered)
# Source: J Appl Physiol 78(2):782-791, Fig 4 (estimated from graph)
# ---------------------------------------------------------------------------
PCR_RECOVERY: list[tuple[int, float]] = [
    (  0, 0.00),
    ( 10, 0.25),
    ( 30, 0.50),
    ( 60, 0.75),
    ( 90, 0.87),
    (120, 0.93),
    (180, 0.97),
    (240, 0.99),
    (300, 1.00),
]


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def _pcr_recovery_factor(rest_seconds: float) -> float:
    """Linear interpolation of PCr recovery fraction (0–1)."""
    if rest_seconds <= 0:
        return 0.0
    if rest_seconds >= PCR_RECOVERY[-1][0]:
        return 1.0
    for i in range(len(PCR_RECOVERY) - 1):
        t0, f0 = PCR_RECOVERY[i]
        t1, f1 = PCR_RECOVERY[i + 1]
        if t0 <= rest_seconds <= t1:
            alpha = (rest_seconds - t0) / (t1 - t0)
            return f0 + alpha * (f1 - f0)
    return 1.0


def _reps_to_pct_1rm(reps_to_failure: float) -> float:
    """
    Inverse Nuzzo lookup: reps-to-failure → %1RM as a fraction (0–1).

    Linear interpolation between adjacent table rows (ascending reps order).
    Returns 1.0 for ≤1 rep and the lowest table value for very high reps.
    """
    if reps_to_failure <= NUZZO_BENCH_TABLE[0][1]:
        return 1.0
    for i in range(len(NUZZO_BENCH_TABLE) - 1):
        pct0, r0, _ = NUZZO_BENCH_TABLE[i]
        pct1, r1, _ = NUZZO_BENCH_TABLE[i + 1]
        if r0 <= reps_to_failure <= r1:
            alpha = (reps_to_failure - r0) / (r1 - r0)
            pct = pct0 + alpha * (pct1 - pct0)
            return pct / 100.0
    # Beyond table range — extrapolate linearly from last two rows
    pct_last, r_last, _ = NUZZO_BENCH_TABLE[-1]
    pct_prev, r_prev, _ = NUZZO_BENCH_TABLE[-2]
    slope = (pct_last - pct_prev) / (r_last - r_prev)  # negative (pct decreases)
    pct_extrap = pct_last + slope * (reps_to_failure - r_last)
    return max(0.1, pct_extrap) / 100.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_max_reps_from_session(
    actual_reps_per_set: list[int],
    rest_before_each_set: list[int],
    rir_reported_per_set: list[int | None] | None = None,
) -> dict | None:
    """
    Estimate fresh max reps from a multi-set training session (Track B).

    Requires ≥ 2 sets with actual_reps > 0.

    Args:
        actual_reps_per_set: Actual reps logged for each completed set.
        rest_before_each_set: Rest in seconds before each set.
        rir_reported_per_set: User-reported RIR per set (may contain None).

    Returns:
        Dict with keys:
          fi_est      — FI-method fresh-max estimate (int)
          nuzzo_est   — Nuzzo-method fresh-max estimate (int)
          fi_reps     — computed fatigue index 0–1 (float, rounded 3 dp)
          confidence  — "high" | "medium" | "low"
        Returns None if there are fewer than 2 sets with reps > 0.
    """
    # Filter to valid sets only
    valid: list[tuple[int, int, int | None]] = []
    for i, r in enumerate(actual_reps_per_set):
        if r > 0:
            rest = rest_before_each_set[i] if i < len(rest_before_each_set) else 180
            rir = (
                rir_reported_per_set[i]
                if rir_reported_per_set and i < len(rir_reported_per_set)
                else None
            )
            valid.append((r, rest, rir))

    if len(valid) < 2:
        return None

    reps = [v[0] for v in valid]
    rests = [v[1] for v in valid]
    rirs = [v[2] for v in valid]

    R1 = reps[0]
    rest_before_R1 = rests[0]  # rest before the session's first set

    # ── FI method ────────────────────────────────────────────────────────────
    subsequent = reps[1:]
    fi_reps: float = 1.0 - (sum(subsequent) / len(subsequent)) / R1 if R1 > 0 else 0.0
    fi_reps = max(0.0, min(1.0, fi_reps))

    # PCr correction for set 1: if the person warmed up and started near-fresh
    # rest_before_R1 == 0 typically means "walked straight to bar after warm-up"
    # Use 180 s as the assumed recovery before a training session if rest == 0
    effective_rest = rest_before_R1 if rest_before_R1 > 0 else 180
    pcr_factor = _pcr_recovery_factor(effective_rest)
    pcr_factor = max(pcr_factor, 0.50)  # clamp: never inflate by more than 2×

    # FI-based fresh max: R1 corrected for PCr, adjusted upward when FI is low
    # (low FI ≡ large reserve ≡ true max > R1)
    adj_R1 = R1 / pcr_factor
    # FI adjustment: at FI=0.35 no correction; below that, slight upward scaling
    fi_adjustment = max(0.0, 0.35 - fi_reps) * 0.6  # ≤ 0.21 extra
    fi_est = round(adj_R1 * (1.0 + fi_adjustment))

    # ── Nuzzo method ─────────────────────────────────────────────────────────
    # Estimate reps-to-failure for R1
    rir1 = rirs[0]
    if rir1 is None:
        # Estimate RIR from FI: high FI → low RIR (near failure); low FI → high RIR
        # At FI=0.30 → RIR≈1; at FI=0.05 → RIR≈3; at FI>0.35 → RIR≈0
        rir1 = max(0, round((0.35 - fi_reps) * 8))

    reps_to_failure = R1 + rir1
    pct_1rm = _reps_to_pct_1rm(float(reps_to_failure))
    if pct_1rm > 0:
        nuzzo_est = round(reps_to_failure / pct_1rm)
    else:
        nuzzo_est = reps_to_failure

    # ── Confidence ───────────────────────────────────────────────────────────
    n_sets = len(reps)
    rir_known = rir_reported_per_set is not None and any(
        r is not None for r in rir_reported_per_set
    )
    if n_sets >= 4 and rir_known:
        confidence = "high"
    elif n_sets >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "fi_est": fi_est,
        "nuzzo_est": nuzzo_est,
        "fi_reps": round(fi_reps, 3),
        "confidence": confidence,
    }
