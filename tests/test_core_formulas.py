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
    GRIP_STRESS_FACTORS,
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

    def test_rir_3_or_higher_is_one(self):
        from bar_scheduler.core.physiology import rir_effort_multiplier
        assert rir_effort_multiplier(3) == pytest.approx(1.0)
        assert rir_effort_multiplier(5) == pytest.approx(1.0)

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

    def test_values_match_config(self):
        from bar_scheduler.core.physiology import grip_stress_multiplier
        for grip in ("pronated", "neutral", "supinated"):
            assert grip_stress_multiplier(grip) == pytest.approx(GRIP_STRESS_FACTORS[grip])

    def test_supinated_highest_stress(self):
        from bar_scheduler.core.physiology import grip_stress_multiplier
        assert grip_stress_multiplier("supinated") > grip_stress_multiplier("neutral")


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
