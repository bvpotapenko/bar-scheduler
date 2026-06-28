"""Tests for PlanCacheStore: the per-exercise plan-result cache + freshness."""

import os
import time

from bar_scheduler.io.plan_cache_store import PlanCacheStore


def test_save_then_load_roundtrips(tmp_path):
    store = PlanCacheStore(tmp_path)
    store.save("pull_up", [{"date": "2026-01-01"}])
    cache = store.load("pull_up")
    assert cache["plans"] == [{"date": "2026-01-01"}]
    assert cache["generated_at"] > 0


def test_load_none_when_absent(tmp_path):
    assert PlanCacheStore(tmp_path).load("pull_up") is None


def test_load_none_when_corrupt(tmp_path):
    (tmp_path / "pull_up_plan_cache.json").write_text("{ not json")
    assert PlanCacheStore(tmp_path).load("pull_up") is None


def test_load_if_fresh_returns_cache_when_input_older(tmp_path):
    store = PlanCacheStore(tmp_path)
    profile = tmp_path / "profile.json"
    profile.touch()
    os.utime(profile, (1.0, 1.0))  # ancient input
    store.save("pull_up", [{"date": "2026-01-01"}])
    assert store.load_if_fresh("pull_up", [profile])["plans"] == [{"date": "2026-01-01"}]


def test_load_if_fresh_none_when_input_newer(tmp_path):
    store = PlanCacheStore(tmp_path)
    profile = tmp_path / "profile.json"
    profile.touch()
    store.save("pull_up", [{"date": "2026-01-01"}])
    future = time.time() + 1000
    os.utime(profile, (future, future))  # input modified after generation
    assert store.load_if_fresh("pull_up", [profile]) is None


def test_load_if_fresh_none_when_no_cache(tmp_path):
    assert PlanCacheStore(tmp_path).load_if_fresh("pull_up", []) is None
