"""Persistence for a single exercise's JSONL training history."""

from datetime import datetime
from pathlib import Path

from bar_scheduler.domain.models import SessionResult
from bar_scheduler.io.serializers import session_to_json_line, sessions_from_jsonl


class HistoryStore:
    """Read/append/delete sessions in ``{exercise_id}_history.jsonl``."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    def path(self, exercise_id: str) -> Path:
        """JSONL history path for ``exercise_id``."""
        return self.data_dir / f"{exercise_id}_history.jsonl"

    def exists(self, exercise_id: str) -> bool:
        """Whether the history file for ``exercise_id`` exists."""
        return self.path(exercise_id).exists()

    def init(self, exercise_id: str) -> None:
        """Create an empty history file for ``exercise_id`` if absent."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.path(exercise_id)
        if not path.exists():
            path.touch()

    def load(self, exercise_id: str) -> list[SessionResult]:
        """All sessions for ``exercise_id``, sorted by date.

        Raises ``FileNotFoundError`` if the history file does not exist.
        """
        path = self.path(exercise_id)
        if not path.exists():
            raise FileNotFoundError(f"History file not found: {path}. Run 'init' first.")
        sessions = sessions_from_jsonl(path.read_text().splitlines())
        sessions.sort(key=lambda sess: sess.date)
        return sessions

    def append(self, session: SessionResult) -> None:
        """Insert ``session`` chronologically (replacing same date + type)."""
        sessions = _insert_ordered(self.load(session.exercise_id), session)
        _write_sessions(self.path(session.exercise_id), sessions)

    def delete_at(self, exercise_id: str, index: int) -> None:
        """Delete the session at 0-based ``index`` in sorted history."""
        sessions = self.load(exercise_id)
        last_idx = len(sessions) - 1
        if index < 0 or index > last_idx:
            raise IndexError(f"Session index {index} out of range (0–{last_idx})")
        sessions.pop(index)
        _write_sessions(self.path(exercise_id), sessions)


def _insert_ordered(sessions: list[SessionResult], session: SessionResult) -> list[SessionResult]:
    """Return ``sessions`` with ``session`` placed by date; same date+type replaces."""
    new_date = datetime.strptime(session.date, "%Y-%m-%d")
    ordered = list(sessions)
    for idx, existing in enumerate(ordered):
        existing_date = datetime.strptime(existing.date, "%Y-%m-%d")
        if new_date < existing_date:
            ordered.insert(idx, session)
            return ordered
        if new_date == existing_date and existing.session_type == session.session_type:
            ordered[idx] = session
            return ordered
    ordered.append(session)
    return ordered


def _write_sessions(path: Path, sessions: list[SessionResult]) -> None:
    """Rewrite ``path`` with one compact JSON line per session."""
    path.write_text("".join(f"{session_to_json_line(sess)}\n" for sess in sessions))
