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

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from ..core.adaptation import get_training_status
from ..core.metrics import session_max_reps, training_max_from_baseline
from ..core.models import SessionResult, SetResult, UserProfile
from ..core.planner import explain_plan_entry, generate_plan
from ..io.history_store import HistoryStore, get_default_history_path
from ..io.serializers import ValidationError, parse_compact_sets, parse_sets_string
from . import views

# Overperformance: if max reps in session significantly exceeds training max
OVERPERFORMANCE_REP_THRESHOLD = 2  # reps above TM to suggest TEST


app = typer.Typer(
    name="bar-scheduler",
    help="Evidence-informed pull-up training planner to reach 30 strict pull-ups.",
    no_args_is_help=False,
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """
    Pull-up training planner. Run without a command for interactive mode.
    """
    if ctx.invoked_subcommand is not None:
        return  # A sub-command was given — let it handle things

    # ── Interactive main menu ───────────────────────────────────────────────
    views.console.print()
    views.console.print("[bold cyan]bar-scheduler[/bold cyan] — pull-up training planner")
    views.console.print()

    menu = {
        "1": ("plan",          "Show training log & plan"),
        "2": ("log-session",   "Log today's session"),
        "3": ("show-history",  "Show full history"),
        "4": ("plot-max",      "Progress chart"),
        "5": ("status",        "Current status"),
        "6": ("update-weight", "Update bodyweight"),
        "7": ("volume",        "Weekly volume chart"),
        "e": ("explain",       "Explain how a session was planned"),
        "i": ("init",          "Setup / edit profile"),
        "d": ("delete-record", "Delete a session by ID"),
        "0": ("quit",          "Quit"),
    }

    for key, (_, desc) in menu.items():
        views.console.print(f"  \\[{key}] {desc}")

    views.console.print()
    choice = views.console.input("Choose [1]: ").strip() or "1"

    if choice == "0":
        raise typer.Exit(0)

    cmd_map = {k: v[0] for k, v in menu.items()}
    chosen = cmd_map.get(choice)

    if chosen is None:
        views.print_error(f"Unknown choice: {choice}")
        raise typer.Exit(1)

    # Invoke the chosen sub-command via typer
    if chosen == "plan":
        ctx.invoke(plan)
    elif chosen == "log-session":
        ctx.invoke(log_session)
    elif chosen == "show-history":
        ctx.invoke(show_history)
    elif chosen == "plot-max":
        ctx.invoke(plot_max)
    elif chosen == "status":
        ctx.invoke(status)
    elif chosen == "update-weight":
        _menu_update_weight()
    elif chosen == "volume":
        ctx.invoke(volume)
    elif chosen == "explain":
        _menu_explain()
    elif chosen == "init":
        _menu_init()
    elif chosen == "delete-record":
        _menu_delete_record()


def get_store(history_path: Path | None) -> HistoryStore:
    """Get history store from path or default."""
    if history_path is None:
        history_path = get_default_history_path()
    return HistoryStore(history_path)


def _menu_delete_record() -> None:
    """Interactive delete-session helper called from the main menu."""
    store = get_store(None)
    try:
        sessions = store.load_history()
    except Exception as e:
        views.print_error(str(e))
        return

    if not sessions:
        views.print_info("No sessions to delete.")
        return

    views.print_history(sessions)

    while True:
        raw = views.console.input("Delete session # (Enter to cancel): ").strip()
        if not raw:
            views.print_info("Cancelled.")
            return
        try:
            record_id = int(raw)
        except ValueError:
            views.print_error("Enter a number")
            continue

        if record_id < 1 or record_id > len(sessions):
            views.print_error(f"Enter a number between 1 and {len(sessions)}")
            continue

        target = sessions[record_id - 1]
        if views.confirm_action(f"Delete {target.date} ({target.session_type})?"):
            store.delete_session_at(record_id - 1)
            views.print_success(
                f"Deleted session #{record_id}: {target.date} ({target.session_type})"
            )
        else:
            views.print_info("Cancelled.")
        return


def _prompt_baseline(store: HistoryStore, bodyweight_kg: float) -> int | None:
    """
    Prompt user to enter their baseline max pull-ups when no history exists.

    Logs a TEST session and returns the rep count, or None if cancelled.
    """
    views.console.print()
    views.print_warning("No training history yet.")
    views.console.print(
        "\nTo generate a plan we need your current pull-up max.\n"
        "  [1] I know my max reps — enter it now\n"
        "  [2] I'm a beginner — use 1 rep as a starting point\n"
        "  [3] Cancel"
    )
    choice = views.console.input("\nChoice [1]: ").strip() or "1"

    if choice == "3":
        return None

    if choice == "2":
        max_reps = 1
    else:
        while True:
            raw = views.console.input("Your current max pull-ups (strict, full ROM): ").strip()
            try:
                max_reps = int(raw)
                if max_reps < 1:
                    raise ValueError
                break
            except ValueError:
                views.print_error("Enter a whole number ≥ 1")

    today = datetime.now().strftime("%Y-%m-%d")
    test_set = SetResult(
        target_reps=max_reps,
        actual_reps=max_reps,
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
        notes="Baseline max test (entered during plan setup)",
    )
    store.append_session(session)
    tm = training_max_from_baseline(max_reps)
    views.print_success(f"Logged baseline: {max_reps} reps. Training max (TM): {tm}.")
    return max_reps


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


def _menu_explain() -> None:
    """Interactive explain helper called from the main menu."""
    from ..core.config import MAX_PLAN_WEEKS

    store = get_store(None)
    try:
        user_state = store.load_user_state()
    except Exception as e:
        views.print_error(str(e))
        return

    plan_start_date = store.get_plan_start_date()
    if plan_start_date is None:
        if user_state.history:
            first_dt = datetime.strptime(user_state.history[0].date, "%Y-%m-%d")
            plan_start_date = (first_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            plan_start_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

    plan_start_dt = datetime.strptime(plan_start_date, "%Y-%m-%d")
    weeks_since_start = max(0, (datetime.now() - plan_start_dt).days // 7)
    total_weeks = max(2, min(weeks_since_start + 4, MAX_PLAN_WEEKS * 3))

    views.console.print()
    date_input = views.console.input("Date to explain (YYYY-MM-DD) or 'next' [next]: ").strip() or "next"

    if date_input.lower() == "next":
        try:
            plans = generate_plan(user_state, plan_start_date, total_weeks)
        except ValueError as e:
            views.print_error(str(e))
            return
        today_str = datetime.now().strftime("%Y-%m-%d")
        nxt = next((p for p in plans if p.date >= today_str), None)
        if nxt is None:
            views.print_error("No upcoming sessions in plan.")
            return
        date_input = nxt.date

    result = explain_plan_entry(user_state, plan_start_date, date_input, total_weeks)
    views.console.print()
    views.console.print(result)
    views.console.print()


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
            # Capture old profile before overwriting (for change display)
            if choice not in ("2", "3", ""):
                old_profile = store.load_profile()
                old_bw = store.load_bodyweight()
            else:
                old_profile = None
                old_bw = None
        else:
            old_profile = None
            old_bw = None
    else:
        old_profile = None
        old_bw = None

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


@app.command()
def plan(
    weeks: Annotated[
        Optional[int],
        typer.Option("--weeks", "-w", help="Number of weeks to show ahead (default: 4)"),
    ] = None,
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
    baseline_max: Annotated[
        Optional[int],
        typer.Option("--baseline-max", "-b", help="Baseline max reps (if no history)"),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON for machine processing"),
    ] = False,
) -> None:
    """
    Show the full training log: past results + upcoming plan in one view.

    Past sessions show what was planned vs what was actually done.
    Future sessions show what is prescribed next.
    The > marker shows your next session.
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

    if not user_state.history and baseline_max is None:
        baseline_max = _prompt_baseline(store, user_state.current_bodyweight_kg)
        if baseline_max is None:
            raise typer.Exit(0)
        # Reload state now that the baseline TEST session has been logged
        user_state = store.load_user_state()

    # Determine where the plan started (set by init; fall back to first history date)
    plan_start_date = store.get_plan_start_date()
    if plan_start_date is None:
        if user_state.history:
            # Fall back: use the day after first history entry
            first_dt = datetime.strptime(user_state.history[0].date, "%Y-%m-%d")
            plan_start_date = (first_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            plan_start_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Generate plan from plan_start_date for enough weeks to cover history + ahead
    # Calculate how many weeks since plan start to cover history
    plan_start_dt = datetime.strptime(plan_start_date, "%Y-%m-%d")
    weeks_since_start = max(0, (datetime.now() - plan_start_dt).days // 7)
    weeks_ahead = weeks if weeks is not None else 4
    total_weeks = weeks_since_start + weeks_ahead

    # Clamp to reasonable range
    from ..core.config import MAX_PLAN_WEEKS
    total_weeks = max(2, min(total_weeks, MAX_PLAN_WEEKS * 3))

    try:
        plans = generate_plan(user_state, plan_start_date, total_weeks, baseline_max)
    except ValueError as e:
        views.print_error(str(e))
        raise typer.Exit(1)

    # Get training status
    status = get_training_status(
        user_state.history,
        user_state.current_bodyweight_kg,
        baseline_max,
    )

    # Build unified timeline and display
    timeline = views.build_timeline(plans, user_state.history)

    if json_out:
        ff = status.fitness_fatigue_state
        sessions_json = []
        for e in timeline:
            plan_type = e.planned.session_type if e.planned else (e.actual.session_type if e.actual else "")
            plan_grip = e.planned.grip if e.planned else (e.actual.grip if e.actual else "")
            session_obj: dict = {
                "date": e.date,
                "week": e.week_number,
                "type": plan_type,
                "grip": plan_grip,
                "status": e.status,
                "id": e.actual_id,
                "expected_tm": e.planned.expected_tm if e.planned else None,
                "prescribed_sets": [
                    {"reps": ps.target_reps, "weight_kg": ps.added_weight_kg, "rest_s": ps.rest_seconds_before}
                    for ps in e.planned.sets
                ] if e.planned else None,
                "actual_sets": [
                    {"reps": sr.actual_reps, "weight_kg": sr.added_weight_kg, "rest_s": sr.rest_seconds_before}
                    for sr in e.actual.completed_sets
                    if sr.actual_reps is not None
                ] if e.actual else None,
            }
            sessions_json.append(session_obj)
        print(json.dumps({
            "status": {
                "training_max": status.training_max,
                "latest_test_max": status.latest_test_max,
                "trend_slope_per_week": round(status.trend_slope, 4),
                "is_plateau": status.is_plateau,
                "deload_recommended": status.deload_recommended,
                "readiness_z_score": round(ff.readiness_z_score(), 4),
            },
            "sessions": sessions_json,
        }, indent=2))
        return

    views.print_unified_plan(timeline, status)


@app.command()
def explain(
    date: Annotated[
        str,
        typer.Argument(
            help="Date to explain (YYYY-MM-DD) or 'next' for the next upcoming session"
        ),
    ],
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
    weeks: Annotated[
        Optional[int],
        typer.Option("--weeks", "-w", help="Plan horizon in weeks"),
    ] = None,
) -> None:
    """Show exactly how a planned session's parameters were calculated."""
    from ..core.config import MAX_PLAN_WEEKS

    store = get_store(history_path)

    try:
        user_state = store.load_user_state()
    except FileNotFoundError as e:
        views.print_error(str(e))
        views.print_info("Run 'init' first to create profile.")
        raise typer.Exit(1)
    except ValidationError as e:
        views.print_error(f"Invalid data: {e}")
        raise typer.Exit(1)

    # Resolve plan_start_date (same logic as plan command)
    plan_start_date = store.get_plan_start_date()
    if plan_start_date is None:
        if user_state.history:
            first_dt = datetime.strptime(user_state.history[0].date, "%Y-%m-%d")
            plan_start_date = (first_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            plan_start_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

    # Compute total weeks (same as plan command)
    plan_start_dt = datetime.strptime(plan_start_date, "%Y-%m-%d")
    weeks_since_start = max(0, (datetime.now() - plan_start_dt).days // 7)
    weeks_ahead_val = weeks if weeks is not None else 4
    total_weeks = max(2, min(weeks_since_start + weeks_ahead_val, MAX_PLAN_WEEKS * 3))

    # Resolve "next" → first upcoming planned session date
    if date.lower() == "next":
        try:
            plans = generate_plan(user_state, plan_start_date, total_weeks)
        except ValueError as e:
            views.print_error(str(e))
            raise typer.Exit(1)
        today_str = datetime.now().strftime("%Y-%m-%d")
        nxt = next((p for p in plans if p.date >= today_str), None)
        if nxt is None:
            views.print_error("No upcoming sessions in plan.")
            raise typer.Exit(1)
        date = nxt.date

    result = explain_plan_entry(user_state, plan_start_date, date, total_weeks)
    views.console.print()
    views.console.print(result)
    views.console.print()


def _interactive_sets() -> str:
    """
    Prompt the user to enter sets one by one.

    Accepts compact plan format on the first entry (before any sets have been entered):
        4x5 +0.5kg / 240s   → expands to 4 sets of 5 reps, +0.5 kg, 240 s rest
        4, 3x8 / 60s         → 1 set of 4 + 3 sets of 8, 60 s rest

    Also accepts per-set formats:
        8@0/180   canonical
        8 0 180   space-separated
        8         bare reps, bodyweight, 180 s rest
    """
    views.console.print()
    views.console.print("[bold]Enter sets one per line.[/bold]")
    views.console.print(
        "  Compact: [cyan]NxM +Wkg / Rs[/cyan]"
        "  e.g. [green]4x5 +0.5kg / 240s[/green]  [green]5x6 / 120s[/green]"
    )
    views.console.print(
        "  Per-set: [cyan]reps@+weight/rest[/cyan] or [cyan]reps weight rest[/cyan]"
        "  e.g. [green]8@0/180[/green]  [green]8 0 180[/green]  [green]8[/green]"
    )
    views.console.print("  Press [bold]Enter[/bold] on an empty line when done.\n")

    parts: list[str] = []
    set_num = 1
    while True:
        raw = views.console.input(f"  Set {set_num}: ").strip()
        if not raw:
            if parts:
                break
            views.print_warning("Enter at least one set.")
            continue
        if not raw[0].isdigit():
            views.print_error("Invalid format. Start with a number, e.g. 4x5 / 240s or 8@0/180")
            continue

        # When no sets have been entered yet, check for compact plan format.
        if not parts:
            compact = parse_compact_sets(raw)
            if compact is not None and len(compact) > 1:
                w = compact[0][1]
                r = compact[0][2]
                w_str = f" +{w:.1f} kg" if w > 0 else " (bodyweight)"
                views.console.print(
                    f"\n  [dim]Compact format — {len(compact)} sets{w_str}, {r}s rest:[/dim]"
                )
                for i, entry in enumerate(compact, 1):
                    views.console.print(f"    Set {i}: {entry[0]} reps")
                confirm = views.console.input("\n  Accept? [Y/n]: ").strip().lower()
                if confirm in ("", "y", "yes"):
                    return raw  # parse_sets_string will expand it
                views.console.print()
                views.print_info("Enter sets individually:")
                continue

        # Per-set validation — re-prompt on error instead of crashing later
        try:
            parse_sets_string(raw)
        except ValidationError as e:
            views.print_error(str(e))
            continue
        parts.append(raw)
        set_num += 1

    return ", ".join(parts)


@app.command("log-session")
def log_session(
    date: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Session date (YYYY-MM-DD, default: today)"),
    ] = None,
    bodyweight_kg: Annotated[
        Optional[float],
        typer.Option("--bodyweight-kg", "-w", help="Bodyweight in kg"),
    ] = None,
    grip: Annotated[
        Optional[str],
        typer.Option("--grip", "-g", help="Grip type: pronated | supinated | neutral"),
    ] = None,
    session_type: Annotated[
        Optional[str],
        typer.Option("--session-type", "-t", help="Session type: S | H | E | T | M (max test)"),
    ] = None,
    sets: Annotated[
        Optional[str],
        typer.Option("--sets", "-s", help="Sets: reps@+kg/rest,... e.g. 8@0/180,6@0"),
    ] = None,
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
    notes: Annotated[
        Optional[str],
        typer.Option("--notes", "-n", help="Session notes"),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON for machine processing"),
    ] = False,
) -> None:
    """
    Log a completed training session.

    Run without options for interactive step-by-step entry.
    Or supply all options for one-liner use:

      bar-scheduler log-session --date 2026-02-18 --bodyweight-kg 82 \\
        --grip pronated --session-type S --sets "8@0/180,6@0/120,6@0"
    """
    store = get_store(history_path)

    if not store.exists():
        views.print_error(f"History file not found: {store.history_path}")
        views.print_info("Run 'init' first to create profile and history.")
        raise typer.Exit(1)

    # ── Interactive prompts for missing values ──────────────────────────────

    # Date
    if date is None:
        default_date = datetime.now().strftime("%Y-%m-%d")
        raw = views.console.input(f"Date [{default_date}]: ").strip()
        date = raw if raw else default_date

    # Bodyweight
    if bodyweight_kg is None:
        # Try to use last known bodyweight as default
        saved_bw = store.load_bodyweight()
        bw_hint = f" [{saved_bw:.1f}]" if saved_bw else ""
        while True:
            raw = views.console.input(f"Bodyweight kg{bw_hint}: ").strip()
            if not raw and saved_bw:
                bodyweight_kg = saved_bw
                break
            try:
                bodyweight_kg = float(raw)
                if bodyweight_kg <= 0:
                    raise ValueError
                break
            except ValueError:
                views.print_error("Enter a positive number, e.g. 82.5")

    # Grip
    if grip is None:
        views.console.print("Grip: [1] pronated  [2] neutral  [3] supinated")
        grip_map = {"1": "pronated", "2": "neutral", "3": "supinated",
                    "pronated": "pronated", "neutral": "neutral", "supinated": "supinated"}
        while True:
            raw = views.console.input("Grip [1]: ").strip() or "1"
            grip = grip_map.get(raw.lower())
            if grip:
                break
            views.print_error("Choose 1, 2, 3 or type pronated/neutral/supinated")

    # Session type
    if session_type is None:
        views.console.print("Session type: [S] Strength  [H] Hypertrophy  [E] Endurance  [T] Technique  [M] Max test")
        valid_types = {"s": "S", "h": "H", "e": "E", "t": "T", "m": "TEST",
                       "S": "S", "H": "H", "E": "E", "T": "T", "M": "TEST", "TEST": "TEST"}
        while True:
            raw = views.console.input("Type [S]: ").strip() or "S"
            session_type = valid_types.get(raw.upper(), valid_types.get(raw))
            if session_type:
                break
            views.print_error("Choose S, H, E, T, or TEST")

    # Sets
    if sets is None:
        sets = _interactive_sets()

    # ── Validate all inputs ─────────────────────────────────────────────────

    if grip not in ("pronated", "supinated", "neutral"):
        views.print_error("Grip must be pronated, supinated, or neutral")
        raise typer.Exit(1)

    if session_type not in ("S", "H", "E", "T", "TEST"):
        views.print_error("Session type must be S, H, E, T, or M (max test)")
        raise typer.Exit(1)

    if bodyweight_kg <= 0:
        views.print_error("Bodyweight must be positive")
        raise typer.Exit(1)

    try:
        parsed_sets = parse_sets_string(sets)
    except ValidationError as e:
        views.print_error(f"Invalid sets format: {e}")
        raise typer.Exit(1)

    # ── Build and save session ──────────────────────────────────────────────

    set_results: list[SetResult] = []
    for reps, weight, rest in parsed_sets:
        set_result = SetResult(
            target_reps=reps,
            actual_reps=reps,
            rest_seconds_before=rest,
            added_weight_kg=weight,
            rir_target=2,
            rir_reported=None,
        )
        set_results.append(set_result)

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

    # Auto-update profile bodyweight if it changed
    try:
        saved_bw = store.load_bodyweight()
        if saved_bw is None or abs(bodyweight_kg - saved_bw) > 0.05:
            store.update_bodyweight(bodyweight_kg)
    except Exception:
        pass

    total_reps = sum(s.actual_reps for s in set_results if s.actual_reps)
    max_reps_bw = max(
        (s.actual_reps for s in set_results if s.actual_reps and s.added_weight_kg == 0),
        default=0,
    )
    max_reps_weighted = max(
        (round(s.actual_reps * (1 + s.added_weight_kg / bodyweight_kg))
         for s in set_results if s.actual_reps and s.added_weight_kg > 0),
        default=0,
    )
    max_reps = max(max_reps_bw, max_reps_weighted)

    # Overperformance / personal best detection
    new_personal_best = False
    new_tm: int | None = None
    if session_type != "TEST" and max_reps > 0:
        try:
            user_state = store.load_user_state()
            train_status = get_training_status(user_state.history, user_state.current_bodyweight_kg)
            tm = train_status.training_max
            test_max = train_status.latest_test_max or 0

            if max_reps > test_max:
                # New personal best — auto-log a TEST session silently
                test_set = SetResult(
                    target_reps=max_reps,
                    actual_reps=max_reps,
                    rest_seconds_before=180,
                    added_weight_kg=0.0,
                    rir_target=0,
                    rir_reported=0,
                )
                test_session = SessionResult(
                    date=date,
                    bodyweight_kg=bodyweight_kg,
                    grip="pronated",
                    session_type="TEST",
                    planned_sets=[test_set],
                    completed_sets=[test_set],
                    notes="Auto-logged from session personal best",
                )
                store.append_session(test_session)
                new_tm = training_max_from_baseline(max_reps)
                new_personal_best = True
                if not json_out:
                    est_note = " (BW-equivalent from weighted set)" if max_reps_weighted > max_reps_bw else ""
                    views.console.print()
                    views.print_success(
                        f"New personal best! Auto-logged TEST ({max_reps} reps{est_note}) — TM updated to {new_tm}."
                    )
            elif max_reps >= tm + OVERPERFORMANCE_REP_THRESHOLD and not json_out:
                views.console.print()
                views.print_warning(
                    f"Great performance! Your max ({max_reps}) exceeds TM ({tm}) by {max_reps - tm} reps."
                )
                views.print_info(
                    "The plan won't update automatically — log a TEST session to set a new baseline."
                )
        except Exception:
            pass

    if json_out:
        print(json.dumps({
            "date": date,
            "session_type": session_type,
            "grip": grip,
            "bodyweight_kg": bodyweight_kg,
            "total_reps": total_reps,
            "max_reps_bodyweight": max_reps_bw,
            "max_reps_equivalent": max_reps,
            "new_personal_best": new_personal_best,
            "new_tm": new_tm,
            "sets": [
                {"reps": s.actual_reps, "weight_kg": s.added_weight_kg, "rest_s": s.rest_seconds_before}
                for s in set_results
            ],
        }, indent=2))
        return

    views.console.print()
    views.print_success(f"Logged {session_type} session for {date}")
    views.print_info(f"Total reps: {total_reps}")
    if max_reps_bw > 0:
        views.print_info(f"Max (bodyweight): {max_reps_bw}")
    if max_reps_weighted > max_reps_bw:
        views.print_info(f"Max (BW-equivalent from weighted): {max_reps_weighted}")


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
    json_out: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON for machine processing"),
    ] = False,
) -> None:
    """
    Display training history as a table.
    """
    from ..core.metrics import session_avg_rest, session_max_reps, session_total_reps

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

    if json_out:
        output = []
        for s in sessions:
            output.append({
                "date": s.date,
                "session_type": s.session_type,
                "grip": s.grip,
                "bodyweight_kg": s.bodyweight_kg,
                "total_reps": session_total_reps(s),
                "max_reps": session_max_reps(s),
                "avg_rest_s": round(session_avg_rest(s)),
                "sets": [
                    {
                        "reps": sr.actual_reps,
                        "weight_kg": sr.added_weight_kg,
                        "rest_s": sr.rest_seconds_before,
                    }
                    for sr in s.completed_sets
                    if sr.actual_reps is not None
                ],
            })
        print(json.dumps(output, indent=2))
        return

    views.print_history(sessions)


@app.command("plot-max")
def plot_max(
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON for machine processing"),
    ] = False,
) -> None:
    """
    Display ASCII plot of max reps progress.
    """
    from ..core.metrics import get_test_sessions, session_max_reps as _max_reps

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

    if json_out:
        data_points = [
            {"date": s.date, "max_reps": _max_reps(s)}
            for s in get_test_sessions(sessions)
            if _max_reps(s) > 0
        ]
        print(json.dumps({"data_points": data_points}, indent=2))
        return

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
    json_out: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON for machine processing"),
    ] = False,
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

    if json_out:
        ff = status_info.fitness_fatigue_state
        print(json.dumps({
            "training_max": status_info.training_max,
            "latest_test_max": status_info.latest_test_max,
            "trend_slope_per_week": round(status_info.trend_slope, 4),
            "is_plateau": status_info.is_plateau,
            "deload_recommended": status_info.deload_recommended,
            "readiness_z_score": round(ff.readiness_z_score(), 4),
            "fitness": round(ff.fitness, 4),
            "fatigue": round(ff.fatigue, 4),
        }, indent=2))
        return

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
    json_out: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON for machine processing"),
    ] = False,
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

    if json_out:
        weekly: dict[int, int] = {}
        if sessions:
            latest = datetime.strptime(sessions[-1].date, "%Y-%m-%d")
            for s in sessions:
                ago = (latest - datetime.strptime(s.date, "%Y-%m-%d")).days // 7
                if ago < weeks:
                    reps = sum(sr.actual_reps for sr in s.completed_sets if sr.actual_reps is not None)
                    weekly[ago] = weekly.get(ago, 0) + reps
        result = []
        for i in range(weeks - 1, -1, -1):
            label = "This week" if i == 0 else ("Last week" if i == 1 else f"{i} weeks ago")
            result.append({"label": label, "total_reps": weekly.get(i, 0)})
        print(json.dumps({"weeks": result}, indent=2))
        return

    views.print_volume_chart(sessions, weeks)


@app.command("delete-record")
def delete_record(
    record_id: Annotated[
        int,
        typer.Argument(help="Session ID to delete (see # column in show-history)"),
    ],
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """
    Remove a session by its ID.

    Use 'show-history' to see session IDs in the # column.
    """
    store = get_store(history_path)

    try:
        sessions = store.load_history()
    except (FileNotFoundError, ValidationError) as e:
        views.print_error(str(e))
        raise typer.Exit(1)

    if not sessions:
        views.print_error("No sessions in history.")
        raise typer.Exit(1)

    if record_id < 1 or record_id > len(sessions):
        views.print_error(f"Record ID must be between 1 and {len(sessions)}")
        raise typer.Exit(1)

    target = sessions[record_id - 1]
    views.console.print(f"Session to delete: [bold]{target.date}[/bold] ({target.session_type})")

    if not force and not views.confirm_action("Delete this session?"):
        views.print_info("Cancelled.")
        raise typer.Exit(0)

    try:
        store.delete_session_at(record_id - 1)
    except Exception as e:
        views.print_error(str(e))
        raise typer.Exit(1)

    views.print_success(f"Deleted session #{record_id}: {target.date} ({target.session_type})")


if __name__ == "__main__":
    app()
