"""Typed exceptions raised by the bar-scheduler API."""

from bar_scheduler.io.serializers import ValidationError

__all__ = [
    "ValidationError",
    "ProfileNotFoundError",
    "HistoryNotFoundError",
    "SessionNotFoundError",
    "ProfileAlreadyExistsError",
]


class ProfileNotFoundError(FileNotFoundError):
    """Raised when profile.json does not exist."""


class HistoryNotFoundError(FileNotFoundError):
    """Raised when the JSONL history file does not exist."""


class SessionNotFoundError(IndexError):
    """Raised when a session index is out of range."""


class ProfileAlreadyExistsError(FileExistsError):
    """Raised when init_profile is called on an already-initialized directory."""
