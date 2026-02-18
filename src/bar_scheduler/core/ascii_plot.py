"""
ASCII plotting for max reps progress visualization.

Creates terminal-friendly plots showing training progress over time.
"""

from datetime import datetime

from .metrics import get_test_sessions, session_max_reps
from .models import SessionResult


def create_max_reps_plot(
    history: list[SessionResult],
    width: int = 60,
    height: int = 20,
    target: int = 30,
    trajectory: list[tuple[datetime, float]] | None = None,
) -> str:
    """
    Create an ASCII plot of max reps progress over time.

    Args:
        history: Training history
        width: Plot width in characters
        height: Plot height in lines
        target: Target max reps (for y-axis scaling)

    Returns:
        ASCII art string
    """
    test_sessions = get_test_sessions(history)

    if not test_sessions:
        return "No test sessions recorded yet. Log a TEST session to see progress."

    # Extract data points
    points: list[tuple[datetime, int]] = []
    for session in test_sessions:
        date = datetime.strptime(session.date, "%Y-%m-%d")
        max_reps = session_max_reps(session)
        if max_reps > 0:
            points.append((date, max_reps))

    if not points:
        return "No valid test results found."

    # Sort by date
    points.sort(key=lambda x: x[0])

    # Calculate ranges
    min_date = points[0][0]
    max_date = points[-1][0]

    # Extend x-axis to cover trajectory if provided (trajectory goes into the future)
    if trajectory:
        traj_end = trajectory[-1][0]
        if traj_end > max_date:
            max_date = traj_end

    date_range = (max_date - min_date).days
    if date_range == 0:
        date_range = 1

    min_reps = min(p[1] for p in points)
    max_reps_val = max(p[1] for p in points)

    # Extend y-axis to include target
    y_min = max(0, min_reps - 2)
    y_max = max(max_reps_val + 2, target)
    y_range = y_max - y_min
    if y_range == 0:
        y_range = 1

    # Create the plot grid
    plot_width = width - 6  # Leave room for y-axis labels
    plot_height = height - 3  # Leave room for x-axis and title

    # Initialize grid with spaces
    grid = [[" " for _ in range(plot_width)] for _ in range(plot_height)]

    # Convert points to grid coordinates
    plot_points: list[tuple[int, int, int]] = []  # (x, y, reps)
    for date, reps in points:
        days_from_start = (date - min_date).days
        x = int((days_from_start / date_range) * (plot_width - 1)) if date_range > 0 else 0
        y = int(((reps - y_min) / y_range) * (plot_height - 1))
        y = plot_height - 1 - y  # Flip y-axis
        plot_points.append((x, y, reps))

    # Draw trajectory (planned growth line) as · dots — done before actual points
    if trajectory:
        for traj_date, traj_val in trajectory:
            days_from_start = (traj_date - min_date).days
            if days_from_start < 0:
                continue
            x = int((days_from_start / date_range) * (plot_width - 1)) if date_range > 0 else 0
            y_raw = (traj_val - y_min) / y_range
            y = int(plot_height - 1 - y_raw * (plot_height - 1))
            if 0 <= x < plot_width and 0 <= y < plot_height:
                if grid[y][x] == " ":
                    grid[y][x] = "·"

    # Draw connecting lines
    for i in range(len(plot_points) - 1):
        x1, y1, _ = plot_points[i]
        x2, y2, _ = plot_points[i + 1]

        # Simple line drawing
        dx = x2 - x1
        dy = y2 - y1
        steps = max(abs(dx), abs(dy), 1)

        for step in range(steps + 1):
            t = step / steps if steps > 0 else 0
            x = int(x1 + t * dx)
            y = int(y1 + t * dy)

            if 0 <= x < plot_width and 0 <= y < plot_height:
                # Choose character based on direction
                if abs(dy) > abs(dx):
                    char = "│"
                elif dy < 0:
                    char = "╭" if step == 0 else "╯"
                elif dy > 0:
                    char = "╰" if step == 0 else "╮"
                else:
                    char = "─"

                if grid[y][x] == " ":
                    grid[y][x] = char

    # Draw data points
    for x, y, reps in plot_points:
        if 0 <= x < plot_width and 0 <= y < plot_height:
            grid[y][x] = "●"

    # Build output
    lines = []

    # Title
    lines.append("Max Reps Progress (Strict Pull-ups)")
    lines.append("─" * width)

    # Y-axis labels and plot
    for i, row in enumerate(grid):
        # Calculate y value for this row
        y_val = y_max - int((i / (plot_height - 1)) * y_range) if plot_height > 1 else y_max

        # Y-axis label
        label = f"{y_val:3d} ┤"

        # Find if any point is on this row and add label
        row_str = "".join(row)

        # Add reps labels next to points
        for x, py, reps in plot_points:
            if py == i and 0 <= x < plot_width:
                # Add label after the point
                label_pos = x + 2
                label_text = f"({reps})"
                if label_pos + len(label_text) < plot_width:
                    row_list = list(row_str)
                    for j, c in enumerate(label_text):
                        if label_pos + j < len(row_list):
                            row_list[label_pos + j] = c
                    row_str = "".join(row_list)

        lines.append(label + row_str)

    # X-axis
    lines.append("─" * width)

    # X-axis labels (dates) — span the full date range including trajectory
    x_labels = "    "
    mid_date = min_date + (max_date - min_date) / 2
    dates_to_show = [
        (0, min_date),
        (plot_width // 2, mid_date),
        (plot_width - 10, max_date),
    ]
    label_line = [" "] * plot_width
    for x_pos, date in dates_to_show:
        date_str = date.strftime("%b %d")
        for i, c in enumerate(date_str):
            if 0 <= x_pos + i < plot_width:
                label_line[x_pos + i] = c
    x_labels += "".join(label_line)

    lines.append(x_labels)

    if trajectory:
        lines.append("● actual max reps   · projected trajectory")

    return "\n".join(lines)


def create_simple_bar_chart(
    labels: list[str],
    values: list[float],
    width: int = 40,
    title: str = "",
) -> str:
    """
    Create a simple horizontal bar chart.

    Args:
        labels: Labels for each bar
        values: Values for each bar
        width: Maximum bar width
        title: Chart title

    Returns:
        ASCII bar chart string
    """
    if not values:
        return "No data to display."

    max_val = max(values) if values else 1
    max_label_len = max(len(l) for l in labels) if labels else 0

    lines = []

    if title:
        lines.append(title)
        lines.append("─" * (max_label_len + width + 5))

    for label, value in zip(labels, values):
        bar_len = int((value / max_val) * width) if max_val > 0 else 0
        bar = "█" * bar_len
        lines.append(f"{label:>{max_label_len}} │{bar} {value:.1f}")

    return "\n".join(lines)


def create_weekly_volume_chart(history: list[SessionResult], weeks: int = 4) -> str:
    """
    Create a chart showing weekly training volume.

    Args:
        history: Training history
        weeks: Number of weeks to show

    Returns:
        ASCII chart string
    """
    from datetime import timedelta

    if not history:
        return "No training history."

    # Group sessions by week
    latest_date = datetime.strptime(history[-1].date, "%Y-%m-%d")

    weekly_volume: dict[int, int] = {}

    for session in history:
        session_date = datetime.strptime(session.date, "%Y-%m-%d")
        weeks_ago = (latest_date - session_date).days // 7

        if weeks_ago < weeks:
            total_reps = sum(
                s.actual_reps for s in session.completed_sets if s.actual_reps is not None
            )
            weekly_volume[weeks_ago] = weekly_volume.get(weeks_ago, 0) + total_reps

    # Create labels and values
    labels = []
    values = []

    for i in range(weeks - 1, -1, -1):
        if i == 0:
            labels.append("This week")
        elif i == 1:
            labels.append("Last week")
        else:
            labels.append(f"{i} weeks ago")

        values.append(float(weekly_volume.get(i, 0)))

    return create_simple_bar_chart(labels, values, title="Weekly Volume (Total Reps)")
