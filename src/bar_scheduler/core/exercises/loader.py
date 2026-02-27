"""
YAML → ExerciseDefinition loader.

Loads exercise definitions from individual YAML files in the bundled
``src/bar_scheduler/exercises/`` directory.  Each file (e.g. pull_up.yaml)
contains a flat exercise definition matching the ExerciseDefinition schema.

User overrides: place matching files in ``~/.bar-scheduler/exercises/``.
A user file is deep-merged over the bundled definition, so only changed
keys need to be listed.  A user file whose exercise_id does not match any
bundled file is treated as a new exercise and added to the registry.

Usage (internal — called by registry.py):
    from .loader import load_exercises_from_yaml
    exercises = load_exercises_from_yaml()   # dict or None on failure
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

from .base import ExerciseDefinition, SessionTypeParams

_REQUIRED_SESSION_PARAMS: frozenset[str] = frozenset(
    {
        "reps_fraction_low",
        "reps_fraction_high",
        "reps_min",
        "reps_max",
        "sets_min",
        "sets_max",
        "rest_min",
        "rest_max",
        "rir_target",
    }
)

_REQUIRED_EXERCISE_FIELDS: frozenset[str] = frozenset(
    {
        "exercise_id",
        "display_name",
        "muscle_group",
        "bw_fraction",
        "load_type",
        "variants",
        "primary_variant",
        "variant_factors",
        "session_params",
        "target_metric",
        "target_value",
        "test_protocol",
        "test_frequency_weeks",
        "onerm_includes_bodyweight",
        "onerm_explanation",
        "weight_increment_fraction",
        "weight_tm_threshold",
        "max_added_weight_kg",
    }
)


def _validate_session_params(d: dict) -> SessionTypeParams:
    """Convert a raw dict to SessionTypeParams, raising ValueError on missing fields."""
    missing = _REQUIRED_SESSION_PARAMS - set(d)
    if missing:
        raise ValueError(f"SessionTypeParams missing fields: {sorted(missing)}")
    return SessionTypeParams(
        reps_fraction_low=float(d["reps_fraction_low"]),
        reps_fraction_high=float(d["reps_fraction_high"]),
        reps_min=int(d["reps_min"]),
        reps_max=int(d["reps_max"]),
        sets_min=int(d["sets_min"]),
        sets_max=int(d["sets_max"]),
        rest_min=int(d["rest_min"]),
        rest_max=int(d["rest_max"]),
        rir_target=int(d["rir_target"]),
    )


def exercise_from_dict(d: dict) -> ExerciseDefinition:
    """Convert a raw dict (from YAML) to an ExerciseDefinition.

    Raises ValueError if any required field is absent.
    """
    d = dict(d)
    missing = _REQUIRED_EXERCISE_FIELDS - set(d)
    if missing:
        raise ValueError(f"ExerciseDefinition missing fields: {sorted(missing)}")

    raw_params = d.pop("session_params")
    session_params = {k: _validate_session_params(v) for k, v in raw_params.items()}

    # Optional fields with defaults matching ExerciseDefinition defaults
    has_variant_rotation = bool(d.pop("has_variant_rotation", True))
    grip_cycles_raw = d.pop("grip_cycles", {})
    grip_cycles: dict[str, list[str]] = (
        {k: list(v) for k, v in grip_cycles_raw.items()}
        if grip_cycles_raw
        else {}
    )

    return ExerciseDefinition(
        exercise_id=str(d["exercise_id"]),
        display_name=str(d["display_name"]),
        muscle_group=str(d["muscle_group"]),
        bw_fraction=float(d["bw_fraction"]),
        load_type=str(d["load_type"]),
        variants=list(d["variants"]),
        primary_variant=str(d["primary_variant"]),
        variant_factors={k: float(v) for k, v in d["variant_factors"].items()},
        session_params=session_params,
        target_metric=str(d["target_metric"]),
        target_value=float(d["target_value"]),
        test_protocol=str(d["test_protocol"]),
        test_frequency_weeks=int(d["test_frequency_weeks"]),
        onerm_includes_bodyweight=bool(d["onerm_includes_bodyweight"]),
        onerm_explanation=str(d["onerm_explanation"]),
        weight_increment_fraction=float(d["weight_increment_fraction"]),
        weight_tm_threshold=int(d["weight_tm_threshold"]),
        max_added_weight_kg=float(d["max_added_weight_kg"]),
        has_variant_rotation=has_variant_rotation,
        grip_cycles=grip_cycles,
    )


def _load_yaml_file(path: Path) -> dict:
    """Load a YAML file; return {} on any error."""
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
    """Recursively merge override into base (non-destructive to base)."""
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _get_bundled_exercises_dir() -> Path | None:
    """Return path to the bundled exercises/ data directory, or None if not found."""
    # loader.py lives at src/bar_scheduler/core/exercises/loader.py
    # three levels up → src/bar_scheduler/
    candidate = Path(__file__).parent.parent.parent / "exercises"
    return candidate if candidate.is_dir() else None


def _get_user_exercises_dir() -> Path | None:
    """Return ~/.bar-scheduler/exercises/ if it exists, else None."""
    home = Path(os.environ.get("HOME", "~")).expanduser()
    p = home / ".bar-scheduler" / "exercises"
    return p if p.is_dir() else None


def load_exercises_from_yaml() -> dict[str, ExerciseDefinition] | None:
    """Return {exercise_id: ExerciseDefinition} loaded from per-exercise YAML files.

    Loads each ``<exercise_id>.yaml`` from the bundled exercises/ directory.
    If a matching file exists in ``~/.bar-scheduler/exercises/`` it is
    deep-merged over the bundled definition (user can override any field).
    User-only files (no bundled counterpart) are loaded as new exercises.

    Returns None (rather than raising) so the registry can fall back gracefully.
    """
    try:
        bundled_dir = _get_bundled_exercises_dir()
        user_dir = _get_user_exercises_dir()

        if bundled_dir is None and user_dir is None:
            return None

        result: dict[str, ExerciseDefinition] = {}

        # Collect all exercise stems to process
        stems: dict[str, Path] = {}  # stem → bundled path (or absent)
        if bundled_dir is not None:
            for p in sorted(bundled_dir.glob("*.yaml")):
                stems[p.stem] = p

        # User-only files (new exercises not in bundled set)
        user_only: list[Path] = []
        if user_dir is not None:
            for p in sorted(user_dir.glob("*.yaml")):
                if p.stem not in stems:
                    user_only.append(p)

        # Load bundled (with optional user merge)
        for stem, bundled_path in stems.items():
            raw = _load_yaml_file(bundled_path)
            if not raw:
                continue
            if user_dir is not None:
                user_path = user_dir / f"{stem}.yaml"
                if user_path.exists():
                    user_raw = _load_yaml_file(user_path)
                    if user_raw:
                        raw = _deep_merge(raw, user_raw)
            try:
                ex = exercise_from_dict(raw)
                result[ex.exercise_id] = ex
            except ValueError as exc:
                warnings.warn(
                    f"bar-scheduler: skipping exercise '{stem}' — {exc}",
                    stacklevel=2,
                )

        # Load user-only exercises
        for p in user_only:
            raw = _load_yaml_file(p)
            if not raw:
                continue
            try:
                ex = exercise_from_dict(raw)
                result[ex.exercise_id] = ex
            except ValueError as exc:
                warnings.warn(
                    f"bar-scheduler: skipping user exercise '{p.stem}' — {exc}",
                    stacklevel=2,
                )

        return result if result else None

    except Exception as exc:
        warnings.warn(
            f"bar-scheduler: failed to load exercises from YAML ({exc}); "
            "using Python defaults.",
            stacklevel=2,
        )
        return None
