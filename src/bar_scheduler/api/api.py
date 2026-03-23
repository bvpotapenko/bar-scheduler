"""
bar-scheduler public API.

A thin, framework-agnostic facade over the engine and IO layers.
No Rich, no Typer — just plain Python functions returning JSON-serialisable
dicts. Suitable for CLI wrappers, Telegram bots, web services, or any other
client.

All functions accept ``data_dir: Path`` as their first argument so callers
can point at a custom directory (useful for tests and multi-user setups).
Pass ``get_data_dir()`` for the default ``~/.bar-scheduler`` location.

Error contract
--------------
- ``ProfileNotFoundError``  — profile.json does not exist (call ``init_profile`` first)
- ``HistoryNotFoundError``  — JSONL history file does not exist (call ``init_profile`` first)
- ``SessionNotFoundError``  — index out of range for delete_session
- ``ValidationError``       — malformed data (re-exported from io.serializers)
- ``ValueError``            — bad argument (unknown exercise_id, invalid date, …)

All write functions are atomic at the file level (they rely on HistoryStore's
own write semantics; no extra locking is added here).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from ..core.adaptation import get_training_status as _get_training_status
from ..core.adaptation import overtraining_severity
from ..core.config import TM_FACTOR, expected_reps_per_week
from ..core.exercises.registry import get_exercise
from ..core.metrics import (
    blended_1rm_added,
    estimate_1rm,
    get_test_sessions,
    session_max_reps as _session_max_reps,
    training_max_from_baseline,
)
from ..core.models import SessionResult, SetResult
from ..core.planner import explain_plan_entry, generate_plan
from ..core.timeline import TimelineEntry, build_timeline
from ..io.history_store import HistoryStore, get_default_history_path
from ..io.serializers import ValidationError, session_result_to_dict, user_profile_to_dict

__all__ = [
    # Exceptions
    "ProfileNotFoundError",
    "HistoryNotFoundError",
    "SessionNotFoundError",
    "ValidationError",
    # User management
    "get_profile",
    "update_bodyweight",
    "update_language",
    "update_equipment",
    # Session management
    "log_session",
    "delete_session",
    "get_history",
    # Planning
    "get_plan",
    "refresh_plan",
    "explain_session",
    # Analysis
    "get_training_status",
    "get_onerepmax_data",
    "get_volume_data",
    "get_progress_data",
    "get_overtraining_status",
]


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class ProfileNotFoundError(FileNotFoundError):
    """Raised when profile.json does not exist."""


class HistoryNotFoundError(FileNotFoundError):
    """Raised when the JSONL history file does not exist."""


class SessionNotFoundError(IndexError):
    """Raised when a session index is out of range."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _store(data_dir: Path, exercise_id: str) -> HistoryStore:
    history_path = data_dir / f"{exercise_id}_history.jsonl"
    return HistoryStore(history_path, exercise_id=exercise_id)


def _require_store(data_dir: Path, exercise_id: str) -> HistoryStore:
    """Return a HistoryStore, raising typed errors when files are missing."""
    store = _store(data_dir, exercise_id)
    if not store.profile_path.exists():
        raise ProfileNotFoundError(
            f"Profile not found at {store.profile_path}. Call init_profile() first."
        )
    if not store.history_path.exists():
        raise HistoryNotFoundError(
            f"History file not found at {store.history_path}. Call init_profile() first."
        )
    return store


def _resolve_plan_start(store: HistoryStore, history: list[SessionResult]) -> str:
    plan_start = store.get_plan_start_date()
    if plan_start is None:
        if history:
            first_dt = datetime.strptime(history[0].date, "%Y-%m-%d")
            plan_start = (first_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            plan_start = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return plan_start


def _total_weeks(plan_start_date: str, weeks_ahead: int = 4) -> int:
    from ..core.config import MAX_PLAN_WEEKS
    plan_start_dt = datetime.strptime(plan_start_date, "%Y-%m-%d")
    weeks_since_start = max(0, (datetime.now() - plan_start_dt).days // 7)
    return max(2, min(weeks_since_start + weeks_ahead, MAX_PLAN_WEEKS * 3))


def _timeline_entry_to_dict(e: TimelineEntry) -> dict:
    """Serialise a TimelineEntry to a JSON-friendly dict."""
    planned_sets = None
    if e.actual is not None and e.actual.planned_sets:
        planned_sets = [
            {"reps": s.target_reps, "weight_kg": s.added_weight_kg, "rest_s": s.rest_seconds_before}
            for s in e.actual.planned_sets
        ]
    elif e.planned is not None and e.planned.sets:
        planned_sets = [
            {"reps": s.target_reps, "weight_kg": s.added_weight_kg, "rest_s": s.rest_seconds_before}
            for s in e.planned.sets
        ]

    actual_sets = None
    if e.actual is not None:
        actual_sets = [
            {"reps": s.actual_reps, "weight_kg": s.added_weight_kg, "rest_s": s.rest_seconds_before}
            for s in e.actual.completed_sets
            if s.actual_reps is not None
        ]

    plan_type = (
        e.actual.session_type if e.actual else (e.planned.session_type if e.planned else "")
    )
    plan_grip = e.actual.grip if e.actual else (e.planned.grip if e.planned else "")

    return {
        "date": e.date,
        "week": e.week_number,
        "type": plan_type,
        "grip": plan_grip,
        "status": e.status,
        "id": e.actual_id,
        "expected_tm": e.planned.expected_tm if e.planned else None,
        "prescribed_sets": planned_sets,
        "actual_sets": actual_sets,
        "track_b": e.track_b,
    }


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


def get_profile(data_dir: Path, exercise_id: str = "pull_up") -> dict | None:
    """
    Return the current user profile as a dict, or None if not initialised.

    The dict includes all UserProfile fields plus ``current_bodyweight_kg``.
    """
    store = _store(data_dir, exercise_id)
    profile = store.load_profile()
    if profile is None:
        return None
    bw = store.load_bodyweight()
    d = user_profile_to_dict(profile)
    d["current_bodyweight_kg"] = bw
    return d


def update_bodyweight(data_dir: Path, exercise_id: str, bodyweight_kg: float) -> None:
    """Update the current bodyweight in profile.json."""
    store = _require_store(data_dir, exercise_id)
    store.update_bodyweight(bodyweight_kg)


def update_language(data_dir: Path, lang: str) -> None:
    """
    Set the display language preference.

    ``lang`` must be one of the supported language codes (e.g. ``"en"``,
    ``"ru"``, ``"zh"``). Passing ``"en"`` removes the key (default).
    """
    from ..core.i18n import available_languages
    if lang != "en" and lang not in available_languages():
        raise ValueError(f"Unsupported language '{lang}'. Available: {available_languages()}")
    # Use a profile-only store (any exercise_id works for language updates)
    store = _store(data_dir, "pull_up")
    if not store.profile_path.exists():
        raise ProfileNotFoundError(
            f"Profile not found at {store.profile_path}. Call init_profile() first."
        )
    store.update_language(lang)


def update_equipment(data_dir: Path, exercise_id: str, equipment_state: dict) -> None:
    """
    Activate a new equipment configuration for an exercise.

    ``equipment_state`` must be a dict with fields matching ``EquipmentState``:
    ``exercise_id``, ``available_items`` (list[str]), ``active_item`` (str),
    ``valid_from`` (ISO date string or None), ``valid_until`` (None — always
    None for a new entry).

    The previous active entry is automatically closed (valid_until = yesterday).
    """
    from ..core.models import EquipmentState
    from ..io.serializers import dict_to_equipment_state
    store = _require_store(data_dir, exercise_id)
    state_obj: EquipmentState = dict_to_equipment_state(equipment_state)
    store.update_equipment(state_obj)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


def log_session(data_dir: Path, exercise_id: str, session: dict) -> dict:
    """
    Append a training session to the history.

    ``session`` must be a dict with fields matching ``SessionResult``
    (see ``io/serializers.py``).  The most important required fields are:

    - ``date``             — ISO date string (YYYY-MM-DD)
    - ``bodyweight_kg``    — float
    - ``grip``             — exercise-specific variant string
    - ``session_type``     — one of ``"S"``, ``"H"``, ``"E"``, ``"T"``, ``"TEST"``
    - ``exercise_id``      — exercise identifier (must match the ``exercise_id`` arg)
    - ``completed_sets``   — list of set dicts

    Returns the serialised ``SessionResult`` dict that was persisted.
    """
    from ..io.serializers import dict_to_session_result
    store = _require_store(data_dir, exercise_id)
    session_obj: SessionResult = dict_to_session_result(session)
    store.append_session(session_obj)
    return session_result_to_dict(session_obj)


def delete_session(data_dir: Path, exercise_id: str, index: int) -> None:
    """
    Delete the session at the given 1-based position in sorted history.

    Raises ``SessionNotFoundError`` if ``index`` is out of range.
    """
    store = _require_store(data_dir, exercise_id)
    sessions = store.load_history()
    zero_based = index - 1
    if zero_based < 0 or zero_based >= len(sessions):
        raise SessionNotFoundError(
            f"Session {index} not found (history has {len(sessions)} sessions)."
        )
    store.delete_session_at(zero_based)


def get_history(data_dir: Path, exercise_id: str) -> list[dict]:
    """
    Return the full session history as a list of dicts, sorted by date.
    """
    store = _require_store(data_dir, exercise_id)
    sessions = store.load_history()
    return [session_result_to_dict(s) for s in sessions]


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


def get_plan(
    data_dir: Path,
    exercise_id: str = "pull_up",
    weeks_ahead: int = 4,
) -> dict:
    """
    Return the unified training timeline (past history + upcoming plan).

    Returns a dict with:

    - ``status``         — training status metrics (training_max, readiness, …)
    - ``sessions``       — list of timeline entry dicts (past + future)
    - ``plan_changes``   — list of human-readable change strings vs. the last
                           cached plan (empty list on first call)
    - ``overtraining``   — overtraining severity dict (level, description, …)
    """
    exercise = get_exercise(exercise_id)
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state()

    plan_start_date = _resolve_plan_start(store, user_state.history)
    total_weeks = _total_weeks(plan_start_date, weeks_ahead)

    ot_severity = overtraining_severity(
        user_state.history, user_state.profile.preferred_days_per_week
    )
    ot_level = ot_severity["level"]

    plans = generate_plan(
        user_state, plan_start_date, exercise,
        weeks_ahead=total_weeks,
        overtraining_level=ot_level,
    )

    training_status = _get_training_status(
        user_state.history,
        user_state.current_bodyweight_kg,
    )

    timeline = build_timeline(plans, user_state.history)

    # Plan change detection
    def _snapshot(e: TimelineEntry) -> dict:
        p = e.planned
        if p is None:
            return {}
        first_set = p.sets[0] if p.sets else None
        return {
            "date": p.date, "type": p.session_type,
            "sets": len(p.sets),
            "reps": first_set.target_reps if first_set else 0,
            "weight": first_set.added_weight_kg if first_set else 0.0,
            "rest": first_set.rest_seconds_before if first_set else 0,
            "expected_tm": p.expected_tm,
        }

    old_cache = store.load_plan_cache()
    new_cache = [
        _snapshot(e) for e in timeline
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
    store.save_plan_cache(new_cache)

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
        "sessions": [_timeline_entry_to_dict(e) for e in timeline],
        "plan_changes": plan_changes,
        "overtraining": ot_severity,
    }


def refresh_plan(data_dir: Path, exercise_id: str = "pull_up") -> dict:
    """
    Reset the plan anchor to today.

    Use after a break when unlogged sessions have piled up in the past.
    Returns a dict with ``plan_start_date`` and ``next_session``
    (or ``None`` if no sessions are generated).
    """
    exercise = get_exercise(exercise_id)
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state()

    today = datetime.now().strftime("%Y-%m-%d")
    store.set_plan_start_date(today)

    plans = generate_plan(user_state, today, exercise, weeks_ahead=2)
    next_session = next((p for p in plans if p.date >= today), None)

    return {
        "plan_start_date": today,
        "next_session": {
            "date": next_session.date,
            "session_type": next_session.session_type,
            "grip": next_session.grip,
        } if next_session else None,
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
    user_state = store.load_user_state()

    plan_start_date = _resolve_plan_start(store, user_state.history)
    total_weeks = _total_weeks(plan_start_date, weeks_ahead)

    days_per_week = user_state.profile.preferred_days_per_week
    ot_severity = overtraining_severity(user_state.history, days_per_week)
    ot_level = ot_severity["level"]
    ot_rest = ot_severity["extra_rest_days"] if ot_level >= 2 else 0

    today_dt = datetime.now()
    ot_cutoff = (today_dt + timedelta(days=max(ot_rest + 14, 14))).strftime("%Y-%m-%d")

    if date.lower() == "next":
        plans = generate_plan(
            user_state, plan_start_date, exercise,
            weeks_ahead=total_weeks,
            overtraining_level=ot_level, overtraining_rest_days=ot_rest,
        )
        today_str = today_dt.strftime("%Y-%m-%d")
        nxt = next((p for p in plans if p.date >= today_str), None)
        if nxt is None:
            raise ValueError("No upcoming sessions found in the plan horizon.")
        date = nxt.date

    if date > ot_cutoff:
        ot_level, ot_rest = 0, 0

    return explain_plan_entry(
        user_state, plan_start_date, date, exercise,
        weeks_ahead=total_weeks,
        overtraining_level=ot_level,
        overtraining_rest_days=ot_rest,
    )


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def get_training_status(data_dir: Path, exercise_id: str = "pull_up") -> dict:
    """
    Return current training status metrics.

    Includes training_max, latest_test_max, trend, plateau flag, deload
    recommendation, and fitness-fatigue state.
    """
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state()
    status = _get_training_status(user_state.history, user_state.current_bodyweight_kg)
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


def get_onerepmax_data(data_dir: Path, exercise_id: str = "pull_up") -> dict | None:
    """
    Estimate 1-rep max using multiple formulas.

    Returns ``None`` if there is not enough history data. Otherwise returns a
    dict with ``formulas`` (epley/brzycki/lander/lombardi/blended values in kg),
    ``recommended_formula``, ``best_reps``, ``best_added_weight_kg``,
    ``effective_load_kg``, and ``best_date``.
    """
    exercise = get_exercise(exercise_id)
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state()
    return estimate_1rm(exercise, user_state.current_bodyweight_kg, user_state.history)


def get_volume_data(
    data_dir: Path,
    exercise_id: str = "pull_up",
    weeks: int = 4,
) -> dict:
    """
    Return weekly rep volume for the last ``weeks`` weeks.

    Returns a dict with a ``"weeks"`` list, each element being:
    ``{"label": str, "week_start": str|None, "total_reps": int}``.
    Week 0 = current week, week 1 = last week, etc.
    """
    store = _require_store(data_dir, exercise_id)
    sessions = store.load_history()

    weekly: dict[int, dict] = {}
    if sessions:
        latest = datetime.strptime(sessions[-1].date, "%Y-%m-%d")
        for s in sessions:
            s_dt = datetime.strptime(s.date, "%Y-%m-%d")
            ago = (latest - s_dt).days // 7
            if ago < weeks:
                reps = sum(
                    sr.actual_reps for sr in s.completed_sets
                    if sr.actual_reps is not None
                )
                if ago not in weekly:
                    # Compute week start (Monday)
                    monday = s_dt - timedelta(days=s_dt.weekday())
                    weekly[ago] = {"total_reps": 0, "week_start": monday.strftime("%Y-%m-%d")}
                weekly[ago]["total_reps"] += reps

    result = []
    for i in range(weeks - 1, -1, -1):
        label = "This week" if i == 0 else ("Last week" if i == 1 else f"{i} weeks ago")
        entry = weekly.get(i, {})
        result.append({
            "label": label,
            "week_start": entry.get("week_start"),
            "total_reps": entry.get("total_reps", 0),
        })

    return {"weeks": result}


def get_progress_data(
    data_dir: Path,
    exercise_id: str = "pull_up",
    trajectory_types: str = "",
) -> dict:
    """
    Return raw data for plotting training progress.

    ``trajectory_types`` is a string of letters: ``z`` = BW reps trajectory,
    ``g`` = reps at goal weight, ``m`` = 1RM in added kg.

    Returns a dict with:
    - ``data_points`` — list of ``{"date": str, "max_reps": int}`` from TEST sessions
    - ``trajectory_z`` — projected BW reps over time (or ``None``)
    - ``trajectory_g`` — projected reps at goal weight (or ``None``)
    - ``trajectory_m`` — projected 1RM added kg over time (or ``None``)
    """
    from ..core.config import TARGET_MAX_REPS
    exercise_def = get_exercise(exercise_id)
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state()

    sessions = user_state.history
    test_sessions = get_test_sessions(sessions)

    data_points = [
        {"date": s.date, "max_reps": _session_max_reps(s)}
        for s in test_sessions
        if _session_max_reps(s) > 0
    ]

    traj_types = set(trajectory_types.lower())
    traj_z = None
    traj_g = None
    traj_m = None

    if traj_types and test_sessions:
        bw = user_state.current_bodyweight_kg
        bw_load = bw * exercise_def.bw_fraction
        traj_target = TARGET_MAX_REPS
        target_weight_kg = 0.0

        try:
            profile = store.load_profile()
            ex_target = profile.target_for_exercise(exercise_id) if profile else None
            if ex_target is not None:
                target_weight_kg = ex_target.weight_kg
                if ex_target.weight_kg > 0:
                    full_load = bw_load + ex_target.weight_kg
                    one_rm = full_load * (1 + ex_target.reps / 30)
                    traj_target = max(int(round(30 * (one_rm / bw_load - 1))), 1)
                else:
                    traj_target = ex_target.reps
        except Exception:
            pass

        # Build base trajectory points
        base_pts: list[tuple[datetime, float]] = []
        latest_test = test_sessions[-1]
        start_dt = datetime.strptime(latest_test.date, "%Y-%m-%d")
        initial_tm = training_max_from_baseline(_session_max_reps(latest_test))
        tm_target = int(traj_target * TM_FACTOR)
        d, tm_f = start_dt, float(initial_tm)
        while tm_f < tm_target and d <= start_dt + timedelta(weeks=104):
            base_pts.append((d, tm_f / TM_FACTOR))
            tm_f = min(
                tm_f + expected_reps_per_week(int(tm_f), tm_target),
                float(tm_target),
            )
            d += timedelta(weeks=1)
        base_pts.append((d, float(traj_target)))

        if "z" in traj_types and base_pts:
            traj_z = [
                {"date": pt.strftime("%Y-%m-%d"), "projected_bw_reps": round(val, 2)}
                for pt, val in base_pts
            ]

        if "g" in traj_types and base_pts:
            if target_weight_kg > 0:
                f = bw_load / (bw_load + target_weight_kg)
                pts_g = [(dt_, max(0.0, f * z + 30.0 * (f - 1.0))) for dt_, z in base_pts]
            else:
                pts_g = list(base_pts)
            traj_g = [
                {"date": pt.strftime("%Y-%m-%d"), "projected_goal_reps": round(val, 2)}
                for pt, val in pts_g
            ]

        if "m" in traj_types and base_pts and bw_load > 0:
            m_pts = []
            for pt, reps in base_pts:
                r = min(int(round(reps)), 20)
                added = blended_1rm_added(bw_load, max(r, 1))
                if added is not None:
                    m_pts.append({"date": pt.strftime("%Y-%m-%d"), "projected_1rm_added_kg": round(added, 2)})
            traj_m = m_pts or None

    return {
        "data_points": data_points,
        "trajectory_z": traj_z,
        "trajectory_g": traj_g,
        "trajectory_m": traj_m,
    }


def get_overtraining_status(data_dir: Path, exercise_id: str = "pull_up") -> dict:
    """
    Return the current overtraining severity assessment.

    Returns a dict with ``level`` (0–3), ``description``, and
    ``extra_rest_days``. Level 0 = no issue; level 3 = severe.
    """
    store = _require_store(data_dir, exercise_id)
    user_state = store.load_user_state()
    return overtraining_severity(
        user_state.history, user_state.profile.preferred_days_per_week
    )
