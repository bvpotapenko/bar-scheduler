"""
Session-scoped fixtures and shared helpers for the golden test suite.

Datetime is frozen to 2026-01-12 (Monday) for the entire test session so that
plan-start resolution and session status ("next"/"planned"/"missed") are deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import time_machine

from bar_scheduler.api import (
    enable_exercise,
    get_history,
    init_profile,
    log_session,
    set_exercise_target,
    set_plan_start_date,
    update_equipment,
)
from bar_scheduler.api.types import SessionInput, SetInput

from .constants_p1 import (
    P1_BODYWEIGHT_KG,
    P1_BSS_AVAILABLE_ITEMS,
    P1_BSS_DAYS,
    P1_BSS_TARGET_REPS,
    P1_BSS_TARGET_WEIGHT_KG,
    P1_BSS_WEIGHTS_KG,
    P1_DIP_AVAILABLE_ITEMS,
    P1_DIP_DAYS,
    P1_DIP_MACHINE_ASSISTANCE_KG,
    P1_DIP_TARGET_REPS,
    P1_DIP_TARGET_WEIGHT_KG,
    P1_HEIGHT_CM,
    P1_INCLINE_AVAILABLE_ITEMS,
    P1_INCLINE_DAYS,
    P1_INCLINE_TARGET_REPS,
    P1_INCLINE_TARGET_WEIGHT_KG,
    P1_INCLINE_WEIGHTS_KG,
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
    P2_PULL_UP_TARGET_WEIGHT_KG,
)
from .constants_p3 import (
    P3_BODYWEIGHT_KG,
    P3_BSS_AVAILABLE_ITEMS,
    P3_BSS_DAYS,
    P3_BSS_TARGET_REPS,
    P3_BSS_TARGET_WEIGHT_KG,
    P3_BSS_WEIGHTS_KG,
    P3_HEIGHT_CM,
    P3_PULL_UP_AVAILABLE_ITEMS,
    P3_PULL_UP_DAYS,
    P3_PULL_UP_TARGET_REPS,
    P3_PULL_UP_TARGET_WEIGHT_KG,
)
from .history_data import (
    P1_BSS_HISTORY,
    P1_DIP_HISTORY,
    P1_INCLINE_HISTORY,
    P2_DIP_HISTORY,
    P2_PULL_UP_HISTORY,
    P3_BSS_HISTORY,
    P3_PULL_UP_HISTORY,
)

FROZEN_TODAY = "2026-01-12"
PLAN_START = "2026-01-13"


# ---------------------------------------------------------------------------
# Datetime freeze
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def freeze_time():
    """Freeze datetime.now() to FROZEN_TODAY for each golden test function.

    Function-scoped so the context does not leak into tests outside tests/golden/.
    Profile fixtures (session-scoped) do not call datetime.now(), so they don't need
    the freeze during setup — only get_plan() calls during test execution do.
    """
    with time_machine.travel(FROZEN_TODAY, tick=False):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(d: dict) -> SessionInput:
    """Convert a plain dict (from history_data or constants) to a SessionInput."""
    sets = [
        SetInput(
            reps=s["reps"],
            rest_seconds=s["rest_seconds"],
            added_weight_kg=s.get("added_weight_kg", 0.0),
            rir_reported=s.get("rir_reported"),
        )
        for s in d["sets"]
    ]
    return SessionInput(
        date=d["date"],
        session_type=d["session_type"],
        bodyweight_kg=d["bodyweight_kg"],
        sets=sets,
        grip=d.get("grip", "standard"),
        notes=d.get("notes", ""),
    )


def _log_history(data_dir: Path, exercise_id: str, sessions: list[dict]) -> None:
    for s in sessions:
        log_session(data_dir, exercise_id, _make_session(s))


def next_session_index(data_dir: Path, exercise_id: str) -> int:
    """Return the 1-based index of the next session (= current length + 1)."""
    return len(get_history(data_dir, exercise_id)) + 1


# ---------------------------------------------------------------------------
# Profile 1 fixture (session-scoped)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def profile1_dir(tmp_path_factory):
    d: Path = tmp_path_factory.mktemp("p1")

    init_profile(d, height_cm=P1_HEIGHT_CM, bodyweight_kg=P1_BODYWEIGHT_KG)

    enable_exercise(d, "dip", days_per_week=P1_DIP_DAYS)
    set_exercise_target(d, "dip", reps=P1_DIP_TARGET_REPS, weight_kg=P1_DIP_TARGET_WEIGHT_KG)
    update_equipment(
        d, "dip",
        available_items=P1_DIP_AVAILABLE_ITEMS,
        available_machine_assistance_kg=P1_DIP_MACHINE_ASSISTANCE_KG,
    )

    enable_exercise(d, "incline_db_press", days_per_week=P1_INCLINE_DAYS)
    set_exercise_target(d, "incline_db_press", reps=P1_INCLINE_TARGET_REPS, weight_kg=P1_INCLINE_TARGET_WEIGHT_KG)
    update_equipment(
        d, "incline_db_press",
        available_items=P1_INCLINE_AVAILABLE_ITEMS,
        available_weights_kg=P1_INCLINE_WEIGHTS_KG,
    )

    enable_exercise(d, "bss", days_per_week=P1_BSS_DAYS)
    set_exercise_target(d, "bss", reps=P1_BSS_TARGET_REPS, weight_kg=P1_BSS_TARGET_WEIGHT_KG)
    update_equipment(
        d, "bss",
        available_items=P1_BSS_AVAILABLE_ITEMS,
        available_weights_kg=P1_BSS_WEIGHTS_KG,
    )

    # Log baseline history then pin plan start
    _log_history(d, "dip", P1_DIP_HISTORY)
    set_plan_start_date(d, "dip", PLAN_START)

    _log_history(d, "incline_db_press", P1_INCLINE_HISTORY)
    set_plan_start_date(d, "incline_db_press", PLAN_START)

    _log_history(d, "bss", P1_BSS_HISTORY)
    set_plan_start_date(d, "bss", PLAN_START)

    return d


# ---------------------------------------------------------------------------
# Profile 2 fixture (session-scoped)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def profile2_dir(tmp_path_factory):
    d: Path = tmp_path_factory.mktemp("p2")

    init_profile(d, height_cm=P2_HEIGHT_CM, bodyweight_kg=P2_BODYWEIGHT_KG)

    enable_exercise(d, "pull_up", days_per_week=P2_PULL_UP_DAYS)
    set_exercise_target(d, "pull_up", reps=P2_PULL_UP_TARGET_REPS, weight_kg=P2_PULL_UP_TARGET_WEIGHT_KG)
    update_equipment(d, "pull_up", available_items=P2_PULL_UP_AVAILABLE_ITEMS)

    enable_exercise(d, "dip", days_per_week=P2_DIP_DAYS)
    set_exercise_target(d, "dip", reps=P2_DIP_TARGET_REPS, weight_kg=P2_DIP_TARGET_WEIGHT_KG)
    update_equipment(d, "dip", available_items=P2_DIP_AVAILABLE_ITEMS)

    _log_history(d, "pull_up", P2_PULL_UP_HISTORY)
    set_plan_start_date(d, "pull_up", PLAN_START)

    _log_history(d, "dip", P2_DIP_HISTORY)
    set_plan_start_date(d, "dip", PLAN_START)

    return d


# ---------------------------------------------------------------------------
# Profile 3 fixture (session-scoped)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def profile3_dir(tmp_path_factory):
    d: Path = tmp_path_factory.mktemp("p3")

    init_profile(d, height_cm=P3_HEIGHT_CM, bodyweight_kg=P3_BODYWEIGHT_KG)

    enable_exercise(d, "bss", days_per_week=P3_BSS_DAYS)
    set_exercise_target(d, "bss", reps=P3_BSS_TARGET_REPS, weight_kg=P3_BSS_TARGET_WEIGHT_KG)
    update_equipment(
        d, "bss",
        available_items=P3_BSS_AVAILABLE_ITEMS,
        available_weights_kg=P3_BSS_WEIGHTS_KG,
    )

    enable_exercise(d, "pull_up", days_per_week=P3_PULL_UP_DAYS)
    set_exercise_target(d, "pull_up", reps=P3_PULL_UP_TARGET_REPS, weight_kg=P3_PULL_UP_TARGET_WEIGHT_KG)
    update_equipment(d, "pull_up", available_items=P3_PULL_UP_AVAILABLE_ITEMS)

    _log_history(d, "bss", P3_BSS_HISTORY)
    set_plan_start_date(d, "bss", PLAN_START)

    _log_history(d, "pull_up", P3_PULL_UP_HISTORY)
    set_plan_start_date(d, "pull_up", PLAN_START)

    return d
