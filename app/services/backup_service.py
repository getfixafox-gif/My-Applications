"""Automatic and manual backup orchestration (no UI dependencies)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.events import BACKUP_FINISHED, bus
from app.settings.config_manager import ConfigManager
from app.storage.backup_manager import BackupError, BackupManager
from app.utils.helpers import parse_iso, utc_now_iso
from app.utils.logger import get_logger

logger = get_logger("backup_service")


class BackupService:
    """Decides *when* to back up; :class:`BackupManager` does the work."""

    def __init__(self, manager: BackupManager, config: ConfigManager) -> None:
        self.manager = manager
        self.config = config

    # -- automatic -------------------------------------------------------
    def is_due(self) -> bool:
        if not self.config.get("autobackup_enabled", True):
            return False
        hours = int(self.config.get("autobackup_interval_hours", 24) or 24)
        last = parse_iso(self.config.get("last_backup_at"))
        if last is None:
            return True
        return datetime.now(timezone.utc) - last >= timedelta(hours=hours)

    def next_run_at(self) -> datetime | None:
        if not self.config.get("autobackup_enabled", True):
            return None
        hours = int(self.config.get("autobackup_interval_hours", 24) or 24)
        last = parse_iso(self.config.get("last_backup_at"))
        if last is None:
            return datetime.now(timezone.utc)
        return last + timedelta(hours=hours)

    def run_auto_backup(self) -> Path | None:
        """Create a snapshot when one is due. Returns the file path or ``None``."""
        if not self.is_due():
            return None
        try:
            path = self.manager.create_database_backup(prefix="auto")
        except BackupError as exc:
            logger.error("Automatic backup failed: %s", exc)
            bus.emit(BACKUP_FINISHED, automatic=True, success=False, message=str(exc))
            return None
        keep = int(self.config.get("autobackup_keep", 10) or 10)
        self.manager.rotate_auto_backups(keep)
        self.config.update(
            {"last_backup_at": utc_now_iso(), "last_backup_path": str(path)}
        )
        logger.info("Automatic backup created: %s", path)
        bus.emit(BACKUP_FINISHED, automatic=True, success=True, path=str(path))
        return path

    # -- manual ----------------------------------------------------------
    def create_manual_backup(self, target: str | Path | None = None, progress=None) -> Path:
        path = self.manager.create_archive(target, progress=progress)
        self.config.update(
            {"last_backup_at": utc_now_iso(), "last_backup_path": str(path)}
        )
        bus.emit(BACKUP_FINISHED, automatic=False, success=True, path=str(path))
        return path

    def export_archive(self, target: str | Path, progress=None) -> Path:
        return self.manager.export_copy(target)

    def inspect(self, source: str | Path):
        return self.manager.inspect_archive(source)

    def restore(self, source: str | Path, *, mode: str = "merge", progress=None):
        result = self.manager.restore(source, mode=mode, progress=progress)
        bus.emit(BACKUP_FINISHED, automatic=False, success=True, path=str(source))
        return result

    def list_auto_backups(self) -> list[Path]:
        return self.manager.list_auto_backups()

    def cleanup_auto(self) -> list[Path]:
        keep = int(self.config.get("autobackup_keep", 10) or 10)
        return self.manager.rotate_auto_backups(keep)
