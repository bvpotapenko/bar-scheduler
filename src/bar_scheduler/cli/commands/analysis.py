"""Analysis commands: status, volume, plot-max, 1rm."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from ...core.adaptation import get_training_status
from ...core.exercises.registry import get_exercise
from ...core.metrics import estimate_1rm, training_max_from_baseline
from ...io.serializers import ValidationError
from .. import views
from ..app import ExerciseOption, app, get_store


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
    exercise_id: ExerciseOption = "pull_up",
) -> None:
    """
    Show current training status.
    """
    store = get_store(history_path, exercise_id)

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
    exercise_id: ExerciseOption = "pull_up",
) -> None:
    """
    Show weekly volume chart.
    """
    store = get_store(history_path, exercise_id)

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
    show_trajectory: Annotated[
        bool,
        typer.Option("--trajectory", "-t", help="Overlay projected goal trajectory line"),
    ] = False,
    exercise_id: ExerciseOption = "pull_up",
) -> None:
    """
    Display ASCII plot of max reps progress.

    Use --trajectory to overlay a dotted line showing the planned growth
    from your first test to the target (30 reps).
    """
    from ...core.config import TARGET_MAX_REPS, TM_FACTOR, expected_reps_per_week
    from ...core.metrics import get_test_sessions, session_max_reps as _max_reps

    store = get_store(history_path, exercise_id)

    if not store.exists():
        views.print_error(f"History file not found: {store.history_path}")
        views.print_info("Run 'init' first to create profile and history.")
        raise typer.Exit(1)

    try:
        sessions = store.load_history()
    except (FileNotFoundError, ValidationError) as e:
        views.print_error(str(e))
        raise typer.Exit(1)

    # Compute trajectory if requested
    traj_points: list[tuple[datetime, float]] | None = None
    traj_json: list[dict] | None = None
    if show_trajectory:
        # Use the user's per-exercise target reps if available; fall back to config constant.
        traj_target = TARGET_MAX_REPS
        try:
            profile = store.load_profile()
            traj_target = profile.target_for_exercise(exercise_id).reps
        except Exception:
            pass

        test_sessions = get_test_sessions(sessions)
        if test_sessions:
            first_test = test_sessions[0]
            start_dt = datetime.strptime(first_test.date, "%Y-%m-%d")
            initial_tm = training_max_from_baseline(_max_reps(first_test))
            traj_points = []
            d, tm_f = start_dt, float(initial_tm)
            while tm_f < traj_target and d <= start_dt + timedelta(weeks=104):
                traj_points.append((d, tm_f / TM_FACTOR))
                tm_f = min(tm_f + expected_reps_per_week(int(tm_f), traj_target), float(traj_target))
                d += timedelta(weeks=1)
            traj_points.append((d, float(traj_target)))
            traj_json = [
                {"date": pt.strftime("%Y-%m-%d"), "projected_max": round(val, 2)}
                for pt, val in traj_points
            ]

    if json_out:
        data_points = [
            {"date": s.date, "max_reps": _max_reps(s)}
            for s in get_test_sessions(sessions)
            if _max_reps(s) > 0
        ]
        print(json.dumps({"data_points": data_points, "trajectory": traj_json}, indent=2))
        return

    views.print_max_plot(sessions, trajectory=traj_points)


@app.command("1rm")
def onerepmax(
    history_path: Annotated[
        Optional[Path],
        typer.Option("--history-path", "-p", help="Path to history JSONL file"),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON for machine processing"),
    ] = False,
    exercise_id: ExerciseOption = "pull_up",
) -> None:
    """
    Estimate 1-rep max using the Epley formula.

    Scans recent sessions for the best loaded set and computes:
      1RM = total_load × (1 + reps / 30)   [Epley]

    For pull-ups: total_load = bodyweight + added_weight.
    For BSS:      total_load = added_weight (external only).
    """
    exercise = get_exercise(exercise_id)
    store = get_store(history_path, exercise_id)

    if not store.exists():
        views.print_error(f"History file not found: {store.history_path}")
        views.print_info("Run 'init' first to create profile and history.")
        raise typer.Exit(1)

    try:
        user_state = store.load_user_state()
    except (FileNotFoundError, ValidationError) as e:
        views.print_error(str(e))
        raise typer.Exit(1)

    result = estimate_1rm(exercise, user_state.current_bodyweight_kg, user_state.history)

    if result is None:
        views.print_error("Not enough data to estimate 1RM. Log some sessions first.")
        raise typer.Exit(1)

    if json_out:
        print(json.dumps(result, indent=2))
        return

    bw = user_state.current_bodyweight_kg
    added = result["best_added_weight_kg"]
    bw_frac = result["bw_fraction"]
    if exercise.onerm_includes_bodyweight:
        load_details = f"{bw:.1f} kg BW × {bw_frac} + {added:.1f} kg added"
    else:
        load_details = f"{added:.1f} kg external load"

    views.console.print()
    views.console.print(f"[bold cyan]1RM Estimate — {exercise.display_name}[/bold cyan]")
    views.console.print(f"  Method:        Epley (1RM = load × (1 + reps/30))")
    views.console.print(f"  Bodyweight:    {bw:.1f} kg")
    views.console.print(f"  Best set:      {result['best_reps']} reps @ +{added:.1f} kg added  ({result['best_date']})")
    views.console.print(f"  Total load:    {result['effective_load_kg']:.1f} kg  ({load_details})")
    views.console.print(f"  [bold green]1RM ≈ {result['1rm_kg']:.1f} kg[/bold green]")
    views.console.print(f"  {exercise.onerm_explanation}")
    views.console.print()


# ---------------------------------------------------------------------------
# Adaptation timeline help text (task.md §7)
# ---------------------------------------------------------------------------

_ADAPTATION_GUIDE = """\
HOW THE PLANNER LEARNS FROM YOUR DATA

This planner is adaptive. Here is what it knows at each stage:

┌─────────────────┬──────────────────────────────────────────────────────┐
│ Stage           │ What the model can do                                │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Day 1           │ Generic safe plan from your baseline max.            │
│ (no history)    │ Conservative volume. No weighted work until TM > 9.  │
│                 │ RECOMMENDATION: Just follow the plan and log.        │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Weeks 1–2       │ EWMA max estimate starts tracking.                   │
│ (3–8 sessions)  │ Rest normalization active (short rest gets credit).  │
│                 │ NO autoregulation yet (not enough data).             │
│                 │ RECOMMENDATION: Log rest times accurately.           │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Weeks 3–4       │ AUTOREGULATION ACTIVATES (≥10 sessions).             │
│ (10–16 sessions)│ Plateau detection possible.                          │
│                 │ Rest adaptation kicks in (RIR + drop-off based).     │
│                 │ RECOMMENDATION: Do your first re-test (TEST session).│
├─────────────────┼──────────────────────────────────────────────────────┤
│ Weeks 6–8       │ Individual fatigue profile fitted.                   │
│ (24–32 sessions)│ Set-to-set predictions improve.                      │
│                 │ Deload triggers become reliable.                     │
│                 │ RECOMMENDATION: Trust the deload if recommended.     │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Weeks 12+       │ Full training profile established.                   │
│ (48+ sessions)  │ Long-term fitness adaptation curve accurate.         │
│                 │ Progression rate calibrated to your response.        │
│                 │ RECOMMENDATION: Model is at peak accuracy.           │
└─────────────────┴──────────────────────────────────────────────────────┘

TIPS FOR BEST RESULTS:
• Log every session, including bad ones (RIR=0, incomplete sets = valuable data)
• Log rest times, even approximate
• Do a TEST session every 3–4 weeks (anchors the max estimate)
• Update bodyweight when it changes by ≥1 kg
• Past prescriptions are frozen — only future sessions adapt
• Different exercises have separate plans and separate adaptation timelines
"""


@app.command("help-adaptation")
def help_adaptation() -> None:
    """
    Explain how the planner adapts over time.

    Shows the adaptation timeline: what the model can predict at each
    stage (day 1, weeks 1–2, weeks 3–4, weeks 6–8, weeks 12+) and
    tips for getting the best results.

    See also: docs/adaptation_guide.md
    """
    views.console.print()
    views.console.print(_ADAPTATION_GUIDE)
