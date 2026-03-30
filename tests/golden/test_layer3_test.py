"""
Layer 3 — Improved TEST session triggers plan adaptation.

For each (profile, exercise) pair:
  1. Log a TEST session with reps > all previous TESTSs.
  2. Verify training_max increases and prescriptions reflect the new TM.
  3. Delete the added session (try/finally) to keep state clean for other tests.

Expected values come from constants_pN.py Section B (baked by regenerate.py).
Tolerance for weight_kg: abs=0.01 (2 decimal places as required).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bar_scheduler.api import delete_session, get_history, get_plan, log_session

from .conftest import _make_session
from .constants_p1 import (
    P1_BSS_AFTER_IMPROVED_TEST,
    P1_BSS_IMPROVED_TEST,
    P1_DIP_AFTER_IMPROVED_TEST,
    P1_DIP_IMPROVED_TEST,
    P1_INCLINE_AFTER_IMPROVED_TEST,
    P1_INCLINE_IMPROVED_TEST,
)
from .constants_p2 import (
    P2_DIP_AFTER_IMPROVED_TEST,
    P2_DIP_IMPROVED_TEST,
    P2_PULL_UP_AFTER_IMPROVED_TEST,
    P2_PULL_UP_IMPROVED_TEST,
)
from .constants_p3 import (
    P3_BSS_AFTER_IMPROVED_TEST,
    P3_BSS_IMPROVED_TEST,
    P3_PULL_UP_AFTER_IMPROVED_TEST,
    P3_PULL_UP_IMPROVED_TEST,
)


def _assert_adapted(plan: dict, expected: dict) -> None:
    """Verify the plan status and first future sessions after an improved TEST."""
    s = plan["status"]
    exp_status = expected["status"]
    assert s["training_max"] == exp_status["training_max"], "training_max not updated"
    assert s["latest_test_max"] == exp_status["latest_test_max"], "latest_test_max not updated"
    assert s["trend_slope_per_week"] == pytest.approx(exp_status["trend_slope_per_week"], abs=0.01)
    assert s["readiness_z_score"] == pytest.approx(exp_status["readiness_z_score"], abs=0.01)

    future = [x for x in plan["sessions"] if x["status"] in ("next", "planned")]
    exp_future = expected["future_sessions"]
    for i, exp in enumerate(exp_future):
        sess = future[i]
        assert sess["date"] == exp["date"]
        assert sess["type"] == exp["type"]
        ps = sess.get("prescribed_sets") or []
        for j, ep in enumerate(exp["prescribed_sets"]):
            assert ps[j]["reps"] == ep["reps"], f"session[{i}] set[{j}] reps"
            assert ps[j]["weight_kg"] == pytest.approx(ep["weight_kg"], abs=0.01), (
                f"session[{i}] set[{j}] weight_kg"
            )


# ---------------------------------------------------------------------------
# Profile 1
# ---------------------------------------------------------------------------


class TestProfile1ImprovedTest:
    def test_dip_adapts(self, profile1_dir: Path):
        n = len(get_history(profile1_dir, "dip"))
        log_session(profile1_dir, "dip", _make_session(P1_DIP_IMPROVED_TEST))
        try:
            plan = get_plan(profile1_dir, "dip", weeks_ahead=4)
            _assert_adapted(plan, P1_DIP_AFTER_IMPROVED_TEST)
        finally:
            delete_session(profile1_dir, "dip", n + 1)

    def test_incline_adapts(self, profile1_dir: Path):
        n = len(get_history(profile1_dir, "incline_db_press"))
        log_session(profile1_dir, "incline_db_press", _make_session(P1_INCLINE_IMPROVED_TEST))
        try:
            plan = get_plan(profile1_dir, "incline_db_press", weeks_ahead=4)
            _assert_adapted(plan, P1_INCLINE_AFTER_IMPROVED_TEST)
        finally:
            delete_session(profile1_dir, "incline_db_press", n + 1)

    def test_bss_adapts(self, profile1_dir: Path):
        n = len(get_history(profile1_dir, "bss"))
        log_session(profile1_dir, "bss", _make_session(P1_BSS_IMPROVED_TEST))
        try:
            plan = get_plan(profile1_dir, "bss", weeks_ahead=4)
            _assert_adapted(plan, P1_BSS_AFTER_IMPROVED_TEST)
        finally:
            delete_session(profile1_dir, "bss", n + 1)


# ---------------------------------------------------------------------------
# Profile 2
# ---------------------------------------------------------------------------


class TestProfile2ImprovedTest:
    def test_pull_up_adapts(self, profile2_dir: Path):
        n = len(get_history(profile2_dir, "pull_up"))
        log_session(profile2_dir, "pull_up", _make_session(P2_PULL_UP_IMPROVED_TEST))
        try:
            plan = get_plan(profile2_dir, "pull_up", weeks_ahead=4)
            _assert_adapted(plan, P2_PULL_UP_AFTER_IMPROVED_TEST)
        finally:
            delete_session(profile2_dir, "pull_up", n + 1)

    def test_dip_adapts(self, profile2_dir: Path):
        n = len(get_history(profile2_dir, "dip"))
        log_session(profile2_dir, "dip", _make_session(P2_DIP_IMPROVED_TEST))
        try:
            plan = get_plan(profile2_dir, "dip", weeks_ahead=4)
            _assert_adapted(plan, P2_DIP_AFTER_IMPROVED_TEST)
        finally:
            delete_session(profile2_dir, "dip", n + 1)


# ---------------------------------------------------------------------------
# Profile 3
# ---------------------------------------------------------------------------


class TestProfile3ImprovedTest:
    def test_bss_adapts(self, profile3_dir: Path):
        n = len(get_history(profile3_dir, "bss"))
        log_session(profile3_dir, "bss", _make_session(P3_BSS_IMPROVED_TEST))
        try:
            plan = get_plan(profile3_dir, "bss", weeks_ahead=4)
            _assert_adapted(plan, P3_BSS_AFTER_IMPROVED_TEST)
        finally:
            delete_session(profile3_dir, "bss", n + 1)

    def test_pull_up_adapts(self, profile3_dir: Path):
        n = len(get_history(profile3_dir, "pull_up"))
        log_session(profile3_dir, "pull_up", _make_session(P3_PULL_UP_IMPROVED_TEST))
        try:
            plan = get_plan(profile3_dir, "pull_up", weeks_ahead=4)
            _assert_adapted(plan, P3_PULL_UP_AFTER_IMPROVED_TEST)
        finally:
            delete_session(profile3_dir, "pull_up", n + 1)
