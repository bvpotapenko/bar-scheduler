"""Unit tests for the OmegaConf-backed model-config loader."""

from pathlib import Path

import pytest

from bar_scheduler.config import ModelConfig, load_model_config

NOWHERE = Path("/nonexistent/bar-scheduler/exercises.yaml")


@pytest.fixture
def bundled_path() -> Path:
    """Path to the real bundled exercises.yaml (model constants)."""
    return Path(__file__).parents[2] / "src" / "bar_scheduler" / "exercises.yaml"


def test_schema_defaults_when_no_files():
    """With no YAML sources the structured-schema defaults are returned."""
    cfg = load_model_config(bundled_path=NOWHERE, user_path=NOWHERE)
    assert cfg.progression.TM_FACTOR == 0.90
    assert cfg.progression.TARGET_MAX_REPS == 30
    assert cfg.rest_normalization.REST_REF_SECONDS == 180
    assert cfg.autoregulation.MIN_SESSIONS_FOR_AUTOREG == 3
    assert cfg.schedule.DAY_SPACING["T"] == 0


def test_bundled_values_loaded(bundled_path):
    """The bundled exercises.yaml overrides schema defaults section-by-section."""
    cfg = load_model_config(bundled_path=bundled_path, user_path=NOWHERE)
    assert cfg.progression.TM_FACTOR == 0.90
    assert cfg.fitness_fatigue.TAU_FATIGUE == 7.0
    assert cfg.fitness_fatigue.TAU_FITNESS == 42.0
    assert cfg.readiness.READINESS_Z_LOW == -0.5
    assert cfg.schedule.SCHEDULE_4_DAYS == ["S", "H", "T", "E"]
    assert cfg.schedule.DAY_SPACING == {"S": 1, "H": 1, "E": 1, "T": 0, "TEST": 1}


def test_user_override_deep_merges(bundled_path, tmp_path):
    """A user file overrides only the keys it names; siblings keep bundled values."""
    user = tmp_path / "exercises.yaml"
    user.write_text("progression:\n  TM_FACTOR: 0.85\n", encoding="utf-8")

    cfg = load_model_config(bundled_path=bundled_path, user_path=user)

    assert cfg.progression.TM_FACTOR == 0.85  # overridden
    assert cfg.progression.TARGET_MAX_REPS == 30  # sibling preserved (deep merge)
    assert cfg.rest_normalization.REST_REF_SECONDS == 180  # other section untouched


def test_returns_typed_model_config(bundled_path):
    """Result is a ModelConfig dataclass with attribute (not dict) access."""
    cfg = load_model_config(bundled_path=bundled_path, user_path=NOWHERE)
    assert isinstance(cfg, ModelConfig)
    assert cfg.plan_horizon.DEFAULT_PLAN_WEEKS == 4
