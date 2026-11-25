"""Default application settings and allowed values."""

from __future__ import annotations

DEFAULT_SETTINGS: dict = {
    "theme": "dark",
    "language": "ru",
    "autobackup_enabled": True,
    "autobackup_interval_hours": 24,
    "autobackup_keep": 10,
    "log_level": "INFO",
    "last_backup_at": None,
    "last_backup_path": None,
    "window_geometry": None,
    "splitter_state": None,
    "sort_mode": "updated_desc",
}

THEMES = ("dark", "light")
LANGUAGES = ("ru", "en")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
#: Allowed automatic backup intervals, in hours.
BACKUP_INTERVALS = (6, 12, 24, 72, 168)
SORT_MODES = (
    "updated_desc",
    "updated_asc",
    "title_asc",
    "title_desc",
    "created_desc",
    "created_asc",
)
