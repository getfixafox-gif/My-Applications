"""JSON settings storage with validation and crash-safe writes."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from app.settings.defaults import (
    BACKUP_INTERVALS,
    DEFAULT_SETTINGS,
    LANGUAGES,
    LOG_LEVELS,
    SORT_MODES,
    THEMES,
)
from app.utils.logger import get_logger

logger = get_logger("settings")


def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _as_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _as_choice(value, choices, default):
    return value if value in choices else default


def _as_optional_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class ConfigManager:
    """Loads, validates and persists :class:`DEFAULT_SETTINGS`."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data: dict = dict(DEFAULT_SETTINGS)

    # -- loading ---------------------------------------------------------
    def load(self) -> dict:
        with self._lock:
            raw: dict = {}
            if self.path.exists():
                try:
                    with self.path.open("r", encoding="utf-8") as handle:
                        loaded = json.load(handle)
                    if isinstance(loaded, dict):
                        raw = loaded
                    else:
                        raise ValueError("settings root is not an object")
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    logger.warning("Cannot read settings (%s); using defaults", exc)
                    self._quarantine_broken_file()
            data = dict(DEFAULT_SETTINGS)
            data.update(raw)
            self._data = self._sanitize(data)
            logger.debug("Settings loaded from %s", self.path)
            return dict(self._data)

    def _quarantine_broken_file(self) -> None:
        try:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            broken = self.path.with_name(f"settings.broken-{stamp}.json")
            os.replace(self.path, broken)
            logger.warning("Broken settings file moved to %s", broken)
        except OSError as exc:
            logger.error("Cannot move broken settings file: %s", exc)

    @staticmethod
    def _sanitize(data: dict) -> dict:
        clean = dict(DEFAULT_SETTINGS)
        clean.update({k: v for k, v in data.items() if k not in DEFAULT_SETTINGS})
        clean["theme"] = _as_choice(data.get("theme"), THEMES, DEFAULT_SETTINGS["theme"])
        clean["language"] = _as_choice(
            data.get("language"), LANGUAGES, DEFAULT_SETTINGS["language"]
        )
        clean["autobackup_enabled"] = _as_bool(
            data.get("autobackup_enabled"), DEFAULT_SETTINGS["autobackup_enabled"]
        )
        interval = _as_int(
            data.get("autobackup_interval_hours"),
            DEFAULT_SETTINGS["autobackup_interval_hours"],
            1,
            8760,
        )
        if interval not in BACKUP_INTERVALS:
            # Snap to the nearest supported interval.
            interval = min(BACKUP_INTERVALS, key=lambda item: abs(item - interval))
        clean["autobackup_interval_hours"] = interval
        clean["autobackup_keep"] = _as_int(
            data.get("autobackup_keep"), DEFAULT_SETTINGS["autobackup_keep"], 1, 100
        )
        clean["log_level"] = _as_choice(
            str(data.get("log_level", "")).upper(), LOG_LEVELS, DEFAULT_SETTINGS["log_level"]
        )
        clean["sort_mode"] = _as_choice(
            data.get("sort_mode"), SORT_MODES, DEFAULT_SETTINGS["sort_mode"]
        )
        clean["last_backup_at"] = _as_optional_str(data.get("last_backup_at"))
        clean["last_backup_path"] = _as_optional_str(data.get("last_backup_path"))
        clean["window_geometry"] = _as_optional_str(data.get("window_geometry"))
        clean["splitter_state"] = _as_optional_str(data.get("splitter_state"))
        return clean

    # -- access ----------------------------------------------------------
    def as_dict(self) -> dict:
        with self._lock:
            return dict(self._data)

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        with self._lock:
            candidate = dict(self._data)
            candidate[key] = value
            self._data = self._sanitize(candidate)
            self.save()

    def update(self, values: dict) -> None:
        with self._lock:
            candidate = dict(self._data)
            candidate.update(values)
            self._data = self._sanitize(candidate)
            self.save()

    def save(self) -> bool:
        """Atomically persist settings. Returns ``False`` when writing fails."""
        with self._lock:
            tmp = self.path.with_suffix(".json.tmp")
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with tmp.open("w", encoding="utf-8", newline="\n") as handle:
                    json.dump(self._data, handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, self.path)
                return True
            except OSError as exc:
                logger.error("Cannot save settings: %s", exc)
                try:
                    if tmp.exists():
                        tmp.unlink()
                except OSError:
                    pass
                return False
