"""
Layer 5 — 15-week overtraining / plateau / recovery simulation.

Two exercises are simulated end-to-end:
  • dip  (P2 spec: 80 kg / 180 cm, WEIGHT_BELT available)  — BW + external
  • incline_db_press  (P1 spec: 50 kg / 160 cm, DUMBBELLS)  — pure external

Each test uses a FRESH function-scoped profile dir (not the shared session fixtures)
so no history contamination occurs and pytest's tmp_path cleanup handles teardown.

Session sequences and checkpoint expected values live in constants_p1/p2.py Section B.

Checkpoints (session index, 1-based):
  7  → Phase 1 end (normal load): no plateau, no deload, z-score in a plausible range
  14 → Phase 2 end (overtraining): plateau=True, deload=True, z-score low
  20 → Phase 3 end (recovery): plateau=False, deload=False, z-score recovers

Expected values are pre-baked by regenerate.py; tests assert exact bool values and
z-score within ±0.5 of the recorded value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bar_scheduler.api import (
    enable_exercise,
    get_plan,
    init_profile,
    log_session,
    set_plan_start_date,
    update_equipment,
)

from .conftest import PLAN_START, _make_session
from .constants_p1 import (
    P1_BODYWEIGHT_KG,
    P1_HEIGHT_CM,
    P1_INCLINE_15W_CHECKPOINTS,
    P1_INCLINE_15W_SESSIONS,
    P1_INCLINE_AVAILABLE_ITEMS,
    P1_INCLINE_DAYS,
    P1_INCLINE_WEIGHTS_KG,
)
from .constants_p2 import (
    P2_BODYWEIGHT_KG,
    P2_DIP_15W_CHECKPOINTS,
    P2_DIP_15W_SESSIONS,
    P2_DIP_AVAILABLE_ITEMS,
    P2_DIP_DAYS,
    P2_HEIGHT_CM,
)

_Z_TOLERANCE = 0.5  # z-score assertion tolerance (absolute)


def _assert_checkpoint(plan: dict, cp: dict, label: str) -> None:
    s = plan["status"]
    assert s["is_plateau"] == cp["is_plateau"], f"{label}: is_plateau"
    assert s["deload_recommended"] == cp["deload_recommended"], f"{label}: deload_recommended"
    z = s["readiness_z_score"]
    z_min = cp.get("readiness_z_score_min")
    z_max = cp.get("readiness_z_score_max")
    if z_min is not None:
        assert z >= z_min - _Z_TOLERANCE, f"{label}: z-score {z:.3f} below expected min {z_min}"
    if z_max is not None:
        assert z <= z_max + _Z_TOLERANCE, f"{label}: z-score {z:.3f} above expected max {z_max}"
    # Also assert it's within ±_Z_TOLERANCE of the stored exact value
    z_exact = cp.get("readiness_z_score")
    if z_exact is not None:
        assert z == pytest.approx(z_exact, abs=_Z_TOLERANCE), f"{label}: z-score vs exact"


# ---------------------------------------------------------------------------
# dip simulation (P2 spec)
# ---------------------------------------------------------------------------


@pytest.fixture
def dip_sim_dir(tmp_path: Path) -> Path:
    """Fresh P2-spec profile with dip only, no history."""
    init_profile(tmp_path, height_cm=P2_HEIGHT_CM, bodyweight_kg=P2_BODYWEIGHT_KG)
    enable_exercise(tmp_path, "dip", days_per_week=P2_DIP_DAYS)
    update_equipment(tmp_path, "dip", available_items=P2_DIP_AVAILABLE_ITEMS)
    set_plan_start_date(tmp_path, "dip", PLAN_START)
    return tmp_path


def test_dip_15w_simulation(dip_sim_dir: Path):
    """
    Log sessions one-by-one and assert at checkpoints:
      - Checkpoint 7:  normal phase  → no plateau, no deload
      - Checkpoint 14: overtrained   → plateau + deload, z-score low
      - Checkpoint 20: recovered     → no plateau, no deload
    """
    assert P2_DIP_15W_CHECKPOINTS, (
        "P2_DIP_15W_CHECKPOINTS is empty — run regenerate.py first"
    )
    checkpoint_set = set(P2_DIP_15W_CHECKPOINTS.keys())

    for i, sess in enumerate(P2_DIP_15W_SESSIONS):
        log_session(dip_sim_dir, "dip", _make_session(sess))
        idx = i + 1  # 1-based
        if idx in checkpoint_set:
            plan = get_plan(dip_sim_dir, "dip", weeks_ahead=4)
            cp = P2_DIP_15W_CHECKPOINTS[idx]
            _assert_checkpoint(plan, cp, label=f"dip checkpoint {idx}")


# ---------------------------------------------------------------------------
# incline_db_press simulation (P1 spec)
# ---------------------------------------------------------------------------


@pytest.fixture
def incline_sim_dir(tmp_path: Path) -> Path:
    """Fresh P1-spec profile with incline_db_press only, no history."""
    init_profile(tmp_path, height_cm=P1_HEIGHT_CM, bodyweight_kg=P1_BODYWEIGHT_KG)
    enable_exercise(tmp_path, "incline_db_press", days_per_week=P1_INCLINE_DAYS)
    update_equipment(
        tmp_path, "incline_db_press",
        available_items=P1_INCLINE_AVAILABLE_ITEMS,
        available_weights_kg=P1_INCLINE_WEIGHTS_KG,
    )
    set_plan_start_date(tmp_path, "incline_db_press", PLAN_START)
    return tmp_path


def test_incline_15w_simulation(incline_sim_dir: Path):
    """
    Log sessions one-by-one and assert at checkpoints:
      - Checkpoint 7:  normal phase  → no plateau, no deload
      - Checkpoint 14: overtrained   → plateau + deload, z-score low
      - Checkpoint 20: recovered     → no plateau, no deload
    """
    assert P1_INCLINE_15W_CHECKPOINTS, (
        "P1_INCLINE_15W_CHECKPOINTS is empty — run regenerate.py first"
    )
    checkpoint_set = set(P1_INCLINE_15W_CHECKPOINTS.keys())

    for i, sess in enumerate(P1_INCLINE_15W_SESSIONS):
        log_session(incline_sim_dir, "incline_db_press", _make_session(sess))
        idx = i + 1
        if idx in checkpoint_set:
            plan = get_plan(incline_sim_dir, "incline_db_press", weeks_ahead=4)
            cp = P1_INCLINE_15W_CHECKPOINTS[idx]
            _assert_checkpoint(plan, cp, label=f"incline checkpoint {idx}")
