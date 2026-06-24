"""Shared store-access and metric helpers for the bar-scheduler API."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from bar_scheduler.api._errors import HistoryNotFoundError, ProfileNotFoundError
from bar_scheduler.core.math.formulas import best_onerm_from_leff
from bar_scheduler.domain.models import SessionResult
from bar_scheduler.io.user_store import UserStore


def _require_profile_store(data_dir: Path) -> UserStore:
    """Return a UserStore, raising ProfileNotFoundError if profile.json is missing."""
    store = UserStore(data_dir)
    if not store.profile_path.exists():
        raise ProfileNotFoundError(
            f"Profile not found at {store.profile_path}. Call init_profile() first."
        )
    return store


def _require_store(data_dir: Path, exercise_id: str) -> UserStore:
    """Return a UserStore, raising typed errors when profile or history files are missing."""
    store = _require_profile_store(data_dir)
    if not store.exists(exercise_id):
        raise HistoryNotFoundError(
            f"History file not found at {store.history_path(exercise_id)}. Call init_profile() first."
        )
    return store


def _resolve_plan_start(store: UserStore, exercise_id: str, history: list[SessionResult]) -> str:
    plan_start = store.get_plan_start_date(exercise_id)
    if plan_start is None:
        if history:
            first_dt = datetime.strptime(history[0].date, "%Y-%m-%d")
            plan_start = (first_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            plan_start = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return plan_start


def _total_weeks(plan_start_date: str, weeks_ahead: int = 4) -> int:
    from bar_scheduler.core.config import MAX_PLAN_WEEKS

    plan_start_dt = datetime.strptime(plan_start_date, "%Y-%m-%d")
    weeks_since_start = max(0, (datetime.now() - plan_start_dt).days // 7)
    return max(2, min(weeks_since_start + weeks_ahead, MAX_PLAN_WEEKS * 3))


def _assistance_for_item(active_item: str, eq_state, ctx) -> float | None:
    """Prescribed machine/band assistance for the recommended item (None otherwise)."""
    from bar_scheduler.containers import container

    calc = container.load_calculator()
    if active_item == "MACHINE_ASSISTED" and eq_state.available_machine_assistance_kg:
        return calc.machine_assistance(ctx)
    if active_item == "BAND_SET" and eq_state.available_band_assistance_kg:
        return calc.band_assistance(ctx)
    return None


def _best_onerm(sets_leff_reps: list[tuple[float, int]]) -> float | None:
    """Highest blended 1RM estimate across (leff, reps) pairs, or None."""
    best: float | None = None
    for leff, reps in sets_leff_reps:
        est = best_onerm_from_leff(leff, reps)
        if est is not None and (best is None or est > best):
            best = est
    return best


def _session_performance_metrics(sets_leff_reps: list[tuple[float, int]]) -> dict:
    """Compute volume_session, avg_volume_set, estimated_1rm from (leff, reps) pairs."""
    volume_session = sum(leff * reps for leff, reps in sets_leff_reps)
    avg_volume_set = volume_session / len(sets_leff_reps) if sets_leff_reps else 0.0
    best = _best_onerm(sets_leff_reps)
    return {
        "volume_session": round(volume_session, 2),
        "avg_volume_set": round(avg_volume_set, 2),
        "estimated_1rm": None if best is None else round(best, 2),
    }
