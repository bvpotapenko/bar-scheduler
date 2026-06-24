"""Unit tests for the compact sets-string parser (3x5, +kg, /Ns)."""

import pytest

from bar_scheduler.io.serializers import (
    ValidationError,
    parse_compact_sets,
    parse_sets_string,
)


def test_compact_multiplier_expands_sets():
    assert parse_sets_string("5x4") == [(5, 0.0, 180)] * 4


def test_compact_weight_and_rest_suffix():
    assert parse_sets_string("5x4 +0.5kg / 240s") == [(5, 0.5, 240)] * 4


def test_compact_mixed_groups():
    single = [(4, 0.0, 60)]
    eights = [(3, 0.0, 60)] * 8
    assert parse_sets_string("4, 3x8 / 60s") == single + eights


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
