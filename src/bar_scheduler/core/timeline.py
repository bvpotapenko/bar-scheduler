"""
Timeline: merge planned sessions + logged history into a unified view.

This is pure computation -- no Rich, no Typer. The result is a list of
TimelineEntry objects suitable for display by any client (CLI, Telegram, web).
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Literal

from bar_scheduler.core.policies.max_estimation import MaxEstimator
from bar_scheduler.domain.models import SessionPlan, SessionResult

_MAX_ESTIMATOR = MaxEstimator()

TimelineStatus = Literal["done", "missed", "next", "planned", "extra"]

_Indexed = tuple[int, SessionResult]
_Lookup = dict[str, list[_Indexed]]


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


def _build_history_lookup(history: list[SessionResult]) -> _Lookup:
    """Build a date -> [(orig_index, session)] mapping for fast plan matching."""
    lookup: _Lookup = {}
    for idx, sess in enumerate(history):
        lookup.setdefault(sess.date, []).append((idx, sess))
    return lookup


def _match_plan_to_history(
    plan: SessionPlan, lookup: _Lookup, matched: set[int]
) -> _Indexed | tuple[None, None]:
    """Find the best unmatched history session to pair with a plan entry."""
    candidates = lookup.get(plan.date, [])
    for orig_i, cand in candidates:
        if cand.session_type == plan.session_type and orig_i not in matched:
            return cand, orig_i
    for orig_i, cand in candidates:
        if orig_i not in matched:
            return cand, orig_i
    return None, None


def _compute_track_b(matched: SessionResult | None) -> dict | None:
    """Compute Track B max estimate for non-TEST S/H sessions with ≥2 sets."""
    if matched is None or matched.session_type not in ("S", "H"):
        return None
    valid = [cs for cs in matched.completed_sets if cs.actual_reps]
    if len(valid) < 2:
        return None
    estimate = _MAX_ESTIMATOR.estimate(
        [cs.actual_reps for cs in valid],
        [cs.rest_seconds_before for cs in valid],
        [cs.rir_reported for cs in valid],
    )
    return None if estimate is None else asdict(estimate)


class _TimelineBuilder:
    """Assemble the merged timeline, carrying match state across plan entries."""

    def __init__(self, plans: list[SessionPlan], history: list[SessionResult]) -> None:
        self._plans = plans
        self._history = history
        self._today = datetime.now().strftime("%Y-%m-%d")
        self._lookup = _build_history_lookup(history)
        self._matched: set[int] = set()
        self._entries: list[TimelineEntry] = []

    def build(self) -> list[TimelineEntry]:
        """Pair plans with history, mark the next session, append extras, sort."""
        self._entries = [self._entry_for_plan(plan) for plan in self._plans]
        self._assign_next()
        self._add_extra(_compute_first_monday(self._history))
        self._entries.sort(key=lambda tl_entry: tl_entry.date)
        return self._entries

    def _entry_for_plan(self, plan: SessionPlan) -> TimelineEntry:
        matched, matched_idx = _match_plan_to_history(plan, self._lookup, self._matched)
        if matched_idx is not None:
            self._matched.add(matched_idx)
        return TimelineEntry(
            date=plan.date,
            week_number=plan.week_number,
            planned=plan,
            actual=matched,
            status=self._plan_status(matched, plan.date),
            actual_id=None if matched_idx is None else matched_idx + 1,
            track_b=_compute_track_b(matched),
        )

    def _plan_status(self, matched: SessionResult | None, plan_date: str) -> TimelineStatus:
        if matched is None:
            return "missed" if plan_date < self._today else "planned"
        return "done"

    def _assign_next(self) -> None:
        """Mark the first upcoming/missed entry (or first planned) as 'next'."""
        for tl_entry in self._entries:
            if tl_entry.status in ("planned", "missed") and tl_entry.date >= self._today:
                tl_entry.status = "next"
                return
        for tl_entry in self._entries:
            if tl_entry.status == "planned":
                tl_entry.status = "next"
                return

    def _add_extra(self, first_monday: datetime | None) -> None:
        for orig_i, sess in enumerate(self._history):
            if orig_i not in self._matched:
                self._entries.append(self._extra_entry(orig_i, sess, first_monday))

    def _extra_entry(
        self, orig_i: int, sess: SessionResult, first_monday: datetime | None
    ) -> TimelineEntry:
        sess_dt = datetime.strptime(sess.date, "%Y-%m-%d")
        week_num = (sess_dt - first_monday).days // 7 + 1 if first_monday else 0
        return TimelineEntry(
            date=sess.date,
            week_number=week_num,
            planned=None,
            actual=sess,
            status="done",
            actual_id=orig_i + 1,
        )


def build_timeline(plans: list[SessionPlan], history: list[SessionResult]) -> list[TimelineEntry]:
    """Merge plan + history into a unified, date-sorted timeline."""
    return _TimelineBuilder(plans, history).build()
