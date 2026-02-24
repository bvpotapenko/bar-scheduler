"""
CLI entry point — thin assembler.

Imports all command modules (which registers their commands on `app`),
then attaches the interactive main-menu callback.
"""

import typer

from . import views
from .app import app
from .commands import analysis, planning, profile, sessions  # noqa: F401 — side-effect: registers commands


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """
    Pull-up training planner. Run without a command for interactive mode.
    """
    if ctx.invoked_subcommand is not None:
        return  # A sub-command was given — let it handle things

    # ── Interactive main menu ────────────────────────────────────────────────
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
        "r": ("1rm",           "Estimate 1-rep max"),
        "s": ("skip",             "Rest day — shift plan forward"),
        "u": ("update-equipment", "Update training equipment"),
        "i": ("init",             "Setup / edit profile"),
        "d": ("delete-record",    "Delete a session by ID"),
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

    if chosen == "plan":
        ctx.invoke(planning.plan)
    elif chosen == "log-session":
        ctx.invoke(sessions.log_session)
    elif chosen == "show-history":
        ctx.invoke(sessions.show_history)
    elif chosen == "plot-max":
        ctx.invoke(analysis.plot_max)
    elif chosen == "status":
        ctx.invoke(analysis.status)
    elif chosen == "update-weight":
        profile._menu_update_weight()
    elif chosen == "volume":
        ctx.invoke(analysis.volume)
    elif chosen == "explain":
        planning._menu_explain()
    elif chosen == "1rm":
        ctx.invoke(analysis.onerepmax)
    elif chosen == "skip":
        ctx.invoke(planning.skip)
    elif chosen == "update-equipment":
        ctx.invoke(profile.update_equipment_cmd)
    elif chosen == "init":
        profile._menu_init()
    elif chosen == "delete-record":
        sessions._menu_delete_record()


if __name__ == "__main__":
    app()
