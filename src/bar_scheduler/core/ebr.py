"""
EBR (Equivalent Bodyweight Reps) — user-facing strength and volume metrics.

Three independent metrics replace the internal Banister training-load for
user-facing displays:

  EBR         — session volume: how hard was this session?
  Capability  — current strength: what can I do right now?
  Progress %  — goal proximity: how close am I to my goal? (nonlinear)

Formulas
--------
Shared:
  L_eff      = bw_fraction × BW + added_weight_kg
  load_ratio = L_eff / BW

EBR per set:
  rest_penalty = max(1, 1 + REST_RHO × exp(-(rest_sec − 20) / REST_TAU))
    → first set (rest_sec == 0): rest_penalty = 1.0 (fresh state)
  EBR_set = reps × (load_ratio ^ EBR_ALPHA) × rest_penalty

Session EBR:
  EBR_session = Σ EBR_set
  kg_eq       = BW × EBR_session   (absolute equivalent for cross-user comparison)

Capability (from best Epley 1RM across all history):
  one_rm_leff = max over history: L_eff × (1 + reps / 30)   [Epley]

Goal metrics (requires a goal to be set):
  goal_leff        = bw_fraction × BW + goal_weight_kg
  max_reps_at_goal = max(0, 30 × (one_rm_leff / goal_leff − 1))   [Epley inverse]
  EBR_goal         = goal_reps × (goal_leff / BW) ^ EBR_ALPHA
  EBR_cap_at_goal  = max_reps_at_goal × (goal_leff / BW) ^ EBR_ALPHA

Progress (log-based, nonlinear — reps_base = 1):
  progress = clamp(log(max_reps_at_goal) / log(goal_reps), 0, 1)
  difficulty_ratio = EBR_goal / EBR_cap_at_goal  (>1 = goal harder than now)

References
----------
- Epley (1985): 1RM estimation formula
- Harman et al. (1990): biomechanical basis for bw_fraction in L_eff
- Newell & Rosenbloom (1981): power-law learning curves (basis for log progress)
"""
from __future__ import annotations

import math

from .config import EBR_ALPHA, EBR_BASE, REST_RHO, REST_TAU


def _rest_penalty(rest_seconds: int, *, is_first_set: bool = False) -> float:
    """Return the rest-penalty multiplier for a set.

    Short rest between sets increases effective stress.  The first set of a
    session is always fresh (penalty = 1.0) regardless of rest_seconds.

    Formula:
        rest_penalty = max(1, 1 + REST_RHO × exp(-(rest_sec − 20) / REST_TAU))

    Args:
        rest_seconds: Seconds of rest before this set.
        is_first_set: True for the first set of a session (forces penalty = 1.0).

    Returns:
        Multiplier ≥ 1.0.
    """
    if is_first_set or rest_seconds == 0:
        return 1.0
    raw = 1.0 + REST_RHO * math.exp(-(rest_seconds - 20) / REST_TAU)
    return max(1.0, raw)


def compute_set_ebr_value(
    reps: int,
    leff: float,
    bw: float,
    rest_seconds: int,
    *,
    is_first_set: bool = False,
) -> float:
    """Compute EBR for a single set.

    EBR_set = reps × (L_eff / BW) ^ EBR_ALPHA × rest_penalty

    Args:
        reps: Reps performed.
        leff: Effective load in kg (bw_fraction × BW + added_weight).
        bw: Session bodyweight in kg.
        rest_seconds: Rest before this set in seconds.
        is_first_set: If True, rest_penalty is forced to 1.0.

    Returns:
        EBR value for the set (float ≥ 0).
    """
    if reps <= 0 or bw <= 0 or leff <= 0:
        return 0.0
    load_ratio = leff / bw
    penalty = _rest_penalty(rest_seconds, is_first_set=is_first_set)
    return reps * (load_ratio ** EBR_ALPHA) * penalty


def compute_session_ebr(
    completed_sets: list,
    bw_fraction: float,
    bodyweight_kg: float,
    assistance_kg: float = 0.0,
) -> tuple[float, float]:
    """Compute total EBR and kg-equivalent for a session.

    Args:
        completed_sets: List of SetResult objects (from SessionResult.completed_sets).
        bw_fraction: Exercise bodyweight fraction (from ExerciseDefinition).
        bodyweight_kg: Bodyweight recorded for the session.
        assistance_kg: Band/machine assistance subtracted from L_eff.

    Returns:
        Tuple of (ebr_session, kg_eq) — both rounded to 2 decimal places.
        ebr_session: Sum of EBR across all sets.
        kg_eq: bodyweight × ebr_session (absolute equivalent in kg-reps).
    """
    total = 0.0
    for i, s in enumerate(completed_sets):
        reps = s.actual_reps
        if not reps or reps < 1:
            continue
        added = s.added_weight_kg or 0.0
        leff = max(0.0, bodyweight_kg * bw_fraction + added - assistance_kg)
        total += compute_set_ebr_value(
            reps,
            leff,
            bodyweight_kg,
            s.rest_seconds_before,
            is_first_set=(i == 0),
        )
    kg_eq = bodyweight_kg * total
    return round(total, 2), round(kg_eq, 2)


def compute_capability(
    history: list,
    bw_fraction: float,
    current_bw: float,
) -> float | None:
    """Estimate current Leff 1RM (Epley) from all historical sets.

    Delegates to the same logic used by the weight-prescription planner
    (_estimate_effective_leff_1rm) but inline here to avoid coupling this
    pure module to the planner package.

    Returns:
        Best Leff 1RM estimate in kg, or None if no usable history.
    """
    candidates: list[float] = []
    for session in history:
        assistance = (
            session.equipment_snapshot.assistance_kg
            if session.equipment_snapshot is not None
            else 0.0
        )
        for s in session.completed_sets:
            if not s.actual_reps or s.actual_reps < 1:
                continue
            leff = max(
                0.0,
                session.bodyweight_kg * bw_fraction
                + (s.added_weight_kg or 0.0)
                - assistance,
            )
            if leff > 0:
                candidates.append(leff * (1 + s.actual_reps / 30))
    return max(candidates) if candidates else None


def compute_goal_metrics(
    one_rm_leff: float,
    goal_reps: int,
    goal_leff: float,
    bw: float,
) -> dict:
    """Compute all goal-related EBR metrics from a known 1RM.

    Args:
        one_rm_leff: Best Leff 1RM estimate (from compute_capability).
        goal_reps: Target rep count at goal weight.
        goal_leff: Effective load at goal weight (bw_fraction × BW + goal_weight_kg).
        bw: Current bodyweight in kg.

    Returns:
        Dict with:
          max_reps_at_goal  — predicted reps at goal weight right now
          ebr_goal          — EBR of hitting the goal exactly
          ebr_cap_at_goal   — EBR the user can currently produce at goal weight
          progress_pct      — 0–100 (log-based, nonlinear)
          difficulty_ratio  — EBR_goal / EBR_cap_at_goal (>1 = goal harder)
    """
    if goal_leff <= 0 or bw <= 0 or one_rm_leff <= 0:
        return {
            "max_reps_at_goal": 0.0,
            "ebr_goal": 0.0,
            "ebr_cap_at_goal": 0.0,
            "progress_pct": 0.0,
            "difficulty_ratio": None,
        }

    max_reps_at_goal = max(0.0, 30.0 * (one_rm_leff / goal_leff - 1.0))

    load_ratio_goal = goal_leff / bw
    ebr_goal = goal_reps * (load_ratio_goal ** EBR_ALPHA)
    ebr_cap_at_goal = max_reps_at_goal * (load_ratio_goal ** EBR_ALPHA)

    # Log-based nonlinear progress: log(current_reps) / log(goal_reps)
    # reps_base = 1 → log(1) = 0 is the zero anchor (no division needed)
    if max_reps_at_goal < EBR_BASE or goal_reps <= 1:
        progress_pct = 0.0
    elif max_reps_at_goal >= goal_reps:
        progress_pct = 100.0
    else:
        progress_pct = round(
            100.0 * math.log(max_reps_at_goal / EBR_BASE) / math.log(goal_reps / EBR_BASE),
            1,
        )
        progress_pct = max(0.0, min(100.0, progress_pct))

    difficulty_ratio = (
        round(ebr_goal / ebr_cap_at_goal, 3) if ebr_cap_at_goal > 0 else None
    )

    return {
        "max_reps_at_goal": round(max_reps_at_goal, 1),
        "ebr_goal": round(ebr_goal, 2),
        "ebr_cap_at_goal": round(ebr_cap_at_goal, 2),
        "progress_pct": progress_pct,
        "difficulty_ratio": difficulty_ratio,
    }
