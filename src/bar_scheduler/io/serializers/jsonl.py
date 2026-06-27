"""Bulk JSONL <-> session conversion for the history file."""

import json
from typing import Iterable

from bar_scheduler.domain.models import SessionResult
from bar_scheduler.io.serializers.sessions import dict_to_session_result
from bar_scheduler.io.serializers.validators import ValidationError


def sessions_from_jsonl(lines: Iterable[str]) -> list[SessionResult]:
    """Parse non-blank JSONL lines into sessions, in file order.

    Skips blank lines and legacy ``type: profile`` records. Raises
    ``ValidationError`` (with the 1-based line number) on any malformed line.
    """
    sessions: list[SessionResult] = []
    for line_num, raw_line in enumerate(lines, 1):
        session = _parse_history_line(raw_line.strip(), line_num)
        if session is not None:
            sessions.append(session)
    return sessions


def _parse_history_line(line: str, line_num: int) -> SessionResult | None:
    """Parse one stripped line, or None when it is blank or a profile record."""
    if not line:
        return None
    try:
        return _session_or_skip(line)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValidationError(f"Error parsing line {line_num}: {exc}") from exc


def _session_or_skip(line: str) -> SessionResult | None:
    """Decode one line; None for legacy profile records, else a session."""
    raw = json.loads(line)
    if raw.get("type") == "profile":
        return None
    return dict_to_session_result(raw)
