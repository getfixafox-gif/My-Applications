"""Filesystem helpers for the application data directory."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.paths import AppPaths
from app.utils.logger import get_logger

logger = get_logger("files")


class FileManager:
    """Safe file operations restricted to the application data directory."""

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def is_inside_storage(self, path: str | Path) -> bool:
        try:
            return Path(path).resolve().is_relative_to(self.paths.root)
        except (OSError, ValueError):
            return False

    def ensure_storage(self) -> None:
        self.paths.ensure()

    @staticmethod
    def free_space(path: str | Path) -> int:
        try:
            return shutil.disk_usage(str(path)).free
        except OSError:
            return 0

    def has_free_space(self, path: str | Path, required_bytes: int) -> bool:
        free = self.free_space(path)
        return free == 0 or free > required_bytes

    def copy_file(self, source: str | Path, target: str | Path) -> Path:
        src = Path(source)
        dst = Path(target)
        if not src.is_file():
            raise FileNotFoundError(f"Файл не найден: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".tmp")
        try:
            shutil.copyfile(src, tmp)
            tmp.replace(dst)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
        return dst
