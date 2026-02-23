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
from datetime import datetime, timedelta
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
        # format_status_display now uses "Cur.Max" / "Tr.Max" labels
        assert "Cur.Max" in result.output or "Tr.Max" in result.output

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

        # Get initial plan — status block uses "Cur.Max: N" for latest test result.
        result1 = runner.invoke(app, [
            "plan",
            "--history-path", str(history_path),
        ])
        assert result1.exit_code == 0
        assert "Cur.Max: 10" in result1.output

        # Log a new TEST session with higher max (use tomorrow to ensure it's after init baseline)
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", tomorrow,
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "TEST",
            "--sets", "15@0/180",
        ])

        # Get updated plan — status block shows new Cur.Max = 15
        result2 = runner.invoke(app, [
            "plan",
            "--history-path", str(history_path),
        ])
        assert result2.exit_code == 0
        assert "Cur.Max: 15" in result2.output


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

        # Log 15 BW reps — beats test max of 10 (use tomorrow so it's after init baseline)
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        result = runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", tomorrow,
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

    def test_plan_starts_from_training_max(self, temp_history_dir):
        """Plan must start from training_max = floor(0.9 * test_max), not raw test_max.

        After a TEST with 12 reps, training_max = floor(0.9*12) = 10.
        The first planned session's expected_tm should be 10, and the plan
        grows from there rather than immediately prescribing the user's max.
        """
        import json
        history_path = temp_history_dir / "history.jsonl"

        # Init with a modest baseline
        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        # Log a TEST session showing test_max=12 — date must be AFTER today
        # so it is more recent than the baseline TEST logged by init.
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", tomorrow,
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "TEST",
            "--sets", "12@0/180",
        ])

        result = runner.invoke(app, [
            "plan", "--json",
            "--history-path", str(history_path),
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)

        # Plan must start from training_max = floor(0.9 * 12) = 10.
        future = [s for s in data["sessions"] if s["status"] in ("next", "planned")]
        assert len(future) > 0, "Plan should have future sessions"
        assert future[0]["expected_tm"] == 10, (
            f"Plan should start at TM=10 (floor(0.9×12)), got {future[0]['expected_tm']}"
        )

        # The plan should grow beyond 10 as weeks progress
        last_tm = future[-1]["expected_tm"]
        assert last_tm > 10, f"Plan should progress beyond initial TM=10, last TM={last_tm}"

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

    def test_plan_weeks_persisted(self, temp_history_dir):
        """Running plan -w N then plain plan should still show N weeks."""
        history_path = temp_history_dir / "history.jsonl"

        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        # First run: explicit 8-week horizon
        r1 = runner.invoke(app, ["plan", "-w", "8", "--json",
                                  "--history-path", str(history_path)])
        assert r1.exit_code == 0

        # Second run: no -w flag — should reuse 8 weeks from profile
        import json
        r2 = runner.invoke(app, ["plan", "--json",
                                  "--history-path", str(history_path)])
        assert r2.exit_code == 0
        data = json.loads(r2.output)
        future = [s for s in data["sessions"] if s["status"] in ("next", "planned")]
        # 8 weeks × 3 sessions/week = up to 24 future sessions (may vary by schedule)
        assert len(future) > 12, (
            f"Expected >12 future sessions from 8-week plan, got {len(future)}"
        )

    def test_rir_saved_via_cli_flag(self, temp_history_dir):
        """--rir flag is stored in history and preserved in completed_sets."""
        import json
        history_path = temp_history_dir / "history.jsonl"

        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        # Use tomorrow so the S session is chronologically after init baseline
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        result = runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", tomorrow,
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "S",
            "--sets", "8@0/180,6@0/180",
            "--rir", "2",
        ])
        assert result.exit_code == 0

        # Verify RIR is stored in completed_sets — search for the S session line
        raw = history_path.read_text()
        lines = [l for l in raw.splitlines() if l.strip()]
        s_line = next((l for l in reversed(lines) if '"session_type":"S"' in l), None)
        assert s_line is not None
        data = json.loads(s_line)
        completed = data.get("completed_sets", [])
        assert len(completed) == 2
        assert all(s.get("rir_reported") == 2 for s in completed)

    def test_notes_saved_via_cli_flag(self, temp_history_dir):
        """--notes flag is stored in history JSONL."""
        import json
        history_path = temp_history_dir / "history.jsonl"

        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        result = runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", "2026-02-20",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "H",
            "--sets", "7@0/120",
            "--notes", "felt strong today",
        ])
        assert result.exit_code == 0

        raw = history_path.read_text()
        # The notes value should appear somewhere in the history file
        assert "felt strong today" in raw

    def test_planned_sets_omitted_without_cache(self, temp_history_dir):
        """Without a plan cache, planned_sets must not appear in the JSONL."""
        import json
        history_path = temp_history_dir / "history.jsonl"

        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        # Log without ever running plan → no cache → no planned_sets
        runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", "2026-02-20",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "S",
            "--sets", "5@0/180",
        ])

        raw = history_path.read_text()
        lines = [l for l in raw.splitlines() if l.strip()]
        # JSONL uses compact separators ("session_type":"S" — no spaces)
        s_line = next(
            (l for l in reversed(lines) if '"session_type":"S"' in l), None
        )
        assert s_line is not None
        data = json.loads(s_line)
        # planned_sets should be absent (omitted when empty)
        assert "planned_sets" not in data or data["planned_sets"] == []


class TestJSONAndTrajectory:
    """Tests for --json output and --trajectory flag."""

    def _init(self, history_path):
        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

    def test_status_json(self, temp_history_dir):
        """status --json returns valid JSON with expected keys."""
        import json
        history_path = temp_history_dir / "history.jsonl"
        self._init(history_path)

        result = runner.invoke(app, ["status", "--json", "--history-path", str(history_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "training_max" in data
        assert "latest_test_max" in data
        assert "readiness_z_score" in data

    def test_volume_json(self, temp_history_dir):
        """volume --json returns valid JSON with weeks list."""
        import json
        history_path = temp_history_dir / "history.jsonl"
        self._init(history_path)

        result = runner.invoke(app, ["volume", "--json", "--history-path", str(history_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "weeks" in data
        assert isinstance(data["weeks"], list)

    def test_plan_json(self, temp_history_dir):
        """plan --json returns valid JSON with sessions and plan_changes."""
        import json
        history_path = temp_history_dir / "history.jsonl"
        self._init(history_path)

        result = runner.invoke(app, ["plan", "--json", "--history-path", str(history_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "sessions" in data
        assert "status" in data
        assert "plan_changes" in data
        assert isinstance(data["plan_changes"], list)

    def test_plan_change_notification(self, temp_history_dir):
        """Running plan twice after a new session shows plan_changes in JSON."""
        import json
        history_path = temp_history_dir / "history.jsonl"
        self._init(history_path)

        # First plan run seeds the cache
        runner.invoke(app, ["plan", "--json", "--history-path", str(history_path)])

        # Log a session so TM/plan may shift
        runner.invoke(app, [
            "log-session",
            "--history-path", str(history_path),
            "--date", "2026-02-20",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "S",
            "--sets", "5@0/180",
        ])

        # Second plan run — plan_changes may or may not be populated, but key must exist
        result = runner.invoke(app, ["plan", "--json", "--history-path", str(history_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "plan_changes" in data

    def test_plot_max_trajectory(self, temp_history_dir):
        """plot-max --trajectory exits 0 and renders trajectory markers."""
        history_path = temp_history_dir / "history.jsonl"
        self._init(history_path)

        result = runner.invoke(app, [
            "plot-max", "--trajectory", "--history-path", str(history_path)
        ])
        assert result.exit_code == 0
        # Either the trajectory dot character or the legend text should appear
        assert "·" in result.output or "projected" in result.output
