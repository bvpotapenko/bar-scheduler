"""Planning commands: plan, explain, skip, and interactive menu helpers."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from ...core.adaptation import get_training_status
from ...core.exercises.registry import get_exercise
from ...core.metrics import training_max_from_baseline
from ...core.models import SessionResult, SetResult
from ...core.planner import explain_plan_entry, generate_plan
from ...io.serializers import ValidationError
from .. import views
from ..app import ExerciseOption, app, get_store


def _prompt_baseline(store, bodyweight_kg: float) -> int | None:
    """
    Prompt user to enter their baseline max reps when no history exists.

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


def _session_snapshot(entry) -> dict:
    """Create a compact plan snapshot dict from a timeline entry (for cache diffing)."""
    p = entry.planned
    if p is None:
        return {}
    first_set = p.sets[0] if p.sets else None
    return {
        "date": p.date,
        "type": p.session_type,
        "sets": len(p.sets),
        "reps": first_set.target_reps if first_set else 0,
        "weight": first_set.added_weight_kg if first_set else 0.0,
        "rest": first_set.rest_seconds_before if first_set else 0,
        "expected_tm": p.expected_tm,
    }


def _diff_plan(old: list[dict], new: list[dict]) -> list[str]:
    """Compare old and new plan snapshots; return human-readable change strings."""
    old_idx = {(s["date"], s["type"]): s for s in old if s}
    new_idx = {(s["date"], s["type"]): s for s in new if s}
    changes: list[str] = []

    for key, snap in new_idx.items():
        if key not in old_idx:
            changes.append(f"New: {snap['date']} {snap['type']}")

    for key, snap in old_idx.items():
        if key not in new_idx:
            changes.append(f"Removed: {snap['date']} {snap['type']}")

    for key in sorted(set(old_idx) & set(new_idx)):
        o, n = old_idx[key], new_idx[key]
        parts: list[str] = []
        if o["sets"] != n["sets"]:
            parts.append(f"{o['sets']}→{n['sets']} sets")
        if o["reps"] != n["reps"]:
            parts.append(f"{o['reps']}→{n['reps']} reps")
        if abs(o.get("weight", 0.0) - n.get("weight", 0.0)) > 0.01:
            parts.append(f"+{o['weight']:.1f}→+{n['weight']:.1f} kg")
        if o["expected_tm"] != n["expected_tm"]:
            parts.append(f"TM {o['expected_tm']}→{n['expected_tm']}")
        if parts:
            changes.append(f"{n['date']} {n['type']}: {', '.join(parts)}")

    return changes


def _menu_explain() -> None:
    """Interactive explain helper called from the main menu."""
    from ...core.config import MAX_PLAN_WEEKS

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
    exercise_id: ExerciseOption = "pull_up",
) -> None:
    """
    Show the full training log: past results + upcoming plan in one view.

    Past sessions show what was planned vs what was actually done.
    Future sessions show what is prescribed next.
    The > marker shows your next session.
    """
    import json

    exercise = get_exercise(exercise_id)
    store = get_store(history_path, exercise_id)

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
            first_dt = datetime.strptime(user_state.history[0].date, "%Y-%m-%d")
            plan_start_date = (first_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            plan_start_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Auto-advance plan_start_date past last logged session so that plan sessions
    # the user missed (skipped days, gap in training) are dropped automatically.
    if user_state.history:
        last_logged = max(s.date for s in user_state.history)
        if last_logged > plan_start_date:
            plan_start_date = last_logged
            store.set_plan_start_date(plan_start_date)

    # Generate plan for enough weeks to cover history + ahead
    plan_start_dt = datetime.strptime(plan_start_date, "%Y-%m-%d")
    weeks_since_start = max(0, (datetime.now() - plan_start_dt).days // 7)
    if weeks is not None:
        weeks_ahead = weeks
        store.set_plan_weeks(weeks)
    else:
        weeks_ahead = store.get_plan_weeks() or 4
    total_weeks = weeks_since_start + weeks_ahead

    from ...core.config import MAX_PLAN_WEEKS
    total_weeks = max(2, min(total_weeks, MAX_PLAN_WEEKS * 3))

    try:
        plans = generate_plan(user_state, plan_start_date, total_weeks, baseline_max, exercise=exercise)
    except ValueError as e:
        views.print_error(str(e))
        raise typer.Exit(1)

    # Get training status
    training_status = get_training_status(
        user_state.history,
        user_state.current_bodyweight_kg,
        baseline_max,
    )

    # Build unified timeline
    timeline = views.build_timeline(plans, user_state.history)

    # Plan change detection
    old_cache = store.load_plan_cache()
    new_cache = [
        _session_snapshot(e)
        for e in timeline
        if e.status in ("next", "planned") and e.planned is not None
    ]
    plan_changes = _diff_plan(old_cache, new_cache) if old_cache is not None else []
    store.save_plan_cache(new_cache)

    if json_out:
        ff = training_status.fitness_fatigue_state
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
                "training_max": training_status.training_max,
                "latest_test_max": training_status.latest_test_max,
                "trend_slope_per_week": round(training_status.trend_slope, 4),
                "is_plateau": training_status.is_plateau,
                "deload_recommended": training_status.deload_recommended,
                "readiness_z_score": round(ff.readiness_z_score(), 4),
            },
            "sessions": sessions_json,
            "plan_changes": plan_changes,
        }, indent=2))
        return

    if plan_changes:
        views.console.print("[yellow]Plan updated:[/yellow]")
        for c in plan_changes[:5]:
            views.console.print(f"  {c}")
        views.console.print()

    goal = user_state.profile.target_max_reps
    if training_status.latest_test_max and training_status.latest_test_max >= goal:
        views.console.print(
            f"[green]Goal reached![/green] Your test max ({training_status.latest_test_max}) "
            f"meets your goal ({goal} reps). "
            "Update target via [i] Setup or --target-max."
        )

    views.print_unified_plan(timeline, training_status, target_max=goal)


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
    exercise_id: ExerciseOption = "pull_up",
) -> None:
    """Show exactly how a planned session's parameters were calculated."""
    from ...core.config import MAX_PLAN_WEEKS

    exercise = get_exercise(exercise_id)
    store = get_store(history_path, exercise_id)

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

    plan_start_dt = datetime.strptime(plan_start_date, "%Y-%m-%d")
    weeks_since_start = max(0, (datetime.now() - plan_start_dt).days // 7)
    weeks_ahead_val = weeks if weeks is not None else 4
    total_weeks = max(2, min(weeks_since_start + weeks_ahead_val, MAX_PLAN_WEEKS * 3))

    # Resolve "next" → first upcoming planned session date
    if date.lower() == "next":
        try:
            plans = generate_plan(user_state, plan_start_date, total_weeks, exercise=exercise)
        except ValueError as e:
            views.print_error(str(e))
            raise typer.Exit(1)
        today_str = datetime.now().strftime("%Y-%m-%d")
        nxt = next((p for p in plans if p.date >= today_str), None)
        if nxt is None:
            views.print_error("No upcoming sessions in plan.")
            raise typer.Exit(1)
        date = nxt.date

    result = explain_plan_entry(user_state, plan_start_date, date, total_weeks, exercise=exercise)
    views.console.print()
    views.console.print(result)
    views.console.print()


@app.command()
def skip(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to shift the plan forward"),
    ] = 1,
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
    exercise_id: ExerciseOption = "pull_up",
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """
    Mark a rest day and shift the plan forward by N days.

    Use this when you can't train on a scheduled day. All future sessions
    slide forward by the specified number of days.
    """
    from ...core.config import MAX_PLAN_WEEKS

    if days < 1:
        views.print_error("--days must be at least 1")
        raise typer.Exit(1)

    store = get_store(history_path, exercise_id)

    if not store.exists():
        views.print_error(f"History file not found: {store.history_path}")
        views.print_info("Run 'init' first to create profile and history.")
        raise typer.Exit(1)

    plan_start_date = store.get_plan_start_date()
    if plan_start_date is None:
        views.print_error("No plan start date found. Run 'init' first.")
        raise typer.Exit(1)

    # Compute new start date
    start_dt = datetime.strptime(plan_start_date, "%Y-%m-%d")
    new_start_dt = start_dt + timedelta(days=days)
    new_start = new_start_dt.strftime("%Y-%m-%d")
    day_word = "day" if days == 1 else "days"

    views.console.print()
    views.console.print(f"Current plan start : [bold]{plan_start_date}[/bold]")
    views.console.print(f"New plan start     : [bold]{new_start}[/bold]  (+{days} {day_word})")

    # Show the next session that will be shifted
    try:
        user_state = store.load_user_state()
        exercise = get_exercise(exercise_id)
        plan_start_dt = datetime.strptime(plan_start_date, "%Y-%m-%d")
        weeks_since_start = max(0, (datetime.now() - plan_start_dt).days // 7)
        total_weeks = max(2, min(weeks_since_start + 4, MAX_PLAN_WEEKS * 3))
        plans = generate_plan(user_state, plan_start_date, total_weeks, exercise=exercise)
        today_str = datetime.now().strftime("%Y-%m-%d")
        nxt = next((p for p in plans if p.date >= today_str), None)
        if nxt:
            views.console.print(
                f"\nNext session being shifted: [bold]{nxt.date}[/bold] — "
                f"{nxt.session_type} ({nxt.grip})"
            )
    except Exception:
        pass

    if not force:
        views.console.print()
        if not views.confirm_action(f"Shift plan forward by {days} {day_word}?"):
            views.print_info("Cancelled.")
            raise typer.Exit(0)

    store.set_plan_start_date(new_start)
    views.print_success(
        f"Plan shifted +{days} {day_word}. Run 'plan' to see the updated schedule."
    )
