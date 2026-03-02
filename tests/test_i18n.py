"""
Tests for bar_scheduler.core.i18n — translation lookup, language switching,
profile serialization with language, and backward compatibility.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Autouse fixture: reset i18n state between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_i18n():
    """Reset language to 'en' and clear catalog cache after every test."""
    yield
    from bar_scheduler.core import i18n as _i18n  # noqa: PLC0415

    _i18n.set_language("en")
    _i18n._catalogs.clear()


# ---------------------------------------------------------------------------
# TestAvailableLanguages
# ---------------------------------------------------------------------------


class TestAvailableLanguages:
    def test_returns_list(self):
        from bar_scheduler.core.i18n import available_languages

        langs = available_languages()
        assert isinstance(langs, list)

    def test_en_always_present(self):
        from bar_scheduler.core.i18n import available_languages

        assert "en" in available_languages()

    def test_ru_present(self):
        from bar_scheduler.core.i18n import available_languages

        assert "ru" in available_languages()

    def test_zh_present(self):
        from bar_scheduler.core.i18n import available_languages

        assert "zh" in available_languages()

    def test_sorted(self):
        from bar_scheduler.core.i18n import available_languages

        langs = available_languages()
        assert langs == sorted(langs)

    def test_missing_locales_dir_returns_en(self, tmp_path, monkeypatch):
        """If locales dir doesn't exist, returns ['en'] rather than raising."""
        from bar_scheduler.core import i18n as _i18n

        monkeypatch.setattr(_i18n, "_locales_dir", lambda: tmp_path / "nonexistent")
        result = _i18n.available_languages()
        assert result == ["en"]

    def test_empty_locales_dir_returns_en(self, tmp_path, monkeypatch):
        """Empty locales dir → ['en'] fallback."""
        from bar_scheduler.core import i18n as _i18n

        (tmp_path / "locales").mkdir()
        monkeypatch.setattr(_i18n, "_locales_dir", lambda: tmp_path / "locales")
        result = _i18n.available_languages()
        assert result == ["en"]

    def test_at_least_three_languages(self):
        from bar_scheduler.core.i18n import available_languages

        assert len(available_languages()) >= 3


# ---------------------------------------------------------------------------
# TestSetLanguage
# ---------------------------------------------------------------------------


class TestSetLanguage:
    def test_set_known_language(self):
        from bar_scheduler.core.i18n import set_language, t

        set_language("ru")
        # Russian translation for menu.quit should differ from English
        assert t("menu.quit") != "menu.quit"

    def test_set_unknown_falls_back_to_en(self):
        from bar_scheduler.core import i18n as _i18n

        _i18n.set_language("xx_nonexistent")
        assert _i18n._current_lang == "en"

    def test_empty_string_falls_back_to_en(self):
        from bar_scheduler.core import i18n as _i18n

        _i18n.set_language("")
        assert _i18n._current_lang == "en"

    def test_language_persists_across_t_calls(self):
        from bar_scheduler.core.i18n import set_language, t

        set_language("zh")
        first = t("menu.quit")
        second = t("menu.quit")
        assert first == second

    def test_switching_back_to_en(self):
        from bar_scheduler.core.i18n import set_language, t

        en_quit = t("menu.quit")
        set_language("ru")
        ru_quit = t("menu.quit")
        set_language("en")
        back_en_quit = t("menu.quit")

        assert en_quit != ru_quit
        assert en_quit == back_en_quit

    def test_set_zh(self):
        from bar_scheduler.core import i18n as _i18n

        _i18n.set_language("zh")
        assert _i18n._current_lang == "zh"


# ---------------------------------------------------------------------------
# TestTranslationLookup
# ---------------------------------------------------------------------------


class TestTranslationLookup:
    def test_english_key_returns_value(self):
        from bar_scheduler.core.i18n import t

        val = t("menu.quit")
        assert val == "Quit"

    def test_russian_key_returns_russian(self):
        from bar_scheduler.core.i18n import set_language, t

        set_language("ru")
        val = t("menu.quit")
        assert val == "Выйти"

    def test_chinese_key_returns_chinese(self):
        from bar_scheduler.core.i18n import set_language, t

        set_language("zh")
        val = t("menu.quit")
        assert val == "退出"

    def test_missing_key_returns_key_itself(self):
        from bar_scheduler.core.i18n import t

        result = t("totally.nonexistent.key.xyz")
        assert result == "totally.nonexistent.key.xyz"

    def test_missing_ru_key_falls_back_to_en(self):
        """A key not in ru.yaml should fall back to the English value, not the key string."""
        from bar_scheduler.core import i18n as _i18n
        from bar_scheduler.core.i18n import set_language

        # Inject a fake key only in English catalog to test fallback
        _i18n._catalogs.clear()
        en_cat = _i18n._load_catalog("en")
        en_cat["_test_en_only"] = "English only value"

        set_language("ru")
        result = _i18n.t("_test_en_only")
        assert result == "English only value"

        # Clean up the injected key
        del en_cat["_test_en_only"]

    def test_varname_interpolation(self):
        from bar_scheduler.core.i18n import t

        result = t("error.profile_not_found", path="/tmp/test")
        assert "/tmp/test" in result
        assert "{path}" not in result

    def test_float_format_specifier(self):
        from bar_scheduler.core.i18n import t

        result = t("status.trend", slope=1.23456)
        assert "+1.23" in result
        assert "{slope" not in result

    def test_missing_kwargs_no_crash(self):
        """Calling t() with missing placeholders should not raise."""
        from bar_scheduler.core.i18n import t

        # Missing the 'path' argument; should return unformatted or key
        result = t("error.profile_not_found")  # no kwargs
        # Should return something without crashing
        assert isinstance(result, str)

    def test_rich_markup_preserved(self):
        from bar_scheduler.core.i18n import t

        result = t("app.tagline")
        assert "[bold cyan]" in result
        assert "[/bold cyan]" in result

    def test_catalog_cached(self):
        """YAML is loaded only once per language; second call returns same dict."""
        from bar_scheduler.core import i18n as _i18n

        _i18n._catalogs.clear()
        cat1 = _i18n._load_catalog("en")
        cat2 = _i18n._load_catalog("en")
        assert cat1 is cat2  # same object (cached)

    def test_language_isolation(self):
        """Setting ru, then en, produces correct results without state leak."""
        from bar_scheduler.core.i18n import set_language, t

        set_language("ru")
        ru_val = t("menu.quit")
        set_language("en")
        en_val = t("menu.quit")

        assert ru_val != en_val
        assert en_val == "Quit"

    def test_en_tagline_no_exercise(self):
        from bar_scheduler.core.i18n import t

        result = t("app.tagline")
        assert "bar-scheduler" in result
        assert "training planner" in result

    def test_en_tagline_with_exercise_interpolation(self):
        from bar_scheduler.core.i18n import t

        result = t("app.tagline_exercise", exercise_name="Pull-Up")
        assert "Pull-Up" in result

    def test_zh_tagline_contains_bar_scheduler(self):
        from bar_scheduler.core.i18n import set_language, t

        set_language("zh")
        result = t("app.tagline")
        assert "bar-scheduler" in result  # brand name always in Latin

    def test_multiline_value_preserved(self):
        from bar_scheduler.core.i18n import t

        # plan.baseline_prompt_intro has a leading \n
        result = t("plan.baseline_prompt_intro", exercise_name="Pull-Up")
        assert "Pull-Up" in result

    def test_positive_format_slope(self):
        from bar_scheduler.core.i18n import t

        result = t("status.trend", slope=-0.5)
        assert "-0.50" in result


# ---------------------------------------------------------------------------
# TestI18nIntegration
# ---------------------------------------------------------------------------


class TestI18nIntegration:
    def test_user_profile_default_language(self):
        from bar_scheduler.core.models import UserProfile

        profile = UserProfile(height_cm=180, sex="male")
        assert profile.language == "en"

    def test_user_profile_russian_language(self):
        from bar_scheduler.core.models import UserProfile

        profile = UserProfile(height_cm=180, sex="male", language="ru")
        assert profile.language == "ru"

    def test_user_profile_invalid_language_raises(self):
        from bar_scheduler.core.models import UserProfile

        with pytest.raises(ValueError, match="language"):
            UserProfile(height_cm=180, sex="male", language="")

    def test_serialise_en_language_omits_key(self):
        """When language='en', 'language' key should be absent from dict (backward compat)."""
        from bar_scheduler.core.models import UserProfile
        from bar_scheduler.io.serializers import user_profile_to_dict

        profile = UserProfile(height_cm=180, sex="male", language="en")
        d = user_profile_to_dict(profile)
        assert "language" not in d

    def test_serialise_ru_language_writes_key(self):
        from bar_scheduler.core.models import UserProfile
        from bar_scheduler.io.serializers import user_profile_to_dict

        profile = UserProfile(height_cm=180, sex="male", language="ru")
        d = user_profile_to_dict(profile)
        assert d["language"] == "ru"

    def test_deserialise_missing_language_defaults_to_en(self):
        """Old profile.json without 'language' key → backward compat, loads as 'en'."""
        from bar_scheduler.io.serializers import dict_to_user_profile

        d = {"height_cm": 180, "sex": "male", "preferred_days_per_week": 3}
        profile = dict_to_user_profile(d)
        assert profile.language == "en"

    def test_deserialise_ru_language(self):
        from bar_scheduler.io.serializers import dict_to_user_profile

        d = {"height_cm": 180, "sex": "male", "preferred_days_per_week": 3, "language": "ru"}
        profile = dict_to_user_profile(d)
        assert profile.language == "ru"

    def test_round_trip_language(self):
        from bar_scheduler.core.models import UserProfile
        from bar_scheduler.io.serializers import dict_to_user_profile, user_profile_to_dict

        original = UserProfile(height_cm=175, sex="female", language="zh")
        d = user_profile_to_dict(original)
        restored = dict_to_user_profile(d)
        assert restored.language == "zh"

    def test_round_trip_en_language_backward_compat(self):
        """'en' language omitted in dict; deserialised back as 'en'."""
        from bar_scheduler.core.models import UserProfile
        from bar_scheduler.io.serializers import dict_to_user_profile, user_profile_to_dict

        original = UserProfile(height_cm=175, sex="male", language="en")
        d = user_profile_to_dict(original)
        assert "language" not in d
        restored = dict_to_user_profile(d)
        assert restored.language == "en"

    def test_set_language_before_t_calls(self):
        """set_language must be called before t() for non-English output."""
        from bar_scheduler.core.i18n import set_language, t

        set_language("ru")
        # Russian "Quit" should be Cyrillic
        assert t("menu.quit") == "Выйти"

    def test_t_fallback_chain_key_itself(self):
        """Completely unknown key returns the key string itself."""
        from bar_scheduler.core.i18n import set_language, t

        set_language("ru")
        result = t("__no_such_key_ever__")
        assert result == "__no_such_key_ever__"

    def test_zh_error_profile_not_found_no_placeholder_in_output(self):
        """zh translation of error.profile_not_found should interpolate {path}."""
        from bar_scheduler.core.i18n import set_language, t

        set_language("zh")
        result = t("error.profile_not_found", path="/some/path")
        assert "/some/path" in result
        assert "{path}" not in result

    def test_available_languages_returns_three(self):
        from bar_scheduler.core.i18n import available_languages

        langs = available_languages()
        assert "en" in langs
        assert "ru" in langs
        assert "zh" in langs
