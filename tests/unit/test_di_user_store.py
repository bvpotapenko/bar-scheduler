"""DI: api resolves the user store from the container, overridable with fakes."""

import pytest
from dependency_injector import providers

from bar_scheduler import api
from bar_scheduler.containers import container
from bar_scheduler.domain.models import UserProfile


class _FakeProfileStore:
    def load(self) -> UserProfile:
        return UserProfile(height_cm=165, bodyweight_kg=55.0)


class _FakeUserStore:
    def __init__(self, data_dir):
        self.profile = _FakeProfileStore()


@pytest.fixture
def _override_user_store():
    container.user_store.override(providers.Factory(_FakeUserStore))
    yield
    container.user_store.reset_override()


def test_get_profile_resolves_store_via_container(_override_user_store, tmp_path):
    profile = api.get_profile(tmp_path)  # no real profile.json on disk
    assert profile["height_cm"] == 165
    assert profile["current_bodyweight_kg"] == pytest.approx(55.0)
