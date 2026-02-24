"""
CLI view formatters using Rich for pretty console output.

Handles table formatting and display of training data.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from rich.console import Console
from rich.table import Table

from ..core.adaptation import get_training_status
from ..core.ascii_plot import create_max_reps_plot, create_weekly_volume_chart
from ..core.max_estimator import estimate_max_reps_from_session
from ..core.metrics import session_avg_rest, session_max_reps, session_total_reps
from ..core.models import SessionPlan, SessionResult, TrainingStatus, UserState

TimelineStatus = Literal["done", "missed", "next", "planned", "extra"]


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

    # Build lookup: date -> history session(s), and id-map for 1-based IDs
    history_by_date: dict[str, list[SessionResult]] = {}
    for s in history:
        history_by_date.setdefault(s.date, []).append(s)

    history_id_map: dict[int, int] = {id(s): i + 1 for i, s in enumerate(history)}

    # Track which history sessions have been matched
    matched_history: set[int] = set()

    entries: list[TimelineEntry] = []

    for plan in plans:
        # Try to find a matching history session (same date, prefer same type)
        matched: SessionResult | None = None
        match_idx: int | None = None

        candidates = history_by_date.get(plan.date, [])
        # Prefer same session type
        for i, s in enumerate(candidates):
            if s.session_type == plan.session_type and id(s) not in matched_history:
                matched = s
                match_idx = id(s)
                break
        # Fall back to any session on that date
        if matched is None:
            for s in candidates:
                if id(s) not in matched_history:
                    matched = s
                    match_idx = id(s)
                    break

        if match_idx is not None:
            matched_history.add(match_idx)

        # Determine status — "next" is assigned by the second pass below
        if matched is not None:
            status: TimelineStatus = "done"
        elif plan.date < today:
            status = "missed"
        else:
            status = "planned"

        # Compute Track B estimate for past non-TEST sessions with ≥2 sets
        track_b: dict | None = None
        if matched is not None and matched.session_type != "TEST":
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
                actual_id=(
                    history_id_map.get(id(matched)) if matched is not None else None
                ),
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
    plan_dates = {p.date for p in plans}
    for s in history:
        if id(s) not in matched_history:
            # Only add if not already in plan dates
            status_extra: TimelineStatus = "done"
            entries.append(
                TimelineEntry(
                    date=s.date,
                    week_number=0,
                    planned=None,
                    actual=s,
                    status=status_extra,
                    actual_id=history_id_map.get(id(s)),
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
    "TEST": "TST", "S": "Str", "H": "Hpy", "E": "End", "T": "Tec",
}


def _fmt_date_cell(date_str: str, status: TimelineStatus) -> str:
    """Format status icon + date as a single compact cell: '> 02.18(Tue)'."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    date_part = dt.strftime("%m.%d(%a)")
    icon = {"done": "✓", "missed": "—", "next": ">", "planned": " ", "extra": "·"}[
        status
    ]
    return f"{icon} {date_part}"


def print_unified_plan(
    entries: list[TimelineEntry],
    status: TrainingStatus,
    title: str = "Training Log",
    target_max: int | None = None,
) -> None:
    """
    Print the full unified timeline: status + single table.

    Args:
        entries: Merged timeline entries
        status: Current training status for header
        title: Table title
        target_max: User's goal reps (shown in status block)
    """
    # Header
    console.print()
    console.print(format_status_display(status, target_max=target_max))
    console.print()

    if not entries:
        console.print("[yellow]No sessions yet. Run 'init' to get started.[/yellow]")
        return

    table = Table(title=title, show_lines=False)

    table.add_column("#", justify="right", style="dim", width=3)   # history ID
    table.add_column("Wk", justify="right", style="dim", width=3)
    table.add_column("Date", style="cyan", width=14, no_wrap=True)  # ✓ MM.DD(Ddd)
    table.add_column("Type", style="magenta", width=5)              # Str/Hpy/End/Tec/TST
    table.add_column("Grip", width=5)                               # Pro/Neu/Sup/…
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

        # eMax column — three cases:
        #  (a) past TEST session  → actual max reps
        #  (b) past non-TEST      → "fi/nz" Track-B estimates (if available)
        #  (c) future session     → projected TM ÷ 0.90, floored at latest_test_max
        floor_max = status.latest_test_max or 0
        if entry.actual is not None:
            if entry.actual.session_type == "TEST":
                test_max = max(
                    (s.actual_reps for s in entry.actual.completed_sets
                     if s.actual_reps is not None),
                    default=None,
                )
                tm_str = str(test_max) if test_max is not None else ""
            elif entry.track_b is not None:
                fi_v = entry.track_b["fi_est"]
                nz_v = entry.track_b["nuzzo_est"]
                tm_str = f"{fi_v}/{nz_v}"
            else:
                tm_str = ""
        else:
            # Future planned session
            tm_val = entry.planned.expected_tm if entry.planned else None
            if tm_val is not None:
                emax_val = max(round(tm_val / 0.90), floor_max)
                tm_str = str(emax_val) if emax_val != last_tm else ""
                if emax_val is not None:
                    last_tm = emax_val
            else:
                tm_str = ""

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

        # For completed sessions: show the historically stored planned_sets
        # (frozen at log time) so past prescriptions are immutable across
        # plan regenerations.  Fall back to the regenerated plan only when
        # no stored prescription is available (e.g. sessions logged without
        # a prior plan).
        if entry.actual and entry.actual.planned_sets:
            prescribed_str = _fmt_prescribed_sets(
                entry.actual.planned_sets, entry.actual.session_type
            )
        elif entry.planned:
            prescribed_str = _fmt_prescribed(entry.planned)
        else:
            prescribed_str = ""
        actual_str = _fmt_actual(entry.actual) if entry.actual else ""

        # Style for the row
        if entry.status == "next":
            row_style = "bold"
        elif entry.status == "done":
            row_style = "dim"
        elif entry.status == "missed":
            row_style = "dim red"
        else:
            row_style = None

        table.add_row(
            id_str,
            wk_str,
            date_cell,
            type_str,
            grip_str,
            prescribed_str,
            actual_str,
            tm_str,
            style=row_style,
        )

    console.print(table)

    # Build a grip legend containing only the variants that appear in this plan
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
    grip_legend = ("  |  Grip: " + "  ".join(grip_parts)) if grip_parts else ""

    console.print(
        "[dim]Type: Str=Strength  Hpy=Hypertrophy  End=Endurance  Tec=Technique  TST=Max-test"
        + grip_legend + "[/dim]"
    )
    console.print(
        "[dim]Prescribed: 5x4 = 5 reps × 4 sets  |  4, 3×8 / 60s = 1 set of 4 + 8 sets of 3  |  "
        "/ Ns = N seconds rest before the set  |  "
        "eMax: past TEST = actual max  |  past session = FI-est/Nuzzo-est  |  future = plan projection[/dim]"
    )


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


def format_plan_table(plans: list[SessionPlan], weeks: int | None = None) -> Table:
    """
    Create a Rich table displaying upcoming session plans.

    Args:
        plans: List of session plans
        weeks: Number of weeks to show (None = all)

    Returns:
        Rich Table object
    """
    title = "Upcoming Plan"
    if weeks:
        title += f" ({weeks} weeks)"

    table = Table(title=title)

    table.add_column("Wk", justify="right", style="dim")
    table.add_column("Date", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Grip", style="green")
    table.add_column("Sets (reps@kg x sets)", style="bold")
    table.add_column("Rest", justify="right")
    table.add_column("Total", justify="right", style="yellow")
    table.add_column("TM", justify="right", style="bold green")

    for plan in plans:
        if not plan.sets:
            sets_str = "(no sets)"
            rest_str = "-"
            total_str = "0"
        else:
            # Format sets
            reps_list = [s.target_reps for s in plan.sets]
            weight = plan.sets[0].added_weight_kg
            rest = plan.sets[0].rest_seconds_before

            # Check if all reps are the same
            if all(r == reps_list[0] for r in reps_list):
                sets_str = f"{len(reps_list)}x({reps_list[0]}@+{weight:.1f})"
            else:
                reps_str = ",".join(str(r) for r in reps_list)
                sets_str = f"({reps_str})@+{weight:.1f}"

            rest_str = str(rest)
            total_str = str(plan.total_reps)

        table.add_row(
            str(plan.week_number),
            plan.date,
            plan.session_type,
            plan.grip,
            sets_str,
            rest_str,
            total_str,
            str(plan.expected_tm),
        )

    return table


def format_status_display(
    status: TrainingStatus,
    target_max: int | None = None,
) -> str:
    """
    Format training status as text block.

    Args:
        status: TrainingStatus to display
        target_max: User's goal (target_max_reps from profile)

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

    if target_max is not None:
        lines.append(f"- My Goal: {target_max} reps")

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


def print_plan(
    plans: list[SessionPlan],
    status: TrainingStatus,
    weeks: int | None = None,
) -> None:
    """
    Print training plan and status to console.

    Args:
        plans: Session plans to display
        status: Current training status
        weeks: Number of weeks being shown
    """
    # Print status
    console.print()
    console.print(format_status_display(status))
    console.print()

    # Print plan table
    if not plans:
        console.print("[yellow]No sessions planned.[/yellow]")
        return

    table = format_plan_table(plans, weeks)
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


def print_plan_with_context(
    plans: list[SessionPlan],
    status: TrainingStatus,
    weeks: int | None,
    history: list[SessionResult],
) -> None:
    """
    Print training plan with context about current position.

    Args:
        plans: Session plans to display
        status: Current training status
        weeks: Number of weeks being shown
        history: Training history for context
    """
    from datetime import datetime

    # Print status
    console.print()
    console.print(format_status_display(status))

    # Show current position
    if history:
        last = history[-1]
        console.print()
        console.print(f"[bold]Last session:[/bold] {last.date} ({last.session_type})")

        # Calculate days since last session
        last_dt = datetime.strptime(last.date, "%Y-%m-%d")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        days_since = (today - last_dt).days
        if days_since == 0:
            console.print("[green]Trained today[/green]")
        elif days_since == 1:
            console.print("[green]Trained yesterday[/green]")
        elif days_since < 0:
            # Future date (data entry for future sessions)
            console.print(f"[dim]Session logged for {-days_since} days ahead[/dim]")
        elif days_since <= 3:
            console.print(f"[green]{days_since} days since last session[/green]")
        else:
            console.print(f"[yellow]{days_since} days since last session[/yellow]")

    console.print()

    # Print plan table
    if not plans:
        console.print("[yellow]No sessions planned.[/yellow]")
        return

    # Find next session (first plan date >= today)
    today_str = datetime.now().strftime("%Y-%m-%d")
    next_session_idx = None
    for i, plan in enumerate(plans):
        if plan.date >= today_str:
            next_session_idx = i
            break

    table = format_plan_table_with_marker(plans, weeks, next_session_idx)
    console.print(table)


def format_plan_table_with_marker(
    plans: list[SessionPlan],
    weeks: int | None = None,
    next_idx: int | None = None,
) -> Table:
    """
    Create a Rich table with a marker showing the next session.

    Args:
        plans: List of session plans
        weeks: Number of weeks to show (None = all)
        next_idx: Index of next session to highlight

    Returns:
        Rich Table object
    """
    title = "Upcoming Plan"
    if weeks:
        title += f" ({weeks} weeks)"

    table = Table(title=title)

    table.add_column("", width=2)  # Marker column
    table.add_column("Wk", justify="right", style="dim")
    table.add_column("Date", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Grip", style="green")
    table.add_column("Sets (reps@kg x sets)", style="bold")
    table.add_column("Rest", justify="right")
    table.add_column("Total", justify="right", style="yellow")
    table.add_column("TM", justify="right", style="bold green")

    for i, plan in enumerate(plans):
        if not plan.sets:
            sets_str = "(no sets)"
            rest_str = "-"
            total_str = "0"
        else:
            # Format sets
            reps_list = [s.target_reps for s in plan.sets]
            weight = plan.sets[0].added_weight_kg
            rest = plan.sets[0].rest_seconds_before

            # Check if all reps are the same
            if all(r == reps_list[0] for r in reps_list):
                sets_str = f"{len(reps_list)}x({reps_list[0]}@+{weight:.1f})"
            else:
                reps_str = ",".join(str(r) for r in reps_list)
                sets_str = f"({reps_str})@+{weight:.1f}"

            rest_str = str(rest)
            total_str = str(plan.total_reps)

        # Marker for next session
        marker = "[bold cyan]>[/bold cyan]" if i == next_idx else ""

        # Highlight row style for next session
        row_style = "bold" if i == next_idx else None

        table.add_row(
            marker,
            str(plan.week_number),
            plan.date,
            plan.session_type,
            plan.grip,
            sets_str,
            rest_str,
            total_str,
            str(plan.expected_tm),
            style=row_style,
        )

    return table


def print_max_plot(
    sessions: list[SessionResult],
    trajectory: list[tuple[datetime, float]] | None = None,
) -> None:
    """
    Print ASCII plot of max reps progress.

    Args:
        sessions: Sessions to plot
        trajectory: Optional list of (date, projected_max) points for overlay
    """
    plot = create_max_reps_plot(sessions, trajectory=trajectory)
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
