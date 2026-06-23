"""Derived training-state models (fitness-fatigue, training status)."""

import math
from dataclasses import dataclass


@dataclass
class FitnessFatigueState:
    """State of the fitness-fatigue impulse response model."""

    fitness: float = 0.0  # G(t) - slow decay fitness
    fatigue: float = 0.0  # H(t) - fast decay fatigue
    m_hat: float = 10.0  # Estimated standardized max
    sigma_m: float = 1.5  # Uncertainty in max estimate
    readiness_mean: float = 0.0  # Rolling mean of readiness
    readiness_var: float = 1.0  # Rolling variance of readiness

    def readiness(self) -> float:
        """Current readiness R(t) = G(t) - H(t)."""
        return self.fitness - self.fatigue

    def readiness_z_score(self) -> float:
        """Readiness z-score for autoregulation."""
        if self.readiness_var <= 0:
            return 0.0
        std = math.sqrt(self.readiness_var)
        if std == 0:
            return 0.0
        return (self.readiness() - self.readiness_mean) / std


@dataclass
class TrainingStatus:
    """Current training status derived from history analysis."""

    training_max: int
    latest_test_max: int | None
    trend_slope: float  # reps per week
    is_plateau: bool
    deload_recommended: bool
    compliance_ratio: float
    fatigue_score: float
    fitness_fatigue_state: FitnessFatigueState
