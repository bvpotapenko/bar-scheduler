"""Pure queries over session history."""

from bar_scheduler.domain.models import SessionResult


def session_max_reps(session: SessionResult) -> int:
    """Max actual reps across completed sets (prefers bodyweight-only sets)."""
    bw_only = [
        sr
        for sr in session.completed_sets
        if sr.actual_reps is not None and sr.added_weight_kg == 0
    ]
    if bw_only:
        return max(sr.actual_reps for sr in bw_only)
    all_done = [sr.actual_reps for sr in session.completed_sets if sr.actual_reps is not None]
    return max(all_done, default=0)


def session_total_reps(session: SessionResult) -> int:
    """Total actual reps across all completed sets."""
    return sum(sr.actual_reps for sr in session.completed_sets if sr.actual_reps is not None)


def session_avg_rest(session: SessionResult) -> float:
    """Average rest before completed sets, or 0.0 if none."""
    if not session.completed_sets:
        return 0.0
    total = sum(sr.rest_seconds_before for sr in session.completed_sets)
    return total / len(session.completed_sets)


def get_test_sessions(history: list[SessionResult]) -> list[SessionResult]:
    """All TEST sessions from history."""
    return [sess for sess in history if sess.session_type == "TEST"]


def latest_test_max(history: list[SessionResult]) -> int | None:
    """Max reps from the most recent TEST session, or None if no tests."""
    test_sessions = get_test_sessions(history)
    if not test_sessions:
        return None
    return session_max_reps(test_sessions[-1])


def overall_max_reps(history: list[SessionResult]) -> int:
    """Highest max reps from any TEST session, or 0."""
    test_sessions = get_test_sessions(history)
    if not test_sessions:
        return 0
    return max(session_max_reps(sess) for sess in test_sessions)
