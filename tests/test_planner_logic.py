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
from bar_scheduler.core.planner.load_calculator import _calculate_added_weight
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
