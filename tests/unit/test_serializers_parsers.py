"""Unit tests for the sets-string parsers (per-set + compact)."""

import pytest

from bar_scheduler.domain.results import ParsedSet
from bar_scheduler.io.serializers import (
    ValidationError,
    parse_compact_sets,
    parse_sets_string,
)


# --- per-set format (parse_sets_string) ---


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
    result = parse_sets_string("6@+5/120")
    assert result[0] == ParsedSet(reps=6, added_weight_kg=5.0, rest_seconds=120)
    assert result[0].reps == 6  # named access
    assert result[0] == (6, 5.0, 120)  # tuple-compatible


# --- compact format ---


def test_compact_multiplier_expands_sets():
    assert parse_sets_string("5x4") == [(5, 0.0, 180)] * 4


def test_compact_weight_and_rest_suffix():
    assert parse_sets_string("5x4 +0.5kg / 240s") == [(5, 0.5, 240)] * 4


def test_compact_mixed_groups():
    assert parse_sets_string("4, 3x8 / 60s") == [(4, 0.0, 60)] + [(3, 0.0, 60)] * 8


def test_compact_bare_ladder_with_rest_suffix():
    assert parse_sets_string("8, 7, 6, 5 / 60s") == [
        (8, 0.0, 60),
        (7, 0.0, 60),
        (6, 0.0, 60),
        (5, 0.0, 60),
    ]


def test_parse_compact_returns_none_for_per_set_input():
    assert parse_compact_sets("8@0/180") is None  # no 'x', no '/Ns' suffix
    assert parse_compact_sets("8 0 180") is None


def test_compact_zero_sets_is_not_compact():
    # "5x0" is not a valid compact group -> None, then per-set parse rejects it.
    assert parse_compact_sets("5x0") is None
    with pytest.raises(ValidationError):
        parse_sets_string("5x0")


# --- error paths ---


@pytest.mark.parametrize(
    "text",
    ["", "   ", "abc", "8 -5", "8@/180"],
    ids=["empty", "whitespace", "letters", "negative-weight", "missing-weight"],
)
def test_invalid_raises_validation_error(text):
    with pytest.raises(ValidationError):
        parse_sets_string(text)
