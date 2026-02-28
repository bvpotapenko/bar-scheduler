"""
Fitness-fatigue impulse response model (Banister model family).

Implements the two-timescale model for tracking adaptation and fatigue.
See docs/training_model.md for detailed explanation.
"""

import math
from datetime import datetime, timedelta

from .config import (
    A_RIR,
    ALPHA_MHAT,
    BETA_SIGMA,
    C_READINESS,
    GAMMA_LOAD,
    GAMMA_S,
    INITIAL_SIGMA_M,
    K_FATIGUE,
    K_FITNESS,
    REST_MIN_CLAMP,
    REST_REF_SECONDS,
    S_REST_MAX,
    TAU_FATIGUE,
    TAU_FITNESS,
)
from .metrics import (
    estimate_rir_from_fraction,
    get_test_sessions,
    session_max_reps,
    standardized_reps,
)
from .models import FitnessFatigueState, SessionResult


def rir_effort_multiplier(rir: int) -> float:
    """
    Calculate effort multiplier based on RIR.

    E_rir = clip(1 + a * (3 - rir), 0.5, 1 + a*3)

    RIR < 3 → above 1.0 (harder than neutral, more fatigue)
    RIR = 3 → 1.0 (neutral baseline)
    RIR > 3 → below 1.0 (easier than neutral, less fatigue), floor 0.5

    Lower RIR (closer to failure) = higher effort.
    Higher RIR (lots of reps left) = less fatigue accumulated.

    Args:
        rir: Repetitions in reserve

    Returns:
        Effort multiplier (0.5 to ~1.45)
    """
    return max(0.5, 1.0 + A_RIR * (3 - rir))


def rest_stress_multiplier(rest_seconds: int) -> float:
    """
    Calculate stress multiplier for short rest.

    S_rest = clip((r_ref / max(r, r_min))^gamma_s, 1, S_max)

    Shorter rest = higher stress per rep.

    Args:
        rest_seconds: Rest time before set

    Returns:
        Rest stress multiplier (1.0 to S_max)
    """
    r = max(rest_seconds, REST_MIN_CLAMP)
    raw = (REST_REF_SECONDS / r) ** GAMMA_S
    return max(1.0, min(S_REST_MAX, raw))


def load_stress_multiplier(
    bodyweight_kg: float,
    added_load_kg: float,
    reference_bodyweight_kg: float,
    bw_fraction: float = 1.0,
    assistance_kg: float = 0.0,
) -> float:
    """
    Calculate stress multiplier for effective load.

    S_load = L_rel^gamma_L
    Leff = BW × bw_fraction + added − assistance_kg
    L_rel = Leff / BW_ref

    Args:
        bodyweight_kg: Session bodyweight
        added_load_kg: Added external load (belt, dumbbells)
        reference_bodyweight_kg: Reference bodyweight
        bw_fraction: Fraction of BW that is the working load
        assistance_kg: Band/machine assistance subtracted from load (≥ 0)

    Returns:
        Load stress multiplier
    """
    effective_bw = bodyweight_kg * bw_fraction
    total = max(0.0, effective_bw + added_load_kg - assistance_kg)
    l_rel = total / reference_bodyweight_kg
    return l_rel ** GAMMA_LOAD


def grip_stress_multiplier(grip: str, variant_factors: dict[str, float] | None = None) -> float:
    """
    Get grip/variant stress multiplier.

    Args:
        grip: Grip or variant name
        variant_factors: Per-variant stress factors from ExerciseDefinition;
                         defaults to 1.0 for any grip if not provided

    Returns:
        Stress multiplier (close to 1.0)
    """
    if variant_factors is None:
        return 1.0
    return variant_factors.get(grip, 1.0)


def calculate_set_hard_reps(
    actual_reps: int,
    rir: int | None,
    estimated_max: int,
) -> float:
    """
    Calculate effective hard reps for a set.

    HR = reps * E_rir(rir)

    Args:
        actual_reps: Actual reps performed
        rir: Reported or estimated RIR
        estimated_max: Current estimated max

    Returns:
        Effective hard reps
    """
    if rir is None:
        rir = estimate_rir_from_fraction(actual_reps, estimated_max)

    effort = rir_effort_multiplier(rir)
    return actual_reps * effort


def calculate_session_training_load(
    session: SessionResult,
    estimated_max: int,
    reference_bodyweight_kg: float,
    bw_fraction: float = 1.0,
    variant_factors: dict[str, float] | None = None,
) -> float:
    """
    Calculate training load impulse w(t) for a session.

    w(t) = sum(HR_j * S_load_j * S_variant_j)

    NOTE: rest_stress_multiplier is intentionally NOT included here.
    Short rest is already credited in metrics.py via effective_reps()
    (reps* = reps / F_rest, giving higher effective reps for short rest).
    Including rest_stress would double-count fatigue accumulation.

    Args:
        session: Completed session
        estimated_max: Current estimated max reps
        reference_bodyweight_kg: Reference bodyweight
        bw_fraction: Fraction of BW that is the working load
        variant_factors: Per-variant stress multipliers from ExerciseDefinition

    Returns:
        Training load impulse
    """
    # Extract band/machine assistance from session equipment snapshot if available
    assistance_kg = 0.0
    if session.equipment_snapshot is not None:
        assistance_kg = session.equipment_snapshot.assistance_kg

    total_load = 0.0

    for set_result in session.completed_sets:
        if set_result.actual_reps is None:
            continue

        rir = set_result.rir_reported
        hr = calculate_set_hard_reps(set_result.actual_reps, rir, estimated_max)

        s_load = load_stress_multiplier(
            session.bodyweight_kg,
            set_result.added_weight_kg,
            reference_bodyweight_kg,
            bw_fraction,
            assistance_kg,
        )
        s_grip = grip_stress_multiplier(session.grip, variant_factors)

        total_load += hr * s_load * s_grip

    return total_load


def update_fitness_fatigue(
    state: FitnessFatigueState,
    training_load: float,
    days_since_last: int = 1,
) -> FitnessFatigueState:
    """
    Update fitness-fatigue state with new training load.

    G(t) = G(t-1) * e^(-days/tau_G) + k_G * w(t)
    H(t) = H(t-1) * e^(-days/tau_H) + k_H * w(t)

    Args:
        state: Current state
        training_load: Training impulse w(t)
        days_since_last: Days since last update

    Returns:
        Updated state
    """
    # Decay existing values
    fitness_decay = math.exp(-days_since_last / TAU_FITNESS)
    fatigue_decay = math.exp(-days_since_last / TAU_FATIGUE)

    new_fitness = state.fitness * fitness_decay + K_FITNESS * training_load
    new_fatigue = state.fatigue * fatigue_decay + K_FATIGUE * training_load

    # Update readiness statistics
    readiness = new_fitness - new_fatigue
    alpha = 0.1  # Smoothing for running stats

    new_mean = (1 - alpha) * state.readiness_mean + alpha * readiness
    new_var = (1 - alpha) * state.readiness_var + alpha * (readiness - new_mean) ** 2

    return FitnessFatigueState(
        fitness=new_fitness,
        fatigue=new_fatigue,
        m_hat=state.m_hat,
        sigma_m=state.sigma_m,
        readiness_mean=new_mean,
        readiness_var=new_var,
    )


def decay_fitness_fatigue(
    state: FitnessFatigueState,
    days: int,
) -> FitnessFatigueState:
    """
    Decay fitness-fatigue state over rest days (no training).

    Args:
        state: Current state
        days: Days of rest

    Returns:
        Decayed state
    """
    fitness_decay = math.exp(-days / TAU_FITNESS)
    fatigue_decay = math.exp(-days / TAU_FATIGUE)

    return FitnessFatigueState(
        fitness=state.fitness * fitness_decay,
        fatigue=state.fatigue * fatigue_decay,
        m_hat=state.m_hat,
        sigma_m=state.sigma_m,
        readiness_mean=state.readiness_mean,
        readiness_var=state.readiness_var,
    )


def update_max_estimate(
    state: FitnessFatigueState,
    observed_max: int,
) -> FitnessFatigueState:
    """
    Update max estimate using EWMA.

    M_hat(t) = (1-alpha) * M_hat(t-1) + alpha * M_obs(t)
    sigma^2 = (1-beta) * sigma^2 + beta * (M_obs - M_hat)^2

    Args:
        state: Current state
        observed_max: Observed max from session

    Returns:
        Updated state with new M_hat and sigma
    """
    # Update EWMA
    new_m_hat = (1 - ALPHA_MHAT) * state.m_hat + ALPHA_MHAT * observed_max

    # Update variance estimate
    residual_sq = (observed_max - state.m_hat) ** 2
    new_sigma_sq = (1 - BETA_SIGMA) * (state.sigma_m ** 2) + BETA_SIGMA * residual_sq
    new_sigma = math.sqrt(max(0.01, new_sigma_sq))  # Floor to avoid zero

    return FitnessFatigueState(
        fitness=state.fitness,
        fatigue=state.fatigue,
        m_hat=new_m_hat,
        sigma_m=new_sigma,
        readiness_mean=state.readiness_mean,
        readiness_var=state.readiness_var,
    )


def predicted_max_with_readiness(
    base_max: float,
    readiness: float,
    mean_readiness: float,
) -> float:
    """
    Adjust max prediction based on readiness.

    M_pred(t) = M_base(t) * (1 + c_R * (R(t) - R_bar))

    Args:
        base_max: Base estimated max (M_hat)
        readiness: Current readiness R(t)
        mean_readiness: Rolling mean readiness

    Returns:
        Adjusted max prediction
    """
    adjustment = C_READINESS * (readiness - mean_readiness)
    return base_max * (1 + adjustment)


def build_fitness_fatigue_state(
    history: list[SessionResult],
    reference_bodyweight_kg: float,
    baseline_max: int | None = None,
    bw_fraction: float = 1.0,
    variant_factors: dict[str, float] | None = None,
) -> FitnessFatigueState:
    """
    Build fitness-fatigue state from training history.

    Processes history chronologically to build up state.

    Args:
        history: Training history sorted by date
        reference_bodyweight_kg: Reference bodyweight for normalization
        baseline_max: Initial max if no history

    Returns:
        Current fitness-fatigue state
    """
    if not history:
        return FitnessFatigueState(
            m_hat=float(baseline_max) if baseline_max else 10.0,
            sigma_m=INITIAL_SIGMA_M,
            readiness_mean=0.0,
            readiness_var=10.0,  # Wide initial variance prevents extreme z-scores early on
        )

    # Initialize from first test session or baseline
    test_sessions = get_test_sessions(history)
    if test_sessions:
        initial_max = session_max_reps(test_sessions[0])
    elif baseline_max:
        initial_max = baseline_max
    else:
        initial_max = 10

    state = FitnessFatigueState(
        m_hat=float(initial_max),
        sigma_m=INITIAL_SIGMA_M,
        readiness_mean=0.0,
        readiness_var=10.0,  # Wide initial variance prevents extreme z-scores early on
    )

    # Process history
    prev_date: datetime | None = None

    for session in history:
        curr_date = datetime.strptime(session.date, "%Y-%m-%d")

        # Calculate days since last
        if prev_date is not None:
            days_since = (curr_date - prev_date).days
        else:
            days_since = 1

        # Decay state over rest days
        if days_since > 1:
            state = decay_fitness_fatigue(state, days_since - 1)

        # Calculate training load
        training_load = calculate_session_training_load(
            session, int(state.m_hat), reference_bodyweight_kg, bw_fraction, variant_factors
        )

        # Update fitness/fatigue
        state = update_fitness_fatigue(state, training_load, days_since_last=1)

        # Update max estimate if this is a test session
        if session.session_type == "TEST":
            observed_max = session_max_reps(session)
            if observed_max > 0:
                state = update_max_estimate(state, observed_max)

        prev_date = curr_date

    return state


def get_session_standardized_max(
    session: SessionResult,
    reference_bodyweight_kg: float,
) -> float:
    """
    Get the maximum standardized reps from a session.

    X(d) = max_j(reps_std_j)

    Args:
        session: Session result
        reference_bodyweight_kg: Reference bodyweight

    Returns:
        Maximum standardized reps
    """
    if not session.completed_sets:
        return 0.0

    max_std = 0.0

    for s in session.completed_sets:
        if s.actual_reps is None:
            continue

        std = standardized_reps(
            actual_reps=s.actual_reps,
            rest_seconds=s.rest_seconds_before,
            session_bodyweight_kg=session.bodyweight_kg,
            reference_bodyweight_kg=reference_bodyweight_kg,
            added_load_kg=s.added_weight_kg,
            grip=session.grip,
        )

        if std > max_std:
            max_std = std

    return max_std
