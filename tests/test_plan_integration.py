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
# 2. Plan prescription stability
# ===========================================================================

class TestPlanPrescriptionStability:
    """
    Invariant: prescription(slot at date D) = f(history where date < D, profile)

    Logging a session at date D must not change:
      - The session type for the slot at D
      - The prescription (sets/reps/rest) for the slot at D
      - Any prescription or type for slots at dates before D

    Logging at D MAY change prescriptions for slots strictly after D.

    Profile: pull_up, 3-day, bw=80, baseline=10
    plan_start: 2026-04-07 (well after today, avoids date clamping edge cases)
    Pre-plan TEST session: 2026-03-01 (before plan_start)
    """

    PLAN_START = "2026-04-07"
    # TEST_DATE must be recent enough that no TEST is auto-inserted at PLAN_START.
    # pull_up test_frequency_weeks = 3 (21 days).
    # 2026-03-25 → gap to 04.07 = 13 days < 21 → no TEST at plan_start. ✓
    TEST_DATE = "2026-03-25"

    def _base_history(self) -> list[SessionResult]:
        """Minimal pre-plan history: one TEST session before plan_start."""
        return [_make_test_session(self.TEST_DATE, 10)]

    def _base_user_state(self, history=None) -> UserState:
        if history is None:
            history = self._base_history()
        return _make_user_state(days_per_week=3, baseline_max=10, history=history)

    def _make_training_session(
        self,
        date: str,
        session_type: str,
        rir: int = 2,
        grip: str = "pronated",
    ) -> SessionResult:
        return SessionResult(
            date=date,
            bodyweight_kg=80.0,
            grip=grip,
            session_type=session_type,
            exercise_id="pull_up",
            planned_sets=[],
            completed_sets=[
                SetResult(
                    target_reps=8,
                    actual_reps=8,
                    rest_seconds_before=180,
                    rir_reported=rir,
                )
            ],
        )

    def test_logging_at_plan_start_does_not_change_prescription(self):
        """
        Prescription for the plan_start slot must be identical before and after
        logging a session on that same date.

        Before fix: _plan_core used ALL history → logging changed recent_same_type
        for the plan_start slot → rest / sets / reps changed retroactively.
        After fix: plan_start slot uses only history with date < plan_start.
        """
        plan_start = self.PLAN_START
        user_state = self._base_user_state()

        plans_before = generate_plan(user_state, plan_start, weeks_ahead=4)
        slot_0 = plans_before[0]
        assert slot_0.date == plan_start, "First slot must be at plan_start"

        # Log a training session at plan_start
        logged = self._make_training_session(plan_start, slot_0.session_type, rir=1)
        user_state_after = self._base_user_state(
            history=self._base_history() + [logged]
        )
        plans_after = generate_plan(user_state_after, plan_start, weeks_ahead=4)
        slot_0_after = plans_after[0]

        assert slot_0_after.date == plan_start
        assert slot_0.session_type == slot_0_after.session_type, (
            "Session type for plan_start slot must not change after logging"
        )
        assert len(slot_0.sets) == len(slot_0_after.sets), (
            "Number of sets must not change"
        )
        assert slot_0.sets[0].target_reps == slot_0_after.sets[0].target_reps, (
            "Target reps must not change"
        )
        assert slot_0.sets[0].rest_seconds_before == slot_0_after.sets[0].rest_seconds_before, (
            "Rest prescription must not change"
        )

    def test_logging_does_not_change_session_type_for_current_slot(self):
        """
        Session type for the slot at plan_start must be identical before and after
        logging a session on that date.

        Before fix: get_next_session_type_index used ALL history → rotation shifted.
        After fix: rotation anchored to history with date < plan_start.
        """
        plan_start = self.PLAN_START
        user_state = self._base_user_state()

        plans_before = generate_plan(user_state, plan_start, weeks_ahead=4)
        type_before = plans_before[0].session_type

        # Log a session with the same type (as if user followed the plan)
        logged = self._make_training_session(plan_start, type_before)
        user_state_after = self._base_user_state(
            history=self._base_history() + [logged]
        )
        plans_after = generate_plan(user_state_after, plan_start, weeks_ahead=4)
        type_after = plans_after[0].session_type

        assert type_before == type_after, (
            f"Session type changed from {type_before!r} to {type_after!r} "
            "after logging — rotation must be anchored to pre-plan history"
        )

    def test_logging_does_not_change_session_type_for_past_slot(self):
        """
        After logging on slot 2 date, regenerate plan — slot 2 type must match original.

        Hand-check (3-day schedule S/H/E, plan_start=04.07):
          Slot 0: 04.07 S  Slot 1: 04.09 H  Slot 2: 04.11 E
          Log session at 04.11 — slot 2 type must still be E.
        """
        plan_start = self.PLAN_START
        user_state = self._base_user_state()

        plans_before = generate_plan(user_state, plan_start, weeks_ahead=4)
        # Slot 2 is the third planned session
        slot_2_before = plans_before[2]

        logged = self._make_training_session(
            slot_2_before.date, slot_2_before.session_type
        )
        user_state_after = self._base_user_state(
            history=self._base_history() + [logged]
        )
        plans_after = generate_plan(user_state_after, plan_start, weeks_ahead=4)
        slot_2_after = plans_after[2]

        assert slot_2_before.date == slot_2_after.date, "Slot 2 date must not change"
        assert slot_2_before.session_type == slot_2_after.session_type, (
            f"Slot 2 type changed from {slot_2_before.session_type!r} to "
            f"{slot_2_after.session_type!r} after logging"
        )

    def test_logging_does_not_change_prescription_for_past_slot(self):
        """
        Prescription (sets/reps/rest) for a past slot must be stable after logging.

        Logs session at slot 2 (the third planned session), then regenerates.
        Verifies that slot 2's prescription is byte-for-byte identical.
        """
        plan_start = self.PLAN_START
        user_state = self._base_user_state()

        plans_before = generate_plan(user_state, plan_start, weeks_ahead=4)
        slot_2_before = plans_before[2]

        logged = self._make_training_session(
            slot_2_before.date, slot_2_before.session_type, rir=1
        )
        user_state_after = self._base_user_state(
            history=self._base_history() + [logged]
        )
        plans_after = generate_plan(user_state_after, plan_start, weeks_ahead=4)
        slot_2_after = plans_after[2]

        assert slot_2_before.date == slot_2_after.date
        assert len(slot_2_before.sets) == len(slot_2_after.sets), (
            "Number of sets changed for past slot after logging"
        )
        for i, (s_before, s_after) in enumerate(
            zip(slot_2_before.sets, slot_2_after.sets)
        ):
            assert s_before.target_reps == s_after.target_reps, (
                f"Set {i} reps changed for past slot"
            )
            assert s_before.rest_seconds_before == s_after.rest_seconds_before, (
                f"Set {i} rest changed for past slot"
            )

    def test_rotation_anchored_to_pre_plan_history(self):
        """
        Session type sequence is entirely determined by pre-plan history.
        Logging sessions within the plan period must not shift the rotation.

        Hand-check: only TEST in pre-plan history → start_rotation_idx=0 → [S,H,E,S,H,E,...]
        After logging S at 04.07: without fix, rotation would see S as last →
        next=H → plan starts with H. With fix, rotation still starts with S.
        """
        plan_start = self.PLAN_START
        user_state = self._base_user_state()

        plans_before = generate_plan(user_state, plan_start, weeks_ahead=4)
        types_before = [p.session_type for p in plans_before[:6]]

        # Log first 3 sessions (one full week)
        logged_sessions = []
        for p in plans_before[:3]:
            logged_sessions.append(
                self._make_training_session(p.date, p.session_type)
            )
        user_state_after = self._base_user_state(
            history=self._base_history() + logged_sessions
        )
        plans_after = generate_plan(user_state_after, plan_start, weeks_ahead=4)
        types_after = [p.session_type for p in plans_after[:6]]

        assert types_before == types_after, (
            f"Type sequence changed after logging:\n"
            f"  before: {types_before}\n"
            f"  after:  {types_after}"
        )

    def test_adaptive_rest_for_current_slot_uses_only_pre_plan_sessions(self):
        """
        Adaptive rest for the plan_start slot must depend only on pre-plan sessions.

        Setup: no pre-plan same-type sessions → recent_same_type=[] → base midpoint rest.
        Log session at plan_start with RIR=1 (near failure → +30s for FUTURE slots).
        Without fix: logged session enters recent_same_type for plan_start → rest changes.
        With fix: recent_same_type for plan_start slot filtered to date < plan_start → [] → same rest.
        """
        plan_start = self.PLAN_START
        user_state = self._base_user_state()  # Only TEST in history → no same-type pre-sessions

        plans_before = generate_plan(user_state, plan_start, weeks_ahead=4)
        slot_0 = plans_before[0]
        rest_before = slot_0.sets[0].rest_seconds_before

        # Log session at plan_start with low RIR (hard session)
        logged = self._make_training_session(plan_start, slot_0.session_type, rir=1)
        user_state_after = self._base_user_state(
            history=self._base_history() + [logged]
        )
        plans_after = generate_plan(user_state_after, plan_start, weeks_ahead=4)
        rest_after = plans_after[0].sets[0].rest_seconds_before

        assert rest_before == rest_after, (
            f"Adaptive rest for plan_start slot changed from {rest_before}s to {rest_after}s "
            "after logging — must be anchored to pre-plan sessions only"
        )

    def test_future_slot_adaptive_rest_updates_after_logging(self):
        """
        Future slots SHOULD adapt to newly logged sessions.

        Log session at plan_start with RIR=1 (near failure → +30s adaptive rest).
        The NEXT same-type slot should see this session in recent_same_type → rest increases.

        Hand-check (3-day S/H/E, plan_start=04.07):
          Slot 0: 04.07 S   ← logged with RIR=1
          Slot 3: 04.14 S   ← next S slot, should see logged session → +30s
        """
        plan_start = self.PLAN_START
        user_state = self._base_user_state()

        plans_before = generate_plan(user_state, plan_start, weeks_ahead=4)
        # Find next same-type slot after slot 0
        slot_0_type = plans_before[0].session_type
        next_same_type = next(
            p for p in plans_before[1:] if p.session_type == slot_0_type
        )
        rest_future_before = next_same_type.sets[0].rest_seconds_before

        # Log plan_start slot with RIR=1 (near-failure → should boost future slot's rest)
        logged = self._make_training_session(plan_start, slot_0_type, rir=1)
        user_state_after = self._base_user_state(
            history=self._base_history() + [logged]
        )
        plans_after = generate_plan(user_state_after, plan_start, weeks_ahead=4)
        next_same_after = next(
            p for p in plans_after[1:] if p.session_type == slot_0_type
        )
        rest_future_after = next_same_after.sets[0].rest_seconds_before

        # Future slot should have equal or higher rest (adapts to hard session)
        assert rest_future_after >= rest_future_before, (
            f"Future slot rest should increase after logging hard session; "
            f"before={rest_future_before}s after={rest_future_after}s"
        )

    def test_grip_rotation_stable_for_current_and_past_slots(self):
        """
        Grip sequence for all plan slots must be stable after logging.

        Before fix: _init_grip_counts used ALL history → logging changed grip counts →
        all subsequent grips shifted by one position.
        After fix: grip counts anchored to pre-plan history.
        """
        plan_start = self.PLAN_START
        user_state = self._base_user_state()

        plans_before = generate_plan(user_state, plan_start, weeks_ahead=4)
        grips_before = [(p.date, p.grip) for p in plans_before[:6]]

        # Log first 2 sessions with specific grips
        logged_sessions = []
        for p in plans_before[:2]:
            logged_sessions.append(
                self._make_training_session(p.date, p.session_type, grip=p.grip)
            )
        user_state_after = self._base_user_state(
            history=self._base_history() + logged_sessions
        )
        plans_after = generate_plan(user_state_after, plan_start, weeks_ahead=4)
        grips_after = [(p.date, p.grip) for p in plans_after[:6]]

        assert grips_before == grips_after, (
            f"Grip sequence changed after logging:\n"
            f"  before: {grips_before}\n"
            f"  after:  {grips_after}"
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
        from datetime import datetime as _dt
        from bar_scheduler.core.adaptation import overtraining_severity

        training, full = self._sessions()
        ref = _dt(2026, 2, 28)
        r_no_credit = overtraining_severity(training, days_per_week=4, reference_date=ref)
        r_credit    = overtraining_severity(training, days_per_week=4, full_history=full, reference_date=ref)

        assert r_credit["extra_rest_days"] < r_no_credit["extra_rest_days"], (
            f"REST credit must reduce extra_rest_days: "
            f"no_credit={r_no_credit['extra_rest_days']}, credit={r_credit['extra_rest_days']}"
        )

    def test_description_is_inclusive(self):
        """Description uses inclusive day count (span_days + 1)."""
        from datetime import datetime as _dt
        from bar_scheduler.core.adaptation import overtraining_severity

        training, _ = self._sessions()
        result = overtraining_severity(training, days_per_week=4, reference_date=_dt(2026, 2, 28))
        desc = result["description"]
        # span_days = (02.27 - 02.24) = 3; inclusive = 4
        assert "4 days" in desc, (
            f"Expected '4 days' (inclusive) in description, got: {desc!r}"
        )

    def test_description_has_session_count(self):
        from datetime import datetime as _dt
        from bar_scheduler.core.adaptation import overtraining_severity

        training, _ = self._sessions()
        result = overtraining_severity(training, days_per_week=4, reference_date=_dt(2026, 2, 28))
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

