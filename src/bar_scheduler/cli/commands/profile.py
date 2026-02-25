"""Profile management commands: init, update-weight, and interactive menu helpers."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from ...core.equipment import (
    BSS_ELEVATION_HEIGHTS,
    BAND_PROGRESSION,
    bss_is_degraded,
    compute_equipment_adjustment,
    compute_leff,
    get_assistance_kg,
    get_catalog,
    snapshot_from_state,
)
from ...core.exercises.registry import get_exercise
from ...core.metrics import training_max_from_baseline
from ...core.models import EquipmentState, ExerciseTarget, SessionResult, SetResult, UserProfile
from .. import views
from ..app import ExerciseOption, app, get_store


@app.command()
def init(
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
    height_cm: Annotated[
        int,
        typer.Option("--height-cm", "-h", help="Height in centimeters"),
    ] = 175,
    sex: Annotated[
        str,
        typer.Option("--sex", "-s", help="Sex (male/female)"),
    ] = "male",
    days_per_week: Annotated[
        int,
        typer.Option("--days-per-week", "-d", help="Training days per week (3 or 4)"),
    ] = 3,
    target_max: Annotated[
        int,
        typer.Option("--target-max", "-t", help="Target max reps for this exercise"),
    ] = 30,
    target_weight: Annotated[
        float,
        typer.Option("--target-weight", help="Target added weight kg (0 = reps only)"),
    ] = 0.0,
    bodyweight_kg: Annotated[
        float,
        typer.Option("--bodyweight-kg", "-w", help="Current bodyweight in kg"),
    ] = 80.0,
    baseline_max: Annotated[
        Optional[int],
        typer.Option("--baseline-max", "-b", help="Baseline max reps (optional)"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force overwrite without prompting"),
    ] = False,
    exercise_id: ExerciseOption = "pull_up",
) -> None:
    """
    Initialize user profile and history file.

    Use --exercise to initialise a separate history for dip or bss without
    touching your pull-up data.  If history exists, offers to keep it
    (merge) or rename it as backup.

    To set different training days for each exercise, run init per exercise:

      bar-scheduler init --exercise pull_up --days-per-week 3
      bar-scheduler init --exercise dip --days-per-week 4

    Each exercise keeps its own schedule independently.
    """
    store = get_store(history_path, exercise_id)

    # Validate inputs
    if sex not in ("male", "female"):
        views.print_error("Sex must be 'male' or 'female'")
        raise typer.Exit(1)

    if days_per_week not in (3, 4):
        views.print_error("Days per week must be 3 or 4")
        raise typer.Exit(1)

    if bodyweight_kg <= 0:
        views.print_error("Bodyweight must be positive")
        raise typer.Exit(1)

    # Always load the existing profile — it may exist from another exercise's init
    # even when this exercise's history file is brand new.
    old_profile = None
    old_bw = None
    try:
        old_profile = store.load_profile()
        old_bw = store.load_bodyweight()
    except Exception:
        old_profile = None
        old_bw = None

    # Check for existing history (independent of profile existence)
    existing_sessions = 0
    if store.exists():
        try:
            existing = store.load_history()
            existing_sessions = len(existing)
        except Exception:
            existing_sessions = 0

        if existing_sessions > 0 and not force:
            views.print_warning(f"Found existing history with {existing_sessions} sessions.")
            views.console.print("\nOptions:")
            views.console.print("  [1] Keep existing history (update profile only)")
            views.console.print("  [2] Backup existing as 'history_old.jsonl' and start fresh")
            views.console.print("  [3] Cancel")

            choice = views.console.input("\nChoice [1/2/3]: ").strip()

            if choice == "3" or choice == "":
                views.print_info("Cancelled.")
                raise typer.Exit(0)
            elif choice == "2":
                # Backup existing history
                backup_path = store.history_path.parent / "history_old.jsonl"
                counter = 1
                while backup_path.exists():
                    backup_path = store.history_path.parent / f"history_old_{counter}.jsonl"
                    counter += 1
                store.history_path.rename(backup_path)
                views.print_success(f"Backed up existing history to {backup_path}")
                existing_sessions = 0
                old_profile = None  # fresh start — don't inherit old profile fields

    # Merge per-exercise days: inherit existing overrides, set this exercise's value.
    # For non-pull_up exercises, preserve the existing global preferred_days_per_week
    # so other exercises that rely on the global default are unaffected.
    merged_exercise_days: dict[str, int] = {}
    global_days = days_per_week  # used for preferred_days_per_week field
    if old_profile is not None:
        merged_exercise_days = dict(old_profile.exercise_days)
        if exercise_id not in (None, "pull_up"):
            # Keep existing global default; only this exercise's days change
            global_days = old_profile.preferred_days_per_week
    merged_exercise_days[exercise_id] = days_per_week

    # Merge per-exercise targets: inherit existing, update this exercise's goal.
    merged_exercise_targets: dict[str, ExerciseTarget] = {}
    if old_profile is not None:
        merged_exercise_targets = dict(old_profile.exercise_targets)
    merged_exercise_targets[exercise_id] = ExerciseTarget(reps=target_max, weight_kg=target_weight)

    # Create profile — preserve optional fields from existing profile when re-initialising
    profile = UserProfile(
        height_cm=height_cm,
        sex=sex,  # type: ignore
        preferred_days_per_week=global_days,
        exercise_days=merged_exercise_days,
        exercise_targets=merged_exercise_targets,
        exercises_enabled=(
            old_profile.exercises_enabled if old_profile is not None
            else ["pull_up", "dip", "bss"]
        ),
        max_session_duration_minutes=(
            old_profile.max_session_duration_minutes if old_profile is not None else 60
        ),
        rest_preference=(
            old_profile.rest_preference if old_profile is not None else "normal"
        ),
        injury_notes=(
            old_profile.injury_notes if old_profile is not None else ""
        ),
    )

    # Initialize store (creates file if not exists)
    store.init()
    store.save_profile(profile, bodyweight_kg)

    if existing_sessions > 0:
        views.print_success(f"Updated profile at {store.profile_path}")
        views.print_info(f"Kept existing history with {existing_sessions} sessions")
        if old_profile is not None:
            views.console.print()
            views.console.print("[bold]Profile changes:[/bold]")

            def _chg(label: str, old: object, new: object) -> None:
                marker = " [green](changed)[/green]" if old != new else ""
                views.console.print(f"  {label}: {old} → {new}{marker}")

            _chg("Height", f"{old_profile.height_cm} cm", f"{height_cm} cm")
            _chg("Sex", old_profile.sex, sex)
            _chg(f"Days/week ({exercise_id})", old_profile.exercise_days.get(exercise_id, old_profile.preferred_days_per_week), days_per_week)
            _chg(f"Target ({exercise_id})", str(old_profile.target_for_exercise(exercise_id)), str(ExerciseTarget(reps=target_max, weight_kg=target_weight)))
            old_bw_str = f"{old_bw:.1f} kg" if old_bw is not None else "?"
            _chg("Bodyweight", old_bw_str, f"{bodyweight_kg:.1f} kg")
    else:
        views.print_success(f"Initialized profile at {store.profile_path}")
        views.print_success(f"History file: {store.history_path}")
        views.print_info(f"Training days/week ({exercise_id}): {days_per_week}")

    # Set plan start date (2 days from today, the first training day)
    today = datetime.now()
    plan_start = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    store.set_plan_start_date(plan_start)

    if baseline_max is not None:
        # Log a baseline test session
        today_str = today.strftime("%Y-%m-%d")
        test_set = SetResult(
            target_reps=baseline_max,
            actual_reps=baseline_max,
            rest_seconds_before=180,
            added_weight_kg=0.0,
            rir_target=0,
            rir_reported=0,
        )
        session = SessionResult(
            date=today_str,
            bodyweight_kg=bodyweight_kg,
            grip="pronated",
            session_type="TEST",
            planned_sets=[test_set],
            completed_sets=[test_set],
            notes="Baseline max test",
        )
        store.append_session(session)
        views.print_success(f"Logged baseline test: {baseline_max} reps")

        tm = training_max_from_baseline(baseline_max)
        views.print_info(f"Training max: {tm}")


@app.command("update-weight")
def update_weight(
    bodyweight_kg: Annotated[
        float,
        typer.Option("--bodyweight-kg", "-w", help="New bodyweight in kg"),
    ],
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
) -> None:
    """
    Update current bodyweight in profile.
    """
    store = get_store(history_path)

    if not store.profile_path.exists():
        views.print_error(f"Profile not found: {store.profile_path}")
        views.print_info("Run 'init' first to create profile.")
        raise typer.Exit(1)

    if bodyweight_kg <= 0:
        views.print_error("Bodyweight must be positive")
        raise typer.Exit(1)

    try:
        store.update_bodyweight(bodyweight_kg)
    except FileNotFoundError as e:
        views.print_error(str(e))
        raise typer.Exit(1)

    views.print_success(f"Updated bodyweight to {bodyweight_kg:.1f} kg")


@app.command("update-equipment")
def update_equipment_cmd(
    exercise_id: ExerciseOption = "pull_up",
) -> None:
    """
    Update equipment for an exercise.

    Shows current equipment, asks what changed, and records a new entry in
    the equipment history. If effective load changes ≥ 10%, shows an
    adjustment recommendation for your next session.

    Example:
        bar-scheduler update-equipment --exercise pull_up
    """
    store = get_store(None)
    if not store.profile_path.exists():
        views.print_error(f"Profile not found: {store.profile_path}")
        views.print_info("Run 'init' first.")
        raise typer.Exit(1)

    existing = store.load_current_equipment(exercise_id)
    exercise = get_exercise(exercise_id)

    if existing is not None:
        views.console.print()
        a_kg = get_assistance_kg(existing.active_item, exercise_id, existing.machine_assistance_kg)
        catalog = get_catalog(exercise_id)
        item_label = catalog.get(existing.active_item, {}).get("label", existing.active_item)
        views.console.print(f"Current equipment — {exercise.display_name}:")
        views.console.print(f"  Active: {item_label}")
        if a_kg > 0:
            views.console.print(f"  Assistance: {a_kg:.1f} kg")
        if existing.elevation_height_cm:
            views.console.print(f"  Elevation: {existing.elevation_height_cm} cm")

    new_state = _ask_equipment(exercise_id, existing)

    # Compute Leff change for adjustment note
    if existing is not None:
        bw = store.load_bodyweight() or 80.0
        ex = get_exercise(exercise_id)
        old_a = get_assistance_kg(existing.active_item, exercise_id, existing.machine_assistance_kg)
        new_a = get_assistance_kg(new_state.active_item, exercise_id, new_state.machine_assistance_kg)
        old_leff = compute_leff(ex.bw_fraction, bw, 0.0, old_a)
        new_leff = compute_leff(ex.bw_fraction, bw, 0.0, new_a)

        adj = compute_equipment_adjustment(old_leff, new_leff)
        if adj["reps_factor"] != 1.0:
            views.console.print()
            views.print_warning(f"Equipment change detected: {adj['description']}")
            views.print_info(
                "Consider adjusting your target reps by this factor for the next session."
            )

    store.update_equipment(new_state)
    views.print_success(f"Equipment updated for {exercise.display_name}.")


def _detect_active_exercises() -> list[str]:
    """Return exercise IDs (in registry order) that have non-empty history files."""
    from ...io.history_store import get_default_history_path
    from ...core.exercises.registry import EXERCISE_REGISTRY

    active = []
    for ex_id in EXERCISE_REGISTRY:
        path = get_default_history_path(ex_id)
        if path.exists() and path.stat().st_size > 0:
            active.append(ex_id)
    return active


def _ask_days(label: str, default: int) -> int:
    """Prompt for training days/week (3 or 4) with a given label and default."""
    while True:
        raw = views.console.input(f"{label} (3/4) [{default}]: ").strip()
        if not raw:
            return default
        try:
            d = int(raw)
            if d in (3, 4):
                return d
        except ValueError:
            pass
        views.print_error("Enter 3 or 4")


def _ask_equipment(exercise_id: str, existing: EquipmentState | None = None) -> EquipmentState:
    """
    Interactively prompt for equipment setup for one exercise.

    Shows numbered options from the exercise catalog; supports multi-select
    for 'available' and single-select for 'active'.  For BSS, shows elevation
    height selection if ELEVATION_SURFACE is chosen.

    Returns a new EquipmentState (valid_from = today, valid_until = None).
    """
    from datetime import datetime

    today_str = datetime.now().strftime("%Y-%m-%d")
    catalog = get_catalog(exercise_id)
    items = list(catalog.items())   # [(id, info), ...]
    exercise = get_exercise(exercise_id)

    views.console.print()
    views.console.print(f"[bold]Equipment — {exercise.display_name}[/bold]")
    views.console.print("[dim]Which items do you have available? (comma-separated numbers)[/dim]")

    # Show numbered list
    for i, (item_id, info) in enumerate(items, 1):
        default_marker = " [dim](default)[/dim]" if i == 1 else ""
        views.console.print(f"  [{i}] {info['label']}{default_marker}")

    # Default: preserve existing available_items or just the first (base) item
    if existing is not None:
        default_avail = existing.available_items
        default_avail_str = ",".join(
            str(i + 1) for i, (item_id, _) in enumerate(items) if item_id in default_avail
        )
    else:
        default_avail_str = "1"

    while True:
        raw = views.console.input(f"  Available [{default_avail_str}]: ").strip()
        selection_str = raw if raw else default_avail_str
        try:
            indices = [int(x.strip()) for x in selection_str.split(",")]
            if all(1 <= idx <= len(items) for idx in indices):
                available_items = [items[idx - 1][0] for idx in indices]
                break
        except ValueError:
            pass
        views.print_error(f"Enter comma-separated numbers between 1 and {len(items)}")

    # Select active item from available subset.
    # Only ask when items have different effective assistance — otherwise the
    # choice has no impact on Leff and prompting is confusing.
    def _effective_assistance(item_id: str) -> object:
        a = catalog[item_id].get("assistance_kg")
        return "machine" if a is None else a

    unique_assistance = {_effective_assistance(iid) for iid in available_items}
    need_active_prompt = len(available_items) > 1 and len(unique_assistance) > 1

    if need_active_prompt:
        views.console.print()
        views.console.print(
            "[dim]Which one are you currently training WITH? "
            "This determines how much assistance is applied to your lift.[/dim]"
        )
        for i, item_id in enumerate(available_items, 1):
            info = catalog[item_id]
            views.console.print(f"  [{i}] {info['label']}")

        if existing is not None and existing.active_item in available_items:
            default_active_idx = available_items.index(existing.active_item) + 1
        else:
            default_active_idx = 1

        while True:
            raw = views.console.input(f"  Active item [{default_active_idx}]: ").strip()
            try:
                idx = int(raw) if raw else default_active_idx
                if 1 <= idx <= len(available_items):
                    active_item = available_items[idx - 1]
                    break
            except ValueError:
                pass
            views.print_error(f"Enter a number between 1 and {len(available_items)}")
    else:
        # All selected items have the same effective load — no prompt needed.
        if existing is not None and existing.active_item in available_items:
            active_item = existing.active_item
        else:
            active_item = available_items[0]

    # Machine-assisted: ask for kg
    machine_assistance_kg: float | None = None
    if active_item == "MACHINE_ASSISTED":
        default_machine = existing.machine_assistance_kg if existing else 40.0
        while True:
            raw = views.console.input(f"  Machine assistance kg [{default_machine}]: ").strip()
            try:
                val = float(raw) if raw else default_machine
                if val >= 0:
                    machine_assistance_kg = val
                    break
            except (TypeError, ValueError):
                pass
            views.print_error("Enter a non-negative number, e.g. 40")

    # BSS elevation height
    elevation_height_cm: int | None = None
    if exercise_id == "bss" and "ELEVATION_SURFACE" in available_items:
        default_elev = existing.elevation_height_cm if existing and existing.elevation_height_cm else 45
        heights_str = "/".join(str(h) for h in BSS_ELEVATION_HEIGHTS)
        while True:
            raw = views.console.input(
                f"  Elevation height cm ({heights_str}) [{default_elev}]: "
            ).strip()
            try:
                val = int(raw) if raw else default_elev
                if val in BSS_ELEVATION_HEIGHTS:
                    elevation_height_cm = val
                    break
            except ValueError:
                pass
            views.print_error(f"Enter one of: {heights_str}")

    # BSS degraded warning
    tmp_state = EquipmentState(
        exercise_id=exercise_id,
        available_items=available_items,
        active_item=active_item,
        machine_assistance_kg=machine_assistance_kg,
        elevation_height_cm=elevation_height_cm,
        valid_from=today_str,
    )
    if exercise_id == "bss" and bss_is_degraded(tmp_state):
        views.console.print()
        views.print_warning(
            "No elevation surface selected. The planner will programme Split Squats "
            "(rear foot flat) instead of Bulgarian Split Squats until you add a surface."
        )

    return tmp_state


def _menu_init() -> None:
    """Interactive profile setup helper called from the main menu."""
    from ...core.exercises.registry import EXERCISE_REGISTRY

    # Detect which exercises already have session data
    active_exercises = _detect_active_exercises()

    # Profile is shared across exercises — always use pull_up store path
    store = get_store(None)
    old_profile = store.load_profile()
    old_bw = store.load_bodyweight()

    views.console.print()
    views.console.print("[bold]Setup / Edit Profile[/bold]")
    views.console.print(
        "[dim]Covers: height, sex, bodyweight, target reps, "
        "training days/week per exercise, and equipment.[/dim]"
    )
    views.console.print("[dim]Press Enter to keep the current value.[/dim]")
    views.console.print()

    # Height
    default_h = old_profile.height_cm if old_profile else 175
    while True:
        raw = views.console.input(f"Height cm [{default_h}]: ").strip()
        if not raw:
            height_cm = default_h
            break
        try:
            height_cm = int(raw)
            if height_cm > 0:
                break
        except ValueError:
            pass
        views.print_error("Enter a positive integer, e.g. 180")

    # Sex
    default_sex = old_profile.sex if old_profile else "male"
    while True:
        raw = views.console.input(f"Sex (male/female) [{default_sex}]: ").strip().lower()
        if not raw:
            sex = default_sex
            break
        if raw in ("male", "female"):
            sex = raw
            break
        views.print_error("Enter 'male' or 'female'")

    # Days per week — asked per active exercise; start from existing exercise_days
    exercise_days_new: dict[str, int] = dict(old_profile.exercise_days) if old_profile else {}

    if not active_exercises:
        # Fresh / no data yet: one global question
        default_days = old_profile.preferred_days_per_week if old_profile else 3
        global_days = _ask_days("Training days per week", default_days)
    elif len(active_exercises) == 1:
        ex_id = active_exercises[0]
        ex_name = EXERCISE_REGISTRY[ex_id].display_name
        default_days = old_profile.days_for_exercise(ex_id) if old_profile else 3
        days = _ask_days(f"Training days per week — {ex_name}", default_days)
        exercise_days_new[ex_id] = days
        global_days = days
    else:
        views.console.print(
            f"[dim]You have data for {len(active_exercises)} exercises"
            " — configure days/week for each:[/dim]"
        )
        for ex_id in active_exercises:
            ex_name = EXERCISE_REGISTRY[ex_id].display_name
            default_days = old_profile.days_for_exercise(ex_id) if old_profile else 3
            days = _ask_days(f"  {ex_name} — days/week", default_days)
            exercise_days_new[ex_id] = days
        # Global fallback: pull_up if configured, else first exercise
        if "pull_up" in exercise_days_new:
            global_days = exercise_days_new["pull_up"]
        else:
            global_days = exercise_days_new[active_exercises[0]]

    # Per-exercise targets — ask for each active exercise (or pull_up if fresh)
    exercise_targets_new: dict[str, ExerciseTarget] = dict(old_profile.exercise_targets) if old_profile else {}
    exercises_to_target = active_exercises if active_exercises else ["pull_up"]
    for ex_id in exercises_to_target:
        ex_name = EXERCISE_REGISTRY[ex_id].display_name
        old_tgt = old_profile.target_for_exercise(ex_id) if old_profile else ExerciseTarget(reps=30)

        while True:
            raw = views.console.input(f"Target reps — {ex_name} [{old_tgt.reps}]: ").strip()
            if not raw:
                target_reps = old_tgt.reps
                break
            try:
                target_reps = int(raw)
                if target_reps > 0:
                    break
            except ValueError:
                pass
            views.print_error("Enter a positive integer, e.g. 30")

        default_wt = old_tgt.weight_kg
        while True:
            raw = views.console.input(
                f"Target added weight kg — {ex_name} [{default_wt:.1f}]: "
            ).strip()
            if not raw:
                target_wt = default_wt
                break
            try:
                target_wt = float(raw)
                if target_wt >= 0:
                    break
            except ValueError:
                pass
            views.print_error("Enter 0 or a positive number, e.g. 40")

        exercise_targets_new[ex_id] = ExerciseTarget(reps=target_reps, weight_kg=target_wt)

    # Bodyweight
    default_bw = old_bw if old_bw is not None else 80.0
    while True:
        raw = views.console.input(f"Bodyweight kg [{default_bw:.1f}]: ").strip()
        if not raw:
            bodyweight_kg = default_bw
            break
        try:
            bodyweight_kg = float(raw)
            if bodyweight_kg > 0:
                break
        except ValueError:
            pass
        views.print_error("Enter a positive number, e.g. 82.5")

    profile = UserProfile(
        height_cm=height_cm,
        sex=sex,  # type: ignore
        preferred_days_per_week=global_days,
        exercise_days=exercise_days_new,
        exercise_targets=exercise_targets_new,
    )
    store.init()
    store.save_profile(profile, bodyweight_kg)

    # Equipment setup — ask for each active exercise
    if active_exercises:
        exercises_to_configure = active_exercises
    else:
        exercises_to_configure = ["pull_up"]

    views.console.print()
    views.console.print("[bold]Equipment Setup[/bold]")
    views.console.print("[dim]Configure equipment for each exercise.[/dim]")

    for ex_id in exercises_to_configure:
        existing_eq = store.load_current_equipment(ex_id)
        new_eq_state = _ask_equipment(ex_id, existing_eq)
        store.update_equipment(new_eq_state)

    views.console.print()
    if old_profile is not None:
        views.console.print("[bold]Profile changes:[/bold]")

        def _chg(label: str, old: object, new: object) -> None:
            marker = " [green](changed)[/green]" if old != new else ""
            views.console.print(f"  {label}: {old} → {new}{marker}")

        _chg("Height", f"{old_profile.height_cm} cm", f"{height_cm} cm")
        _chg("Sex", old_profile.sex, sex)
        if not active_exercises:
            _chg("Days/week", old_profile.preferred_days_per_week, global_days)
        else:
            for ex_id, new_days in exercise_days_new.items():
                old_days = old_profile.exercise_days.get(ex_id, old_profile.preferred_days_per_week)
                ex_name = EXERCISE_REGISTRY[ex_id].display_name
                _chg(f"Days/week ({ex_name})", old_days, new_days)
        for ex_id, new_tgt in exercise_targets_new.items():
            old_tgt = old_profile.target_for_exercise(ex_id)
            ex_name = EXERCISE_REGISTRY[ex_id].display_name
            _chg(f"Target ({ex_name})", str(old_tgt), str(new_tgt))
        old_bw_str = f"{old_bw:.1f} kg" if old_bw is not None else "?"
        _chg("Bodyweight", old_bw_str, f"{bodyweight_kg:.1f} kg")
    else:
        views.print_success(f"Profile saved at {store.profile_path}")


def _menu_update_weight() -> None:
    """Interactive bodyweight update helper called from the main menu."""
    store = get_store(None)
    current_bw = store.load_bodyweight()
    hint = f" [{current_bw:.1f}]" if current_bw is not None else ""

    views.console.print()
    while True:
        raw = views.console.input(f"New bodyweight kg{hint}: ").strip()
        if not raw and current_bw is not None:
            views.print_info("No change.")
            return
        try:
            bodyweight_kg = float(raw)
            if bodyweight_kg > 0:
                break
        except ValueError:
            pass
        views.print_error("Enter a positive number, e.g. 82.5")

    try:
        store.update_bodyweight(bodyweight_kg)
        views.print_success(f"Updated bodyweight to {bodyweight_kg:.1f} kg")
    except Exception as e:
        views.print_error(str(e))
