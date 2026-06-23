"""
Timeline: merge planned sessions + logged history into a unified view.

This is pure computation -- no Rich, no Typer. The result is a list of
TimelineEntry objects suitable for display by any client (CLI, Telegram, web).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from bar_scheduler.core.max_estimator import estimate_max_reps_from_session
from bar_scheduler.domain.models import SessionPlan, SessionResult

TimelineStatus = Literal["done", "missed", "next", "planned", "extra"]


@dataclass
class TimelineEntry:
    """A single row in the unified plan/history timeline."""

    date: str
    week_number: int
    planned: SessionPlan | None  # None for unplanned (extra) sessions
    actual: SessionResult | None  # None for future sessions
    status: TimelineStatus
    actual_id: int | None = None  # 1-based ID in sorted history (for delete-record)
    track_b: dict | None = None  # Track B max estimate (fi_est, nuzzo_est, …)


def _compute_first_monday(history: list[SessionResult]) -> datetime | None:
    """Return the Monday of the week containing the first real session."""
    if not history:
        return None
    first_date = datetime.strptime(min(sess.date for sess in history), "%Y-%m-%d")
    return first_date - timedelta(days=first_date.weekday())


def _build_history_lookup(
    history: list[SessionResult],
) -> dict[str, list[tuple[int, SessionResult]]]:
    """Build a date -> [(orig_index, session)] mapping for fast plan matching."""
    lookup: dict[str, list[tuple[int, SessionResult]]] = {}
    for idx, sess in enumerate(history):
        lookup.setdefault(sess.date, []).append((idx, sess))
    return lookup


def _match_plan_to_history(
    plan: SessionPlan,
    history_by_date: dict[str, list[tuple[int, SessionResult]]],
    matched_indices: set[int],
) -> tuple[SessionResult | None, int | None]:
    """Find the best history session to pair with a plan entry."""
    candidates = history_by_date.get(plan.date, [])
    # Prefer same session type
    for orig_i, cs in candidates:
        if cs.session_type == plan.session_type and orig_i not in matched_indices:
            return cs, orig_i
    # Fall back to any session on that date
    for orig_i, cs in candidates:
        if orig_i not in matched_indices:
            return cs, orig_i
    return None, None


def _plan_status(
    matched: SessionResult | None,
    plan_date: str,
    today: str,
) -> TimelineStatus:
    if matched is None:
        return "missed" if plan_date < today else "planned"
    return "done"


def _compute_track_b(matched: SessionResult | None) -> dict | None:
    """Compute Track B max estimate for non-TEST sessions with ≥2 sets."""
    if matched is None or matched.session_type not in ("S", "H"):
        return None
    valid_sets = [
        cs for cs in matched.completed_sets if cs.actual_reps is not None and cs.actual_reps > 0
    ]
    if len(valid_sets) < 2:
        return None
    return estimate_max_reps_from_session(
        [cs.actual_reps for cs in valid_sets],  # type: ignore[misc]
        [cs.rest_seconds_before for cs in valid_sets],
        [cs.rir_reported for cs in valid_sets],
    )


def _assign_next_status(entries: list[TimelineEntry], today: str) -> None:
    """Mark the first upcoming/missed entry as 'next'."""
    for tl_entry in entries:
        if tl_entry.status in ("planned", "missed") and tl_entry.date >= today:
            tl_entry.status = "next"
            return
    # All future entries are done/missed; mark first planned as next
    for tl_entry in entries:
        if tl_entry.status == "planned":
            tl_entry.status = "next"
            return


def _add_extra_sessions(
    entries: list[TimelineEntry],
    history: list[SessionResult],
    matched_indices: set[int],
    first_monday: datetime | None,
) -> None:
    """Append unmatched history sessions as 'extra' (unplanned) entries."""
    for orig_i, sess in enumerate(history):
        if orig_i not in matched_indices:
            sess_dt = datetime.strptime(sess.date, "%Y-%m-%d")
            week_num = (sess_dt - first_monday).days // 7 + 1 if first_monday else 0
            entries.append(
                TimelineEntry(
                    date=sess.date,
                    week_number=week_num,
                    planned=None,
                    actual=sess,
                    status="done",
                    actual_id=orig_i + 1,
                )
            )


def build_timeline(
    plans: list[SessionPlan],
    history: list[SessionResult],
) -> list[TimelineEntry]:
    """
    Merge plan + history into a unified chronological timeline.

    Matching: a history session is matched to a plan entry if dates are
    within 1 day of each other and session types agree, or if dates match
    exactly regardless of type.

    Args:
        plans: Generated plan entries (may include past dates)
        history: Logged sessions

    Returns:
        Sorted list of TimelineEntry
    """
    today = datetime.now().strftime("%Y-%m-%d")
    first_monday = _compute_first_monday(history)
    history_by_date = _build_history_lookup(history)
    matched_indices: set[int] = set()
    entries: list[TimelineEntry] = []

    for plan in plans:
        matched, matched_idx = _match_plan_to_history(plan, history_by_date, matched_indices)
        if matched_idx is not None:
            matched_indices.add(matched_idx)

        entries.append(
            TimelineEntry(
                date=plan.date,
                week_number=plan.week_number,
                planned=plan,
                actual=matched,
                status=_plan_status(matched, plan.date, today),
                actual_id=None if matched_idx is None else matched_idx + 1,
                track_b=_compute_track_b(matched),
            )
        )

    _assign_next_status(entries, today)
    _add_extra_sessions(entries, history, matched_indices, first_monday)
    entries.sort(key=lambda tl_entry: tl_entry.date)
    return entries
