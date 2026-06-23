"""Typed, OmegaConf-backed configuration for the training model."""

from bar_scheduler.config.loader import (
    default_bundled_config_path,
    default_user_config_path,
    load_model_config,
)
from bar_scheduler.config.schema import ModelConfig

__all__ = [
    "ModelConfig",
    "load_model_config",
    "default_bundled_config_path",
    "default_user_config_path",
]
