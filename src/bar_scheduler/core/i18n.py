"""
Internationalization (i18n) support for bar-scheduler.

Global state is appropriate here: the CLI is single-threaded and the
language is set once in main_callback before any command logic runs.

Priority for language selection (highest first):
  1. --lang flag (explicit CLI override)
  2. profile.json "language" field
  3. "en" fallback

Usage:
    from bar_scheduler.core.i18n import t, set_language, available_languages
    set_language("ru")
    print(t("menu.quit"))                                 # "Выйти"
    print(t("error.profile_not_found", path="/tmp/p"))   # interpolated
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Module-level state (single-threaded CLI — global state is intentional)
# ---------------------------------------------------------------------------
_current_lang: str = "en"
_catalogs: dict[str, dict] = {}   # cache: {lang_code: flat_dict}


def _locales_dir() -> Path:
    """Return the bundled locales/ directory (src/bar_scheduler/locales/)."""
    return Path(__file__).parent.parent / "locales"


def available_languages() -> list[str]:
    """
    Scan locales/ for .yaml files and return language codes.

    Returns:
        Sorted list of language code strings, e.g. ["en", "ru", "zh"].
        Always contains at least ["en"].
    """
    d = _locales_dir()
    if not d.is_dir():
        return ["en"]
    codes = sorted(p.stem for p in d.glob("*.yaml"))
    return codes if codes else ["en"]


def _load_catalog(lang: str) -> dict:
    """
    Load and cache the flat key→string dict for the given language.

    On any failure (missing file, parse error) returns an empty dict so
    the fallback chain in t() handles the miss gracefully.
    """
    if lang in _catalogs:
        return _catalogs[lang]
    try:
        import yaml  # PyYAML is a hard dependency
        path = _locales_dir() / f"{lang}.yaml"
        if not path.exists():
            _catalogs[lang] = {}
            return {}
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        catalog = data if isinstance(data, dict) else {}
        _catalogs[lang] = catalog
        return catalog
    except Exception:
        _catalogs[lang] = {}
        return {}


def set_language(lang: str) -> None:
    """
    Set the active language for all subsequent t() calls.

    If lang has no matching .yaml file, falls back silently to "en".

    Args:
        lang: Language code, e.g. "en", "ru", "zh".
    """
    global _current_lang
    if lang and isinstance(lang, str) and lang in available_languages():
        _current_lang = lang
    else:
        _current_lang = "en"


def t(key: str, **kwargs: object) -> str:
    """
    Look up a translation key and interpolate named placeholders.

    Fallback chain:
      1. Current language catalog
      2. "en" catalog (if current language is not "en")
      3. key itself (always returns something)

    Placeholders use {varname} syntax, interpolated via str.format_map().
    Rich markup [tags] are preserved verbatim (no collision with {varname}).

    Args:
        key:     Dotted key, e.g. "error.profile_not_found"
        **kwargs: Named values for placeholder substitution

    Returns:
        Translated and interpolated string, or key itself if not found.

    Example:
        t("error.profile_not_found", path="/home/user/.bar-scheduler")
        → "Profile not found: /home/user/.bar-scheduler"
    """
    # Try current language
    catalog = _load_catalog(_current_lang)
    text = catalog.get(key)

    # Fallback to English if current lang is not English and key is missing
    if text is None and _current_lang != "en":
        en_catalog = _load_catalog("en")
        text = en_catalog.get(key)

    # Final fallback: return the key itself
    if text is None:
        return key

    # Interpolate {varname} placeholders; leave Rich [tags] untouched
    if kwargs:
        try:
            text = text.format_map(kwargs)
        except (KeyError, ValueError):
            pass  # Return unformatted text rather than crash

    return str(text)
