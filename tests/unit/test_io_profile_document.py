"""Tests for ProfileDocument: the sole profile.json gateway."""

from bar_scheduler.io.profile_document import ProfileDocument


def test_read_missing_returns_empty(tmp_path):
    doc = ProfileDocument(tmp_path / "profile.json")
    assert doc.read() == {}


def test_write_then_read_roundtrips(tmp_path):
    doc = ProfileDocument(tmp_path / "profile.json")
    doc.write({"height_cm": 180, "language": "ru"})
    assert doc.read() == {"height_cm": 180, "language": "ru"}


def test_write_creates_parent_dirs(tmp_path):
    doc = ProfileDocument(tmp_path / "nested" / "deep" / "profile.json")
    doc.write({"height_cm": 175})
    assert doc.read() == {"height_cm": 175}


def test_exists_reflects_file(tmp_path):
    doc = ProfileDocument(tmp_path / "profile.json")
    assert doc.exists() is False
    doc.write({})
    assert doc.exists() is True


def test_mutate_persists_nested_key(tmp_path):
    doc = ProfileDocument(tmp_path / "profile.json")
    doc.write({"height_cm": 180})
    with doc.mutate() as raw:
        raw.setdefault("plan_start_dates", {})["pull_up"] = "2026-01-01"
    assert doc.read() == {"height_cm": 180, "plan_start_dates": {"pull_up": "2026-01-01"}}


def test_read_corrupt_returns_empty(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text("{ not valid json")
    assert ProfileDocument(path).read() == {}
