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

    table.add_column("Date", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Grip", style="green")
    table.add_column("Sets (reps@kg x sets)", style="bold")
    table.add_column("Rest(s)", justify="right")

    for plan in plans:
        if not plan.sets:
            sets_str = "(no sets)"
            rest_str = "-"
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

        table.add_row(
            plan.date,
            plan.session_type,
            plan.grip,
            sets_str,
            rest_str,
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
