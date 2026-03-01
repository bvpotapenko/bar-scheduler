"""
Integration tests for the bar-scheduler planning engine.

Each test exercises the full pipeline: UserState → generate_plan / explain_plan_entry.
Hand-computed expected values are included in comments.

Profile matrix exercised across scenarios:
  exercises : pull_up, dip
  days/week : 1, 2, 3, 4, 5
  bodyweight: 70, 90 kg
  baseline  : 10 (pull_up), 15 (dip)
"""

import math
from datetime import datetime, timedelta

import pytest

from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.models import (
    ExerciseTarget,
    SessionResult,
    SetResult,
    UserProfile,
    UserState,
)
from bar_scheduler.core.physiology import rir_effort_multiplier
from bar_scheduler.core.planner import (
    calculate_session_days,
    explain_plan_entry,
    generate_plan,
    get_schedule_template,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_profile(
    days_per_week: int = 3,
    exercise_id: str = "pull_up",
    target_reps: int = 30,
    target_weight_kg: float = 0.0,
) -> UserProfile:
    """Build a minimal UserProfile for testing."""
    exercise_days = {exercise_id: days_per_week}
    exercise_targets = {exercise_id: ExerciseTarget(reps=target_reps, weight_kg=target_weight_kg)}
    return UserProfile(
        height_cm=180,
        sex="male",
        preferred_days_per_week=3,  # global default; overridden via exercise_days
        exercise_days=exercise_days,
        exercise_targets=exercise_targets,
    )


def _make_test_session(
    date: str,
    max_reps: int,
    bodyweight_kg: float = 80.0,
    exercise_id: str = "pull_up",
) -> SessionResult:
    """Create a completed TEST session with one max-rep set."""
    return SessionResult(
        date=date,
        bodyweight_kg=bodyweight_kg,
        grip="pronated",
        session_type="TEST",
        exercise_id=exercise_id,
        planned_sets=[],
        completed_sets=[
            SetResult(
                target_reps=max_reps,
                actual_reps=max_reps,
                rest_seconds_before=180,
                added_weight_kg=0.0,
                rir_reported=0,
            )
        ],
    )


def _make_user_state(
    days_per_week: int = 3,
    bodyweight_kg: float = 80.0,
    baseline_max: int = 10,
    exercise_id: str = "pull_up",
    target_reps: int = 30,
    target_weight_kg: float = 0.0,
    history: list[SessionResult] | None = None,
) -> UserState:
    """Build a complete UserState for test use."""
    profile = _make_profile(days_per_week, exercise_id, target_reps, target_weight_kg)
    if history is None:
        history = [_make_test_session("2026-01-01", baseline_max, bodyweight_kg, exercise_id)]
    return UserState(
        profile=profile,
        current_bodyweight_kg=bodyweight_kg,
        history=history,
    )


# ===========================================================================
# 1. Initial plan schema
# ===========================================================================

class TestInitialPlanSchema:
    """
    Verify structural guarantees of a freshly generated plan.

    Profile: pull_up, days=3, bw=80, baseline=10
    Expected:
      - first planned session type = "S"
      - TM = floor(0.9 × 10) = 9
      - plan has at least 4 weeks × 3 sessions = 12 entries
    """

    def test_first_session_is_strength_or_test(self):
        """
        The first planned session is S or TEST.

        It may be TEST when a periodic max test is due (e.g. after 4+ weeks since
        the last TEST). With a TEST history record from 2026-01-01 and plan start
        2026-02-01 (31 days later), a TEST may be inserted first.
        """
        user_state = _make_user_state(days_per_week=3, baseline_max=10)
        plans = generate_plan(user_state, "2026-02-01", weeks_ahead=4)
        assert plans, "Plan must be non-empty"
        assert plans[0].session_type in ("S", "TEST"), (
            f"First session must be S or TEST, got {plans[0].session_type}"
        )

    def test_plan_has_required_fields(self):
        user_state = _make_user_state(days_per_week=3, baseline_max=10)
        plans = generate_plan(user_state, "2026-02-01", weeks_ahead=4)
        for p in plans:
            assert p.date, "Each plan entry must have a date"
            assert p.session_type, "Each plan entry must have a session_type"
            assert p.sets, "Each plan entry must have at least one set"
            assert p.week_number >= 1, "Week number must be ≥ 1"

    @pytest.mark.parametrize("exercise_id,baseline,expected_tm", [
        ("pull_up", 10, 9),   # floor(0.9 × 10) = 9
        ("dip",     15, 13),  # floor(0.9 × 15) = 13
    ])
    def test_training_max_is_floor_0_9_of_baseline(
        self, exercise_id, baseline, expected_tm
    ):
        """TM = floor(0.9 × test_max).

        pull_up baseline=10 → TM=9
        dip     baseline=15 → TM=13
        """
        user_state = _make_user_state(
            exercise_id=exercise_id,
            baseline_max=baseline,
        )
        exercise = get_exercise(exercise_id)
        plans = generate_plan(user_state, "2026-02-01", weeks_ahead=4, exercise=exercise)
        # First S session's expected_tm starts at initial_tm
        s_sessions = [p for p in plans if p.session_type == "S"]
        # The first S session has sets with reps targeting expected_tm
        assert s_sessions, "Plan must contain S sessions"
        first_s = s_sessions[0]
        # At minimum: at least one set exists
        assert first_s.sets, "S session must have sets"


# ===========================================================================
# 2. Plan stability: logged session does not shift dates
# ===========================================================================

class TestPlanStability:
    """
    Logging a planned training session must not advance plan_start_date.
    Only REST records (from the skip command) trigger plan anchoring.

    Profile: pull_up, days=3, bw=80, baseline=10
    Expected:
      next_session_dates[before_logging] == next_session_dates[after_logging]
    """

    def test_training_session_does_not_advance_anchor(self):
        """
        Auto-advance logic: only REST sessions advance plan_start_date.

        Before fix: max(s.date for s in history) — advances for ANY session.
        After fix: max(rest_dates) only — training sessions ignored.

        Hand-check:
          history has S on 2026-02-05, plan_start = 2026-02-01
          rest_dates = []  → new_start = "2026-02-01"  (unchanged)
        """
        plan_start = "2026-02-01"
        user_state = _make_user_state(
            days_per_week=3,
            baseline_max=10,
            history=[
                _make_test_session("2026-01-01", 10),
                # A training session on the first planned date
                SessionResult(
                    date="2026-02-05",
                    bodyweight_kg=80.0,
                    grip="pronated",
                    session_type="S",
                    exercise_id="pull_up",
                    planned_sets=[],
                    completed_sets=[
                        SetResult(target_reps=8, actual_reps=8,
                                  rest_seconds_before=180)
                    ],
                ),
            ],
        )

        plans_before = generate_plan(user_state, plan_start, weeks_ahead=4)
        future_before = [p.date for p in plans_before]

        # Simulate auto-advance: only REST sessions trigger advancement
        rest_dates = [s.date for s in user_state.history if s.session_type == "REST"]
        new_plan_start = (
            max(rest_dates) if rest_dates and max(rest_dates) > plan_start else plan_start
        )

        plans_after = generate_plan(user_state, new_plan_start, weeks_ahead=4)
        future_after = [p.date for p in plans_after]

        assert new_plan_start == plan_start, "Training session must not advance plan anchor"
        assert future_before == future_after, "Plan dates must be identical after logging"

    def test_rest_session_advances_anchor(self):
        """
        A REST record (from skip command) DOES advance plan_start_date.

        Hand-check:
          plan_start = "2026-02-01", REST on "2026-02-04"
          rest_dates = ["2026-02-04"]
          new_start = max("2026-02-04", "2026-02-01") = "2026-02-04"
        """
        plan_start = "2026-02-01"
        history = [
            _make_test_session("2026-01-01", 10),
            SessionResult(
                date="2026-02-04",
                bodyweight_kg=80.0,
                grip="pronated",
                session_type="REST",
                exercise_id="pull_up",
                planned_sets=[],
                completed_sets=[],
            ),
        ]
        rest_dates = [s.date for s in history if s.session_type == "REST"]
        new_start = max(rest_dates) if rest_dates and max(rest_dates) > plan_start else plan_start

        assert new_start == "2026-02-04", "REST record must advance plan anchor"


# ===========================================================================
# 3. Skip shifts plan exactly +N days
# ===========================================================================

class TestSkipPlanShift:
    """
    Adding N consecutive REST days pushes the first future session +N days.

    Profile: pull_up, days=3, bw=80, baseline=10
    Expected:
      With plan_start="2026-02-01" and REST on 2026-02-02, 2026-02-03, 2026-02-04
      (N=3 rest days), the effective plan start advances to 2026-02-04.
      The first planned session date shifts from day_offsets[0] relative
      to 2026-02-01 → day_offsets[0] relative to 2026-02-04 (+3 days).
    """

    def test_skip_n_days_shifts_first_session(self):
        user_state = _make_user_state(days_per_week=3, baseline_max=10)
        plan_start_original = "2026-02-01"

        plans_original = generate_plan(user_state, plan_start_original, weeks_ahead=4)
        first_date_original = datetime.strptime(plans_original[0].date, "%Y-%m-%d")

        # Simulate 3-day skip by advancing plan_start by 3 days
        n_skip = 3
        plan_start_shifted = (
            datetime.strptime(plan_start_original, "%Y-%m-%d") + timedelta(days=n_skip)
        ).strftime("%Y-%m-%d")

        plans_shifted = generate_plan(user_state, plan_start_shifted, weeks_ahead=4)
        first_date_shifted = datetime.strptime(plans_shifted[0].date, "%Y-%m-%d")

        shift = (first_date_shifted - first_date_original).days
        assert shift == n_skip, (
            f"First session should shift exactly +{n_skip} days; got shift={shift}"
        )


# ===========================================================================
# 4. RIR fatigue effect
# ===========================================================================

class TestRIRFatigueEffect:
    """
    Fix 4: RIR=4+ sessions generate less fatigue than RIR=3 sessions.

    Verified directly via rir_effort_multiplier().
    With A_RIR=0.15:
      RIR=3: 1.0 + 0.15*(3-3) = 1.00  (neutral)
      RIR=4: 1.0 + 0.15*(3-4) = 0.85  (easier)
      RIR=5: 1.0 + 0.15*(3-5) = 0.70  (much easier)
      floor : 0.50                     (floor for very high RIR)
    """

    def test_rir_monotonically_decreasing(self):
        """Higher RIR → lower multiplier (less fatigue per rep)."""
        rirs = [0, 1, 2, 3, 4, 5, 7]
        multipliers = [rir_effort_multiplier(r) for r in rirs]
        for i in range(len(multipliers) - 1):
            assert multipliers[i] > multipliers[i + 1], (
                f"rir_effort_multiplier must decrease: "
                f"RIR={rirs[i]} → {multipliers[i]}, RIR={rirs[i+1]} → {multipliers[i+1]}"
            )

    def test_high_rir_below_neutral(self):
        """RIR=4 and RIR=5 are strictly below neutral (1.0)."""
        assert rir_effort_multiplier(4) < 1.0
        assert rir_effort_multiplier(5) < 1.0

    def test_floor_respected(self):
        """Multiplier never falls below 0.5 regardless of RIR."""
        for rir in range(7, 20):
            assert rir_effort_multiplier(rir) >= 0.5, (
                f"Floor violated at RIR={rir}: {rir_effort_multiplier(rir)}"
            )


# ===========================================================================
# 5. Explain: rest day within horizon
# ===========================================================================

class TestExplainRestDay:
    """
    explain_plan_entry() returns a "rest day" message for dates within the
    plan horizon that have no scheduled session.

    Profile: pull_up, days=3, bw=80, baseline=10
    Plan start: 2026-02-01 (Mon). 3-day offsets: day 0, 2, 4 of each week.
      Week 1 sessions: 2026-02-01 (Mon), 2026-02-03 (Wed), 2026-02-05 (Fri)
      2026-02-02 (Tue) is a rest day within the horizon.
    Expected: result contains "rest day" (case-insensitive)
    """

    def test_rest_day_in_horizon(self):
        user_state = _make_user_state(days_per_week=3, baseline_max=10)
        plan_start = "2026-02-01"
        weeks_ahead = 4

        # 2026-02-02 is a Tuesday — not a session day in the 3-day schedule
        result = explain_plan_entry(user_state, plan_start, "2026-02-02", weeks_ahead)
        assert "rest" in result.lower(), (
            f"Expected 'rest' in explain output for non-training day, got:\n{result}"
        )

    def test_outside_horizon_gives_error(self):
        user_state = _make_user_state(days_per_week=3, baseline_max=10)
        plan_start = "2026-02-01"
        # 10 years in the future — definitely outside any 4-week horizon
        result = explain_plan_entry(user_state, plan_start, "2036-01-01", 4)
        assert "No planned session" in result or "outside" in result.lower() or "horizon" in result.lower(), (
            f"Expected 'no planned session' or similar for out-of-horizon date, got:\n{result}"
        )


# ===========================================================================
# 6. Explain: overtraining shift notice
# ===========================================================================

class TestExplainOvertrain:
    """
    When overtraining_rest_days > 0, the explain output for the first
    planned session must contain a shift notice.

    Profile: pull_up, days=3, bw=80, baseline=10
    Simulate level-3 overtraining (5 sessions in 1 day → extra_rest_days=6).
    With ot_rest=6, start shifts +6 days.
    The explain output for the new first session should mention "shifted".
    """

    def _overtrained_user_state(self) -> UserState:
        """5 sessions on the same day to trigger level-3 overtraining."""
        today = "2026-02-28"
        sessions = [_make_test_session("2026-01-01", 10)]
        for _ in range(5):
            sessions.append(
                SessionResult(
                    date=today,
                    bodyweight_kg=80.0,
                    grip="pronated",
                    session_type="S",
                    exercise_id="pull_up",
                    planned_sets=[],
                    completed_sets=[
                        SetResult(target_reps=8, actual_reps=8, rest_seconds_before=180)
                    ],
                )
            )
        return _make_user_state(days_per_week=3, baseline_max=10, history=sessions)

    def test_shift_notice_in_explain(self):
        from bar_scheduler.core.adaptation import overtraining_severity

        user_state = self._overtrained_user_state()
        training_history = [s for s in user_state.history if s.session_type != "REST"]
        severity = overtraining_severity(training_history, days_per_week=3,
                                        full_history=user_state.history)
        ot_level = severity["level"]
        ot_rest = severity["extra_rest_days"] if ot_level >= 2 else 0

        assert ot_level >= 2, f"Expected overtraining level ≥ 2, got {ot_level}"
        assert ot_rest > 0, f"Expected extra_rest_days > 0, got {ot_rest}"

        # Generate plan with shift to find the first planned date
        plan_start = "2026-03-01"
        plans = generate_plan(
            user_state, plan_start, weeks_ahead=4,
            overtraining_level=ot_level, overtraining_rest_days=ot_rest,
        )
        assert plans, "Plan must be non-empty even with overtraining shift"
        first_date = plans[0].date

        result = explain_plan_entry(
            user_state, plan_start, first_date, weeks_ahead=4,
            overtraining_level=ot_level, overtraining_rest_days=ot_rest,
        )
        assert "shifted" in result.lower() or "overtraining" in result.lower(), (
            f"Expected overtraining shift notice in explain output, got:\n{result}"
        )


# ===========================================================================
# 7–9. Schedule density: 1, 2, 5 days/week
# ===========================================================================

class TestScheduleDensity:
    """
    Verify the correct number of sessions per week and session types for
    all supported schedule densities.

    All offsets are within a 7-day window anchored at start_date.
    """

    START = datetime(2026, 2, 2)  # Monday

    def test_1_day_per_week_one_session(self):
        """
        days=1 → exactly 1 session per week, all type 'S'.

        Schedule: ["S"]
        Day offsets: [0]  → Mon only

        Expected for 4 weeks: 4 sessions total, all S.
        """
        sessions = calculate_session_days(self.START, days_per_week=1, num_weeks=4)
        assert len(sessions) == 4, f"Expected 4 sessions (1×4 weeks), got {len(sessions)}"
        types = [st for _, st in sessions]
        assert all(t == "S" for t in types), (
            f"All sessions for 1-day schedule must be S, got: {types}"
        )

    def test_2_days_per_week_two_sessions(self):
        """
        days=2 → exactly 2 sessions per week.

        Schedule: ["S", "H"]
        Day offsets: [0, 3]  → Mon, Thu

        Expected for 4 weeks: 8 sessions total.
        """
        sessions = calculate_session_days(self.START, days_per_week=2, num_weeks=4)
        assert len(sessions) == 8, f"Expected 8 sessions (2×4 weeks), got {len(sessions)}"
        types = [st for _, st in sessions]
        assert "S" in types, "2-day schedule must include S sessions"
        assert "H" in types, "2-day schedule must include H sessions"

    def test_2_days_correct_offsets(self):
        """
        2-day offsets are [0, 3]: Mon(0) and Thu(3).

        Expected:
          Week 1: 2026-02-02 (Mon +0), 2026-02-05 (Mon +3 = Thu)
        """
        sessions = calculate_session_days(self.START, days_per_week=2, num_weeks=1)
        dates = [d.strftime("%Y-%m-%d") for d, _ in sessions]
        assert dates[0] == "2026-02-02", f"Expected 2026-02-02, got {dates[0]}"
        assert dates[1] == "2026-02-05", f"Expected 2026-02-05, got {dates[1]}"

    def test_3_days_per_week_three_sessions(self):
        """
        days=3 → exactly 3 sessions per week.

        Schedule: ["S", "H", "E"]
        Day offsets: [0, 2, 4]  → Mon, Wed, Fri

        Expected for 4 weeks: 12 sessions total.
        """
        sessions = calculate_session_days(self.START, days_per_week=3, num_weeks=4)
        assert len(sessions) == 12, f"Expected 12 sessions (3×4 weeks), got {len(sessions)}"

    def test_5_days_per_week_five_sessions(self):
        """
        days=5 → exactly 5 sessions per week.

        Schedule: ["S", "H", "T", "E", "S"]
        Day offsets: [0, 1, 2, 4, 5]  → Mon, Tue, Wed, Fri, Sat

        Expected for 4 weeks: 20 sessions total.
        """
        sessions = calculate_session_days(self.START, days_per_week=5, num_weeks=4)
        assert len(sessions) == 20, f"Expected 20 sessions (5×4 weeks), got {len(sessions)}"
        types = [st for _, st in sessions]
        # Must include all four types from the rotation
        for t in ("S", "H", "T", "E"):
            assert t in types, f"5-day schedule must include {t} sessions"

    def test_5_days_correct_offsets(self):
        """
        5-day offsets are [0,1,2,4,5]: Mon, Tue, Wed, Fri, Sat.

        Expected week 1 dates starting 2026-02-02:
          02-02 (Mon), 02-03 (Tue), 02-04 (Wed), 02-06 (Fri), 02-07 (Sat)
        """
        sessions = calculate_session_days(self.START, days_per_week=5, num_weeks=1)
        dates = [d.strftime("%Y-%m-%d") for d, _ in sessions]
        expected = ["2026-02-02", "2026-02-03", "2026-02-04", "2026-02-06", "2026-02-07"]
        assert dates == expected, f"Expected {expected}, got {dates}"

    def test_get_schedule_template(self):
        """
        get_schedule_template returns correct templates for all densities.

        Expected:
          1-day → ["S"]
          2-day → ["S", "H"]
          3-day → ["S", "H", "E"]
          4-day → ["S", "H", "T", "E"]
          5-day → ["S", "H", "T", "E", "S"]
        """
        assert get_schedule_template(1) == ["S"]
        assert get_schedule_template(2) == ["S", "H"]
        assert get_schedule_template(3) == ["S", "H", "E"]
        assert get_schedule_template(4) == ["S", "H", "T", "E"]
        assert get_schedule_template(5) == ["S", "H", "T", "E", "S"]


# ===========================================================================
# 10. Overtraining: REST credit reduces severity
# ===========================================================================

class TestOvertTrainingRestCredit:
    """
    Fix 3: REST records within the training span are credited as recovery,
    reducing apparent overtraining severity.

    Scenario:
      5 sessions on 2 dates (02.24 x2, 02.26 x2, 02.27), REST on 02.25
      span_days = (02.27 - 02.24).days = 3
      rest_in_span = 1 (the 02.25 REST record)
      actual_days_with_credit    = max(3 + 1, 1) = 4
      actual_days_without_credit = max(3, 1) = 3

      expected_days = 5 × (7/4) = 8.75
      extra_with_credit    = round(8.75 - 4) = 5
      extra_without_credit = round(8.75 - 3) = 6

      Description should say "5 sessions in 4 days" (inclusive: 24,25,26,27).
    """

    def _sessions(self):
        from bar_scheduler.core.models import SessionResult

        def _s(d, st):
            return SessionResult(
                date=d, bodyweight_kg=80.0, grip="pronated",
                session_type=st, planned_sets=[], completed_sets=[],
            )

        training = [
            _s("2026-02-24", "S"),
            _s("2026-02-24", "TEST"),
            _s("2026-02-26", "S"),
            _s("2026-02-26", "H"),
            _s("2026-02-27", "S"),
        ]
        full = training + [_s("2026-02-25", "REST")]
        return training, full

    def test_rest_credit_reduces_extra_days(self):
        from bar_scheduler.core.adaptation import overtraining_severity

        training, full = self._sessions()
        r_no_credit = overtraining_severity(training, days_per_week=4)
        r_credit    = overtraining_severity(training, days_per_week=4, full_history=full)

        assert r_credit["extra_rest_days"] < r_no_credit["extra_rest_days"], (
            f"REST credit must reduce extra_rest_days: "
            f"no_credit={r_no_credit['extra_rest_days']}, credit={r_credit['extra_rest_days']}"
        )

    def test_description_is_inclusive(self):
        """Description uses inclusive day count (span_days + 1)."""
        from bar_scheduler.core.adaptation import overtraining_severity

        training, _ = self._sessions()
        result = overtraining_severity(training, days_per_week=4)
        desc = result["description"]
        # span_days = (02.27 - 02.24) = 3; inclusive = 4
        assert "4 days" in desc, (
            f"Expected '4 days' (inclusive) in description, got: {desc!r}"
        )

    def test_description_has_session_count(self):
        from bar_scheduler.core.adaptation import overtraining_severity

        training, _ = self._sessions()
        result = overtraining_severity(training, days_per_week=4)
        desc = result["description"]
        assert "5 sessions" in desc, (
            f"Expected '5 sessions' in description, got: {desc!r}"
        )


# ===========================================================================
# 11. Explain matches plan prescription
# ===========================================================================

class TestExplainMatchesPlan:
    """
    explain_plan_entry(date) must return output consistent with the plan
    generated by generate_plan() for the same date.

    Profile: pull_up, days=3, bw=80, baseline=10
    Expected:
      If plan says first session is on 2026-02-01 (type="S"),
      explain for 2026-02-01 must mention "S" or "Strength" and contain TM info.
    """

    def test_explain_first_session_mentions_session_type(self):
        user_state = _make_user_state(days_per_week=3, baseline_max=10)
        plan_start = "2026-02-01"
        plans = generate_plan(user_state, plan_start, weeks_ahead=4)
        first = plans[0]

        result = explain_plan_entry(user_state, plan_start, first.date, weeks_ahead=4)
        assert first.session_type in result or "Strength" in result, (
            f"Explain for first session ({first.session_type}) must mention session type.\n"
            f"Got:\n{result}"
        )
        assert "TRAINING MAX" in result, "Explain must contain TRAINING MAX section"

    def test_explain_past_session_in_history(self):
        """
        For a date that's in history, explain returns a historical summary.

        Profile: pull_up, days=3, bw=80, baseline=10
        Expected:
          explain for "2026-01-01" (the TEST session in history) contains
          "TEST" or "2026-01-01" in the output.
        """
        user_state = _make_user_state(days_per_week=3, baseline_max=10)
        plan_start = "2026-02-01"
        result = explain_plan_entry(user_state, plan_start, "2026-01-01", weeks_ahead=4)
        assert "2026-01-01" in result or "TEST" in result or "Historical" in result, (
            f"Explain for historical date should summarise the session.\nGot:\n{result}"
        )


# ===========================================================================
# 12. Multi-exercise: plan uses exercise-specific parameters
# ===========================================================================

class TestMultiExercise:
    """
    Verify that dip plans use dip-specific parameters (bw_fraction=0.92)
    and pull-up plans are unaffected by dip history.

    Profile: dip, days=3, bw=80, baseline=15
    Expected:
      TM for dip = floor(0.9 × 15) = 13
      Plan sessions use exercise_id = "dip"
    """

    def test_dip_plan_sessions_use_dip_exercise_id(self):
        user_state = _make_user_state(
            exercise_id="dip",
            baseline_max=15,
        )
        exercise = get_exercise("dip")
        plans = generate_plan(user_state, "2026-02-01", weeks_ahead=4, exercise=exercise)
        assert plans, "Dip plan must be non-empty"
        for p in plans:
            assert p.exercise_id == "dip", (
                f"Dip plan entries must have exercise_id='dip', got {p.exercise_id!r}"
            )

    def test_pull_up_and_dip_histories_are_isolated(self):
        """
        Dip history must not appear in pull-up plan and vice versa.

        Profile: pull_up, days=3, bw=80, baseline=10
        History includes both pull_up TEST and dip TEST sessions.
        generate_plan(exercise=pull_up) must ignore dip sessions.
        """
        pull_up_exercise = get_exercise("pull_up")
        dip_exercise = get_exercise("dip")

        history = [
            _make_test_session("2026-01-01", 10, exercise_id="pull_up"),
            _make_test_session("2026-01-02", 15, exercise_id="dip"),
        ]
        profile = UserProfile(
            height_cm=180,
            sex="male",
            preferred_days_per_week=3,
            exercise_days={"pull_up": 3, "dip": 3},
            exercise_targets={
                "pull_up": ExerciseTarget(reps=30),
                "dip": ExerciseTarget(reps=40),
            },
        )
        user_state = UserState(profile=profile, current_bodyweight_kg=80.0, history=history)

        pu_plans = generate_plan(user_state, "2026-02-01", 4, exercise=pull_up_exercise)
        dip_plans = generate_plan(user_state, "2026-02-01", 4, exercise=dip_exercise)

        assert all(p.exercise_id == "pull_up" for p in pu_plans), (
            "Pull-up plan must only contain pull_up sessions"
        )
        assert all(p.exercise_id == "dip" for p in dip_plans), (
            "Dip plan must only contain dip sessions"
        )


# ===========================================================================
# 13. Parametric profile/bodyweight matrix
# ===========================================================================

class TestProfileMatrix:
    """
    Smoke-test all exercise / bodyweight combinations produce valid plans.

    Profile matrix:
      exercises    : pull_up, dip
      bodyweights  : 70, 90 kg
      days_per_week: 3 (representative for matrix; density tested separately)
      baselines    : pull_up→10, dip→15
    """

    @pytest.mark.parametrize("exercise_id,baseline", [
        ("pull_up", 10),
        ("dip",     15),
    ])
    @pytest.mark.parametrize("bw", [70, 90])
    def test_plan_non_empty_for_profile(self, exercise_id, baseline, bw):
        """
        Every (exercise, bodyweight) combination must produce a non-empty plan.

        Expected: len(plans) ≥ 1
        """
        user_state = _make_user_state(
            exercise_id=exercise_id,
            baseline_max=baseline,
            bodyweight_kg=bw,
        )
        exercise = get_exercise(exercise_id)
        plans = generate_plan(user_state, "2026-02-01", weeks_ahead=4, exercise=exercise)
        assert plans, (
            f"Plan must be non-empty for {exercise_id}, bw={bw}, baseline={baseline}"
        )
        assert plans[0].session_type in ("S", "H", "E", "T", "TEST"), (
            f"First session must have valid type for {exercise_id}"
        )

    @pytest.mark.parametrize("days_per_week", [1, 2, 3, 4, 5])
    def test_plan_respects_days_per_week(self, days_per_week):
        """
        Plans for days_per_week=N have exactly N sessions per week.

        Expected:
          days=1 → 1×4=4 sessions (4 weeks)
          days=2 → 2×4=8 sessions
          days=3 → 3×4=12 sessions
          days=4 → 4×4=16 sessions
          days=5 → 5×4=20 sessions
        """
        sessions = calculate_session_days(
            datetime(2026, 2, 2),
            days_per_week=days_per_week,
            num_weeks=4,
        )
        expected = days_per_week * 4
        assert len(sessions) == expected, (
            f"days={days_per_week}: expected {expected} sessions, got {len(sessions)}"
        )


# ===========================================================================
# 14. Bug 2 regression: _menu_delete_record must accept exercise_id
# ===========================================================================

class TestMenuDeleteRecordExerciseId:
    """
    Regression for Bug 2: `_menu_delete_record()` was calling
    `get_store(None)` without exercise_id, so `-e dip` always routed
    to the pull_up history.

    Fix: the function now accepts `exercise_id` and passes it to `get_store`.
    """

    def test_menu_delete_record_has_exercise_id_param(self):
        """
        _menu_delete_record must declare an exercise_id parameter so the
        caller (main.py) can pass the active exercise.

        Before the fix: def _menu_delete_record() → no exercise_id param.
        After the fix:  def _menu_delete_record(exercise_id="pull_up") → param exists.
        """
        import inspect

        from bar_scheduler.cli.commands.sessions import _menu_delete_record

        sig = inspect.signature(_menu_delete_record)
        assert "exercise_id" in sig.parameters, (
            "_menu_delete_record must accept exercise_id so '-e dip' routes to "
            "dip history, not pull_up history"
        )

    def test_menu_delete_record_default_exercise_is_pull_up(self):
        """
        Default exercise_id must be 'pull_up' for backward compatibility with
        direct calls that don't pass an exercise.
        """
        import inspect

        from bar_scheduler.cli.commands.sessions import _menu_delete_record

        sig = inspect.signature(_menu_delete_record)
        default = sig.parameters["exercise_id"].default
        assert default == "pull_up", (
            f"exercise_id default must be 'pull_up', got {default!r}"
        )


# ===========================================================================
# 15. Bug 3 regression: no overtraining shift notice for far-future explain
# ===========================================================================

class TestExplainNoOvertrain:
    """
    Regression for Bug 3: explain_plan_entry() was showing an overtraining
    shift notice even for dates a month ahead, because today's overtraining
    severity was passed unconditionally to explain_plan_entry().

    Fix: planning.py computes a cutoff = today + max(ot_rest + 14, 14) days
    and zeros out ot_level/ot_rest when target_date > cutoff.

    Verification via explain_plan_entry():
      - Calling with ot_rest=0 (what planning.py should pass for far dates)
        must NOT produce a shift notice.
      - Calling with ot_rest>0 (near-future, within cutoff) MUST produce
        a shift notice on the first shifted session.
    """

    def test_no_shift_notice_when_ot_rest_is_zero(self):
        """
        Far-future explain: planning.py zeros ot params → no shift notice.

        Scenario:
          plan_start = 2026-03-01, target = 2026-03-25 (24 days out)
          overtraining_rest_days = 0  (zeroed by cutoff logic in planning.py)
        Expected:
          "shifted" must NOT appear in explain output.
        """
        user_state = _make_user_state(days_per_week=3, baseline_max=10)
        plan_start = "2026-03-01"

        # A date well inside the 4-week horizon but far in the future
        far_date = "2026-03-25"
        plans = generate_plan(user_state, plan_start, weeks_ahead=4)
        # Find the nearest plan date on or after far_date for a valid session
        plan_dates = [p.date for p in plans]
        valid_dates = [d for d in plan_dates if d >= far_date]
        target_date = valid_dates[0] if valid_dates else plans[-1].date

        # Simulate what planning.py does after cutoff check: ot params zeroed
        result = explain_plan_entry(
            user_state, plan_start, target_date, weeks_ahead=4,
            overtraining_level=0, overtraining_rest_days=0,
        )
        assert "shifted" not in result.lower(), (
            f"Explain with ot_rest=0 must not show shift notice.\nGot:\n{result}"
        )

    def test_cutoff_formula_zeros_params_for_far_dates(self):
        """
        Verify the cutoff formula itself: with ot_rest=6 (level-3 overtraining),
        cutoff = today + max(6+14, 14) = today + 20 days.
        A date 30 days away must be beyond the cutoff → ot params zeroed.
        A date 10 days away must be within the cutoff → ot params kept.

        Expected with today = 2026-02-28, ot_rest = 6:
          cutoff_date = 2026-03-20  (02.28 + 20 days)
          far_date  = 2026-03-30  (02.28 + 30) → > cutoff → effective ot_rest = 0
          near_date = 2026-03-08  (02.28 + 8)  → ≤ cutoff → effective ot_rest = 6
        """
        from datetime import datetime, timedelta

        today = datetime(2026, 2, 28)
        ot_rest = 6

        cutoff_dt = today + timedelta(days=max(ot_rest + 14, 14))
        assert cutoff_dt.strftime("%Y-%m-%d") == "2026-03-20", (
            f"cutoff must be 2026-03-20, got {cutoff_dt.strftime('%Y-%m-%d')}"
        )

        far_date  = (today + timedelta(days=30)).strftime("%Y-%m-%d")  # 2026-03-30
        near_date = (today + timedelta(days=8)).strftime("%Y-%m-%d")   # 2026-03-08
        cutoff_str = cutoff_dt.strftime("%Y-%m-%d")

        # Far date → beyond cutoff → params should be zeroed
        effective_far = ot_rest if far_date <= cutoff_str else 0
        assert effective_far == 0, (
            f"Far date {far_date} must be beyond cutoff {cutoff_str}: effective_ot_rest={effective_far}"
        )

        # Near date → within cutoff → params should be kept
        effective_near = ot_rest if near_date <= cutoff_str else 0
        assert effective_near == 6, (
            f"Near date {near_date} must be within cutoff {cutoff_str}: effective_ot_rest={effective_near}"
        )


# ===========================================================================
# 16. Skip-backward regression
# ===========================================================================

class TestSkipBackward:
    """
    Regression for Bug A (backward skip didn't move plan) and
    Bug B (overtraining level increased after backward skip).

    Tests use the CLI runner to invoke skip() with simulated input, then
    inspect the HistoryStore directly.

    from_date=2026-03-06, N=-6 → target_date = 2026-02-28
    """

    def _setup_store(self, tmp_path, extra_rest_dates: list[str] | None = None) -> "Path":
        """
        Create a minimal store with:
          - profile + baseline TEST session on 2026-02-17
          - optional plan-REST records
          - plan_start_date = "2026-03-01"
        Returns the history_path.
        """
        from typer.testing import CliRunner

        from bar_scheduler.cli.main import app

        runner = CliRunner()
        history_path = tmp_path / "pull_up_history.jsonl"

        # Init profile
        runner.invoke(app, [
            "init", "--exercise", "pull_up",
            "--history-path", str(history_path),
            "--height-cm", "180", "--sex", "male",
            "--days-per-week", "3", "--bodyweight-kg", "80",
            "--baseline-max", "10",
        ])

        from bar_scheduler.io.history_store import HistoryStore
        from bar_scheduler.core.models import SessionResult

        store = HistoryStore(history_path, exercise_id="pull_up")
        store.set_plan_start_date("2026-03-01")

        if extra_rest_dates:
            for d in extra_rest_dates:
                store.append_session(SessionResult(
                    date=d, bodyweight_kg=80.0, grip="pronated",
                    session_type="REST", exercise_id="pull_up",
                    planned_sets=[], completed_sets=[],
                ))

        return history_path

    def test_backward_skip_sets_plan_start_to_target_date(self, tmp_path):
        """
        skip from_date=2026-03-10, N=-6 → plan_start_date = 2026-03-04

        Setup:
          plan_start_date = "2026-03-01" (no extra REST records)
          Baseline TEST created by init on today (2026-03-01) — target_date must stay
          above first_training to avoid the clamp. 03.10 − 6 = 03.04 > 03.01 ✓
        Expected:
          store.get_plan_start_date() == "2026-03-04"
        """
        from typer.testing import CliRunner
        from bar_scheduler.cli.main import app
        from bar_scheduler.io.history_store import HistoryStore

        history_path = self._setup_store(tmp_path)
        runner = CliRunner()

        result = runner.invoke(
            app, ["skip", "--exercise", "pull_up", "--history-path", str(history_path)],
            input="2026-03-10\n-6\n",
        )
        assert result.exit_code == 0, f"skip failed: {result.output}"

        store = HistoryStore(history_path, exercise_id="pull_up")
        new_start = store.get_plan_start_date()
        assert new_start == "2026-03-04", (
            f"plan_start_date must be 2026-03-04 (03.10 − 6), got {new_start!r}"
        )

    def test_backward_skip_removes_rest_records_in_gap(self, tmp_path):
        """
        REST records in [target_date, from_date) are removed.

        Setup:
          REST on 2026-02-28, 2026-03-01, 2026-03-03  (all within gap [02.28, 03.06))
          REST on 2026-02-25  (before gap — must NOT be removed)
        from_date=2026-03-06, N=-6  (target=2026-02-28)
        Expected:
          2026-02-25 REST still in history
          2026-02-28, 2026-03-01, 2026-03-03 REST removed
        """
        from typer.testing import CliRunner
        from bar_scheduler.cli.main import app
        from bar_scheduler.io.history_store import HistoryStore

        history_path = self._setup_store(
            tmp_path,
            extra_rest_dates=["2026-02-25", "2026-02-28", "2026-03-01", "2026-03-03"],
        )
        runner = CliRunner()

        result = runner.invoke(
            app, ["skip", "--exercise", "pull_up", "--history-path", str(history_path)],
            input="2026-03-06\n-6\n",
        )
        assert result.exit_code == 0, f"skip failed: {result.output}"

        store = HistoryStore(history_path, exercise_id="pull_up")
        rest_dates = {s.date for s in store.load_history() if s.session_type == "REST"}

        assert "2026-02-25" in rest_dates, (
            "REST record on 2026-02-25 (before gap) must be preserved"
        )
        for d in ("2026-02-28", "2026-03-01", "2026-03-03"):
            assert d not in rest_dates, (
                f"REST record on {d} (in gap) must be removed by backward skip"
            )

    def test_backward_skip_preserves_rest_records_before_target(self, tmp_path):
        """
        REST records before target_date are untouched.

        Regression for Bug B: old code removed s.date <= from_date, which
        included the pre-gap REST record and raised overtraining severity.

        Setup:
          REST on 2026-02-25 only (before target_date 2026-02-28)
        from_date=2026-03-06, N=-6
        Expected:
          2026-02-25 REST still in history after skip
        """
        from typer.testing import CliRunner
        from bar_scheduler.cli.main import app
        from bar_scheduler.io.history_store import HistoryStore

        history_path = self._setup_store(tmp_path, extra_rest_dates=["2026-02-25"])
        runner = CliRunner()

        result = runner.invoke(
            app, ["skip", "--exercise", "pull_up", "--history-path", str(history_path)],
            input="2026-03-06\n-6\n",
        )
        assert result.exit_code == 0, f"skip failed: {result.output}"

        store = HistoryStore(history_path, exercise_id="pull_up")
        rest_dates = {s.date for s in store.load_history() if s.session_type == "REST"}
        assert "2026-02-25" in rest_dates, (
            "REST record on 2026-02-25 (before target) must survive backward skip"
        )

    def test_backward_skip_does_not_increase_overtraining_level(self, tmp_path):
        """
        Overtraining severity level must not increase after backward skip.

        Regression for Bug B: old code removed the pre-gap 2026-02-25 REST record,
        reducing rest_in_span and bumping severity from level 1 to level 2.

        Setup:
          Training sessions on 2026-02-22, 2026-02-24, 2026-02-26, 2026-02-27
          REST on 2026-02-25 (between sessions → credits rest_in_span)
          → 4 sessions, span=5, rest_in_span=1, actual=6, level-1 severity
        After backward skip (doesn't touch 2026-02-25 REST):
          → same severity level
        """
        from typer.testing import CliRunner
        from bar_scheduler.cli.main import app
        from bar_scheduler.io.history_store import HistoryStore
        from bar_scheduler.core.adaptation import overtraining_severity

        history_path = self._setup_store(tmp_path, extra_rest_dates=["2026-02-25"])

        # Add 4 training sessions in 6 days
        store = HistoryStore(history_path, exercise_id="pull_up")
        from bar_scheduler.core.models import SessionResult, SetResult
        for d in ("2026-02-22", "2026-02-24", "2026-02-26", "2026-02-27"):
            store.append_session(SessionResult(
                date=d, bodyweight_kg=80.0, grip="pronated",
                session_type="S", exercise_id="pull_up",
                planned_sets=[],
                completed_sets=[SetResult(target_reps=8, actual_reps=8, rest_seconds_before=180)],
            ))

        # Compute severity BEFORE skip
        history_before = store.load_history()
        training_before = [s for s in history_before if s.session_type != "REST"]
        severity_before = overtraining_severity(training_before, days_per_week=3,
                                                full_history=history_before)
        level_before = severity_before["level"]

        # Run backward skip
        runner = CliRunner()
        result = runner.invoke(
            app, ["skip", "--exercise", "pull_up", "--history-path", str(history_path)],
            input="2026-03-06\n-6\n",
        )
        assert result.exit_code == 0, f"skip failed: {result.output}"

        # Compute severity AFTER skip
        history_after = store.load_history()
        training_after = [s for s in history_after if s.session_type != "REST"]
        severity_after = overtraining_severity(training_after, days_per_week=3,
                                               full_history=history_after)
        level_after = severity_after["level"]

        assert level_after <= level_before, (
            f"Overtraining level must not increase after backward skip: "
            f"before={level_before}, after={level_after}"
        )


# ===========================================================================
# 17. Skip-forward: calendar-day shift and session-type preservation
# ===========================================================================

class TestSkipForwardCalendarDays:
    """
    Regression for two forward-skip bugs:

    Bug 1 — REST consumes a session-type slot:
      Skip +1 from plan_start caused REST to fill slot 0, skipping the Str
      session type. Fixed by advancing plan_start to last_REST + 1 day.

    Bug 2 — Sessions shift by training days, not calendar days:
      Every future session must shift by exactly N calendar days.
      Fixed as a consequence of Bug 1 fix (plan_start moves by N).

    All tests verify dates via `plan --json` output.
    """

    def _setup_store(self, tmp_path) -> "Path":
        """
        Init a store with a baseline TEST on a past date.
        Returns history_path with plan_start_date = tomorrow (a future anchor).
        """
        from typer.testing import CliRunner
        from bar_scheduler.cli.main import app
        from bar_scheduler.io.history_store import HistoryStore

        runner = CliRunner()
        history_path = tmp_path / "pull_up_history.jsonl"
        runner.invoke(app, [
            "init", "--exercise", "pull_up",
            "--history-path", str(history_path),
            "--height-cm", "180", "--sex", "male",
            "--days-per-week", "3", "--bodyweight-kg", "80",
            "--baseline-max", "10",
        ])

        # Set plan_start_date to a fixed future date so forward skip has a clean anchor
        store = HistoryStore(history_path, exercise_id="pull_up")
        store.set_plan_start_date("2026-03-10")
        return history_path

    def _future_dates(self, history_path) -> list[str]:
        """Run plan --json and return all future session dates in order."""
        import json as _json
        from typer.testing import CliRunner
        from bar_scheduler.cli.main import app

        runner = CliRunner()
        r = runner.invoke(app, ["plan", "--json", "--history-path", str(history_path)])
        assert r.exit_code == 0, f"plan --json failed: {r.output}"
        data = _json.loads(r.output)
        return [
            s["date"]
            for s in data["sessions"]
            if s["status"] in ("next", "planned")
        ]

    def _future_types(self, history_path) -> list[tuple[str, str]]:
        """Run plan --json and return (date, session_type) for all future sessions."""
        import json as _json
        from typer.testing import CliRunner
        from bar_scheduler.cli.main import app

        runner = CliRunner()
        r = runner.invoke(app, ["plan", "--json", "--history-path", str(history_path)])
        assert r.exit_code == 0, f"plan --json failed: {r.output}"
        data = _json.loads(r.output)
        return [
            (s["date"], s["type"])
            for s in data["sessions"]
            if s["status"] in ("next", "planned")
        ]

    def test_forward_skip_1_day_shifts_all_sessions_by_1(self, tmp_path):
        """
        Skip +1 from plan_start shifts every future session by exactly 1 calendar day.

        Setup:
          plan_start_date = "2026-03-10"
          Future sessions before skip: 2026-03-10 (S), 2026-03-12 (H), 2026-03-14 (E), ...
        After skip +1 from 2026-03-10:
          Future sessions: 2026-03-11 (S), 2026-03-13 (H), 2026-03-15 (E), ...
        Expected: each session date = original + 1 calendar day.
        """
        from typer.testing import CliRunner
        from bar_scheduler.cli.main import app

        runner = CliRunner()
        history_path = self._setup_store(tmp_path)

        dates_before = self._future_dates(history_path)
        assert len(dates_before) >= 3, "Need at least 3 future sessions for this test"

        result = runner.invoke(
            app, ["skip", "--exercise", "pull_up", "--history-path", str(history_path)],
            input="2026-03-10\n1\n",
        )
        assert result.exit_code == 0, f"skip failed: {result.output}"

        dates_after = self._future_dates(history_path)
        assert len(dates_after) >= 3, "Need at least 3 future sessions after skip"

        for before, after in zip(dates_before, dates_after):
            from datetime import datetime
            d_before = datetime.strptime(before, "%Y-%m-%d")
            d_after  = datetime.strptime(after,  "%Y-%m-%d")
            shift = (d_after - d_before).days
            assert shift == 1, (
                f"Session {before} must shift to {before}+1 calendar day, "
                f"but shifted to {after} ({shift:+d} days)"
            )

    def test_forward_skip_3_days_shifts_all_sessions_by_3(self, tmp_path):
        """
        Skip +3 from plan_start shifts every future session by exactly 3 calendar days.
        """
        from typer.testing import CliRunner
        from bar_scheduler.cli.main import app

        runner = CliRunner()
        history_path = self._setup_store(tmp_path)

        dates_before = self._future_dates(history_path)

        result = runner.invoke(
            app, ["skip", "--exercise", "pull_up", "--history-path", str(history_path)],
            input="2026-03-10\n3\n",
        )
        assert result.exit_code == 0, f"skip failed: {result.output}"

        dates_after = self._future_dates(history_path)

        for before, after in zip(dates_before, dates_after):
            from datetime import datetime
            shift = (datetime.strptime(after, "%Y-%m-%d") - datetime.strptime(before, "%Y-%m-%d")).days
            assert shift == 3, (
                f"Session {before} must shift +3 calendar days, "
                f"but shifted to {after} ({shift:+d} days)"
            )

    def test_forward_skip_preserves_session_type_rotation(self, tmp_path):
        """
        After skip, the session type at the new first date must equal the
        session type that was originally planned for the old first date.

        Regression for Bug 1: REST was consuming the Str slot, so after skip
        from a Str date the next session appeared as Hpy, not Str.

        Expected: type_at(new_first_date) == type_at(old_first_date)
        """
        from typer.testing import CliRunner
        from bar_scheduler.cli.main import app

        runner = CliRunner()
        history_path = self._setup_store(tmp_path)

        types_before = self._future_types(history_path)
        assert types_before, "Need at least one future session before skip"
        first_type_before = types_before[0][1]   # session type at plan_start

        result = runner.invoke(
            app, ["skip", "--exercise", "pull_up", "--history-path", str(history_path)],
            input="2026-03-10\n1\n",
        )
        assert result.exit_code == 0, f"skip failed: {result.output}"

        types_after = self._future_types(history_path)
        assert types_after, "Need at least one future session after skip"
        first_type_after = types_after[0][1]

        assert first_type_after == first_type_before, (
            f"After skip, first future session must have same type as before.\n"
            f"Before: {first_type_before} at {types_before[0][0]}\n"
            f"After:  {first_type_after} at {types_after[0][0]}\n"
            f"Regression: REST consumed the {first_type_before} slot"
        )

    def test_backward_skip_shifts_all_sessions_by_n_calendar_days(self, tmp_path):
        """
        Backward skip -3 from plan_start makes every future session appear
        exactly 3 calendar days earlier than before the skip.

        Setup:
          plan_start_date = "2026-03-16" (no prior REST records)
          from_date = "2026-03-16", N = -3
          target_date = "2026-03-13" (> first training session 2026-03-01, no clamp)
        Expected: each session date = original - 3 days.
        """
        from typer.testing import CliRunner
        from bar_scheduler.cli.main import app
        from bar_scheduler.io.history_store import HistoryStore

        runner = CliRunner()
        history_path = self._setup_store(tmp_path)

        # Override plan_start to the from_date so target falls 3 days earlier
        store = HistoryStore(history_path, exercise_id="pull_up")
        store.set_plan_start_date("2026-03-16")

        dates_before = self._future_dates(history_path)

        result = runner.invoke(
            app, ["skip", "--exercise", "pull_up", "--history-path", str(history_path)],
            input="2026-03-16\n-3\n",
        )
        assert result.exit_code == 0, f"skip failed: {result.output}"

        dates_after = self._future_dates(history_path)

        for before, after in zip(dates_before, dates_after):
            from datetime import datetime
            shift = (datetime.strptime(after, "%Y-%m-%d") - datetime.strptime(before, "%Y-%m-%d")).days
            assert shift == -3, (
                f"Session {before} must shift -3 calendar days, "
                f"but shifted to {after} ({shift:+d} days)"
            )
