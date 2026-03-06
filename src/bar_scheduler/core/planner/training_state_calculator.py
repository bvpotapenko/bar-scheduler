"""Compute initial training state at plan-generation time."""

from ..adaptation import get_training_status
from ..config import TM_FACTOR
from ..exercises.base import ExerciseDefinition
from ..models import SessionResult, TrainingStatus, UserState


def _extract_last_test_weight(
    history_for_init: list[SessionResult],
    exercise: ExerciseDefinition,
) -> float:
    """
    Extract the dumbbell weight from the most recent TEST session.

    Used for external_only exercises (e.g. BSS) where the strength load
    is carried forward from the last test rather than computed from TM.

    Returns:
        Last test added weight in kg, or 0.0 if none found.
    """
    if exercise.load_type != "external_only":
        return 0.0
    test_hist = [s for s in history_for_init if s.session_type == "TEST"]
    if not test_hist or not test_hist[-1].completed_sets:
        return 0.0
    weights = [
        s.added_weight_kg for s in test_hist[-1].completed_sets
        if s.added_weight_kg > 0
    ]
    return weights[-1] if weights else 0.0


def compute_training_state(
    user_state: UserState,
    history: list[SessionResult],
    history_for_init: list[SessionResult],
    exercise: ExerciseDefinition,
    baseline_max: int | None,
) -> tuple:
    """
    Compute all training-state values needed to start plan generation.

    Applies the plan-stability invariant: only pre-plan sessions (history_for_init)
    are used for TM, FF state, and initial autoregulation; full history is used
    for week-number anchoring and TEST scheduling.

    Args:
        user_state: Current user state with profile and history
        history: Full filtered exercise history (non-REST sessions only)
        history_for_init: Pre-plan-start sessions (subset of history)
        exercise: Exercise being planned
        baseline_max: Fallback baseline if no history

    Returns:
        (status, initial_tm, ff_state, z_score, last_test_weight)
        where status is TrainingStatus, ff_state is FitnessFatigueState,
        z_score is float, last_test_weight is float.
    """
    effective_init = history_for_init if history_for_init else history

    status: TrainingStatus = get_training_status(
        effective_init, user_state.current_bodyweight_kg, baseline_max
    )
    initial_tm = status.training_max
    if initial_tm <= 1 and baseline_max is not None:
        initial_tm = int(baseline_max * TM_FACTOR) or baseline_max

    ff_state = status.fitness_fatigue_state
    z_score = ff_state.readiness_z_score()

    last_test_weight = _extract_last_test_weight(effective_init, exercise)

    return status, initial_tm, ff_state, z_score, last_test_weight
