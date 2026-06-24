"""Unit tests for the per-set sets-string parser (parse_sets_string)."""

import pytest

from bar_scheduler.domain.results import ParsedSet
from bar_scheduler.io.serializers import ValidationError, parse_sets_string


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8@0/180", [(8, 0.0, 180)]),
        ("6@+5", [(6, 5.0, 180)]),  # rest defaults to 180
        ("8 0 180", [(8, 0.0, 180)]),
        ("8 0", [(8, 0.0, 180)]),
        ("8", [(8, 0.0, 180)]),  # bare int
        ("8@0/180, 6@+5/120", [(8, 0.0, 180), (6, 5.0, 120)]),
    ],
    ids=["at-rest", "at-default-rest", "space-rest", "space-default", "bare", "multi"],
)
def test_per_set_formats(text, expected):
    assert parse_sets_string(text) == expected


def test_result_is_parsedset_with_named_fields():
    parsed = parse_sets_string("6@+5/120")
    assert parsed[0] == ParsedSet(reps=6, added_weight_kg=5.0, rest_seconds=120)
    assert parsed[0].reps == 6  # named access
    assert parsed[0] == (6, 5.0, 120)  # tuple-compatible


@pytest.mark.parametrize(
    "text",
    ["", "   ", "abc", "8 -5", "8@/180"],
    ids=["empty", "whitespace", "letters", "negative-weight", "missing-weight"],
)
def test_invalid_raises_validation_error(text):
    with pytest.raises(ValidationError):
        parse_sets_string(text)
