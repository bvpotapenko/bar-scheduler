"""Field validation for incoming JSON data."""

import re
from datetime import datetime

from bar_scheduler.domain.models import Grip, SessionType


class ValidationError(Exception):
    """Raised when data validation fails."""


def validate_date(date_str: str) -> str:
    """Validate and return an ISO ``YYYY-MM-DD`` date string."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        raise ValidationError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValidationError(f"Invalid date: {date_str}") from exc
    return date_str


def validate_grip(grip: str) -> Grip:
    """Validate that a grip / variant is a non-empty string."""
    if not isinstance(grip, str) or not grip.strip():
        raise ValidationError(f"Invalid grip: {grip!r}. Must be a non-empty string.")
    return grip


def validate_session_type(session_type: str) -> SessionType:
    """Validate that the session type is one of S/H/E/T/TEST."""
    valid_types = ("S", "H", "E", "T", "TEST")
    if session_type not in valid_types:
        raise ValidationError(
            f"Invalid session_type: {session_type}. Must be one of {valid_types}"
        )
    return session_type


def validate_non_negative(num: int | float, name: str) -> int | float:
    """Validate that ``num`` is >= 0."""
    if num < 0:
        raise ValidationError(f"{name} must be non-negative, got {num}")
    return num


def validate_positive(num: int | float, name: str) -> int | float:
    """Validate that ``num`` is > 0."""
    if num <= 0:
        raise ValidationError(f"{name} must be positive, got {num}")
    return num
