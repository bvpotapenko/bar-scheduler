"""Typed computation results (replace ad-hoc dicts/tuples)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MaxEstimate:
    """Between-test fresh-max estimate from a multi-set session (Track B)."""

    fi_est: int  # fatigue-index method estimate
    nuzzo_est: int  # Nuzzo reps~%1RM table method estimate
    fi_reps: float  # computed fatigue index (0-1)
    confidence: str  # "high" | "medium" | "low"
