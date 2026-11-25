"""Application data directories (Windows / Linux, offline only)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "MyApplications"


def default_data_dir() -> Path:
    """Return the platform-specific default data directory."""
    override = os.environ.get("MY_APPLICATIONS_HOME")
    if override:
        return Path(override).expanduser()
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_DIR_NAME
        return Path.home() / "AppData" / "Roaming" / APP_DIR_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg).expanduser() / APP_DIR_NAME
    return Path.home() / ".local" / "share" / APP_DIR_NAME


class AppPaths:
    """Every filesystem location used by the application.

    Layout::

        <root>/database.db
        <root>/Images/entries/...
        <root>/Images/thumbnails/...
        <root>/Backups/...
        <root>/Backups/auto/...
        <root>/Logs/...
        <root>/config/settings.json
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root).expanduser().resolve() if root else default_data_dir()

    # -- directories -----------------------------------------------------
    @property
    def database_file(self) -> Path:
        return self.root / "database.db"

    @property
    def images_dir(self) -> Path:
        return self.root / "Images"

    @property
    def entries_images_dir(self) -> Path:
        return self.images_dir / "entries"

    @property
    def thumbnails_dir(self) -> Path:
        return self.images_dir / "thumbnails"

    @property
    def backups_dir(self) -> Path:
        return self.root / "Backups"

    @property
    def auto_backups_dir(self) -> Path:
        return self.backups_dir / "auto"

    @property
    def logs_dir(self) -> Path:
        return self.root / "Logs"

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def work_dir(self) -> Path:
        return self.root / ".work"

    def ensure(self) -> "AppPaths":
        """Create every directory required for normal operation."""
        for directory in (
            self.root,
            self.images_dir,
            self.entries_images_dir,
            self.thumbnails_dir,
            self.backups_dir,
            self.auto_backups_dir,
            self.logs_dir,
            self.config_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    # -- image helpers ---------------------------------------------------
    def _safe_join(self, base: Path, relative: str) -> Path:
        if not relative:
            raise ValueError("Empty relative path")
        rel = Path(relative)
        if rel.is_absolute() or rel.drive or ".." in rel.parts:
            raise ValueError(f"Unsafe relative path: {relative!r}")
        candidate = (base / rel).resolve()
        if not candidate.is_relative_to(base.resolve()):
            raise ValueError(f"Path escapes data directory: {relative!r}")
        return candidate

    def image_file(self, relative: str) -> Path:
        """Absolute path of an image stored relative to ``Images/``."""
        return self._safe_join(self.images_dir, relative)

    def image_relative(self, path: Path) -> str:
        """Convert an absolute image path into a path relative to ``Images/``."""
        return path.resolve().relative_to(self.images_dir.resolve()).as_posix()

    def thumbnail_relative(self, image_relative: str) -> str:
        rel = Path(image_relative)
        parts = list(rel.parts)
        if len(parts) >= 2 and parts[0] == "entries":
            parts[0] = "thumbnails"
        else:
            parts = ["thumbnails", rel.name]
        return Path(*parts).as_posix()

    def thumbnail_file(self, image_relative: str) -> Path:
        return self.image_file(self.thumbnail_relative(image_relative))

    # -- diagnostics -----------------------------------------------------
    @staticmethod
    def _dir_size(path: Path) -> int:
        total = 0
        if not path.exists():
            return 0
        for item in path.rglob("*"):
            try:
                if item.is_file():
                    total += item.stat().st_size
            except OSError:
                continue
        return total

    def _file_size(self, path: Path) -> int:
        try:
            return path.stat().st_size if path.is_file() else 0
        except OSError:
            return 0

    def storage_usage(self) -> dict[str, int]:
        """Return sizes (bytes) of the storage areas."""
        db_size = self._file_size(self.database_file)
        wal = self._file_size(Path(str(self.database_file) + "-wal"))
        shm = self._file_size(Path(str(self.database_file) + "-shm"))
        usage = {
            "database": db_size + wal + shm,
            "images": self._dir_size(self.images_dir),
            "backups": self._dir_size(self.backups_dir),
            "logs": self._dir_size(self.logs_dir),
        }
        usage["total"] = sum(usage.values())
        return usage
