"""
turzx/i18n.py — Internationalization skeleton
===============================================
Provides a ``_()`` function that currently returns strings unchanged.
All user-facing UI labels should use ``_("text")`` so a future
translation backend (gettext, JSON, etc.) can be plugged in.

Usage::

    from turzx.i18n import _
    label = _("CPU Usage")
"""

from __future__ import annotations

# Active language code (ISO 639-1).  "en" is the built-in default.
_current_lang: str = "en"

# Translation tables can be loaded here in the future.
# Format: { "es": { "CPU Usage": "Uso de CPU", ... }, ... }
_translations: dict[str, dict[str, str]] = {}


def _(text: str) -> str:
    """Translate *text* into the current language.

    Returns the original string when no translation is available.
    """
    if _current_lang == "en":
        return text
    table = _translations.get(_current_lang)
    if table:
        return table.get(text, text)
    return text


def set_language(lang: str) -> None:
    """Switch the active language."""
    global _current_lang
    _current_lang = lang


def get_language() -> str:
    """Return the current language code."""
    return _current_lang


def load_translations(lang: str, table: dict[str, str]) -> None:
    """Register a translation table for *lang*."""
    _translations[lang] = table
