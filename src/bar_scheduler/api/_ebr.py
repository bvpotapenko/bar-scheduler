"""EBR (Equivalent Bodyweight Reps) — user-facing metrics API.

Three independent metrics for clients:
  get_ebr_data      — per-session EBR history + projected plan (replaces get_load_data)
  get_goal_progress — capability and nonlinear progress toward the current goal
  compute_set_ebr   — EBR for a single hypothetical set (replaces compute_session_load)
"""
from __future__ import annotations

from pathlib import Path

from ..core.config import EBR_ALPHA
from ..core.ebr import (
    compute_capability,
    compute_goal_metrics,
    compute_session_ebr,
    compute_set_ebr_value,
)
from ..core.exercises.registry import get_exercise
from ..core.planner import generate_plan
from ._common import _require_store, _resolve_plan_start


def get_ebr_data(
    data_dir: Path,
    exercise_id: str,
    weeks_ahead: int = 4,
) -> dict:
    """Return per-session EBR for history and the upcoming plan.

    Replaces ``get_load_data()``.  EBR (Equivalent Bodyweight Reps) is a
    user-facing volume metric that scales nonlinearly with load and adjusts
    for short rest between sets.  See ``docs/performance-formulas.md`` for
    the full formula.

    Historical EBR is computed from stored session data (reps, weight, rest,
    bodyweight).  Plan EBR is projected from the planned prescription.

    Args:
        data_dir: Directory with profile and history files.
        exercise_id: Which exercise.
        weeks_ahead: How many plan weeks to project.

    Returns:
        Dict with two keys:

        - ``"history"``: list of ``{"date", "session_type", "ebr", "kg_eq"}``
        - ``"plan"``:    list of ``{"date", "session_type", "ebr", "kg_eq"}``

        ``kg_eq`` = bodyweight × ebr (absolute equivalent in kg-reps).
    """
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)
    ex = get_exercise(exercise_id)
    history = [s for s in user_state.history if s.exercise_id == exercise_id]

    # --- history ---
    history_out = []
    for session in history:
        assistance = (
            session.equipment_snapshot.assistance_kg
            if session.equipment_snapshot is not None
            else 0.0
        )
        ebr, kg_eq = compute_session_ebr(
            session.completed_sets,
            ex.bw_fraction,
            session.bodyweight_kg,
            assistance,
        )
        history_out.append({
            "date": session.date,
            "session_type": session.session_type,
            "ebr": ebr,
            "kg_eq": kg_eq,
        })

    # --- plan ---
    plan_start = _resolve_plan_start(store, exercise_id, history)
    plans = generate_plan(user_state, plan_start, ex, weeks_ahead=weeks_ahead)
    bw = user_state.current_bodyweight_kg

    plan_out = []
    for session_plan in plans:
        ebr_total = 0.0
        for i, ps in enumerate(session_plan.sets):
            leff = max(
                0.0,
                bw * ex.bw_fraction + (ps.added_weight_kg or 0.0),
            )
            ebr_total += compute_set_ebr_value(
                ps.target_reps,
                leff,
                bw,
                ps.rest_seconds_before,
                is_first_set=(i == 0),
            )
        plan_out.append({
            "date": session_plan.date,
            "session_type": session_plan.session_type,
            "ebr": round(ebr_total, 2),
            "kg_eq": round(bw * ebr_total, 2),
        })

    return {"history": history_out, "plan": plan_out}


def get_goal_progress(
    data_dir: Path,
    exercise_id: str,
) -> dict:
    """Return current capability and nonlinear progress toward the set goal.

    ``max_reps_at_goal`` is the primary user-readable output:
    "You can currently do ~6 reps at +25 kg."

    ``progress_pct`` uses a log-based nonlinear scale: early reps require
    the most adaptation; later reps toward the goal come more readily once
    the strength base is built.  See ``docs/performance-formulas.md``.

    Args:
        data_dir: Directory with profile and history files.
        exercise_id: Which exercise.

    Returns:
        Dict with:

        - ``one_rm_leff``        — best Epley Leff 1RM from history (kg), or None
        - ``capability_ebr``     — EBR of one rep at estimated max, or None
        - ``goal_reps``          — target reps (from set_exercise_target), or None
        - ``goal_weight_kg``     — target added weight, or None
        - ``goal_ebr``           — EBR of hitting the goal exactly, or None
        - ``max_reps_at_goal``   — predicted reps at goal weight right now, or None
        - ``progress_pct``       — 0–100 (nonlinear log scale), or None
        - ``difficulty_ratio``   — EBR_goal / EBR_cap_at_goal (>1 = goal harder), or None
    """
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)
    ex = get_exercise(exercise_id)
    history = [s for s in user_state.history if s.exercise_id == exercise_id]
    bw = user_state.current_bodyweight_kg

    one_rm_leff = compute_capability(history, ex.bw_fraction, bw)

    # Capability EBR: EBR of performing 1 rep at 1RM
    capability_ebr = None
    if one_rm_leff is not None and bw > 0:
        load_ratio = one_rm_leff / bw
        capability_ebr = round(load_ratio ** EBR_ALPHA, 3)

    # Goal
    profile = user_state.profile
    try:
        target = profile.target_for_exercise(exercise_id)
    except Exception:
        target = None

    if target is None or one_rm_leff is None:
        return {
            "one_rm_leff": round(one_rm_leff, 2) if one_rm_leff is not None else None,
            "capability_ebr": capability_ebr,
            "goal_reps": None,
            "goal_weight_kg": None,
            "goal_ebr": None,
            "max_reps_at_goal": None,
            "progress_pct": None,
            "difficulty_ratio": None,
        }

    goal_reps = target.reps
    goal_weight_kg = target.weight_kg or 0.0
    goal_leff = bw * ex.bw_fraction + goal_weight_kg

    metrics = compute_goal_metrics(one_rm_leff, goal_reps, goal_leff, bw)

    return {
        "one_rm_leff": round(one_rm_leff, 2),
        "capability_ebr": capability_ebr,
        "goal_reps": goal_reps,
        "goal_weight_kg": goal_weight_kg,
        "goal_ebr": metrics["ebr_goal"],
        "max_reps_at_goal": metrics["max_reps_at_goal"],
        "progress_pct": metrics["progress_pct"],
        "difficulty_ratio": metrics["difficulty_ratio"],
    }


def compute_set_ebr(
    data_dir: Path,
    exercise_id: str,
    reps: int,
    added_weight_kg: float = 0.0,
    *,
    rest_seconds: int = 180,
    bodyweight_kg: float | None = None,
) -> float:
    """Compute EBR for a single hypothetical set.

    Replaces ``compute_session_load()``.  Useful for estimating how a goal
    session would compare against historical EBR values.

    Args:
        data_dir: Directory with profile and history files.
        exercise_id: Which exercise.
        reps: Number of reps in the hypothetical set.
        added_weight_kg: External load (belt, dumbbell). Default 0.
        rest_seconds: Rest before this set (default 180 = well-rested).
        bodyweight_kg: Override session bodyweight; defaults to current profile value.

    Returns:
        EBR for the set (float).
    """
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)
    ex = get_exercise(exercise_id)

    bw = bodyweight_kg if bodyweight_kg is not None else user_state.current_bodyweight_kg
    leff = max(0.0, bw * ex.bw_fraction + added_weight_kg)

    return round(
        compute_set_ebr_value(reps, leff, bw, rest_seconds, is_first_set=(rest_seconds >= 180)),
        3,
    )
