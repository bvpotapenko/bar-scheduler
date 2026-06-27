"""JSON serialization for training data models (the sole I/O boundary).

Cohesive split: ``validators`` (field checks), ``sets``/``equipment``/
``profile``/``sessions`` (dataclass <-> dict), and ``compact``/``parsers``
(sets-string parsing). Importers use ``bar_scheduler.io.serializers`` directly.
"""

from bar_scheduler.io.serializers.compact import parse_compact_sets
from bar_scheduler.io.serializers.equipment import (
    dict_to_equipment_snapshot,
    dict_to_equipment_state,
    equipment_snapshot_to_dict,
    equipment_state_to_dict,
)
from bar_scheduler.io.serializers.jsonl import sessions_from_jsonl
from bar_scheduler.io.serializers.parsers import parse_sets_string
from bar_scheduler.io.serializers.profile import (
    dict_to_exercise_target,
    dict_to_user_profile,
    exercise_target_to_dict,
    user_profile_to_dict,
)
from bar_scheduler.io.serializers.sessions import (
    dict_to_session_plan,
    dict_to_session_result,
    json_line_to_session,
    session_plan_to_dict,
    session_result_to_dict,
    session_to_json_line,
)
from bar_scheduler.io.serializers.sets import (
    dict_to_planned_set,
    dict_to_set_result,
    planned_set_to_dict,
    set_result_to_dict,
)
from bar_scheduler.io.serializers.validators import (
    ValidationError,
    validate_date,
    validate_grip,
    validate_non_negative,
    validate_positive,
    validate_session_type,
)

__all__ = [
    "ValidationError",
    "validate_date",
    "validate_grip",
    "validate_session_type",
    "validate_non_negative",
    "validate_positive",
    "set_result_to_dict",
    "dict_to_set_result",
    "planned_set_to_dict",
    "dict_to_planned_set",
    "equipment_snapshot_to_dict",
    "dict_to_equipment_snapshot",
    "equipment_state_to_dict",
    "dict_to_equipment_state",
    "exercise_target_to_dict",
    "dict_to_exercise_target",
    "user_profile_to_dict",
    "dict_to_user_profile",
    "session_result_to_dict",
    "dict_to_session_result",
    "session_to_json_line",
    "json_line_to_session",
    "sessions_from_jsonl",
    "session_plan_to_dict",
    "dict_to_session_plan",
    "parse_compact_sets",
    "parse_sets_string",
]
