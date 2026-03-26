"""
Configuration constants for the bar-scheduler training engine.

All tunable constants are loaded from exercises.yaml at import time.
Python literals here serve as fallback defaults when the YAML file is
absent or a key is missing.

User overrides: create ~/.bar-scheduler/exercises.yaml with only the
keys you want to change -- the file is deep-merged over the bundled
definition.

See docs/training_model.md for detailed explanations.
"""

from .engine.config_loader import load_model_config

# Re-export SessionTypeParams so existing callers don't break.
from .exercises.base import SessionTypeParams  # noqa: F401

# Load YAML config (bundled + user override); empty dict on any failure.
_cfg = load_model_config()
_rest_norm = _cfg.get("rest_normalization", {})
_ewma = _cfg.get("ewma_max", {})
_ff = _cfg.get("fitness_fatigue", {})
_tload = _cfg.get("training_load", {})
_wsf = _cfg.get("within_session_fatigue", {})
_vol = _cfg.get("volume", {})
_prog = _cfg.get("progression", {})
_plateau = _cfg.get("plateau", {})
_autoreg = _cfg.get("autoregulation", {})
_readiness = _cfg.get("readiness", {})
_horizon = _cfg.get("plan_horizon", {})
_sched = _cfg.get("schedule", {})

# =============================================================================
# REST NORMALIZATION (Section 2.1 of training model)
# =============================================================================

REST_REF_SECONDS: int = int(_rest_norm.get("REST_REF_SECONDS", 180))
GAMMA_REST: float = float(_rest_norm.get("GAMMA_REST", 0.20))
F_REST_MIN: float = float(_rest_norm.get("F_REST_MIN", 0.80))
F_REST_MAX: float = float(_rest_norm.get("F_REST_MAX", 1.05))
REST_MIN_CLAMP: int = int(_rest_norm.get("REST_MIN_CLAMP", 30))

# =============================================================================
# EWMA FOR MAX ESTIMATION (Section 3.2)
# =============================================================================

ALPHA_MHAT: float = float(_ewma.get("ALPHA_MHAT", 0.25))
BETA_SIGMA: float = float(_ewma.get("BETA_SIGMA", 0.15))
INITIAL_SIGMA_M: float = float(_ewma.get("INITIAL_SIGMA_M", 1.5))

# =============================================================================
# FITNESS-FATIGUE MODEL (Section 4)
# =============================================================================

TAU_FATIGUE: float = float(_ff.get("TAU_FATIGUE", 7.0))
TAU_FITNESS: float = float(_ff.get("TAU_FITNESS", 42.0))
K_FATIGUE: float = float(_ff.get("K_FATIGUE", 1.0))
K_FITNESS: float = float(_ff.get("K_FITNESS", 0.5))
C_READINESS: float = float(_ff.get("C_READINESS", 0.02))

# =============================================================================
# TRAINING LOAD CALCULATION (Section 5)
# =============================================================================

A_RIR: float = float(_tload.get("A_RIR", 0.15))
GAMMA_S: float = float(_tload.get("GAMMA_S", 0.15))
S_REST_MAX: float = float(_tload.get("S_REST_MAX", 1.5))
GAMMA_LOAD: float = float(_tload.get("GAMMA_LOAD", 1.5))

# =============================================================================
# WITHIN-SESSION FATIGUE (Section 6)
# =============================================================================

LAMBDA_DECAY: float = float(_wsf.get("LAMBDA_DECAY", 0.08))
Q_REST_RECOVERY: float = float(_wsf.get("Q_REST_RECOVERY", 0.3))
TAU_REST_RECOVERY: float = float(_wsf.get("TAU_REST_RECOVERY", 60.0))
DROP_OFF_THRESHOLD: float = float(_wsf.get("DROP_OFF_THRESHOLD", 0.35))

# =============================================================================
# VOLUME TARGETS (Section 7.2)
# =============================================================================

WEEKLY_HARD_SETS_MIN: int = int(_vol.get("WEEKLY_HARD_SETS_MIN", 8))
WEEKLY_HARD_SETS_MAX: int = int(_vol.get("WEEKLY_HARD_SETS_MAX", 20))
WEEKLY_VOLUME_INCREASE_RATE: float = float(_vol.get("WEEKLY_VOLUME_INCREASE_RATE", 0.10))
DELOAD_VOLUME_REDUCTION: float = float(_vol.get("DELOAD_VOLUME_REDUCTION", 0.40))
MAX_DAILY_REPS: int = int(_vol.get("MAX_DAILY_REPS", 45))
MAX_DAILY_SETS: int = int(_vol.get("MAX_DAILY_SETS", 10))

# =============================================================================
# TRAINING MAX CALCULATION (Section 7.3)
# =============================================================================

TM_FACTOR: float = float(_cfg.get("progression", {}).get("TM_FACTOR", 0.90))

# =============================================================================
# WEEKLY SCHEDULE TEMPLATES
# =============================================================================

SCHEDULE_1_DAYS: list[str] = list(_sched.get("SCHEDULE_1_DAYS", ["S"]))
SCHEDULE_2_DAYS: list[str] = list(_sched.get("SCHEDULE_2_DAYS", ["S", "H"]))
SCHEDULE_3_DAYS: list[str] = list(_sched.get("SCHEDULE_3_DAYS", ["S", "H", "E"]))
SCHEDULE_4_DAYS: list[str] = list(_sched.get("SCHEDULE_4_DAYS", ["S", "H", "T", "E"]))
SCHEDULE_5_DAYS: list[str] = list(_sched.get("SCHEDULE_5_DAYS", ["S", "H", "T", "E", "S"]))

# Day spacing: minimum rest days after each session type
DAY_SPACING: dict[str, int] = {
    k: int(v)
    for k, v in _sched.get(
        "DAY_SPACING", {"S": 1, "H": 1, "E": 1, "T": 0, "TEST": 1}
    ).items()
}

# =============================================================================
# PROGRESSION (Section 7.5)
# =============================================================================

TARGET_MAX_REPS: int = int(_prog.get("TARGET_MAX_REPS", 30))
DELTA_PROGRESSION_MIN: float = float(_prog.get("DELTA_PROGRESSION_MIN", 0.3))
DELTA_PROGRESSION_MAX: float = float(_prog.get("DELTA_PROGRESSION_MAX", 1.0))
ETA_PROGRESSION: float = float(_prog.get("ETA_PROGRESSION", 1.5))

# =============================================================================
# PLATEAU AND DELOAD (Section 8)
# =============================================================================

PLATEAU_SLOPE_THRESHOLD: float = float(_plateau.get("PLATEAU_SLOPE_THRESHOLD", 0.05))
PLATEAU_WINDOW_DAYS: int = int(_plateau.get("PLATEAU_WINDOW_DAYS", 21))
TREND_WINDOW_DAYS: int = int(_plateau.get("TREND_WINDOW_DAYS", 21))

FATIGUE_Z_THRESHOLD: float = float(_plateau.get("FATIGUE_Z_THRESHOLD", -0.5))
UNDERPERFORMANCE_THRESHOLD: float = float(_plateau.get("UNDERPERFORMANCE_THRESHOLD", 0.10))
COMPLIANCE_THRESHOLD: float = float(_plateau.get("COMPLIANCE_THRESHOLD", 0.70))

# =============================================================================
# AUTOREGULATION GATING
# =============================================================================

MIN_SESSIONS_FOR_AUTOREG: int = int(_autoreg.get("MIN_SESSIONS_FOR_AUTOREG", 10))

# =============================================================================
# READINESS GATING (Section 7.4)
# =============================================================================

READINESS_Z_LOW: float = float(_readiness.get("READINESS_Z_LOW", -1.0))
READINESS_Z_HIGH: float = float(_readiness.get("READINESS_Z_HIGH", 1.0))
READINESS_VOLUME_REDUCTION: float = float(_readiness.get("READINESS_VOLUME_REDUCTION", 0.30))

# =============================================================================
# PLAN HORIZON
# =============================================================================

MIN_PLAN_WEEKS: int = int(_horizon.get("MIN_PLAN_WEEKS", 2))
MAX_PLAN_WEEKS: int = int(_horizon.get("MAX_PLAN_WEEKS", 52))
DEFAULT_PLAN_WEEKS: int = int(_horizon.get("DEFAULT_PLAN_WEEKS", 4))

EXPECTED_WEEKS_PER_REP: float = 2.0  # Rough estimate; not in YAML (internal only)


def expected_reps_per_week(training_max: int, target: int = TARGET_MAX_REPS) -> float:
    """
    Calculate expected progression rate based on current level.

    As training max approaches the target, progression slows nonlinearly.

    Args:
        training_max: Current training max reps
        target: Exercise target (default TARGET_MAX_REPS=30 for pull-ups)

    Returns:
        Expected reps gained per week
    """
    if training_max >= target:
        return 0.0

    fraction_to_goal = 1 - (training_max / target)
    delta = DELTA_PROGRESSION_MIN + (DELTA_PROGRESSION_MAX - DELTA_PROGRESSION_MIN) * (
        fraction_to_goal**ETA_PROGRESSION
    )
    return delta


def estimate_weeks_to_target(current_max: int, target: int = TARGET_MAX_REPS) -> int:
    """
    Estimate weeks needed to reach target from current max.

    Uses iterative calculation with expected progression rate.

    Args:
        current_max: Current max reps
        target: Target max reps (default TARGET_MAX_REPS=30)

    Returns:
        Estimated weeks to reach target
    """
    if current_max >= target:
        return 0

    weeks = 0
    current = float(current_max)

    while current < target and weeks < MAX_PLAN_WEEKS * 4:  # Safety limit
        rate = expected_reps_per_week(int(current), target)
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
