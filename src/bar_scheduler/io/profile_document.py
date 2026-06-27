"""The sole gateway to a user's ``profile.json`` document.

Centralises every ``json.load`` / ``json.dump`` on the file so the stores built
on top express partial updates as ``with doc.mutate() as raw: raw[...] = ...``.
"""

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class ProfileDocument:
    """Read/write access to one profile.json file."""

    def __init__(self, path: Path):
        self.path = path

    def exists(self) -> bool:
        """Whether the document file is present on disk."""
        return self.path.exists()

    def read(self) -> dict:
        """Return the parsed document, or ``{}`` when missing or corrupt."""
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except json.JSONDecodeError:
            return {}

    def write(self, raw: dict) -> None:
        """Persist ``raw`` as pretty JSON, creating parent directories."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(raw, indent=2))

    @contextmanager
    def mutate(self) -> Iterator[dict]:
        """Yield the current document, persisting it on context exit."""
        raw = self.read()
        yield raw
        self.write(raw)
