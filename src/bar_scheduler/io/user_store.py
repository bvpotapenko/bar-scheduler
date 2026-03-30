"""
JSONL-based history storage for training sessions.

Handles reading, writing, and managing the training history file.
"""

import json
from datetime import datetime
from pathlib import Path

from ..core.models import EquipmentState, SessionResult, UserProfile, UserState
from .serializers import (
    ValidationError,
    dict_to_equipment_state,
    dict_to_session_result,
    dict_to_user_profile,
    equipment_state_to_dict,
    session_to_json_line,
    user_profile_to_dict,
)


class UserStore:
    """
    Profile-centric store for a single user's data directory.

    One UserStore per user (data_dir). Profile operations need no exercise context.
    Exercise-specific operations (history, plan dates, equipment) accept exercise_id
    as a parameter -- no per-exercise store objects, no dummy IDs.
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

    def save_profile(self, profile: UserProfile) -> None:
        """
        Save user profile to profile.json.

        Args:
            profile: User profile to save (bodyweight_kg is part of UserProfile)
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)

        data = user_profile_to_dict(profile)

        with open(self.profile_path, "w") as f:
            json.dump(data, f, indent=2)

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
            UserState with profile and history

        Raises:
            FileNotFoundError: If required files don't exist
            ValidationError: If data is invalid
        """
        profile = self.load_profile()
        if profile is None:
            raise FileNotFoundError(
                f"Profile not found: {self.profile_path}. Run 'init' first."
            )

        history = self.load_history(exercise_id)

        return UserState(
            profile=profile,
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

        return [s for s in sessions if datetime.strptime(s.date, "%Y-%m-%d") > target]

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
            raise IndexError(
                f"Session index {index} out of range (0–{len(sessions) - 1})"
            )
        del sessions[index]
        self._write_sessions(exercise_id, sessions)

    def _input_files_mtime(self, exercise_id: str) -> float:
        """Max mtime of profile.json and history JSONL (the two plan inputs)."""
        mtimes = [
            p.stat().st_mtime
            for p in (self.profile_path, self.history_path(exercise_id))
            if p.exists()
        ]
        return max(mtimes) if mtimes else 0.0

    def load_plan_result_cache(self, exercise_id: str) -> dict | None:
        """Load the plan result cache, or None if absent/corrupt."""
        path = self.data_dir / f"{exercise_id}_plan_cache.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, OSError):
            return None

    def save_plan_result_cache(self, exercise_id: str, plans: list[dict]) -> None:
        """Persist the generated plan list with a generation timestamp."""
        import time

        path = self.data_dir / f"{exercise_id}_plan_cache.json"
        with open(path, "w") as f:
            json.dump({"generated_at": time.time(), "plans": plans}, f)

    # ------------------------------------------------------------------
    # Equipment profile persistence
    # Current equipment is stored under profile.json -> "equipment" key,
    # as a dict: {exercise_id: EquipmentState}.  Updating overwrites.
    # ------------------------------------------------------------------

    def load_current_equipment(self, exercise_id: str) -> EquipmentState | None:
        """
        Return the current EquipmentState for the given exercise,
        or None if none has been configured yet.
        """
        if not self.profile_path.exists():
            return None
        try:
            with open(self.profile_path) as f:
                data = json.load(f)
            raw = data.get("equipment", {}).get(exercise_id)
            if raw is None:
                return None
            return dict_to_equipment_state(raw)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def update_equipment(self, new_state: EquipmentState) -> None:
        """
        Save (overwrite) the current EquipmentState for an exercise.

        Args:
            new_state: EquipmentState to store
        """
        if not self.profile_path.exists():
            return
        with open(self.profile_path) as f:
            data = json.load(f)
        if "equipment" not in data:
            data["equipment"] = {}
        data["equipment"][new_state.exercise_id] = equipment_state_to_dict(new_state)
        with open(self.profile_path, "w") as f:
            json.dump(data, f, indent=2)

    def clear_history(self, exercise_id: str) -> None:
        """
        Clear all history for the given exercise (dangerous - use with caution).
        """
        path = self.history_path(exercise_id)
        if path.exists():
            path.write_text("")
