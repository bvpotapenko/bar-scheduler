"""Load and merge model config from YAML via OmegaConf.

Replaces the hand-rolled deep-merge / yaml.safe_load loader. The structured
schema provides type coercion, defaults, and validation; OmegaConf provides
the bundled-then-user deep merge.
"""

from importlib import resources as importlib_resources
import os
from pathlib import Path

from omegaconf import OmegaConf

from bar_scheduler.config.schema import ModelConfig


def default_bundled_config_path() -> Path | None:
    """Path to the bundled ``exercises.yaml`` shipped with the package."""
    try:
        ref = importlib_resources.files("bar_scheduler").joinpath("exercises.yaml")
        with importlib_resources.as_file(ref) as path:
            return path if path.exists() else None
    except (ModuleNotFoundError, FileNotFoundError):
        candidate = Path(__file__).parent.parent / "exercises.yaml"
        return candidate if candidate.exists() else None


def default_user_config_path() -> Path:
    """Path to the optional user override ``~/.bar-scheduler/exercises.yaml``."""
    home = Path(os.environ.get("HOME", "~")).expanduser()
    return home / ".bar-scheduler" / "exercises.yaml"


def load_model_config(
    bundled_path: Path | None = None,
    user_path: Path | None = None,
) -> ModelConfig:
    """Merge schema defaults < bundled YAML < user YAML into a typed config.

    Paths default to the bundled package file and the user home override.
    Missing files are skipped, so the structured-schema defaults always win
    as the final fallback.
    """
    bundled = default_bundled_config_path() if bundled_path is None else bundled_path
    user = default_user_config_path() if user_path is None else user_path

    merged = OmegaConf.structured(ModelConfig)
    for source in (bundled, user):
        if source is not None and source.exists():
            merged = OmegaConf.merge(merged, OmegaConf.load(source))

    return OmegaConf.to_object(merged)
