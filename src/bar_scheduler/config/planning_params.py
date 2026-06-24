"""Planning/adaptation config sections (volume, progression, plateau, readiness)."""

from dataclasses import dataclass


@dataclass
class VolumeConfig:
    WEEKLY_HARD_SETS_MIN: int = 8
    WEEKLY_HARD_SETS_MAX: int = 20
    WEEKLY_VOLUME_INCREASE_RATE: float = 0.1
    DELOAD_VOLUME_REDUCTION: float = 0.4
    MAX_DAILY_REPS: int = 45
    MAX_DAILY_SETS: int = 10


@dataclass
class ProgressionConfig:
    TM_FACTOR: float = 0.9
    TARGET_MAX_REPS: int = 30
    DELTA_PROGRESSION_MIN: float = 0.3
    DELTA_PROGRESSION_MAX: float = 1.0
    ETA_PROGRESSION: float = 1.5


@dataclass
class PlateauConfig:
    PLATEAU_SLOPE_THRESHOLD: float = 0.05
    PLATEAU_WINDOW_DAYS: int = 21
    TREND_WINDOW_DAYS: int = 21
    FATIGUE_Z_THRESHOLD: float = -0.5
    UNDERPERFORMANCE_THRESHOLD: float = 0.1
    COMPLIANCE_THRESHOLD: float = 0.7


@dataclass
class AutoregulationConfig:
    MIN_SESSIONS_FOR_AUTOREG: int = 3


@dataclass
class ReadinessConfig:
    READINESS_Z_LOW: float = -0.5
    READINESS_Z_HIGH: float = 0.5
    READINESS_VOLUME_REDUCTION: float = 0.3
