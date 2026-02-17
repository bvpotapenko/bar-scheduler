"""
CLI entry point using Typer.

Provides commands for training plan management:
- init: Initialize user profile and history
- plan: Generate and display training plan
- log-session: Log a completed session
- show-history: Display training history
- plot-max: Show ASCII progress chart
- update-weight: Update current bodyweight
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from ..core.adaptation import get_training_status
from ..core.metrics import training_max_from_baseline
from ..core.models import SessionResult, SetResult, UserProfile
from ..core.planner import generate_plan
from ..io.history_store import HistoryStore, get_default_history_path
from ..io.serializers import ValidationError, parse_sets_string
from . import views


app = typer.Typer(
    name="bar-scheduler",
    help="Evidence-informed pull-up training planner to reach 30 strict pull-ups.",
    no_args_is_help=True,
)


def get_store(history_path: Path | None) -> HistoryStore:
    """Get history store from path or default."""
    if history_path is None:
        history_path = get_default_history_path()
    return HistoryStore(history_path)


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
) -> None:
    """
    Initialize user profile and history file.

    If history exists, offers to keep it (merge) or rename it as backup.
    """
    store = get_store(history_path)

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
    else:
        views.print_success(f"Initialized profile at {store.profile_path}")
        views.print_success(f"History file: {store.history_path}")

    if baseline_max is not None:
        # Log a baseline test session
        today = datetime.now().strftime("%Y-%m-%d")
        test_set = SetResult(
            target_reps=baseline_max,
            actual_reps=baseline_max,
            rest_seconds_before=180,
            added_weight_kg=0.0,
            rir_target=0,
            rir_reported=0,
        )
        session = SessionResult(
            date=today,
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


@app.command()
def plan(
    start_date: Annotated[
        Optional[str],
        typer.Option("--start-date", help="Start date (YYYY-MM-DD, default: tomorrow)"),
    ] = None,
    weeks: Annotated[
        Optional[int],
        typer.Option("--weeks", "-w", help="Number of weeks to plan"),
    ] = None,
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
    baseline_max: Annotated[
        Optional[int],
        typer.Option("--baseline-max", "-b", help="Baseline max reps (if no history)"),
    ] = None,
) -> None:
    """
    Generate and display a training plan.

    Shows current status and upcoming sessions.
    """
    store = get_store(history_path)

    if not store.exists():
        views.print_error(f"History file not found: {store.history_path}")
        views.print_info("Run 'init' first to create profile and history.")
        raise typer.Exit(1)

    try:
        user_state = store.load_user_state()
    except FileNotFoundError as e:
        views.print_error(str(e))
        views.print_info("Run 'init' first to create profile.")
        raise typer.Exit(1)
    except ValidationError as e:
        views.print_error(f"Invalid data: {e}")
        raise typer.Exit(1)

    # Default start date to tomorrow
    if start_date is None:
        start_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Check if we have history or baseline
    if not user_state.history and baseline_max is None:
        views.print_error("No history available. Provide --baseline-max or log a TEST session.")
        raise typer.Exit(1)

    try:
        plans = generate_plan(user_state, start_date, weeks, baseline_max)
    except ValueError as e:
        views.print_error(str(e))
        raise typer.Exit(1)

    # Get training status
    status = get_training_status(
        user_state.history,
        user_state.current_bodyweight_kg,
        baseline_max,
    )

    views.print_plan(plans, status, weeks)


@app.command("log-session")
def log_session(
    date: Annotated[
        str,
        typer.Option("--date", "-d", help="Session date (YYYY-MM-DD)"),
    ],
    bodyweight_kg: Annotated[
        float,
        typer.Option("--bodyweight-kg", "-w", help="Bodyweight in kg"),
    ],
    grip: Annotated[
        str,
        typer.Option("--grip", "-g", help="Grip type (pronated/supinated/neutral)"),
    ],
    session_type: Annotated[
        str,
        typer.Option("--session-type", "-t", help="Session type (S/H/E/T/TEST)"),
    ],
    sets: Annotated[
        str,
        typer.Option("--sets", "-s", help="Sets: reps@+kg/rest,reps@+kg/rest,... (e.g., 8@0/180,6@0/120)"),
    ],
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
    notes: Annotated[
        Optional[str],
        typer.Option("--notes", "-n", help="Session notes"),
    ] = None,
) -> None:
    """
    Log a completed training session.

    Sets format: reps@+kg/rest,reps@+kg/rest,...
    Example: 8@0/180,6@0/120,6@0/120,5@0/120
    """
    store = get_store(history_path)

    if not store.exists():
        views.print_error(f"History file not found: {store.history_path}")
        views.print_info("Run 'init' first to create profile and history.")
        raise typer.Exit(1)

    # Validate inputs
    if grip not in ("pronated", "supinated", "neutral"):
        views.print_error("Grip must be 'pronated', 'supinated', or 'neutral'")
        raise typer.Exit(1)

    if session_type not in ("S", "H", "E", "T", "TEST"):
        views.print_error("Session type must be S, H, E, T, or TEST")
        raise typer.Exit(1)

    if bodyweight_kg <= 0:
        views.print_error("Bodyweight must be positive")
        raise typer.Exit(1)

    # Parse sets
    try:
        parsed_sets = parse_sets_string(sets)
    except ValidationError as e:
        views.print_error(f"Invalid sets format: {e}")
        raise typer.Exit(1)

    # Create set results
    set_results: list[SetResult] = []
    for reps, weight, rest in parsed_sets:
        set_result = SetResult(
            target_reps=reps,
            actual_reps=reps,  # Logged sessions have actual = target
            rest_seconds_before=rest,
            added_weight_kg=weight,
            rir_target=2,  # Default
            rir_reported=None,
        )
        set_results.append(set_result)

    # Create session
    session = SessionResult(
        date=date,
        bodyweight_kg=bodyweight_kg,
        grip=grip,  # type: ignore
        session_type=session_type,  # type: ignore
        planned_sets=set_results.copy(),
        completed_sets=set_results,
        notes=notes,
    )

    try:
        store.append_session(session)
    except ValidationError as e:
        views.print_error(f"Invalid session data: {e}")
        raise typer.Exit(1)

    views.print_success(f"Logged {session_type} session for {date}")

    # Show summary
    total_reps = sum(s.actual_reps for s in set_results if s.actual_reps)
    max_reps = max((s.actual_reps for s in set_results if s.actual_reps and s.added_weight_kg == 0), default=0)

    views.print_info(f"Total reps: {total_reps}")
    if max_reps > 0:
        views.print_info(f"Max (bodyweight): {max_reps}")


@app.command("show-history")
def show_history(
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-l", help="Limit number of sessions to show"),
    ] = None,
) -> None:
    """
    Display training history as a table.
    """
    store = get_store(history_path)

    if not store.exists():
        views.print_error(f"History file not found: {store.history_path}")
        views.print_info("Run 'init' first to create profile and history.")
        raise typer.Exit(1)

    try:
        sessions = store.load_history()
    except (FileNotFoundError, ValidationError) as e:
        views.print_error(str(e))
        raise typer.Exit(1)

    if limit is not None:
        sessions = sessions[-limit:]

    views.print_history(sessions)


@app.command("plot-max")
def plot_max(
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
) -> None:
    """
    Display ASCII plot of max reps progress.
    """
    store = get_store(history_path)

    if not store.exists():
        views.print_error(f"History file not found: {store.history_path}")
        views.print_info("Run 'init' first to create profile and history.")
        raise typer.Exit(1)

    try:
        sessions = store.load_history()
    except (FileNotFoundError, ValidationError) as e:
        views.print_error(str(e))
        raise typer.Exit(1)

    views.print_max_plot(sessions)


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


@app.command()
def status(
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
) -> None:
    """
    Show current training status.
    """
    store = get_store(history_path)

    if not store.exists():
        views.print_error(f"History file not found: {store.history_path}")
        views.print_info("Run 'init' first to create profile and history.")
        raise typer.Exit(1)

    try:
        user_state = store.load_user_state()
    except (FileNotFoundError, ValidationError) as e:
        views.print_error(str(e))
        raise typer.Exit(1)

    status_info = get_training_status(
        user_state.history,
        user_state.current_bodyweight_kg,
    )

    views.console.print()
    views.console.print(views.format_status_display(status_info))
    views.console.print()


@app.command()
def volume(
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
    weeks: Annotated[
        int,
        typer.Option("--weeks", "-w", help="Number of weeks to show"),
    ] = 4,
) -> None:
    """
    Show weekly volume chart.
    """
    store = get_store(history_path)

    if not store.exists():
        views.print_error(f"History file not found: {store.history_path}")
        views.print_info("Run 'init' first to create profile and history.")
        raise typer.Exit(1)

    try:
        sessions = store.load_history()
    except (FileNotFoundError, ValidationError) as e:
        views.print_error(str(e))
        raise typer.Exit(1)

    views.print_volume_chart(sessions, weeks)


if __name__ == "__main__":
    app()
