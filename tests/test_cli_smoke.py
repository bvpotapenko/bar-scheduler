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


# ===========================================================================
# Multi-exercise architecture tests (Steps 1–12)
# ===========================================================================

class TestMultiExercise:
    """Tests for the multi-exercise architecture."""

    def test_exercise_registry(self):
        """get_exercise returns known definitions; raises ValueError for unknown."""
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.exercises.base import ExerciseDefinition

        pu = get_exercise("pull_up")
        assert isinstance(pu, ExerciseDefinition)
        assert pu.exercise_id == "pull_up"

        dip = get_exercise("dip")
        assert dip.exercise_id == "dip"
        assert dip.bw_fraction == pytest.approx(0.92)

        bss = get_exercise("bss")
        assert bss.load_type == "external_only"

        with pytest.raises(ValueError):
            get_exercise("unknown_exercise")

    def test_dip_added_weight(self):
        """Dip added-weight formula: BW×0.92×0.012×(TM−12), rounded to 0.5 kg."""
        from bar_scheduler.core.planner import _calculate_added_weight
        from bar_scheduler.core.exercises.registry import get_exercise

        dip = get_exercise("dip")
        # TM=15, BW=82: raw = 82*0.92*0.012*3 = 2.716 → nearest 0.5 = 2.5
        result = _calculate_added_weight(dip, training_max=15, bodyweight_kg=82.0)
        assert result == pytest.approx(2.5)

    def test_bss_uses_test_weight(self):
        """BSS Strength sessions inherit dumbbell weight from last TEST session."""
        from bar_scheduler.core.planner import _calculate_added_weight
        from bar_scheduler.core.exercises.registry import get_exercise

        bss = get_exercise("bss")
        # external_only: always returns last_test_weight regardless of TM
        result = _calculate_added_weight(bss, training_max=12, bodyweight_kg=82.0,
                                         last_test_weight=24.0)
        assert result == pytest.approx(24.0)

        # With no test weight, returns 0
        result_zero = _calculate_added_weight(bss, training_max=12, bodyweight_kg=82.0)
        assert result_zero == pytest.approx(0.0)

    def test_auto_test_insertion(self):
        """Plan inserts TEST session when freq_weeks threshold is reached."""
        from bar_scheduler.core.planner import _insert_test_sessions
        from datetime import datetime, timedelta

        # Build a 6-week plan: sessions every 2 days (simplified)
        start = datetime(2026, 3, 1)
        session_dates = [
            (start + timedelta(days=i * 2), "S") for i in range(21)  # ~6 weeks
        ]
        # No history — threshold triggers immediately (last_test = start - 21 days)
        result = _insert_test_sessions(session_dates, [], test_frequency_weeks=3, plan_start=start)
        test_sessions = [(d, t) for d, t in result if t == "TEST"]
        assert len(test_sessions) >= 2  # should see at least 2 TEST insertions in 6 weeks

    def test_1rm_pullup(self):
        """Epley 1RM for pull-up: BW=82, 5 reps @ +10 kg → (82+10)×(1+5/30) ≈ 107.3 kg."""
        from bar_scheduler.core.metrics import estimate_1rm
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.models import SessionResult, SetResult

        pull_up = get_exercise("pull_up")
        s = SetResult(target_reps=5, actual_reps=5, rest_seconds_before=180,
                      added_weight_kg=10.0, rir_target=2)
        session = SessionResult(date="2026-03-01", bodyweight_kg=82.0, grip="pronated",
                                session_type="S", exercise_id="pull_up",
                                planned_sets=[], completed_sets=[s])
        result = estimate_1rm(pull_up, 82.0, [session])
        assert result is not None
        assert result["1rm_kg"] == pytest.approx(92.0 * (1 + 5 / 30), rel=1e-3)

    def test_1rm_bss(self):
        """Epley 1RM for BSS (external_only): 8 reps @ 48 kg → 48×(1+8/30) ≈ 60.8 kg."""
        from bar_scheduler.core.metrics import estimate_1rm
        from bar_scheduler.core.exercises.registry import get_exercise
        from bar_scheduler.core.models import SessionResult, SetResult

        bss = get_exercise("bss")
        s = SetResult(target_reps=8, actual_reps=8, rest_seconds_before=90,
                      added_weight_kg=48.0, rir_target=2)
        session = SessionResult(date="2026-03-01", bodyweight_kg=82.0, grip="standard",
                                session_type="S", exercise_id="bss",
                                planned_sets=[], completed_sets=[s])
        result = estimate_1rm(bss, 82.0, [session])
        # BSS now uses bw_fraction=0.71: Leff = 0.71×82 + 48 = 106.22 kg
        # Epley: 1RM = Leff × (1 + 8/30)
        import math
        leff = 0.71 * 82.0 + 48.0
        expected = leff * (1 + 8 / 30)
        assert result is not None
        assert result["1rm_kg"] == pytest.approx(expected, rel=1e-3)

    def test_bss_unilateral_display(self):
        """_fmt_prescribed appends '(per leg)' for BSS sessions."""
        from bar_scheduler.core.models import SessionPlan, PlannedSet
        from bar_scheduler.cli.views import _fmt_prescribed

        ps = PlannedSet(target_reps=8, rest_seconds_before=60, added_weight_kg=24.0,
                        rir_target=2)
        plan = SessionPlan(date="2026-03-01", grip="standard", session_type="S",
                           exercise_id="bss", sets=[ps], expected_tm=12, week_number=1)
        text = _fmt_prescribed(plan)
        assert "(per leg)" in text

        # Pull-up plan should NOT have the suffix
        plan_pu = SessionPlan(date="2026-03-01", grip="pronated", session_type="S",
                              exercise_id="pull_up", sets=[ps], expected_tm=12, week_number=1)
        assert "(per leg)" not in _fmt_prescribed(plan_pu)

    def test_exercise_id_serialization(self):
        """exercise_id round-trips through serialization; absent field defaults to pull_up."""
        from bar_scheduler.io.serializers import session_result_to_dict, dict_to_session_result
        from bar_scheduler.core.models import SessionResult, SetResult

        s = SetResult(target_reps=8, actual_reps=8, rest_seconds_before=180,
                      added_weight_kg=0.0, rir_target=2)

        # Dip session round-trips
        session = SessionResult(date="2026-03-01", bodyweight_kg=82.0, grip="standard",
                                session_type="H", exercise_id="dip",
                                planned_sets=[], completed_sets=[s])
        d = session_result_to_dict(session)
        assert d["exercise_id"] == "dip"
        loaded = dict_to_session_result(d)
        assert loaded.exercise_id == "dip"

        # Legacy record without exercise_id defaults to pull_up
        d_legacy = dict(d)
        d_legacy.pop("exercise_id")
        d_legacy["grip"] = "pronated"  # use a pull-up grip for legacy record
        loaded_legacy = dict_to_session_result(d_legacy)
        assert loaded_legacy.exercise_id == "pull_up"


class TestEquipmentIntegration:
    """Integration tests for the equipment-aware system."""

    def _store(self, tmp_path):
        from bar_scheduler.io.history_store import HistoryStore
        history_path = tmp_path / "history.jsonl"
        store = HistoryStore(history_path)
        store.init()
        from bar_scheduler.core.models import UserProfile
        store.save_profile(
            UserProfile(height_cm=180, sex="male", preferred_days_per_week=3,
                        target_max_reps=20),
            bodyweight_kg=80.0,
        )
        return store

    def test_equipment_history_round_trip(self, tmp_path):
        """save/load equipment history preserves all fields."""
        from bar_scheduler.core.models import EquipmentState
        store = self._store(tmp_path)
        state = EquipmentState(
            exercise_id="pull_up",
            available_items=["BAR_ONLY", "BAND_MEDIUM"],
            active_item="BAND_MEDIUM",
            valid_from="2026-01-01",
        )
        store.save_equipment_history("pull_up", [state])
        loaded = store.load_equipment_history("pull_up")
        assert len(loaded) == 1
        assert loaded[0].active_item == "BAND_MEDIUM"
        assert loaded[0].available_items == ["BAR_ONLY", "BAND_MEDIUM"]

    def test_load_current_equipment_none_when_absent(self, tmp_path):
        store = self._store(tmp_path)
        result = store.load_current_equipment("pull_up")
        assert result is None

    def test_update_equipment_closes_old_and_appends_new(self, tmp_path):
        """update_equipment sets valid_until on old entry and appends a new one."""
        from datetime import datetime, timedelta
        from bar_scheduler.core.models import EquipmentState
        store = self._store(tmp_path)

        old_state = EquipmentState(
            exercise_id="pull_up",
            available_items=["BAND_MEDIUM"],
            active_item="BAND_MEDIUM",
            valid_from="2026-01-01",
        )
        store.update_equipment(old_state)

        new_state = EquipmentState(
            exercise_id="pull_up",
            available_items=["BAR_ONLY"],
            active_item="BAR_ONLY",
            valid_from="2026-02-24",
        )
        store.update_equipment(new_state)

        history = store.load_equipment_history("pull_up")
        assert len(history) == 2
        # Old entry should now have valid_until set
        assert history[0].valid_until is not None
        # New entry should be active
        current = store.load_current_equipment("pull_up")
        assert current is not None
        assert current.active_item == "BAR_ONLY"

    def test_log_session_attaches_equipment_snapshot(self, tmp_path):
        """log-session stores equipment_snapshot if equipment state is configured."""
        from bar_scheduler.core.models import EquipmentState, SessionResult, SetResult
        from bar_scheduler.core.equipment import snapshot_from_state
        from bar_scheduler.io.serializers import session_result_to_dict

        store = self._store(tmp_path)
        # Set up equipment state
        eq_state = EquipmentState(
            exercise_id="pull_up",
            available_items=["BAND_MEDIUM"],
            active_item="BAND_MEDIUM",
            valid_from="2026-01-01",
        )
        store.update_equipment(eq_state)

        # Simulate log-session: build session with snapshot
        snapshot = snapshot_from_state(eq_state)
        s = SetResult(target_reps=8, actual_reps=8, rest_seconds_before=180,
                      added_weight_kg=0.0, rir_target=2)
        session = SessionResult(
            date="2026-02-24", bodyweight_kg=80.0, grip="pronated",
            session_type="H", exercise_id="pull_up",
            equipment_snapshot=snapshot,
            planned_sets=[], completed_sets=[s],
        )
        store.append_session(session)

        loaded = store.load_history()
        assert len(loaded) == 1
        assert loaded[0].equipment_snapshot is not None
        assert loaded[0].equipment_snapshot.active_item == "BAND_MEDIUM"
        assert loaded[0].equipment_snapshot.assistance_kg == pytest.approx(35.0)

    def test_bss_degraded_flag(self, tmp_path):
        """bss_is_degraded returns True when ELEVATION_SURFACE absent."""
        from bar_scheduler.core.models import EquipmentState
        from bar_scheduler.core.equipment import bss_is_degraded

        without_elevation = EquipmentState(
            exercise_id="bss",
            available_items=["DUMBBELLS"],
            active_item="DUMBBELLS",
            valid_from="2026-01-01",
        )
        assert bss_is_degraded(without_elevation) is True

        with_elevation = EquipmentState(
            exercise_id="bss",
            available_items=["DUMBBELLS", "ELEVATION_SURFACE"],
            active_item="DUMBBELLS",
            elevation_height_cm=45,
            valid_from="2026-01-01",
        )
        assert bss_is_degraded(with_elevation) is False
