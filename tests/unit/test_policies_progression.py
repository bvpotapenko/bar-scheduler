"""Unit tests for the ProgressionPolicy."""

import pytest

from bar_scheduler.config.planning_params import ProgressionConfig
from bar_scheduler.core.exercises.registry import get_exercise
from bar_scheduler.core.policies.load import DEFAULT_SESSION_TARGET_REPS, LoadCalculator
from bar_scheduler.core.policies.progression import ProgressionPolicy
from bar_scheduler.domain.context import EquipmentConstraints, PrescriptionContext, ProgressionGoal


@pytest.fixture
def progression() -> ProgressionPolicy:
    load = LoadCalculator(tm_factor=0.9, session_target_reps=DEFAULT_SESSION_TARGET_REPS)
    return ProgressionPolicy(ProgressionConfig(), load)


def _ctx() -> PrescriptionContext:
    return PrescriptionContext(
        exercise=get_exercise("pull_up"),
        training_max=10,
        bodyweight_kg=80.0,
        history=(),
        session_type="S",
        equipment=EquipmentConstraints(),
    )


def test_reps_per_week_slows_toward_target(progression):
    assert progression.reps_per_week(10, 30) == pytest.approx(0.681, abs=1e-3)
    assert progression.reps_per_week(30, 30) == pytest.approx(0.0)  # at/over target


def test_weeks_to_target_positive_and_bounded(progression):
    weeks = progression.weeks_to_target(10, 15)
    assert 0 < weeks < 50


def test_weekly_delta_unweighted_goal(progression):
    delta = progression.weekly_delta(10.0, ProgressionGoal(reps=20), _ctx())
    assert delta == pytest.approx(progression.reps_per_week(10, 20))


def test_weekly_delta_weighted_goal_not_met_keeps_growing(progression):
    # Empty history -> projected weight 0 < goal weight -> keep progressing (>= DELTA min).
    delta = progression.weekly_delta(12.0, ProgressionGoal(reps=10, weight_kg=20.0), _ctx())
    assert delta >= ProgressionConfig().DELTA_PROGRESSION_MIN
