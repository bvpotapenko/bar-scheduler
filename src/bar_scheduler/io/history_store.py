"""
JSONL-based history storage for training sessions.

Handles reading, writing, and managing the training history file.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from ..core.models import EquipmentState, SessionResult, UserProfile, UserState
from .serializers import (
    ValidationError,
    dict_to_equipment_state,
    dict_to_session_result,
    dict_to_user_profile,
    equipment_state_to_dict,
    session_result_to_dict,
    session_to_json_line,
    user_profile_to_dict,
)


class UserStore:
    """
    Profile-centric store for a single user's data directory.

    One UserStore per user (data_dir). Profile operations need no exercise context.
    Exercise-specific operations (history, plan dates, equipment) accept exercise_id
    as a parameter — no per-exercise store objects, no dummy IDs.
    """

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.profile_path = self.data_dir / "profile.json"

    def history_path(self, exercise_id: str) -> Path:
        """Return the JSONL history file path for the given exercise."""
        return self.data_dir / f"{exercise_id}_history.jsonl"

    def exists(self, exercise_id: str) -> bool:
        """Check if the history file exists for the given exercise."""
        return self.history_path(exercise_id).exists()

    def init_exercise(self, exercise_id: str) -> None:
        """
        Initialize empty history file for exercise if it doesn't exist.

        Creates parent directories if needed.
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.history_path(exercise_id)
        if not path.exists():
            path.touch()

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

    def get_plan_start_date(self, exercise_id: str) -> str | None:
        """
        Get the plan start date from profile.json for this exercise.

        Returns:
            ISO date string or None if not set
        """
        if not self.profile_path.exists():
            return None
        try:
            with open(self.profile_path, "r") as f:
                data = json.load(f)
            return data.get("plan_start_dates", {}).get(exercise_id)
        except (json.JSONDecodeError, KeyError):
            return None

    def set_plan_start_date(self, exercise_id: str, date: str) -> None:
        """
        Store the plan start date in profile.json for this exercise.

        Writes to the per-exercise nested key so different exercises
        don't overwrite each other's plan anchor.

        Args:
            exercise_id: Exercise identifier
            date: ISO date string (YYYY-MM-DD)
        """
        if not self.profile_path.exists():
            return
        with open(self.profile_path, "r") as f:
            data = json.load(f)
        if "plan_start_dates" not in data:
            data["plan_start_dates"] = {}
        data["plan_start_dates"][exercise_id] = date
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

    def lookup_plan_cache_entry(self, exercise_id: str, date: str, session_type: str) -> dict | None:
        """Find the cached plan prescription for a given (date, session_type), or None."""
        cache = self.load_plan_cache(exercise_id)
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
        self.data_dir.mkdir(parents=True, exist_ok=True)

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

    def update_language(self, lang: str) -> None:
        """Update the display language in profile.json."""
        if not self.profile_path.exists():
            raise FileNotFoundError(
                f"Profile not found: {self.profile_path}. Run 'init' first."
            )
        with open(self.profile_path) as f:
            data = json.load(f)
        if lang == "en":
            data.pop("language", None)
        else:
            data["language"] = lang
        with open(self.profile_path, "w") as f:
            json.dump(data, f, indent=2)

    def load_history(self, exercise_id: str) -> list[SessionResult]:
        """
        Load all sessions from the history file for the given exercise.

        Returns:
            List of SessionResult, sorted by date

        Raises:
            FileNotFoundError: If history file doesn't exist
        """
        path = self.history_path(exercise_id)
        if not path.exists():
            raise FileNotFoundError(
                f"History file not found: {path}. Run 'init' first."
            )

        sessions: list[SessionResult] = []

        with open(path, "r") as f:
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
                        f"Error parsing line {line_num} in {path}: {e}"
                    ) from e

        # Sort by date
        sessions.sort(key=lambda s: s.date)

        return sessions

    def load_user_state(self, exercise_id: str) -> UserState:
        """
        Load complete user state (profile + history for the given exercise).

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

        history = self.load_history(exercise_id)

        return UserState(
            profile=profile,
            current_bodyweight_kg=bodyweight,
            history=history,
        )

    def append_session(self, session: SessionResult) -> None:
        """
        Append a session to the history file.

        Maintains chronological order by inserting at the correct position.
        Uses session.exercise_id to determine the history file.

        Args:
            session: Session to append
        """
        path = self.history_path(session.exercise_id)
        if not path.exists():
            raise FileNotFoundError(
                f"History file not found: {path}. Run 'init' first."
            )

        # Load existing sessions
        sessions = self.load_history(session.exercise_id)

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
        self._write_sessions(session.exercise_id, sessions)

    def _write_sessions(self, exercise_id: str, sessions: list[SessionResult]) -> None:
        """
        Write all sessions to the history file for the given exercise.

        Args:
            exercise_id: Exercise identifier
            sessions: Sessions to write
        """
        with open(self.history_path(exercise_id), "w") as f:
            for session in sessions:
                f.write(session_to_json_line(session) + "\n")

    def get_latest_session(self, exercise_id: str) -> SessionResult | None:
        """
        Get the most recent session for the given exercise.

        Returns:
            Latest SessionResult or None if no history
        """
        try:
            sessions = self.load_history(exercise_id)
            return sessions[-1] if sessions else None
        except FileNotFoundError:
            return None

    def get_sessions_after(self, exercise_id: str, date: str) -> list[SessionResult]:
        """
        Get all sessions after a given date.

        Args:
            exercise_id: Exercise identifier
            date: ISO date string (YYYY-MM-DD)

        Returns:
            List of sessions after the date
        """
        sessions = self.load_history(exercise_id)
        target = datetime.strptime(date, "%Y-%m-%d")

        return [
            s for s in sessions if datetime.strptime(s.date, "%Y-%m-%d") > target
        ]

    def delete_session_at(self, exercise_id: str, index: int) -> None:
        """
        Delete the session at the given 0-based index in sorted history.

        Args:
            exercise_id: Exercise identifier
            index: 0-based index

        Raises:
            IndexError: If index is out of range
        """
        sessions = self.load_history(exercise_id)
        if index < 0 or index >= len(sessions):
            raise IndexError(f"Session index {index} out of range (0–{len(sessions) - 1})")
        del sessions[index]
        self._write_sessions(exercise_id, sessions)

    def load_plan_cache(self, exercise_id: str) -> list[dict] | None:
        """
        Load the previously saved plan snapshot for diffing.

        Returns:
            List of session snapshot dicts or None if not found
        """
        cache_path = self.data_dir / f"{exercise_id}_plan_cache.json"
        if not cache_path.exists():
            return None
        try:
            with open(cache_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def save_plan_cache(self, exercise_id: str, sessions: list[dict]) -> None:
        """
        Persist upcoming plan sessions for next-run diffing.

        Args:
            exercise_id: Exercise identifier
            sessions: List of session snapshot dicts
        """
        cache_path = self.data_dir / f"{exercise_id}_plan_cache.json"
        with open(cache_path, "w") as f:
            json.dump(sessions, f, indent=2)

    # ------------------------------------------------------------------
    # Equipment profile persistence
    # Equipment history is stored under profile.json → "equipment" key,
    # as an append-only dict: {exercise_id: [EquipmentState, ...]}.
    # ------------------------------------------------------------------

    def load_equipment_history(self, exercise_id: str) -> list[EquipmentState]:
        """
        Load all EquipmentState entries for the given exercise.

        Returns:
            List of EquipmentState (chronological), or [] if none found
        """
        if not self.profile_path.exists():
            return []
        try:
            with open(self.profile_path) as f:
                data = json.load(f)
            raw = data.get("equipment", {}).get(exercise_id, [])
            return [dict_to_equipment_state(e) for e in raw]
        except (json.JSONDecodeError, KeyError, TypeError):
            return []

    def load_current_equipment(self, exercise_id: str) -> EquipmentState | None:
        """
        Return the currently active EquipmentState for the given exercise,
        or None if none has been set up yet.
        """
        history = self.load_equipment_history(exercise_id)
        for state in reversed(history):
            if state.valid_until is None:
                return state
        return None

    def save_equipment_history(
        self, exercise_id: str, history: list[EquipmentState]
    ) -> None:
        """
        Persist the full equipment history list for an exercise.

        Args:
            exercise_id: Exercise identifier
            history: Complete list of EquipmentState entries to store
        """
        if not self.profile_path.exists():
            return
        with open(self.profile_path) as f:
            data = json.load(f)
        if "equipment" not in data:
            data["equipment"] = {}
        data["equipment"][exercise_id] = [equipment_state_to_dict(e) for e in history]
        with open(self.profile_path, "w") as f:
            json.dump(data, f, indent=2)

    def update_equipment(self, new_state: EquipmentState) -> None:
        """
        Append a new EquipmentState entry, closing the previous one.

        The currently active entry's valid_until is set to yesterday's date
        and the new entry is appended with valid_until=None (= still current).

        Args:
            new_state: New EquipmentState to activate (valid_from must be set)
        """
        from datetime import datetime, timedelta

        exercise_id = new_state.exercise_id
        history = self.load_equipment_history(exercise_id)

        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # Close any currently open entry
        for entry in history:
            if entry.valid_until is None:
                entry.valid_until = yesterday

        # Ensure new entry has a valid_from
        if not new_state.valid_from:
            new_state.valid_from = today

        history.append(new_state)
        self.save_equipment_history(exercise_id, history)

    def clear_history(self, exercise_id: str) -> None:
        """
        Clear all history for the given exercise (dangerous - use with caution).
        """
        path = self.history_path(exercise_id)
        if path.exists():
            path.write_text("")


# ---------------------------------------------------------------------------
# Backward-compatibility alias
# ---------------------------------------------------------------------------

HistoryStore = UserStore


def get_data_dir() -> Path:
    """Return the base data directory where all bar-scheduler data is stored."""
    return Path.home() / ".bar-scheduler"


def get_profile_store() -> "UserStore":
    """
    Return a UserStore for the default data directory.

    Suitable for profile-only operations when no specific exercise is needed.
    """
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return UserStore(data_dir)
