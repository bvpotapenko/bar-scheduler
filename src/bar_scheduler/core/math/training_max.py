"""Training-max derivation from history or a baseline."""

from bar_scheduler.core.config import TM_FACTOR
from bar_scheduler.core.math.history_queries import latest_test_max
from bar_scheduler.domain.models import SessionResult


def training_max(history: list[SessionResult]) -> int:
    """TM = floor(TM_FACTOR * latest_test_max), minimum 1 (1 if no history)."""
    test_max = latest_test_max(history)
    if test_max is None or test_max == 0:
        return 1
    return max(1, int(test_max * TM_FACTOR))


def training_max_from_baseline(baseline_max: int) -> int:
    """TM = floor(TM_FACTOR * baseline_max), minimum 1."""
    return max(1, int(baseline_max * TM_FACTOR))
