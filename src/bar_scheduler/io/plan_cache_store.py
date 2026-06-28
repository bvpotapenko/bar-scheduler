"""Persistence for the per-exercise generated-plan cache.

The cache is valid only while it is newer than every plan input (profile +
history); ``load_if_fresh`` encapsulates that mtime comparison.
"""

import json
import time
from pathlib import Path


class PlanCacheStore:
    """Read/write ``{exercise_id}_plan_cache.json`` with freshness checking."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    def load(self, exercise_id: str) -> dict | None:
        """The cached plan payload, or None if absent or corrupt."""
        path = self._path(exercise_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        return raw if isinstance(raw, dict) else None

    def save(self, exercise_id: str, plans: list[dict]) -> None:
        """Persist ``plans`` stamped with the current generation time."""
        payload = {"generated_at": time.time(), "plans": plans}
        self._path(exercise_id).write_text(json.dumps(payload))

    def load_if_fresh(self, exercise_id: str, input_paths: list[Path]) -> dict | None:
        """The cached payload when newer than every input path, else None."""
        cache = self.load(exercise_id)
        if cache and cache.get("generated_at", 0.0) >= _max_mtime(input_paths):
            return cache
        return None

    def _path(self, exercise_id: str) -> Path:
        return self.data_dir / f"{exercise_id}_plan_cache.json"


def _max_mtime(paths: list[Path]) -> float:
    """Newest modification time among existing ``paths`` (0.0 if none exist)."""
    mtimes = [path.stat().st_mtime for path in paths if path.exists()]
    return max(mtimes) if mtimes else 0.0
