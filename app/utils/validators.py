"""Validation and normalisation of user input."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

MAX_TITLE = 200
MAX_TYPE = 64
MAX_DESCRIPTION = 20_000
MAX_TAG = 40
MAX_CATEGORY = 60
MAX_LINK_TITLE = 120
MAX_URL = 2048
MAX_LINKS = 500

ALLOWED_SCHEMES = {"http", "https", "ftp", "mailto"}
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")
_WHITESPACE_RE = re.compile(r"\s")


class ValidationError(ValueError):
    """Raised when user input cannot be stored."""


def _clean_text(raw: str | None) -> str:
    if raw is None:
        return ""
    return str(raw).replace("\x00", "").strip()


def clean_title(raw: str | None) -> str:
    title = _clean_text(raw)
    if not title:
        raise ValidationError("Название не может быть пустым")
    if len(title) > MAX_TITLE:
        raise ValidationError(f"Название не может быть длиннее {MAX_TITLE} символов")
    return title


def clean_type(raw: str | None) -> str:
    value = _clean_text(raw)
    if len(value) > MAX_TYPE:
        raise ValidationError(f"Тип не может быть длиннее {MAX_TYPE} символов")
    return value


def clean_description(raw: str | None) -> str:
    value = "" if raw is None else str(raw).replace("\x00", "").strip()
    if len(value) > MAX_DESCRIPTION:
        raise ValidationError(f"Описание не может быть длиннее {MAX_DESCRIPTION} символов")
    return value


def clean_tag_name(raw: str | None) -> str:
    value = _clean_text(raw).lstrip("#").strip()
    value = re.sub(r"\s+", " ", value)
    if not value:
        raise ValidationError("Название тега не может быть пустым")
    if len(value) > MAX_TAG:
        raise ValidationError(f"Название тега не может быть длиннее {MAX_TAG} символов")
    return value


def clean_category_name(raw: str | None) -> str:
    value = _clean_text(raw)
    value = re.sub(r"\s+", " ", value)
    if not value:
        raise ValidationError("Название категории не может быть пустым")
    if len(value) > MAX_CATEGORY:
        raise ValidationError(f"Название категории не может быть длиннее {MAX_CATEGORY} символов")
    return value


def clean_link_title(raw: str | None, fallback: str = "") -> str:
    value = _clean_text(raw)
    if len(value) > MAX_LINK_TITLE:
        raise ValidationError(f"Название ссылки не может быть длиннее {MAX_LINK_TITLE} символов")
    return value or fallback


def normalize_url(raw: str | None) -> str:
    """Validate a link and return a normalised absolute URL.

    A missing scheme is resolved as ``https://`` when the input looks like a
    host name (e.g. ``example.org/path``). Unsupported or unsafe schemes are
    rejected.
    """
    url = _clean_text(raw)
    if not url:
        raise ValidationError("Адрес ссылки не может быть пустым")
    if len(url) > MAX_URL:
        raise ValidationError("Адрес ссылки слишком длинный")
    if _WHITESPACE_RE.search(url):
        raise ValidationError("Адрес ссылки не должен содержать пробелы")

    has_scheme = bool(_SCHEME_RE.match(url))
    if not has_scheme:
        url = "https://" + url

    scheme = url.split(":", 1)[0].lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValidationError(
            "Поддерживаются только ссылки http, https, ftp и mailto"
        )

    if scheme == "mailto":
        address = url[7:].split("?", 1)[0]
        if not address or "@" not in address or "@" == address[0]:
            raise ValidationError("Некорректный адрес электронной почты")
        return url

    parts = urlsplit(url)
    if not parts.netloc:
        raise ValidationError("В ссылке отсутствует адрес сайта")
    hostname = parts.hostname
    if not hostname:
        raise ValidationError("Некорректный адрес сайта")
    if hostname.startswith(".") or hostname.endswith(".") or ".." in hostname:
        raise ValidationError("Некорректный адрес сайта")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValidationError("Некорректный порт в ссылке") from exc
    if port is not None and not (0 < port < 65536):
        raise ValidationError("Некорректный порт в ссылке")
    return url


def is_valid_url(raw: str | None) -> bool:
    try:
        normalize_url(raw)
    except ValidationError:
        return False
    return True


def validate_link_pair(title: str | None, url: str | None) -> tuple[str, str]:
    """Validate and normalise a (title, url) pair."""
    normalized = normalize_url(url)
    final_title = clean_link_title(title, fallback=normalized)
    return final_title, normalized
