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


def _resolve_plan_start(store, user_state, default_offset_days: int = 1) -> str:
    """Return plan_start_date from store, or fall back to first history date + offset."""
    plan_start_date = store.get_plan_start_date()
    if plan_start_date is None:
        if user_state.history:
            first_dt = datetime.strptime(user_state.history[0].date, "%Y-%m-%d")
            plan_start_date = (first_dt + timedelta(days=default_offset_days)).strftime("%Y-%m-%d")
        else:
            plan_start_date = (datetime.now() + timedelta(days=default_offset_days)).strftime("%Y-%m-%d")
    return plan_start_date


def _total_weeks(plan_start_date: str, weeks_ahead: int = 4) -> int:
    """Return total plan horizon in weeks, clamped to [2, MAX_PLAN_WEEKS*3]."""
    from ...core.config import MAX_PLAN_WEEKS
    plan_start_dt = datetime.strptime(plan_start_date, "%Y-%m-%d")
    weeks_since_start = max(0, (datetime.now() - plan_start_dt).days // 7)
    return max(2, min(weeks_since_start + weeks_ahead, MAX_PLAN_WEEKS * 3))


def _prompt_baseline(store, bodyweight_kg: float, exercise=None) -> int | None:
    """
    Prompt user to enter their baseline max reps when no history exists.

    Uses exercise-specific language if ``exercise`` (an ExerciseDefinition)
    is provided; defaults to pull-up language otherwise.

    Logs a TEST session and returns the rep count, or None if cancelled.
    """
    from ...core.exercises.pull_up import PULL_UP

    if exercise is None:
        exercise = PULL_UP

    ex_name = exercise.display_name  # e.g. "Pull-Up", "Parallel Bar Dip"

    views.console.print()
    views.print_warning(f"No {ex_name} training history yet.")
    views.console.print(
        f"\nTo generate a plan we need your current {ex_name} max.\n"
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
            raw = views.console.input(
                f"Your current max {ex_name} reps (strict, full ROM): "
            ).strip()
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
        grip=exercise.primary_variant,
        session_type="TEST",
        exercise_id=exercise.exercise_id,
        planned_sets=[test_set],
        completed_sets=[test_set],
        notes=f"Baseline max test ({ex_name}, entered during plan setup)",
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
    store = get_store(None)
    try:
        user_state = store.load_user_state()
    except Exception as e:
        views.print_error(str(e))
        return

    plan_start_date = _resolve_plan_start(store, user_state)
    total_weeks = _total_weeks(plan_start_date)

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
        baseline_max = _prompt_baseline(store, user_state.current_bodyweight_kg, exercise)
        if baseline_max is None:
            raise typer.Exit(0)
        # Reload state now that the baseline TEST session has been logged
        user_state = store.load_user_state()

    # Determine where the plan started (set by init; fall back to first history date)
    plan_start_date = _resolve_plan_start(store, user_state)

    # Auto-advance plan_start_date past last logged session so that plan sessions
    # the user missed (skipped days, gap in training) are dropped automatically.
    if user_state.history:
        last_logged = max(s.date for s in user_state.history)
        if last_logged > plan_start_date:
            plan_start_date = last_logged
            store.set_plan_start_date(plan_start_date)

    # Generate plan for enough weeks to cover history + ahead
    if weeks is not None:
        weeks_ahead = weeks
        store.set_plan_weeks(weeks)
    else:
        weeks_ahead = store.get_plan_weeks() or 4
    total_weeks = _total_weeks(plan_start_date, weeks_ahead)

    try:
        plans = generate_plan(user_state, plan_start_date, total_weeks, baseline_max, exercise=exercise)
    except ValueError as e:
        views.print_error(str(e))
        raise typer.Exit(1)

    # Get training status (REST records don't count as training sessions)
    training_history = [s for s in user_state.history if s.session_type != "REST"]
    training_status = get_training_status(
        training_history,
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

    # Volume cap warnings — informational only, plan is still executed as-is
    from ...core.config import MAX_DAILY_REPS, MAX_DAILY_SETS
    today_str = datetime.now().strftime("%Y-%m-%d")
    overloaded = [
        p for p in plans
        if p.date >= today_str and p.sets and (
            p.total_reps > MAX_DAILY_REPS or len(p.sets) > MAX_DAILY_SETS
        )
    ]
    if overloaded:
        days_per_week = user_state.profile.preferred_days_per_week
        views.console.print(
            f"[yellow]⚠  {len(overloaded)} upcoming session(s) exceed the science-backed"
            f" per-session ceiling (>{MAX_DAILY_REPS} reps or >{MAX_DAILY_SETS} sets)."
            " These sessions are still scheduled — the limit is informational.[/yellow]"
        )
        if days_per_week < 6:
            views.console.print(
                f"[dim]Tip: increasing training days from {days_per_week} → {days_per_week + 1}"
                " per week would spread the load. Update via [i] Setup or 'init'.[/dim]"
            )
        else:
            views.console.print(
                "[dim]Tip: the weekly volume goal is high — consider reducing total weekly reps.[/dim]"
            )
        views.console.print()

    exercise_target = user_state.profile.target_for_exercise(exercise_id)
    goal_reached = False
    if training_status.latest_test_max is not None and training_status.latest_test_max >= exercise_target.reps:
        if exercise_target.weight_kg == 0.0:
            goal_reached = True
        else:
            # Weight-gated goal: check if the latest TEST session used at least target weight
            test_sessions = [s for s in user_state.history if s.session_type == "TEST"]
            if test_sessions:
                last_test = max(test_sessions, key=lambda s: s.date)
                best_weight = max(
                    (st.added_weight_kg for st in last_test.completed_sets),
                    default=0.0,
                )
                goal_reached = best_weight >= exercise_target.weight_kg
    if goal_reached:
        views.console.print(
            f"[green]Goal reached![/green] Your test max meets your goal ({exercise_target}). "
            "Update target via [i] Setup or --target-max."
        )

    # Load equipment state for display
    equipment_state = None
    try:
        equipment_state = store.load_current_equipment(exercise_id)
    except Exception:
        pass

    views.print_unified_plan(
        timeline,
        training_status,
        exercise_target=exercise_target,
        equipment_state=equipment_state,
        history=user_state.history,
        exercise_id=exercise_id,
        bodyweight_kg=user_state.current_bodyweight_kg,
    )


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

    plan_start_date = _resolve_plan_start(store, user_state)
    weeks_ahead_val = weeks if weeks is not None else 4
    total_weeks = _total_weeks(plan_start_date, weeks_ahead_val)

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
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
    exercise_id: ExerciseOption = "pull_up",
) -> None:
    """
    Add or remove rest days to shift the training plan forward or backward.

    Adding N rest days pushes future sessions forward by N days.
    Using a negative number removes rest days, undoing a previous shift.
    """
    store = get_store(history_path, exercise_id)

    if not store.exists():
        views.print_error(f"History file not found: {store.history_path}")
        views.print_info("Run 'init' first to create profile and history.")
        raise typer.Exit(1)

    plan_start_date = store.get_plan_start_date()
    if plan_start_date is None:
        views.print_error("No plan start date found. Run 'init' first.")
        raise typer.Exit(1)

    user_state = store.load_user_state()
    exercise = get_exercise(exercise_id)

    # Build the current plan to find missed sessions for the default from-date
    total_weeks = _total_weeks(plan_start_date)
    try:
        plans = generate_plan(user_state, plan_start_date, total_weeks, exercise=exercise)
    except ValueError:
        plans = []

    today_str = datetime.now().strftime("%Y-%m-%d")
    timeline = views.build_timeline(plans, user_state.history)
    missed = [e for e in timeline if e.status == "missed" and e.date < today_str]
    missed.sort(key=lambda e: e.date, reverse=True)
    default_from = missed[0].date if missed else today_str

    # Prompt for from-date
    views.console.print()
    from_input = views.console.input(f"Shift from [{default_from}]: ").strip()
    from_date = from_input if from_input else default_from
    try:
        datetime.strptime(from_date, "%Y-%m-%d")
    except ValueError:
        views.print_error(f"Invalid date: {from_date!r}. Expected YYYY-MM-DD.")
        raise typer.Exit(1)

    # Prompt for shift days (positive = forward, negative = backward)
    days_input = views.console.input("Shift by N days [0]: ").strip()
    try:
        shift_days = int(days_input) if days_input else 0
    except ValueError:
        views.print_error(f"Invalid number: {days_input!r}. Enter an integer.")
        raise typer.Exit(1)

    if shift_days == 0:
        views.print_info("No change applied.")
        raise typer.Exit(0)

    if shift_days > 0:
        # Add N consecutive REST records starting from from_date
        bw = user_state.current_bodyweight_kg
        from_dt = datetime.strptime(from_date, "%Y-%m-%d")
        for i in range(shift_days):
            rest_date = (from_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            rest_session = SessionResult(
                date=rest_date,
                bodyweight_kg=bw,
                grip=exercise.primary_variant,
                session_type="REST",
                exercise_id=exercise_id,
                planned_sets=[],
                completed_sets=[],
            )
            store.append_session(rest_session)
        sign = "+"
    else:
        # Remove up to |shift_days| REST records at or before from_date (newest first)
        all_history = store.load_history()
        rest_candidates = [
            (i, s) for i, s in enumerate(all_history)
            if s.session_type == "REST" and s.date <= from_date
        ]
        rest_candidates.sort(key=lambda x: x[1].date, reverse=True)
        to_delete = rest_candidates[:abs(shift_days)]
        # Delete from highest index to lowest to keep earlier indices stable
        for idx, _ in sorted(to_delete, key=lambda x: x[0], reverse=True):
            store.delete_session_at(idx)
        # Roll back plan_start_date to the last non-REST date
        updated_history = store.load_history()
        non_rest = [s for s in updated_history if s.session_type != "REST"]
        if non_rest:
            new_start = max(s.date for s in non_rest)
            store.set_plan_start_date(new_start)
        sign = ""

    day_word = "day" if abs(shift_days) == 1 else "days"
    views.print_success(
        f"Plan shifted {sign}{shift_days} {day_word} from {from_date}. "
        "Run 'plan' to see the updated schedule."
    )
