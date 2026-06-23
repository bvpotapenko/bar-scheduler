"""Per-set sets-string parser (an ordered (regex, has_weight, has_rest) table).

Tries the compact plan parser first, then matches each comma-separated part
against the per-set formats below. Rest defaults to 180 s when omitted.
"""

import re

from bar_scheduler.domain.results import ParsedSet
from bar_scheduler.io.serializers.compact import _DEFAULT_REST_SECONDS, parse_compact_sets
from bar_scheduler.io.serializers.validators import ValidationError

# (pattern, has_weight, has_rest). Order = match priority.
_Format = tuple[re.Pattern[str], bool, bool]
_PER_SET_FORMATS: list[_Format] = [
    (re.compile(r"^(\d+)@\+?(-?\d+\.?\d*)/(\d+)$"), True, True),   # reps@+kg/rest
    (re.compile(r"^(\d+)@\+?(-?\d+\.?\d*)$"), True, False),        # reps@+kg
    (re.compile(r"^(\d+)\s+(\+?-?\d+\.?\d*)\s+(\d+)$"), True, True),  # reps kg rest
    (re.compile(r"^(\d+)\s+(\+?-?\d+\.?\d*)$"), True, False),      # reps kg
    (re.compile(r"^(\d+)$"), False, False),                        # bare reps
]

_FORMAT_HELP = (
    "Use: reps@weight/rest (e.g. 8@0/180), reps@weight (e.g. 6@+5),\n"
    "     or space-separated: reps weight rest (e.g. 8 0 180)."
)


def _build(match: re.Match[str], has_weight: bool, has_rest: bool) -> ParsedSet:
    reps = int(match.group(1))
    weight = float(match.group(2)) if has_weight else 0.0
    rest = int(match.group(3)) if has_rest else _DEFAULT_REST_SECONDS
    return ParsedSet(reps, weight, rest)


def _parse_part(part: str) -> ParsedSet:
    for pattern, has_weight, has_rest in _PER_SET_FORMATS:
        match = pattern.match(part)
        if match:
            return _validate(_build(match, has_weight, has_rest))
    raise ValidationError(f"Invalid set format: '{part}'.\n{_FORMAT_HELP}")


def _validate(parsed: ParsedSet) -> ParsedSet:
    if parsed.reps < 0:
        raise ValidationError(f"Reps must be non-negative: {parsed.reps}")
    if parsed.added_weight_kg < 0:
        raise ValidationError(f"Weight must be non-negative: {parsed.added_weight_kg}")
    if parsed.rest_seconds < 0:
        raise ValidationError(f"Rest must be non-negative: {parsed.rest_seconds}")
    return parsed


def parse_sets_string(sets_str: str) -> list[ParsedSet]:
    """Parse a sets string into ParsedSet tuples (compact form tried first).

    Per-set formats (comma-separated): ``reps@+kg/rest``, ``reps@+kg``,
    ``reps kg rest``, ``reps kg``, or bare ``reps``. Raises ValidationError on
    an empty or unparseable string.
    """
    if not sets_str or not sets_str.strip():
        raise ValidationError("Sets string cannot be empty")
    compact = parse_compact_sets(sets_str.strip())
    if compact is not None:
        return compact
    parts = [part.strip() for part in sets_str.split(",") if part.strip()]
    sets = [_parse_part(part) for part in parts]
    if not sets:
        raise ValidationError("No valid sets found in sets string")
    return sets
