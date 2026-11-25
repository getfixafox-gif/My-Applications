"""Small utility functions shared across layers."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.i18n import language


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string with timezone information."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_datetime(value: str | None) -> str:
    """Format an ISO timestamp for the UI in local time."""
    parsed = parse_iso(value)
    if parsed is None:
        return ""
    local = parsed.astimezone()
    if language() == "en":
        return local.strftime("%Y-%m-%d %H:%M")
    return local.strftime("%d.%m.%Y %H:%M")


def format_size(size: int) -> str:
    """Human readable byte size using binary units."""
    value = float(max(0, int(size)))
    units = ("Б", "КБ", "МБ", "ГБ", "ТБ")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "Б":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}".replace(".", ",") if language() == "ru" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} ТБ"


def sha256_file(path: Path, chunk_size: int = 1024 * 256) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
