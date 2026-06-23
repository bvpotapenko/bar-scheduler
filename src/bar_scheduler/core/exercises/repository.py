"""Lazy, per-exercise definition loader.

One exercise is loaded on demand from ``<id>.yaml`` (bundled, then user
override deep-merged on top) via an OmegaConf structured config keyed on
:class:`ExerciseDefinition`. This replaces the import-time "load every
exercise" registry: planning one exercise never parses the others.
"""

from __future__ import annotations

import os
from pathlib import Path

from omegaconf import OmegaConf
from omegaconf.errors import OmegaConfBaseException

from bar_scheduler.core.exercises.base import ExerciseDefinition


def default_bundled_exercises_dir() -> Path | None:
    """Bundled ``exercises/`` directory shipped with the package."""
    candidate = Path(__file__).parent.parent.parent / "exercises"
    return candidate if candidate.is_dir() else None


def default_user_exercises_dir() -> Path:
    """User override directory ``~/.bar-scheduler/exercises/``."""
    home = Path(os.environ.get("HOME", "~")).expanduser()
    return home / ".bar-scheduler" / "exercises"


def _is_strictly_ascending(values: list[int]) -> bool:
    pairs = zip(values, values[1:])
    return all(lower < upper for lower, upper in pairs)


def _validate(definition: ExerciseDefinition) -> None:
    """Domain checks OmegaConf cannot express (strictly-ascending thresholds)."""
    thresholds = definition.level_thresholds
    if thresholds is not None and not _is_strictly_ascending(thresholds):
        raise ValueError("level_thresholds must be strictly ascending")


class ExerciseRepository:
    """Loads and caches one :class:`ExerciseDefinition` per id, on demand."""

    def __init__(
        self,
        bundled_dir: Path | None = None,
        user_dir: Path | None = None,
    ) -> None:
        self._bundled_dir = default_bundled_exercises_dir() if bundled_dir is None else bundled_dir
        self._user_dir = default_user_exercises_dir() if user_dir is None else user_dir
        self._cache: dict[str, ExerciseDefinition] = {}

    def list_available(self) -> list[str]:
        """All exercise ids with a YAML file in either directory (no parsing)."""
        stems: set[str] = set()
        for directory in (self._bundled_dir, self._user_dir):
            if directory is not None and directory.is_dir():
                stems.update(path.stem for path in directory.glob("*.yaml"))
        return sorted(stems)

    def get(self, exercise_id: str) -> ExerciseDefinition:
        """Return the definition for ``exercise_id`` (cached after first load)."""
        cached = self._cache.get(exercise_id)
        if cached is None:
            cached = self._load(exercise_id)
            self._cache[exercise_id] = cached
        return cached

    def _load(self, exercise_id: str) -> ExerciseDefinition:
        sources = self._sources(exercise_id)
        if not sources:
            valid = ", ".join(self.list_available())
            raise ValueError(f"Unknown exercise '{exercise_id}'. Valid IDs: {valid}")
        merged = OmegaConf.structured(ExerciseDefinition)
        for path in sources:
            merged = OmegaConf.merge(merged, OmegaConf.load(path))
        try:
            definition: ExerciseDefinition = OmegaConf.to_object(merged)
        except OmegaConfBaseException as exc:
            raise ValueError(f"Invalid exercise '{exercise_id}': {exc}") from exc
        _validate(definition)
        return definition

    def _sources(self, exercise_id: str) -> list[Path]:
        sources: list[Path] = []
        for directory in (self._bundled_dir, self._user_dir):
            candidate = None if directory is None else directory / f"{exercise_id}.yaml"
            if candidate is not None and candidate.is_file():
                sources.append(candidate)
        return sources
