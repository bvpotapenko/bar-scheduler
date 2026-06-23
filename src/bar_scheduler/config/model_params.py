"""Physiological-model config sections (rest, EWMA, fitness-fatigue, load)."""

from dataclasses import dataclass


@dataclass
class RestNormalizationConfig:
    REST_REF_SECONDS: int = 180
    GAMMA_REST: float = 0.20
    F_REST_MIN: float = 0.80
    F_REST_MAX: float = 1.05
    REST_MIN_CLAMP: int = 30


@dataclass
class EwmaMaxConfig:
    ALPHA_MHAT: float = 0.25
    BETA_SIGMA: float = 0.15
    INITIAL_SIGMA_M: float = 1.5


@dataclass
class FitnessFatigueConfig:
    TAU_FATIGUE: float = 7.0
    TAU_FITNESS: float = 42.0
    K_FATIGUE: float = 1.0
    K_FITNESS: float = 0.5
    C_READINESS: float = 0.02


@dataclass
class TrainingLoadConfig:
    A_RIR: float = 0.15
    GAMMA_S: float = 0.15
    S_REST_MAX: float = 1.5
    GAMMA_LOAD: float = 1.5


@dataclass
class WithinSessionFatigueConfig:
    LAMBDA_DECAY: float = 0.08
    Q_REST_RECOVERY: float = 0.3
    TAU_REST_RECOVERY: float = 60.0
    DROP_OFF_THRESHOLD: float = 0.35
