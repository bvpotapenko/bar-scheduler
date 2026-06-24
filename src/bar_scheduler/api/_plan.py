"""Planning functions for the bar-scheduler API."""

from __future__ import annotations

from pathlib import Path

from bar_scheduler.containers import container
from bar_scheduler.core.timeline import build_timeline
from bar_scheduler.api._common import _require_profile_store
from bar_scheduler.api._plan_build import _load_plan_inputs, _plan_response, _resolve_plans


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
    - ``overtraining``   -- overtraining severity dict (level, description, …)
    """
    inputs = _load_plan_inputs(data_dir, exercise_id)
    ot_severity = container.overtraining().severity(inputs.user_state.history, inputs.days_per_week)
    plans = _resolve_plans(inputs, weeks_ahead, ot_severity["level"])
    timeline = build_timeline(plans, inputs.user_state.history)
    return _plan_response(inputs, ot_severity, timeline)


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
