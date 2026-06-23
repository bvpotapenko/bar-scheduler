"""Unit tests for the lazy, per-exercise OmegaConf repository."""

from pathlib import Path

import pytest

from bar_scheduler.core.exercises.base import ExerciseDefinition
from bar_scheduler.core.exercises.repository import ExerciseRepository

BUNDLED = Path(__file__).parents[2] / "src" / "bar_scheduler" / "exercises"


@pytest.fixture
def repo() -> ExerciseRepository:
    return ExerciseRepository(bundled_dir=BUNDLED, user_dir=Path("/nonexistent"))


def test_get_loads_typed_definition(repo):
    pull_up = repo.get("pull_up")
    assert isinstance(pull_up, ExerciseDefinition)
    assert pull_up.exercise_id == "pull_up"
    assert pull_up.bw_fraction == 1.0
    assert pull_up.load_type == "bw_plus_external"
    assert pull_up.weight_tm_threshold == 9
    assert pull_up.level_thresholds == [4, 13, 24]
    assert pull_up.session_params["S"].reps_min == 4
    assert pull_up.session_params["S"].sets_by_level == [1, 2, 3, 4]


def test_list_available_enumerates_bundled(repo):
    assert set(repo.list_available()) >= {"pull_up", "dip", "bss", "incline_db_press"}


def test_unknown_exercise_raises(repo):
    with pytest.raises(ValueError, match="Unknown exercise"):
        repo.get("does_not_exist")


def test_user_override_deep_merges(tmp_path):
    user = tmp_path / "exercises"
    user.mkdir()
    (user / "pull_up.yaml").write_text("target_value: 25.0\n", encoding="utf-8")

    repo = ExerciseRepository(bundled_dir=BUNDLED, user_dir=user)
    pull_up = repo.get("pull_up")

    assert pull_up.target_value == 25.0  # overridden by user file
    assert pull_up.bw_fraction == 1.0  # bundled value preserved (deep merge)


def test_non_ascending_level_thresholds_rejected(tmp_path):
    bundled = tmp_path / "exercises"
    bundled.mkdir()
    base = (BUNDLED / "pull_up.yaml").read_text(encoding="utf-8")
    broken = base.replace("level_thresholds: [4, 13, 24]", "level_thresholds: [13, 4, 24]")
    (bundled / "pull_up.yaml").write_text(broken, encoding="utf-8")

    repo = ExerciseRepository(bundled_dir=bundled, user_dir=Path("/nonexistent"))
    with pytest.raises(ValueError, match="ascending"):
        repo.get("pull_up")
