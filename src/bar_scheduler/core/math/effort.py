"""Effort / reps-in-reserve estimation."""


def estimate_rir_from_fraction(actual_reps: int, estimated_max: int) -> int:
    """RIR_hat = clip(estimated_max - reps, 0, 5)."""
    return max(0, min(5, estimated_max - actual_reps))
