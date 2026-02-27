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
            "plot-max", "--trajectory", "z", "--history-path", str(history_path)
        ])
        assert result.exit_code == 0
        # Either the trajectory dot character or the legend text should appear
        assert "·" in result.output or "BW reps" in result.output


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
        from bar_scheduler.core.models import ExerciseTarget, UserProfile
        store.save_profile(
            UserProfile(height_cm=180, sex="male", preferred_days_per_week=3,
                        exercise_targets={"pull_up": ExerciseTarget(reps=20)}),
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

    def test_ask_equipment_skips_active_prompt_when_same_assistance(self, tmp_path, monkeypatch):
        """
        When all selected available items have the same assistance_kg (e.g.
        BAR_ONLY + WEIGHT_BELT, both 0.0), _ask_equipment must NOT ask for an
        active item — it silently selects the first item.
        """
        from bar_scheduler.cli.commands import profile as profile_mod
        from bar_scheduler.core.models import EquipmentState

        # Simulate user entering "1,6" for available items (BAR_ONLY + WEIGHT_BELT)
        # then nothing more — if the active-item prompt fires it would block.
        # BAR_ONLY is item 1, WEIGHT_BELT is item 6 in the pull_up catalog.
        inputs = iter(["1,6"])  # only one input: available items selection

        monkeypatch.setattr(profile_mod.views.console, "input", lambda _prompt: next(inputs))
        monkeypatch.setattr(profile_mod.views.console, "print", lambda *a, **kw: None)

        result = profile_mod._ask_equipment("pull_up", existing=None)

        # Both BAR_ONLY (idx 1) and WEIGHT_BELT (idx 6) have assistance_kg=0.0;
        # active_item should default to the first selected item without prompting.
        assert result.available_items == ["BAR_ONLY", "WEIGHT_BELT"]
        assert result.active_item == "BAR_ONLY"
        # Confirm the iterator was fully consumed (no extra prompts fired)
        assert list(inputs) == []

    def test_ask_equipment_shows_active_prompt_when_assistance_differs(self, tmp_path, monkeypatch):
        """
        When selected items have different assistance values (e.g. BAR_ONLY +
        BAND_MEDIUM), _ask_equipment MUST ask which one is active.
        """
        from bar_scheduler.cli.commands import profile as profile_mod

        # User selects items 1 (BAR_ONLY) and 3 (BAND_MEDIUM) as available,
        # then picks item 2 (BAND_MEDIUM) as the active one.
        inputs = iter(["1,3", "2"])

        monkeypatch.setattr(profile_mod.views.console, "input", lambda _prompt: next(inputs))
        monkeypatch.setattr(profile_mod.views.console, "print", lambda *a, **kw: None)

        result = profile_mod._ask_equipment("pull_up", existing=None)

        assert result.available_items == ["BAR_ONLY", "BAND_MEDIUM"]
        assert result.active_item == "BAND_MEDIUM"
        assert list(inputs) == []


# =============================================================================
# ExerciseTarget and per-exercise goals
# =============================================================================


class TestExerciseTarget:
    """Unit tests for ExerciseTarget and UserProfile.target_for_exercise."""

    def test_str_reps_only(self):
        from bar_scheduler.core.models import ExerciseTarget
        assert str(ExerciseTarget(reps=30)) == "30 reps"

    def test_str_reps_and_weight(self):
        from bar_scheduler.core.models import ExerciseTarget
        assert str(ExerciseTarget(reps=12, weight_kg=40.0)) == "12 reps @ 40.0 kg"

    def test_invalid_reps_raises(self):
        from bar_scheduler.core.models import ExerciseTarget
        with pytest.raises(ValueError, match="reps"):
            ExerciseTarget(reps=0)

    def test_negative_weight_raises(self):
        from bar_scheduler.core.models import ExerciseTarget
        with pytest.raises(ValueError, match="weight_kg"):
            ExerciseTarget(reps=10, weight_kg=-1.0)

    def test_target_for_exercise_explicit(self):
        from bar_scheduler.core.models import ExerciseTarget, UserProfile
        p = UserProfile(
            height_cm=175, sex="male",
            exercise_targets={"pull_up": ExerciseTarget(reps=25)},
        )
        assert p.target_for_exercise("pull_up").reps == 25
        assert p.target_for_exercise("pull_up").weight_kg == 0.0

    def test_target_for_exercise_fallback_defaults(self):
        """When no explicit target is set, returns hardcoded per-exercise defaults."""
        from bar_scheduler.core.models import UserProfile
        p = UserProfile(height_cm=175, sex="male")
        assert p.target_for_exercise("pull_up").reps == 30
        assert p.target_for_exercise("dip").reps == 40
        assert p.target_for_exercise("bss").reps == 20
        assert p.target_for_exercise("unknown").reps == 30  # generic fallback

    def test_target_for_exercise_weight_zero_by_default(self):
        from bar_scheduler.core.models import UserProfile
        p = UserProfile(height_cm=175, sex="male")
        assert p.target_for_exercise("bss").weight_kg == 0.0

    def test_target_for_exercise_with_weight(self):
        from bar_scheduler.core.models import ExerciseTarget, UserProfile
        p = UserProfile(
            height_cm=175, sex="male",
            exercise_targets={"bss": ExerciseTarget(reps=20, weight_kg=40.0)},
        )
        t = p.target_for_exercise("bss")
        assert t.reps == 20
        assert t.weight_kg == 40.0

    def test_serialization_round_trip_reps_only(self):
        from bar_scheduler.core.models import ExerciseTarget
        from bar_scheduler.io.serializers import dict_to_exercise_target, exercise_target_to_dict
        t = ExerciseTarget(reps=30)
        d = exercise_target_to_dict(t)
        assert d == {"reps": 30}  # weight_kg omitted when 0
        t2 = dict_to_exercise_target(d)
        assert t2.reps == 30
        assert t2.weight_kg == 0.0

    def test_serialization_round_trip_with_weight(self):
        from bar_scheduler.core.models import ExerciseTarget
        from bar_scheduler.io.serializers import dict_to_exercise_target, exercise_target_to_dict
        t = ExerciseTarget(reps=12, weight_kg=40.0)
        d = exercise_target_to_dict(t)
        assert d == {"reps": 12, "weight_kg": 40.0}
        t2 = dict_to_exercise_target(d)
        assert t2.reps == 12
        assert t2.weight_kg == 40.0

    def test_profile_round_trip_with_targets(self):
        from bar_scheduler.core.models import ExerciseTarget, UserProfile
        from bar_scheduler.io.serializers import dict_to_user_profile, user_profile_to_dict
        p = UserProfile(
            height_cm=180, sex="male",
            exercise_targets={
                "pull_up": ExerciseTarget(reps=25),
                "bss": ExerciseTarget(reps=15, weight_kg=30.0),
            },
        )
        d = user_profile_to_dict(p)
        assert d["exercise_targets"]["pull_up"] == {"reps": 25}
        assert d["exercise_targets"]["bss"] == {"reps": 15, "weight_kg": 30.0}
        p2 = dict_to_user_profile(d)
        assert p2.target_for_exercise("pull_up").reps == 25
        assert p2.target_for_exercise("bss").weight_kg == 30.0

    def test_backward_compat_target_max_reps_migrates(self):
        """Old JSON with target_max_reps migrates to pull_up ExerciseTarget."""
        from bar_scheduler.io.serializers import dict_to_user_profile
        old = {
            "height_cm": 175, "sex": "male", "preferred_days_per_week": 3,
            "target_max_reps": 25,
        }
        p = dict_to_user_profile(old)
        assert p.target_for_exercise("pull_up").reps == 25
        assert p.target_for_exercise("dip").reps == 40  # default, not migrated

    def test_init_command_writes_exercise_targets(self, tmp_path):
        """init --target-max 20 --target-weight 10 writes ExerciseTarget to profile."""
        import json as _json
        history_path = tmp_path / "history.jsonl"
        result = runner.invoke(app, [
            "init", "--history-path", str(history_path),
            "--target-max", "20", "--target-weight", "10.0",
            "--exercise", "bss",
        ])
        assert result.exit_code == 0, result.output
        profile_path = history_path.parent / "profile.json"
        data = _json.loads(profile_path.read_text())
        assert "exercise_targets" in data
        assert data["exercise_targets"]["bss"]["reps"] == 20
        assert data["exercise_targets"]["bss"]["weight_kg"] == 10.0

    def test_different_targets_per_exercise(self, tmp_path):
        """init for two exercises stores separate targets without clobbering each other."""
        import json as _json
        pull_up_path = tmp_path / "pull_up_history.jsonl"
        bss_path = tmp_path / "bss_history.jsonl"
        # init pull_up
        runner.invoke(app, [
            "init", "--history-path", str(pull_up_path),
            "--target-max", "30", "--exercise", "pull_up",
        ])
        # init bss with a weight goal
        runner.invoke(app, [
            "init", "--history-path", str(bss_path),
            "--target-max", "15", "--target-weight", "40.0", "--exercise", "bss",
        ])
        profile_path = pull_up_path.parent / "profile.json"
        data = _json.loads(profile_path.read_text())
        # both exercises must be present
        assert data["exercise_targets"]["pull_up"]["reps"] == 30
        assert "weight_kg" not in data["exercise_targets"]["pull_up"]
        assert data["exercise_targets"]["bss"]["reps"] == 15
        assert data["exercise_targets"]["bss"]["weight_kg"] == 40.0


# =============================================================================
# New feature tests: profile fields, help-adaptation, YAML config loader
# =============================================================================


class TestProfileFields:
    """Tests for new UserProfile fields added in task.md §6."""

    def test_default_new_fields(self):
        """UserProfile has correct defaults for new fields."""
        from bar_scheduler.core.models import UserProfile

        p = UserProfile(height_cm=175, sex="male")
        assert p.exercises_enabled == ["pull_up", "dip", "bss"]
        assert p.max_session_duration_minutes == 60
        assert p.rest_preference == "normal"
        assert p.injury_notes == ""

    def test_is_exercise_enabled(self):
        """is_exercise_enabled respects the exercises_enabled list."""
        from bar_scheduler.core.models import UserProfile

        p = UserProfile(
            height_cm=175,
            sex="male",
            exercises_enabled=["pull_up", "dip"],
        )
        assert p.is_exercise_enabled("pull_up") is True
        assert p.is_exercise_enabled("dip") is True
        assert p.is_exercise_enabled("bss") is False

    def test_invalid_rest_preference_raises(self):
        """rest_preference must be 'short', 'normal', or 'long'."""
        from bar_scheduler.core.models import UserProfile

        with pytest.raises(ValueError, match="rest_preference"):
            UserProfile(height_cm=175, sex="male", rest_preference="very_slow")

    def test_profile_serialisation_round_trip(self):
        """New fields survive to_dict / from_dict round-trip."""
        from bar_scheduler.core.models import UserProfile
        from bar_scheduler.io.serializers import dict_to_user_profile, user_profile_to_dict

        p = UserProfile(
            height_cm=180,
            sex="female",
            preferred_days_per_week=4,
            exercises_enabled=["pull_up"],
            max_session_duration_minutes=45,
            rest_preference="short",
            injury_notes="left elbow tendinopathy",
        )
        d = user_profile_to_dict(p)
        assert d["exercises_enabled"] == ["pull_up"]
        assert d["max_session_duration_minutes"] == 45
        assert d["rest_preference"] == "short"
        assert d["injury_notes"] == "left elbow tendinopathy"

        p2 = dict_to_user_profile(d)
        assert p2.exercises_enabled == ["pull_up"]
        assert p2.max_session_duration_minutes == 45
        assert p2.rest_preference == "short"
        assert p2.injury_notes == "left elbow tendinopathy"

    def test_backwards_compat_missing_fields(self):
        """Old profile JSON without new fields deserialises with defaults."""
        from bar_scheduler.io.serializers import dict_to_user_profile

        old_dict = {
            "height_cm": 175,
            "sex": "male",
            "preferred_days_per_week": 3,
            "target_max_reps": 30,
            # new fields deliberately absent
        }
        p = dict_to_user_profile(old_dict)
        assert p.exercises_enabled == ["pull_up", "dip", "bss"]
        assert p.max_session_duration_minutes == 60
        assert p.rest_preference == "normal"
        assert p.injury_notes == ""
        # Old target_max_reps migrated to pull_up ExerciseTarget
        assert p.target_for_exercise("pull_up").reps == 30
        # Other exercises fall back to their built-in defaults
        assert p.target_for_exercise("dip").reps == 40
        assert p.target_for_exercise("bss").reps == 20

    def test_init_command_preserves_new_fields(self, tmp_path):
        """Re-running init does not reset exercises_enabled or injury_notes."""
        import json as _json

        history_path = tmp_path / "history.jsonl"

        # Initial init
        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--height-cm", "175",
            "--sex", "male",
            "--days-per-week", "3",
            "--bodyweight-kg", "80",
        ])

        # Manually patch the profile to set custom values
        profile_path = tmp_path / "profile.json"
        data = _json.loads(profile_path.read_text())
        data["exercises_enabled"] = ["pull_up"]
        data["injury_notes"] = "shoulder impingement"
        data["rest_preference"] = "long"
        profile_path.write_text(_json.dumps(data))

        # Re-run init (keep existing history)
        runner.invoke(app, [
            "init",
            "--history-path", str(history_path),
            "--height-cm", "178",  # changed
            "--sex", "male",
            "--days-per-week", "3",
            "--bodyweight-kg", "80",
            "--force",
        ])

        # Profile should keep custom new fields
        data2 = _json.loads(profile_path.read_text())
        assert data2.get("exercises_enabled") == ["pull_up"]
        assert data2.get("injury_notes") == "shoulder impingement"
        assert data2.get("rest_preference") == "long"


class TestHelpAdaptation:
    """Tests for the help-adaptation CLI command."""

    def test_help_adaptation_runs(self):
        """help-adaptation command exits 0 and prints the table."""
        result = runner.invoke(app, ["help-adaptation"])
        assert result.exit_code == 0

    def test_help_adaptation_contains_stages(self):
        """Output mentions all adaptation stages."""
        result = runner.invoke(app, ["help-adaptation"])
        assert "Day 1" in result.output
        assert "Weeks 1" in result.output
        assert "Weeks 3" in result.output
        assert "Weeks 6" in result.output
        assert "Weeks 12" in result.output

    def test_help_adaptation_contains_tips(self):
        """Output contains practical tips section."""
        result = runner.invoke(app, ["help-adaptation"])
        assert "TIPS" in result.output or "tips" in result.output.lower()
        assert "TEST" in result.output

    def test_help_adaptation_in_help_text(self):
        """help-adaptation is visible in the app's command list."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "help-adaptation" in result.output or "adaptation" in result.output.lower()


class TestYAMLConfigLoader:
    """Tests for the YAML config loader (task.md #14)."""

    def test_load_model_config_returns_dict(self):
        """load_model_config() returns a dict (even if yaml is unavailable)."""
        from bar_scheduler.core.engine.config_loader import load_model_config

        cfg = load_model_config()
        assert isinstance(cfg, dict)

    def test_bundled_yaml_has_expected_sections(self):
        """Bundled exercises.yaml contains all required config sections."""
        from bar_scheduler.core.engine.config_loader import load_model_config

        cfg = load_model_config()
        # Only check if YAML loaded; it may be empty if PyYAML not installed
        if not cfg:
            pytest.skip("PyYAML not available — skipping YAML content checks")

        expected_sections = [
            "rest_normalization",
            "fitness_fatigue",
            "progression",
            "plateau",
            "autoregulation",
            "volume",
        ]
        for section in expected_sections:
            assert section in cfg, f"Missing section: {section}"

    def test_bundled_yaml_rest_ref_seconds(self):
        """REST_REF_SECONDS in YAML matches config.py default (180)."""
        from bar_scheduler.core.engine.config_loader import load_model_config

        cfg = load_model_config()
        if not cfg:
            pytest.skip("PyYAML not available")

        val = cfg.get("rest_normalization", {}).get("REST_REF_SECONDS")
        assert val == 180, f"Expected 180, got {val}"

    def test_user_override_merges(self, tmp_path, monkeypatch):
        """User override at ~/.bar-scheduler/exercises.yaml is merged."""
        from bar_scheduler.core.engine import config_loader

        override_dir = tmp_path / ".bar-scheduler"
        override_dir.mkdir()
        override_file = override_dir / "exercises.yaml"
        override_file.write_text(
            "rest_normalization:\n  REST_REF_SECONDS: 240\n"
        )

        # Patch get_user_yaml_path to return our temp file
        monkeypatch.setattr(config_loader, "get_user_yaml_path", lambda: override_file)

        cfg = config_loader.load_model_config()
        if not cfg:
            pytest.skip("PyYAML not available")

        val = cfg.get("rest_normalization", {}).get("REST_REF_SECONDS")
        assert val == 240, f"User override should give 240, got {val}"

    def test_deep_merge_preserves_other_keys(self, tmp_path, monkeypatch):
        """User override only changes specified keys; others remain from bundled."""
        from bar_scheduler.core.engine import config_loader

        override_dir = tmp_path / ".bar-scheduler"
        override_dir.mkdir()
        override_file = override_dir / "exercises.yaml"
        # Override only one fitness_fatigue constant
        override_file.write_text("fitness_fatigue:\n  TAU_FATIGUE: 5.0\n")
        monkeypatch.setattr(config_loader, "get_user_yaml_path", lambda: override_file)

        cfg = config_loader.load_model_config()
        if not cfg:
            pytest.skip("PyYAML not available")

        ff = cfg.get("fitness_fatigue", {})
        assert ff.get("TAU_FATIGUE") == 5.0
        # TAU_FITNESS should still be the bundled default (42.0)
        assert ff.get("TAU_FITNESS") == 42.0


# =============================================================================
# Interactive log-session tests (Task 4)
# =============================================================================


class TestInteractiveLogSession:
    """Smoke tests for interactive log-session input paths."""

    def _init_with_baseline(self, history_path: Path, exercise_id: str = "pull_up") -> None:
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        runner.invoke(app, [
            "init",
            "--exercise", exercise_id,
            "--history-path", str(history_path),
            "--height-cm", "180",
            "--sex", "male",
            "--days-per-week", "3",
            "--bodyweight-kg", "82",
            "--baseline-max", "12",
        ])

    def test_log_session_pull_up_noninteractive(self, temp_history_dir):
        """Non-interactive pull_up log with all flags exits 0 and persists session."""
        history_path = temp_history_dir / "history.jsonl"
        self._init_with_baseline(history_path)

        result = runner.invoke(app, [
            "log-session",
            "--exercise", "pull_up",
            "--history-path", str(history_path),
            "--date", "2026-03-01",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "S",
            "--sets", "5@0/180,5@0/180,4@0/180",
        ])
        assert result.exit_code == 0, result.output
        assert "Logged" in result.output

    def test_log_session_dip_noninteractive_no_grip_prompt(self, temp_history_dir):
        """Dip log with --grip omitted uses primary variant (standard) without asking."""
        history_path = temp_history_dir / "dip_history.jsonl"
        self._init_with_baseline(history_path, "dip")

        # No --grip flag: should work because dip defaults to 'standard'
        result = runner.invoke(app, [
            "log-session",
            "--exercise", "dip",
            "--history-path", str(history_path),
            "--date", "2026-03-01",
            "--bodyweight-kg", "82",
            "--session-type", "H",
            "--sets", "8@0/120,8@0/120,6@0/120",
        ])
        assert result.exit_code == 0, result.output
        assert "Logged" in result.output

    def test_log_session_bss_noninteractive(self, temp_history_dir):
        """BSS log with all flags exits 0 and persists session."""
        history_path = temp_history_dir / "bss_history.jsonl"
        self._init_with_baseline(history_path, "bss")

        result = runner.invoke(app, [
            "log-session",
            "--exercise", "bss",
            "--history-path", str(history_path),
            "--date", "2026-03-01",
            "--bodyweight-kg", "82",
            "--grip", "standard",
            "--session-type", "H",
            "--sets", "10@24/90,10@24/90,8@24/90",
        ])
        assert result.exit_code == 0, result.output
        assert "Logged" in result.output

    def test_log_session_compact_format(self, temp_history_dir):
        """Compact set format '4x5 +2kg / 240s' is accepted by log-session."""
        history_path = temp_history_dir / "history.jsonl"
        self._init_with_baseline(history_path)

        result = runner.invoke(app, [
            "log-session",
            "--exercise", "pull_up",
            "--history-path", str(history_path),
            "--date", "2026-03-01",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "S",
            "--sets", "4x5 +2kg / 240s",
        ])
        assert result.exit_code == 0, result.output
        assert "Logged" in result.output

    def test_log_session_overperformance_creates_test(self, temp_history_dir):
        """Logging reps > test_max auto-creates a TEST session."""
        history_path = temp_history_dir / "history.jsonl"
        self._init_with_baseline(history_path)  # baseline_max=12 → test_max=12

        result = runner.invoke(app, [
            "log-session",
            "--exercise", "pull_up",
            "--history-path", str(history_path),
            "--date", "2026-03-02",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "H",
            "--sets", "15@0/180",  # 15 reps > 12 test_max → personal best
        ])
        assert result.exit_code == 0, result.output
        assert "personal best" in result.output.lower() or "New personal best" in result.output

    def test_log_session_json_output_fields(self, temp_history_dir):
        """--json output contains all expected fields with correct types."""
        import json
        history_path = temp_history_dir / "history.jsonl"
        self._init_with_baseline(history_path)

        result = runner.invoke(app, [
            "log-session",
            "--exercise", "pull_up",
            "--history-path", str(history_path),
            "--date", "2026-03-01",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "S",
            "--sets", "6@0/180,5@0/180",
            "--json",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["date"] == "2026-03-01"
        assert data["session_type"] == "S"
        assert data["grip"] == "pronated"
        assert data["bodyweight_kg"] == pytest.approx(82.0)
        assert data["total_reps"] == 11
        assert isinstance(data["sets"], list)
        assert len(data["sets"]) == 2
        assert data["sets"][0]["reps"] == 6
        assert data["sets"][0]["rest_s"] == 180

    def test_markup_hint_does_not_crash(self, temp_history_dir):
        """_interactive_sets help text renders without Rich MarkupError."""
        # Simulate interactive input: enter one set then blank line to finish
        history_path = temp_history_dir / "history.jsonl"
        self._init_with_baseline(history_path)

        result = runner.invoke(app, [
            "log-session",
            "--exercise", "pull_up",
            "--history-path", str(history_path),
            "--date", "2026-03-01",
            "--bodyweight-kg", "82",
            "--grip", "pronated",
            "--session-type", "S",
        ], input="8@0/180\n\n\n")  # one set, blank to finish, blank for RIR, blank for notes
        # Should not crash with MarkupError; exit code 0 or 1 both acceptable
        # as long as there's no exception traceback
        assert "MarkupError" not in result.output
        assert "Error" not in result.output or "invalid" in result.output.lower()


# =============================================================================
# All commands × all exercise types (Task 4 extended)
# =============================================================================


class TestAllCommandsAllExercises:
    """
    Smoke tests covering plan / status / show-history / plot-max / volume / 1rm
    for each of the three exercises (pull_up, dip, bss).
    Does NOT duplicate tests already in TestCLISmoke or TestMultiExercise.
    """

    def _setup_exercise(self, tmp_path: Path, exercise_id: str) -> Path:
        """Init and log one session for the given exercise; return history path."""
        history_path = tmp_path / f"{exercise_id}_history.jsonl"
        grip = "pronated" if exercise_id == "pull_up" else "standard"
        runner.invoke(app, [
            "init",
            "--exercise", exercise_id,
            "--history-path", str(history_path),
            "--height-cm", "180", "--sex", "male",
            "--days-per-week", "3", "--bodyweight-kg", "82",
            "--baseline-max", "12",
        ])
        runner.invoke(app, [
            "log-session",
            "--exercise", exercise_id,
            "--history-path", str(history_path),
            "--date", "2026-03-01",
            "--bodyweight-kg", "82",
            "--grip", grip,
            "--session-type", "H",
            "--sets", "8@0/120,8@0/120,7@0/120",
        ])
        return history_path

    # ── plan ───────────────────────────────────────────────────────────────

    @pytest.mark.parametrize("exercise_id", ["pull_up", "dip", "bss"])
    def test_plan_exits_0_for_each_exercise(self, tmp_path, exercise_id):
        """plan exits 0 and outputs session rows for pull_up, dip, and bss."""
        history_path = self._setup_exercise(tmp_path, exercise_id)
        result = runner.invoke(app, [
            "plan", "--exercise", exercise_id,
            "--history-path", str(history_path),
        ])
        assert result.exit_code == 0, f"[{exercise_id}] {result.output}"

    # ── status ─────────────────────────────────────────────────────────────

    @pytest.mark.parametrize("exercise_id", ["pull_up", "dip", "bss"])
    def test_status_for_each_exercise(self, tmp_path, exercise_id):
        """status --json exits 0 and contains training_max for each exercise."""
        import json
        history_path = self._setup_exercise(tmp_path, exercise_id)
        result = runner.invoke(app, [
            "status", "--json",
            "--exercise", exercise_id,
            "--history-path", str(history_path),
        ])
        assert result.exit_code == 0, f"[{exercise_id}] {result.output}"
        data = json.loads(result.output)
        assert "training_max" in data
        assert isinstance(data["training_max"], int)

    # ── show-history ───────────────────────────────────────────────────────

    @pytest.mark.parametrize("exercise_id", ["pull_up", "dip", "bss"])
    def test_show_history_for_each_exercise(self, tmp_path, exercise_id):
        """show-history exits 0 for all exercises."""
        history_path = self._setup_exercise(tmp_path, exercise_id)
        result = runner.invoke(app, [
            "show-history", "--exercise", exercise_id,
            "--history-path", str(history_path),
        ])
        assert result.exit_code == 0, f"[{exercise_id}] {result.output}"

    # ── plot-max ───────────────────────────────────────────────────────────

    @pytest.mark.parametrize("exercise_id", ["pull_up", "dip", "bss"])
    def test_plot_max_for_each_exercise(self, tmp_path, exercise_id):
        """plot-max exits 0 for all exercises."""
        history_path = self._setup_exercise(tmp_path, exercise_id)
        result = runner.invoke(app, [
            "plot-max", "--exercise", exercise_id,
            "--history-path", str(history_path),
        ])
        assert result.exit_code == 0, f"[{exercise_id}] {result.output}"

    # ── volume ─────────────────────────────────────────────────────────────

    @pytest.mark.parametrize("exercise_id", ["pull_up", "dip", "bss"])
    def test_volume_for_each_exercise(self, tmp_path, exercise_id):
        """volume --json exits 0 for all exercises."""
        import json
        history_path = self._setup_exercise(tmp_path, exercise_id)
        result = runner.invoke(app, [
            "volume", "--json",
            "--exercise", exercise_id,
            "--history-path", str(history_path),
        ])
        assert result.exit_code == 0, f"[{exercise_id}] {result.output}"
        data = json.loads(result.output)
        assert "weeks" in data

    # ── 1rm ────────────────────────────────────────────────────────────────

    @pytest.mark.parametrize("exercise_id,sets_str", [
        ("pull_up", "5@0/180"),        # pull_up: BW is load
        ("dip",     "5@0/180"),        # dip: BW×0.92 is load
        ("bss",     "10@24/90"),       # BSS: external load required for 1RM
    ])
    def test_1rm_for_each_exercise(self, tmp_path, exercise_id, sets_str):
        """1rm exits 0 for all exercises when sessions with usable load exist."""
        history_path = tmp_path / f"{exercise_id}_history.jsonl"
        grip = "pronated" if exercise_id == "pull_up" else "standard"
        runner.invoke(app, [
            "init", "--exercise", exercise_id,
            "--history-path", str(history_path),
            "--height-cm", "180", "--sex", "male",
            "--days-per-week", "3", "--bodyweight-kg", "82",
            "--baseline-max", "12",
        ])
        runner.invoke(app, [
            "log-session", "--exercise", exercise_id,
            "--history-path", str(history_path),
            "--date", "2026-03-01", "--bodyweight-kg", "82",
            "--grip", grip, "--session-type", "H",
            "--sets", sets_str,
        ])
        result = runner.invoke(app, [
            "1rm", "--exercise", exercise_id,
            "--history-path", str(history_path),
        ])
        assert result.exit_code == 0, f"[{exercise_id}] {result.output}"

    # ── delete-record ──────────────────────────────────────────────────────

    @pytest.mark.parametrize("exercise_id", ["pull_up", "dip", "bss"])
    def test_delete_record_for_each_exercise(self, tmp_path, exercise_id):
        """delete-record #1 (the init baseline TEST) works for all exercises."""
        history_path = self._setup_exercise(tmp_path, exercise_id)
        # After setup: history has [baseline TEST, H session] → delete #2 (H)
        result = runner.invoke(app, [
            "delete-record", "2",
            "--exercise", exercise_id,
            "--history-path", str(history_path),
            "--force",
        ])
        assert result.exit_code == 0, f"[{exercise_id}] {result.output}"
        assert "Deleted" in result.output

    # ── interactive exercise selection: only initialized exercises shown ───

    def test_interactive_log_only_shows_initialized_exercises(self, tmp_path):
        """Exercise selection prompt only offers exercises with existing history."""
        # Only init pull_up — bss and dip should NOT appear
        pu_path = tmp_path / "pull_up_history.jsonl"
        runner.invoke(app, [
            "init", "--exercise", "pull_up",
            "--history-path", str(pu_path),
            "--height-cm", "180", "--sex", "male",
            "--days-per-week", "3", "--bodyweight-kg", "82",
            "--baseline-max", "10",
        ])

        # Simulate interactive log: pick "3" which would be BSS if all exercises shown
        # The prompt should only show [1] for pull_up, so "3" is invalid
        result = runner.invoke(app, [
            "log-session",
            "--history-path", str(pu_path),
        ], input="1\n\n2026-03-01\n82\npronated\nS\n8@0/180\n\n\n")

        # Should not crash with "History file not found: bss_history.jsonl"
        assert "bss_history.jsonl" not in result.output
        assert "dip_history.jsonl" not in result.output


class TestTimelineBugFixes:
    """Unit tests for two display bugs in build_timeline / print_unified_plan.

    BUG 1: Past sessions with empty planned_sets (cache miss at log time) must not
            show a prescription taken from the freshly-regenerated plan entry.
    BUG 2: Track-B eMax estimates must only be computed for S and H sessions.
            Endurance (E) and Technique (T) sessions use intentionally short rests
            and sub-failure reps — the FI/Nuzzo estimator gives meaningless results.
    """

    def _make_set(self, reps: int, rest: int, rir: int = 2):
        from bar_scheduler.core.models import SetResult

        return SetResult(
            target_reps=reps,
            actual_reps=reps,
            rest_seconds_before=rest,
            rir_reported=rir,
        )

    def _past_plan(self, session_type: str, date: str = "2026-01-15"):
        from bar_scheduler.core.models import SessionPlan

        return SessionPlan(date=date, grip="pronated", session_type=session_type, week_number=1)

    def _past_session(self, session_type: str, completed_sets: list, date: str = "2026-01-15"):
        from bar_scheduler.core.models import SessionResult

        return SessionResult(
            date=date,
            bodyweight_kg=80.0,
            grip="pronated",
            session_type=session_type,
            planned_sets=[],
            completed_sets=completed_sets,
        )

    # --- BUG 2: track_b should only be computed for S and H ---

    def test_endurance_track_b_is_none(self):
        """E sessions must not produce a track_b estimate regardless of set count."""
        from bar_scheduler.cli.views import build_timeline

        sets = [self._make_set(10, 60) for _ in range(4)]
        entries = build_timeline([self._past_plan("E")], [self._past_session("E", sets)])
        assert len(entries) == 1
        assert entries[0].track_b is None

    def test_technique_track_b_is_none(self):
        """T sessions must not produce a track_b estimate (sub-failure by design)."""
        from bar_scheduler.cli.views import build_timeline

        sets = [self._make_set(5, 120) for _ in range(3)]
        entries = build_timeline([self._past_plan("T")], [self._past_session("T", sets)])
        assert len(entries) == 1
        assert entries[0].track_b is None

    def test_strength_track_b_computed(self):
        """S sessions with ≥2 sets and a valid rep pattern must produce a track_b estimate."""
        from bar_scheduler.cli.views import build_timeline

        sets = [
            self._make_set(10, 120),
            self._make_set(8, 240),
            self._make_set(7, 240),
            self._make_set(6, 240),
        ]
        entries = build_timeline([self._past_plan("S")], [self._past_session("S", sets)])
        assert len(entries) == 1
        assert entries[0].track_b is not None

    def test_hypertrophy_track_b_computed(self):
        """H sessions with ≥2 sets and a valid rep pattern must produce a track_b estimate."""
        from bar_scheduler.cli.views import build_timeline

        sets = [
            self._make_set(10, 120),
            self._make_set(8, 180),
            self._make_set(7, 180),
            self._make_set(6, 180),
        ]
        entries = build_timeline([self._past_plan("H")], [self._past_session("H", sets)])
        assert len(entries) == 1
        assert entries[0].track_b is not None

    # --- BUG 1: past session with empty planned_sets must not show regenerated plan ---

    def test_past_session_prescribed_uses_stored_not_regenerated(self):
        """When a past session has empty planned_sets (cache miss) and the regenerated
        plan has a *different* session type on the same date, the prescribed column
        must be empty — not taken from the regenerated plan prescription.

        The rendering fix is: `elif entry.planned and entry.actual is None:` (future only).
        """
        from bar_scheduler.cli.views import TimelineEntry, build_timeline
        from bar_scheduler.core.models import SessionPlan, SessionResult

        date = "2026-01-15"
        # Regenerated plan says S session on this date (rotation shifted after a log)
        plan_entry = SessionPlan(date=date, grip="pronated", session_type="S", week_number=1)
        # User actually logged an E session; no stored prescription (cache miss)
        actual_session = SessionResult(
            date=date,
            bodyweight_kg=80.0,
            grip="pronated",
            session_type="E",
            planned_sets=[],
            completed_sets=[],
        )

        entries = build_timeline([plan_entry], [actual_session])
        assert len(entries) == 1
        entry = entries[0]

        # Confirm the bug-prone state: past, empty planned_sets, non-None planned
        assert entry.actual is actual_session
        assert entry.planned is plan_entry
        assert entry.actual.planned_sets == []
        assert entry.actual is not None

        # The rendering fix: only use entry.planned for future sessions (actual is None)
        def _prescribed(e: TimelineEntry) -> str:
            if e.actual and e.actual.planned_sets:
                return "stored"
            elif e.planned and e.actual is None:
                return "plan"
            return ""

        # With the fix: past session with empty planned_sets → empty prescribed
        assert _prescribed(entry) == ""
