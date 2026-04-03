"""
Library-level integration tests for the bar-scheduler planning engine.

These tests call core functions directly -- no CLI, no CliRunner, no Typer.
Each test builds a specific history state and compares exact computed values
against hand-calculated expectations derived from the documented formulas.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from bar_scheduler.core.adaptation import apply_autoregulation, get_training_status
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.metrics import training_max
from bar_scheduler.core.models import (
    FitnessFatigueState,
    SessionResult,
    SetResult,
    UserProfile,
    UserState,
)
from bar_scheduler.core.planner.grip_selector import _init_grip_counts, _next_grip
from bar_scheduler.core.planner.load_calculator import (
    _calculate_added_weight,
    _expand_dual_dumbbell_totals,
)
from bar_scheduler.core.planner.plan_engine import generate_plan
from bar_scheduler.core.planner.set_prescriptor import (
    _classify_level,
    calculate_set_prescription,
)


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
        bodyweight_kg=bw,
        exercise_days={"pull_up": days_per_week},
        exercises_enabled=["pull_up"],
    )
    return UserState(profile=profile, history=history)


def make_session(
    date: str,
    session_type: str,
    grip: str,
    exercise_id: str = "pull_up",
    reps: int = 7,
    bw: float = 80.0,
) -> SessionResult:
    """Minimal session with specified type and grip."""
    s = SetResult(reps, reps, 150)
    return SessionResult(date, bw, grip, session_type, exercise_id, completed_sets=[s])


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_training_max_formula():
    """TM = floor(0.9 × test_max), clamped to minimum 1."""
    assert training_max([make_test_session("2026-01-01", 12)]) == 10  # floor(10.8)
    assert training_max([make_test_session("2026-01-01", 10)]) == 9  # floor(9.0)
    assert (
        training_max([make_test_session("2026-01-01", 1)]) == 1
    )  # floor(0.9) -> clamp


def test_strength_session_prescription():
    """
    First S session at TM=10, BW=80, test_max=12 in history.

    Level classification: _classify_level(12, [4,13,24]) → level 1
    S sets_by_level[1] = 2 sets.

    Expected (pull_up S params: low=0.35, high=0.55, reps_min=4, reps_max=6,
              rest_min=180, rest_max=300):
      reps_low  = max(4, int(10*0.35)) = max(4, 3) = 4
      reps_high = min(6, int(10*0.55)) = min(6, 5) = 5
      target    = (4+5)//2 = 4
      sets      = sets_by_level[1] = 2  (level-based, no autoregulation: <10 sessions)
      rest      = (180+300)//2 = 240  (no same-type history -> base midpoint)
      weight    = 6.5 kg  (Leff 1RM from TEST: 80*(1+12/30)=112;
                           leff_target=112*0.9/(1+5/30)=86.4; added=6.4->6.5)

    Rep decay (set_fatigue_curve=[1.0, 0.85, ...]):
      set1 = round(4*1.00) = 4
      set2 = round(4*0.85) = 3
    """
    exercise = get_exercise("pull_up")
    history = [make_test_session("2026-01-01", 12)]  # TM = 10
    plan = generate_plan(
        make_user_state(history), "2026-01-02", exercise, weeks_ahead=2
    )

    s_sessions = [p for p in plan if p.session_type == "S"]
    assert s_sessions, "plan must contain S sessions"
    first_s = s_sessions[0]

    assert len(first_s.sets) == 2
    assert first_s.sets[0].target_reps == 4
    assert first_s.sets[1].target_reps == 3
    assert all(s.added_weight_kg == 6.5 for s in first_s.sets)
    assert all(s.rest_seconds_before == 240 for s in first_s.sets)


def test_hypertrophy_session_prescription():
    """
    First H session at TM=10, test_max=12 in history.

    Level classification: _classify_level(12, [4,13,24]) → level 1
    H sets_by_level[1] = 3 sets.

    Expected (pull_up H params: low=0.60, high=0.85, reps_min=6, reps_max=12,
              rest_min=120, rest_max=180):
      reps_low  = max(6, int(10*0.60)) = 6
      reps_high = min(12, int(10*0.85)) = 8
      target    = (6+8)//2 = 7
      sets      = sets_by_level[1] = 3  (level-based, no autoregulation: <10 sessions)
      rest      = (120+180)//2 = 150
      weight    = 0.0 (Leff 1RM=112; leff_target for H(8 reps)=79.6 < BW_contrib=80
                       -> added = max(0, 79.6-80) = 0.0)

    Rep decay (set_fatigue_curve=[1.0, 0.85, 0.75, ...]):
      set1 = round(7*1.00) = 7
      set2 = round(7*0.85) = 6
      set3 = round(7*0.75) = 5
    """
    exercise = get_exercise("pull_up")
    history = [make_test_session("2026-01-01", 12)]  # TM = 10
    plan = generate_plan(
        make_user_state(history), "2026-01-02", exercise, weeks_ahead=2
    )

    h_sessions = [p for p in plan if p.session_type == "H"]
    assert h_sessions
    first_h = h_sessions[0]

    assert len(first_h.sets) == 3
    assert first_h.sets[0].target_reps == 7
    assert first_h.sets[1].target_reps == 6
    assert first_h.sets[2].target_reps == 5
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
        5, 4, 3, 3, 3, 3, 3, 3, 3, 3  -> 10 sets (hits sets_max before total≥34)
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
    _calculate_added_weight uses Leff-1RM Epley inverse (no history -> TM-derived fallback).

    Epley is capped at _MAX_EPLEY_REPS=12 to prevent over-prescription for high rep TMs.
    pull_up: bw_fraction=1.0, threshold=9, max=20 kg, TM_FACTOR=0.9, S->target_reps=5

    Fallback: leff_1rm_tm = bw * (1 + min(TM, 0.9*12) / (0.9*30))
              leff_target = leff_1rm * 0.9 / (1 + 5/30)
              added = max(0, leff_target - bw), rounded to 0.5 kg.

    TM=9  (at threshold)   -> 0.0
    TM=10: min(10, 10.8)=10; leff_1rm=80*(1+10/27)=109.63; leff_target=84.57; added=4.5
    TM=12: min(12, 10.8)=10.8; leff_1rm=80*(1+10.8/27)=112.0; leff_target=86.4; added=6.5
    TM=21: min(21, 10.8)=10.8; leff_1rm=112.0 (capped, same as TM=12); added=6.5
    """
    exercise = get_exercise("pull_up")
    assert _calculate_added_weight(exercise, 9, 80.0, [], "S") == 0.0
    assert _calculate_added_weight(exercise, 10, 80.0, [], "S") == 4.5
    assert _calculate_added_weight(exercise, 12, 80.0, [], "S") == 6.5
    assert _calculate_added_weight(exercise, 21, 80.0, [], "S") == 6.5


def test_grip_rotation_cycles_for_s_sessions():
    """
    S sessions rotate through pronated -> neutral -> supinated -> pronated.

    With only a TEST session in history (counted under "TEST", not "S"),
    the first planned S session starts at index 0 -> pronated.
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
      slope window: latest=day63, cutoff=day42 -> sessions [day42(11), day63(11)]
        points=[(0,11),(21,11)], slope=0.0 reps/week < 0.05 ✓
      best_ever=12; recent tests (≥day42) are [11, 11]; neither ≥ 12 ✓
    -> is_plateau = True, TM = floor(0.9*11) = 9
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

    With DAY_SPACING["TEST"]=1: TEST on 2026-01-05 -> first plan session must be
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
        (datetime(2026, 1, 6), "S"),  # 1 day after TEST — should be pushed
        (datetime(2026, 1, 8), "H"),  # 3 days after TEST — fine
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
    Regression: plan Str sessions should prescribe reasonable weight.

    Setup: BW=81.7, single TEST of 13 reps -> TM=11.
    Epley cap at 12 reps: leff_1rm_tm = 81.7*(1+min(11,10.8)/27) = 114.38 kg.
    hist 1RM: 81.7*(1+min(13,12)/30) = 114.38 kg.  Both estimates coincide at cap.
    S target reps=5: leff_target = 114.38*0.9/(1+5/30) = 88.24; added = 6.5 kg.

    With fixed pre-plan history, the TM-derived 1RM is capped for all plan sessions.
    Weight stays flat at ~6.5 kg across the plan — this is correct capped behavior.
    Once the user logs heavier sessions the history-based ratchet will take over.
    """
    bw = 81.7
    test_date = "2026-01-01"
    plan_start = "2026-01-05"

    history = [make_test_session(test_date, 13, bw)]
    user_state = make_user_state(history, bw=bw, days_per_week=4)
    ex = get_exercise("pull_up")

    sessions = generate_plan(user_state, plan_start, ex, weeks_ahead=10)

    str_sessions = [s for s in sessions if s.session_type == "S"]
    assert len(str_sessions) >= 6, "need enough Str sessions to observe"

    weights = [s.sets[0].added_weight_kg for s in str_sessions if s.sets]

    # Initial weight must be in the Epley-capped range
    assert (
        5.5 <= weights[0] <= 8.5
    ), f"first Str weight {weights[0]} out of expected range"

    # Weight must not decrease across the plan
    assert min(weights) >= weights[0], f"Str weight decreased: {weights}"


def test_overtraining_protection_reduces_early_session_sets():
    """
    Regression: when overtraining_level=2, early sessions should have fewer sets.

    At overtraining_level=2 the engine drops one set (when len > 2) from the first
    `overtraining_level` sessions, leaving later sessions with the full base count.

    test_max=25 → level 3 → S sets_by_level[3]=4.
    overtraining_level=2 triggers drop: first S = 3 sets (dropped from 4).
    Later S sessions (after density_sessions_left=0) = 4 sets.
    """
    bw = 80.0
    test_date = "2026-01-01"
    plan_start = "2026-01-05"

    history = [make_test_session(test_date, 25, bw)]  # level 3 → 4 S sets
    user_state = make_user_state(history, bw=bw, days_per_week=3)
    ex = get_exercise("pull_up")

    sessions = generate_plan(
        user_state, plan_start, ex, weeks_ahead=4, overtraining_level=2
    )

    s_sessions = [s for s in sessions if s.session_type == "S"]
    assert len(s_sessions) >= 4

    first_s_count = len(s_sessions[0].sets)
    later_s_count = len(s_sessions[3].sets)
    assert first_s_count < later_s_count, (
        f"overtraining_level=2 should reduce early S session sets "
        f"(first={first_s_count}, later={later_s_count})"
    )


def test_deload_recommended_for_low_compliance():
    """
    Deload triggers via compliance: compliance_ratio < 0.70.

    Setup: TEST 14 days ago (12 reps), S yesterday planned 4×8=32 but done 4×2=8.
      compliance_ratio = 8/32 = 0.25 < 0.70 -> should_deload() = True
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
        # [8, 10, 16] -> singles + all pairs
        result = _expand_dual_dumbbell_totals([8.0, 10.0, 16.0])
        assert result == [8.0, 10.0, 16.0, 18.0, 20.0, 24.0, 26.0, 32.0]

    def test_single_weight(self):
        # One weight: single + same-pair
        result = _expand_dual_dumbbell_totals([10.0])
        assert result == [10.0, 20.0]

    def test_sorted_and_deduped(self):
        # [4, 8] -> 4, 8, 12 (4+8), 16 (8+8) — 8 is both single and pair result
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
        # available=[8, 10, 16], last TEST=22 -> nearest achievable total ≤ 22 is 20 (10+10)
        bss = get_exercise("bss")
        history = [self._make_bss_test_session("2026-01-01", 22.0)]
        w = _calculate_added_weight(
            bss, 15, 80.0, history, "S", available_weights_kg=[8.0, 10.0, 16.0]
        )
        assert w == 20.0

    def test_snap_exact_match(self):
        # last TEST=16 -> exact match on single DB (16) or pair (8+8)
        bss = get_exercise("bss")
        history = [self._make_bss_test_session("2026-01-01", 16.0)]
        w = _calculate_added_weight(
            bss, 15, 80.0, history, "S", available_weights_kg=[8.0, 10.0, 16.0]
        )
        assert w == 16.0

    def test_snap_to_smallest_when_below(self):
        # last TEST=6 -> below all singles, returns smallest (8)
        bss = get_exercise("bss")
        history = [self._make_bss_test_session("2026-01-01", 6.0)]
        w = _calculate_added_weight(
            bss, 15, 80.0, history, "S", available_weights_kg=[8.0, 10.0, 16.0]
        )
        assert w == 8.0

    def test_snap_to_double_largest(self):
        # last TEST=33 -> largest achievable total ≤ 33 is 32 (16+16)
        bss = get_exercise("bss")
        history = [self._make_bss_test_session("2026-01-01", 33.0)]
        w = _calculate_added_weight(
            bss, 15, 80.0, history, "S", available_weights_kg=[8.0, 10.0, 16.0]
        )
        assert w == 32.0

    def test_incline_db_press_no_expansion(self):
        # incline_db_press has dual_dumbbell=False — available=[8, 10, 16], TEST=22 -> snaps to 16 (no pairs)
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
        w = _calculate_added_weight(
            idp, 15, 80.0, [session], "S", available_weights_kg=[8.0, 10.0, 16.0]
        )
        assert w == 16.0


# ── best_1rm_from_leff Tests ──────────────────────────────────────────────────


class TestBest1rmFromLeff:
    """best_1rm_from_leff: rep-range-aware 1RM in Leff units."""

    def test_zero_reps_returns_none(self):
        from bar_scheduler.core.metrics import best_1rm_from_leff

        assert best_1rm_from_leff(80.0, 0) is None

    def test_over_20_reps_returns_estimate(self):
        # No upper cap — Lombardi+Epley blend used for all r > 10
        from bar_scheduler.core.metrics import best_1rm_from_leff

        result = best_1rm_from_leff(80.0, 25)
        assert result is not None and result > 80.0

    def test_strength_range_uses_brzycki_lander_blend(self):
        # r=5, leff=100
        # brzycki: 100 / (1.0278 - 0.0278*5) = 100 / 0.889 ≈ 112.49
        # lander:  100*100 / (101.3 - 2.67123*5) = 10000 / 87.94 ≈ 113.71
        # avg ≈ 113.10
        from bar_scheduler.core.metrics import best_1rm_from_leff

        result = best_1rm_from_leff(100.0, 5)
        assert result == pytest.approx(113.1, abs=0.5)

    def test_moderate_range_three_formula_blend(self):
        # r=8, leff=100: avg(Brzycki, Lander, Epley)
        # epley: 100 * (1 + 8/30) ≈ 126.67
        from bar_scheduler.core.metrics import best_1rm_from_leff

        result = best_1rm_from_leff(100.0, 8)
        assert result is not None
        assert 115.0 < result < 135.0  # sanity range

    def test_high_rep_range_lombardi_epley_blend(self):
        # r=15, leff=80
        from bar_scheduler.core.metrics import best_1rm_from_leff

        result = best_1rm_from_leff(80.0, 15)
        assert result is not None
        assert result > 80.0  # 1RM must exceed working load

    def test_result_exceeds_working_leff(self):
        # For any valid rep count, 1RM ≥ leff
        from bar_scheduler.core.metrics import best_1rm_from_leff

        for reps in [1, 5, 10, 15, 20]:
            result = best_1rm_from_leff(100.0, reps)
            assert result is not None and result >= 100.0

    def test_high_reps_above_20_returns_estimate(self):
        from bar_scheduler.core.metrics import best_1rm_from_leff

        assert best_1rm_from_leff(80.0, 30) is not None


# ── Regression tests ──────────────────────────────────────────────────────────


def test_overtraining_severity_no_alert_two_sessions_five_days():
    """
    Regression: 2 sessions in 5 days at 3x/week should NOT trigger an alert.

    The expected span for n=2 sessions is (n-1)=1 interval = 7/3 ≈ 2.33 days.
    Actual span = 4 days (03.25->03.29) > 2.33 -> no overtraining.
    Previously the formula used n*interval = 4.67 days, causing extra=1, level=1.
    """
    from bar_scheduler.core.adaptation import overtraining_severity

    s1 = SetResult(12, 12, 180, added_weight_kg=10.0)
    s2 = SetResult(5, 5, 180, added_weight_kg=24.0)
    session1 = SessionResult(
        "2026-03-25", 82.0, "standard", "TEST", "incline_db_press", completed_sets=[s1]
    )
    session2 = SessionResult(
        "2026-03-29",
        82.0,
        "standard",
        "S",
        "incline_db_press",
        completed_sets=[s2, s2, s2],
    )
    result = overtraining_severity(
        [session1, session2], days_per_week=3, reference_date=datetime(2026, 3, 30)
    )
    assert result["level"] == 0
    assert result["description"] == "2 sessions in 5 days"


def test_session_max_reps_weighted_test_session():
    """
    Regression: session_max_reps should return max reps from all sets when
    no bodyweight-only sets exist (e.g., external_only exercise TEST with added weight).
    Previously returned 0 for any session with only weighted sets.
    """
    from bar_scheduler.core.metrics import session_max_reps

    s = SetResult(12, 12, 180, added_weight_kg=10.0)
    session = SessionResult(
        "2026-03-25", 82.0, "standard", "TEST", "incline_db_press", completed_sets=[s]
    )
    assert session_max_reps(session) == 12


def test_external_only_zero_bw_prescription_uses_history():
    """
    Regression: for external_only exercises with bw_fraction=0, the weight
    prescription must use Leff 1RM from all history, not just the last TEST weight.

    Str session at +24.0kg for 12 reps -> Epley 1RM = 24*(1+12/30) = 33.6 kg.
    Hpy target (8 reps): leff_target = 33.6*0.9/(1+8/30) ≈ 23.87 -> rounds to 24.0 kg.
    Previously returned 0.0 (no TEST in history -> _last_test_weight_bss=0).
    """
    exercise = get_exercise("incline_db_press")
    s = SetResult(12, 12, 180, added_weight_kg=24.0)
    str_session = SessionResult(
        "2026-03-29",
        82.0,
        "standard",
        "S",
        "incline_db_press",
        completed_sets=[s, s, s],
    )
    added = _calculate_added_weight(exercise, 10, 82.0, [str_session], "H")
    assert added == pytest.approx(24.0, abs=0.5)


# ── Level-based adaptive set counts + intra-session decay ─────────────────────


def test_classify_level():
    """
    _classify_level returns the correct 0-indexed level from test_max and thresholds.

    level = first index i where test_max <= threshold, else len(thresholds).
    None input → middle level (default fallback).
    """
    lt = [4, 13, 24]  # 4 levels: 0, 1, 2, 3
    assert _classify_level(None, lt) == 1  # middle of 4 levels: (3-1)//2 = 1
    assert _classify_level(4, lt) == 0  # 4 <= lt[0]=4
    assert _classify_level(13, lt) == 1  # 13 <= lt[1]=13 (inclusive)
    assert _classify_level(14, lt) == 2  # 14 <= lt[2]=24
    assert _classify_level(25, lt) == 3  # 25 > all → len=3
    assert _classify_level(13, None) == 0  # no thresholds → default 0


def test_dip_s_weight_capped_epley():
    """
    Dip S weight for TM=18 (test_max=20) with Epley cap.

    Without cap: leff_1rm_tm ≈ 125.7 → added ≈ 21.5 kg (over-prescription).
    With cap (min(TM, 0.9*12)=10.8): leff_1rm_tm = 75.44*1.4 = 105.6 kg.
    leff_target (S, 5 reps) = 105.6*0.9/1.167 ≈ 81.5; added ≈ 6 kg.
    """
    exercise = get_exercise("dip")
    added = _calculate_added_weight(exercise, 18, 82.0, [], "S")
    assert added == pytest.approx(6.0, abs=0.5)


def test_pull_up_h_level1_3_sets_with_decay():
    """
    Pull-up H session: test_max=13 → level 1 → 3 sets, reps decay 7→6→5.

    TM = floor(0.9*13) = 11
    reps_low=6, reps_high=9, target=7
    sets_by_level=[2,3,4,5][1] = 3
    set_fatigue_curve=[1.0, 0.85, 0.75, ...]:
      set1=round(7*1.00)=7, set2=round(7*0.85)=6, set3=round(7*0.75)=5
    total=18 (1.38× test_max=13 ✓)
    """
    exercise = get_exercise("pull_up")
    ff = FitnessFatigueState()  # neutral: z=0, no autoregulation
    sets = calculate_set_prescription(
        "H", 11, ff, 80.0, exercise=exercise, history=[], latest_test_max=13
    )
    assert len(sets) == 3
    assert sets[0].target_reps == 7
    assert sets[1].target_reps == 6
    assert sets[2].target_reps == 5
    assert sum(s.target_reps for s in sets) == 18


def test_dip_h_level2_4_sets_with_decay():
    """
    Dip H session: test_max=20 → level 2 → 4 sets, reps decay 11→9→8→7.

    TM = floor(0.9*20) = 18
    reps_low=9, reps_high=13, target=11
    level_thresholds=[7,19,33]: 20>19 → level 2; sets_by_level=[2,3,4,5][2] = 4
    set_fatigue_curve=[1.0, 0.85, 0.75, 0.68, ...]:
      set1=11, set2=round(11*0.85)=9, set3=round(11*0.75)=8, set4=round(11*0.68)=7
    total=35 (1.75× test_max=20 ✓)
    """
    exercise = get_exercise("dip")
    ff = FitnessFatigueState()
    sets = calculate_set_prescription(
        "H", 18, ff, 82.0, exercise=exercise, history=[], latest_test_max=20
    )
    assert len(sets) == 4
    assert sets[0].target_reps > sets[1].target_reps
    assert sets[1].target_reps >= sets[2].target_reps
    assert sets[2].target_reps >= sets[3].target_reps
    assert sum(s.target_reps for s in sets) == 35


def test_autoregulation_floor_respects_sets_min():
    """
    apply_autoregulation with low readiness uses sets_min as floor, not hardcoded 3.

    Extreme fatigue: z = (0-10-0)/1 = -10 << READINESS_Z_LOW=-1.0
    base_sets=2, READINESS_VOLUME_REDUCTION=0.30:
      adjusted = max(sets_min=1, int(2*(1-0.30))) = max(1, int(1.4)) = max(1,1) = 1
    Old behaviour (hardcoded floor=3): max(3, 1) = 3 → over-prescribing for beginners.
    """
    ff = FitnessFatigueState(fitness=0.0, fatigue=10.0, readiness_mean=0.0, readiness_var=1.0)
    adj_sets, adj_reps = apply_autoregulation(2, 7, ff, sets_min=1)
    assert adj_sets == 1


def test_grip_rotation_recovers_after_deviation():
    """
    After a deviant grip is logged, rotation resumes from the correct position.

    History: [H:pronated, H:neutral, H:pronated]  ← 3rd is deviant (should have been supinated)
    _init_grip_counts: last_grip["H"]="pronated" → cycle.index("pronated")=0 → count=1
    Next grips from count=1: neutral → supinated → pronated (correct cycle resume).
    """
    exercise = get_exercise("pull_up")
    history = [
        make_session("2026-01-01", "H", "pronated"),
        make_session("2026-01-08", "H", "neutral"),
        make_session("2026-01-15", "H", "pronated"),  # deviant: should have been supinated
    ]
    counts = _init_grip_counts(history, exercise)
    assert counts.get("H") == 1  # index-after-last: pronated is at index 0, so count=1
    assert _next_grip("H", counts, exercise) == "neutral"
    assert _next_grip("H", counts, exercise) == "supinated"
    assert _next_grip("H", counts, exercise) == "pronated"  # back to start


def test_grip_rotation_normal_no_deviation():
    """
    Normal rotation: last grip was neutral → next is supinated.

    History: [H:pronated, H:neutral]
    last_grip["H"] = "neutral" → cycle.index("neutral")=1 → count=2
    next: cycle[2%3] = "supinated" ✓
    """
    exercise = get_exercise("pull_up")
    history = [
        make_session("2026-01-01", "H", "pronated"),
        make_session("2026-01-08", "H", "neutral"),
    ]
    counts = _init_grip_counts(history, exercise)
    assert counts.get("H") == 2
    assert _next_grip("H", counts, exercise) == "supinated"
