"""
JSONL-based history storage for training sessions.

Handles reading, writing, and managing the training history file.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from ..core.models import SessionResult, UserProfile, UserState
from .serializers import (
    ValidationError,
    dict_to_session_result,
    dict_to_user_profile,
    session_result_to_dict,
    session_to_json_line,
    user_profile_to_dict,
)


class HistoryStore:
    """
    Manages training history stored in JSONL format.

    The history file contains one JSON object per line:
    - First line (optional): profile record with type="profile"
    - Subsequent lines: session records

    A separate profile.json file stores user profile data.
    """

    def __init__(self, history_path: str | Path):
        """
        Initialize the history store.

        Args:
            history_path: Path to the JSONL history file
        """
        self.history_path = Path(history_path)
        self.profile_path = self.history_path.parent / "profile.json"

    def exists(self) -> bool:
        """Check if the history file exists."""
        return self.history_path.exists()

    def init(self) -> None:
        """
        Initialize empty history file if it doesn't exist.

        Creates parent directories if needed.
        """
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.history_path.exists():
            self.history_path.touch()

    def load_profile(self) -> UserProfile | None:
        """
        Load user profile from profile.json.

        Returns:
            UserProfile if file exists and is valid, None otherwise
        """
        if not self.profile_path.exists():
            return None

        try:
            with open(self.profile_path, "r") as f:
                data = json.load(f)
            return dict_to_user_profile(data)
        except (json.JSONDecodeError, ValidationError, KeyError):
            return None

    def get_plan_start_date(self) -> str | None:
        """
        Get the plan start date from profile.json.

        Returns:
            ISO date string or None if not set
        """
        if not self.profile_path.exists():
            return None
        try:
            with open(self.profile_path, "r") as f:
                data = json.load(f)
            return data.get("plan_start_date")
        except (json.JSONDecodeError, KeyError):
            return None

    def set_plan_start_date(self, date: str) -> None:
        """
        Store the plan start date in profile.json.

        Args:
            date: ISO date string (YYYY-MM-DD)
        """
        if not self.profile_path.exists():
            return
        with open(self.profile_path, "r") as f:
            data = json.load(f)
        data["plan_start_date"] = date
        with open(self.profile_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_plan_weeks(self) -> int | None:
        """Return the last user-specified plan horizon in weeks, or None if never set."""
        if not self.profile_path.exists():
            return None
        try:
            with open(self.profile_path) as f:
                data = json.load(f)
            v = data.get("plan_weeks")
            return int(v) if v is not None else None
        except (json.JSONDecodeError, ValueError):
            return None

    def set_plan_weeks(self, weeks: int) -> None:
        """Persist the user-chosen plan horizon so subsequent plain 'plan' runs reuse it."""
        if not self.profile_path.exists():
            return
        with open(self.profile_path) as f:
            data = json.load(f)
        data["plan_weeks"] = weeks
        with open(self.profile_path, "w") as f:
            json.dump(data, f, indent=2)

    def lookup_plan_cache_entry(self, date: str, session_type: str) -> dict | None:
        """Find the cached plan prescription for a given (date, session_type), or None."""
        cache = self.load_plan_cache()
        if not cache:
            return None
        for entry in cache:
            if entry.get("date") == date and entry.get("type") == session_type:
                return entry
        return None

    def save_profile(self, profile: UserProfile, bodyweight_kg: float) -> None:
        """
        Save user profile to profile.json.

        Args:
            profile: User profile to save
            bodyweight_kg: Current bodyweight
        """
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)

        data = user_profile_to_dict(profile)
        data["current_bodyweight_kg"] = bodyweight_kg

        with open(self.profile_path, "w") as f:
            json.dump(data, f, indent=2)

    def load_bodyweight(self) -> float | None:
        """
        Load current bodyweight from profile.json.

        Returns:
            Bodyweight in kg or None if not set
        """
        if not self.profile_path.exists():
            return None

        try:
            with open(self.profile_path, "r") as f:
                data = json.load(f)
            return float(data.get("current_bodyweight_kg", 0)) or None
        except (json.JSONDecodeError, ValueError):
            return None

    def update_bodyweight(self, bodyweight_kg: float) -> None:
        """
        Update current bodyweight in profile.json.

        Args:
            bodyweight_kg: New bodyweight in kg
        """
        if not self.profile_path.exists():
            raise FileNotFoundError(
                f"Profile not found: {self.profile_path}. Run 'init' first."
            )

        with open(self.profile_path, "r") as f:
            data = json.load(f)

        data["current_bodyweight_kg"] = bodyweight_kg

        with open(self.profile_path, "w") as f:
            json.dump(data, f, indent=2)

    def load_history(self) -> list[SessionResult]:
        """
        Load all sessions from the history file.

        Returns:
            List of SessionResult, sorted by date

        Raises:
            FileNotFoundError: If history file doesn't exist
        """
        if not self.history_path.exists():
            raise FileNotFoundError(
                f"History file not found: {self.history_path}. Run 'init' first."
            )

        sessions: list[SessionResult] = []

        with open(self.history_path, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)

                    # Skip profile records (legacy support)
                    if data.get("type") == "profile":
                        continue

                    session = dict_to_session_result(data)
                    sessions.append(session)

                except (json.JSONDecodeError, ValidationError) as e:
                    raise ValidationError(
                        f"Error parsing line {line_num} in {self.history_path}: {e}"
                    ) from e

        # Sort by date
        sessions.sort(key=lambda s: s.date)

        return sessions

    def load_user_state(self) -> UserState:
        """
        Load complete user state (profile + history).

        Returns:
            UserState with profile, bodyweight, and history

        Raises:
            FileNotFoundError: If required files don't exist
            ValidationError: If data is invalid
        """
        profile = self.load_profile()
        if profile is None:
            raise FileNotFoundError(
                f"Profile not found: {self.profile_path}. Run 'init' first."
            )

        bodyweight = self.load_bodyweight()
        if bodyweight is None:
            raise ValidationError("Bodyweight not set in profile. Run 'init' with --bodyweight-kg.")

        history = self.load_history()

        return UserState(
            profile=profile,
            current_bodyweight_kg=bodyweight,
            history=history,
        )

    def append_session(self, session: SessionResult) -> None:
        """
        Append a session to the history file.

        Maintains chronological order by inserting at the correct position.

        Args:
            session: Session to append
        """
        if not self.history_path.exists():
            raise FileNotFoundError(
                f"History file not found: {self.history_path}. Run 'init' first."
            )

        # Load existing sessions
        sessions = self.load_history()

        # Insert new session in chronological order
        session_date = datetime.strptime(session.date, "%Y-%m-%d")
        insert_idx = len(sessions)

        for i, existing in enumerate(sessions):
            existing_date = datetime.strptime(existing.date, "%Y-%m-%d")
            if session_date < existing_date:
                insert_idx = i
                break
            elif session_date == existing_date:
                # Same date: replace existing session of same type, or insert after
                if existing.session_type == session.session_type:
                    sessions[i] = session
                    insert_idx = -1  # Signal that we replaced
                    break

        if insert_idx >= 0:
            sessions.insert(insert_idx, session)

        # Rewrite file
        self._write_sessions(sessions)

    def _write_sessions(self, sessions: list[SessionResult]) -> None:
        """
        Write all sessions to the history file.

        Args:
            sessions: Sessions to write
        """
        with open(self.history_path, "w") as f:
            for session in sessions:
                f.write(session_to_json_line(session) + "\n")

    def get_latest_session(self) -> SessionResult | None:
        """
        Get the most recent session.

        Returns:
            Latest SessionResult or None if no history
        """
        try:
            sessions = self.load_history()
            return sessions[-1] if sessions else None
        except FileNotFoundError:
            return None

    def get_sessions_after(self, date: str) -> list[SessionResult]:
        """
        Get all sessions after a given date.

        Args:
            date: ISO date string (YYYY-MM-DD)

        Returns:
            List of sessions after the date
        """
        sessions = self.load_history()
        target = datetime.strptime(date, "%Y-%m-%d")

        return [
            s for s in sessions if datetime.strptime(s.date, "%Y-%m-%d") > target
        ]

    def delete_session_at(self, index: int) -> None:
        """
        Delete the session at the given 0-based index in sorted history.

        Args:
            index: 0-based index

        Raises:
            IndexError: If index is out of range
        """
        sessions = self.load_history()
        if index < 0 or index >= len(sessions):
            raise IndexError(f"Session index {index} out of range (0–{len(sessions) - 1})")
        del sessions[index]
        self._write_sessions(sessions)

    def load_plan_cache(self) -> list[dict] | None:
        """
        Load the previously saved plan snapshot for diffing.

        Returns:
            List of session snapshot dicts or None if not found
        """
        cache_path = self.history_path.parent / "plan_cache.json"
        if not cache_path.exists():
            return None
        try:
            with open(cache_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def save_plan_cache(self, sessions: list[dict]) -> None:
        """
        Persist upcoming plan sessions for next-run diffing.

        Args:
            sessions: List of session snapshot dicts
        """
        cache_path = self.history_path.parent / "plan_cache.json"
        with open(cache_path, "w") as f:
            json.dump(sessions, f, indent=2)

    def clear_history(self) -> None:
        """
        Clear all history (dangerous - use with caution).
        """
        if self.history_path.exists():
            self.history_path.write_text("")


def get_default_history_path(exercise_id: str = "pull_up") -> Path:
    """
    Get the default history file path for an exercise.

    Pull-up history is routed to the legacy ``history.jsonl`` when it exists
    (backward compat) and to ``pull_up_history.jsonl`` otherwise.
    All other exercises get their own ``<exercise_id>_history.jsonl``.

    Args:
        exercise_id: Exercise identifier (default: "pull_up")

    Returns:
        Default history path
    """
    base = Path.home() / ".bar-scheduler"
    if exercise_id == "pull_up":
        legacy = base / "history.jsonl"
        if legacy.exists():
            return legacy
        return base / "pull_up_history.jsonl"
    return base / f"{exercise_id}_history.jsonl"


def get_default_store() -> HistoryStore:
    """
    Get a HistoryStore with the default path.

    Returns:
        HistoryStore instance
    """
    return HistoryStore(get_default_history_path())
