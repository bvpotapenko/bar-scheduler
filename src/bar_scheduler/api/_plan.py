"""Planning functions for the bar-scheduler API."""

from __future__ import annotations

from pathlib import Path

from bar_scheduler.containers import container
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.timeline import build_timeline
from bar_scheduler.domain.context import EquipmentConstraints, PlanRequest
from bar_scheduler.io.serializers import dict_to_session_plan, session_plan_to_dict
from bar_scheduler.api._common import (
    _require_profile_store,
    _require_store,
    _resolve_plan_start,
    _timeline_entry_to_dict,
    _total_weeks,
)


def get_plan(
    data_dir: Path,
    exercise_id: str,
    weeks_ahead: int = 4,
) -> dict:
    """
    Return the unified training timeline (past history + upcoming plan).

    Returns a dict with:

    - ``status``         -- training status metrics (training_max, readiness, …)
    - ``sessions``       -- list of timeline entry dicts (past + future)
    - ``plan_changes``   -- list of human-readable change strings vs. the last
                           cached plan (empty list on first call)
    - ``overtraining``   -- overtraining severity dict (level, description, …)
    """
    exercise = get_exercise(exercise_id)
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)

    plan_start_date = _resolve_plan_start(store, exercise_id, user_state.history)
    total_weeks = _total_weeks(plan_start_date, weeks_ahead)

    ot_severity = container.overtraining().severity(
        user_state.history, user_state.profile.days_for_exercise(exercise_id)
    )
    ot_level = ot_severity["level"]

    eq_state = store.load_current_equipment(exercise_id)

    cache = store.load_plan_result_cache(exercise_id)
    input_mtime = store._input_files_mtime(exercise_id)
    if cache and cache.get("generated_at", 0.0) >= input_mtime:
        plans = [dict_to_session_plan(plan_dict) for plan_dict in cache["plans"]]
    else:
        request = PlanRequest(
            user_state=user_state,
            start_date=plan_start_date,
            exercise=exercise,
            weeks_ahead=total_weeks,
            overtraining_level=ot_level,
            equipment=EquipmentConstraints.from_state(eq_state),
        )
        plans = container.planning_service().generate(request)
        store.save_plan_result_cache(exercise_id, [session_plan_to_dict(plan) for plan in plans])

    training_status = container.training_state().status(
        user_state.history,
        user_state.profile.bodyweight_kg,
    )

    timeline = build_timeline(plans, user_state.history)

    ff = training_status.fitness_fatigue_state
    return {
        "status": {
            "training_max": training_status.training_max,
            "latest_test_max": training_status.latest_test_max,
            "trend_slope_per_week": round(training_status.trend_slope, 4),
            "is_plateau": training_status.is_plateau,
            "deload_recommended": training_status.deload_recommended,
            "readiness_z_score": round(ff.readiness_z_score(), 4),
            "fitness": round(ff.fitness, 4),
            "fatigue": round(ff.fatigue, 4),
        },
        "sessions": [
            _timeline_entry_to_dict(tl_entry, exercise, user_state.profile.bodyweight_kg)
            for tl_entry in timeline
        ],
        "overtraining": ot_severity,
    }


def set_plan_start_date(data_dir: Path, exercise_id: str, date: str) -> None:
    """
    Set the plan anchor date for an exercise.

    Future calls to ``get_plan`` will treat this date as the start of the
    current planning cycle.  Useful after a break or when you want to
    manually reset the schedule.
    Raises ``ProfileNotFoundError`` if the profile has not been initialised.
    """
    store = _require_profile_store(data_dir)
    store.set_plan_start_date(exercise_id, date)


def get_plan_weeks(data_dir: Path) -> int | None:
    """
    Return the saved plan horizon in weeks, or ``None`` if never set.

    The value is persisted by ``set_plan_weeks`` and reused by subsequent
    ``get_plan`` calls that do not pass an explicit ``weeks_ahead`` argument.
    Raises ``ProfileNotFoundError`` if the profile has not been initialised.
    """
    store = _require_profile_store(data_dir)
    return store.get_plan_weeks()


def set_plan_weeks(data_dir: Path, weeks: int) -> None:
    """
    Persist the user-chosen plan horizon so subsequent plan calls reuse it.

    Raises ``ProfileNotFoundError`` if the profile has not been initialised.
    """
    store = _require_profile_store(data_dir)
    store.set_plan_weeks(weeks)
