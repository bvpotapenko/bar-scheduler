"""
Regenerate the GENERATED sections of constants_p1/p2/p3.py.

Run once whenever history_data.py or the planner changes:
    python tests/golden/regenerate.py

This script:
1. Creates three fresh profiles in a temp dir.
2. Freezes time to FROZEN_TODAY via time_machine.
3. Runs get_plan / get_training_status for every (profile, exercise) pair.
4. Runs Layer 3 / Layer 4 / Layer 5 scenarios.
5. Overwrites the GENERATED block in each constants file.
"""

from __future__ import annotations

import pprint
import sys
import tempfile
from pathlib import Path

import time_machine

# Make sure project src is importable when run from project root.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from bar_scheduler.api import (
    delete_session,
    enable_exercise,
    get_history,
    get_plan,
    init_profile,
    log_session,
    set_exercise_target,
    set_plan_start_date,
    update_equipment,
)
from bar_scheduler.api.types import SessionInput, SetInput

# ---- import hand-authored constants ----
sys.path.insert(0, str(Path(__file__).parent))

from constants_p1 import (
    P1_BODYWEIGHT_KG,
    P1_BSS_AVAILABLE_ITEMS,
    P1_BSS_DAYS,
    P1_BSS_IMPROVED_TEST,
    P1_BSS_OVERPERFORMANCE,
    P1_BSS_TARGET_REPS,
    P1_BSS_TARGET_WEIGHT_KG,
    P1_BSS_WEIGHTS_KG,
    P1_DIP_AVAILABLE_ITEMS,
    P1_DIP_DAYS,
    P1_DIP_IMPROVED_TEST,
    P1_DIP_MACHINE_ASSISTANCE_KG,
    P1_DIP_TARGET_REPS,
    P1_DIP_TARGET_WEIGHT_KG,
    P1_HEIGHT_CM,
    P1_INCLINE_15W_CHECKPOINT_IDX,
    P1_INCLINE_15W_SESSIONS,
    P1_INCLINE_AVAILABLE_ITEMS,
    P1_INCLINE_DAYS,
    P1_INCLINE_IMPROVED_TEST,
    P1_INCLINE_OVERPERFORMANCE,
    P1_INCLINE_TARGET_REPS,
    P1_INCLINE_TARGET_WEIGHT_KG,
    P1_INCLINE_WEIGHTS_KG,
)
from constants_p2 import (
    P2_BODYWEIGHT_KG,
    P2_DIP_15W_CHECKPOINT_IDX,
    P2_DIP_15W_SESSIONS,
    P2_DIP_AVAILABLE_ITEMS,
    P2_DIP_DAYS,
    P2_DIP_IMPROVED_TEST,
    P2_DIP_OVERPERFORMANCE,
    P2_DIP_TARGET_REPS,
    P2_DIP_TARGET_WEIGHT_KG,
    P2_HEIGHT_CM,
    P2_PULL_UP_AVAILABLE_ITEMS,
    P2_PULL_UP_DAYS,
    P2_PULL_UP_IMPROVED_TEST,
    P2_PULL_UP_OVERPERFORMANCE,
    P2_PULL_UP_TARGET_REPS,
    P2_PULL_UP_TARGET_WEIGHT_KG,
)
from constants_p3 import (
    P3_BODYWEIGHT_KG,
    P3_BSS_AVAILABLE_ITEMS,
    P3_BSS_DAYS,
    P3_BSS_IMPROVED_TEST,
    P3_BSS_OVERPERFORMANCE,
    P3_BSS_TARGET_REPS,
    P3_BSS_TARGET_WEIGHT_KG,
    P3_BSS_WEIGHTS_KG,
    P3_HEIGHT_CM,
    P3_PULL_UP_AVAILABLE_ITEMS,
    P3_PULL_UP_DAYS,
    P3_PULL_UP_IMPROVED_TEST,
    P3_PULL_UP_OVERPERFORMANCE,
    P3_PULL_UP_TARGET_REPS,
    P3_PULL_UP_TARGET_WEIGHT_KG,
)
from history_data import (
    P1_BSS_HISTORY,
    P1_DIP_HISTORY,
    P1_INCLINE_HISTORY,
    P2_DIP_HISTORY,
    P2_PULL_UP_HISTORY,
    P3_BSS_HISTORY,
    P3_PULL_UP_HISTORY,
)

FROZEN_TODAY = "2026-01-12"
PLAN_START = "2026-01-13"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(d: dict) -> SessionInput:
    sets = [
        SetInput(
            reps=s["reps"],
            rest_seconds=s["rest_seconds"],
            added_weight_kg=s.get("added_weight_kg", 0.0),
            rir_reported=s.get("rir_reported"),
        )
        for s in d["sets"]
    ]
    return SessionInput(
        date=d["date"],
        session_type=d["session_type"],
        bodyweight_kg=d["bodyweight_kg"],
        sets=sets,
        grip=d.get("grip", "standard"),
    )


def _log_history(data_dir: Path, exercise_id: str, sessions: list[dict]) -> None:
    for s in sessions:
        log_session(data_dir, exercise_id, _make_session(s))


def _extract_status(plan: dict) -> dict:
    s = plan["status"]
    return {
        "training_max": s["training_max"],
        "latest_test_max": s["latest_test_max"],
        "trend_slope_per_week": round(s["trend_slope_per_week"], 4),
        "is_plateau": s["is_plateau"],
        "deload_recommended": s["deload_recommended"],
        "readiness_z_score": round(s["readiness_z_score"], 4),
        "fitness": round(s["fitness"], 4),
        "fatigue": round(s["fatigue"], 4),
    }


def _extract_future_sessions(plan: dict) -> list[dict]:
    result = []
    for sess in plan["sessions"]:
        if sess["status"] not in ("next", "planned"):
            continue
        ps = sess.get("prescribed_sets") or []
        result.append(
            {
                "date": sess["date"],
                "type": sess["type"],
                "prescribed_sets": [
                    {
                        "reps": p["reps"],
                        "weight_kg": round(p["weight_kg"], 2),
                        "rest_s": p["rest_s"],
                    }
                    for p in ps
                ],
            }
        )
    return result


def _extract_done_metrics(plan: dict) -> list[dict]:
    result = []
    for sess in plan["sessions"]:
        if sess["status"] != "done":
            continue
        m = sess.get("session_metrics") or {}
        result.append(
            {
                "volume_session": round(m.get("volume_session") or 0.0, 2),
                "avg_volume_set": round(m.get("avg_volume_set") or 0.0, 2),
                "estimated_1rm": (
                    round(m.get("estimated_1rm") or 0.0, 2)
                    if m.get("estimated_1rm") is not None
                    else None
                ),
            }
        )
    return result


def _setup_profile1(d: Path) -> None:
    init_profile(d, height_cm=P1_HEIGHT_CM, bodyweight_kg=P1_BODYWEIGHT_KG)
    enable_exercise(d, "dip", days_per_week=P1_DIP_DAYS)
    set_exercise_target(
        d, "dip", reps=P1_DIP_TARGET_REPS, weight_kg=P1_DIP_TARGET_WEIGHT_KG
    )
    update_equipment(
        d,
        "dip",
        available_items=P1_DIP_AVAILABLE_ITEMS,
        available_machine_assistance_kg=P1_DIP_MACHINE_ASSISTANCE_KG,
    )
    enable_exercise(d, "incline_db_press", days_per_week=P1_INCLINE_DAYS)
    set_exercise_target(
        d,
        "incline_db_press",
        reps=P1_INCLINE_TARGET_REPS,
        weight_kg=P1_INCLINE_TARGET_WEIGHT_KG,
    )
    update_equipment(
        d,
        "incline_db_press",
        available_items=P1_INCLINE_AVAILABLE_ITEMS,
        available_weights_kg=P1_INCLINE_WEIGHTS_KG,
    )
    enable_exercise(d, "bss", days_per_week=P1_BSS_DAYS)
    set_exercise_target(
        d, "bss", reps=P1_BSS_TARGET_REPS, weight_kg=P1_BSS_TARGET_WEIGHT_KG
    )
    update_equipment(
        d,
        "bss",
        available_items=P1_BSS_AVAILABLE_ITEMS,
        available_weights_kg=P1_BSS_WEIGHTS_KG,
    )
    _log_history(d, "dip", P1_DIP_HISTORY)
    set_plan_start_date(d, "dip", PLAN_START)
    _log_history(d, "incline_db_press", P1_INCLINE_HISTORY)
    set_plan_start_date(d, "incline_db_press", PLAN_START)
    _log_history(d, "bss", P1_BSS_HISTORY)
    set_plan_start_date(d, "bss", PLAN_START)


def _setup_profile2(d: Path) -> None:
    init_profile(d, height_cm=P2_HEIGHT_CM, bodyweight_kg=P2_BODYWEIGHT_KG)
    enable_exercise(d, "pull_up", days_per_week=P2_PULL_UP_DAYS)
    set_exercise_target(
        d, "pull_up", reps=P2_PULL_UP_TARGET_REPS, weight_kg=P2_PULL_UP_TARGET_WEIGHT_KG
    )
    update_equipment(d, "pull_up", available_items=P2_PULL_UP_AVAILABLE_ITEMS)
    enable_exercise(d, "dip", days_per_week=P2_DIP_DAYS)
    set_exercise_target(
        d, "dip", reps=P2_DIP_TARGET_REPS, weight_kg=P2_DIP_TARGET_WEIGHT_KG
    )
    update_equipment(d, "dip", available_items=P2_DIP_AVAILABLE_ITEMS)
    _log_history(d, "pull_up", P2_PULL_UP_HISTORY)
    set_plan_start_date(d, "pull_up", PLAN_START)
    _log_history(d, "dip", P2_DIP_HISTORY)
    set_plan_start_date(d, "dip", PLAN_START)


def _setup_profile3(d: Path) -> None:
    init_profile(d, height_cm=P3_HEIGHT_CM, bodyweight_kg=P3_BODYWEIGHT_KG)
    enable_exercise(d, "bss", days_per_week=P3_BSS_DAYS)
    set_exercise_target(
        d, "bss", reps=P3_BSS_TARGET_REPS, weight_kg=P3_BSS_TARGET_WEIGHT_KG
    )
    update_equipment(
        d,
        "bss",
        available_items=P3_BSS_AVAILABLE_ITEMS,
        available_weights_kg=P3_BSS_WEIGHTS_KG,
    )
    enable_exercise(d, "pull_up", days_per_week=P3_PULL_UP_DAYS)
    set_exercise_target(
        d, "pull_up", reps=P3_PULL_UP_TARGET_REPS, weight_kg=P3_PULL_UP_TARGET_WEIGHT_KG
    )
    update_equipment(d, "pull_up", available_items=P3_PULL_UP_AVAILABLE_ITEMS)
    _log_history(d, "bss", P3_BSS_HISTORY)
    set_plan_start_date(d, "bss", PLAN_START)
    _log_history(d, "pull_up", P3_PULL_UP_HISTORY)
    set_plan_start_date(d, "pull_up", PLAN_START)


def _after_improved_test(d: Path, ex_id: str, improved_test: dict) -> dict:
    n = len(get_history(d, ex_id))
    log_session(d, ex_id, _make_session(improved_test))
    plan = get_plan(d, ex_id, weeks_ahead=4)
    status = _extract_status(plan)
    future = _extract_future_sessions(plan)
    delete_session(d, ex_id, n + 1)
    return {"status": status, "future_sessions": future[:4]}


def _after_overperformance(d: Path, ex_id: str, overperf: dict) -> dict:
    n = len(get_history(d, ex_id))
    log_session(d, ex_id, _make_session(overperf))
    plan = get_plan(d, ex_id, weeks_ahead=4)
    status = _extract_status(plan)
    future = _extract_future_sessions(plan)
    delete_session(d, ex_id, n + 1)
    return {"status": status, "future_sessions": future[:4]}


def _run_15w_checkpoints(
    d: Path, ex_id: str, sessions: list[dict], checkpoint_idxs: list[int]
) -> dict:
    checkpoints: dict[int, dict] = {}
    logged = 0
    for i, sess in enumerate(sessions):
        log_session(d, ex_id, _make_session(sess))
        logged += 1
        if (i + 1) in checkpoint_idxs:
            plan = get_plan(d, ex_id, weeks_ahead=4)
            s = plan["status"]
            z = round(s["readiness_z_score"], 4)
            checkpoints[i + 1] = {
                "is_plateau": s["is_plateau"],
                "deload_recommended": s["deload_recommended"],
                "readiness_z_score": z,
            }
    # Delete all logged sessions (they were added to a fresh dir starting at position 1)
    for _ in range(logged):
        delete_session(d, ex_id, 1)
    return checkpoints


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _pp(v) -> str:
    return pprint.pformat(v, width=100, sort_dicts=False)


def _write_generated_block(filepath: Path, block: str) -> None:
    text = filepath.read_text()
    marker = "# ===========================================================================\n# Section B: GENERATED"
    idx = text.find(marker)
    if idx == -1:
        raise RuntimeError(f"GENERATED marker not found in {filepath}")
    new_text = text[:idx] + block
    filepath.write_text(new_text)
    print(f"  Wrote {filepath.name}")


def run() -> None:
    with time_machine.travel(FROZEN_TODAY, tick=False):
        with tempfile.TemporaryDirectory() as tmp:
            p1 = Path(tmp) / "p1"
            p2 = Path(tmp) / "p2"
            p3 = Path(tmp) / "p3"
            p1.mkdir()
            p2.mkdir()
            p3.mkdir()

            print("Setting up profiles...")
            _setup_profile1(p1)
            _setup_profile2(p2)
            _setup_profile3(p3)

            print("Computing Layer 2 plan data...")
            p1_dip_plan = get_plan(p1, "dip", weeks_ahead=4)
            p1_incline_plan = get_plan(p1, "incline_db_press", weeks_ahead=4)
            p1_bss_plan = get_plan(p1, "bss", weeks_ahead=4)
            p2_pu_plan = get_plan(p2, "pull_up", weeks_ahead=4)
            p2_dip_plan = get_plan(p2, "dip", weeks_ahead=4)
            p3_bss_plan = get_plan(p3, "bss", weeks_ahead=4)
            p3_pu_plan = get_plan(p3, "pull_up", weeks_ahead=4)

            print("Computing Layer 3 (improved TEST) data...")
            p1_dip_l3 = _after_improved_test(p1, "dip", P1_DIP_IMPROVED_TEST)
            p1_incline_l3 = _after_improved_test(
                p1, "incline_db_press", P1_INCLINE_IMPROVED_TEST
            )
            p1_bss_l3 = _after_improved_test(p1, "bss", P1_BSS_IMPROVED_TEST)
            p2_pu_l3 = _after_improved_test(p2, "pull_up", P2_PULL_UP_IMPROVED_TEST)
            p2_dip_l3 = _after_improved_test(p2, "dip", P2_DIP_IMPROVED_TEST)
            p3_bss_l3 = _after_improved_test(p3, "bss", P3_BSS_IMPROVED_TEST)
            p3_pu_l3 = _after_improved_test(p3, "pull_up", P3_PULL_UP_IMPROVED_TEST)

            print("Computing Layer 4 (overperformance) data...")
            p1_incline_l4 = _after_overperformance(
                p1, "incline_db_press", P1_INCLINE_OVERPERFORMANCE
            )
            p1_bss_l4 = _after_overperformance(p1, "bss", P1_BSS_OVERPERFORMANCE)
            p2_pu_l4 = _after_overperformance(p2, "pull_up", P2_PULL_UP_OVERPERFORMANCE)
            p2_dip_l4 = _after_overperformance(p2, "dip", P2_DIP_OVERPERFORMANCE)
            p3_bss_l4 = _after_overperformance(p3, "bss", P3_BSS_OVERPERFORMANCE)
            p3_pu_l4 = _after_overperformance(p3, "pull_up", P3_PULL_UP_OVERPERFORMANCE)

            print("Computing Layer 5 (15W simulation) data...")
            # Use fresh dirs for Layer 5 (separate from baseline profiles)
            sim_p2_dip = Path(tmp) / "sim_p2_dip"
            sim_p2_dip.mkdir()
            init_profile(
                sim_p2_dip, height_cm=P2_HEIGHT_CM, bodyweight_kg=P2_BODYWEIGHT_KG
            )
            enable_exercise(sim_p2_dip, "dip", days_per_week=P2_DIP_DAYS)
            update_equipment(sim_p2_dip, "dip", available_items=P2_DIP_AVAILABLE_ITEMS)
            set_plan_start_date(sim_p2_dip, "dip", PLAN_START)

            sim_p1_incline = Path(tmp) / "sim_p1_incline"
            sim_p1_incline.mkdir()
            init_profile(
                sim_p1_incline, height_cm=P1_HEIGHT_CM, bodyweight_kg=P1_BODYWEIGHT_KG
            )
            enable_exercise(
                sim_p1_incline, "incline_db_press", days_per_week=P1_INCLINE_DAYS
            )
            update_equipment(
                sim_p1_incline,
                "incline_db_press",
                available_items=P1_INCLINE_AVAILABLE_ITEMS,
                available_weights_kg=P1_INCLINE_WEIGHTS_KG,
            )
            set_plan_start_date(sim_p1_incline, "incline_db_press", PLAN_START)

            p2_dip_15w_cps = _run_15w_checkpoints(
                sim_p2_dip, "dip", P2_DIP_15W_SESSIONS, P2_DIP_15W_CHECKPOINT_IDX
            )
            p1_incline_15w_cps = _run_15w_checkpoints(
                sim_p1_incline,
                "incline_db_press",
                P1_INCLINE_15W_SESSIONS,
                P1_INCLINE_15W_CHECKPOINT_IDX,
            )

    # ---- build checkpoint dicts with z-score bounds ----
    def _cp_to_bounds(cp_raw: dict) -> dict:
        result = {}
        for idx, v in cp_raw.items():
            z = v["readiness_z_score"]
            result[idx] = {
                "is_plateau": v["is_plateau"],
                "deload_recommended": v["deload_recommended"],
                "readiness_z_score": z,
                # ±20% bounds for z-score assertions in tests
                "readiness_z_score_min": round(
                    min(z - 0.5, z * 1.2 if z < 0 else z * 0.8), 4
                ),
                "readiness_z_score_max": round(
                    max(z + 0.5, z * 0.8 if z < 0 else z * 1.2), 4
                ),
            }
        return result

    p2_dip_15w_bounds = _cp_to_bounds(p2_dip_15w_cps)
    p1_incline_15w_bounds = _cp_to_bounds(p1_incline_15w_cps)

    # ---- write constants_p1.py ----
    here = Path(__file__).parent
    block_p1 = f"""# ===========================================================================
# Section B: GENERATED — do not hand-edit; run regenerate.py to refresh
# ===========================================================================

# --- Layer 2: plan status after baseline history ---
P1_DIP_STATUS = {_pp(_extract_status(p1_dip_plan))}
P1_INCLINE_STATUS = {_pp(_extract_status(p1_incline_plan))}
P1_BSS_STATUS = {_pp(_extract_status(p1_bss_plan))}

# --- Layer 2: future session prescriptions ---
P1_DIP_FUTURE_SESSIONS = {_pp(_extract_future_sessions(p1_dip_plan))}
P1_INCLINE_FUTURE_SESSIONS = {_pp(_extract_future_sessions(p1_incline_plan))}
P1_BSS_FUTURE_SESSIONS = {_pp(_extract_future_sessions(p1_bss_plan))}

# --- Layer 2: done-session metrics ---
P1_DIP_DONE_METRICS = {_pp(_extract_done_metrics(p1_dip_plan))}
P1_INCLINE_DONE_METRICS = {_pp(_extract_done_metrics(p1_incline_plan))}
P1_BSS_DONE_METRICS = {_pp(_extract_done_metrics(p1_bss_plan))}

# --- Layer 3: plan state after improved TEST ---
P1_DIP_AFTER_IMPROVED_TEST = {_pp(p1_dip_l3)}
P1_INCLINE_AFTER_IMPROVED_TEST = {_pp(p1_incline_l3)}
P1_BSS_AFTER_IMPROVED_TEST = {_pp(p1_bss_l3)}

# --- Layer 4: expected plan state after overperformance session ---
P1_INCLINE_AFTER_OVERPERFORMANCE = {_pp(p1_incline_l4)}
P1_BSS_AFTER_OVERPERFORMANCE = {_pp(p1_bss_l4)}

# --- Layer 5: 15W checkpoints ---
P1_INCLINE_15W_CHECKPOINTS = {_pp(p1_incline_15w_bounds)}
"""
    _write_generated_block(here / "constants_p1.py", block_p1)

    # ---- write constants_p2.py ----
    block_p2 = f"""# ===========================================================================
# Section B: GENERATED
# ===========================================================================

P2_PULL_UP_STATUS = {_pp(_extract_status(p2_pu_plan))}
P2_DIP_STATUS = {_pp(_extract_status(p2_dip_plan))}

P2_PULL_UP_FUTURE_SESSIONS = {_pp(_extract_future_sessions(p2_pu_plan))}
P2_DIP_FUTURE_SESSIONS = {_pp(_extract_future_sessions(p2_dip_plan))}

P2_PULL_UP_DONE_METRICS = {_pp(_extract_done_metrics(p2_pu_plan))}
P2_DIP_DONE_METRICS = {_pp(_extract_done_metrics(p2_dip_plan))}

P2_PULL_UP_AFTER_IMPROVED_TEST = {_pp(p2_pu_l3)}
P2_DIP_AFTER_IMPROVED_TEST = {_pp(p2_dip_l3)}

P2_PULL_UP_AFTER_OVERPERFORMANCE = {_pp(p2_pu_l4)}
P2_DIP_AFTER_OVERPERFORMANCE = {_pp(p2_dip_l4)}

P2_DIP_15W_CHECKPOINTS = {_pp(p2_dip_15w_bounds)}
"""
    _write_generated_block(here / "constants_p2.py", block_p2)

    # ---- write constants_p3.py ----
    block_p3 = f"""# ===========================================================================
# Section B: GENERATED
# ===========================================================================

P3_BSS_STATUS = {_pp(_extract_status(p3_bss_plan))}
P3_PULL_UP_STATUS = {_pp(_extract_status(p3_pu_plan))}

P3_BSS_FUTURE_SESSIONS = {_pp(_extract_future_sessions(p3_bss_plan))}
P3_PULL_UP_FUTURE_SESSIONS = {_pp(_extract_future_sessions(p3_pu_plan))}

P3_BSS_DONE_METRICS = {_pp(_extract_done_metrics(p3_bss_plan))}
P3_PULL_UP_DONE_METRICS = {_pp(_extract_done_metrics(p3_pu_plan))}

P3_BSS_AFTER_IMPROVED_TEST = {_pp(p3_bss_l3)}
P3_PULL_UP_AFTER_IMPROVED_TEST = {_pp(p3_pu_l3)}

P3_BSS_AFTER_OVERPERFORMANCE = {_pp(p3_bss_l4)}
P3_PULL_UP_AFTER_OVERPERFORMANCE = {_pp(p3_pu_l4)}
"""
    _write_generated_block(here / "constants_p3.py", block_p3)

    print("\nDone. Inspect the generated sections then commit.")


if __name__ == "__main__":
    run()
