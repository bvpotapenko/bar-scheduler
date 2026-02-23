"""
Configuration constants for the pull-up training model.

All adjustable parameters are centralized here for easy tuning.
See docs/training_model.md for detailed explanations.
"""

from dataclasses import dataclass
from typing import Final

# =============================================================================
# REST NORMALIZATION (Section 2.1 of training model)
# =============================================================================

REST_REF_SECONDS: Final[int] = 180  # Reference rest interval for normalization
GAMMA_REST: Final[float] = 0.20  # Exponent for rest factor calculation
F_REST_MIN: Final[float] = 0.80  # Minimum rest factor (floor)
F_REST_MAX: Final[float] = 1.05  # Maximum rest factor (ceiling)
REST_MIN_CLAMP: Final[int] = 30  # Minimum rest to avoid division issues

# =============================================================================
# BODYWEIGHT NORMALIZATION (Section 2.2)
# =============================================================================

GAMMA_BW: Final[float] = 1.0  # Exponent for bodyweight adjustment

# =============================================================================
# GRIP NORMALIZATION (Section 2.3)
# =============================================================================

GRIP_FACTORS: Final[dict[str, float]] = {
    "pronated": 1.00,
    "neutral": 1.00,
    "supinated": 1.00,
}

# =============================================================================
# EWMA FOR MAX ESTIMATION (Section 3.2)
# =============================================================================

ALPHA_MHAT: Final[float] = 0.25  # Smoothing factor for M_hat EWMA
BETA_SIGMA: Final[float] = 0.15  # Smoothing factor for variance tracking
INITIAL_SIGMA_M: Final[float] = 1.5  # Initial uncertainty in reps

# =============================================================================
# FITNESS-FATIGUE MODEL (Section 4)
# =============================================================================

TAU_FATIGUE: Final[float] = 7.0  # Fatigue time constant (days)
TAU_FITNESS: Final[float] = 42.0  # Fitness time constant (days)
K_FATIGUE: Final[float] = 1.0  # Fatigue gain from training load
K_FITNESS: Final[float] = 0.5  # Fitness gain from training load
C_READINESS: Final[float] = 0.02  # Readiness scaling factor

# =============================================================================
# TRAINING LOAD CALCULATION (Section 5)
# =============================================================================

A_RIR: Final[float] = 0.15  # Effort multiplier per RIR below 3
GAMMA_S: Final[float] = 0.15  # Exponent for rest stress
S_REST_MAX: Final[float] = 1.5  # Maximum rest stress multiplier
GAMMA_LOAD: Final[float] = 1.5  # Exponent for added load stress

GRIP_STRESS_FACTORS: Final[dict[str, float]] = {
    "pronated": 1.00,
    "neutral": 0.95,
    "supinated": 1.05,
}

# =============================================================================
# WITHIN-SESSION FATIGUE (Section 6)
# =============================================================================

LAMBDA_DECAY: Final[float] = 0.08  # Within-session rep decay rate
Q_REST_RECOVERY: Final[float] = 0.3  # Rest recovery parameter
TAU_REST_RECOVERY: Final[float] = 60.0  # Rest recovery time constant
DROP_OFF_THRESHOLD: Final[float] = 0.35  # Threshold for high drop-off

# =============================================================================
# VOLUME TARGETS (Section 7.2)
# =============================================================================

WEEKLY_HARD_SETS_MIN: Final[int] = 8  # Minimum hard sets per week
WEEKLY_HARD_SETS_MAX: Final[int] = 20  # Maximum hard sets per week
WEEKLY_VOLUME_INCREASE_RATE: Final[float] = 0.10  # Max weekly increase (10%)
DELOAD_VOLUME_REDUCTION: Final[float] = 0.40  # Volume reduction during deload

# =============================================================================
# TRAINING MAX CALCULATION (Section 7.3)
# =============================================================================

TM_FACTOR: Final[float] = 0.90  # Training max as fraction of test max

# =============================================================================
# ADDED WEIGHT (Section 7.3.1)
# =============================================================================

WEIGHT_INCREMENT_FRACTION_PER_TM: Final[float] = 0.01  # 1% BW per TM point above threshold
WEIGHT_TM_THRESHOLD: Final[int] = 9                    # TM must exceed this before adding weight
MAX_ADDED_WEIGHT_KG: Final[float] = 20.0               # Absolute cap on added weight

# =============================================================================
# SESSION TYPE PARAMETERS
# =============================================================================

@dataclass(frozen=True)
class SessionTypeParams:
    """Parameters for each session type."""

    reps_fraction_low: float  # Lower bound as fraction of TM
    reps_fraction_high: float  # Upper bound as fraction of TM
    reps_min: int  # Absolute minimum reps
    reps_max: int  # Absolute maximum reps
    sets_min: int
    sets_max: int
    rest_min: int  # Rest in seconds
    rest_max: int
    rir_target: int


SESSION_PARAMS: Final[dict[str, SessionTypeParams]] = {
    "S": SessionTypeParams(  # Strength
        reps_fraction_low=0.35,
        reps_fraction_high=0.55,
        reps_min=4,
        reps_max=6,
        sets_min=4,
        sets_max=5,
        rest_min=180,
        rest_max=300,
        rir_target=2,
    ),
    "H": SessionTypeParams(  # Hypertrophy
        reps_fraction_low=0.60,
        reps_fraction_high=0.85,
        reps_min=6,
        reps_max=12,
        sets_min=4,
        sets_max=6,
        rest_min=120,
        rest_max=180,
        rir_target=2,
    ),
    "E": SessionTypeParams(  # Endurance/Density
        reps_fraction_low=0.40,  # Increased from 0.35
        reps_fraction_high=0.60,  # Increased from 0.55
        reps_min=3,
        reps_max=8,
        sets_min=6,  # Increased from 5
        sets_max=10,  # Increased from 8
        rest_min=45,
        rest_max=75,  # Reduced from 90
        rir_target=3,
    ),
    "T": SessionTypeParams(  # Technique
        reps_fraction_low=0.20,
        reps_fraction_high=0.40,
        reps_min=2,
        reps_max=4,
        sets_min=4,
        sets_max=8,
        rest_min=60,
        rest_max=120,
        rir_target=5,
    ),
    "TEST": SessionTypeParams(  # Max test
        reps_fraction_low=1.0,
        reps_fraction_high=1.0,
        reps_min=1,
        reps_max=50,
        sets_min=1,
        sets_max=1,
        rest_min=180,
        rest_max=300,
        rir_target=0,
    ),
}

# =============================================================================
# WEEKLY SCHEDULE TEMPLATES
# =============================================================================

SCHEDULE_3_DAYS: Final[list[str]] = ["S", "H", "E"]
SCHEDULE_4_DAYS: Final[list[str]] = ["S", "H", "T", "E"]

# Day spacing: minimum rest days after each session type
DAY_SPACING: Final[dict[str, int]] = {
    "S": 1,  # At least 1 rest day after Strength
    "H": 1,
    "E": 1,  # At least 1 rest day after Endurance
    "T": 0,  # Technique can be followed immediately
    "TEST": 2,  # More recovery after max test
}

# =============================================================================
# PROGRESSION (Section 7.5)
# =============================================================================

TARGET_MAX_REPS: Final[int] = 30
DELTA_PROGRESSION_MIN: Final[float] = 0.3  # Min reps/week progression
DELTA_PROGRESSION_MAX: Final[float] = 1.0  # Max reps/week progression
ETA_PROGRESSION: Final[float] = 1.5  # Nonlinear progression exponent

# =============================================================================
# PLATEAU AND DELOAD (Section 8)
# =============================================================================

PLATEAU_SLOPE_THRESHOLD: Final[float] = 0.05  # reps/week minimum slope
PLATEAU_WINDOW_DAYS: Final[int] = 21  # Days without new best
TREND_WINDOW_DAYS: Final[int] = 21  # Window for trend calculation

FATIGUE_Z_THRESHOLD: Final[float] = -0.5  # Z-score for fatigue concern
UNDERPERFORMANCE_THRESHOLD: Final[float] = 0.10  # 10% underperformance
COMPLIANCE_THRESHOLD: Final[float] = 0.70  # Minimum compliance ratio

# =============================================================================
# AUTOREGULATION GATING
# =============================================================================

MIN_SESSIONS_FOR_AUTOREG: Final[int] = 10  # Minimum sessions before autoregulation is applied

# =============================================================================
# READINESS GATING (Section 7.4)
# =============================================================================

READINESS_Z_LOW: Final[float] = -1.0  # Below this: reduce volume
READINESS_Z_HIGH: Final[float] = 1.0  # Above this: allow progression
READINESS_VOLUME_REDUCTION: Final[float] = 0.30  # Reduce by 30%

# =============================================================================
# PLAN HORIZON
# =============================================================================

MIN_PLAN_WEEKS: Final[int] = 2
MAX_PLAN_WEEKS: Final[int] = 52
DEFAULT_PLAN_WEEKS: Final[int] = 4

# Estimation for needed weeks (rough)
EXPECTED_WEEKS_PER_REP: Final[float] = 2.0  # Roughly 0.5 reps per week


def expected_reps_per_week(training_max: int) -> float:
    """
    Calculate expected progression rate based on current level.

    As training max approaches 30, progression slows nonlinearly.

    Args:
        training_max: Current training max reps

    Returns:
        Expected reps gained per week
    """
    if training_max >= TARGET_MAX_REPS:
        return 0.0

    fraction_to_goal = 1 - (training_max / TARGET_MAX_REPS)
    delta = DELTA_PROGRESSION_MIN + (DELTA_PROGRESSION_MAX - DELTA_PROGRESSION_MIN) * (
        fraction_to_goal ** ETA_PROGRESSION
    )
    return delta


def estimate_weeks_to_target(current_max: int, target: int = TARGET_MAX_REPS) -> int:
    """
    Estimate weeks needed to reach target from current max.

    Uses iterative calculation with expected progression rate.

    Args:
        current_max: Current max reps
        target: Target max reps (default 30)

    Returns:
        Estimated weeks to reach target
    """
    if current_max >= target:
        return 0

    weeks = 0
    current = float(current_max)

    while current < target and weeks < MAX_PLAN_WEEKS * 4:  # Safety limit
        rate = expected_reps_per_week(int(current))
        if rate <= 0:
            break
        current += rate
        weeks += 1

    return min(weeks, MAX_PLAN_WEEKS * 4)


def endurance_volume_multiplier(training_max: int) -> float:
    """
    Scaling factor for endurance session total-rep target.

    kE grows linearly from 3.0 (TM=5) to 5.0 (TM=30):

        kE = 3.0 + 2.0 * clip((TM - 5) / 25, 0, 1)

    Total reps target = kE(TM) * TM

    Args:
        training_max: Current training max reps

    Returns:
        Volume multiplier (3.0 to 5.0)
    """
    fraction = min(1.0, max(0.0, (training_max - 5) / 25))
    return 3.0 + 2.0 * fraction
