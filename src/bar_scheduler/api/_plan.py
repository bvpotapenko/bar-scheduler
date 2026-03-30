"""Planning functions for the bar-scheduler API."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..core.adaptation import get_training_status as _get_training_status
from ..core.adaptation import overtraining_severity
from ..core.exercises.registry import get_exercise
from ..core.planner import generate_plan
from ..core.timeline import build_timeline
from ..io.serializers import dict_to_session_plan, session_plan_to_dict
from ._common import (
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

    ot_severity = overtraining_severity(
        user_state.history, user_state.profile.days_for_exercise(exercise_id)
    )
    ot_level = ot_severity["level"]

    eq_state = store.load_current_equipment(exercise_id)
    available_weights_kg = eq_state.available_weights_kg if eq_state is not None else []
    available_machine_assistance_kg = (
        eq_state.available_machine_assistance_kg if eq_state is not None else []
    )

    cache = store.load_plan_result_cache(exercise_id)
    input_mtime = store._input_files_mtime(exercise_id)
    if cache is not None and cache.get("generated_at", 0.0) >= input_mtime:
        plans = [dict_to_session_plan(d) for d in cache["plans"]]
    else:
        plans = generate_plan(
            user_state,
            plan_start_date,
            exercise,
            weeks_ahead=total_weeks,
            overtraining_level=ot_level,
            available_weights_kg=available_weights_kg or None,
            available_machine_assistance_kg=available_machine_assistance_kg or None,
        )
        store.save_plan_result_cache(exercise_id, [session_plan_to_dict(p) for p in plans])

    training_status = _get_training_status(
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
            _timeline_entry_to_dict(e, exercise, user_state.profile.bodyweight_kg)
            for e in timeline
        ],
        "overtraining": ot_severity,
    }


def refresh_plan(data_dir: Path, exercise_id: str) -> dict:
    """
    Reset the plan anchor to today.

    Use after a break when unlogged sessions have piled up in the past.
    Returns a dict with ``plan_start_date`` and ``next_session``
    (or ``None`` if no sessions are generated).
    """
    exercise = get_exercise(exercise_id)
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)

    today = datetime.now().strftime("%Y-%m-%d")
    store.set_plan_start_date(exercise_id, today)

    eq_state = store.load_current_equipment(exercise_id)
    available_weights_kg = eq_state.available_weights_kg if eq_state is not None else []

    plans = generate_plan(
        user_state, today, exercise, weeks_ahead=2,
        available_weights_kg=available_weights_kg or None,
    )
    next_session = next((p for p in plans if p.date >= today), None)

    return {
        "plan_start_date": today,
        "next_session": (
            {
                "date": next_session.date,
                "session_type": next_session.session_type,
                "grip": next_session.grip,
            }
            if next_session
            else None
        ),
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


