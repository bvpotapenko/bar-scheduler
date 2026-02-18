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
            "--weeks", "2",
        ])

        assert result.exit_code == 0
        assert "Training max" in result.output

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

        # Get initial plan (TM=9 from baseline 10)
        result1 = runner.invoke(app, [
            "plan",
            "--history-path", str(history_path),
        ])
        assert result1.exit_code == 0
        assert "Training max (TM): 9" in result1.output

        # Log a new TEST session with higher max
        runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", "2026-02-20",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "TEST",
            "--sets", "15@0/180",
        ])

        # Get updated plan - TM should now be 13 (floor(0.9 * 15))
        result2 = runner.invoke(app, [
            "plan",
            "--history-path", str(history_path),
        ])
        assert result2.exit_code == 0
        assert "Training max (TM): 13" in result2.output


class TestNewFeatures:
    """Tests for new fixes: parse, delete-record, bodyweight update, overperformance."""

    def test_parse_sets_omit_rest_defaults_180(self):
        """Omitting rest on any set (not just the last) defaults to 180 s."""
        from bar_scheduler.io.serializers import parse_sets_string

        result = parse_sets_string("8@0, 6@5")
        assert result[0][2] == 180  # first set rest
        assert result[1][2] == 180  # second set rest

        # Mixed: first has explicit rest, second omits
        result2 = parse_sets_string("8@0/120, 6@0")
        assert result2[0][2] == 120
        assert result2[1][2] == 180

    def test_delete_record_removes_session(self, temp_history_dir):
        """delete-record removes the correct session by ID."""
        history_path = temp_history_dir / "history.jsonl"

        # Init
        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        # Log a second session
        runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", "2026-02-20",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "S",
            "--sets", "5@0/180,5@0/180",
        ])

        # Confirm 2 sessions exist (TEST baseline + S session)
        from bar_scheduler.io.history_store import HistoryStore
        store = HistoryStore(history_path)
        sessions_before = store.load_history()
        assert len(sessions_before) >= 2

        # Delete record #1 (the baseline TEST)
        result = runner.invoke(app, [
            "delete-record",
            "1",
            "--history-path", str(history_path),
            "--force",
        ])
        assert result.exit_code == 0
        assert "Deleted" in result.output

        sessions_after = store.load_history()
        assert len(sessions_after) == len(sessions_before) - 1

    def test_log_updates_bodyweight(self, temp_history_dir):
        """Logging a session with a different bodyweight updates the profile."""
        import json
        history_path = temp_history_dir / "history.jsonl"
        profile_path = temp_history_dir / "profile.json"

        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
        ])

        runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", "2026-02-20",
            "--bodyweight-kg", "80.5",
            "--grip", "pronated",
            "--session-type", "S",
            "--sets", "5@0/180",
        ])

        profile = json.loads(profile_path.read_text())
        assert abs(profile["current_bodyweight_kg"] - 80.5) < 0.1

    def test_overperformance_bw_set_auto_logs_test(self, temp_history_dir):
        """Logging reps > current test max auto-logs a TEST session."""
        history_path = temp_history_dir / "history.jsonl"

        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        # Log 15 BW reps — beats test max of 10
        result = runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", "2026-02-20",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "S",
            "--sets", "15@0/180",
        ])

        assert result.exit_code == 0
        assert "New personal best" in result.output

        # History should now contain an auto-logged TEST session
        from bar_scheduler.io.history_store import HistoryStore
        sessions = HistoryStore(history_path).load_history()
        test_sessions = [s for s in sessions if s.session_type == "TEST"]
        # At least 2 TEST sessions: baseline + auto-logged
        assert len(test_sessions) >= 2
        latest_test = max(test_sessions, key=lambda s: s.date)
        assert any(s.actual_reps == 15 for s in latest_test.completed_sets)

    def test_overperformance_weighted_set_bw_equivalent(self, temp_history_dir):
        """Weighted sets exceeding test max via BW-equivalent trigger auto TEST."""
        history_path = temp_history_dir / "history.jsonl"

        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        # 10 reps @ +10kg → BW-equiv = round(10 * (1 + 10/82)) ≈ 11 > 10
        result = runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", "2026-02-20",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "S",
            "--sets", "10@+10/240",
        ])

        assert result.exit_code == 0
        assert "New personal best" in result.output

        from bar_scheduler.io.history_store import HistoryStore
        sessions = HistoryStore(history_path).load_history()
        test_sessions = [s for s in sessions if s.session_type == "TEST"]
        assert len(test_sessions) >= 2
