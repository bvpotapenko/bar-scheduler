"""
CLI view formatters using Rich for pretty console output.

Handles table formatting and display of training data.
"""

from rich.console import Console
from rich.table import Table

from ..core.adaptation import get_training_status
from ..core.ascii_plot import create_max_reps_plot, create_weekly_volume_chart
from ..core.metrics import session_avg_rest, session_max_reps, session_total_reps
from ..core.models import SessionPlan, SessionResult, TrainingStatus, UserState


console = Console()


def format_session_table(sessions: list[SessionResult]) -> Table:
    """
    Create a Rich table displaying session history.

    Args:
        sessions: List of sessions to display

    Returns:
        Rich Table object
    """
    table = Table(title="Training History")

    table.add_column("Date", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Grip", style="green")
    table.add_column("BW(kg)", justify="right")
    table.add_column("Max(BW)", justify="right", style="bold")
    table.add_column("Total reps", justify="right")
    table.add_column("Avg rest(s)", justify="right")

    for session in sessions:
        max_reps = session_max_reps(session)
        total = session_total_reps(session)
        avg_rest = session_avg_rest(session)

        table.add_row(
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


def format_status_display(status: TrainingStatus) -> str:
    """
    Format training status as text block.

    Args:
        status: TrainingStatus to display

    Returns:
        Formatted string
    """
    lines = [
        "Current status",
        f"- Training max (TM): {status.training_max}",
    ]

    if status.latest_test_max is not None:
        lines.append(f"- Latest test max: {status.latest_test_max}")

    lines.extend([
        f"- Trend (reps/week): {status.trend_slope:+.2f}",
        f"- Plateau: {'yes' if status.is_plateau else 'no'}",
        f"- Deload recommended: {'yes' if status.deload_recommended else 'no'}",
    ])

    # Add readiness info
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


def print_max_plot(sessions: list[SessionResult]) -> None:
    """
    Print ASCII plot of max reps progress.

    Args:
        sessions: Sessions to plot
    """
    plot = create_max_reps_plot(sessions)
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
