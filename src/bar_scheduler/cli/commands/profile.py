"""Profile management commands: init, update-weight, and interactive menu helpers."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from ...core.metrics import training_max_from_baseline
from ...core.models import SessionResult, SetResult, UserProfile
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
        typer.Option("--target-max", "-t", help="Target max reps"),
    ] = 30,
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

    # Check for existing history
    existing_sessions = 0
    old_profile = None
    old_bw = None
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
            # choice == "1" means keep existing, just update profile
            if choice not in ("2", "3", ""):
                old_profile = store.load_profile()
                old_bw = store.load_bodyweight()

    # Create profile
    profile = UserProfile(
        height_cm=height_cm,
        sex=sex,  # type: ignore
        preferred_days_per_week=days_per_week,
        target_max_reps=target_max,
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
            _chg("Days/week", old_profile.preferred_days_per_week, days_per_week)
            _chg("Target max reps", old_profile.target_max_reps, target_max)
            old_bw_str = f"{old_bw:.1f} kg" if old_bw is not None else "?"
            _chg("Bodyweight", old_bw_str, f"{bodyweight_kg:.1f} kg")
    else:
        views.print_success(f"Initialized profile at {store.profile_path}")
        views.print_success(f"History file: {store.history_path}")

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


def _menu_init() -> None:
    """Interactive profile setup helper called from the main menu."""
    store = get_store(None)

    old_profile = store.load_profile()
    old_bw = store.load_bodyweight()

    views.console.print()
    views.console.print("[bold]Setup / Edit Profile[/bold]")
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

    # Days per week
    default_days = old_profile.preferred_days_per_week if old_profile else 3
    while True:
        raw = views.console.input(f"Training days per week (3/4) [{default_days}]: ").strip()
        if not raw:
            days_per_week = default_days
            break
        try:
            days_per_week = int(raw)
            if days_per_week in (3, 4):
                break
        except ValueError:
            pass
        views.print_error("Enter 3 or 4")

    # Target max reps
    default_target = old_profile.target_max_reps if old_profile else 30
    while True:
        raw = views.console.input(f"Target max reps [{default_target}]: ").strip()
        if not raw:
            target_max = default_target
            break
        try:
            target_max = int(raw)
            if target_max > 0:
                break
        except ValueError:
            pass
        views.print_error("Enter a positive integer, e.g. 30")

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
        preferred_days_per_week=days_per_week,
        target_max_reps=target_max,
    )
    store.init()
    store.save_profile(profile, bodyweight_kg)

    views.console.print()
    if old_profile is not None:
        views.console.print("[bold]Profile changes:[/bold]")

        def _chg(label: str, old: object, new: object) -> None:
            marker = " [green](changed)[/green]" if old != new else ""
            views.console.print(f"  {label}: {old} → {new}{marker}")

        _chg("Height", f"{old_profile.height_cm} cm", f"{height_cm} cm")
        _chg("Sex", old_profile.sex, sex)
        _chg("Days/week", old_profile.preferred_days_per_week, days_per_week)
        _chg("Target max reps", old_profile.target_max_reps, target_max)
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
