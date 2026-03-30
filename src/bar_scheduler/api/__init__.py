"""bar-scheduler public API."""
from __future__ import annotations

# Exceptions
from ._common import (
    ProfileNotFoundError,
    HistoryNotFoundError,
    SessionNotFoundError,
    ProfileAlreadyExistsError,
)

# ValidationError from io layer
from ..io.serializers import ValidationError

# Types
from .types import SessionType, SessionInput, SetInput

# Profile
from ._profile import (
    init_profile,
    get_profile,
    update_bodyweight,
    update_height,
    update_language,
    update_profile,
)

# Exercises
from ._exercises import (
    list_exercises,
    get_exercise_info,
    get_equipment_catalog,
    set_exercise_target,
    set_exercise_days,
    enable_exercise,
    disable_exercise,
    delete_exercise_history,
)

# Sessions
from ._sessions import (
    log_session,
    delete_session,
    get_history,
)

# Planning
from ._plan import (
    get_plan,
    refresh_plan,
    explain_session,
    set_plan_start_date,
    get_plan_weeks,
    set_plan_weeks,
)

# Analysis
from ._analysis import (
    get_training_status,
    get_onerepmax_data,
    get_volume_data,
    get_progress_data,
    get_overtraining_status,
    get_goal_metrics,
    training_max_from_baseline,
)

# Equipment
from ._equipment import (
    update_equipment,
    get_current_equipment,
    check_band_progression,
    compute_leff,
    compute_equipment_adjustment,
    get_assistance_kg,
    get_next_band_step,
    get_assist_progression,
)

# Utils
from ._utils import (
    get_data_dir,
    parse_sets_string,
    parse_compact_sets,
)

__all__ = [
    # Exceptions
    "ProfileNotFoundError",
    "HistoryNotFoundError",
    "SessionNotFoundError",
    "ValidationError",
    "ProfileAlreadyExistsError",
    # Types
    "SessionType",
    "SessionInput",
    "SetInput",
    # Profile
    "init_profile",
    "get_profile",
    "update_bodyweight",
    "update_height",
    "update_language",
    "update_profile",
    # Exercises
    "list_exercises",
    "get_exercise_info",
    "get_equipment_catalog",
    "set_exercise_target",
    "set_exercise_days",
    "enable_exercise",
    "disable_exercise",
    "delete_exercise_history",
    # Sessions
    "log_session",
    "delete_session",
    "get_history",
    # Planning
    "get_plan",
    "refresh_plan",
    "explain_session",
    "set_plan_start_date",
    "get_plan_weeks",
    "set_plan_weeks",
    # Analysis
    "get_training_status",
    "get_onerepmax_data",
    "get_volume_data",
    "get_progress_data",
    "get_overtraining_status",
    "get_goal_metrics",
    # Equipment
    "update_equipment",
    "get_current_equipment",
    "check_band_progression",
    "compute_leff",
    "compute_equipment_adjustment",
    "get_assistance_kg",
    "get_next_band_step",
    "get_assist_progression",
    # Utils
    "get_data_dir",
    "training_max_from_baseline",
    "parse_sets_string",
    "parse_compact_sets",
]
