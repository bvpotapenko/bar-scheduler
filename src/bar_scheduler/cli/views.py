"""
CLI view formatters using Rich for pretty console output.

Handles table formatting and display of training data.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from rich.console import Console
from rich.table import Table

from ..core.adaptation import get_training_status
from ..core.ascii_plot import create_max_reps_plot, create_weekly_volume_chart
from ..core.equipment import bss_is_degraded, check_band_progression, compute_leff, get_assistance_kg, get_catalog, get_next_band_step
from ..core.exercises.registry import get_exercise
from ..core.max_estimator import estimate_max_reps_from_session
from ..core.metrics import session_avg_rest, session_max_reps, session_total_reps
from ..core.models import EquipmentState, ExerciseTarget, SessionPlan, SessionResult, TrainingStatus, UserState

TimelineStatus = Literal["done", "missed", "next", "planned", "extra", "rested"]


@dataclass
class TimelineEntry:
    """A single row in the unified plan/history timeline."""

    date: str
    week_number: int
    planned: SessionPlan | None  # None for unplanned (extra) sessions
    actual: SessionResult | None  # None for future sessions
    status: TimelineStatus
    actual_id: int | None = None  # 1-based ID in sorted history (for delete-record)
    track_b: dict | None = None  # Track B max estimate (fi_est, nuzzo_est, …)


console = Console()


def build_timeline(
    plans: list[SessionPlan],
    history: list[SessionResult],
) -> list[TimelineEntry]:
    """
    Merge plan + history into a unified chronological timeline.

    Matching: a history session is matched to a plan entry if dates are
    within 1 day of each other and session types agree, or if dates match
    exactly regardless of type.

    Args:
        plans: Generated plan entries (may include past dates)
        history: Logged sessions

    Returns:
        Sorted list of TimelineEntry
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # Stable week-number anchor: Monday of the week containing the first real session.
    # Anchoring to Monday means Mon-Sun calendar weeks stay together (e.g. sessions
    # on Mon 03.02 and Wed 03.04 both appear as "week 3", not split across weeks).
    real_history = [s for s in history if s.session_type != "REST"]
    first_date: datetime | None = (
        datetime.strptime(min(s.date for s in real_history), "%Y-%m-%d")
        if real_history else None
    )
    first_monday: datetime | None = (
        first_date - timedelta(days=first_date.weekday()) if first_date is not None else None
    )

    # Build lookup: date -> list of (original_index, session) pairs
    history_by_date: dict[str, list[tuple[int, SessionResult]]] = {}
    for i, s in enumerate(history):
        history_by_date.setdefault(s.date, []).append((i, s))

    # Track which history sessions have been matched (by original index)
    matched_indices: set[int] = set()

    entries: list[TimelineEntry] = []

    for plan in plans:
        # Try to find a matching history session (same date, prefer same type)
        matched: SessionResult | None = None
        matched_idx: int | None = None

        candidates = history_by_date.get(plan.date, [])
        # Prefer same session type
        for orig_i, s in candidates:
            if s.session_type == plan.session_type and orig_i not in matched_indices:
                matched = s
                matched_idx = orig_i
                break
        # Fall back to any session on that date
        if matched is None:
            for orig_i, s in candidates:
                if orig_i not in matched_indices:
                    matched = s
                    matched_idx = orig_i
                    break

        if matched_idx is not None:
            matched_indices.add(matched_idx)

        # Determine status — "next" is assigned by the second pass below
        if matched is not None:
            status: TimelineStatus = "rested" if matched.session_type == "REST" else "done"
        elif plan.date < today:
            status = "missed"
        else:
            status = "planned"

        # Compute Track B estimate for past non-TEST sessions with ≥2 sets
        track_b: dict | None = None
        if matched is not None and matched.session_type in ("S", "H"):
            valid_sets = [s for s in matched.completed_sets if s.actual_reps is not None and s.actual_reps > 0]
            if len(valid_sets) >= 2:
                track_b = estimate_max_reps_from_session(
                    [s.actual_reps for s in valid_sets],       # type: ignore[misc]
                    [s.rest_seconds_before for s in valid_sets],
                    [s.rir_reported for s in valid_sets],
                )

        entries.append(
            TimelineEntry(
                date=plan.date,
                week_number=plan.week_number,
                planned=plan,
                actual=matched,
                status=status,
                actual_id=matched_idx + 1 if matched_idx is not None else None,
                track_b=track_b,
            )
        )

    # Find first non-done future entry and mark as "next"
    set_next = False
    for e in entries:
        if e.status in ("planned", "missed") and e.date >= today:
            e.status = "next" if not set_next else "planned"
            set_next = True
            break
    if not set_next:
        # All past or today is next
        for e in entries:
            if e.status == "planned":
                e.status = "next"
                break

    # Add any extra (unplanned) history sessions not matched to a plan
    for orig_i, s in enumerate(history):
        if orig_i not in matched_indices:
            session_dt = datetime.strptime(s.date, "%Y-%m-%d")
            wn = (session_dt - first_monday).days // 7 + 1 if first_monday else 0
            entries.append(
                TimelineEntry(
                    date=s.date,
                    week_number=wn,
                    planned=None,
                    actual=s,
                    status="done",
                    actual_id=orig_i + 1,
                )
            )

    entries.sort(key=lambda e: e.date)
    return entries


def _fmt_prescribed_sets(sets: list, session_type: str) -> str:
    """
    Format a list of sets (PlannedSet or SetResult) as a compact string.

    Works with any object that has .target_reps, .added_weight_kg,
    .rest_seconds_before attributes.
    """
    if not sets:
        return "(no sets)"
    if session_type == "TEST":
        return "1x max reps"

    from collections import Counter

    reps_list = [s.target_reps for s in sets]
    weight = sets[0].added_weight_kg
    rest = sets[0].rest_seconds_before

    if all(r == reps_list[0] for r in reps_list):
        base = f"{reps_list[0]}x{len(reps_list)}"
    else:
        counts = Counter(reps_list)
        parts_out = []
        for rep_val in sorted(counts.keys(), reverse=True):
            n = counts[rep_val]
            parts_out.append(f"{rep_val}×{n}" if n > 1 else str(rep_val))
        base = ", ".join(parts_out)

    weight_str = f" +{weight:.1f}kg" if weight > 0 else ""
    return f"{base}{weight_str} / {rest}s"


def _fmt_prescribed(plan: SessionPlan) -> str:
    """Format a planned session as a compact single-line string."""
    text = _fmt_prescribed_sets(plan.sets, plan.session_type)
    if plan.exercise_id == "bss":
        text += " (per leg)"
    return text


def _fmt_actual(session: SessionResult) -> str:
    """Format a completed session as a short string including rest times."""
    sets = [s for s in session.completed_sets if s.actual_reps is not None]
    if not sets:
        return "—"
    if session.session_type == "TEST":
        max_r = max(s.actual_reps for s in sets)
        return f"{max_r} reps (max)"

    total = sum(s.actual_reps for s in sets)
    reps_str = "+".join(str(s.actual_reps) for s in sets)

    weights = [s.added_weight_kg for s in sets]
    weight_str = f" +{weights[0]:.1f}kg" if weights[0] > 0 else ""

    # Inter-set rests (rest_seconds_before for sets 2+; include set 1 too)
    rests = [s.rest_seconds_before for s in sets]
    if all(r == rests[0] for r in rests):
        rest_str = f"{rests[0]}s"
    else:
        rest_str = ",".join(str(r) for r in rests) + "s"

    rirs = [s.rir_reported for s in sets if s.rir_reported is not None]
    rir_str = f" RIR≈{round(sum(rirs)/len(rirs))}" if rirs else ""

    return f"{reps_str} = {total}{weight_str} / {rest_str}{rir_str}"


_GRIP_ABBR: dict[str, str] = {
    # pull-up variants
    "pronated": "Pro", "neutral": "Neu", "supinated": "Sup",
    # dip variants
    "standard": "Std", "chest_lean": "CL ", "tricep_upright": "TUp",
    # bss variants
    "deficit": "Def", "front_foot_elevated": "FFE",
}
_TYPE_DISPLAY: dict[str, str] = {
    "TEST": "TST", "S": "Str", "H": "Hpy", "E": "End", "T": "Tec", "REST": "Rest",
}


def _fmt_date_cell(date_str: str, status: TimelineStatus) -> str:
    """Format status icon + date as a single compact cell: '> 02.18(Tue)'."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    date_part = dt.strftime("%m.%d(%a)")
    icon = {"done": "✓", "missed": "—", "next": ">", "planned": " ", "extra": "·", "rested": "~"}[
        status
    ]
    return f"{icon} {date_part}"


def _print_equipment_header(exercise, equipment_state: EquipmentState, bodyweight_kg: float | None, exercise_id: str) -> None:
    """Print the equipment info line (and optional BSS-degraded warning)."""
    catalog = get_catalog(exercise_id)
    item_label = catalog.get(equipment_state.active_item, {}).get("label", equipment_state.active_item)
    a_kg = get_assistance_kg(
        equipment_state.active_item, exercise_id, equipment_state.machine_assistance_kg
    )
    if bodyweight_kg and bodyweight_kg > 0:
        leff = compute_leff(exercise.bw_fraction, bodyweight_kg, 0.0, a_kg)
        console.print(
            f"[dim]Equipment: {item_label}  (Leff ≈ {leff:.0f} kg @ {bodyweight_kg:.0f} kg BW)[/dim]"
        )
    else:
        console.print(f"[dim]Equipment: {item_label}[/dim]")
    if exercise_id == "bss" and bss_is_degraded(equipment_state):
        console.print(
            "[yellow]⚠ Split Squat mode — add an elevation surface to unlock BSS.[/yellow]"
        )


def _emax_cell(
    entry: "TimelineEntry",
    floor_max: int,
    last_tm: int | None,
) -> tuple[str, int | None]:
    """
    Compute the eMax cell value for a timeline entry.

    Returns (cell_str, updated_last_tm) — last_tm is used to suppress
    identical consecutive TM projections in the future portion of the plan.
    """
    if entry.actual is not None:
        if entry.actual.session_type == "TEST":
            test_max = max(
                (s.actual_reps for s in entry.actual.completed_sets if s.actual_reps is not None),
                default=None,
            )
            return (str(test_max) if test_max is not None else "", last_tm)
        elif entry.track_b is not None:
            fi_v = entry.track_b["fi_est"]
            nz_v = entry.track_b["nuzzo_est"]
            return (f"{fi_v}/{nz_v}", last_tm)
        else:
            return ("", last_tm)
    else:
        # Future planned session — project from TM
        tm_val = entry.planned.expected_tm if entry.planned else None
        if tm_val is not None:
            emax_val = max(round(tm_val / 0.90), floor_max)
            cell = str(emax_val) if emax_val != last_tm else ""
            return (cell, emax_val)
        return ("", last_tm)


def _grip_legend_str(entries: "list[TimelineEntry]", show_grip: bool) -> str:
    """Return the grip abbreviation legend string (empty string when no grip column)."""
    if not show_grip:
        return ""
    grips_seen: set[str] = set()
    for e in entries:
        if e.actual:
            grips_seen.add(e.actual.grip)
        elif e.planned:
            grips_seen.add(e.planned.grip)

    _GRIP_FULL: dict[str, str] = {
        "pronated": "Pronated", "neutral": "Neutral", "supinated": "Supinated",
        "standard": "Standard", "chest_lean": "Chest-lean", "tricep_upright": "Tricep-upright",
        "deficit": "Deficit", "front_foot_elevated": "Front-foot-elevated",
    }
    grip_parts = [
        f"{_GRIP_ABBR[g].strip()}={_GRIP_FULL[g]}"
        for g in ("pronated", "neutral", "supinated", "standard",
                  "chest_lean", "tricep_upright", "deficit", "front_foot_elevated")
        if g in grips_seen and g in _GRIP_ABBR
    ]
    return ("  |  Grip: " + "  ".join(grip_parts)) if grip_parts else ""


def _print_band_progression(exercise_id: str, history: list[SessionResult], equipment_state: EquipmentState) -> None:
    """Print a band-progression suggestion if the user is ready to step up."""
    if equipment_state.active_item not in ("BAND_HEAVY", "BAND_MEDIUM", "BAND_LIGHT"):
        return
    try:
        ex = get_exercise(exercise_id)
        if check_band_progression(history, exercise_id, ex.session_params):
            next_band = get_next_band_step(equipment_state.active_item)
            if next_band is not None:
                catalog = get_catalog(exercise_id)
                current_label = catalog.get(equipment_state.active_item, {}).get("label", equipment_state.active_item)
                next_label = catalog.get(next_band, {}).get("label", next_band)
                console.print()
                console.print(
                    f"[yellow]Ready to progress: you've consistently hit the rep ceiling. "
                    f"Consider stepping from {current_label} → {next_label}.[/yellow]"
                )
    except Exception:
        pass


def print_unified_plan(
    entries: list[TimelineEntry],
    status: TrainingStatus,
    title: str = "Training Log",
    exercise_target: ExerciseTarget | None = None,
    equipment_state: EquipmentState | None = None,
    history: list[SessionResult] | None = None,
    exercise_id: str = "pull_up",
    bodyweight_kg: float | None = None,
) -> None:
    """
    Print the full unified timeline: status + single table.

    Args:
        entries: Merged timeline entries
        status: Current training status for header
        title: Table title
        exercise_target: User's goal for this exercise (shown in status block)
        equipment_state: Current equipment state (for header line)
        history: Full session history (for band progression check)
        exercise_id: Exercise being displayed
        bodyweight_kg: Current bodyweight (for Leff calculation in header)
    """
    exercise = get_exercise(exercise_id)
    show_grip = exercise.has_variant_rotation

    # Header
    console.print()
    console.print(format_status_display(status, exercise_target=exercise_target))
    console.print()

    # Equipment header line
    if equipment_state is not None:
        _print_equipment_header(exercise, equipment_state, bodyweight_kg, exercise_id)

    if not entries:
        console.print("[yellow]No sessions yet. Run 'init' to get started.[/yellow]")
        return

    table = Table(title=title, show_lines=False)

    table.add_column("#", justify="right", style="dim", width=3)   # history ID
    table.add_column("Wk", justify="right", style="dim", width=3)
    table.add_column("Date", style="cyan", width=14, no_wrap=True)  # ✓ MM.DD(Ddd)
    table.add_column("Type", style="magenta", width=5)              # Str/Hpy/End/Tec/TST
    if show_grip:
        table.add_column("Grip", width=5)                           # Pro/Neu/Sup/…
    table.add_column("Prescribed", width=22)
    table.add_column("Actual", width=24)
    table.add_column(
        "eMax", justify="right", style="bold green", width=6
    )  # past TEST=actual  past train=fi/nz  future=plan projection

    last_wk: int | None = None
    last_tm: int | None = None

    for entry in entries:
        date_cell = _fmt_date_cell(entry.date, entry.status)

        # Wk: only show when week number changes
        wk_val = entry.week_number if entry.week_number > 0 else None
        wk_str = str(wk_val) if wk_val is not None and wk_val != last_wk else ""
        if wk_val is not None:
            last_wk = wk_val

        # eMax column — (a) past TEST → actual max  (b) past train → fi/nz  (c) future → projection
        floor_max = status.latest_test_max or 0
        tm_str, last_tm = _emax_cell(entry, floor_max, last_tm)

        id_str = str(entry.actual_id) if entry.actual_id is not None else ""

        # Type and grip: prefer actual if available; abbreviate
        if entry.actual:
            raw_type = entry.actual.session_type
            raw_grip = entry.actual.grip
        elif entry.planned:
            raw_type = entry.planned.session_type
            raw_grip = entry.planned.grip
        else:
            raw_type = ""
            raw_grip = ""

        type_str = _TYPE_DISPLAY.get(raw_type, raw_type[:3] if raw_type else "")
        grip_str = _GRIP_ABBR.get(raw_grip, raw_grip[:3].capitalize() if raw_grip else "")

        # REST rows: show the type label but no prescription/actual/eMax content
        is_rest_row = entry.actual is not None and entry.actual.session_type == "REST"

        # For completed sessions: show the historically stored planned_sets
        # (frozen at log time) so past prescriptions are immutable across
        # plan regenerations.  Fall back to the regenerated plan only when
        # no stored prescription is available (e.g. sessions logged without
        # a prior plan).
        if is_rest_row:
            prescribed_str = ""
            actual_str = ""
            tm_str = ""
        elif entry.actual and entry.actual.planned_sets:
            prescribed_str = _fmt_prescribed_sets(
                entry.actual.planned_sets, entry.actual.session_type
            )
        elif entry.planned and entry.actual is None:
            prescribed_str = _fmt_prescribed(entry.planned)
        else:
            prescribed_str = ""
        if not is_rest_row:
            actual_str = _fmt_actual(entry.actual) if entry.actual else ""

        # Style for the row
        if entry.status == "next":
            row_style = "bold"
        elif entry.status in ("done", "rested"):
            row_style = "dim"
        elif entry.status == "missed":
            row_style = "dim red"
        else:
            row_style = None

        row_cells = [id_str, wk_str, date_cell, type_str]
        if show_grip:
            row_cells.append(grip_str)
        row_cells.extend([prescribed_str, actual_str, tm_str])
        table.add_row(*row_cells, style=row_style)

    console.print(table)

    grip_legend = _grip_legend_str(entries, show_grip)
    console.print(
        "[dim]Type: Str=Strength  Hpy=Hypertrophy  End=Endurance  Tec=Technique  TST=Max-test"
        + grip_legend + "[/dim]"
    )
    console.print(
        "[dim]Prescribed: 5x4 = 5 reps × 4 sets  |  4, 3×8 / 60s = 1 set of 4 + 8 sets of 3  |  "
        "/ Ns = N seconds rest before the set  |  "
        "eMax: past TEST = actual max  |  past session = FI-est/Nuzzo-est  |  future = plan projection[/dim]"
    )

    # Band progression suggestion
    if equipment_state is not None and history is not None:
        _print_band_progression(exercise_id, history, equipment_state)


def format_session_table(sessions: list[SessionResult]) -> Table:
    """
    Create a Rich table displaying session history.

    Args:
        sessions: List of sessions to display

    Returns:
        Rich Table object
    """
    table = Table(title="Training History")

    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Date", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Grip", style="green")
    table.add_column("BW(kg)", justify="right")
    table.add_column("Max(BW)", justify="right", style="bold")
    table.add_column("Total reps", justify="right")
    table.add_column("Avg rest(s)", justify="right")

    for i, session in enumerate(sessions, 1):
        max_reps = session_max_reps(session)
        total = session_total_reps(session)
        avg_rest = session_avg_rest(session)

        table.add_row(
            str(i),
            session.date,
            session.session_type,
            session.grip,
            f"{session.bodyweight_kg:.1f}",
            str(max_reps) if max_reps > 0 else "-",
            str(total),
            f"{avg_rest:.0f}" if avg_rest > 0 else "-",
        )

    return table


def format_status_display(
    status: TrainingStatus,
    exercise_target: ExerciseTarget | None = None,
) -> str:
    """
    Format training status as text block.

    Args:
        status: TrainingStatus to display
        exercise_target: User's personal goal for this exercise

    Returns:
        Formatted string
    """
    lines = ["Current status"]

    if status.latest_test_max is not None:
        lines.append(f"- Cur.Max: {status.latest_test_max} reps  (last test result)")
        lines.append(
            f"- Tr.Max:  {status.training_max} reps"
            "  (= 90% × Cur.Max, used for prescriptions)"
        )
    else:
        lines.append(f"- Tr.Max:  {status.training_max} reps")

    if exercise_target is not None:
        lines.append(f"- My Goal: {exercise_target}")

    lines.extend(
        [
            f"- Trend (reps/week): {status.trend_slope:+.2f}",
            f"- Plateau: {'yes' if status.is_plateau else 'no'}",
            f"- Deload recommended: {'yes' if status.deload_recommended else 'no'}",
        ]
    )

    ff = status.fitness_fatigue_state
    z = ff.readiness_z_score()
    lines.append(f"- Readiness z-score: {z:+.2f}")

    return "\n".join(lines)


def print_history(sessions: list[SessionResult]) -> None:
    """
    Print session history to console.

    Args:
        sessions: Sessions to display
    """
    if not sessions:
        console.print("[yellow]No sessions recorded yet.[/yellow]")
        return

    table = format_session_table(sessions)
    console.print(table)


def print_recent_history(sessions: list[SessionResult]) -> None:
    """
    Print recent training history in compact form.

    Args:
        sessions: Recent sessions to display
    """
    if not sessions:
        return

    console.print()
    console.print("[bold]Recent History[/bold]")

    table = Table(show_header=True, header_style="dim")
    table.add_column("Date", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Grip")
    table.add_column("Sets", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Max", justify="right", style="bold")

    for session in sessions:
        max_reps = session_max_reps(session)
        total = session_total_reps(session)
        sets_count = len(session.completed_sets)

        table.add_row(
            session.date,
            session.session_type,
            session.grip,
            str(sets_count),
            str(total),
            str(max_reps) if max_reps > 0 else "-",
        )

    console.print(table)
    console.print()


def print_max_plot(
    sessions: list[SessionResult],
    trajectory_z: list[tuple[datetime, float]] | None = None,
    trajectory_g: list[tuple[datetime, float]] | None = None,
    trajectory_m: list[tuple[datetime, float]] | None = None,
    bw_load_kg: float = 0.0,
    target_weight_kg: float = 0.0,
    exercise_name: str = "Pull-Up",
    target: int = 30,
    traj_types: frozenset[str] = frozenset(),
) -> None:
    """
    Print ASCII plot of max reps progress.

    Args:
        sessions: Sessions to plot
        trajectory_z: BW reps trajectory (· dots)
        trajectory_g: Goal-weight reps trajectory (× dots)
        trajectory_m: 1RM added kg trajectory (○ dots, independent right axis)
        bw_load_kg: BW × bw_fraction; used with trajectory_m for right axis
        target_weight_kg: Goal added weight (for legend label)
        exercise_name: Display name shown in the chart title
        target: Target rep count for y-axis scaling
        traj_types: Set of requested trajectory flags (z/g/m); used for legend labels
    """
    plot = create_max_reps_plot(
        sessions,
        trajectory_z=trajectory_z,
        trajectory_g=trajectory_g,
        trajectory_m=trajectory_m,
        bw_load_kg=bw_load_kg,
        target_weight_kg=target_weight_kg,
        exercise_name=exercise_name,
        target=target,
        traj_types=traj_types,
    )
    console.print(plot)


def print_volume_chart(sessions: list[SessionResult], weeks: int = 4) -> None:
    """
    Print weekly volume chart.

    Args:
        sessions: Sessions to chart
        weeks: Number of weeks to show
    """
    chart = create_weekly_volume_chart(sessions, weeks)
    console.print(chart)


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]{message}[/green]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[red]Error: {message}[/red]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]Warning: {message}[/yellow]")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[blue]{message}[/blue]")


def confirm_action(message: str) -> bool:
    """
    Prompt user for confirmation.

    Args:
        message: Confirmation message

    Returns:
        True if confirmed, False otherwise
    """
    response = console.input(f"{message} [y/N]: ")
    return response.lower() in ("y", "yes")
