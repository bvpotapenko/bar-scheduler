"""Root structured config that composes the per-concern sections.

Field defaults are the canonical fallbacks; ``exercises.yaml`` (bundled +
user override) is merged on top by :mod:`bar_scheduler.config.loader`.
"""

from dataclasses import dataclass, field

from bar_scheduler.config.model_params import (
    EwmaMaxConfig,
    FitnessFatigueConfig,
    RestNormalizationConfig,
    TrainingLoadConfig,
    WithinSessionFatigueConfig,
)
from bar_scheduler.config.planning_params import (
    AutoregulationConfig,
    PlateauConfig,
    ProgressionConfig,
    ReadinessConfig,
    VolumeConfig,
)
from bar_scheduler.config.schedule_params import PlanHorizonConfig, ScheduleConfig


@dataclass
class ModelConfig:
    """Root config: one nested section per training-model concern."""

    rest_normalization: RestNormalizationConfig = field(default_factory=RestNormalizationConfig)
    ewma_max: EwmaMaxConfig = field(default_factory=EwmaMaxConfig)
    fitness_fatigue: FitnessFatigueConfig = field(default_factory=FitnessFatigueConfig)
    training_load: TrainingLoadConfig = field(default_factory=TrainingLoadConfig)
    within_session_fatigue: WithinSessionFatigueConfig = field(
        default_factory=WithinSessionFatigueConfig,
    )
    volume: VolumeConfig = field(default_factory=VolumeConfig)
    progression: ProgressionConfig = field(default_factory=ProgressionConfig)
    plateau: PlateauConfig = field(default_factory=PlateauConfig)
    autoregulation: AutoregulationConfig = field(default_factory=AutoregulationConfig)
    readiness: ReadinessConfig = field(default_factory=ReadinessConfig)
    plan_horizon: PlanHorizonConfig = field(default_factory=PlanHorizonConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
