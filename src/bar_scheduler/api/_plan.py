"""Planning functions for the bar-scheduler API."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from ..core.adaptation import get_training_status as _get_training_status
from ..core.adaptation import overtraining_severity
from ..core.exercises.registry import get_exercise
from ..core.planner import explain_plan_entry, generate_plan
from ..core.timeline import TimelineEntry, build_timeline
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

    plans = generate_plan(
        user_state,
        plan_start_date,
        exercise,
        weeks_ahead=total_weeks,
        overtraining_level=ot_level,
        available_weights_kg=available_weights_kg or None,
        available_machine_assistance_kg=available_machine_assistance_kg or None,
    )

    training_status = _get_training_status(
        user_state.history,
        user_state.profile.bodyweight_kg,
    )

    timeline = build_timeline(plans, user_state.history)

    # Plan change detection
    def _snapshot(e: TimelineEntry) -> dict:
        p = e.planned
        if p is None:
            return {}
        first_set = p.sets[0] if p.sets else None
        return {
            "date": p.date,
            "type": p.session_type,
            "sets": len(p.sets),
            "reps": first_set.target_reps if first_set else 0,
            "weight": first_set.added_weight_kg if first_set else 0.0,
            "rest": first_set.rest_seconds_before if first_set else 0,
            "expected_tm": p.expected_tm,
        }

    old_cache = store.load_plan_cache(exercise_id)
    new_cache = [
        _snapshot(e)
        for e in timeline
        if e.status in ("next", "planned") and e.planned is not None
    ]
    plan_changes: list[str] = []
    if old_cache is not None:
        old_idx = {(s["date"], s["type"]): s for s in old_cache if s}
        new_idx = {(s["date"], s["type"]): s for s in new_cache if s}
        for key, snap in new_idx.items():
            if key not in old_idx:
                plan_changes.append(f"New: {snap['date']} {snap['type']}")
        for key, snap in old_idx.items():
            if key not in new_idx:
                plan_changes.append(f"Removed: {snap['date']} {snap['type']}")
        for key in sorted(set(old_idx) & set(new_idx)):
            o, n = old_idx[key], new_idx[key]
            parts: list[str] = []
            if o["sets"] != n["sets"]:
                parts.append(f"{o['sets']}→{n['sets']} sets")
            if o["reps"] != n["reps"]:
                parts.append(f"{o['reps']}→{n['reps']} reps")
            if abs(o.get("weight", 0.0) - n.get("weight", 0.0)) > 0.01:
                parts.append(f"+{o['weight']:.1f}→+{n['weight']:.1f} kg")
            if o["expected_tm"] != n["expected_tm"]:
                parts.append(f"TM {o['expected_tm']}→{n['expected_tm']}")
            if parts:
                plan_changes.append(f"{n['date']} {n['type']}: {', '.join(parts)}")
    store.save_plan_cache(exercise_id, new_cache)

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
        "plan_changes": plan_changes,
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


def explain_session(
    data_dir: Path,
    exercise_id: str,
    date: str,
    weeks_ahead: int = 4,
) -> str:
    """
    Return a plain-text explanation of how a session's parameters were derived.

    ``date`` is an ISO date string (YYYY-MM-DD) or ``"next"`` for the next
    upcoming session.  The returned string contains no Rich markup.
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
    ot_rest = ot_severity["extra_rest_days"] if ot_level >= 2 else 0

    today_dt = datetime.now()
    ot_cutoff = (today_dt + timedelta(days=max(ot_rest + 14, 14))).strftime(
        "%Y-%m-%d"
    )

    eq_state = store.load_current_equipment(exercise_id)
    available_weights_kg = eq_state.available_weights_kg if eq_state is not None else []
    avail = available_weights_kg or None

    if date.lower() == "next":
        plans = generate_plan(
            user_state,
            plan_start_date,
            exercise,
            weeks_ahead=total_weeks,
            overtraining_level=ot_level,
            overtraining_rest_days=ot_rest,
            available_weights_kg=avail,
        )
        today_str = today_dt.strftime("%Y-%m-%d")
        nxt = next((p for p in plans if p.date >= today_str), None)
        if nxt is None:
            raise ValueError("No upcoming sessions found in the plan horizon.")
        date = nxt.date

    if date > ot_cutoff:
        ot_level, ot_rest = 0, 0

    return explain_plan_entry(
        user_state,
        plan_start_date,
        date,
        exercise,
        weeks_ahead=total_weeks,
        overtraining_level=ot_level,
        overtraining_rest_days=ot_rest,
        available_weights_kg=avail,
    )


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


def get_plan_cache_entry(
    data_dir: Path, exercise_id: str, date: str, session_type: str
) -> dict | None:
    """
    Look up a cached plan prescription for a specific (date, session_type).

    Returns the cached session dict if found, or ``None`` if no cache entry
    matches.  Useful for pre-populating a session log form with planned sets.
    Raises ``ProfileNotFoundError`` if the profile has not been initialised.
    """
    store = _require_profile_store(data_dir)
    return store.lookup_plan_cache_entry(exercise_id, date, session_type)
