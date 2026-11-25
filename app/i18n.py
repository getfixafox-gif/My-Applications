"""Minimal runtime translation helper (Russian is the default language)."""

from __future__ import annotations

LANGUAGES = ("ru", "en")
LANGUAGE_TITLES = {"ru": "Русский", "en": "English"}

_current = "ru"


def set_language(lang: str | None) -> str:
    """Set the active UI language. Unknown values fall back to Russian."""
    global _current
    _current = lang if lang in LANGUAGES else "ru"
    return _current


def language() -> str:
    return _current


def tr(ru: str, en: str | None = None) -> str:
    """Return the text for the active language.

    Russian is the source language, so call sites always provide it. English
    text is optional: when omitted the Russian string is returned unchanged.
    """
    if _current == "ru":
        return ru
    return en if en is not None else ru


def plural_ru(number: int, one: str, few: str, many: str) -> str:
    n = abs(int(number)) % 100
    if 11 <= n <= 19:
        return many
    n = n % 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def entries_label(count: int) -> str:
    """Human readable entry count: ``12 записей`` / ``12 entries``."""
    if _current == "en":
        return f"{count} entr{'y' if count == 1 else 'ies'}"
    return f"{count} {plural_ru(count, 'запись', 'записи', 'записей')}"


def links_label(count: int) -> str:
    if _current == "en":
        return f"{count} link{'s' if count != 1 else ''}"
    return f"{count} {plural_ru(count, 'ссылка', 'ссылки', 'ссылок')}"


def tag_count_label(count: int) -> str:
    if _current == "en":
        return f"{count} tag{'s' if count != 1 else ''}"
    return f"{count} {plural_ru(count, 'тег', 'тега', 'тегов')}"
