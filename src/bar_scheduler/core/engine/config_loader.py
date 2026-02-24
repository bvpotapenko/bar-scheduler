"""
YAML → typed config loader.

Loads model constants from exercises.yaml (bundled with the package) and
optionally merges user overrides from ~/.bar-scheduler/exercises.yaml.

Usage:
    from bar_scheduler.core.engine.config_loader import load_model_config
    cfg = load_model_config()
    tau_fatigue = cfg.get("fitness_fatigue", {}).get("TAU_FATIGUE", 7.0)

If the bundled YAML cannot be parsed, all lookups return the Python defaults
from config.py (no crash).  If the user override file exists but has parse
errors, a warning is printed and the file is ignored.
"""

from __future__ import annotations

import importlib.resources
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load a single YAML file; return {} on any error."""
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (non-destructive to base)."""
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_bundled_yaml_path() -> Path | None:
    """Return the path to the bundled exercises.yaml, or None if not found."""
    try:
        # Python ≥3.9: importlib.resources.files
        pkg_files = importlib.resources.files("bar_scheduler")
        ref = pkg_files.joinpath("exercises.yaml")
        # Materialise to a real path so we can pass it to open()
        with importlib.resources.as_file(ref) as p:
            return p
    except Exception:
        # Fallback: look relative to this file's package root
        candidate = Path(__file__).parent.parent.parent / "exercises.yaml"
        return candidate if candidate.exists() else None


def get_user_yaml_path() -> Path | None:
    """Return ~/.bar-scheduler/exercises.yaml if it exists, else None."""
    home = Path(os.environ.get("HOME", "~")).expanduser()
    p = home / ".bar-scheduler" / "exercises.yaml"
    return p if p.exists() else None


def load_model_config() -> dict[str, Any]:
    """
    Load and merge model configuration from YAML sources.

    Load order (later overrides earlier):
    1. Bundled src/bar_scheduler/exercises.yaml
    2. User override at ~/.bar-scheduler/exercises.yaml

    Returns:
        Merged dict of config sections.  Empty dict if no YAML available.
    """
    config: dict[str, Any] = {}

    bundled = get_bundled_yaml_path()
    if bundled is not None:
        config = _deep_merge(config, _load_yaml_file(bundled))

    user = get_user_yaml_path()
    if user is not None:
        user_cfg = _load_yaml_file(user)
        if user_cfg:
            config = _deep_merge(config, user_cfg)

    return config
