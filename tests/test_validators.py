"""Tests for validation helpers."""

from __future__ import annotations

import pytest

from app.utils.validators import (
    ValidationError,
    clean_category_name,
    clean_description,
    clean_tag_name,
    clean_title,
    is_valid_url,
    normalize_url,
    validate_link_pair,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("example.com", "https://example.com"),
        ("https://example.com/path?x=1", "https://example.com/path?x=1"),
        ("http://localhost:8080", "http://localhost:8080"),
        ("  https://a.b  ", "https://a.b"),
        ("mailto:user@example.com", "mailto:user@example.com"),
        ("ftp://files.example.com/file.zip", "ftp://files.example.com/file.zip"),
        ("sub.domain.example.org/a/b", "https://sub.domain.example.org/a/b"),
    ],
)
def test_normalize_url_ok(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "javascript:alert(1)",
        "data:text/html,<script>",
        "file:///etc/passwd",
        "https://exa mple.com",
        "https://",
        "mailto:not-an-email",
        "https://example.com:99999",
        "https://..bad..",
    ],
)
def test_normalize_url_rejects(raw: str) -> None:
    with pytest.raises(ValidationError):
        normalize_url(raw)


def test_is_valid_url() -> None:
    assert is_valid_url("example.com")
    assert not is_valid_url("javascript:void(0)")


def test_validate_link_pair_uses_url_as_title() -> None:
    title, url = validate_link_pair("", "example.com/x")
    assert title == "https://example.com/x"
    assert url == "https://example.com/x"


def test_clean_title() -> None:
    assert clean_title("  My App  ") == "My App"
    with pytest.raises(ValidationError):
        clean_title("   ")
    with pytest.raises(ValidationError):
        clean_title("x" * 500)


def test_clean_title_removes_nul() -> None:
    assert clean_title("a\x00b") == "ab"


def test_clean_description_keeps_newlines() -> None:
    assert clean_description("  a\nb\n  ") == "a\nb"


def test_clean_tag_name_strips_hash() -> None:
    assert clean_tag_name("#graphics") == "graphics"
    assert clean_tag_name("  two   words ") == "two words"
    with pytest.raises(ValidationError):
        clean_tag_name("  ")


def test_clean_category_name() -> None:
    assert clean_category_name("  Dev  Tools ") == "Dev Tools"
    with pytest.raises(ValidationError):
        clean_category_name("")
