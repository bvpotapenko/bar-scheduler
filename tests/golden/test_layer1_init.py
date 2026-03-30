"""
Layer 1 — Profile initialisation tests.

Verifies that all three profiles are created with correct fields,
exercises, targets, and equipment.  No plan output is checked here —
that requires history (Layer 2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bar_scheduler.api import get_current_equipment, get_history, get_profile

from .constants_p1 import (
    P1_BODYWEIGHT_KG,
    P1_BSS_AVAILABLE_ITEMS,
    P1_BSS_DAYS,
    P1_BSS_TARGET_REPS,
    P1_BSS_TARGET_WEIGHT_KG,
    P1_DIP_AVAILABLE_ITEMS,
    P1_DIP_DAYS,
    P1_DIP_MACHINE_ASSISTANCE_KG,
    P1_DIP_TARGET_REPS,
    P1_HEIGHT_CM,
    P1_INCLINE_AVAILABLE_ITEMS,
    P1_INCLINE_DAYS,
    P1_INCLINE_TARGET_REPS,
    P1_INCLINE_TARGET_WEIGHT_KG,
)
from .constants_p2 import (
    P2_BODYWEIGHT_KG,
    P2_DIP_AVAILABLE_ITEMS,
    P2_DIP_DAYS,
    P2_DIP_TARGET_REPS,
    P2_DIP_TARGET_WEIGHT_KG,
    P2_HEIGHT_CM,
    P2_PULL_UP_AVAILABLE_ITEMS,
    P2_PULL_UP_DAYS,
    P2_PULL_UP_TARGET_REPS,
)
from .constants_p3 import (
    P3_BODYWEIGHT_KG,
    P3_BSS_AVAILABLE_ITEMS,
    P3_BSS_DAYS,
    P3_BSS_TARGET_REPS,
    P3_BSS_TARGET_WEIGHT_KG,
    P3_HEIGHT_CM,
    P3_PULL_UP_AVAILABLE_ITEMS,
    P3_PULL_UP_DAYS,
    P3_PULL_UP_TARGET_REPS,
    P3_PULL_UP_TARGET_WEIGHT_KG,
)


# ---------------------------------------------------------------------------
# Profile 1
# ---------------------------------------------------------------------------


class TestProfile1Init:
    def test_profile_fields(self, profile1_dir: Path):
        p = get_profile(profile1_dir)
        assert p["height_cm"] == P1_HEIGHT_CM
        assert p["current_bodyweight_kg"] == P1_BODYWEIGHT_KG

    def test_exercises_enabled(self, profile1_dir: Path):
        p = get_profile(profile1_dir)
        assert set(p["exercises_enabled"]) == {"dip", "incline_db_press", "bss"}

    def test_exercise_days(self, profile1_dir: Path):
        p = get_profile(profile1_dir)
        assert p["exercise_days"]["dip"] == P1_DIP_DAYS
        assert p["exercise_days"]["incline_db_press"] == P1_INCLINE_DAYS
        assert p["exercise_days"]["bss"] == P1_BSS_DAYS

    def test_exercise_targets(self, profile1_dir: Path):
        p = get_profile(profile1_dir)
        targets = p.get("exercise_targets", {})
        assert targets["dip"]["reps"] == P1_DIP_TARGET_REPS
        assert targets["incline_db_press"]["reps"] == P1_INCLINE_TARGET_REPS
        assert targets["incline_db_press"]["weight_kg"] == pytest.approx(P1_INCLINE_TARGET_WEIGHT_KG, abs=0.01)
        assert targets["bss"]["reps"] == P1_BSS_TARGET_REPS
        assert targets["bss"]["weight_kg"] == pytest.approx(P1_BSS_TARGET_WEIGHT_KG, abs=0.01)

    def test_dip_equipment(self, profile1_dir: Path):
        eq = get_current_equipment(profile1_dir, "dip")
        assert sorted(eq["available_items"]) == sorted(P1_DIP_AVAILABLE_ITEMS)
        assert eq["available_machine_assistance_kg"] == P1_DIP_MACHINE_ASSISTANCE_KG

    def test_incline_equipment(self, profile1_dir: Path):
        eq = get_current_equipment(profile1_dir, "incline_db_press")
        assert sorted(eq["available_items"]) == sorted(P1_INCLINE_AVAILABLE_ITEMS)
        # Discrete weight snapping verified indirectly via Layer 2 prescription checks

    def test_bss_equipment(self, profile1_dir: Path):
        eq = get_current_equipment(profile1_dir, "bss")
        assert sorted(eq["available_items"]) == sorted(P1_BSS_AVAILABLE_ITEMS)
        # Discrete weight snapping verified indirectly via Layer 2 prescription checks

    def test_history_populated(self, profile1_dir: Path):
        assert len(get_history(profile1_dir, "dip")) == 10
        assert len(get_history(profile1_dir, "incline_db_press")) == 10
        assert len(get_history(profile1_dir, "bss")) == 10


# ---------------------------------------------------------------------------
# Profile 2
# ---------------------------------------------------------------------------


class TestProfile2Init:
    def test_profile_fields(self, profile2_dir: Path):
        p = get_profile(profile2_dir)
        assert p["height_cm"] == P2_HEIGHT_CM
        assert p["current_bodyweight_kg"] == P2_BODYWEIGHT_KG

    def test_exercises_enabled(self, profile2_dir: Path):
        p = get_profile(profile2_dir)
        assert set(p["exercises_enabled"]) == {"pull_up", "dip"}

    def test_exercise_days(self, profile2_dir: Path):
        p = get_profile(profile2_dir)
        assert p["exercise_days"]["pull_up"] == P2_PULL_UP_DAYS
        assert p["exercise_days"]["dip"] == P2_DIP_DAYS

    def test_exercise_targets(self, profile2_dir: Path):
        p = get_profile(profile2_dir)
        targets = p.get("exercise_targets", {})
        assert targets["pull_up"]["reps"] == P2_PULL_UP_TARGET_REPS
        assert targets["dip"]["reps"] == P2_DIP_TARGET_REPS
        assert targets["dip"]["weight_kg"] == pytest.approx(P2_DIP_TARGET_WEIGHT_KG, abs=0.01)

    def test_pull_up_equipment(self, profile2_dir: Path):
        eq = get_current_equipment(profile2_dir, "pull_up")
        assert sorted(eq["available_items"]) == sorted(P2_PULL_UP_AVAILABLE_ITEMS)

    def test_dip_equipment(self, profile2_dir: Path):
        eq = get_current_equipment(profile2_dir, "dip")
        assert sorted(eq["available_items"]) == sorted(P2_DIP_AVAILABLE_ITEMS)

    def test_history_populated(self, profile2_dir: Path):
        assert len(get_history(profile2_dir, "pull_up")) == 10
        assert len(get_history(profile2_dir, "dip")) == 10


# ---------------------------------------------------------------------------
# Profile 3
# ---------------------------------------------------------------------------


class TestProfile3Init:
    def test_profile_fields(self, profile3_dir: Path):
        p = get_profile(profile3_dir)
        assert p["height_cm"] == P3_HEIGHT_CM
        assert p["current_bodyweight_kg"] == P3_BODYWEIGHT_KG

    def test_exercises_enabled(self, profile3_dir: Path):
        p = get_profile(profile3_dir)
        assert set(p["exercises_enabled"]) == {"bss", "pull_up"}

    def test_exercise_days(self, profile3_dir: Path):
        p = get_profile(profile3_dir)
        assert p["exercise_days"]["bss"] == P3_BSS_DAYS
        assert p["exercise_days"]["pull_up"] == P3_PULL_UP_DAYS

    def test_exercise_targets(self, profile3_dir: Path):
        p = get_profile(profile3_dir)
        targets = p.get("exercise_targets", {})
        assert targets["bss"]["reps"] == P3_BSS_TARGET_REPS
        assert targets["bss"]["weight_kg"] == pytest.approx(P3_BSS_TARGET_WEIGHT_KG, abs=0.01)
        assert targets["pull_up"]["reps"] == P3_PULL_UP_TARGET_REPS
        assert targets["pull_up"]["weight_kg"] == pytest.approx(P3_PULL_UP_TARGET_WEIGHT_KG, abs=0.01)

    def test_bss_equipment(self, profile3_dir: Path):
        eq = get_current_equipment(profile3_dir, "bss")
        assert sorted(eq["available_items"]) == sorted(P3_BSS_AVAILABLE_ITEMS)

    def test_pull_up_equipment_no_bands(self, profile3_dir: Path):
        """P3 pull_up has BAR_ONLY — absolute novice with no assisting equipment."""
        eq = get_current_equipment(profile3_dir, "pull_up")
        assert eq["available_items"] == P3_PULL_UP_AVAILABLE_ITEMS
        # No machine assistance configured
        assert eq.get("available_machine_assistance_kg", []) == []

    def test_history_populated(self, profile3_dir: Path):
        assert len(get_history(profile3_dir, "bss")) == 10
        assert len(get_history(profile3_dir, "pull_up")) == 10
