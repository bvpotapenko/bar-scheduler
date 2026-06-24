"""Adaptive rest duration from recent-session fatigue signals and readiness."""

from bar_scheduler.core.exercises.base import ExerciseDefinition, SessionTypeParams
from bar_scheduler.domain.models import FitnessFatigueState, SessionResult, SetResult

# Rest adjustments (seconds) and user-pattern bounds.
_NEAR_FAILURE = 30
_FELT_EASY = -15
_HIGH_DROP_OFF = 15
_USER_SHORT = -20
_USER_LONG = 20
_SHORT_BOUND = 0.85
_LONG_BOUND = 1.1


def _analyze_rir(sets: list[SetResult], rest: int) -> int:
    """+30s if any set near failure (RIR<=1); -15s if all felt easy (RIR>=3)."""
    rirs = [sr.rir_reported for sr in sets if sr.rir_reported is not None]
    if not rirs:
        return rest
    if any(rir <= 1 for rir in rirs):
        return rest + _NEAR_FAILURE
    if all(rir >= 3 for rir in rirs):
        return rest + _FELT_EASY
    return rest


def _analyze_rep_drop(sets: list[SetResult], rest: int, drop_off_threshold: float) -> int:
    """+15s when within-session rep drop-off exceeds the threshold."""
    reps = [sr.actual_reps for sr in sets if sr.actual_reps is not None]
    if len(reps) < 2 or reps[0] <= 0:
        return rest
    drop_off = (reps[0] - reps[-1]) / reps[0]
    return rest + _HIGH_DROP_OFF if drop_off > drop_off_threshold else rest


def _adjust_for_readiness(ff_state: FitnessFatigueState | None, rest: int, z_low: float) -> int:
    """+30s when readiness z-score is below the low threshold."""
    if ff_state is None:
        return rest
    return rest + _NEAR_FAILURE if ff_state.readiness_z_score() < z_low else rest


def _actual_rests(recent_sessions: list[SessionResult]) -> list[int]:
    return [
        sr.rest_seconds_before
        for session in recent_sessions
        for sr in session.completed_sets
        if sr.rest_seconds_before > 0
    ]


def _adjust_for_user_pattern(
    recent: list[SessionResult], rest: int, sparams: SessionTypeParams
) -> int:
    """Shift toward the user's actual rest behaviour (needs >=3 data points)."""
    rests = _actual_rests(recent)
    if len(rests) < 3:
        return rest
    avg = sum(rests) / len(rests)
    if avg < sparams.rest_min * _SHORT_BOUND:
        return rest + _USER_SHORT
    if avg > sparams.rest_max * _LONG_BOUND:
        return rest + _USER_LONG
    return rest


class RestAdvisor:
    """Recommend rest seconds from recent same-type sessions and readiness."""

    def __init__(self, drop_off_threshold: float, readiness_z_low: float) -> None:
        self._drop_off = drop_off_threshold
        self._z_low = readiness_z_low

    def recommend(
        self,
        session_type: str,
        recent_sessions: list[SessionResult],
        ff_state: FitnessFatigueState | None,
        exercise: ExerciseDefinition,
    ) -> int:
        """Midpoint rest adjusted by RIR, drop-off, readiness, and user pattern."""
        sparams = exercise.session_params[session_type]
        rest = (sparams.rest_min + sparams.rest_max) // 2
        sets = self._last_sets(recent_sessions)
        if not sets:
            return rest
        rest = _analyze_rir(sets, rest)
        rest = _analyze_rep_drop(sets, rest, self._drop_off)
        rest = _adjust_for_readiness(ff_state, rest, self._z_low)
        rest = _adjust_for_user_pattern(recent_sessions, rest, sparams)
        return max(sparams.rest_min, min(sparams.rest_max, rest))

    def _last_sets(self, recent_sessions: list[SessionResult]) -> list[SetResult]:
        if not recent_sessions:
            return []
        return [sr for sr in recent_sessions[-1].completed_sets if sr.actual_reps is not None]
