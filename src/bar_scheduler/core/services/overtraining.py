"""Overtraining-severity assessment from recent session density.

Compares how compressed the last 7 days of training are against the user's
planned frequency. Unlogged days count as rest -- no explicit REST records.
"""

from collections.abc import Mapping
from datetime import datetime, timedelta
from types import MappingProxyType

from bar_scheduler.domain.models import SessionResult

_WINDOW_DAYS = 7

_ZERO_STATS: Mapping[str, object] = MappingProxyType(
    {
        "level": 0,
        "sessions": 0,
        "span_days": 0,
        "extra_rest_days": 0,
        "description": "",
    }
)


def _parse(session: SessionResult) -> datetime:
    return datetime.strptime(session.date, "%Y-%m-%d")


class OvertrainingDetector:
    """Assess recent training overcompression vs. the planned frequency."""

    def severity(
        self,
        history: list[SessionResult],
        days_per_week: int = 3,
        reference_date: datetime | None = None,
    ) -> dict:
        """Severity dict: ``level`` 0-3, ``sessions``, ``span_days``, extras, text."""
        if not history:
            return dict(_ZERO_STATS)
        anchor = reference_date or datetime.now()
        ref = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        dates = self._recent_dates(history, ref)
        if len(dates) < 2:
            return dict(_ZERO_STATS)
        return self._summary(dates, days_per_week)

    def _recent_dates(
        self, history: list[SessionResult], reference_date: datetime
    ) -> list[datetime]:
        cutoff = reference_date - timedelta(days=_WINDOW_DAYS - 1)
        parsed = sorted(_parse(session) for session in history)
        return [date for date in parsed if date >= cutoff]

    def _summary(self, dates: list[datetime], days_per_week: int) -> dict:
        count = len(dates)
        span_days = (dates[-1] - dates[0]).days
        extra = self._extra_rest(count, span_days, days_per_week)
        return {
            "level": self._level(extra),
            "sessions": count,
            "span_days": span_days,
            "extra_rest_days": extra,
            "description": self._describe(count, span_days),
        }

    def _extra_rest(self, count: int, span_days: int, days_per_week: int) -> int:
        expected = (count - 1) * (_WINDOW_DAYS / max(days_per_week, 1))
        return max(0, round(expected - max(span_days, 1)))

    def _level(self, extra_rest_days: int) -> int:
        if extra_rest_days == 0:
            return 0
        if extra_rest_days == 1:
            return 1
        return 2 if extra_rest_days <= 3 else 3

    def _describe(self, count: int, span_days: int) -> str:
        inclusive = span_days + 1
        word = "day" if inclusive <= 1 else "days"
        return f"{count} sessions in {inclusive} {word}"
