"""
Layer 4 — 50%-over-prescribed volume triggers upward plan adaptation.

Covers each exercise type:
  pull_up  (P2) — bodyweight + optional belt
  dip      (P2) — bodyweight + optional belt
  bss      (P1 and P3) — external dumbbell
  incline_db_press (P1) — pure external

For each test:
  1. Log a session where performed volume is ~1.5× the first prescribed session.
  2. Verify TM or future prescriptions shift upward vs Layer 2 baseline.
  3. Delete the added session in try/finally for repeatability.

The overperformance sessions are pre-baked constants (not computed dynamically)
to keep the tests fully deterministic.

Expected plan states come from constants_pN.py Section B (baked by regenerate.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bar_scheduler.api import delete_session, get_history, get_plan, log_session

from .conftest import _make_session
from .constants_p1 import (
    P1_BSS_AFTER_OVERPERFORMANCE,
    P1_BSS_OVERPERFORMANCE,
    P1_BSS_STATUS,
    P1_INCLINE_AFTER_OVERPERFORMANCE,
    P1_INCLINE_OVERPERFORMANCE,
    P1_INCLINE_STATUS,
)
from .constants_p2 import (
    P2_DIP_AFTER_OVERPERFORMANCE,
    P2_DIP_OVERPERFORMANCE,
    P2_DIP_STATUS,
    P2_PULL_UP_AFTER_OVERPERFORMANCE,
    P2_PULL_UP_OVERPERFORMANCE,
    P2_PULL_UP_STATUS,
)
from .constants_p3 import (
    P3_BSS_AFTER_OVERPERFORMANCE,
    P3_BSS_OVERPERFORMANCE,
    P3_BSS_STATUS,
    P3_PULL_UP_AFTER_OVERPERFORMANCE,
    P3_PULL_UP_OVERPERFORMANCE,
    P3_PULL_UP_STATUS,
)


def _baseline_tm(status_const: dict) -> int:
    return status_const["training_max"]


def _assert_plan_shifted_up(plan: dict, expected: dict, baseline_status: dict) -> None:
    """Verify the plan adapted upward after overperformance."""
    s = plan["status"]
    exp_status = expected["status"]
    # TM must not decrease; it may stay same or go up
    assert s["training_max"] >= _baseline_tm(baseline_status), "TM should not decrease after overperformance"
    assert s["training_max"] == exp_status["training_max"], "training_max mismatch vs expected"

    # Future prescriptions should match the expected (shifted) values
    future = [x for x in plan["sessions"] if x["status"] in ("next", "planned")]
    exp_future = expected["future_sessions"]
    for i, exp in enumerate(exp_future):
        sess = future[i]
        assert sess["date"] == exp["date"]
        assert sess["type"] == exp["type"]
        ps = sess.get("prescribed_sets") or []
        for j, ep in enumerate(exp["prescribed_sets"]):
            assert ps[j]["reps"] == ep["reps"]
            assert ps[j]["weight_kg"] == pytest.approx(ep["weight_kg"], abs=0.01)


# ---------------------------------------------------------------------------
# pull_up — P2
# ---------------------------------------------------------------------------


def test_pull_up_overperformance_adapts(profile2_dir: Path):
    n = len(get_history(profile2_dir, "pull_up"))
    log_session(profile2_dir, "pull_up", _make_session(P2_PULL_UP_OVERPERFORMANCE))
    try:
        plan = get_plan(profile2_dir, "pull_up", weeks_ahead=4)
        _assert_plan_shifted_up(plan, P2_PULL_UP_AFTER_OVERPERFORMANCE, P2_PULL_UP_STATUS)
    finally:
        delete_session(profile2_dir, "pull_up", n + 1)


# ---------------------------------------------------------------------------
# dip — P2 (bodyweight + weighted belt)
# ---------------------------------------------------------------------------


def test_dip_overperformance_adapts(profile2_dir: Path):
    n = len(get_history(profile2_dir, "dip"))
    log_session(profile2_dir, "dip", _make_session(P2_DIP_OVERPERFORMANCE))
    try:
        plan = get_plan(profile2_dir, "dip", weeks_ahead=4)
        _assert_plan_shifted_up(plan, P2_DIP_AFTER_OVERPERFORMANCE, P2_DIP_STATUS)
    finally:
        delete_session(profile2_dir, "dip", n + 1)


# ---------------------------------------------------------------------------
# incline_db_press — P1 (pure external load)
# ---------------------------------------------------------------------------


def test_incline_overperformance_adapts(profile1_dir: Path):
    n = len(get_history(profile1_dir, "incline_db_press"))
    log_session(profile1_dir, "incline_db_press", _make_session(P1_INCLINE_OVERPERFORMANCE))
    try:
        plan = get_plan(profile1_dir, "incline_db_press", weeks_ahead=4)
        _assert_plan_shifted_up(plan, P1_INCLINE_AFTER_OVERPERFORMANCE, P1_INCLINE_STATUS)
    finally:
        delete_session(profile1_dir, "incline_db_press", n + 1)


# ---------------------------------------------------------------------------
# bss — P1 (external dumbbell, lighter profile)
# ---------------------------------------------------------------------------


def test_bss_overperformance_adapts_p1(profile1_dir: Path):
    n = len(get_history(profile1_dir, "bss"))
    log_session(profile1_dir, "bss", _make_session(P1_BSS_OVERPERFORMANCE))
    try:
        plan = get_plan(profile1_dir, "bss", weeks_ahead=4)
        _assert_plan_shifted_up(plan, P1_BSS_AFTER_OVERPERFORMANCE, P1_BSS_STATUS)
    finally:
        delete_session(profile1_dir, "bss", n + 1)


# ---------------------------------------------------------------------------
# bss — P3 (external dumbbell, heavy 120 kg profile)
# ---------------------------------------------------------------------------


def test_bss_overperformance_adapts_p3(profile3_dir: Path):
    n = len(get_history(profile3_dir, "bss"))
    log_session(profile3_dir, "bss", _make_session(P3_BSS_OVERPERFORMANCE))
    try:
        plan = get_plan(profile3_dir, "bss", weeks_ahead=4)
        _assert_plan_shifted_up(plan, P3_BSS_AFTER_OVERPERFORMANCE, P3_BSS_STATUS)
    finally:
        delete_session(profile3_dir, "bss", n + 1)


# ---------------------------------------------------------------------------
# pull_up — P3 (BAR_ONLY novice, 120 kg)
# ---------------------------------------------------------------------------


def test_pull_up_overperformance_adapts_p3(profile3_dir: Path):
    n = len(get_history(profile3_dir, "pull_up"))
    log_session(profile3_dir, "pull_up", _make_session(P3_PULL_UP_OVERPERFORMANCE))
    try:
        plan = get_plan(profile3_dir, "pull_up", weeks_ahead=4)
        _assert_plan_shifted_up(plan, P3_PULL_UP_AFTER_OVERPERFORMANCE, P3_PULL_UP_STATUS)
    finally:
        delete_session(profile3_dir, "pull_up", n + 1)
