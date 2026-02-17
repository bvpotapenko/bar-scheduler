"""
Minimal smoke tests for bar-scheduler CLI.

Tests basic functionality:
- App runs without errors
- History file creates
- Sessions can be logged
- Plan is generated
- Plot is shown
"""

import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bar_scheduler.cli.main import app


runner = CliRunner()


@pytest.fixture
def temp_history_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestCLISmoke:
    """Basic smoke tests for CLI commands."""

    def test_app_help(self):
        """Test that app runs and shows help."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "bar-scheduler" in result.output or "pull-up" in result.output.lower()

    def test_init_creates_history(self, temp_history_dir):
        """Test init creates history and profile files."""
        history_path = temp_history_dir / "history.jsonl"

        result = runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--height-cm", "180",
            "--sex", "male",
            "--days-per-week", "3",
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        assert result.exit_code == 0
        assert history_path.exists()
        assert (temp_history_dir / "profile.json").exists()

    def test_log_session_adds_to_history(self, temp_history_dir):
        """Test log-session adds entry to history."""
        history_path = temp_history_dir / "history.jsonl"

        # First init
        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        # Log a session
        result = runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", "2026-02-16",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "S",
            "--sets", "5@0/180,5@0/180,4@0/180",
        ])

        assert result.exit_code == 0
        assert "Logged" in result.output

        # Check history has content
        content = history_path.read_text()
        assert "2026-02-16" in content

    def test_plan_generates_sessions(self, temp_history_dir):
        """Test plan generates upcoming sessions."""
        history_path = temp_history_dir / "history.jsonl"

        # Init with baseline
        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        # Generate plan
        result = runner.invoke(app, [
            "plan",
            "--history-path", str(history_path),
            "--start-date", "2026-02-18",
            "--weeks", "2",
        ])

        assert result.exit_code == 0
        assert "Training max" in result.output
        assert "2026-02" in result.output  # Should show dates

    def test_show_history_displays_sessions(self, temp_history_dir):
        """Test show-history displays logged sessions."""
        history_path = temp_history_dir / "history.jsonl"

        # Init and log
        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        # Show history
        result = runner.invoke(app, [
            "show-history",
            "--history-path", str(history_path),
        ])

        assert result.exit_code == 0
        # Should show the baseline TEST session
        assert "TEST" in result.output

    def test_plot_max_runs(self, temp_history_dir):
        """Test plot-max runs and shows output."""
        history_path = temp_history_dir / "history.jsonl"

        # Init with baseline
        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        # Plot
        result = runner.invoke(app, [
            "plot-max",
            "--history-path", str(history_path),
        ])

        assert result.exit_code == 0
        # Should show plot or message about data
        assert len(result.output) > 0

    def test_update_weight_changes_profile(self, temp_history_dir):
        """Test update-weight modifies profile."""
        history_path = temp_history_dir / "history.jsonl"
        profile_path = temp_history_dir / "profile.json"

        # Init
        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
        ])

        # Update weight
        result = runner.invoke(app, [
            "update-weight",
            "--history-path", str(history_path),
            "--bodyweight-kg", "80.5",
        ])

        assert result.exit_code == 0
        assert "80.5" in result.output

        # Verify profile changed
        profile_content = profile_path.read_text()
        assert "80.5" in profile_content

    def test_plan_updates_after_new_log(self, temp_history_dir):
        """Test that plan changes after logging new sessions."""
        history_path = temp_history_dir / "history.jsonl"

        # Init with baseline 10
        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        # Get initial plan
        result1 = runner.invoke(app, [
            "plan",
            "--history-path", str(history_path),
            "--start-date", "2026-03-01",
        ])

        initial_tm = None
        for line in result1.output.split("\n"):
            if "Training max" in line:
                initial_tm = line
                break

        # Log a new TEST session with higher max
        runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", "2026-02-20",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "TEST",
            "--sets", "12@0/180",
        ])

        # Get updated plan
        result2 = runner.invoke(app, [
            "plan",
            "--history-path", str(history_path),
            "--start-date", "2026-03-01",
        ])

        updated_tm = None
        for line in result2.output.split("\n"):
            if "Training max" in line:
                updated_tm = line
                break

        # Training max should have changed
        assert initial_tm != updated_tm
