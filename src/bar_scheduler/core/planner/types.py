"""Shared internal types for the planner package."""

from dataclasses import dataclass
from typing import Any

from ..exercises.base import ExerciseDefinition, SessionTypeParams


@dataclass
class _SessionTrace:
    """
    All intermediate values from _plan_core() for one session.

    Consumed by _format_explain() to produce the step-by-step explanation
    without any re-computation or divergence from the plan.
    """

    # Identity
    date_str: str
    session_type: str
    session_week_idx: int
    week_num: int
    week_offset: int
    weeks_ahead: int

    # Grip / variant
    grip: str
    cycle: list
    count_before: int       # grip count before this session (history + prior plan)
    hist_count: int         # grip count from history only

    # Training max
    initial_tm: int
    current_tm: int
    tm_float: float
    weekly_log: list        # [(abs_week_idx, prog, tm_before, tm_after), ...]

    # Sets / reps
    base_sets: int
    base_reps: int
    adj_sets: int
    adj_reps: int
    has_autoreg: bool
    z_score: float
    reps_low: int
    reps_high: int

    # Weight
    added_weight: float
    last_test_weight: float

    # Rest
    adj_rest: int
    recent_same_type: list  # last 5 same-type history sessions

    # Expected TM
    expected_tm_after: int

    # Plan context
    history: list           # filtered exercise history (non-REST)
    history_len: int
    days_per_week: int
    user_target: int
    schedule: list

    # Typed config objects
    params: SessionTypeParams
    exercise: ExerciseDefinition
    ff_state: Any           # FitnessFatigueState

    # Overtraining shift (0 = not shifted)
    overtraining_shift_days: int = 0
    overtraining_level: int = 0
