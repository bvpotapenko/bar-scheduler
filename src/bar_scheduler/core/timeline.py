"""
Timeline: merge planned sessions + logged history into a unified view.

This is pure computation — no Rich, no Typer. The result is a list of
TimelineEntry objects suitable for display by any client (CLI, Telegram, web).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .max_estimator import estimate_max_reps_from_session
from .models import SessionPlan, SessionResult

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

    # Stable week-number anchor: Monday of the week containing the first real session.
    # Anchoring to Monday means Mon-Sun calendar weeks stay together (e.g. sessions
    # on Mon 03.02 and Wed 03.04 both appear as "week 3", not split across weeks).
    first_date: datetime | None = (
        datetime.strptime(min(s.date for s in history), "%Y-%m-%d")
        if history else None
    )
    first_monday: datetime | None = (
        first_date - timedelta(days=first_date.weekday()) if first_date is not None else None
    )

    # Build lookup: date -> list of (original_index, session) pairs
    history_by_date: dict[str, list[tuple[int, SessionResult]]] = {}
    for i, s in enumerate(history):
        history_by_date.setdefault(s.date, []).append((i, s))

    # Track which history sessions have been matched (by original index)
    matched_indices: set[int] = set()

    entries: list[TimelineEntry] = []

    for plan in plans:
        # Try to find a matching history session (same date, prefer same type)
        matched: SessionResult | None = None
        matched_idx: int | None = None

        candidates = history_by_date.get(plan.date, [])
        # Prefer same session type
        for orig_i, s in candidates:
            if s.session_type == plan.session_type and orig_i not in matched_indices:
                matched = s
                matched_idx = orig_i
                break
        # Fall back to any session on that date
        if matched is None:
            for orig_i, s in candidates:
                if orig_i not in matched_indices:
                    matched = s
                    matched_idx = orig_i
                    break

        if matched_idx is not None:
            matched_indices.add(matched_idx)

        # Determine status — "next" is assigned by the second pass below
        if matched is not None:
            status: TimelineStatus = "done"
        elif plan.date < today:
            status = "missed"
        else:
            status = "planned"

        # Compute Track B estimate for past non-TEST sessions with ≥2 sets
        track_b: dict | None = None
        if matched is not None and matched.session_type in ("S", "H"):
            valid_sets = [s for s in matched.completed_sets if s.actual_reps is not None and s.actual_reps > 0]
            if len(valid_sets) >= 2:
                track_b = estimate_max_reps_from_session(
                    [s.actual_reps for s in valid_sets],       # type: ignore[misc]
                    [s.rest_seconds_before for s in valid_sets],
                    [s.rir_reported for s in valid_sets],
                )

        entries.append(
            TimelineEntry(
                date=plan.date,
                week_number=plan.week_number,
                planned=plan,
                actual=matched,
                status=status,
                actual_id=matched_idx + 1 if matched_idx is not None else None,
                track_b=track_b,
            )
        )

    # Find first non-done future entry and mark as "next"
    set_next = False
    for e in entries:
        if e.status in ("planned", "missed") and e.date >= today:
            e.status = "next" if not set_next else "planned"
            set_next = True
            break
    if not set_next:
        # All past or today is next
        for e in entries:
            if e.status == "planned":
                e.status = "next"
                break

    # Add any extra (unplanned) history sessions not matched to a plan
    for orig_i, s in enumerate(history):
        if orig_i not in matched_indices:
            session_dt = datetime.strptime(s.date, "%Y-%m-%d")
            wn = (session_dt - first_monday).days // 7 + 1 if first_monday else 0
            entries.append(
                TimelineEntry(
                    date=s.date,
                    week_number=wn,
                    planned=None,
                    actual=s,
                    status="done",
                    actual_id=orig_i + 1,
                )
            )

    entries.sort(key=lambda e: e.date)
    return entries
