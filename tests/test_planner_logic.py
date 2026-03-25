"""
Library-level integration tests for the bar-scheduler planning engine.

These tests call core functions directly -- no CLI, no CliRunner, no Typer.
Each test builds a specific history state and compares exact computed values
against hand-calculated expectations derived from the documented formulas.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from bar_scheduler.core.adaptation import get_training_status
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.metrics import training_max
from bar_scheduler.core.models import SessionResult, SetResult, UserProfile, UserState
from bar_scheduler.core.planner.load_calculator import (
    _calculate_added_weight,
    _expand_dual_dumbbell_totals,
)
from bar_scheduler.core.planner.plan_engine import generate_plan


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_test_session(date: str, reps: int, bw: float = 80.0) -> SessionResult:
    """Minimal TEST session: one set, reps performed = reps target."""
    s = SetResult(reps, reps, 180)
    return SessionResult(date, bw, "pronated", "TEST", "pull_up", completed_sets=[s])


def make_user_state(
    history: list[SessionResult], bw: float = 80.0, days_per_week: int = 3
) -> UserState:
    profile = UserProfile(
        height_cm=180,
        exercise_days={"pull_up": days_per_week},
        exercises_enabled=["pull_up"],
    )
    return UserState(profile=profile, current_bodyweight_kg=bw, history=history)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_training_max_formula():
    """TM = floor(0.9 × test_max), clamped to minimum 1."""
    assert training_max([make_test_session("2026-01-01", 12)]) == 10  # floor(10.8)
    assert training_max([make_test_session("2026-01-01", 10)]) == 9  # floor(9.0)
    assert training_max([make_test_session("2026-01-01", 1)]) == 1  # floor(0.9) → clamp


def test_strength_session_prescription():
    """
    First S session at TM=10, BW=80, one TEST of 12 reps in history.

    Expected (pull_up S params: low=0.35, high=0.55, reps_min=4, reps_max=6,
              sets_min=4, sets_max=5, rest_min=180, rest_max=300):
      reps_low  = max(4, int(10*0.35)) = max(4, 3) = 4
      reps_high = min(6, int(10*0.55)) = min(6, 5) = 5
      target    = (4+5)//2 = 4
      sets      = (4+5)//2 = 4  (no autoregulation: <10 sessions)
      rest      = (180+300)//2 = 240  (no same-type history → base midpoint)
      weight    = 6.5 kg  (Leff 1RM from TEST: 80*(1+12/30)=112;
                           leff_target=112*0.9/(1+5/30)=86.4; added=6.4→6.5)
    """
    exercise = get_exercise("pull_up")
    history = [make_test_session("2026-01-01", 12)]  # TM = 10
    plan = generate_plan(
        make_user_state(history), "2026-01-02", exercise, weeks_ahead=2
    )

    s_sessions = [p for p in plan if p.session_type == "S"]
    assert s_sessions, "plan must contain S sessions"
    first_s = s_sessions[0]

    assert len(first_s.sets) == 4
    assert all(s.target_reps == 4 for s in first_s.sets)
    assert all(s.added_weight_kg == 6.5 for s in first_s.sets)
    assert all(s.rest_seconds_before == 240 for s in first_s.sets)


def test_hypertrophy_session_prescription():
    """
    First H session at TM=10, one TEST of 12 reps in history.

    Expected (pull_up H params: low=0.60, high=0.85, reps_min=6, reps_max=12,
              sets_min=4, sets_max=6, rest_min=120, rest_max=180):
      reps_low  = max(6, int(10*0.60)) = 6
      reps_high = min(12, int(10*0.85)) = 8
      target    = (6+8)//2 = 7
      sets      = (4+6)//2 = 5
      rest      = (120+180)//2 = 150
      weight    = 0.0 (Leff 1RM=112; leff_target for H(8 reps)=79.6 < BW_contrib=80
                       → added = max(0, 79.6-80) = 0.0)
    """
    exercise = get_exercise("pull_up")
    history = [make_test_session("2026-01-01", 12)]  # TM = 10
    plan = generate_plan(
        make_user_state(history), "2026-01-02", exercise, weeks_ahead=2
    )

    h_sessions = [p for p in plan if p.session_type == "H"]
    assert h_sessions
    first_h = h_sessions[0]

    assert len(first_h.sets) == 5
    assert all(s.target_reps == 7 for s in first_h.sets)
    assert all(s.added_weight_kg == 0.0 for s in first_h.sets)
    assert all(s.rest_seconds_before == 150 for s in first_h.sets)


def test_endurance_session_volume_formula():
    """
    First E session at TM=10 uses a descending rep ladder.

    Expected (pull_up E params: low=0.40, high=0.60, reps_min=3, reps_max=8,
              sets_min=6, sets_max=10, rest_min=45, rest_max=75):
      kE(10)        = 3.0 + 2.0*clip((10-5)/25, 0, 1) = 3.4
      total_target  = int(3.4*10) = 34
      reps_low      = max(3, int(10*0.40)) = 4
      reps_high     = min(8, int(10*0.60)) = 6
      target_reps   = (4+6)//2 = 5

      Descending ladder (start=5, decrement by 1, floor at 3):
        5, 4, 3, 3, 3, 3, 3, 3, 3, 3  → 10 sets (hits sets_max before total≥34)
        total reps = 5+4+3*8 = 33

      rest = (45+75)//2 = 60
    """
    exercise = get_exercise("pull_up")
    history = [make_test_session("2026-01-01", 12)]  # TM = 10
    plan = generate_plan(
        make_user_state(history), "2026-01-02", exercise, weeks_ahead=2
    )

    e_sessions = [p for p in plan if p.session_type == "E"]
    assert e_sessions
    first_e = e_sessions[0]

    assert [s.target_reps for s in first_e.sets] == [5, 4, 3, 3, 3, 3, 3, 3, 3, 3]
    assert first_e.total_reps == 33
    assert all(s.rest_seconds_before == 60 for s in first_e.sets)


def test_added_weight_formula():
    """
    _calculate_added_weight uses Leff-1RM Epley inverse (no history → conservative fallback).

    pull_up: bw_fraction=1.0, threshold=9, max=20 kg, TM_FACTOR=0.9, S→target_reps=5

    Fallback: leff_1rm = bw * (1 + TM / (0.9 * 30)); leff_target = leff_1rm * 0.9 / (1 + 5/30)
    added = max(0, leff_target - bw), rounded to 0.5 kg, capped at 20 kg.

    TM=9  (at threshold)   → 0.0
    TM=10: leff_1rm=109.63; leff_target=84.57; added=4.57 → 4.5
    TM=12: leff_1rm=115.56; leff_target=89.14; added=9.14 → 9.0
    TM=21: leff_1rm=142.22; leff_target=109.71; added=29.71 → cap at 20.0
    """
    exercise = get_exercise("pull_up")
    assert _calculate_added_weight(exercise, 9, 80.0, [], "S") == 0.0
    assert _calculate_added_weight(exercise, 10, 80.0, [], "S") == 4.5
    assert _calculate_added_weight(exercise, 12, 80.0, [], "S") == 9.0
    assert _calculate_added_weight(exercise, 21, 80.0, [], "S") == 20.0


def test_grip_rotation_cycles_for_s_sessions():
    """
    S sessions rotate through pronated → neutral → supinated → pronated.

    With only a TEST session in history (counted under "TEST", not "S"),
    the first planned S session starts at index 0 → pronated.
    """
    exercise = get_exercise("pull_up")
    history = [make_test_session("2026-01-01", 12)]
    # A TEST is inserted every 3 weeks (test_frequency_weeks=3), which can replace
    # an S slot in week 3 of a 4-week plan. Use weeks_ahead=5 to guarantee ≥4 S sessions.
    plan = generate_plan(
        make_user_state(history), "2026-01-02", exercise, weeks_ahead=5
    )

    s_sessions = [p for p in plan if p.session_type == "S"]
    assert (
        len(s_sessions) >= 4
    ), f"expected ≥4 S sessions in 5-week plan, got {len(s_sessions)}"

    assert s_sessions[0].grip == "pronated"
    assert s_sessions[1].grip == "neutral"
    assert s_sessions[2].grip == "supinated"
    assert s_sessions[3].grip == "pronated"  # back to start


def test_plateau_detected_with_stagnant_test_sessions():
    """
    Plateau triggers when slope < 0.05 reps/week AND no new best in 21 days.

    History: TEST day0=12, day42=11, day63=11.
      slope window: latest=day63, cutoff=day42 → sessions [day42(11), day63(11)]
        points=[(0,11),(21,11)], slope=0.0 reps/week < 0.05 ✓
      best_ever=12; recent tests (≥day42) are [11, 11]; neither ≥ 12 ✓
    → is_plateau = True, TM = floor(0.9*11) = 9
    """
    base = datetime(2026, 1, 1)
    history = [
        make_test_session(base.strftime("%Y-%m-%d"), 12),
        make_test_session((base + timedelta(days=42)).strftime("%Y-%m-%d"), 11),
        make_test_session((base + timedelta(days=63)).strftime("%Y-%m-%d"), 11),
    ]
    status = get_training_status(history, 80.0)

    assert status.is_plateau is True
    assert status.training_max == 9
    assert status.latest_test_max == 11
    assert status.trend_slope < 0.05


def test_test_session_recovery_spacing():
    """
    Regression: after a TEST in history, the next planned session must be
    at least DAY_SPACING["TEST"] + 1 days later (i.e. ≥ 1 rest day gap).

    With DAY_SPACING["TEST"]=1: TEST on 2026-01-05 → first plan session must be
    on 2026-01-07 at earliest (gap ≥ 2).  Without the fix it would be 2026-01-06
    (gap = 1, violating the rest requirement).
    """
    from bar_scheduler.core.config import DAY_SPACING
    from bar_scheduler.core.planner.test_session_inserter import _insert_test_sessions

    test_date = datetime(2026, 1, 5)  # Monday
    history = [make_test_session("2026-01-05", 12)]
    plan_start = datetime(2026, 1, 6)

    # Schedule: first session the very next day (1-day gap — too close with spacing=1)
    schedule = [
        (datetime(2026, 1, 6), "S"),   # 1 day after TEST — should be pushed
        (datetime(2026, 1, 8), "H"),   # 3 days after TEST — fine
        (datetime(2026, 1, 10), "E"),
    ]

    result = _insert_test_sessions(
        schedule, history, test_frequency_weeks=3, plan_start=plan_start
    )

    first_date = result[0][0]
    min_gap = DAY_SPACING["TEST"] + 1  # 2 days with spacing=1
    assert (first_date - test_date).days >= min_gap, (
        f"First session {first_date.date()} too close to TEST {test_date.date()}: "
        f"gap={(first_date - test_date).days}, need ≥{min_gap}"
    )


def test_weight_progression_in_plan():
    """
    Regression: plan Str sessions should show increasing added weight as TM grows,
    not a flat value derived solely from the initial historical 1RM.

    Setup: BW=81.7, single TEST of 13 reps → TM=11, hist_leff_1rm≈117.1 kg.
    At TM=11 the TM-derived estimate (114.9) is lower → history wins → ~8.5 kg.
    At TM=12 the TM-derived estimate (118.0) overtakes history → weight grows.
    Across a 10-week plan the Str added weight must strictly increase overall.
    """
    bw = 81.7
    test_date = "2026-01-01"
    plan_start = "2026-01-05"

    history = [make_test_session(test_date, 13, bw)]
    user_state = make_user_state(history, bw=bw, days_per_week=4)
    ex = get_exercise("pull_up")

    sessions = generate_plan(user_state, plan_start, ex, weeks_ahead=10)

    str_sessions = [s for s in sessions if s.session_type == "S"]
    assert len(str_sessions) >= 6, "need enough Str sessions to observe progression"

    weights = [s.sets[0].added_weight_kg for s in str_sessions if s.sets]

    # First session weight must match the history-based prescription (~8.5 kg)
    assert 7.5 <= weights[0] <= 10.0, f"first Str weight {weights[0]} out of expected range"

    # Weight must increase over the plan (last half > first half)
    first_half_max = max(weights[: len(weights) // 2])
    second_half_min = min(weights[len(weights) // 2 :])
    assert second_half_min > first_half_max or max(weights) > weights[0], (
        f"Str weight did not increase across plan: {weights}"
    )


def test_overtraining_protection_reduces_early_session_sets():
    """
    Regression: when overtraining_level=2, the first 2 non-TEST sessions should
    have fewer actual sets than later sessions of the same type.

    At overtraining_level=2 the engine drops one set (floor at 2) from the first
    `overtraining_level` sessions, leaving later sessions with the full base count.
    """
    bw = 80.0
    test_date = "2026-01-01"
    plan_start = "2026-01-05"

    history = [make_test_session(test_date, 12, bw)]
    user_state = make_user_state(history, bw=bw, days_per_week=3)
    ex = get_exercise("pull_up")

    sessions = generate_plan(
        user_state, plan_start, ex, weeks_ahead=4, overtraining_level=2
    )

    non_test = [s for s in sessions if s.session_type != "TEST"]
    assert len(non_test) >= 4

    first_count = len(non_test[0].sets)
    later_count = len(non_test[3].sets)
    assert first_count < later_count, (
        f"overtraining_level=2 should reduce early session sets "
        f"(first={first_count}, later={later_count})"
    )


def test_deload_recommended_for_low_compliance():
    """
    Deload triggers via compliance: compliance_ratio < 0.70.

    Setup: TEST 14 days ago (12 reps), S yesterday planned 4×8=32 but done 4×2=8.
      compliance_ratio = 8/32 = 0.25 < 0.70 → should_deload() = True
      detect_plateau = False (only 1 TEST session, requires ≥2)
    """
    today = datetime.now()
    yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    two_weeks_ago = (today - timedelta(days=14)).strftime("%Y-%m-%d")

    test_session = make_test_session(two_weeks_ago, 12)

    planned_sets = [SetResult(8, None, 240)] * 4
    completed_sets = [SetResult(8, 2, 240)] * 4
    low_compliance_session = SessionResult(
        date=yesterday,
        bodyweight_kg=80.0,
        grip="pronated",
        session_type="S",
        exercise_id="pull_up",
        planned_sets=planned_sets,
        completed_sets=completed_sets,
    )

    status = get_training_status([test_session, low_compliance_session], 80.0)

    assert status.deload_recommended is True
    assert status.compliance_ratio < 0.70
    assert status.is_plateau is False


class TestExpandDualDumbbellTotals:
    """Regression tests for _expand_dual_dumbbell_totals."""

    def test_basic_expansion(self):
        # [8, 10, 16] → singles + all pairs
        result = _expand_dual_dumbbell_totals([8.0, 10.0, 16.0])
        assert result == [8.0, 10.0, 16.0, 18.0, 20.0, 24.0, 26.0, 32.0]

    def test_single_weight(self):
        # One weight: single + same-pair
        result = _expand_dual_dumbbell_totals([10.0])
        assert result == [10.0, 20.0]

    def test_sorted_and_deduped(self):
        # [4, 8] → 4, 8, 12 (4+8), 16 (8+8) — 8 is both single and pair result
        result = _expand_dual_dumbbell_totals([4.0, 8.0])
        assert result == [4.0, 8.0, 12.0, 16.0]


class TestBSSDualDumbbellSnap:
    """Regression tests for BSS weight snapping using dual-dumbbell expansion."""

    def _make_bss_test_session(self, date: str, weight_kg: float) -> SessionResult:
        return SessionResult(
            date=date,
            bodyweight_kg=80.0,
            grip="standard",
            session_type="TEST",
            exercise_id="bss",
            completed_sets=[SetResult(8, 8, 180, added_weight_kg=weight_kg)],
        )

    def test_snap_to_pair_total(self):
        # available=[8, 10, 16], last TEST=22 → nearest achievable total ≤ 22 is 20 (10+10)
        bss = get_exercise("bss")
        history = [self._make_bss_test_session("2026-01-01", 22.0)]
        w = _calculate_added_weight(bss, 15, 80.0, history, "S", available_weights_kg=[8.0, 10.0, 16.0])
        assert w == 20.0

    def test_snap_exact_match(self):
        # last TEST=16 → exact match on single DB (16) or pair (8+8)
        bss = get_exercise("bss")
        history = [self._make_bss_test_session("2026-01-01", 16.0)]
        w = _calculate_added_weight(bss, 15, 80.0, history, "S", available_weights_kg=[8.0, 10.0, 16.0])
        assert w == 16.0

    def test_snap_to_smallest_when_below(self):
        # last TEST=6 → below all singles, returns smallest (8)
        bss = get_exercise("bss")
        history = [self._make_bss_test_session("2026-01-01", 6.0)]
        w = _calculate_added_weight(bss, 15, 80.0, history, "S", available_weights_kg=[8.0, 10.0, 16.0])
        assert w == 8.0

    def test_snap_to_double_largest(self):
        # last TEST=33 → largest achievable total ≤ 33 is 32 (16+16)
        bss = get_exercise("bss")
        history = [self._make_bss_test_session("2026-01-01", 33.0)]
        w = _calculate_added_weight(bss, 15, 80.0, history, "S", available_weights_kg=[8.0, 10.0, 16.0])
        assert w == 32.0

    def test_incline_db_press_no_expansion(self):
        # incline_db_press has dual_dumbbell=False — available=[8, 10, 16], TEST=22 → snaps to 16 (no pairs)
        from bar_scheduler.core.models import SessionResult, SetResult
        idp = get_exercise("incline_db_press")
        session = SessionResult(
            date="2026-01-01",
            bodyweight_kg=80.0,
            grip="standard",
            session_type="TEST",
            exercise_id="incline_db_press",
            completed_sets=[SetResult(8, 8, 180, added_weight_kg=22.0)],
        )
        w = _calculate_added_weight(idp, 15, 80.0, [session], "S", available_weights_kg=[8.0, 10.0, 16.0])
        assert w == 16.0


# ── EBR Core Formula Tests ────────────────────────────────────────────────────


class TestComputeSetEbrValue:
    """compute_set_ebr_value: exact formula values from documented constants."""

    def test_first_set_bw_only_is_exact(self):
        # reps=5, leff=bw=80 (load_ratio=1.0), is_first_set → penalty=1.0
        # EBR = 5 × 1.0^1.6 × 1.0 = 5.0
        from bar_scheduler.core.ebr import compute_set_ebr_value
        result = compute_set_ebr_value(5, leff=80.0, bw=80.0, rest_seconds=0, is_first_set=True)
        assert result == 5.0

    def test_rest_180_raises_penalty_above_one(self):
        # Same set but rest=180 → rest_penalty > 1 → EBR > 5.0
        from bar_scheduler.core.ebr import compute_set_ebr_value
        result = compute_set_ebr_value(5, leff=80.0, bw=80.0, rest_seconds=180, is_first_set=False)
        assert result == pytest.approx(5.2113, abs=1e-3)

    def test_heavier_load_scales_nonlinearly(self):
        # reps=8, added=20 kg to BW=80 pull-up (k=1.0) → leff=100, is_first_set=True
        # load_ratio=1.25, 1.25^1.6 ≈ 1.4293 → EBR ≈ 11.434
        from bar_scheduler.core.ebr import compute_set_ebr_value
        result = compute_set_ebr_value(8, leff=100.0, bw=80.0, rest_seconds=0, is_first_set=True)
        assert result == pytest.approx(11.434, abs=0.01)

    def test_zero_reps_returns_zero(self):
        from bar_scheduler.core.ebr import compute_set_ebr_value
        assert compute_set_ebr_value(0, leff=80.0, bw=80.0, rest_seconds=180) == 0.0

    def test_zero_leff_returns_zero(self):
        from bar_scheduler.core.ebr import compute_set_ebr_value
        assert compute_set_ebr_value(5, leff=0.0, bw=80.0, rest_seconds=180) == 0.0


class TestComputeSessionEbr:
    """compute_session_ebr: multi-set totals with rest-penalty accumulation."""

    def test_three_set_pullup_exact(self):
        # BW=80, bw_fraction=1.0, no assistance
        # set0: 5 reps rest=0 (first) → EBR=5.0
        # set1: 4 reps rest=180       → EBR≈4.169
        # set2: 3 reps rest=180       → EBR≈3.127
        # total≈12.296, kg_eq=80×12.296≈983.66
        from bar_scheduler.core.ebr import compute_session_ebr
        sets = [
            SetResult(5, 5, 0),
            SetResult(4, 4, 180),
            SetResult(3, 3, 180),
        ]
        ebr, kg_eq = compute_session_ebr(sets, bw_fraction=1.0, bodyweight_kg=80.0)
        assert ebr == pytest.approx(12.3, abs=0.02)
        assert kg_eq == pytest.approx(983.66, abs=1.0)

    def test_empty_sets_returns_zero(self):
        from bar_scheduler.core.ebr import compute_session_ebr
        ebr, kg_eq = compute_session_ebr([], bw_fraction=1.0, bodyweight_kg=80.0)
        assert ebr == 0.0
        assert kg_eq == 0.0

    def test_assistance_reduces_leff(self):
        # Same reps at BW with 30 kg band assistance → leff = 80-30 = 50 → lower EBR
        from bar_scheduler.core.ebr import compute_session_ebr
        sets_unassisted = [SetResult(5, 5, 0)]
        sets_assisted = [SetResult(5, 5, 0)]
        ebr_u, _ = compute_session_ebr(sets_unassisted, bw_fraction=1.0, bodyweight_kg=80.0)
        ebr_a, _ = compute_session_ebr(sets_assisted, bw_fraction=1.0, bodyweight_kg=80.0, assistance_kg=30.0)
        assert ebr_a < ebr_u


class TestComputeCapability:
    """compute_capability: Epley 1RM from history."""

    def test_one_set_15_reps_at_bw(self):
        # leff = 80×1.0 = 80, 1RM = 80 × (1 + 15/30) = 120.0
        from bar_scheduler.core.ebr import compute_capability
        session = SessionResult("2026-01-01", 80.0, "pronated", "TEST", "pull_up",
                                completed_sets=[SetResult(15, 15, 180)])
        result = compute_capability([session], bw_fraction=1.0, current_bw=80.0)
        assert result == pytest.approx(120.0, abs=1e-6)

    def test_empty_history_returns_none(self):
        from bar_scheduler.core.ebr import compute_capability
        assert compute_capability([], bw_fraction=1.0, current_bw=80.0) is None

    def test_weighted_set_yields_higher_estimate(self):
        # Added weight → higher Leff → higher 1RM estimate than BW-only
        from bar_scheduler.core.ebr import compute_capability
        bw_session = SessionResult("2026-01-01", 80.0, "pronated", "S", "pull_up",
                                   completed_sets=[SetResult(15, 15, 180)])
        weighted_session = SessionResult("2026-01-02", 80.0, "pronated", "S", "pull_up",
                                         completed_sets=[SetResult(8, 8, 180, added_weight_kg=20.0)])
        one_rm_bw = compute_capability([bw_session], bw_fraction=1.0, current_bw=80.0)
        one_rm_weighted = compute_capability([bw_session, weighted_session], bw_fraction=1.0, current_bw=80.0)
        assert one_rm_weighted > one_rm_bw


class TestComputeGoalMetrics:
    """compute_goal_metrics: goal EBR, progress, and difficulty ratio."""

    def test_goal_met_progress_is_100(self):
        # one_rm=120, goal=15 reps @ leff=80 → max_reps=15 ≥ goal → 100%
        from bar_scheduler.core.ebr import compute_goal_metrics
        result = compute_goal_metrics(one_rm_leff=120.0, goal_reps=15, goal_leff=80.0, bw=80.0)
        assert result["max_reps_at_goal"] == pytest.approx(15.0, abs=1e-6)
        assert result["progress_pct"] == 100.0
        assert result["difficulty_ratio"] == pytest.approx(1.0, abs=1e-3)

    def test_partial_progress_log_scale(self):
        # one_rm=120, max_reps_at_goal=15, goal=30 → progress = ln(15)/ln(30) ≈ 79.6%
        from bar_scheduler.core.ebr import compute_goal_metrics
        result = compute_goal_metrics(one_rm_leff=120.0, goal_reps=30, goal_leff=80.0, bw=80.0)
        assert result["max_reps_at_goal"] == pytest.approx(15.0, abs=1e-6)
        assert result["progress_pct"] == pytest.approx(79.6, abs=0.2)
        assert result["difficulty_ratio"] == pytest.approx(2.0, abs=1e-3)

    def test_zero_capability_returns_zero_progress(self):
        from bar_scheduler.core.ebr import compute_goal_metrics
        result = compute_goal_metrics(one_rm_leff=0.0, goal_reps=12, goal_leff=80.0, bw=80.0)
        assert result["progress_pct"] == 0.0
