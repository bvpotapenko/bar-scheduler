"""
Configuration constants for the bar-scheduler training engine.

Transitional module: the canonical config now lives in the typed, OmegaConf
structured :class:`bar_scheduler.config.ModelConfig`. These module-level names
re-expose it so existing callers keep working while the policy redesign moves
each section to the component that consumes it.

User overrides: create ~/.bar-scheduler/exercises.yaml with only the keys you
want to change -- the file is deep-merged over the bundled definition.
"""

from bar_scheduler.config import load_model_config

_cfg = load_model_config()
_rest = _cfg.rest_normalization
_ewma = _cfg.ewma_max
_ff = _cfg.fitness_fatigue
_tload = _cfg.training_load
_wsf = _cfg.within_session_fatigue
_vol = _cfg.volume
_prog = _cfg.progression
_plateau = _cfg.plateau
_autoreg = _cfg.autoregulation
_readiness = _cfg.readiness
_horizon = _cfg.plan_horizon
_sched = _cfg.schedule

# Rest normalization
REST_REF_SECONDS: int = _rest.REST_REF_SECONDS
GAMMA_REST: float = _rest.GAMMA_REST
F_REST_MIN: float = _rest.F_REST_MIN
F_REST_MAX: float = _rest.F_REST_MAX
REST_MIN_CLAMP: int = _rest.REST_MIN_CLAMP

# EWMA max estimation
ALPHA_MHAT: float = _ewma.ALPHA_MHAT
BETA_SIGMA: float = _ewma.BETA_SIGMA
INITIAL_SIGMA_M: float = _ewma.INITIAL_SIGMA_M

# Fitness-fatigue model
TAU_FATIGUE: float = _ff.TAU_FATIGUE
TAU_FITNESS: float = _ff.TAU_FITNESS
K_FATIGUE: float = _ff.K_FATIGUE
K_FITNESS: float = _ff.K_FITNESS
C_READINESS: float = _ff.C_READINESS

# Training load
A_RIR: float = _tload.A_RIR
GAMMA_S: float = _tload.GAMMA_S
S_REST_MAX: float = _tload.S_REST_MAX
GAMMA_LOAD: float = _tload.GAMMA_LOAD

# Within-session fatigue
LAMBDA_DECAY: float = _wsf.LAMBDA_DECAY
Q_REST_RECOVERY: float = _wsf.Q_REST_RECOVERY
TAU_REST_RECOVERY: float = _wsf.TAU_REST_RECOVERY
DROP_OFF_THRESHOLD: float = _wsf.DROP_OFF_THRESHOLD

# Volume targets
WEEKLY_HARD_SETS_MIN: int = _vol.WEEKLY_HARD_SETS_MIN
WEEKLY_HARD_SETS_MAX: int = _vol.WEEKLY_HARD_SETS_MAX
WEEKLY_VOLUME_INCREASE_RATE: float = _vol.WEEKLY_VOLUME_INCREASE_RATE
DELOAD_VOLUME_REDUCTION: float = _vol.DELOAD_VOLUME_REDUCTION
MAX_DAILY_REPS: int = _vol.MAX_DAILY_REPS
MAX_DAILY_SETS: int = _vol.MAX_DAILY_SETS

# Training max
TM_FACTOR: float = _prog.TM_FACTOR

# Schedule templates
SCHEDULE_ONE_DAYS: list[str] = list(_sched.SCHEDULE_1_DAYS)
SCHEDULE_TWO_DAYS: list[str] = list(_sched.SCHEDULE_2_DAYS)
SCHEDULE_THREE_DAYS: list[str] = list(_sched.SCHEDULE_3_DAYS)
SCHEDULE_FOUR_DAYS: list[str] = list(_sched.SCHEDULE_4_DAYS)
SCHEDULE_FIVE_DAYS: list[str] = list(_sched.SCHEDULE_5_DAYS)
DAY_SPACING: dict[str, int] = dict(_sched.DAY_SPACING)

# Progression
TARGET_MAX_REPS: int = _prog.TARGET_MAX_REPS
DELTA_PROGRESSION_MIN: float = _prog.DELTA_PROGRESSION_MIN
DELTA_PROGRESSION_MAX: float = _prog.DELTA_PROGRESSION_MAX
ETA_PROGRESSION: float = _prog.ETA_PROGRESSION

# Plateau and deload
PLATEAU_SLOPE_THRESHOLD: float = _plateau.PLATEAU_SLOPE_THRESHOLD
PLATEAU_WINDOW_DAYS: int = _plateau.PLATEAU_WINDOW_DAYS
TREND_WINDOW_DAYS: int = _plateau.TREND_WINDOW_DAYS
FATIGUE_Z_THRESHOLD: float = _plateau.FATIGUE_Z_THRESHOLD
UNDERPERFORMANCE_THRESHOLD: float = _plateau.UNDERPERFORMANCE_THRESHOLD
COMPLIANCE_THRESHOLD: float = _plateau.COMPLIANCE_THRESHOLD

# Autoregulation gating
MIN_SESSIONS_FOR_AUTOREG: int = _autoreg.MIN_SESSIONS_FOR_AUTOREG

# Readiness gating
READINESS_Z_LOW: float = _readiness.READINESS_Z_LOW
READINESS_Z_HIGH: float = _readiness.READINESS_Z_HIGH
READINESS_VOLUME_REDUCTION: float = _readiness.READINESS_VOLUME_REDUCTION

# Plan horizon
MIN_PLAN_WEEKS: int = _horizon.MIN_PLAN_WEEKS
MAX_PLAN_WEEKS: int = _horizon.MAX_PLAN_WEEKS
DEFAULT_PLAN_WEEKS: int = _horizon.DEFAULT_PLAN_WEEKS

EXPECTED_WEEKS_PER_REP: float = 2.0  # Rough estimate; internal only


def expected_reps_per_week(training_max: int, target: int = TARGET_MAX_REPS) -> float:
    """
    Calculate expected progression rate based on current level.

    As training max approaches the target, progression slows nonlinearly.
    Returns expected reps gained per week.
    """
    if training_max >= target:
        return 0.0

    fraction_to_goal = 1 - (training_max / target)
    return DELTA_PROGRESSION_MIN + (DELTA_PROGRESSION_MAX - DELTA_PROGRESSION_MIN) * (
        fraction_to_goal**ETA_PROGRESSION
    )


def estimate_weeks_to_target(current_max: int, target: int = TARGET_MAX_REPS) -> int:
    """
    Estimate weeks needed to reach target from current max.

    Iterates with the expected progression rate until the target is reached.
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
