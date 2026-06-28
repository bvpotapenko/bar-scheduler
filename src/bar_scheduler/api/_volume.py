"""Weekly training-volume aggregation for the bar-scheduler API."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from bar_scheduler.api._common import _require_store


def _accumulate_week(weekly: dict[int, dict], sess, latest: datetime, weeks: int) -> None:
    """Add one session's reps into its week bucket (weeks-ago key)."""
    sess_dt = datetime.strptime(sess.date, "%Y-%m-%d")
    ago = (latest - sess_dt).days // 7
    if ago >= weeks:
        return
    reps = sum(sr.actual_reps for sr in sess.completed_sets if sr.actual_reps is not None)
    if ago not in weekly:
        monday = sess_dt - timedelta(days=sess_dt.weekday())
        weekly[ago] = {"total_reps": 0, "week_start": monday.strftime("%Y-%m-%d")}
    weekly[ago]["total_reps"] += reps


def _weekly_reps(sessions: list, weeks: int) -> dict[int, dict]:
    weekly: dict[int, dict] = {}
    if not sessions:
        return weekly
    latest = datetime.strptime(sessions[-1].date, "%Y-%m-%d")
    for sess in sessions:
        _accumulate_week(weekly, sess, latest, weeks)
    return weekly


def _week_label(week_ago: int) -> str:
    if week_ago == 0:
        return "This week"
    if week_ago == 1:
        return "Last week"
    return f"{week_ago} weeks ago"


def _volume_rows(weekly: dict[int, dict], weeks: int) -> list[dict]:
    rows = []
    for week_ago in range(weeks - 1, -1, -1):
        entry = weekly.get(week_ago, {})
        rows.append(
            {
                "label": _week_label(week_ago),
                "week_start": entry.get("week_start"),
                "total_reps": entry.get("total_reps", 0),
            }
        )
    return rows


def get_volume_data(data_dir: Path, exercise_id: str, weeks: int = 4) -> dict:
    """
    Return weekly rep volume for the last ``weeks`` weeks.

    Returns a dict with a ``"weeks"`` list, each element being:
    ``{"label": str, "week_start": str|None, "total_reps": int}``.
    Week 0 = current week, week 1 = last week, etc.
    """
    store = _require_store(data_dir, exercise_id)
    weekly = _weekly_reps(store.history.load(exercise_id), weeks)
    return {"weeks": _volume_rows(weekly, weeks)}
