"""
Layer 2 — Plan comparison against pre-calculated constants.

For every (profile, exercise) combination, verifies:
- Training status fields (training_max, trend, is_plateau, deload, z-score)
- Future session prescriptions (date, type, reps, weight_kg to ±0.01)
- Done session metrics (volume_session, avg_volume_set, estimated_1rm to ±0.01)

All expected values live in constants_pN.py Section B (GENERATED).
Run regenerate.py once to bake them in, then these tests freeze the output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bar_scheduler.api import get_plan

from .constants_p1 import (
    P1_BSS_DONE_METRICS,
    P1_BSS_FUTURE_SESSIONS,
    P1_BSS_STATUS,
    P1_DIP_DONE_METRICS,
    P1_DIP_FUTURE_SESSIONS,
    P1_DIP_STATUS,
    P1_INCLINE_DONE_METRICS,
    P1_INCLINE_FUTURE_SESSIONS,
    P1_INCLINE_STATUS,
)
from .constants_p2 import (
    P2_DIP_DONE_METRICS,
    P2_DIP_FUTURE_SESSIONS,
    P2_DIP_STATUS,
    P2_PULL_UP_DONE_METRICS,
    P2_PULL_UP_FUTURE_SESSIONS,
    P2_PULL_UP_STATUS,
)
from .constants_p3 import (
    P3_BSS_DONE_METRICS,
    P3_BSS_FUTURE_SESSIONS,
    P3_BSS_STATUS,
    P3_PULL_UP_DONE_METRICS,
    P3_PULL_UP_FUTURE_SESSIONS,
    P3_PULL_UP_STATUS,
)


def _assert_status(plan: dict, expected: dict) -> None:
    s = plan["status"]
    assert s["training_max"] == expected["training_max"], "training_max mismatch"
    assert s["latest_test_max"] == expected["latest_test_max"], "latest_test_max mismatch"
    assert s["is_plateau"] == expected["is_plateau"], "is_plateau mismatch"
    assert s["deload_recommended"] == expected["deload_recommended"], "deload_recommended mismatch"
    assert s["trend_slope_per_week"] == pytest.approx(expected["trend_slope_per_week"], abs=0.01)
    assert s["readiness_z_score"] == pytest.approx(expected["readiness_z_score"], abs=0.01)
    assert s["fitness"] == pytest.approx(expected["fitness"], abs=0.01)
    assert s["fatigue"] == pytest.approx(expected["fatigue"], abs=0.01)


def _assert_future_sessions(plan: dict, expected: list[dict]) -> None:
    future = [x for x in plan["sessions"] if x["status"] in ("next", "planned")]
    assert len(future) >= len(expected), (
        f"Expected at least {len(expected)} future sessions, got {len(future)}"
    )
    for i, exp in enumerate(expected):
        sess = future[i]
        assert sess["date"] == exp["date"], f"session[{i}] date mismatch"
        assert sess["type"] == exp["type"], f"session[{i}] type mismatch"
        ps = sess.get("prescribed_sets") or []
        assert len(ps) == len(exp["prescribed_sets"]), f"session[{i}] set count mismatch"
        for j, ep in enumerate(exp["prescribed_sets"]):
            assert ps[j]["reps"] == ep["reps"], f"session[{i}] set[{j}] reps mismatch"
            assert ps[j]["weight_kg"] == pytest.approx(ep["weight_kg"], abs=0.01), (
                f"session[{i}] set[{j}] weight_kg mismatch"
            )


def _assert_done_metrics(plan: dict, expected: list[dict]) -> None:
    done = [x for x in plan["sessions"] if x["status"] == "done"]
    assert len(done) >= len(expected), (
        f"Expected at least {len(expected)} done sessions, got {len(done)}"
    )
    for i, exp in enumerate(expected):
        m = done[i].get("session_metrics") or {}
        assert (m.get("volume_session") or 0.0) == pytest.approx(exp["volume_session"], abs=0.01)
        assert (m.get("avg_volume_set") or 0.0) == pytest.approx(exp["avg_volume_set"], abs=0.01)
        if exp.get("estimated_1rm") is not None:
            assert m.get("estimated_1rm") == pytest.approx(exp["estimated_1rm"], abs=0.01)


# ---------------------------------------------------------------------------
# Profile 1
# ---------------------------------------------------------------------------


class TestProfile1Plan:
    def test_dip_status(self, profile1_dir: Path):
        plan = get_plan(profile1_dir, "dip", weeks_ahead=4)
        _assert_status(plan, P1_DIP_STATUS)

    def test_dip_future_sessions(self, profile1_dir: Path):
        plan = get_plan(profile1_dir, "dip", weeks_ahead=4)
        _assert_future_sessions(plan, P1_DIP_FUTURE_SESSIONS)

    def test_dip_done_metrics(self, profile1_dir: Path):
        plan = get_plan(profile1_dir, "dip", weeks_ahead=4)
        _assert_done_metrics(plan, P1_DIP_DONE_METRICS)

    def test_incline_status(self, profile1_dir: Path):
        plan = get_plan(profile1_dir, "incline_db_press", weeks_ahead=4)
        _assert_status(plan, P1_INCLINE_STATUS)

    def test_incline_future_sessions(self, profile1_dir: Path):
        plan = get_plan(profile1_dir, "incline_db_press", weeks_ahead=4)
        _assert_future_sessions(plan, P1_INCLINE_FUTURE_SESSIONS)

    def test_incline_done_metrics(self, profile1_dir: Path):
        plan = get_plan(profile1_dir, "incline_db_press", weeks_ahead=4)
        _assert_done_metrics(plan, P1_INCLINE_DONE_METRICS)

    def test_bss_status(self, profile1_dir: Path):
        plan = get_plan(profile1_dir, "bss", weeks_ahead=4)
        _assert_status(plan, P1_BSS_STATUS)

    def test_bss_future_sessions(self, profile1_dir: Path):
        plan = get_plan(profile1_dir, "bss", weeks_ahead=4)
        _assert_future_sessions(plan, P1_BSS_FUTURE_SESSIONS)

    def test_bss_done_metrics(self, profile1_dir: Path):
        plan = get_plan(profile1_dir, "bss", weeks_ahead=4)
        _assert_done_metrics(plan, P1_BSS_DONE_METRICS)


# ---------------------------------------------------------------------------
# Profile 2
# ---------------------------------------------------------------------------


class TestProfile2Plan:
    def test_pull_up_status(self, profile2_dir: Path):
        plan = get_plan(profile2_dir, "pull_up", weeks_ahead=4)
        _assert_status(plan, P2_PULL_UP_STATUS)

    def test_pull_up_future_sessions(self, profile2_dir: Path):
        plan = get_plan(profile2_dir, "pull_up", weeks_ahead=4)
        _assert_future_sessions(plan, P2_PULL_UP_FUTURE_SESSIONS)

    def test_pull_up_done_metrics(self, profile2_dir: Path):
        plan = get_plan(profile2_dir, "pull_up", weeks_ahead=4)
        _assert_done_metrics(plan, P2_PULL_UP_DONE_METRICS)

    def test_dip_status(self, profile2_dir: Path):
        plan = get_plan(profile2_dir, "dip", weeks_ahead=4)
        _assert_status(plan, P2_DIP_STATUS)

    def test_dip_future_sessions(self, profile2_dir: Path):
        plan = get_plan(profile2_dir, "dip", weeks_ahead=4)
        _assert_future_sessions(plan, P2_DIP_FUTURE_SESSIONS)

    def test_dip_done_metrics(self, profile2_dir: Path):
        plan = get_plan(profile2_dir, "dip", weeks_ahead=4)
        _assert_done_metrics(plan, P2_DIP_DONE_METRICS)


# ---------------------------------------------------------------------------
# Profile 3
# ---------------------------------------------------------------------------


class TestProfile3Plan:
    def test_bss_status(self, profile3_dir: Path):
        plan = get_plan(profile3_dir, "bss", weeks_ahead=4)
        _assert_status(plan, P3_BSS_STATUS)

    def test_bss_future_sessions(self, profile3_dir: Path):
        plan = get_plan(profile3_dir, "bss", weeks_ahead=4)
        _assert_future_sessions(plan, P3_BSS_FUTURE_SESSIONS)

    def test_bss_done_metrics(self, profile3_dir: Path):
        plan = get_plan(profile3_dir, "bss", weeks_ahead=4)
        _assert_done_metrics(plan, P3_BSS_DONE_METRICS)

    def test_pull_up_status(self, profile3_dir: Path):
        """P3 pull_up: 120 kg novice, BAR_ONLY only — planner must handle with no assistance."""
        plan = get_plan(profile3_dir, "pull_up", weeks_ahead=4)
        _assert_status(plan, P3_PULL_UP_STATUS)

    def test_pull_up_future_sessions(self, profile3_dir: Path):
        plan = get_plan(profile3_dir, "pull_up", weeks_ahead=4)
        _assert_future_sessions(plan, P3_PULL_UP_FUTURE_SESSIONS)

    def test_pull_up_done_metrics(self, profile3_dir: Path):
        plan = get_plan(profile3_dir, "pull_up", weeks_ahead=4)
        _assert_done_metrics(plan, P3_PULL_UP_DONE_METRICS)
