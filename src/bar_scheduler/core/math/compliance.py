"""Planned-vs-actual compliance ratios."""

from datetime import datetime, timedelta

from bar_scheduler.domain.models import SessionResult, SetResult


def compliance_ratio(planned_sets: list[SetResult], completed_sets: list[SetResult]) -> float:
    """Actual reps / planned reps (inf if planned 0 but reps were done)."""
    planned_total = sum(sr.target_reps for sr in planned_sets)
    actual_total = sum(sr.actual_reps for sr in completed_sets if sr.actual_reps is not None)
    if planned_total == 0:
        return 1.0 if actual_total == 0 else float("inf")
    return actual_total / planned_total


def session_compliance(session: SessionResult) -> float:
    """Compliance ratio for a single session."""
    return compliance_ratio(session.planned_sets, session.completed_sets)


def weekly_compliance(history: list[SessionResult], weeks_back: int = 1) -> float:
    """Average session compliance over the last ``weeks_back`` weeks."""
    if not history:
        return 1.0
    latest = datetime.strptime(history[-1].date, "%Y-%m-%d")
    cutoff = latest - timedelta(days=weeks_back * 7)
    recent = [sess for sess in history if datetime.strptime(sess.date, "%Y-%m-%d") >= cutoff]
    if not recent:
        return 1.0
    ratios = [session_compliance(sess) for sess in recent]
    return sum(ratios) / len(ratios)
