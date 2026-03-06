"""Adaptive rest duration calculation based on fatigue signals."""

import math

from ..config import DROP_OFF_THRESHOLD, READINESS_Z_LOW
from ..exercises.base import ExerciseDefinition
from ..exercises.registry import get_exercise
from ..models import SessionResult, SessionType

PULL_UP = get_exercise("pull_up")


def _analyze_rir(sets: list, rest: int) -> int:
    """
    Adjust rest based on RIR values from the last session's sets.

    Any set with RIR ≤ 1 → +30 s (near failure).
    All sets with RIR ≥ 3 → −15 s (felt easy).
    """
    rirs = [s.rir_reported for s in sets if s.rir_reported is not None]
    if not rirs:
        return rest
    if any(r <= 1 for r in rirs):
        return rest + 30
    if all(r >= 3 for r in rirs):
        return rest - 15
    return rest


def _analyze_rep_drop(sets: list, rest: int) -> int:
    """
    Adjust rest based on within-session rep drop-off.

    Drop-off > DROP_OFF_THRESHOLD → +15 s.
    """
    reps_list = [s.actual_reps for s in sets if s.actual_reps is not None]
    if len(reps_list) >= 2 and reps_list[0] > 0:
        drop_off = (reps_list[0] - reps_list[-1]) / reps_list[0]
        if drop_off > DROP_OFF_THRESHOLD:
            return rest + 15
    return rest


def _adjust_for_readiness(ff_state, rest: int) -> int:
    """
    Adjust rest based on readiness z-score.

    z < READINESS_Z_LOW → +30 s.
    """
    if ff_state is None:
        return rest
    readiness = ff_state.fitness - ff_state.fatigue
    readiness_var = max(ff_state.readiness_var, 0.01)
    z = (readiness - ff_state.readiness_mean) / math.sqrt(readiness_var)
    if z < READINESS_Z_LOW:
        return rest + 30
    return rest


def _adjust_for_user_rest_pattern(
    recent_sessions: list[SessionResult],
    rest: int,
    params,
) -> int:
    """
    Shift rest prescription toward the user's actual rest behaviour.

    Avg actual rest < rest_min × 0.85 → −20 s (user consistently rests short).
    Avg actual rest > rest_max × 1.10 → +20 s (user needs more rest).
    Only applied when ≥ 3 actual-rest data points exist.
    """
    actual_rests = [
        s.rest_seconds_before
        for session in recent_sessions
        for s in session.completed_sets
        if s.rest_seconds_before > 0
    ]
    if len(actual_rests) < 3:
        return rest
    avg_actual = sum(actual_rests) / len(actual_rests)
    if avg_actual < params.rest_min * 0.85:
        return rest - 20
    if avg_actual > params.rest_max * 1.10:
        return rest + 20
    return rest


def calculate_adaptive_rest(
    session_type: SessionType,
    recent_sessions: list[SessionResult],
    ff_state,
    exercise: ExerciseDefinition = PULL_UP,
) -> int:
    """
    Calculate adaptive rest based on recent same-type session performance and readiness.

    Adjustments from midpoint:
    - Any set with RIR <= 1: +30s (session was near failure)
    - Drop-off > DROP_OFF_THRESHOLD: +15s (within-session fatigue)
    - Readiness z-score < READINESS_Z_LOW: +30s (low readiness)
    - All sets RIR >= 3: -15s (session felt easy)
    - Avg actual rest across sessions < rest_min*0.85: -20s (user rests short)
    - Avg actual rest across sessions > rest_max*1.10: +20s (user needs more rest)
    Clamped to [rest_min, rest_max].

    Args:
        session_type: Session type
        recent_sessions: Last few sessions of this same type from history
        ff_state: Fitness-fatigue state
        exercise: ExerciseDefinition with session params

    Returns:
        Recommended rest in seconds
    """
    params = exercise.session_params[session_type]
    rest = (params.rest_min + params.rest_max) // 2

    if not recent_sessions:
        return rest

    last = recent_sessions[-1]
    sets = [s for s in last.completed_sets if s.actual_reps is not None]

    if not sets:
        return rest

    rest = _analyze_rir(sets, rest)
    rest = _analyze_rep_drop(sets, rest)
    rest = _adjust_for_readiness(ff_state, rest)
    rest = _adjust_for_user_rest_pattern(recent_sessions, rest, params)

    return max(params.rest_min, min(params.rest_max, rest))
