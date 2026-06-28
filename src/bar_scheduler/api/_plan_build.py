"""Helpers that assemble the get_plan response (loading, caching, serializing)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bar_scheduler.containers import container
from bar_scheduler.core.exercises.base import ExerciseDefinition
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.domain.context import EquipmentConstraints, PlanRequest
from bar_scheduler.domain.models import SessionPlan, UserState
from bar_scheduler.io.serializers import dict_to_session_plan, session_plan_to_dict
from bar_scheduler.io.user_store import UserStore
from bar_scheduler.api._common import _require_store, _resolve_plan_start, _total_weeks
from bar_scheduler.api._timeline_dict import _timeline_entry_to_dict


@dataclass(frozen=True)
class _PlanInputs:
    store: UserStore
    exercise: ExerciseDefinition
    user_state: UserState
    plan_start_date: str

    @property
    def exercise_id(self) -> str:
        return self.exercise.exercise_id

    @property
    def bodyweight_kg(self) -> float:
        return self.user_state.profile.bodyweight_kg

    @property
    def days_per_week(self) -> int:
        return self.user_state.profile.days_for_exercise(self.exercise_id)


def _load_plan_inputs(data_dir: Path, exercise_id: str) -> _PlanInputs:
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state(exercise_id)
    return _PlanInputs(
        store=store,
        exercise=get_exercise(exercise_id),
        user_state=user_state,
        plan_start_date=_resolve_plan_start(store, exercise_id, user_state.history),
    )


def _plan_request(inputs: _PlanInputs, total_weeks: int, ot_level: int) -> PlanRequest:
    eq_state = inputs.store.equipment.load(inputs.exercise_id)
    return PlanRequest(
        user_state=inputs.user_state,
        start_date=inputs.plan_start_date,
        exercise=inputs.exercise,
        weeks_ahead=total_weeks,
        overtraining_level=ot_level,
        equipment=EquipmentConstraints.from_state(eq_state),
    )


def _resolve_plans(inputs: _PlanInputs, weeks_ahead: int, ot_level: int) -> list[SessionPlan]:
    """Return cached plans when still fresh, else generate and cache them."""
    store = inputs.store
    total_weeks = _total_weeks(inputs.plan_start_date, weeks_ahead)
    input_paths = [store.profile.path, store.history.path(inputs.exercise_id)]
    cache = store.plan_cache.load_if_fresh(inputs.exercise_id, input_paths)
    if cache is not None:
        return [dict_to_session_plan(plan_dict) for plan_dict in cache["plans"]]
    plans = container.planning_service().generate(_plan_request(inputs, total_weeks, ot_level))
    store.plan_cache.save(inputs.exercise_id, [session_plan_to_dict(plan) for plan in plans])
    return plans


def _status_dict(status) -> dict:
    ff = status.fitness_fatigue_state
    return {
        "training_max": status.training_max,
        "latest_test_max": status.latest_test_max,
        "trend_slope_per_week": round(status.trend_slope, 4),
        "is_plateau": status.is_plateau,
        "deload_recommended": status.deload_recommended,
        "readiness_z_score": round(ff.readiness_z_score(), 4),
        "fitness": round(ff.fitness, 4),
        "fatigue": round(ff.fatigue, 4),
    }


def _plan_response(inputs: _PlanInputs, ot_severity: dict, timeline: list) -> dict:
    status = container.training_state().status(inputs.user_state.history, inputs.bodyweight_kg)
    return {
        "status": _status_dict(status),
        "sessions": [
            _timeline_entry_to_dict(tl_entry, inputs.exercise, inputs.bodyweight_kg)
            for tl_entry in timeline
        ],
        "overtraining": ot_severity,
    }
