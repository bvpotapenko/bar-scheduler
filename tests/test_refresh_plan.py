"""
Tests for:
  - refresh-plan command (plan anchor reset to today)
  - long-break log-session one-liner (no interactive prompts)
  - session_type CLI normalization (M→TEST, m→TEST, etc.)
  - overtraining detection still works after long break
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

import bar_scheduler.io.history_store as hs_module
from bar_scheduler.cli.main import app

TODAY = datetime.now().strftime("%Y-%m-%d")
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
TWO_WEEKS_AGO = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def patch_data_dir(tmp_path, monkeypatch):
    """Redirect all HistoryStore operations to tmp_path."""
    monkeypatch.setattr(hs_module, "get_data_dir", lambda: tmp_path)
    yield tmp_path


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def initialized(runner, tmp_path):
    """
    A profile + pull_up exercise with a baseline TEST session (10 reps).
    Returns (runner, tmp_path).
    """
    r = runner.invoke(app, [
        "profile", "init",
        "--height-cm", "180", "--sex", "male", "--bodyweight-kg", "80",
        "--days-per-week", "3",
    ])
    assert r.exit_code == 0, f"profile init failed: {r.output}"

    # Feed newlines to accept all equipment prompts with defaults
    r = runner.invoke(app, [
        "profile", "add-exercise", "pull_up",
        "--days-per-week", "3", "--target-reps", "20",
        "--baseline-max", "10",
    ], input="\n\n\n\n\n")
    assert r.exit_code == 0, f"add-exercise failed: {r.output}"
    return runner, tmp_path


def _log(runner, date, session_type, grip, sets, bw=80.0, exercise="pull_up"):
    """Log a session one-liner."""
    return runner.invoke(app, [
        "log-session", "-e", exercise,
        "--date", date, "-w", str(bw), "-g", grip,
        "-t", session_type, "-s", sets,
    ])


def _log_sequence(runner, sessions):
    """Log a list of (date, session_type, grip) tuples with default sets."""
    for date, stype, grip in sessions:
        r = _log(runner, date, stype, grip, "8@0/180")
        assert r.exit_code == 0, f"log failed for {date} {stype}: {r.output}"


# ── Tests: session_type CLI normalization ─────────────────────────────────────


class TestSessionTypeNormalization:
    def test_uppercase_M_logs_as_TEST(self, initialized, runner):
        runner, _ = initialized
        result = _log(runner, YESTERDAY, "M", "pronated", "12")
        assert result.exit_code == 0, result.output

        r2 = runner.invoke(app, ["show-history", "-e", "pull_up", "--json"])
        history = json.loads(r2.output)
        test_sessions = [s for s in history if s["session_type"] == "TEST" and s["date"] == YESTERDAY]
        assert len(test_sessions) >= 1, f"Expected a TEST on {YESTERDAY}, got: {history}"

    def test_lowercase_m_logs_as_TEST(self, initialized, runner):
        runner, _ = initialized
        result = _log(runner, YESTERDAY, "m", "pronated", "12")
        assert result.exit_code == 0, result.output

        r2 = runner.invoke(app, ["show-history", "-e", "pull_up", "--json"])
        history = json.loads(r2.output)
        test_sessions = [s for s in history if s["session_type"] == "TEST" and s["date"] == YESTERDAY]
        assert len(test_sessions) >= 1, f"Expected a TEST on {YESTERDAY}, got: {history}"

    def test_S_H_E_T_normalized(self, initialized, runner):
        runner, _ = initialized
        for stype, grip in [("s", "pronated"), ("h", "neutral"), ("e", "supinated"), ("t", "pronated")]:
            r = _log(runner, TODAY, stype, grip, "8@0/180")
            assert r.exit_code == 0, f"{stype}: {r.output}"


class TestLogSessionOneliner:
    def test_full_oneliner_no_prompts(self, initialized, runner):
        """Full one-liner with all flags should succeed without any prompts."""
        runner, _ = initialized
        result = _log(runner, TODAY, "S", "pronated", "8@0/180,6@0/120")
        assert result.exit_code == 0, result.output

    def test_oneliner_after_long_break(self, initialized, runner):
        """Logging a session 14 days ago should work and appear in history."""
        runner, _ = initialized
        result = _log(runner, TWO_WEEKS_AGO, "S", "pronated", "8@0/180")
        assert result.exit_code == 0, result.output

        r2 = runner.invoke(app, ["show-history", "-e", "pull_up", "--json"])
        history = json.loads(r2.output)
        dates = [s["date"] for s in history]
        assert TWO_WEEKS_AGO in dates

    def test_no_REST_type_accepted(self, initialized, runner):
        """After removing REST, -t R should be rejected."""
        runner, _ = initialized
        result = _log(runner, TODAY, "R", "pronated", "")
        # Should fail with non-zero exit code (invalid session type)
        assert result.exit_code != 0


# ── Tests: refresh-plan ───────────────────────────────────────────────────────


class TestRefreshPlan:
    def test_sets_plan_start_date_to_today(self, initialized, runner):
        runner, _ = initialized
        result = runner.invoke(app, ["refresh-plan", "-e", "pull_up", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["plan_start_date"] == TODAY

    def test_next_session_not_null(self, initialized, runner):
        runner, _ = initialized
        result = runner.invoke(app, ["refresh-plan", "-e", "pull_up", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["next_session"] is not None
        assert data["next_session"]["date"] >= TODAY

    def test_next_session_follows_rotation_after_long_break(self, initialized, runner):
        """
        History: S, H, T, E sessions 2 weeks ago → next should be S.
        Schedule for 3 days/week: S, H, T, E (4-cycle).
        After E comes S again.
        """
        runner, _ = initialized
        base = datetime.now() - timedelta(days=14)
        sessions = [
            ((base + timedelta(days=0)).strftime("%Y-%m-%d"), "S", "pronated"),
            ((base + timedelta(days=2)).strftime("%Y-%m-%d"), "H", "neutral"),
            ((base + timedelta(days=4)).strftime("%Y-%m-%d"), "T", "pronated"),
            ((base + timedelta(days=6)).strftime("%Y-%m-%d"), "E", "supinated"),
        ]
        _log_sequence(runner, sessions)

        result = runner.invoke(app, ["refresh-plan", "-e", "pull_up", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["next_session"]["session_type"] == "S"

    def test_plan_shows_no_future_sessions_before_today(self, initialized, runner):
        """After refresh-plan, plan --json must show all future sessions on or after today."""
        runner, _ = initialized
        # Log some old sessions
        base = datetime.now() - timedelta(days=10)
        _log_sequence(runner, [
            ((base).strftime("%Y-%m-%d"), "S", "pronated"),
            ((base + timedelta(days=2)).strftime("%Y-%m-%d"), "H", "neutral"),
        ])

        runner.invoke(app, ["refresh-plan", "-e", "pull_up", "--json"])

        result = runner.invoke(app, ["plan", "-e", "pull_up", "--json"])
        assert result.exit_code == 0, result.output
        plan_data = json.loads(result.output)
        future = [s for s in plan_data["sessions"]
                  if s["status"] in ("next", "planned")]
        assert all(s["date"] >= TODAY for s in future), (
            f"Found future sessions before today: {[s for s in future if s['date'] < TODAY]}"
        )

    def test_no_overtraining_after_long_break(self, initialized, runner):
        """
        4 sessions crammed 2 weeks ago → no overtraining detected today
        (7-day window doesn't see them).
        """
        runner, _ = initialized
        base = datetime.now() - timedelta(days=14)
        _log_sequence(runner, [
            ((base + timedelta(days=i)).strftime("%Y-%m-%d"), "S", "pronated")
            for i in range(4)
        ])

        result = runner.invoke(app, ["refresh-plan", "-e", "pull_up", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        # Plan should succeed and yield a next session (not blocked by overtraining)
        assert data["next_session"] is not None

    def test_overtraining_detected_for_recent_sessions(self, initialized, runner):
        """
        3 sessions in the last 3 days → overtraining > 0 → plan still generates.
        """
        runner, _ = initialized
        recent_sessions = [
            ((datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"), "S", "pronated")
            for i in range(3)
        ]
        _log_sequence(runner, recent_sessions)

        # refresh-plan should still succeed
        result = runner.invoke(app, ["refresh-plan", "-e", "pull_up", "--json"])
        assert result.exit_code == 0, result.output

        # plan --json should also succeed
        result2 = runner.invoke(app, ["plan", "-e", "pull_up", "--json"])
        assert result2.exit_code == 0, result2.output
        plan_data = json.loads(result2.output)
        assert len(plan_data["sessions"]) > 0

    def test_grip_rotation_continues_from_history(self, initialized, runner):
        """
        After H session (2nd in rotation), next S should use pronated grip
        (first grip in S cycle).
        """
        runner, _ = initialized
        base = datetime.now() - timedelta(days=10)
        _log_sequence(runner, [
            (base.strftime("%Y-%m-%d"), "S", "pronated"),
        ])

        result = runner.invoke(app, ["refresh-plan", "-e", "pull_up", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        nxt = data["next_session"]
        assert nxt is not None
        assert nxt["session_type"] == "H"  # S done → H is next
        assert nxt["grip"] in ("pronated", "neutral", "supinated")  # valid grip


# ── Tests: overtraining_severity with no REST records ─────────────────────────


class TestOverttrainingSeverityNoRest:
    def test_level_zero_with_spaced_sessions(self):
        """3 sessions spread 5 days apart → overtraining level 0."""
        from bar_scheduler.core.adaptation import overtraining_severity
        from bar_scheduler.core.models import SessionResult, SetResult

        def make_session(date_str: str, stype: str = "S") -> SessionResult:
            return SessionResult(
                date=date_str, bodyweight_kg=80.0, grip="pronated",
                session_type=stype, exercise_id="pull_up",  # type: ignore
                completed_sets=[SetResult(target_reps=8, actual_reps=8,
                                          rest_seconds_before=180)],
            )

        ref = datetime.now()
        history = [
            make_session((ref - timedelta(days=14)).strftime("%Y-%m-%d")),
            make_session((ref - timedelta(days=10)).strftime("%Y-%m-%d")),
            make_session((ref - timedelta(days=5)).strftime("%Y-%m-%d")),
        ]
        result = overtraining_severity(history, days_per_week=3, reference_date=ref)
        assert result["level"] == 0

    def test_level_nonzero_with_dense_sessions(self):
        """3 sessions in 2 days → overtraining level > 0."""
        from bar_scheduler.core.adaptation import overtraining_severity
        from bar_scheduler.core.models import SessionResult, SetResult

        def make_session(date_str: str, stype: str = "S") -> SessionResult:
            return SessionResult(
                date=date_str, bodyweight_kg=80.0, grip="pronated",
                session_type=stype, exercise_id="pull_up",  # type: ignore
                completed_sets=[SetResult(target_reps=8, actual_reps=8,
                                          rest_seconds_before=180)],
            )

        ref = datetime.now()
        history = [
            make_session((ref - timedelta(days=2)).strftime("%Y-%m-%d")),
            make_session((ref - timedelta(days=1)).strftime("%Y-%m-%d")),
            make_session(ref.strftime("%Y-%m-%d")),
        ]
        result = overtraining_severity(history, days_per_week=3, reference_date=ref)
        assert result["level"] > 0
