"""Utility functions for the bar-scheduler API."""
from __future__ import annotations

from pathlib import Path



def get_data_dir() -> Path:
    """Return the default data directory: ``~/.bar-scheduler``."""
    return Path.home() / ".bar-scheduler"


def parse_sets_string(sets_str: str) -> list[tuple[int, float, int]]:
    """
    Parse a sets string into a list of ``(reps, added_weight_kg, rest_seconds)`` tuples.

    Accepts compact format (``"4×1 3×8/60s"``, ``"5x4"``) or per-set format
    (``"8@0/180"``, ``"8 0 180"``, ``"8"``).
    Raises ``ValidationError`` if the string is empty or cannot be parsed.
    """
    from ..io.serializers import parse_sets_string as _parse

    return _parse(sets_str)


def parse_compact_sets(s: str) -> list[tuple[int, float, int]] | None:
    """
    Try to parse a compact sets string.

    Returns a list of ``(reps, added_weight_kg, rest_seconds)`` tuples if the
    string matches compact format, or ``None`` if it does not.
    """
    from ..io.serializers import parse_compact_sets as _parse

    return _parse(s)
