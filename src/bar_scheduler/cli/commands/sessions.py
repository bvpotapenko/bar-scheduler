"""Session commands: log-session, show-history, delete-record, and helpers."""

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from ...core.adaptation import get_training_status
from ...core.exercises.registry import get_exercise
from ...core.metrics import session_max_reps, training_max_from_baseline
from ...core.models import SessionResult, SetResult
from ...io.serializers import ValidationError, parse_compact_sets, parse_sets_string
from .. import views
from ..app import OVERPERFORMANCE_REP_THRESHOLD, ExerciseOption, app, get_store


def _interactive_sets() -> str:
    """
    Prompt the user to enter sets one by one.

    Accepts compact plan format on the first entry (before any sets have been entered):
        5x4 +0.5kg / 240s   → expands to 4 sets of 5 reps, +0.5 kg, 240 s rest
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
        "  e.g. [green]5x4 +0.5kg / 240s[/green]  [green]6x5 / 120s[/green]"
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
    rir: Annotated[
        Optional[int],
        typer.Option("--rir", help="Reps in reserve on last set (0=failure, 5=easy)"),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON for machine processing"),
    ] = False,
    exercise_id: ExerciseOption = "pull_up",
) -> None:
    """
    Log a completed training session.

    Run without options for interactive step-by-step entry.
    Or supply all options for one-liner use:

      bar-scheduler log-session --date 2026-02-18 --bodyweight-kg 82 \\
        --grip pronated --session-type S --sets "8@0/180,6@0/120,6@0"
    """
    exercise = get_exercise(exercise_id)
    store = get_store(history_path, exercise_id)

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

    # Grip / variant — show exercise-specific options
    if grip is None:
        variants = exercise.variants
        hint = "  ".join(f"[{i+1}] {v}" for i, v in enumerate(variants))
        views.console.print(f"Variant: {hint}")
        grip_map: dict[str, str] = {}
        for i, v in enumerate(variants, 1):
            grip_map[str(i)] = v
            grip_map[v] = v
        while True:
            raw = views.console.input("Variant [1]: ").strip() or "1"
            grip = grip_map.get(raw.lower())
            if grip:
                break
            views.print_error(f"Choose 1–{len(variants)} or type the variant name")

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
    was_interactive = sets is None
    if sets is None:
        sets = _interactive_sets()

    # RIR (Reps In Reserve)
    rir_value: int | None = rir
    if rir is None and was_interactive:
        views.console.print()
        raw_rir = views.console.input(
            "[dim]Reps left in tank on last set? (0=failure…5=easy, Enter to skip): [/dim]"
        ).strip()
        if raw_rir:
            try:
                rir_value = max(0, min(10, int(raw_rir)))
            except ValueError:
                pass

    # Notes
    if notes is None and was_interactive:
        views.console.print()
        raw_notes = views.console.input("[dim]Notes (optional, Enter to skip): [/dim]").strip()
        notes = raw_notes if raw_notes else None

    # ── Validate all inputs ─────────────────────────────────────────────────

    if grip not in exercise.variants:
        views.print_error(f"Variant must be one of: {', '.join(exercise.variants)}")
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
            rir_reported=rir_value,
        )
        set_results.append(set_result)

    # Populate planned_sets from plan cache if a matching prescription exists.
    planned_sets: list[SetResult] = []
    cache_entry = store.lookup_plan_cache_entry(date, session_type)
    if cache_entry and cache_entry.get("sets", 0) > 0:
        n = cache_entry["sets"]
        tr = cache_entry.get("reps", 0)
        wt = cache_entry.get("weight", 0.0)
        rs = cache_entry.get("rest", 180)
        planned_sets = [
            SetResult(target_reps=tr, actual_reps=None,
                      rest_seconds_before=rs, added_weight_kg=wt, rir_target=2)
            for _ in range(n)
        ]

    session = SessionResult(
        date=date,
        bodyweight_kg=bodyweight_kg,
        grip=grip,  # type: ignore
        session_type=session_type,  # type: ignore
        exercise_id=exercise_id,
        planned_sets=planned_sets,
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
    exercise_id: ExerciseOption = "pull_up",
) -> None:
    """
    Display training history as a table.
    """
    from ...core.metrics import session_avg_rest, session_max_reps, session_total_reps

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
    exercise_id: ExerciseOption = "pull_up",
) -> None:
    """
    Remove a session by its ID.

    Use 'show-history' to see session IDs in the # column.
    """
    store = get_store(history_path, exercise_id)

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
