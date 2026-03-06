"""
Planning package for bar-scheduler.

Re-exports every symbol that was previously importable from
``bar_scheduler.core.planner`` so that all existing CLI code and tests
continue to work without modification.
"""

# --- Primary public API (imported by cli/commands/planning.py) ---
from .plan_engine import (
    explain_plan_entry,
    generate_plan,
    create_synthetic_test_session,
    estimate_plan_completion_date,
    format_plan_summary,
)

# --- Schedule construction (imported by test_plan_integration.py, test_core_formulas.py) ---
from .schedule_builder import (
    get_schedule_template,
    get_next_session_type_index,
    calculate_session_days,
)

# --- Grip rotation (imported by tests) ---
from .grip_selector import (
    select_grip,
    _init_grip_counts,
    _next_grip,
    GripSelector,
)

# --- Load calculation (imported by test_cli_smoke.py) ---
from .load_calculator import _calculate_added_weight

# --- Rest calculation (imported by test_core_formulas.py) ---
from .rest_advisor import calculate_adaptive_rest

# --- Set prescription (imported by tests) ---
from .set_prescriptor import calculate_set_prescription

# --- TEST injection (imported by test_cli_smoke.py) ---
from .test_session_inserter import _insert_test_sessions

# --- Internal types (available for advanced consumers) ---
from .types import _SessionTrace

__all__ = [
    # Public API
    "explain_plan_entry",
    "generate_plan",
    "create_synthetic_test_session",
    "estimate_plan_completion_date",
    "format_plan_summary",
    # Schedule
    "get_schedule_template",
    "get_next_session_type_index",
    "calculate_session_days",
    # Grip
    "select_grip",
    "_init_grip_counts",
    "_next_grip",
    "GripSelector",
    # Load
    "_calculate_added_weight",
    # Rest
    "calculate_adaptive_rest",
    # Sets
    "calculate_set_prescription",
    # Test sessions
    "_insert_test_sessions",
    # Types
    "_SessionTrace",
]
