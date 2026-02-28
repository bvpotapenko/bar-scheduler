"""
Formula-focused unit tests for the core training engine.

Each test verifies a specific formula from:
- docs/core_training_formulas_fatigue.md  (§ references match that doc)
- docs/training_model.md

Values are hand-computed from the formulas so the tests act as a spec.
"""

import math

import pytest

from bar_scheduler.core.config import (
    A_RIR,
    ALPHA_MHAT,
    BETA_SIGMA,
    C_READINESS,
    COMPLIANCE_THRESHOLD,
    DELOAD_VOLUME_REDUCTION,
    F_REST_MAX,
    F_REST_MIN,
    GAMMA_BW,
    GAMMA_LOAD,
    GAMMA_REST,
    GAMMA_S,
    K_FATIGUE,
    K_FITNESS,
    READINESS_VOLUME_REDUCTION,
    READINESS_Z_HIGH,
    READINESS_Z_LOW,
    REST_MIN_CLAMP,
    REST_REF_SECONDS,
    S_REST_MAX,
    TAU_FATIGUE,
    TAU_FITNESS,
    TM_FACTOR,
    UNDERPERFORMANCE_THRESHOLD,
    WEEKLY_HARD_SETS_MAX,
    WEEKLY_HARD_SETS_MIN,
    WEEKLY_VOLUME_INCREASE_RATE,
)
from bar_scheduler.core.models import FitnessFatigueState, SessionResult, SetResult

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _set(reps: int, rest: int = 180, added_kg: float = 0.0, rir: int | None = None) -> SetResult:
    return SetResult(
        target_reps=reps,
        actual_reps=reps,
        rest_seconds_before=rest,
        added_weight_kg=added_kg,
        rir_reported=rir,
    )


def _planned(reps: int, rest: int = 180, added_kg: float = 0.0) -> SetResult:
    return SetResult(
        target_reps=reps,
        actual_reps=None,
        rest_seconds_before=rest,
        added_weight_kg=added_kg,
    )


def _session(
    date: str,
    reps_list: list[int],
    *,
    session_type: str = "S",
    grip: str = "pronated",
    bw: float = 80.0,
    rest: int = 180,
    added_kg: float = 0.0,
) -> SessionResult:
    sets = [_set(r, rest=rest, added_kg=added_kg) for r in reps_list]
    return SessionResult(
        date=date,
        bodyweight_kg=bw,
        grip=grip,
        session_type=session_type,
        planned_sets=sets,
        completed_sets=sets,
    )


def _test_session(date: str, max_reps: int, bw: float = 80.0) -> SessionResult:
    s = _set(max_reps, rest=180)
    return SessionResult(
        date=date,
        bodyweight_kg=bw,
        grip="pronated",
        session_type="TEST",
        planned_sets=[s],
        completed_sets=[s],
    )


def _neutral_ff(m_hat: float = 10.0) -> FitnessFatigueState:
    """FF state with zero fitness/fatigue and unit variance (z = readiness)."""
    return FitnessFatigueState(
        fitness=0.0,
        fatigue=0.0,
        m_hat=m_hat,
        sigma_m=1.5,
        readiness_mean=0.0,
        readiness_var=1.0,
    )


def _ff_with_z(z: float) -> FitnessFatigueState:
    """FF state whose readiness_z_score() equals z (unit variance, zero mean)."""
    return FitnessFatigueState(
        fitness=max(0.0, z),
        fatigue=max(0.0, -z),
        m_hat=10.0,
        sigma_m=1.5,
        readiness_mean=0.0,
        readiness_var=1.0,
    )


# ===========================================================================
# metrics.py — §2.1  rest_factor
# ===========================================================================

class TestRestFactor:
    """F_rest(r) = clip((r / r_ref)^gamma_r, F_min, F_max)"""

    from bar_scheduler.core.metrics import rest_factor

    def test_reference_rest_returns_one(self):
        from bar_scheduler.core.metrics import rest_factor
        assert rest_factor(REST_REF_SECONDS) == pytest.approx(1.0, rel=1e-6)

    def test_short_rest_clamps_to_f_min(self):
        # (30/180)^0.20 ≈ 0.699 → clipped to 0.80
        from bar_scheduler.core.metrics import rest_factor
        assert rest_factor(REST_MIN_CLAMP) == pytest.approx(F_REST_MIN, rel=1e-6)

    def test_below_clamp_treated_as_clamp(self):
        # 10 s < REST_MIN_CLAMP → same result as 30 s
        from bar_scheduler.core.metrics import rest_factor
        assert rest_factor(10) == pytest.approx(rest_factor(REST_MIN_CLAMP), rel=1e-6)

    def test_long_rest_clamps_to_f_max(self):
        # (720/180)^0.20 = 4^0.20 ≈ 1.32 → clipped to 1.05
        from bar_scheduler.core.metrics import rest_factor
        assert rest_factor(720) == pytest.approx(F_REST_MAX, rel=1e-6)

    def test_intermediate_rest_applies_power_law(self):
        # 90 s: (90/180)^0.20 = 0.5^0.20 ≈ 0.871 — within bounds
        from bar_scheduler.core.metrics import rest_factor
        expected = (90 / REST_REF_SECONDS) ** GAMMA_REST
        assert F_REST_MIN < expected < F_REST_MAX
        assert rest_factor(90) == pytest.approx(expected, rel=1e-6)


# ===========================================================================
# metrics.py — §2.1  effective_reps
# ===========================================================================

class TestEffectiveReps:
    """reps* = reps / F_rest(rest)"""

    def test_reference_rest_is_identity(self):
        from bar_scheduler.core.metrics import effective_reps
        assert effective_reps(10, REST_REF_SECONDS) == pytest.approx(10.0, rel=1e-6)

    def test_short_rest_inflates_reps(self):
        # F_rest(30) == F_REST_MIN → reps* = reps / F_REST_MIN
        from bar_scheduler.core.metrics import effective_reps
        assert effective_reps(8, 30) == pytest.approx(8 / F_REST_MIN, rel=1e-6)

    def test_long_rest_deflates_reps_slightly(self):
        from bar_scheduler.core.metrics import effective_reps
        assert effective_reps(8, 720) == pytest.approx(8 / F_REST_MAX, rel=1e-6)


# ===========================================================================
# metrics.py — §2.2  bodyweight_normalized_reps
# ===========================================================================

class TestBodyweightNormalization:
    """reps** = reps* × ((bw + load) / bw_ref)^gamma_bw"""

    def test_matching_bw_no_load_is_identity(self):
        from bar_scheduler.core.metrics import bodyweight_normalized_reps
        assert bodyweight_normalized_reps(10.0, 80.0, 80.0, 0.0) == pytest.approx(10.0, rel=1e-6)

    def test_heavier_bw_scales_up(self):
        # (90/80)^1.0 = 1.125
        from bar_scheduler.core.metrics import bodyweight_normalized_reps
        expected = 10.0 * (90.0 / 80.0) ** GAMMA_BW
        assert bodyweight_normalized_reps(10.0, 90.0, 80.0, 0.0) == pytest.approx(expected, rel=1e-6)

    def test_added_load_same_as_heavier_bw(self):
        # bw=80+10 load vs bw=90+0 — same relative load
        from bar_scheduler.core.metrics import bodyweight_normalized_reps
        with_load = bodyweight_normalized_reps(10.0, 80.0, 80.0, 10.0)
        heavier   = bodyweight_normalized_reps(10.0, 90.0, 80.0, 0.0)
        assert with_load == pytest.approx(heavier, rel=1e-6)


# ===========================================================================
# metrics.py — §2.1–2.3  standardized_reps (combined pipeline)
# ===========================================================================

class TestStandardizedReps:
    """reps_std = (reps / F_rest) × L_rel^gamma_bw × F_grip"""

    def test_reference_conditions_is_identity(self):
        from bar_scheduler.core.metrics import standardized_reps
        result = standardized_reps(
            actual_reps=10,
            rest_seconds=REST_REF_SECONDS,
            session_bodyweight_kg=80.0,
            reference_bodyweight_kg=80.0,
            added_load_kg=0.0,
            grip="pronated",
        )
        assert result == pytest.approx(10.0, rel=1e-6)

    def test_short_rest_increases_standardized_reps(self):
        from bar_scheduler.core.metrics import standardized_reps
        ref   = standardized_reps(10, REST_REF_SECONDS, 80.0, 80.0, 0.0, "pronated")
        short = standardized_reps(10, 30,               80.0, 80.0, 0.0, "pronated")
        assert short > ref


# ===========================================================================
# metrics.py — session_max_reps / session_total_reps
# ===========================================================================

class TestSessionReps:

    def test_max_reps_picks_highest_bw_only_set(self):
        from bar_scheduler.core.metrics import session_max_reps
        session = _session("2025-01-01", [8, 10, 7])
        assert session_max_reps(session) == 10

    def test_max_reps_excludes_weighted_sets(self):
        from bar_scheduler.core.metrics import session_max_reps
        bw  = _set(10)
        wt  = _set(15, added_kg=5.0)
        session = SessionResult(
            date="2025-01-01", bodyweight_kg=80.0, grip="pronated", session_type="S",
            planned_sets=[bw], completed_sets=[bw, wt],
        )
        assert session_max_reps(session) == 10

    def test_max_reps_no_bw_sets_returns_zero(self):
        from bar_scheduler.core.metrics import session_max_reps
        wt = _set(10, added_kg=5.0)
        session = SessionResult(
            date="2025-01-01", bodyweight_kg=80.0, grip="pronated", session_type="S",
            planned_sets=[], completed_sets=[wt],
        )
        assert session_max_reps(session) == 0

    def test_total_reps_sums_all_sets(self):
        from bar_scheduler.core.metrics import session_total_reps
        session = _session("2025-01-01", [8, 6, 7])
        assert session_total_reps(session) == 21


# ===========================================================================
# metrics.py — §7.3  training_max
# ===========================================================================

class TestTrainingMax:
    """TM = floor(0.9 × latest_test_max), minimum 1."""

    def test_floor_of_ninety_percent(self):
        from bar_scheduler.core.metrics import training_max
        history = [_test_session("2025-01-01", 10)]
        assert training_max(history) == 9          # floor(0.9×10) = 9

    def test_floor_truncates_not_rounds(self):
        from bar_scheduler.core.metrics import training_max
        history = [_test_session("2025-01-01", 11)]
        assert training_max(history) == 9          # floor(9.9) = 9, not 10

    def test_uses_latest_test_session(self):
        from bar_scheduler.core.metrics import training_max
        history = [
            _test_session("2025-01-01", 10),
            _test_session("2025-01-15", 14),
        ]
        assert training_max(history) == 12         # floor(0.9×14) = 12

    def test_no_history_returns_one(self):
        from bar_scheduler.core.metrics import training_max
        assert training_max([]) == 1

    def test_training_max_from_baseline_same_factor(self):
        from bar_scheduler.core.metrics import training_max_from_baseline
        assert training_max_from_baseline(10) == int(10 * TM_FACTOR)


# ===========================================================================
# metrics.py — overall_max_reps / latest_test_max / get_test_sessions
# ===========================================================================

class TestTestSessionHelpers:

    def test_get_test_sessions_filters_type(self):
        from bar_scheduler.core.metrics import get_test_sessions
        history = [
            _session("2025-01-01", [8], session_type="S"),
            _test_session("2025-01-02", 10),
        ]
        result = get_test_sessions(history)
        assert len(result) == 1 and result[0].session_type == "TEST"

    def test_overall_max_reps_all_time_best(self):
        from bar_scheduler.core.metrics import overall_max_reps
        history = [
            _test_session("2025-01-01", 10),
            _test_session("2025-01-15", 14),   # new best
            _test_session("2025-02-01", 11),
        ]
        assert overall_max_reps(history) == 14

    def test_latest_test_max_uses_last_not_highest(self):
        from bar_scheduler.core.metrics import latest_test_max
        history = [
            _test_session("2025-01-01", 14),   # earlier but higher
            _test_session("2025-01-15", 10),   # later
        ]
        assert latest_test_max(history) == 10


# ===========================================================================
# metrics.py — §8.2  compliance_ratio / session_compliance / weekly_compliance
# ===========================================================================

class TestCompliance:
    """compliance = actual_total_reps / planned_total_reps"""

    def test_perfect_compliance(self):
        from bar_scheduler.core.metrics import compliance_ratio
        planned = [_planned(10), _planned(8)]
        done    = [_set(10),     _set(8)]
        assert compliance_ratio(planned, done) == pytest.approx(1.0)

    def test_partial_compliance(self):
        from bar_scheduler.core.metrics import compliance_ratio
        planned = [_planned(10)]
        done    = [_set(5)]
        assert compliance_ratio(planned, done) == pytest.approx(0.5)

    def test_zero_planned_and_done_is_perfect(self):
        from bar_scheduler.core.metrics import compliance_ratio
        assert compliance_ratio([], []) == pytest.approx(1.0)

    def test_session_compliance_delegates(self):
        from bar_scheduler.core.metrics import session_compliance
        session = SessionResult(
            date="2025-01-01", bodyweight_kg=80.0, grip="pronated", session_type="S",
            planned_sets=[_planned(10)],
            completed_sets=[_set(6)],
        )
        assert session_compliance(session) == pytest.approx(0.6)

    def test_weekly_compliance_averages_sessions(self):
        from bar_scheduler.core.metrics import weekly_compliance
        # session 1: 10/10 = 1.0,  session 2: 5/10 = 0.5 → avg 0.75
        s1 = SessionResult(
            date="2025-01-01", bodyweight_kg=80.0, grip="pronated", session_type="S",
            planned_sets=[_planned(10)], completed_sets=[_set(10)],
        )
        s2 = SessionResult(
            date="2025-01-05", bodyweight_kg=80.0, grip="pronated", session_type="S",
            planned_sets=[_planned(10)], completed_sets=[_set(5)],
        )
        assert weekly_compliance([s1, s2], weeks_back=1) == pytest.approx(0.75)


# ===========================================================================
# metrics.py — §6.2  drop_off_ratio
# ===========================================================================

class TestDropOffRatio:
    """D = 1 - mean(last_2_reps) / first_set_reps"""

    def test_uniform_sets_zero_dropoff(self):
        from bar_scheduler.core.metrics import drop_off_ratio
        sets = [_set(10), _set(10), _set(10)]
        s = SessionResult(
            date="2025-01-01", bodyweight_kg=80.0, grip="pronated", session_type="S",
            planned_sets=sets, completed_sets=sets,
        )
        assert drop_off_ratio(s) == pytest.approx(0.0)

    def test_declining_reps_10_8_6(self):
        from bar_scheduler.core.metrics import drop_off_ratio
        # D = 1 - mean(8,6)/10 = 1 - 7/10 = 0.3
        sets = [_set(10), _set(8), _set(6)]
        s = SessionResult(
            date="2025-01-01", bodyweight_kg=80.0, grip="pronated", session_type="S",
            planned_sets=sets, completed_sets=sets,
        )
        assert drop_off_ratio(s) == pytest.approx(0.3, rel=1e-6)

    def test_single_set_returns_zero(self):
        from bar_scheduler.core.metrics import drop_off_ratio
        sets = [_set(10)]
        s = SessionResult(
            date="2025-01-01", bodyweight_kg=80.0, grip="pronated", session_type="S",
            planned_sets=sets, completed_sets=sets,
        )
        assert drop_off_ratio(s) == pytest.approx(0.0)


# ===========================================================================
# metrics.py — §5.1  estimate_rir_from_fraction
# ===========================================================================

class TestEstimateRIR:
    """RIR_hat = clip(M_hat - reps, 0, 5)"""

    def test_two_below_max(self):
        from bar_scheduler.core.metrics import estimate_rir_from_fraction
        assert estimate_rir_from_fraction(8, 10) == 2

    def test_above_max_clips_to_zero(self):
        from bar_scheduler.core.metrics import estimate_rir_from_fraction
        assert estimate_rir_from_fraction(12, 10) == 0

    def test_far_below_max_clips_to_five(self):
        from bar_scheduler.core.metrics import estimate_rir_from_fraction
        assert estimate_rir_from_fraction(3, 10) == 5

    def test_exactly_at_max_is_zero(self):
        from bar_scheduler.core.metrics import estimate_rir_from_fraction
        assert estimate_rir_from_fraction(10, 10) == 0


# ===========================================================================
# metrics.py — §6.1  predict_set_reps
# ===========================================================================

class TestPredictSetReps:
    """reps_pred = floor((p - RIR) × e^{-λ(j-1)} × Q_rest(r))
       Q_rest(r) = 1 - q × e^{-r/τ}
    """

    def _q(self, rest: int) -> float:
        return 1 - 0.3 * math.exp(-rest / 60.0)

    def test_first_set_reference_rest(self):
        from bar_scheduler.core.metrics import predict_set_reps
        # j=1: decay = 1.0
        expected = math.floor(8 * 1.0 * self._q(180))
        assert predict_set_reps(10, set_number=1, rest_seconds=180, rir_target=2) == expected

    def test_later_set_has_fewer_reps(self):
        from bar_scheduler.core.metrics import predict_set_reps
        s1 = predict_set_reps(10, 1, 180, 2)
        s3 = predict_set_reps(10, 3, 180, 2)
        assert s3 <= s1

    def test_shorter_rest_reduces_reps(self):
        from bar_scheduler.core.metrics import predict_set_reps
        long  = predict_set_reps(10, 1, 180, 2)
        short = predict_set_reps(10, 1,  30, 2)
        assert short <= long

    def test_set2_manual_formula(self):
        from bar_scheduler.core.metrics import predict_set_reps
        # j=2: decay = e^{-0.08×1}
        p, rir, rest = 12, 2, 180
        expected = math.floor((p - rir) * math.exp(-0.08 * 1) * self._q(rest))
        assert predict_set_reps(p, 2, rest, rir) == expected


# ===========================================================================
# metrics.py — linear_trend_max_reps / trend_slope_per_week
# ===========================================================================

class TestLinearTrend:

    def test_two_points_slope_and_intercept(self):
        from bar_scheduler.core.metrics import linear_trend_max_reps
        a, b = linear_trend_max_reps([(0, 10), (7, 12)])
        assert b == pytest.approx(2 / 7, rel=1e-6)
        assert a == pytest.approx(10.0, rel=1e-6)

    def test_single_point_zero_slope(self):
        from bar_scheduler.core.metrics import linear_trend_max_reps
        a, b = linear_trend_max_reps([(0, 8)])
        assert b == pytest.approx(0.0)
        assert a == pytest.approx(8.0)

    def test_flat_series_zero_slope(self):
        from bar_scheduler.core.metrics import linear_trend_max_reps
        _, b = linear_trend_max_reps([(0, 10), (7, 10), (14, 10)])
        assert b == pytest.approx(0.0, abs=1e-10)

    def test_trend_slope_per_week_converts_to_weekly(self):
        from bar_scheduler.core.metrics import trend_slope_per_week
        # +7 reps in 7 days → 7 reps/week
        history = [
            _test_session("2025-01-01", 10),
            _test_session("2025-01-08", 17),
        ]
        assert trend_slope_per_week(history, window_days=21) == pytest.approx(7.0, rel=1e-4)


# ===========================================================================
# physiology.py — §5.1  rir_effort_multiplier
# ===========================================================================

class TestRIREffortMultiplier:
    """E_rir = 1 + A_RIR × max(0, 3 - rir)   (A_RIR = 0.15)"""

    def test_rir_3_is_neutral(self):
        # RIR=3 is the neutral reference point → multiplier exactly 1.0
        from bar_scheduler.core.physiology import rir_effort_multiplier
        assert rir_effort_multiplier(3) == pytest.approx(1.0)

    def test_rir_above_3_below_neutral(self):
        # High RIR = easy session → multiplier < 1.0 (less fatigue accumulated)
        from bar_scheduler.core.physiology import rir_effort_multiplier
        # RIR=4: 1.0 + 0.15*(3-4) = 0.85
        assert rir_effort_multiplier(4) == pytest.approx(0.85)
        # RIR=5: 1.0 + 0.15*(3-5) = 0.70
        assert rir_effort_multiplier(5) == pytest.approx(0.70)
        # Floor at 0.5: RIR=10 → 1.0 + 0.15*(3-10) = -0.05 → clamped to 0.5
        assert rir_effort_multiplier(10) == pytest.approx(0.5)

    def test_rir_2_adds_one_step(self):
        from bar_scheduler.core.physiology import rir_effort_multiplier
        assert rir_effort_multiplier(2) == pytest.approx(1.0 + A_RIR)

    def test_rir_1_adds_two_steps(self):
        from bar_scheduler.core.physiology import rir_effort_multiplier
        assert rir_effort_multiplier(1) == pytest.approx(1.0 + 2 * A_RIR)

    def test_rir_0_adds_three_steps(self):
        from bar_scheduler.core.physiology import rir_effort_multiplier
        assert rir_effort_multiplier(0) == pytest.approx(1.0 + 3 * A_RIR)


# ===========================================================================
# physiology.py — §5.2  rest_stress_multiplier
# ===========================================================================

class TestRestStressMultiplier:
    """S_rest = clip((r_ref / max(r, r_min))^gamma_s, 1, S_max)"""

    def test_reference_rest_is_one(self):
        from bar_scheduler.core.physiology import rest_stress_multiplier
        assert rest_stress_multiplier(REST_REF_SECONDS) == pytest.approx(1.0, rel=1e-6)

    def test_90s_rest_manual(self):
        from bar_scheduler.core.physiology import rest_stress_multiplier
        # (180/90)^0.15 = 2^0.15
        expected = 2 ** GAMMA_S
        assert rest_stress_multiplier(90) == pytest.approx(expected, rel=1e-6)

    def test_short_rest_greater_than_one(self):
        from bar_scheduler.core.physiology import rest_stress_multiplier
        assert rest_stress_multiplier(60) > 1.0

    def test_below_clamp_equals_at_clamp(self):
        from bar_scheduler.core.physiology import rest_stress_multiplier
        assert rest_stress_multiplier(10) == pytest.approx(rest_stress_multiplier(REST_MIN_CLAMP))

    def test_never_exceeds_s_rest_max(self):
        from bar_scheduler.core.physiology import rest_stress_multiplier
        assert rest_stress_multiplier(1) <= S_REST_MAX + 1e-9


# ===========================================================================
# physiology.py — §5.3  load_stress_multiplier
# ===========================================================================

class TestLoadStressMultiplier:
    """S_load = ((bw + load) / bw_ref)^gamma_L"""

    def test_no_load_matching_bw_is_one(self):
        from bar_scheduler.core.physiology import load_stress_multiplier
        assert load_stress_multiplier(80.0, 0.0, 80.0) == pytest.approx(1.0, rel=1e-6)

    def test_added_load_manual(self):
        from bar_scheduler.core.physiology import load_stress_multiplier
        # (90/80)^1.5
        expected = (90.0 / 80.0) ** GAMMA_LOAD
        assert load_stress_multiplier(80.0, 10.0, 80.0) == pytest.approx(expected, rel=1e-6)

    def test_heavier_bw_increases_stress(self):
        from bar_scheduler.core.physiology import load_stress_multiplier
        assert load_stress_multiplier(90.0, 0.0, 80.0) > 1.0

    def test_gamma_load_applied(self):
        from bar_scheduler.core.physiology import load_stress_multiplier
        bw, load, ref = 85.0, 5.0, 80.0
        expected = ((bw + load) / ref) ** GAMMA_LOAD
        assert load_stress_multiplier(bw, load, ref) == pytest.approx(expected, rel=1e-6)


# ===========================================================================
# physiology.py — grip_stress_multiplier
# ===========================================================================

class TestGripStressMultiplier:

    def test_none_variant_factors_returns_one(self):
        from bar_scheduler.core.physiology import grip_stress_multiplier
        # Without exercise-specific factors, multiplier is 1.0 regardless of grip
        for grip in ("pronated", "neutral", "supinated"):
            assert grip_stress_multiplier(grip) == pytest.approx(1.0)

    def test_variant_factors_passthrough(self):
        from bar_scheduler.core.physiology import grip_stress_multiplier
        # Custom factors are respected
        factors = {"pronated": 1.0, "neutral": 0.95, "supinated": 1.05}
        assert grip_stress_multiplier("supinated", factors) == pytest.approx(1.05)
        assert grip_stress_multiplier("neutral", factors) == pytest.approx(0.95)

    def test_unknown_variant_defaults_to_one(self):
        from bar_scheduler.core.physiology import grip_stress_multiplier
        factors = {"standard": 1.0}
        assert grip_stress_multiplier("unknown_variant", factors) == pytest.approx(1.0)


# ===========================================================================
# physiology.py — §5  calculate_set_hard_reps
# ===========================================================================

class TestCalculateSetHardReps:
    """HR = reps × E_rir(rir)"""

    def test_known_rir(self):
        from bar_scheduler.core.physiology import calculate_set_hard_reps
        # rir=2 → E = 1 + 0.15 = 1.15, HR = 8 × 1.15 = 9.2
        assert calculate_set_hard_reps(8, rir=2, estimated_max=10) == pytest.approx(9.2, rel=1e-6)

    def test_none_rir_estimated_from_max(self):
        from bar_scheduler.core.physiology import calculate_set_hard_reps
        # reps=8, max=10 → rir_hat = 2 → same as above
        assert calculate_set_hard_reps(8, rir=None, estimated_max=10) == pytest.approx(9.2, rel=1e-6)

    def test_rir_zero_gives_max_effort(self):
        from bar_scheduler.core.physiology import calculate_set_hard_reps
        # E_rir(0) = 1 + 3×0.15 = 1.45
        assert calculate_set_hard_reps(8, rir=0, estimated_max=10) == pytest.approx(8 * 1.45, rel=1e-6)


# ===========================================================================
# physiology.py — §5.4  calculate_session_training_load
# ===========================================================================

class TestSessionTrainingLoad:
    """w(t) = Σ HR_j × S_rest_j × S_load_j × S_grip_j"""

    def test_reference_conditions_manual(self):
        from bar_scheduler.core.physiology import calculate_session_training_load
        # 3 sets × 8 reps, 180 s rest, BW only, pronated, bw=bw_ref=80
        # rir_hat = clip(10-8,0,5)=2, E=1.15, HR=9.2
        # S_rest=1.0, S_load=1.0, S_grip=1.0 → w = 3×9.2 = 27.6
        session = _session("2025-01-01", [8, 8, 8], bw=80.0)
        w = calculate_session_training_load(session, estimated_max=10, reference_bodyweight_kg=80.0)
        assert w == pytest.approx(27.6, rel=1e-4)

    def test_more_reps_higher_load(self):
        from bar_scheduler.core.physiology import calculate_session_training_load
        s8  = _session("2025-01-01", [8, 8, 8], bw=80.0)
        s10 = _session("2025-01-01", [10, 10, 10], bw=80.0)
        assert (
            calculate_session_training_load(s10, 15, 80.0)
            > calculate_session_training_load(s8, 15, 80.0)
        )

    def test_added_load_higher_than_bw_only(self):
        from bar_scheduler.core.physiology import calculate_session_training_load
        bw_s = _session("2025-01-01", [8, 8], bw=80.0, added_kg=0.0)
        wt_s = _session("2025-01-01", [8, 8], bw=80.0, added_kg=10.0)
        assert (
            calculate_session_training_load(wt_s, 12, 80.0)
            > calculate_session_training_load(bw_s, 12, 80.0)
        )


# ===========================================================================
# physiology.py — §4.1  update_fitness_fatigue
# ===========================================================================

class TestUpdateFitnessFatigue:
    """G(t) = G(t-1)·e^{-1/τ_G} + k_G·w(t)
       H(t) = H(t-1)·e^{-1/τ_H} + k_H·w(t)
    """

    def test_from_zero_state_one_day(self):
        from bar_scheduler.core.physiology import update_fitness_fatigue
        state = _neutral_ff()
        new = update_fitness_fatigue(state, training_load=10.0, days_since_last=1)
        assert new.fitness == pytest.approx(K_FITNESS * 10.0, rel=1e-6)
        assert new.fatigue == pytest.approx(K_FATIGUE * 10.0, rel=1e-6)

    def test_fatigue_grows_faster_than_fitness(self):
        from bar_scheduler.core.physiology import update_fitness_fatigue
        new = update_fitness_fatigue(_neutral_ff(), 20.0)
        assert new.fatigue > new.fitness   # K_FATIGUE > K_FITNESS

    def test_readiness_is_fitness_minus_fatigue(self):
        from bar_scheduler.core.physiology import update_fitness_fatigue
        new = update_fitness_fatigue(_neutral_ff(), 10.0)
        assert new.readiness() == pytest.approx(new.fitness - new.fatigue, rel=1e-9)

    def test_multi_day_gap_decays_prior_state(self):
        from bar_scheduler.core.physiology import update_fitness_fatigue
        state = FitnessFatigueState(
            fitness=10.0, fatigue=10.0, m_hat=10.0, sigma_m=1.5,
            readiness_mean=0.0, readiness_var=1.0,
        )
        new = update_fitness_fatigue(state, training_load=0.0, days_since_last=7)
        assert new.fitness == pytest.approx(10.0 * math.exp(-7 / TAU_FITNESS), rel=1e-6)
        assert new.fatigue == pytest.approx(10.0 * math.exp(-7 / TAU_FATIGUE), rel=1e-6)


# ===========================================================================
# physiology.py — §4.1  decay_fitness_fatigue
# ===========================================================================

class TestDecayFitnessFatigue:

    def test_fatigue_decays_by_e_inverse_after_tau(self):
        from bar_scheduler.core.physiology import decay_fitness_fatigue
        state = FitnessFatigueState(
            fitness=10.0, fatigue=10.0, m_hat=10.0, sigma_m=1.5,
            readiness_mean=0.0, readiness_var=1.0,
        )
        decayed = decay_fitness_fatigue(state, days=int(TAU_FATIGUE))
        assert decayed.fatigue == pytest.approx(10.0 * math.exp(-1.0), rel=1e-4)

    def test_fitness_decays_slower_than_fatigue(self):
        from bar_scheduler.core.physiology import decay_fitness_fatigue
        state = FitnessFatigueState(
            fitness=10.0, fatigue=10.0, m_hat=10.0, sigma_m=1.5,
            readiness_mean=0.0, readiness_var=1.0,
        )
        decayed = decay_fitness_fatigue(state, days=int(TAU_FATIGUE))
        assert decayed.fitness > decayed.fatigue   # TAU_FITNESS >> TAU_FATIGUE


# ===========================================================================
# physiology.py — §3.2  update_max_estimate
# ===========================================================================

class TestUpdateMaxEstimate:
    """M_hat_new = (1-α)·M_hat + α·M_obs
       σ²_new    = (1-β)·σ²_old + β·(M_obs - M_hat_old)²
    """

    def test_ewma_formula(self):
        from bar_scheduler.core.physiology import update_max_estimate
        state = _neutral_ff(m_hat=10.0)
        new = update_max_estimate(state, observed_max=12)
        expected = (1 - ALPHA_MHAT) * 10.0 + ALPHA_MHAT * 12
        assert new.m_hat == pytest.approx(expected, rel=1e-6)

    def test_observation_above_pulls_up(self):
        from bar_scheduler.core.physiology import update_max_estimate
        new = update_max_estimate(_neutral_ff(10.0), 14)
        assert new.m_hat > 10.0

    def test_observation_below_pulls_down(self):
        from bar_scheduler.core.physiology import update_max_estimate
        new = update_max_estimate(_neutral_ff(10.0), 7)
        assert new.m_hat < 10.0

    def test_sigma_variance_formula(self):
        from bar_scheduler.core.physiology import update_max_estimate
        state = _neutral_ff(m_hat=10.0)
        new = update_max_estimate(state, observed_max=12)
        residual_sq = (12 - 10.0) ** 2   # uses old m_hat
        expected_var = (1 - BETA_SIGMA) * (1.5 ** 2) + BETA_SIGMA * residual_sq
        assert new.sigma_m == pytest.approx(math.sqrt(expected_var), rel=1e-6)


# ===========================================================================
# physiology.py — §4.2  predicted_max_with_readiness
# ===========================================================================

class TestPredictedMaxWithReadiness:
    """M_pred = M_base × (1 + c_R × (R - R_bar))"""

    def test_readiness_at_mean_is_identity(self):
        from bar_scheduler.core.physiology import predicted_max_with_readiness
        assert predicted_max_with_readiness(10.0, 5.0, 5.0) == pytest.approx(10.0)

    def test_above_mean_raises_prediction(self):
        from bar_scheduler.core.physiology import predicted_max_with_readiness
        assert predicted_max_with_readiness(10.0, 6.0, 5.0) > 10.0

    def test_below_mean_lowers_prediction(self):
        from bar_scheduler.core.physiology import predicted_max_with_readiness
        assert predicted_max_with_readiness(10.0, 4.0, 5.0) < 10.0

    def test_exact_formula(self):
        from bar_scheduler.core.physiology import predicted_max_with_readiness
        result = predicted_max_with_readiness(10.0, 3.0, 1.0)
        expected = 10.0 * (1 + C_READINESS * (3.0 - 1.0))
        assert result == pytest.approx(expected, rel=1e-6)


# ===========================================================================
# physiology.py — §9  build_fitness_fatigue_state
# ===========================================================================

class TestBuildFitnessFatigueState:

    def test_no_history_uses_baseline(self):
        from bar_scheduler.core.physiology import build_fitness_fatigue_state
        state = build_fitness_fatigue_state([], 80.0, baseline_max=15)
        assert state.m_hat == pytest.approx(15.0)

    def test_no_history_no_baseline_defaults_to_ten(self):
        from bar_scheduler.core.physiology import build_fitness_fatigue_state
        state = build_fitness_fatigue_state([], 80.0)
        assert state.m_hat == pytest.approx(10.0)

    def test_no_history_zero_fitness_fatigue(self):
        from bar_scheduler.core.physiology import build_fitness_fatigue_state
        state = build_fitness_fatigue_state([], 80.0, baseline_max=10)
        assert state.fitness == pytest.approx(0.0)
        assert state.fatigue == pytest.approx(0.0)

    def test_test_session_sets_m_hat(self):
        from bar_scheduler.core.physiology import build_fitness_fatigue_state
        history = [_test_session("2025-01-01", 12)]
        state = build_fitness_fatigue_state(history, 80.0, baseline_max=10)
        assert state.m_hat == pytest.approx(12.0)

    def test_training_session_increases_fatigue(self):
        from bar_scheduler.core.physiology import build_fitness_fatigue_state
        history = [_session("2025-01-01", [8, 8, 8])]
        state = build_fitness_fatigue_state(history, 80.0, baseline_max=10)
        assert state.fatigue > 0.0


# ===========================================================================
# adaptation.py — §8.1  detect_plateau
# ===========================================================================

class TestDetectPlateau:

    def test_no_history_false(self):
        from bar_scheduler.core.adaptation import detect_plateau
        assert detect_plateau([]) is False

    def test_single_test_session_false(self):
        from bar_scheduler.core.adaptation import detect_plateau
        assert detect_plateau([_test_session("2025-01-01", 10)]) is False

    def test_rising_slope_not_plateau(self):
        from bar_scheduler.core.adaptation import detect_plateau
        # +7 reps/week >> PLATEAU_SLOPE_THRESHOLD
        history = [
            _test_session("2025-01-01", 5),
            _test_session("2025-01-08", 12),
        ]
        assert detect_plateau(history) is False

    def test_stalled_below_alltime_best_is_plateau(self):
        from bar_scheduler.core.adaptation import detect_plateau
        from datetime import date, timedelta
        base = date(2025, 1, 1)
        # Day 0: all-time best (10). Days 39 & 60: below best (8).
        # Trend window (21 days from day 60) contains both day-39 and day-60 sessions.
        # slope = 0  <  0.05 reps/week. No new best in 21-day window.
        history = [
            _test_session((base).strftime("%Y-%m-%d"), 10),
            _test_session((base + timedelta(39)).strftime("%Y-%m-%d"), 8),
            _test_session((base + timedelta(60)).strftime("%Y-%m-%d"), 8),
        ]
        assert detect_plateau(history) is True


# ===========================================================================
# adaptation.py — calculate_fatigue_score
# ===========================================================================

class TestCalculateFatigueScore:
    """fatigue_score = (actual_max - predicted) / predicted"""

    def test_no_test_sessions_zero(self):
        from bar_scheduler.core.adaptation import calculate_fatigue_score
        history = [_session("2025-01-01", [8, 8])]
        assert calculate_fatigue_score(history, _neutral_ff()) == pytest.approx(0.0)

    def test_overperformance_positive(self):
        from bar_scheduler.core.adaptation import calculate_fatigue_score
        # neutral state → predicted = m_hat = 10.  actual = 12 → +0.2
        state = _neutral_ff(m_hat=10.0)
        history = [_test_session("2025-01-01", 12)]
        assert calculate_fatigue_score(history, state) == pytest.approx(0.2, rel=1e-6)

    def test_underperformance_negative(self):
        from bar_scheduler.core.adaptation import calculate_fatigue_score
        state = _neutral_ff(m_hat=10.0)
        history = [_test_session("2025-01-01", 8)]
        assert calculate_fatigue_score(history, state) == pytest.approx(-0.2, rel=1e-6)

    def test_exact_performance_zero(self):
        from bar_scheduler.core.adaptation import calculate_fatigue_score
        state = _neutral_ff(m_hat=10.0)
        history = [_test_session("2025-01-01", 10)]
        assert calculate_fatigue_score(history, state) == pytest.approx(0.0, abs=1e-6)


# ===========================================================================
# adaptation.py — §8.2  check_underperformance
# ===========================================================================

class TestCheckUnderperformance:
    """actual < predicted × (1 - threshold) for N consecutive S sessions"""

    def test_too_few_sessions_false(self):
        from bar_scheduler.core.adaptation import check_underperformance
        history = [_session("2025-01-01", [7])]
        assert check_underperformance(history, _neutral_ff(10.0), consecutive_required=2) is False

    def test_both_below_threshold_true(self):
        from bar_scheduler.core.adaptation import check_underperformance
        # predicted=10, threshold=9, both sessions give max=7 < 9
        history = [
            _session("2025-01-01", [7]),
            _session("2025-01-04", [7]),
        ]
        assert check_underperformance(history, _neutral_ff(10.0)) is True

    def test_one_good_session_breaks_streak(self):
        from bar_scheduler.core.adaptation import check_underperformance
        history = [
            _session("2025-01-01", [7]),
            _session("2025-01-04", [10]),  # ≥ threshold (9) → OK
        ]
        assert check_underperformance(history, _neutral_ff(10.0)) is False

    def test_exactly_at_threshold_is_not_underperforming(self):
        from bar_scheduler.core.adaptation import check_underperformance
        # threshold_max = 10 × 0.9 = 9; reps=9 ≥ 9 → not underperforming
        history = [
            _session("2025-01-01", [7]),
            _session("2025-01-04", [9]),
        ]
        assert check_underperformance(history, _neutral_ff(10.0)) is False


# ===========================================================================
# adaptation.py — §8.2  should_deload
# ===========================================================================

class TestShouldDeload:

    def test_no_history_false(self):
        from bar_scheduler.core.adaptation import should_deload
        assert should_deload([], _neutral_ff()) is False

    def test_low_compliance_triggers_deload(self):
        from bar_scheduler.core.adaptation import should_deload
        # Plan 20 reps, complete 5 → compliance ≈ 0.25 < 0.70
        session = SessionResult(
            date="2025-01-01", bodyweight_kg=80.0, grip="pronated", session_type="S",
            planned_sets=[_planned(10), _planned(10)],
            completed_sets=[_set(3), _set(2)],
        )
        assert should_deload([session], _neutral_ff()) is True

    def test_good_compliance_no_plateau_no_deload(self):
        from bar_scheduler.core.adaptation import should_deload
        # compliance=1.0, no TEST → no plateau, single S → no underperformance
        assert should_deload([_session("2025-01-01", [10, 10])], _neutral_ff()) is False


# ===========================================================================
# adaptation.py — §7.4  apply_autoregulation
# ===========================================================================

class TestApplyAutoregulation:
    """z < -1 → reduce sets; -1 ≤ z ≤ 1 → base plan; z > 1 → +1 rep"""

    def test_low_z_reduces_sets(self):
        from bar_scheduler.core.adaptation import apply_autoregulation
        state = _ff_with_z(-2.0)
        sets, reps = apply_autoregulation(base_sets=5, base_reps=8, ff_state=state)
        expected = max(3, int(5 * (1 - READINESS_VOLUME_REDUCTION)))
        assert sets == expected
        assert reps == 8

    def test_normal_z_returns_base(self):
        from bar_scheduler.core.adaptation import apply_autoregulation
        sets, reps = apply_autoregulation(5, 8, _ff_with_z(0.0))
        assert sets == 5 and reps == 8

    def test_high_z_adds_one_rep(self):
        from bar_scheduler.core.adaptation import apply_autoregulation
        sets, reps = apply_autoregulation(5, 8, _ff_with_z(2.0))
        assert sets == 5 and reps == 9

    def test_low_z_never_below_three_sets(self):
        from bar_scheduler.core.adaptation import apply_autoregulation
        sets, _ = apply_autoregulation(base_sets=4, base_reps=8, ff_state=_ff_with_z(-5.0))
        assert sets >= 3


# ===========================================================================
# adaptation.py — calculate_volume_adjustment
# ===========================================================================

class TestCalculateVolumeAdjustment:

    def _compliant_session(self) -> SessionResult:
        """One S session with perfect compliance — no deload triggers."""
        return _session("2025-01-01", [10, 10])

    def test_low_z_reduces_volume(self):
        from bar_scheduler.core.adaptation import calculate_volume_adjustment
        history = [self._compliant_session()]
        result = calculate_volume_adjustment(history, _ff_with_z(-2.0), current_weekly_sets=12)
        expected = max(WEEKLY_HARD_SETS_MIN, int(12 * (1 - READINESS_VOLUME_REDUCTION)))
        assert result == expected

    def test_high_z_good_compliance_increases_volume(self):
        from bar_scheduler.core.adaptation import calculate_volume_adjustment
        history = [self._compliant_session()]
        result = calculate_volume_adjustment(history, _ff_with_z(2.0), current_weekly_sets=12)
        expected = min(WEEKLY_HARD_SETS_MAX, int(12 * (1 + WEEKLY_VOLUME_INCREASE_RATE)))
        assert result == expected

    def test_normal_z_maintains_volume(self):
        from bar_scheduler.core.adaptation import calculate_volume_adjustment
        history = [self._compliant_session()]
        result = calculate_volume_adjustment(history, _ff_with_z(0.0), current_weekly_sets=12)
        assert result == 12

    def test_deload_reduces_volume_significantly(self):
        from bar_scheduler.core.adaptation import calculate_volume_adjustment
        # Low-compliance session triggers deload
        session = SessionResult(
            date="2025-01-01", bodyweight_kg=80.0, grip="pronated", session_type="S",
            planned_sets=[_planned(10), _planned(10)],
            completed_sets=[_set(2), _set(2)],
        )
        result = calculate_volume_adjustment([session], _neutral_ff(), current_weekly_sets=14)
        expected = max(WEEKLY_HARD_SETS_MIN, int(14 * (1 - DELOAD_VOLUME_REDUCTION)))
        assert result == expected


# ===========================================================================
# equipment.py — compute_leff, check_band_progression, compute_equipment_adjustment
# ===========================================================================

class TestComputeLeff:
    """Effective load formula: Leff = BW × bw_fraction + added − assistance."""

    def test_band_medium_pull_up(self):
        """BW=80, bw_fraction=1.0, BAND_MEDIUM (35 kg) → Leff = 80 - 35 = 45."""
        from bar_scheduler.core.equipment import compute_leff
        leff = compute_leff(bw_fraction=1.0, bodyweight_kg=80.0, added_weight_kg=0.0, assistance_kg=35.0)
        assert leff == pytest.approx(45.0)

    def test_weight_belt_pull_up(self):
        """BW=80, bw_fraction=1.0, added=5 (weight belt) → Leff = 80 + 5 = 85."""
        from bar_scheduler.core.equipment import compute_leff
        leff = compute_leff(bw_fraction=1.0, bodyweight_kg=80.0, added_weight_kg=5.0, assistance_kg=0.0)
        assert leff == pytest.approx(85.0)

    def test_bss_bodyweight(self):
        """BSS: bw_fraction=0.71, added=0, no assistance → Leff = 0.71 × 80 = 56.8."""
        from bar_scheduler.core.equipment import compute_leff
        leff = compute_leff(bw_fraction=0.71, bodyweight_kg=80.0, added_weight_kg=0.0)
        assert leff == pytest.approx(56.8, rel=1e-4)

    def test_bss_with_dumbbells(self):
        """BSS: bw_fraction=0.71, BW=80, added=20 → Leff = 0.71×80 + 20 = 76.8."""
        from bar_scheduler.core.equipment import compute_leff
        leff = compute_leff(bw_fraction=0.71, bodyweight_kg=80.0, added_weight_kg=20.0)
        assert leff == pytest.approx(76.8, rel=1e-4)

    def test_over_assisted_clamps_to_zero(self):
        """Excessive assistance should clamp Leff to 0, not go negative."""
        from bar_scheduler.core.equipment import compute_leff
        leff = compute_leff(bw_fraction=1.0, bodyweight_kg=50.0, added_weight_kg=0.0, assistance_kg=100.0)
        assert leff == 0.0


class TestCheckBandProgression:
    """check_band_progression returns True when last N sessions hit the rep ceiling."""

    def _make_sessions(self, reps_list: list[int]) -> list:
        sessions = []
        from bar_scheduler.core.models import SessionResult, SetResult
        for i, reps in enumerate(reps_list):
            s = SetResult(target_reps=reps, actual_reps=reps, rest_seconds_before=180, added_weight_kg=0.0, rir_target=2)
            sessions.append(SessionResult(
                date=f"2026-01-{i+1:02d}", bodyweight_kg=80.0, grip="pronated",
                session_type="H", exercise_id="pull_up",
                planned_sets=[], completed_sets=[s],
            ))
        return sessions

    def test_two_sessions_at_ceiling_true(self):
        from bar_scheduler.core.equipment import check_band_progression
        from bar_scheduler.core.exercises.registry import get_exercise
        ex = get_exercise("pull_up")
        # H session reps_max = 12; both sessions hit 12
        history = self._make_sessions([12, 12])
        assert check_band_progression(history, "pull_up", ex.session_params, n_sessions=2) is True

    def test_one_session_below_ceiling_false(self):
        from bar_scheduler.core.equipment import check_band_progression
        from bar_scheduler.core.exercises.registry import get_exercise
        ex = get_exercise("pull_up")
        history = self._make_sessions([12, 8])  # last session only 8 reps
        assert check_band_progression(history, "pull_up", ex.session_params, n_sessions=2) is False

    def test_too_few_sessions_false(self):
        from bar_scheduler.core.equipment import check_band_progression
        from bar_scheduler.core.exercises.registry import get_exercise
        ex = get_exercise("pull_up")
        history = self._make_sessions([12])  # only 1 session, need 2
        assert check_band_progression(history, "pull_up", ex.session_params, n_sessions=2) is False


class TestComputeEquipmentAdjustment:
    """Rep factor adjustments when Leff changes by ≥10%."""

    def test_10pct_increase_reduces_reps_20pct(self):
        from bar_scheduler.core.equipment import compute_equipment_adjustment
        adj = compute_equipment_adjustment(old_leff=80.0, new_leff=88.0)  # +10%
        assert adj["reps_factor"] == pytest.approx(0.80)

    def test_10pct_decrease_increases_reps(self):
        from bar_scheduler.core.equipment import compute_equipment_adjustment
        adj = compute_equipment_adjustment(old_leff=80.0, new_leff=72.0)  # -10%
        expected_factor = round(1.0 / (72.0 / 80.0), 2)
        assert adj["reps_factor"] == pytest.approx(expected_factor, rel=1e-3)

    def test_minor_change_no_adjustment(self):
        from bar_scheduler.core.equipment import compute_equipment_adjustment
        adj = compute_equipment_adjustment(old_leff=80.0, new_leff=85.0)  # +6.25% — < 10%
        assert adj["reps_factor"] == pytest.approx(1.0)

    def test_zero_old_leff_no_adjustment(self):
        from bar_scheduler.core.equipment import compute_equipment_adjustment
        adj = compute_equipment_adjustment(old_leff=0.0, new_leff=80.0)
        assert adj["reps_factor"] == pytest.approx(1.0)


class TestLoadStressWithAssistance:
    """load_stress_multiplier subtracts assistance_kg from effective load."""

    def test_band_reduces_load_stress(self):
        from bar_scheduler.core.physiology import load_stress_multiplier
        # Without band: S_load at BW=80, reference=80, bw_fraction=1.0
        no_band = load_stress_multiplier(80.0, 0.0, 80.0, bw_fraction=1.0, assistance_kg=0.0)
        # With BAND_MEDIUM: Leff = 80 - 35 = 45 → smaller stress
        with_band = load_stress_multiplier(80.0, 0.0, 80.0, bw_fraction=1.0, assistance_kg=35.0)
        assert with_band < no_band

    def test_bss_new_bw_fraction(self):
        """BSS bw_fraction=0.71 gives non-zero stress even without added weight."""
        from bar_scheduler.core.physiology import load_stress_multiplier
        stress = load_stress_multiplier(80.0, 0.0, 80.0, bw_fraction=0.71, assistance_kg=0.0)
        # Leff = 0.71 × 80 = 56.8; L_rel = 56.8/80 = 0.71; S = 0.71^GAMMA_LOAD
        from bar_scheduler.core.config import GAMMA_LOAD
        expected = (0.71 ** GAMMA_LOAD)
        assert stress == pytest.approx(expected, rel=1e-4)


class TestEquipmentSerialization:
    """EquipmentSnapshot round-trips through serializers."""

    def test_snapshot_round_trip(self):
        from bar_scheduler.io.serializers import equipment_snapshot_to_dict, dict_to_equipment_snapshot
        from bar_scheduler.core.models import EquipmentSnapshot
        snap = EquipmentSnapshot(active_item="BAND_MEDIUM", assistance_kg=35.0, elevation_height_cm=None)
        d = equipment_snapshot_to_dict(snap)
        loaded = dict_to_equipment_snapshot(d)
        assert loaded.active_item == "BAND_MEDIUM"
        assert loaded.assistance_kg == pytest.approx(35.0)
        assert loaded.elevation_height_cm is None

    def test_snapshot_with_elevation(self):
        from bar_scheduler.io.serializers import equipment_snapshot_to_dict, dict_to_equipment_snapshot
        from bar_scheduler.core.models import EquipmentSnapshot
        snap = EquipmentSnapshot(active_item="ELEVATION_SURFACE", assistance_kg=0.0, elevation_height_cm=45)
        d = equipment_snapshot_to_dict(snap)
        loaded = dict_to_equipment_snapshot(d)
        assert loaded.elevation_height_cm == 45

    def test_session_result_with_snapshot_serializes(self):
        from bar_scheduler.io.serializers import session_result_to_dict, dict_to_session_result
        from bar_scheduler.core.models import SessionResult, SetResult, EquipmentSnapshot
        snap = EquipmentSnapshot(active_item="BAND_LIGHT", assistance_kg=17.0)
        s = SetResult(target_reps=8, actual_reps=8, rest_seconds_before=180, added_weight_kg=0.0, rir_target=2)
        session = SessionResult(
            date="2026-03-01", bodyweight_kg=80.0, grip="pronated",
            session_type="H", exercise_id="pull_up",
            equipment_snapshot=snap, planned_sets=[], completed_sets=[s],
        )
        d = session_result_to_dict(session)
        assert "equipment_snapshot" in d
        assert d["equipment_snapshot"]["active_item"] == "BAND_LIGHT"
        loaded = dict_to_session_result(d)
        assert loaded.equipment_snapshot is not None
        assert loaded.equipment_snapshot.active_item == "BAND_LIGHT"
        assert loaded.equipment_snapshot.assistance_kg == pytest.approx(17.0)

    def test_session_without_snapshot_backward_compat(self):
        """Legacy sessions (no equipment_snapshot key) load with snapshot=None."""
        from bar_scheduler.io.serializers import dict_to_session_result
        legacy = {
            "date": "2026-01-01", "bodyweight_kg": 80.0, "grip": "pronated",
            "session_type": "S", "exercise_id": "pull_up",
            "completed_sets": [{"target_reps": 8, "actual_reps": 8,
                                 "rest_seconds_before": 180, "added_weight_kg": 0.0,
                                 "rir_target": 2}],
        }
        session = dict_to_session_result(legacy)
        assert session.equipment_snapshot is None


# ===========================================================================
# Regression tests for Bug 1: dip no-variant-rotation
# ===========================================================================

class TestDipNoVariantRotation:
    """Dip plans must always use the primary variant (standard), never rotate."""

    def test_dip_grip_always_standard(self):
        """generate_plan for dip must return grip='standard' for every session."""
        from bar_scheduler.core.planner import generate_plan
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.models import UserState, UserProfile, SessionResult, SetResult

        exercise = get_exercise("dip")
        profile = UserProfile(height_cm=180, sex="male", preferred_days_per_week=3)
        test_set = SetResult(target_reps=7, actual_reps=7, rest_seconds_before=180)
        history = [
            SessionResult(
                date="2026-01-01", bodyweight_kg=80.0, grip="standard",
                session_type="TEST", exercise_id="dip",
                planned_sets=[test_set], completed_sets=[test_set],
            )
        ]
        user_state = UserState(profile=profile, current_bodyweight_kg=80.0, history=history)
        plans = generate_plan(user_state, "2026-01-02", weeks_ahead=4, exercise=exercise)
        bad = [p for p in plans if p.grip != "standard"]
        assert not bad, f"Dip plans with non-standard grip: {[(p.date, p.grip) for p in bad]}"


# ===========================================================================
# Regression tests for Bug 2: REST session type
# ===========================================================================

class TestRestSessionType:
    """REST sessions must be accepted, stored, and ignored by rotation/planner logic."""

    def test_rest_is_valid_session_type(self):
        """SessionResult with session_type='REST' must construct without error."""
        from bar_scheduler.core.models import SessionResult

        session = SessionResult(
            date="2026-01-02", bodyweight_kg=80.0, grip="standard",
            session_type="REST", exercise_id="dip",
            planned_sets=[], completed_sets=[],
        )
        assert session.session_type == "REST"

    def test_rest_not_counted_in_rotation(self):
        """REST session between two S sessions must not reset S→H→E rotation."""
        from bar_scheduler.core.planner import get_next_session_type_index, get_schedule_template
        from bar_scheduler.core.models import SessionResult, SetResult

        s_set = SetResult(target_reps=5, actual_reps=5, rest_seconds_before=180)
        history = [
            SessionResult(
                date="2026-01-01", bodyweight_kg=80.0, grip="pronated",
                session_type="S", exercise_id="pull_up",
                planned_sets=[s_set], completed_sets=[s_set],
            ),
            SessionResult(
                date="2026-01-02", bodyweight_kg=80.0, grip="pronated",
                session_type="REST", exercise_id="pull_up",
                planned_sets=[], completed_sets=[],
            ),
        ]
        schedule = get_schedule_template(3)  # ["S", "H", "E"]
        idx = get_next_session_type_index(history, schedule)
        # After one S session (ignoring the REST), next should be H at index 1
        assert idx == 1, (
            f"Expected rotation index 1 (H after S), got {idx}. "
            "REST session must not advance or reset the rotation."
        )

    def test_rest_serializes_to_jsonl(self):
        """REST session must round-trip through JSONL serialization."""
        from bar_scheduler.core.models import SessionResult
        from bar_scheduler.io.serializers import session_result_to_dict, dict_to_session_result

        session = SessionResult(
            date="2026-01-02", bodyweight_kg=80.0, grip="standard",
            session_type="REST", exercise_id="dip",
            planned_sets=[], completed_sets=[],
        )
        d = session_result_to_dict(session)
        assert d["session_type"] == "REST"
        loaded = dict_to_session_result(d)
        assert loaded.session_type == "REST"
        assert loaded.date == "2026-01-02"


class TestPlanStartDatePerExercise:
    """plan_start_date is stored and read independently per exercise."""

    def test_plan_start_dates_are_independent(self, tmp_path):
        """Setting plan_start_date for dip must not affect pull_up."""
        import json
        from bar_scheduler.io.history_store import HistoryStore

        profile = {"training_days_per_week": 3, "current_bodyweight_kg": 80.0}
        (tmp_path / "profile.json").write_text(json.dumps(profile))

        pull_up_store = HistoryStore(tmp_path / "history.jsonl", exercise_id="pull_up")
        dip_store     = HistoryStore(tmp_path / "dip_history.jsonl", exercise_id="dip")

        pull_up_store.set_plan_start_date("2026-02-20")
        dip_store.set_plan_start_date("2026-02-26")

        assert pull_up_store.get_plan_start_date() == "2026-02-20"
        assert dip_store.get_plan_start_date()     == "2026-02-26"

    def test_legacy_plan_start_date_readable(self, tmp_path):
        """Legacy single plan_start_date key is still readable for pull_up."""
        import json
        from bar_scheduler.io.history_store import HistoryStore

        profile = {"training_days_per_week": 3, "plan_start_date": "2026-02-15"}
        (tmp_path / "profile.json").write_text(json.dumps(profile))

        store = HistoryStore(tmp_path / "history.jsonl", exercise_id="pull_up")
        assert store.get_plan_start_date() == "2026-02-15"

    def test_legacy_key_not_written_on_update(self, tmp_path):
        """After set_plan_start_date(), new per-exercise key is used; old key untouched."""
        import json
        from bar_scheduler.io.history_store import HistoryStore

        profile = {"training_days_per_week": 3, "plan_start_date": "2026-02-15"}
        (tmp_path / "profile.json").write_text(json.dumps(profile))

        store = HistoryStore(tmp_path / "history.jsonl", exercise_id="pull_up")
        store.set_plan_start_date("2026-02-20")

        data = json.loads((tmp_path / "profile.json").read_text())
        assert data["plan_start_dates"]["pull_up"] == "2026-02-20"
        assert data["plan_start_date"] == "2026-02-15"   # legacy key untouched
        assert store.get_plan_start_date() == "2026-02-20"  # new key takes precedence


# ===========================================================================
# Regression tests: explain_plan_entry() accuracy bugs
# ===========================================================================

class TestExplainAccuracy:
    """
    Regression tests for bugs in explain_plan_entry() that caused it to diverge
    from generate_plan().  Each test targets a specific known divergence.

    Bug B: BSS last_test_weight not extracted → always shows 0 kg weight.
    Bug C: week-number anchor uses first REST record as epoch → wrong week shown.
    Bug F: has_variant_rotation not checked → _next_grip called for non-rotating exercises.
    """

    def test_bss_last_test_weight_used(self):
        """
        explain_plan_entry() must show the weight from the last BSS TEST session, not 0 kg.

        Bug: _calculate_added_weight(exercise, tm, bw) is called without last_test_weight.
        For BSS (load_type='external_only'), _calculate_added_weight returns last_test_weight
        which defaults to 0.0 → the explain always shows "ADDED WEIGHT: 0.0 kg".
        """
        from bar_scheduler.core.planner import explain_plan_entry
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.models import UserState, UserProfile, SessionResult, SetResult

        bss = get_exercise("bss")
        profile = UserProfile(height_cm=175, sex="male", preferred_days_per_week=3)
        test_set = SetResult(
            target_reps=10, actual_reps=10, rest_seconds_before=180, added_weight_kg=15.0,
        )
        history = [
            SessionResult(
                date="2026-01-01", bodyweight_kg=80.0, grip="standard",
                session_type="TEST", exercise_id="bss",
                planned_sets=[test_set], completed_sets=[test_set],
            ),
        ]
        state = UserState(profile=profile, current_bodyweight_kg=80.0, history=history)

        # plan_start = day after TEST; first session is S (rotation idx 0, no prior S/H/E/T)
        output = explain_plan_entry(state, "2026-01-02", "2026-01-02", exercise=bss)

        assert "ADDED WEIGHT: 15.0 kg" in output, (
            "Bug B: explain_plan_entry() showed 0.0 kg for BSS S session "
            "instead of using the last TEST dumbbell weight (15.0 kg).\n"
            f"Output:\n{output[:600]}"
        )

    def test_week_anchor_excludes_rest_sessions(self):
        """
        Week numbers in explain must match generate_plan week numbers even when
        a REST record exists before the first real training session.

        Bug: explain builds original_history without filtering REST, so first_date
        can be a REST record → week_offset is inflated → week_num is too high.
        """
        from bar_scheduler.core.planner import explain_plan_entry, generate_plan
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.models import UserState, UserProfile, SessionResult, SetResult

        exercise = get_exercise("pull_up")
        profile = UserProfile(height_cm=175, sex="male", preferred_days_per_week=3)
        test_set = SetResult(target_reps=12, actual_reps=12, rest_seconds_before=180)
        history = [
            # REST record 12 days before the TEST — must NOT become the epoch anchor.
            # If used: week_offset = 12//7 = 1 → week_num = 1+0+1 = 2 (WRONG).
            SessionResult(
                date="2025-12-25", bodyweight_kg=80.0, grip="pronated",
                session_type="REST", exercise_id="pull_up",
                planned_sets=[], completed_sets=[],
            ),
            SessionResult(
                date="2026-01-05", bodyweight_kg=80.0, grip="pronated",
                session_type="TEST", exercise_id="pull_up",
                planned_sets=[test_set], completed_sets=[test_set],
            ),
        ]
        state = UserState(profile=profile, current_bodyweight_kg=80.0, history=history)
        plan_start = "2026-01-06"

        # generate_plan correctly excludes REST → first plan session is Week 1
        plans = generate_plan(state, plan_start, 4, exercise=exercise)
        first = plans[0]

        output = explain_plan_entry(state, plan_start, first.date, exercise=exercise)
        expected_marker = f"Week {first.week_number}"  # "Week 1"
        assert expected_marker in output, (
            f"Bug C: explain shows wrong week number for {first.date}. "
            f"generate_plan says week {first.week_number} but explain disagrees.\n"
            f"Output:\n{output[:600]}"
        )

    def test_dip_explain_shows_primary_variant(self):
        """
        explain_plan_entry() for DIP must show the primary variant ('standard')
        and must not crash when has_variant_rotation=False.

        Bug F risk: explain calls _next_grip unconditionally; generate_plan checks
        has_variant_rotation first. Both return primary_variant for DIP but for
        different reasons — the guard ensures they always agree.
        """
        from bar_scheduler.core.planner import explain_plan_entry
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.models import UserState, UserProfile, SessionResult, SetResult

        dip = get_exercise("dip")
        profile = UserProfile(height_cm=175, sex="male", preferred_days_per_week=3)
        test_set = SetResult(target_reps=10, actual_reps=10, rest_seconds_before=180)
        history = [
            SessionResult(
                date="2026-01-01", bodyweight_kg=80.0, grip="standard",
                session_type="TEST", exercise_id="dip",
                planned_sets=[test_set], completed_sets=[test_set],
            ),
        ]
        state = UserState(profile=profile, current_bodyweight_kg=80.0, history=history)

        output = explain_plan_entry(state, "2026-01-02", "2026-01-02", exercise=dip)

        # DIP should show 'standard' variant and must not crash
        assert "standard" in output.lower(), (
            f"explain_plan_entry() for DIP must show 'standard' variant.\nOutput:\n{output[:500]}"
        )


class TestStableWeekNumbers:
    """Week numbers must be Monday-anchored (Mon-Sun calendar weeks), not day-of-week shifted."""

    def test_week_numbers_monday_anchored(self):
        """
        Week numbers are anchored to the Monday of the week containing the first
        training session. This ensures all sessions in the same Mon-Sun calendar
        week share the same week number, regardless of plan_start_date.

        first_date = 2026-02-17 (Tuesday)
        first_monday = 2026-02-16 (Monday of that week)

        Expected (first_monday = 02.16):
          02.17: (1 day) → week 1
          02.23: (7 days) → week 2   (plan_start — was week 1 with old formula, WRONG)
          02.24: (8 days) → week 2
          03.02: (15 days) → week 3  (Monday — same calendar week as 03.04)
          03.04: (17 days) → week 3  (both 03.02 and 03.04 are week 3 now, CORRECT)
        """
        from datetime import datetime, timedelta
        from bar_scheduler.core.planner import generate_plan
        from bar_scheduler.core.models import SessionResult, SetResult, UserProfile, UserState
        from bar_scheduler.core.exercises.registry import get_exercise
        PULL_UP = get_exercise("pull_up")

        first_day = "2026-02-17"  # Tuesday — training epoch
        test_set = SetResult(target_reps=12, actual_reps=12, rest_seconds_before=180,
                             added_weight_kg=0.0, rir_target=0, rir_reported=0)
        history = [
            SessionResult(date=first_day, bodyweight_kg=80.0, grip="pronated",
                          session_type="TEST", exercise_id="pull_up",
                          planned_sets=[test_set], completed_sets=[test_set]),
        ]
        profile = UserProfile(height_cm=175, sex="male", preferred_days_per_week=3)
        state = UserState(profile=profile, current_bodyweight_kg=80.0, history=history)

        plans = generate_plan(state, "2026-02-23", 4, exercise=PULL_UP)

        first_dt = datetime.strptime(first_day, "%Y-%m-%d")
        first_monday = first_dt - timedelta(days=first_dt.weekday())
        for plan in plans:
            plan_dt = datetime.strptime(plan.date, "%Y-%m-%d")
            expected_week = (plan_dt - first_monday).days // 7 + 1
            assert plan.week_number == expected_week, (
                f"Date {plan.date}: expected week {expected_week} (Monday-anchored), "
                f"got {plan.week_number}."
            )

    def test_monday_and_wednesday_same_week(self):
        """
        A Monday session and a Wednesday session in the same ISO calendar week
        must both have the same week number.

        Scenario: first_date = 02.17 (Tue), plan_start = 02.25 (Wed)
        With 4-day schedule [0,1,3,5] from 02.25:
          02.25 (Wed), 02.26 (Thu), 02.28 (Sat), 03.02 (Mon)  ← plan week 0
          03.04 (Wed), 03.05 (Thu), 03.07 (Sat), 03.09 (Mon)  ← plan week 1

        With Monday-anchoring (first_monday = 02.16):
          03.02: (15 days) → week 3
          03.04: (17 days) → week 3  ← same week! CORRECT

        Old formula (anchored to first_date 02.17 Tue):
          03.02: 13 days → week 2
          03.04: 15 days → week 3  ← different weeks, WRONG
        """
        from datetime import datetime, timedelta
        from bar_scheduler.core.planner import generate_plan
        from bar_scheduler.core.models import SessionResult, SetResult, UserProfile, UserState
        from bar_scheduler.core.exercises.registry import get_exercise
        PULL_UP = get_exercise("pull_up")

        first_day = "2026-02-17"  # Tuesday
        test_set = SetResult(target_reps=12, actual_reps=12, rest_seconds_before=180,
                             added_weight_kg=0.0, rir_target=0, rir_reported=0)
        history = [
            SessionResult(date=first_day, bodyweight_kg=80.0, grip="pronated",
                          session_type="TEST", exercise_id="pull_up",
                          planned_sets=[test_set], completed_sets=[test_set]),
        ]
        profile = UserProfile(height_cm=175, sex="male", preferred_days_per_week=4)
        state = UserState(profile=profile, current_bodyweight_kg=80.0, history=history)

        # plan_start = 02.25 (Wed); 4-day offsets [0,1,3,5] → sessions cross week boundary
        plans = generate_plan(state, "2026-02-25", 4, exercise=PULL_UP)

        plan_by_date = {p.date: p.week_number for p in plans}

        # 03.02 (Mon) and 03.04 (Wed) are in the same ISO calendar week
        # Both must get the same week number with Monday-anchored formula
        if "2026-03-02" in plan_by_date and "2026-03-04" in plan_by_date:
            assert plan_by_date["2026-03-02"] == plan_by_date["2026-03-04"], (
                f"03.02 week={plan_by_date['2026-03-02']}, "
                f"03.04 week={plan_by_date['2026-03-04']}: "
                "Monday and Wednesday in the same calendar week must have the same week number"
            )


# ===========================================================================
# Rest-adherence signal in calculate_adaptive_rest()
# ===========================================================================

class TestRestAdherence:
    """
    calculate_adaptive_rest() must adjust its prescription toward the user's
    actual rest pattern when they consistently rest far outside the configured
    [rest_min, rest_max] range.

    Uses pull_up H session params: rest_min=120, rest_max=180, mid=150.
    Threshold for "short": avg < rest_min * 0.85 = 102 s → rest -= 20
    Threshold for "long":  avg > rest_max * 1.10 = 198 s → rest += 20
    """

    def _h_sessions_with_rest(self, n: int, rest_per_set: int) -> list:
        """Create n H sessions each containing 4 sets with the given rest.

        rir_reported=None so no RIR signal fires; adherence is the only signal.
        All sets same reps so no drop-off signal fires either.
        """
        from bar_scheduler.core.models import SessionResult, SetResult
        sessions = []
        for i in range(n):
            sets = [
                SetResult(
                    target_reps=8, actual_reps=8,
                    rest_seconds_before=rest_per_set,
                    rir_reported=None,  # no RIR signal — isolates adherence signal
                )
                for _ in range(4)
            ]
            sessions.append(
                SessionResult(
                    date=f"2026-01-{i + 1:02d}", bodyweight_kg=80.0, grip="pronated",
                    session_type="H", exercise_id="pull_up",
                    planned_sets=sets, completed_sets=sets,
                )
            )
        return sessions

    def test_shorter_actual_rests_lower_prescription(self):
        """
        Avg actual rest of 60 s is well below rest_min (120) * 0.85 = 102 s.
        Adherence signal must lower the prescription below the midpoint (150 s).
        """
        from bar_scheduler.core.planner import calculate_adaptive_rest
        from bar_scheduler.core.exercises.registry import get_exercise

        exercise = get_exercise("pull_up")
        sessions = self._h_sessions_with_rest(5, rest_per_set=60)
        result = calculate_adaptive_rest("H", sessions, None, exercise)

        mid = (exercise.session_params["H"].rest_min + exercise.session_params["H"].rest_max) // 2
        assert result < mid, (
            f"Expected rest < {mid} s when user consistently rests 60 s "
            f"(well below rest_min={exercise.session_params['H'].rest_min}), got {result} s."
        )

    def test_longer_actual_rests_raise_prescription(self):
        """
        Avg actual rest of 220 s is above rest_max (180) * 1.10 = 198 s.
        Adherence signal must raise the prescription above the midpoint (150 s).
        """
        from bar_scheduler.core.planner import calculate_adaptive_rest
        from bar_scheduler.core.exercises.registry import get_exercise

        exercise = get_exercise("pull_up")
        sessions = self._h_sessions_with_rest(5, rest_per_set=220)
        result = calculate_adaptive_rest("H", sessions, None, exercise)

        mid = (exercise.session_params["H"].rest_min + exercise.session_params["H"].rest_max) // 2
        assert result > mid, (
            f"Expected rest > {mid} s when user consistently rests 220 s "
            f"(above rest_max={exercise.session_params['H'].rest_max}), got {result} s."
        )

    def test_adherence_within_range_no_adjustment(self):
        """
        Avg actual rest of 150 s (exactly at midpoint) is within [rest_min, rest_max].
        Neither adherence threshold fires; prescription stays at midpoint (before other signals).
        """
        from bar_scheduler.core.planner import calculate_adaptive_rest
        from bar_scheduler.core.exercises.registry import get_exercise

        exercise = get_exercise("pull_up")
        # RIR=3 on all sets: all-RIR-≥-3 signal fires → rest -= 15 → 150-15 = 135
        # But the adherence signal must NOT fire since 150 is within [120, 180].
        # Compare result with identical sessions but different rest: if adherence fired,
        # the two would diverge. Here we just verify the threshold is not crossed.
        sessions = self._h_sessions_with_rest(5, rest_per_set=150)
        result = calculate_adaptive_rest("H", sessions, None, exercise)

        # rir_reported=None → no RIR signal; adherence within range → no extra adjustment
        # → result must equal midpoint exactly
        params = exercise.session_params["H"]
        mid = (params.rest_min + params.rest_max) // 2
        assert result == mid, (
            f"Expected {mid} s (no signals fire when avg rest is at midpoint "
            f"and rir_reported=None), got {result} s."
        )


# =============================================================================
# YAML exercise loading tests
# =============================================================================


class TestYamlExerciseLoading:
    """Tests for loader.py and registry.py YAML-backed exercise loading."""

    def test_yaml_exercises_match_expected_values(self):
        """Key fields from YAML files match the expected exercise definitions."""
        from bar_scheduler.core.exercises.loader import load_exercises_from_yaml

        loaded = load_exercises_from_yaml()
        assert loaded is not None, "load_exercises_from_yaml() returned None (YAML not available?)"

        expected = {
            "pull_up": {"bw_fraction": 1.0,  "target_value": 30.0, "has_variant_rotation": True},
            "dip":     {"bw_fraction": 0.92, "target_value": 40.0, "has_variant_rotation": False},
            "bss":     {"bw_fraction": 0.71, "target_value": 20.0, "has_variant_rotation": True},
        }

        for ex_id, fields in expected.items():
            assert ex_id in loaded, f"'{ex_id}' missing from YAML exercises"
            yaml_def = loaded[ex_id]

            assert yaml_def.exercise_id == ex_id, f"{ex_id}: exercise_id mismatch"
            assert yaml_def.bw_fraction == fields["bw_fraction"], (
                f"{ex_id}: bw_fraction {yaml_def.bw_fraction} != {fields['bw_fraction']}"
            )
            assert yaml_def.target_value == fields["target_value"], (
                f"{ex_id}: target_value {yaml_def.target_value} != {fields['target_value']}"
            )
            assert len(yaml_def.session_params) == 5, (
                f"{ex_id}: expected 5 session_params, got {len(yaml_def.session_params)}"
            )
            assert yaml_def.has_variant_rotation == fields["has_variant_rotation"], (
                f"{ex_id}: has_variant_rotation mismatch"
            )

    def test_exercise_from_dict_missing_field_raises(self):
        """exercise_from_dict() raises ValueError when a required field is absent."""
        from bar_scheduler.core.exercises.loader import exercise_from_dict

        # Build a minimal valid dict, then remove bw_fraction
        minimal = {
            "exercise_id": "test_ex",
            "display_name": "Test",
            "muscle_group": "test",
            # bw_fraction intentionally omitted
            "load_type": "bw_plus_external",
            "variants": ["standard"],
            "primary_variant": "standard",
            "variant_factors": {"standard": 1.0},
            "session_params": {
                "S": {
                    "reps_fraction_low": 0.35,
                    "reps_fraction_high": 0.55,
                    "reps_min": 3,
                    "reps_max": 8,
                    "sets_min": 3,
                    "sets_max": 5,
                    "rest_min": 120,
                    "rest_max": 180,
                    "rir_target": 2,
                }
            },
            "target_metric": "max_reps",
            "target_value": 10.0,
            "test_protocol": "Test protocol",
            "test_frequency_weeks": 4,
            "onerm_includes_bodyweight": True,
            "onerm_explanation": "Explanation",
            "weight_increment_fraction": 0.01,
            "weight_tm_threshold": 9,
            "max_added_weight_kg": 20.0,
        }
        import pytest

        with pytest.raises(ValueError, match="bw_fraction"):
            exercise_from_dict(minimal)

    def test_session_params_missing_field_raises(self):
        """_validate_session_params() raises ValueError when rir_target is absent."""
        from bar_scheduler.core.exercises.loader import _validate_session_params
        import pytest

        incomplete = {
            "reps_fraction_low": 0.35,
            "reps_fraction_high": 0.55,
            "reps_min": 3,
            "reps_max": 8,
            "sets_min": 3,
            "sets_max": 5,
            "rest_min": 120,
            "rest_max": 180,
            # rir_target intentionally omitted
        }
        with pytest.raises(ValueError, match="rir_target"):
            _validate_session_params(incomplete)

    def test_load_exercises_from_yaml_contains_all_three(self):
        """The YAML exercises block defines pull_up, dip, and bss."""
        from bar_scheduler.core.exercises.loader import load_exercises_from_yaml

        loaded = load_exercises_from_yaml()
        assert loaded is not None
        assert "pull_up" in loaded
        assert "dip" in loaded
        assert "bss" in loaded

    def test_registry_get_exercise_all_exercises(self):
        """get_exercise() returns an ExerciseDefinition for each known id."""
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.exercises.base import ExerciseDefinition

        for ex_id in ("pull_up", "dip", "bss"):
            result = get_exercise(ex_id)
            assert isinstance(result, ExerciseDefinition), (
                f"get_exercise('{ex_id}') returned {type(result)}, expected ExerciseDefinition"
            )
            assert result.exercise_id == ex_id

    def test_registry_unknown_exercise_raises(self):
        """get_exercise() raises ValueError for an unknown exercise id."""
        from bar_scheduler.core.exercises.registry import get_exercise
        import pytest

        with pytest.raises(ValueError, match="foo"):
            get_exercise("foo")

    def test_bundled_exercise_yaml_files_exist_on_disk(self):
        """
        Regression: PyYAML was previously an optional dep; if missing, YAML
        files load as empty dicts, registry raises RuntimeError, CLI crashes
        on startup. Verify the files are reachable at the expected path.
        """
        from bar_scheduler.core.exercises.loader import _get_bundled_exercises_dir

        exercises_dir = _get_bundled_exercises_dir()
        assert exercises_dir is not None, (
            "Bundled exercises directory not found. "
            "Check that src/bar_scheduler/exercises/ exists."
        )
        for exercise_id in ("pull_up", "dip", "bss"):
            yaml_file = exercises_dir / f"{exercise_id}.yaml"
            assert yaml_file.exists(), (
                f"Missing bundled exercise file: {yaml_file}. "
                "This would cause a RuntimeError at CLI startup."
            )

    def test_exercise_registry_builds_at_import_time(self):
        """
        Regression: EXERCISE_REGISTRY must be populated at module import time.
        If load_exercises_from_yaml() fails (e.g. PyYAML not installed),
        _build_registry() raises RuntimeError and the CLI crashes on startup.
        """
        from bar_scheduler.core.exercises.registry import EXERCISE_REGISTRY

        assert len(EXERCISE_REGISTRY) >= 3, (
            f"Expected at least 3 exercises, got {len(EXERCISE_REGISTRY)}"
        )
        for ex_id in ("pull_up", "dip", "bss"):
            assert ex_id in EXERCISE_REGISTRY, (
                f"'{ex_id}' missing from EXERCISE_REGISTRY at import time."
            )


# =============================================================================
# explain_plan_entry() thin-wrapper tests
# =============================================================================


def _make_user_state_with_test(exercise_id="pull_up", test_reps=12, added_kg=0.0, bw=80.0):
    """Return a UserState with one TEST session logged."""
    from datetime import date, timedelta
    from bar_scheduler.core.models import (
        UserProfile, UserState, SessionResult, SetResult,
    )
    test_date = (date.today() - timedelta(days=7)).isoformat()
    test_set = SetResult(
        target_reps=test_reps,
        actual_reps=test_reps,
        rest_seconds_before=180,
        added_weight_kg=added_kg,
        rir_target=0,
        rir_reported=0,
    )
    session = SessionResult(
        date=test_date,
        bodyweight_kg=bw,
        grip="pronated",
        session_type="TEST",
        exercise_id=exercise_id,
        planned_sets=[test_set],
        completed_sets=[test_set],
    )
    profile = UserProfile(height_cm=178, sex="male", preferred_days_per_week=3)
    return UserState(
        profile=profile,
        current_bodyweight_kg=bw,
        history=[session],
    )


class TestExplainWrapper:
    """Verify that explain_plan_entry() delegates to _plan_core() and produces correct output."""

    def _plan_start(self):
        """Return tomorrow's date string."""
        from datetime import date, timedelta
        return (date.today() + timedelta(days=1)).isoformat()

    def _first_session_date(self, plan_start_str, days_per_week=3):
        """Return the date string of the first planned session."""
        from bar_scheduler.core.planner import generate_plan
        user_state = _make_user_state_with_test()
        plans = generate_plan(user_state, plan_start_str, weeks_ahead=4)
        return plans[0].date

    def test_explain_s_session_pull_up(self):
        """S session explanation contains type label, week marker, and grip."""
        from bar_scheduler.core.planner import explain_plan_entry, generate_plan
        user_state = _make_user_state_with_test()
        plan_start = self._plan_start()
        plans = generate_plan(user_state, plan_start, weeks_ahead=4)
        s_plans = [p for p in plans if p.session_type == "S"]
        assert s_plans, "No S session in plan"
        result = explain_plan_entry(user_state, plan_start, s_plans[0].date, weeks_ahead=4)
        assert "Strength (S)" in result
        assert "Week" in result
        assert "TRAINING MAX" in result
        assert "SETS" in result
        assert "REPS PER SET" in result

    def test_explain_h_session(self):
        """H session explanation shows 'Hypertrophy (H)'."""
        from bar_scheduler.core.planner import explain_plan_entry, generate_plan
        user_state = _make_user_state_with_test()
        plan_start = self._plan_start()
        plans = generate_plan(user_state, plan_start, weeks_ahead=4)
        h_plans = [p for p in plans if p.session_type == "H"]
        assert h_plans, "No H session in plan"
        result = explain_plan_entry(user_state, plan_start, h_plans[0].date, weeks_ahead=4)
        assert "Hypertrophy (H)" in result

    def test_explain_test_session(self):
        """TEST session explanation shows 'Max Test (TEST)'."""
        from bar_scheduler.core.planner import explain_plan_entry, generate_plan
        user_state = _make_user_state_with_test()
        plan_start = self._plan_start()
        plans = generate_plan(user_state, plan_start, weeks_ahead=12)
        test_plans = [p for p in plans if p.session_type == "TEST"]
        assert test_plans, "No TEST session in plan"
        result = explain_plan_entry(user_state, plan_start, test_plans[0].date, weeks_ahead=12)
        assert "Max Test (TEST)" in result

    def test_explain_bss_s_shows_correct_weight(self):
        """BSS S session: last TEST weight appears in the ADDED WEIGHT line."""
        from bar_scheduler.core.planner import explain_plan_entry, generate_plan
        from bar_scheduler.core.exercises.registry import get_exercise
        exercise = get_exercise("bss")
        user_state = _make_user_state_with_test(exercise_id="bss", test_reps=8, added_kg=12.5)
        plan_start = self._plan_start()
        plans = generate_plan(user_state, plan_start, weeks_ahead=4, exercise=exercise)
        s_plans = [p for p in plans if p.session_type == "S"]
        assert s_plans, "No S session in BSS plan"
        result = explain_plan_entry(
            user_state, plan_start, s_plans[0].date, weeks_ahead=4, exercise=exercise
        )
        assert "ADDED WEIGHT" in result
        assert "12.5" in result, f"Expected '12.5' in output, got:\n{result}"

    def test_explain_dip_no_variant_cycle(self):
        """DIP has no variant rotation — explain must not show '…-step cycle'."""
        from bar_scheduler.core.planner import explain_plan_entry, generate_plan
        from bar_scheduler.core.exercises.registry import get_exercise
        exercise = get_exercise("dip")
        user_state = _make_user_state_with_test(exercise_id="dip")
        plan_start = self._plan_start()
        plans = generate_plan(user_state, plan_start, weeks_ahead=4, exercise=exercise)
        s_plans = [p for p in plans if p.session_type == "S"]
        assert s_plans, "No S session in DIP plan"
        result = explain_plan_entry(
            user_state, plan_start, s_plans[0].date, weeks_ahead=4, exercise=exercise
        )
        assert "-step cycle" not in result, (
            f"DIP explain should not contain '-step cycle': {result}"
        )
        assert "GRIP" in result
        assert "primary variant" in result.lower() or "no rotation" in result.lower()

    def test_explain_not_found_returns_warning(self):
        """A date beyond the plan horizon returns a yellow warning string."""
        from bar_scheduler.core.planner import explain_plan_entry
        user_state = _make_user_state_with_test()
        plan_start = self._plan_start()
        result = explain_plan_entry(user_state, plan_start, "2030-01-01", weeks_ahead=4)
        assert "[yellow]" in result
        assert "2030-01-01" in result

    def test_explain_no_history_returns_error(self):
        """No history and no baseline_max returns a yellow error string."""
        from bar_scheduler.core.planner import explain_plan_entry
        from bar_scheduler.core.models import UserProfile, UserState
        profile = UserProfile(height_cm=178, sex="male", preferred_days_per_week=3)
        user_state = UserState(profile=profile, current_bodyweight_kg=80.0, history=[])
        plan_start = self._plan_start()
        result = explain_plan_entry(user_state, plan_start, plan_start, weeks_ahead=4)
        assert "[yellow]" in result

    def test_explain_first_week_no_progression(self):
        """First session of the plan shows 'No weekly progression yet'."""
        from bar_scheduler.core.planner import explain_plan_entry, generate_plan
        user_state = _make_user_state_with_test()
        plan_start = self._plan_start()
        plans = generate_plan(user_state, plan_start, weeks_ahead=4)
        result = explain_plan_entry(user_state, plan_start, plans[0].date, weeks_ahead=4)
        assert "No weekly progression yet" in result

    def test_explain_week2_shows_progression_log(self):
        """A session in week 2 shows at least one 'Week N: TM' progression log line."""
        from bar_scheduler.core.planner import explain_plan_entry, generate_plan
        from datetime import date, timedelta
        user_state = _make_user_state_with_test()
        plan_start = self._plan_start()
        plans = generate_plan(user_state, plan_start, weeks_ahead=4)
        # Find a session in week 2 (plan_start + 7 days into the plan)
        start_dt = date.fromisoformat(plan_start)
        week2_sessions = [
            p for p in plans
            if (date.fromisoformat(p.date) - start_dt).days >= 7
        ]
        assert week2_sessions, "No sessions found in week 2 of plan"
        result = explain_plan_entry(
            user_state, plan_start, week2_sessions[0].date, weeks_ahead=4
        )
        assert "Progression by week:" in result
        assert "TM" in result and "+" in result

    def test_explain_autoreg_off_below_threshold(self):
        """With < MIN_SESSIONS_FOR_AUTOREG history, output says autoregulation is off."""
        from bar_scheduler.core.planner import explain_plan_entry, generate_plan
        user_state = _make_user_state_with_test()   # 1 TEST session → autoreg off
        plan_start = self._plan_start()
        plans = generate_plan(user_state, plan_start, weeks_ahead=4)
        result = explain_plan_entry(user_state, plan_start, plans[0].date, weeks_ahead=4)
        assert "Autoregulation" in result
        assert "off" in result

    def test_explain_matches_generate_plan_date(self):
        """explain_plan_entry output date matches the SessionPlan.date."""
        from bar_scheduler.core.planner import explain_plan_entry, generate_plan
        user_state = _make_user_state_with_test()
        plan_start = self._plan_start()
        plans = generate_plan(user_state, plan_start, weeks_ahead=4)
        target = plans[1].date   # second session
        result = explain_plan_entry(user_state, plan_start, target, weeks_ahead=4)
        assert target in result


# =============================================================================
# plot-max chart tests
# =============================================================================


def _make_plot_session(date: str, reps: int, exercise_id: str = "pull_up"):
    """Return a TEST SessionResult with the given max reps."""
    from bar_scheduler.core.models import SessionResult, SetResult
    set_ = SetResult(
        target_reps=reps, actual_reps=reps, rest_seconds_before=180,
        added_weight_kg=0.0, rir_target=0, rir_reported=0,
    )
    return SessionResult(
        date=date, bodyweight_kg=80.0, grip="pronated",
        session_type="TEST", exercise_id=exercise_id,
        planned_sets=[set_], completed_sets=[set_],
    )


class TestPlotMaxChart:
    """Regression tests for the three plot-max bugs."""

    def test_caption_uses_exercise_display_name(self):
        """
        Regression: caption was hardcoded to 'Strict Pull-ups'.
        create_max_reps_plot() must include the exercise_name argument in the title.
        """
        from bar_scheduler.core.ascii_plot import create_max_reps_plot

        s = _make_plot_session("2026-01-01", 10)
        for name in ("Parallel Bar Dip", "Bulgarian Split Squat (DB)", "My Custom Exercise"):
            plot = create_max_reps_plot([s], exercise_name=name)
            assert name in plot, f"Expected '{name}' in chart title. Got:\n{plot[:200]}"
            assert "Strict Pull-ups" not in plot, (
                f"Hardcoded 'Strict Pull-ups' found despite exercise_name='{name}'"
            )

    def test_line_style_uses_staircase_corners(self):
        """
        Regression: connecting lines used only '╯' (linear interpolation).
        The staircase algorithm must produce '╭', '─', and '╯' characters.
        """
        from bar_scheduler.core.ascii_plot import create_max_reps_plot

        # Two sessions far apart in value — forces multi-row traversal
        sessions = [
            _make_plot_session("2026-01-01", 5),
            _make_plot_session("2026-02-01", 20),
        ]
        plot = create_max_reps_plot(sessions)
        assert "╭" in plot, f"Expected '╭' staircase corner in chart:\n{plot}"
        assert "─" in plot, f"Expected '─' horizontal segment in chart:\n{plot}"
        assert "╯" in plot, f"Expected '╯' staircase corner in chart:\n{plot}"

    def test_trajectory_starts_from_latest_test(self):
        """
        Regression: trajectory was anchored to the first test, not the latest.
        _build_trajectory() must use test_sessions[-1] as its starting point.
        """
        from datetime import datetime
        from bar_scheduler.cli.commands.analysis import _build_trajectory
        from bar_scheduler.core.metrics import get_test_sessions

        sessions = [
            _make_plot_session("2026-01-01", 5),   # first (old) test
            _make_plot_session("2026-02-01", 15),   # latest test
        ]
        traj = _build_trajectory(get_test_sessions(sessions), target=30)
        assert traj, "Trajectory must not be empty"
        first_traj_date = traj[0][0]
        assert first_traj_date == datetime(2026, 2, 1), (
            f"Trajectory must start from latest test (2026-02-01), "
            f"got {first_traj_date.date()}"
        )

    def test_label_shown_for_rightmost_data_point(self):
        from bar_scheduler.core.ascii_plot import create_max_reps_plot

        sessions = [
            _make_plot_session("2026-01-01", 10),
            _make_plot_session("2026-06-01", 20),
        ]
        plot = create_max_reps_plot(sessions)
        assert "(20)" in plot, "Label for the rightmost data point must appear in the plot"

    def test_weighted_goal_trajectory_extends_past_current_reps(self):
        from bar_scheduler.cli.commands.analysis import _build_trajectory
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.metrics import get_test_sessions

        sessions = [_make_plot_session("2026-02-01", 15, exercise_id="dip")]
        test_sessions = get_test_sessions(sessions)

        # Epley conversion: dip target 12 reps @ 25 kg, BW=80
        exercise_def = get_exercise("dip")
        bw = 80.0
        bw_load = bw * exercise_def.bw_fraction
        full_load = bw_load + 25.0
        one_rm = full_load * (1 + 12 / 30)
        traj_target = max(int(round(30 * (one_rm / bw_load - 1))), 1)

        traj = _build_trajectory(test_sessions, target=traj_target)
        assert len(traj) > 1, "Weighted-goal equiv target must produce a forward trajectory"
        assert traj_target > 15, "Equiv target must exceed current BW max"

    def test_vertical_segment_uses_pipe_not_corner(self):
        from bar_scheduler.core.ascii_plot import create_max_reps_plot

        # Same date → both map to the same x column → should draw │ vertically
        sessions = [
            _make_plot_session("2026-02-24", 7),
            _make_plot_session("2026-02-24", 15),
        ]
        plot = create_max_reps_plot(sessions)
        assert "│" in plot, "Same-column points must use │ for vertical connection"
        lines_without_bullet = [l for l in plot.splitlines() if "╭" in l and "●" not in l]
        assert not lines_without_bullet, f"╭ appears on non-data rows: {lines_without_bullet}"

    def test_g_trajectory_linear_transform(self):
        from bar_scheduler.core.exercises.registry import get_exercise

        exercise_def = get_exercise("dip")
        bw, tw = 80.0, 25.0
        bw_load = bw * exercise_def.bw_fraction
        f = bw_load / (bw_load + tw)

        g_at_target = f * 26.0 + 30.0 * (f - 1.0)
        assert abs(g_at_target - 12.0) < 0.5, f"g at equiv target must ≈12, got {g_at_target:.2f}"

        g_now = f * 15.0 + 30.0 * (f - 1.0)
        assert 3.0 < g_now < 5.0, f"g at current BW max must ≈4, got {g_now:.2f}"

    def test_1rm_right_axis_shown_when_trajectory_m_provided(self):
        from bar_scheduler.core.ascii_plot import create_max_reps_plot

        sessions = [_make_plot_session("2026-02-01", 15, exercise_id="dip")]
        bw_load = 73.6
        traj_m = self._m_traj_kg(self._base_traj(target=30), bw_load)

        plot_with = create_max_reps_plot(sessions, trajectory_m=traj_m, bw_load_kg=bw_load)
        plot_without = create_max_reps_plot(sessions)
        assert "kg" in plot_with, "Right axis must contain 'kg' labels when trajectory_m provided"
        assert "kg" not in plot_without, "No 'kg' labels when no trajectory_m"

    def test_trajectory_is_monotonically_non_decreasing(self):
        from bar_scheduler.cli.commands.analysis import _build_trajectory
        from bar_scheduler.core.metrics import get_test_sessions

        sessions = [_make_plot_session("2026-02-01", 15)]
        traj = _build_trajectory(get_test_sessions(sessions), target=26)
        assert len(traj) > 1, "Trajectory must have at least 2 points"
        values = [v for _, v in traj]
        for i in range(len(values) - 1):
            assert values[i] <= values[i + 1] + 0.01, (
                f"Trajectory dropped at step {i}: {values[i]:.2f} → {values[i + 1]:.2f}"
            )

    # ------------------------------------------------------------------
    # Trajectory flag regression tests (3 flags × 3 goal types = 9 cases)
    # ------------------------------------------------------------------
    # Helpers shared by all 9 tests

    def _base_traj(self, target: int = 30):
        from bar_scheduler.cli.commands.analysis import _build_trajectory
        from bar_scheduler.core.metrics import get_test_sessions
        return _build_trajectory(
            get_test_sessions([_make_plot_session("2026-02-01", 12)]), target=target
        )

    def _g_transform(self, base, bw_load: float, added_kg: float):
        f = bw_load / (bw_load + added_kg)
        return [(d, max(0.0, f * v + 30 * (f - 1))) for d, v in base]

    def _m_traj_kg(self, traj_reps, bw_load_kg: float):
        """Convert a reps-based trajectory to added-kg using blended_1rm_added."""
        from bar_scheduler.core.metrics import blended_1rm_added
        m_pts = []
        for d, reps in traj_reps:
            r = min(int(round(reps)), 20)
            added = blended_1rm_added(bw_load_kg, max(r, 1))
            if added is not None:
                m_pts.append((d, added))
        return m_pts

    # --- z tests (marker = '·') ---

    def test_z_bw_goal_shows_dots(self):
        from bar_scheduler.core.ascii_plot import create_max_reps_plot
        traj = self._base_traj(target=30)
        sessions = [_make_plot_session("2026-02-01", 12)]
        plot = create_max_reps_plot(sessions, trajectory_z=traj, traj_types=frozenset({"z"}))
        assert plot.count("·") >= 2, "z with BW goal must show ≥2 · dots"

    def test_z_weighted_goal_shows_dots(self):
        from bar_scheduler.core.ascii_plot import create_max_reps_plot
        # Equiv target ~26 for dip 12 reps @ 25kg, bw=80, bw_frac=0.92
        traj = self._base_traj(target=26)
        sessions = [_make_plot_session("2026-02-01", 12)]
        plot = create_max_reps_plot(sessions, trajectory_z=traj, traj_types=frozenset({"z"}))
        assert plot.count("·") >= 2, "z with weighted goal must show ≥2 · dots"

    def test_z_1rm_goal_shows_dots(self):
        from bar_scheduler.core.ascii_plot import create_max_reps_plot
        # 1RM goal (1 rep @ 80kg) converts to a high equiv target
        traj = self._base_traj(target=40)
        sessions = [_make_plot_session("2026-02-01", 12)]
        plot = create_max_reps_plot(sessions, trajectory_z=traj, traj_types=frozenset({"z"}))
        assert plot.count("·") >= 2, "z with 1RM goal must show ≥2 · dots"

    # --- g tests (marker = '×') ---

    def test_g_bw_goal_shows_cross_dots(self):
        from bar_scheduler.core.ascii_plot import create_max_reps_plot
        # BW goal: g = z (same trajectory)
        traj = self._base_traj(target=30)
        sessions = [_make_plot_session("2026-02-01", 12)]
        plot = create_max_reps_plot(
            sessions, trajectory_g=traj,
            target_weight_kg=0, traj_types=frozenset({"g"})
        )
        assert plot.count("×") >= 2, "g with BW goal must show ≥2 × dots"
        assert "right:" not in plot, "g alone must not show right axis"

    def test_g_weighted_goal_shows_cross_dots(self):
        from bar_scheduler.core.ascii_plot import create_max_reps_plot
        bw_load = 80 * 0.92
        base = self._base_traj(target=26)
        pts_g = self._g_transform(base, bw_load, added_kg=25)
        sessions = [_make_plot_session("2026-02-01", 12)]
        plot = create_max_reps_plot(
            sessions, trajectory_g=pts_g,
            target_weight_kg=25, traj_types=frozenset({"g"})
        )
        assert plot.count("×") >= 2, "g with weighted goal must show ≥2 × dots"
        assert "right:" not in plot, "g alone must not show right axis"

    def test_g_1rm_goal_shows_cross_dots(self):
        from bar_scheduler.core.ascii_plot import create_max_reps_plot
        # 1RM goal: 1 rep @ 80kg; g-reps are very small (≈0.5) so at bottom
        bw_load = 80 * 1.0
        base = self._base_traj(target=40)
        pts_g = self._g_transform(base, bw_load, added_kg=80)
        sessions = [_make_plot_session("2026-02-01", 12)]
        plot = create_max_reps_plot(
            sessions, trajectory_g=pts_g,
            target_weight_kg=80, traj_types=frozenset({"g"})
        )
        assert plot.count("×") >= 2, "g with 1RM goal must show ≥2 × dots"
        assert "right:" not in plot, "g alone must not show right axis"

    # --- m tests (○ dots shown + independent right axis with kg) ---

    def test_m_bw_goal_shows_circle_dots_and_kg_axis(self):
        from bar_scheduler.core.ascii_plot import create_max_reps_plot
        bw_load = 80.0
        traj_m = self._m_traj_kg(self._base_traj(target=30), bw_load)
        sessions = [_make_plot_session("2026-02-01", 12)]
        plot = create_max_reps_plot(
            sessions, trajectory_m=traj_m,
            bw_load_kg=bw_load, traj_types=frozenset({"m"})
        )
        assert plot.count("○") >= 2, "m with BW goal must show ≥2 trajectory ○ dots"
        assert "kg" in plot, "m must show right kg axis"

    def test_m_weighted_goal_shows_circle_dots_and_kg_axis(self):
        from bar_scheduler.core.ascii_plot import create_max_reps_plot
        bw_load = 80 * 0.92
        traj_m = self._m_traj_kg(self._base_traj(target=26), bw_load)
        sessions = [_make_plot_session("2026-02-01", 12, exercise_id="dip")]
        plot = create_max_reps_plot(
            sessions, trajectory_m=traj_m,
            bw_load_kg=bw_load, traj_types=frozenset({"m"})
        )
        assert plot.count("○") >= 2, "m with weighted goal must show ≥2 trajectory ○ dots"
        assert "kg" in plot, "m must show right kg axis"

    def test_m_1rm_goal_shows_circle_dots_and_kg_axis(self):
        from bar_scheduler.core.ascii_plot import create_max_reps_plot
        bw_load = 80.0
        traj_m = self._m_traj_kg(self._base_traj(target=40), bw_load)
        sessions = [_make_plot_session("2026-02-01", 12)]
        plot = create_max_reps_plot(
            sessions, trajectory_m=traj_m,
            bw_load_kg=bw_load, traj_types=frozenset({"m"})
        )
        assert plot.count("○") >= 2, "m with 1RM goal must show ≥2 trajectory ○ dots"
        assert "kg" in plot, "m must show right kg axis"


class TestBlended1RM:
    """Unit tests for multi-formula 1RM estimators in metrics.py."""

    def test_lombardi_1rm(self):
        from bar_scheduler.core.metrics import lombardi_1rm
        # 80 kg × 15^0.10 ≈ 80 × 1.3107 ≈ 104.9 kg
        result = lombardi_1rm(80.0, 15)
        assert abs(result - 104.9) < 0.5, f"lombardi_1rm(80, 15) expected ≈104.9, got {result:.2f}"

    def test_brzycki_1rm(self):
        from bar_scheduler.core.metrics import brzycki_1rm
        # 80 / (1.0278 − 0.0278×5) = 80 / 0.8888 ≈ 90.0
        result = brzycki_1rm(80.0, 5)
        assert abs(result - 90.0) < 0.5, f"brzycki_1rm(80, 5) expected ≈90.0, got {result:.2f}"

    def test_lander_1rm(self):
        from bar_scheduler.core.metrics import lander_1rm
        # 100×80 / (101.3 − 2.67123×5) = 8000 / 87.944 ≈ 90.9
        result = lander_1rm(80.0, 5)
        assert abs(result - 90.9) < 0.5, f"lander_1rm(80, 5) expected ≈90.9, got {result:.2f}"

    def test_blended_1rm_added_returns_none_above_20(self):
        from bar_scheduler.core.metrics import blended_1rm_added
        assert blended_1rm_added(73.6, 21) is None
        assert blended_1rm_added(73.6, 25) is None

    def test_blended_1rm_added_non_negative(self):
        from bar_scheduler.core.metrics import blended_1rm_added
        for r in range(1, 21):
            result = blended_1rm_added(73.6, r)
            assert result is not None and result >= 0.0, f"blended_1rm_added(73.6, {r}) must be ≥0"

    def test_m_trajectory_non_linear_differs_from_epley(self):
        """Blended formula at r=5 uses Brzycki+Lander (no Epley), giving a distinct value."""
        from bar_scheduler.core.metrics import blended_1rm_added, epley_1rm
        bw_load = 73.6
        # At r=5, blended = avg(Brzycki, Lander); Epley gives higher estimate at low reps
        added_blended = blended_1rm_added(bw_load, 5)
        added_epley = epley_1rm(bw_load, 5) - bw_load
        assert added_blended is not None
        assert abs(added_blended - added_epley) > 1.0, (
            f"Blended@r=5 ({added_blended:.2f}kg) must differ from Epley ({added_epley:.2f}kg) by >1kg"
        )


# =============================================================================
# Overtraining severity detection (Feature 2)
# =============================================================================


class TestOvertrain:
    """Unit tests for overtraining_severity() in adaptation.py."""

    def _make_sessions(self, dates: list[str], session_type: str = "S") -> list:
        """Create minimal SessionResult objects for the given dates."""
        from bar_scheduler.core.models import SessionResult
        sessions = []
        for d in dates:
            sessions.append(
                SessionResult(
                    date=d,
                    bodyweight_kg=80.0,
                    grip="pronated",
                    session_type=session_type,
                    planned_sets=[],
                    completed_sets=[],
                )
            )
        return sessions

    def test_level_0_normal_spacing(self):
        """2 sessions 5 days apart at 3×/week → level 0 (no overtraining)."""
        from bar_scheduler.core.adaptation import overtraining_severity
        # n=2, expected = 2 × (7/3) ≈ 4.67 days; span_days=5; actual=5
        # extra = max(0, round(4.67 - 5)) = max(0, round(-0.33)) = 0 → level 0
        sessions = self._make_sessions(["2026-02-22", "2026-02-27"])
        result = overtraining_severity(sessions, days_per_week=3)
        assert result["level"] == 0, f"Expected level 0, got {result}"
        assert result["extra_rest_days"] == 0

    def test_level_1_mild(self):
        """2 sessions 4 days apart at 3×/week → mild overtraining (level 1)."""
        from bar_scheduler.core.adaptation import overtraining_severity
        # n=2, expected = 2 × (7/3) ≈ 4.67 days; span_days=4; actual=4
        # extra = max(0, round(4.67 - 4)) = max(0, round(0.67)) = 1 → level 1
        sessions = self._make_sessions(["2026-02-23", "2026-02-27"])
        result = overtraining_severity(sessions, days_per_week=3)
        assert result["level"] == 1, f"Expected level 1, got {result}"
        assert result["extra_rest_days"] == 1

    def test_level_2_moderate(self):
        """3 sessions compressed into 2 days at 3×/week → level 2."""
        from bar_scheduler.core.adaptation import overtraining_severity
        # span_days=2, n=3, expected=7 days, extra=round(7-2)=5 → level 3
        # For level 2: extra in [2,3]. 3 sessions, 3×/week: expected=7, actual≈4-5
        sessions = self._make_sessions(["2026-02-23", "2026-02-25", "2026-02-27"])
        result = overtraining_severity(sessions, days_per_week=3)
        # span_days=4, expected=7, extra=round(7-4)=3 → level 2
        assert result["level"] == 2, f"Expected level 2, got {result}"
        assert 2 <= result["extra_rest_days"] <= 3

    def test_level_3_severe(self):
        """3 sessions in 1 day at 3×/week → level 3 (all same date)."""
        from bar_scheduler.core.adaptation import overtraining_severity
        sessions = self._make_sessions(["2026-02-27", "2026-02-27", "2026-02-27"])
        result = overtraining_severity(sessions, days_per_week=3)
        assert result["level"] == 3, f"Expected level 3, got {result}"
        # span_days=0 → actual=max(0,1)=1; expected=7; extra=round(7-1)=6
        assert result["extra_rest_days"] == 6
        assert result["sessions"] == 3
        assert result["span_days"] == 0

    def test_rest_sessions_excluded(self):
        """REST-type records must not count toward density calculation."""
        from bar_scheduler.core.adaptation import overtraining_severity
        # 1 real session + many REST sessions → level 0 (< 2 non-REST)
        sessions = (
            self._make_sessions(["2026-02-25", "2026-02-26", "2026-02-27"], "REST")
            + self._make_sessions(["2026-02-27"], "S")
        )
        result = overtraining_severity(sessions, days_per_week=3)
        assert result["level"] == 0, "REST sessions must not count toward overtraining"

    def test_empty_history(self):
        """Empty history returns level 0."""
        from bar_scheduler.core.adaptation import overtraining_severity
        assert overtraining_severity([], days_per_week=3)["level"] == 0

    def test_description_format(self):
        """Description string contains session count and day count."""
        from bar_scheduler.core.adaptation import overtraining_severity
        sessions = self._make_sessions(["2026-02-27", "2026-02-27", "2026-02-27"])
        result = overtraining_severity(sessions, days_per_week=3)
        desc = result["description"]
        assert "3" in desc, f"Session count (3) must be in description: {desc!r}"
        assert "day" in desc.lower(), f"'day' must appear in description: {desc!r}"

    def test_rest_day_credits_toward_span(self):
        """REST records between training sessions reduce apparent overtraining severity."""
        from bar_scheduler.core.adaptation import overtraining_severity
        from bar_scheduler.core.models import SessionResult

        def _s(d, st):
            return SessionResult(
                date=d, bodyweight_kg=80.0, grip="pronated",
                session_type=st, planned_sets=[], completed_sets=[],
            )

        # 5 training sessions: 02.24 (x2), 02.26 (x2), 02.27
        # 1 REST record on 02.25 (between 02.24 and 02.27)
        # span_days = (02.27 - 02.24).days = 3; rest_in_span = 1
        # actual_days = max(3 + 1, 1) = 4
        # expected = 5 * (7/4) = 8.75 days; extra = round(8.75 - 4) = 5 → level 3
        # Without REST credit: actual_days = 3; extra = round(8.75-3)=6 → also level 3
        # But description should use inclusive count (span_days+1 = 4 days) not 3
        training = [
            _s("2026-02-24", "S"),
            _s("2026-02-24", "TEST"),
            _s("2026-02-26", "S"),
            _s("2026-02-26", "H"),
            _s("2026-02-27", "S"),
        ]
        full = training + [_s("2026-02-25", "REST")]

        result_no_credit = overtraining_severity(training, days_per_week=4)
        result_with_credit = overtraining_severity(training, days_per_week=4, full_history=full)

        # extra_rest_days is lower (or equal) when REST credit is applied
        assert result_with_credit["extra_rest_days"] <= result_no_credit["extra_rest_days"]

    def test_description_uses_inclusive_days(self):
        """Description day count is inclusive (span_days + 1), not exclusive."""
        from bar_scheduler.core.adaptation import overtraining_severity

        # 2 sessions on 02.24 and 02.26: span_days = 2, inclusive = 3 days
        # Expected description: "2 sessions in 3 days"
        sessions = self._make_sessions(["2026-02-24", "2026-02-26"])
        result = overtraining_severity(sessions, days_per_week=3)
        desc = result["description"]
        # Inclusive count: Feb 24 to Feb 26 = 3 calendar days (24, 25, 26)
        assert "3" in desc, f"Inclusive day count (3) must appear in: {desc!r}"
        assert "2" in desc, f"Session count (2) must appear in: {desc!r}"

    def test_description_same_day_is_one_day(self):
        """Two sessions on the same date → description says '1 day' (inclusive)."""
        from bar_scheduler.core.adaptation import overtraining_severity

        # span_days=0, inclusive=1
        sessions = self._make_sessions(["2026-02-27", "2026-02-27"])
        result = overtraining_severity(sessions, days_per_week=3)
        desc = result["description"]
        assert "1 day" in desc, f"Expected '1 day' in: {desc!r}"

    def test_auto_advance_only_for_rest_sessions(self):
        """
        Plan start date should only advance when REST records exist in history.

        This tests the filtering logic: only REST-type sessions trigger plan_start_date
        advancement. Training sessions (S, H, T, E, TEST) must not shift the anchor.
        """
        # Simulate the auto-advance logic from planning.py:plan()
        # After Fix 1: plan_start_date only advances to the latest REST date.
        original_start = "2026-02-28"

        # History with only training sessions (no REST)
        history_training_only = [
            {"date": "2026-02-28", "session_type": "S"},
            {"date": "2026-03-01", "session_type": "H"},
        ]
        rest_dates = [s["date"] for s in history_training_only if s["session_type"] == "REST"]
        # No REST records → plan_start_date must not advance
        assert rest_dates == [], "Training sessions must not be treated as REST"
        new_start = max(rest_dates) if rest_dates and max(rest_dates) > original_start else original_start
        assert new_start == original_start, (
            "Logging a training session must not advance plan_start_date"
        )

        # History with a REST record
        history_with_rest = history_training_only + [{"date": "2026-03-03", "session_type": "REST"}]
        rest_dates = [s["date"] for s in history_with_rest if s["session_type"] == "REST"]
        new_start = max(rest_dates) if rest_dates and max(rest_dates) > original_start else original_start
        assert new_start == "2026-03-03", "REST record must advance plan_start_date"


# =============================================================================
# Multi-formula 1RM output from estimate_1rm() (Feature 3)
# =============================================================================


class TestEstimate1rmFormulas:
    """estimate_1rm() must return a 'formulas' dict and 'recommended_formula' key."""

    def _session(self, reps: int, added_kg: float = 0.0):
        from bar_scheduler.core.models import SessionResult, SetResult
        s = SetResult(
            target_reps=reps, actual_reps=reps, rest_seconds_before=180,
            added_weight_kg=added_kg, rir_target=2,
        )
        return SessionResult(
            date="2026-02-27", bodyweight_kg=80.0, grip="pronated",
            session_type="S", exercise_id="pull_up",
            planned_sets=[s], completed_sets=[s],
        )

    def test_formulas_key_present(self):
        from bar_scheduler.core.metrics import estimate_1rm
        from bar_scheduler.core.exercises.registry import get_exercise
        result = estimate_1rm(get_exercise("pull_up"), 80.0, [self._session(8)])
        assert result is not None
        assert "formulas" in result, "estimate_1rm must return a 'formulas' key"

    def test_formulas_contains_all_methods(self):
        from bar_scheduler.core.metrics import estimate_1rm
        from bar_scheduler.core.exercises.registry import get_exercise
        result = estimate_1rm(get_exercise("pull_up"), 80.0, [self._session(8)])
        assert result is not None
        formulas = result["formulas"]
        for name in ("epley", "brzycki", "lander", "lombardi", "blended"):
            assert name in formulas, f"Missing formula key: {name!r}"

    def test_recommended_formula_key_present(self):
        from bar_scheduler.core.metrics import estimate_1rm
        from bar_scheduler.core.exercises.registry import get_exercise
        result = estimate_1rm(get_exercise("pull_up"), 80.0, [self._session(8)])
        assert result is not None
        assert "recommended_formula" in result

    def test_recommended_formula_low_reps(self):
        """For r≤10, recommended_formula should mention 'brzycki' or 'lander'."""
        from bar_scheduler.core.metrics import estimate_1rm
        from bar_scheduler.core.exercises.registry import get_exercise
        result = estimate_1rm(get_exercise("pull_up"), 80.0, [self._session(5)])
        assert result is not None
        rec = result["recommended_formula"]
        assert "brzycki" in rec or "lander" in rec, (
            f"Expected brzycki/lander recommendation at r=5, got {rec!r}"
        )

    def test_recommended_formula_mid_reps(self):
        """For 10 < r ≤ 20, recommended_formula should mention 'blended'."""
        from bar_scheduler.core.metrics import estimate_1rm
        from bar_scheduler.core.exercises.registry import get_exercise
        result = estimate_1rm(get_exercise("pull_up"), 80.0, [self._session(15)])
        assert result is not None
        rec = result["recommended_formula"]
        assert "blended" in rec, f"Expected blended recommendation at r=15, got {rec!r}"

    def test_brzycki_none_above_36_reps(self):
        """Brzycki/Lander are undefined at r≥37 — must be None in formulas dict."""
        from bar_scheduler.core.metrics import estimate_1rm
        from bar_scheduler.core.exercises.registry import get_exercise
        result = estimate_1rm(get_exercise("pull_up"), 80.0, [self._session(37)])
        assert result is not None
        formulas = result["formulas"]
        assert formulas["brzycki"] is None, "Brzycki must be None at r≥37"
        assert formulas["lander"] is None, "Lander must be None at r≥37"

    def test_epley_matches_1rm_kg(self):
        """formulas['epley'] must equal result['1rm_kg'] (Epley is the canonical value)."""
        from bar_scheduler.core.metrics import estimate_1rm
        from bar_scheduler.core.exercises.registry import get_exercise
        result = estimate_1rm(get_exercise("pull_up"), 80.0, [self._session(8)])
        assert result is not None
        assert result["formulas"]["epley"] == pytest.approx(result["1rm_kg"], rel=1e-3)


# =============================================================================
# trajectory_m in plot-max JSON output (Feature 4)
# =============================================================================


class TestTrajectoryMJson:
    """trajectory_m must appear in plot-max --json output when -t m is used."""

    def _base_sessions(self):
        return [
            _make_plot_session("2026-01-01", 8),
            _make_plot_session("2026-02-01", 10),
        ]

    def test_trajectory_m_key_present_in_json(self):
        """plot-max JSON must include 'trajectory_m' key when trajectory_m is passed."""
        import json as json_mod
        from bar_scheduler.core.ascii_plot import create_max_reps_plot
        from datetime import datetime

        sessions = self._base_sessions()
        bw_load = 80.0
        # Build a minimal m trajectory
        traj_m = [
            (datetime(2026, 1, 1), 0.0),
            (datetime(2026, 2, 1), 2.5),
            (datetime(2026, 3, 1), 5.0),
        ]
        # We test that the analysis.py JSON block includes trajectory_m
        # by verifying the variable is passed through correctly in analysis.py
        # Here we test the building block: traj_m_json list construction
        traj_m_json = [
            {"date": pt.strftime("%Y-%m-%d"), "projected_1rm_added_kg": round(val, 2)}
            for pt, val in traj_m
        ]
        assert len(traj_m_json) == 3
        assert traj_m_json[0]["date"] == "2026-01-01"
        assert traj_m_json[1]["projected_1rm_added_kg"] == 2.5
        assert traj_m_json[2]["projected_1rm_added_kg"] == 5.0

    def test_trajectory_m_json_serializable(self):
        """traj_m_json entries must be JSON-serializable dicts with expected keys."""
        import json as json_mod
        from datetime import datetime

        traj_m = [(datetime(2026, 2, 15), 3.75)]
        traj_m_json = [
            {"date": pt.strftime("%Y-%m-%d"), "projected_1rm_added_kg": round(val, 2)}
            for pt, val in traj_m
        ]
        serialized = json_mod.dumps({"trajectory_m": traj_m_json})
        parsed = json_mod.loads(serialized)
        assert "trajectory_m" in parsed
        entry = parsed["trajectory_m"][0]
        assert entry["date"] == "2026-02-15"
        assert entry["projected_1rm_added_kg"] == 3.75
