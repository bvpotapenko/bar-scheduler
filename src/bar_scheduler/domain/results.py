"""Typed computation results (replace ad-hoc dicts/tuples)."""

from dataclasses import dataclass

from bar_scheduler.domain.models import FitnessFatigueState, TrainingStatus


@dataclass(frozen=True)
class MaxEstimate:
    """Between-test fresh-max estimate from a multi-set session (Track B)."""

    fi_est: int  # fatigue-index method estimate
    nuzzo_est: int  # Nuzzo reps~%1RM table method estimate
    fi_reps: float  # computed fatigue index (0-1)
    confidence: str  # "high" | "medium" | "low"


@dataclass(frozen=True)
class TrainingState:
    """Initial state at plan-generation time (status + baseline-adjusted TM)."""

    status: TrainingStatus
    initial_tm: int

    @property
    def ff_state(self) -> FitnessFatigueState:
        return self.status.fitness_fatigue_state

    @property
    def latest_test_max(self) -> int | None:
        return self.status.latest_test_max
