"""Shared fixtures for the unit suite."""

import pytest

from bar_scheduler import api


@pytest.fixture
def data_dir(tmp_path):
    """A profile with pull_up enabled and one TEST + one S session logged."""
    api.init_profile(tmp_path, height_cm=180, bodyweight_kg=80.0)
    api.enable_exercise(tmp_path, "pull_up", days_per_week=3)
    api.log_session(
        tmp_path,
        "pull_up",
        api.SessionInput(
            date="2026-01-04",
            session_type="TEST",
            bodyweight_kg=80.0,
            sets=[api.SetInput(reps=12, rest_seconds=180, added_weight_kg=0.0)],
        ),
    )
    api.log_session(
        tmp_path,
        "pull_up",
        api.SessionInput(
            date="2026-01-06",
            session_type="S",
            bodyweight_kg=80.0,
            sets=[
                api.SetInput(reps=5, rest_seconds=180, added_weight_kg=0.0),
                api.SetInput(reps=4, rest_seconds=180, added_weight_kg=0.0),
            ],
        ),
    )
    return tmp_path
