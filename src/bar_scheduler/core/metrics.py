"""Transitional facade re-exporting the split math modules.

The pure metric functions now live in :mod:`bar_scheduler.core.math`. This
module re-exports them so existing callers keep working while the policy
redesign migrates them to ``core.math`` directly. It is removed once the
last importer (physiology, adaptation, api) is rewired.
"""

from bar_scheduler.core.math.compliance import (
    compliance_ratio,
    session_compliance,
    weekly_compliance,
)
from bar_scheduler.core.math.effort import estimate_rir_from_fraction
from bar_scheduler.core.math.formulas import (
    best_onerm_from_leff,
    blended_onerm_added,
    brzycki_onerm,
    epley_onerm,
    lander_onerm,
    lombardi_onerm,
)
from bar_scheduler.core.math.history_queries import (
    get_test_sessions,
    latest_test_max,
    overall_max_reps,
    session_avg_rest,
    session_max_reps,
    session_total_reps,
)
from bar_scheduler.core.math.normalization import (
    bodyweight_normalized_reps,
    effective_reps,
    grip_factor,
    rest_factor,
    standardized_reps,
)
from bar_scheduler.core.math.onerm import estimate_onerm
from bar_scheduler.core.math.training_max import training_max, training_max_from_baseline
from bar_scheduler.core.math.trend import linear_trend_max_reps, trend_slope_per_week

__all__ = [
    "compliance_ratio",
    "session_compliance",
    "weekly_compliance",
    "estimate_rir_from_fraction",
    "epley_onerm",
    "lombardi_onerm",
    "brzycki_onerm",
    "lander_onerm",
    "blended_onerm_added",
    "best_onerm_from_leff",
    "get_test_sessions",
    "latest_test_max",
    "overall_max_reps",
    "session_avg_rest",
    "session_max_reps",
    "session_total_reps",
    "rest_factor",
    "effective_reps",
    "bodyweight_normalized_reps",
    "grip_factor",
    "standardized_reps",
    "estimate_onerm",
    "training_max",
    "training_max_from_baseline",
    "linear_trend_max_reps",
    "trend_slope_per_week",
]
