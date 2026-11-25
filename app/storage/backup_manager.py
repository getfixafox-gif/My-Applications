"""Backup / export / import archives (ZIP with JSON payload)."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.database.connection import Database
from app.database.repository import Repository
from app.paths import AppPaths
from app.utils.helpers import new_id, sha256_file, utc_now_iso
from app.utils.logger import get_logger
from app.version import (
    APP_VERSION,
    ARCHIVE_FORMAT,
    ARCHIVE_FORMAT_VERSION,
    DB_SCHEMA_VERSION,
)

logger = get_logger("backup")

MAX_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024  # 4 GiB safety limit
MAX_ARCHIVE_ENTRIES = 200_000
MAX_JSON_BYTES = 256 * 1024 * 1024


class BackupError(RuntimeError):
    """Raised when a backup or archive operation fails."""


class ImportConflictError(BackupError):
    """Raised when an archive cannot be imported as-is."""


@dataclass(slots=True)
class ArchiveInspection:
    """Result of validating an archive before importing it."""

    path: Path
    format_version: int
    app_version: str
    created_at: str
    counts: dict[str, int] = field(default_factory=dict)
    conflicts: int = 0
    images: dict[str, str] = field(default_factory=dict)  # relative path -> sha256
    payload: dict | None = None


ProgressCallback = Callable[[str, int, int], None]


def _human_now() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def default_backup_name() -> str:
    return f"MyApplications_Backup_{_human_now()}.zip"


def _safe_member_name(name: str) -> bool:
    if not name or name.startswith("/") or "\\" in name:
        return False
    parts = name.split("/")
    return all(part not in ("", ".", "..") for part in parts) and not (
        len(parts[0]) == 2 and parts[0][1] == ":"
    )


class BackupManager:
    def __init__(
        self,
        database: Database,
        repository: Repository,
        paths: AppPaths,
    ) -> None:
        self.db = database
        self.repo = repository
        self.paths = paths

    # ------------------------------------------------------------------
    # Building archives
    # ------------------------------------------------------------------
    def _collect_payload(self) -> dict:
        entries: list[dict] = []
        for row in self.repo.list_entries():
            entry = self.repo.get_entry(row.id)
            if entry is None:
                continue
            entries.append(
                {
                    "id": entry.id,
                    "title": entry.title,
                    "description": entry.description,
                    "type": entry.type,
                    "category_id": entry.category_id,
                    "image": entry.image_path,
                    "created_at": entry.created_at,
                    "updated_at": entry.updated_at,
                    "links": [
                        {
                            "id": link.id,
                            "title": link.title,
                            "url": link.url,
                            "position": link.position,
                        }
                        for link in entry.links
                    ],
                    "tags": [tag.id for tag in entry.tags],
                }
            )
        categories = [
            {"id": item.id, "name": item.name, "created_at": item.created_at}
            for item in self.repo.list_categories()
        ]
        tags = [
            {"id": item.id, "name": item.name, "created_at": item.created_at}
            for item in self.repo.list_tags()
        ]
        return {
            "format": ARCHIVE_FORMAT,
            "format_version": ARCHIVE_FORMAT_VERSION,
            "app_version": APP_VERSION,
            "schema_version": DB_SCHEMA_VERSION,
            "created_at": utc_now_iso(),
            "entries": entries,
            "categories": categories,
            "tags": tags,
        }

    def create_archive(
        self,
        target: str | Path | None = None,
        *,
        progress: ProgressCallback | None = None,
    ) -> Path:
        """Write a portable ZIP archive to ``target``."""
        target_path = (
            Path(target) if target else self.paths.backups_dir / default_backup_name()
        )
        if target_path.suffix.lower() != ".zip":
            target_path = target_path.with_suffix(".zip")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_zip = target_path.with_name(target_path.name + ".part")

        payload = self._collect_payload()
        images: list[tuple[Path, str]] = []
        for entry in payload["entries"]:
            relative = entry.get("image")
            if not relative:
                continue
            source = self.paths.image_file(relative)
            if source.is_file():
                images.append((source, f"Images/{Path(relative).name}"))
                entry["image"] = Path(relative).name
            else:
                logger.warning("Image missing for entry %s: %s", entry["id"], relative)
                entry["image"] = None

        metadata = {
            "app_name": "My Applications",
            "app_version": APP_VERSION,
            "schema_version": DB_SCHEMA_VERSION,
            "format": ARCHIVE_FORMAT,
            "format_version": ARCHIVE_FORMAT_VERSION,
            "created_at": payload["created_at"],
            "counts": {
                "entries": len(payload["entries"]),
                "categories": len(payload["categories"]),
                "tags": len(payload["tags"]),
                "links": sum(len(item["links"]) for item in payload["entries"]),
                "images": len(images),
            },
        }

        try:
            with zipfile.ZipFile(
                temp_zip, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
            ) as archive:
                archive.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "format": ARCHIVE_FORMAT,
                            "format_version": ARCHIVE_FORMAT_VERSION,
                            "files": ["database.json", "metadata/backup_info.json"],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
                archive.writestr(
                    "database.json", json.dumps(payload, ensure_ascii=False, indent=2)
                )
                archive.writestr(
                    "metadata/backup_info.json",
                    json.dumps(metadata, ensure_ascii=False, indent=2),
                )
                total = len(images)
                for index, (source, arcname) in enumerate(images, start=1):
                    archive.write(source, arcname)
                    if progress:
                        progress("images", index, total)
            temp_zip.replace(target_path)
        except (OSError, zipfile.BadZipFile, ValueError) as exc:
            try:
                if temp_zip.exists():
                    temp_zip.unlink()
            except OSError:
                pass
            raise BackupError(f"Не удалось создать резервную копию: {exc}") from exc

        logger.info("Archive created: %s (%s entries)", target_path, len(payload["entries"]))
        return target_path

    # ------------------------------------------------------------------
    # SQLite snapshots (automatic backups)
    # ------------------------------------------------------------------
    def create_database_backup(self, prefix: str = "auto") -> Path:
        """Consistent ``.db`` snapshot used for automatic backups."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = self.paths.auto_backups_dir / f"{prefix}-{stamp}.db"
        # Never overwrite an existing snapshot, even with equal timestamps.
        counter = 1
        while target.exists():
            target = self.paths.auto_backups_dir / f"{prefix}-{stamp}-{counter}.db"
            counter += 1
        try:
            self.db.checkpoint()
            self.db.backup_to(target)
        except (sqlite3.Error, OSError) as exc:
            try:
                if target.exists():
                    target.unlink()
            except OSError:
                pass
            raise BackupError(f"Не удалось создать резервную копию базы: {exc}") from exc
        logger.info("Database snapshot created: %s", target)
        return target

    def rotate_auto_backups(self, keep: int) -> list[Path]:
        """Delete the oldest snapshots beyond ``keep``."""
        keep = max(1, int(keep))
        removed: list[Path] = []
        if not self.paths.auto_backups_dir.exists():
            return removed
        snapshots = sorted(
            self.paths.auto_backups_dir.glob("*.db"),
            key=lambda path: path.stat().st_mtime,
        )
        for path in snapshots[: max(0, len(snapshots) - keep)]:
            try:
                path.unlink()
                removed.append(path)
            except OSError as exc:
                logger.warning("Cannot remove old backup %s: %s", path, exc)
        return removed

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def inspect_archive(self, source: str | Path) -> ArchiveInspection:
        """Validate an archive without touching current data."""
        path = Path(source)
        if not path.is_file():
            raise BackupError("Файл резервной копии не найден")
        try:
            with zipfile.ZipFile(path) as archive:
                self._validate_zip_structure(archive)
                payload = self._read_payload(archive)
                metadata = self._read_metadata(archive)
                images = self._collect_image_hashes(archive, payload)
        except zipfile.BadZipFile as exc:
            raise BackupError("Архив повреждён или не является ZIP-файлом") from exc
        except (OSError, ValueError) as exc:
            raise BackupError(f"Не удалось прочитать архив: {exc}") from exc

        existing_ids = {row.id for row in self.repo.list_entries()}
        conflicts = sum(1 for entry in payload["entries"] if entry["id"] in existing_ids)
        counts = {
            "entries": len(payload["entries"]),
            "categories": len(payload["categories"]),
            "tags": len(payload["tags"]),
            "links": sum(len(item.get("links", [])) for item in payload["entries"]),
            "images": len(images),
        }
        return ArchiveInspection(
            path=path,
            format_version=int(payload.get("format_version", 0)),
            app_version=str(payload.get("app_version", "")),
            created_at=str(metadata.get("created_at") or payload.get("created_at") or ""),
            counts=counts,
            conflicts=conflicts,
            images=images,
            payload=payload,
        )

    @staticmethod
    def _validate_zip_structure(archive: zipfile.ZipFile) -> None:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise BackupError("Архив содержит слишком много файлов")
        total = 0
        names: set[str] = set()
        for info in infos:
            if not _safe_member_name(info.filename):
                raise BackupError(f"Небезопасный путь в архиве: {info.filename}")
            if info.filename in names:
                raise BackupError(f"Дублирующийся файл в архиве: {info.filename}")
            names.add(info.filename)
            total += max(0, info.file_size)
            if total > MAX_UNCOMPRESSED_BYTES:
                raise BackupError("Архив слишком большой после распаковки")
        for required in ("manifest.json", "database.json"):
            if required not in names:
                raise BackupError(f"В архиве отсутствует обязательный файл {required}")
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        if not isinstance(manifest, dict):
            raise BackupError("Некорректный manifest.json")
        if manifest.get("format") != ARCHIVE_FORMAT:
            raise BackupError("Неизвестный формат резервной копии")

    @staticmethod
    def _read_payload(archive: zipfile.ZipFile) -> dict:
        info = archive.getinfo("database.json")
        if info.file_size > MAX_JSON_BYTES:
            raise BackupError("database.json слишком большой")
        try:
            payload = json.loads(archive.read(info).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupError(f"Некорректный JSON в архиве: {exc}") from exc
        if not isinstance(payload, dict):
            raise BackupError("Некорректная структура данных в архиве")
        if payload.get("format") not in (None, ARCHIVE_FORMAT):
            raise BackupError("Архив создан другим приложением")
        version = payload.get("format_version", 0)
        try:
            version = int(version)
        except (TypeError, ValueError) as exc:
            raise BackupError("Некорректная версия формата архива") from exc
        if version > ARCHIVE_FORMAT_VERSION:
            raise BackupError(
                "Архив создан более новой версией приложения и не может быть импортирован"
            )
        payload["format_version"] = version

        entries = payload.get("entries")
        categories = payload.get("categories", [])
        tags = payload.get("tags", [])
        if not isinstance(entries, list) or not isinstance(categories, list) or not isinstance(tags, list):
            raise BackupError("Некорректная структура данных в архиве")
        for entry in entries:
            if not isinstance(entry, dict) or not str(entry.get("title", "")).strip():
                raise BackupError("В архиве найдена запись без названия")
            if not entry.get("id"):
                raise BackupError("В архиве найдена запись без идентификатора")
            links = entry.get("links", [])
            if not isinstance(links, list):
                raise BackupError("Некорректный список ссылок в архиве")
        for item in categories + tags:
            if not isinstance(item, dict) or not item.get("id") or not item.get("name"):
                raise BackupError("Некорректные категории или теги в архиве")
        return payload

    @staticmethod
    def _read_metadata(archive: zipfile.ZipFile) -> dict:
        try:
            raw = archive.read("metadata/backup_info.json").decode("utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _collect_image_hashes(archive: zipfile.ZipFile, payload: dict) -> dict[str, str]:
        required: set[str] = set()
        for entry in payload["entries"]:
            image = entry.get("image")
            if image:
                required.add(Path(str(image)).name)
        result: dict[str, str] = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            if not info.filename.startswith("Images/"):
                continue
            name = Path(info.filename).name
            if name not in required:
                continue
            if info.file_size > MAX_JSON_BYTES:
                raise BackupError("Файл изображения в архиве слишком большой")
            data = archive.read(info)
            result[name] = hashlib.sha256(data).hexdigest()
        missing = required - set(result)
        if missing:
            raise BackupError(
                "В архиве отсутствуют изображения: " + ", ".join(sorted(missing)[:5])
            )
        return result

    # ------------------------------------------------------------------
    # Import / restore
    # ------------------------------------------------------------------
    def restore(
        self,
        source: str | Path,
        *,
        mode: str = "merge",
        progress: ProgressCallback | None = None,
    ) -> dict[str, int]:
        """Import an archive.

        ``mode='merge'`` keeps existing data and adds new records,
        ``mode='replace'`` wipes current data first (after validation).
        Matching IDs are treated as the same object and merged.
        """
        if mode not in ("merge", "replace"):
            raise BackupError("Неизвестный режим импорта")
        inspection = self.inspect_archive(source)
        payload = inspection.payload or {}
        result = {"entries": 0, "categories": 0, "tags": 0, "images": 0, "skipped": 0}

        staged_dir = Path(tempfile.mkdtemp(prefix="myapp-import-", dir=str(self.paths.root)))
        try:
            with zipfile.ZipFile(inspection.path) as archive:
                staged = self._extract_images(archive, payload, staged_dir)
            snapshot = None
            if mode == "replace":
                try:
                    snapshot = self.create_database_backup(prefix="before-import")
                except BackupError as exc:
                    logger.warning("Pre-import snapshot failed: %s", exc)

            with self.db.transaction():
                if mode == "replace":
                    self._clear_all()
                result = self._import_payload(payload, staged, progress=progress)
            if snapshot is not None:
                logger.info("Pre-import snapshot kept at %s", snapshot)
        except (sqlite3.Error, OSError) as exc:
            logger.exception("Import failed")
            raise BackupError(f"Импорт прерван, данные не изменены: {exc}") from exc
        finally:
            shutil.rmtree(staged_dir, ignore_errors=True)
        logger.info("Import finished: %s", result)
        return result

    def _extract_images(
        self, archive: zipfile.ZipFile, payload: dict, staged_dir: Path
    ) -> dict[str, Path]:
        """Extract archive images into a temporary directory, verifying hashes."""
        staged_dir.mkdir(parents=True, exist_ok=True)
        names = {
            Path(str(entry["image"])).name
            for entry in payload.get("entries", [])
            if entry.get("image")
        }
        extracted: dict[str, Path] = {}
        for info in archive.infolist():
            if info.is_dir() or not info.filename.startswith("Images/"):
                continue
            name = Path(info.filename).name
            if name not in names:
                continue
            target = staged_dir / name
            with archive.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            if target.stat().st_size != info.file_size:
                raise BackupError(f"Изображение {name} распаковано не полностью")
            extracted[name] = target
        return extracted

    def _clear_all(self) -> None:
        self.db.execute("DELETE FROM links")
        self.db.execute("DELETE FROM entry_tags")
        self.db.execute("DELETE FROM entries")
        self.db.execute("DELETE FROM categories")
        self.db.execute("DELETE FROM tags")

    def _import_payload(
        self,
        payload: dict,
        staged: dict[str, Path],
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, int]:
        result = {"entries": 0, "categories": 0, "tags": 0, "images": 0, "skipped": 0}
        category_map: dict[str, str] = {}
        for item in payload.get("categories", []):
            name = str(item["name"]).strip()
            existing = self.repo.find_category_by_name(name)
            if existing is not None:
                category_map[item["id"]] = existing.id
                result["skipped"] += 1
                continue
            created = self.repo.create_category(name, category_id=item["id"])
            category_map[item["id"]] = created.id
            result["categories"] += 1

        tag_map: dict[str, str] = {}
        for item in payload.get("tags", []):
            name = str(item["name"]).strip()
            existing = self.repo.find_tag_by_name(name)
            if existing is not None:
                tag_map[item["id"]] = existing.id
                result["skipped"] += 1
                continue
            created = self.repo.create_tag(name, tag_id=item["id"])
            tag_map[item["id"]] = created.id
            result["tags"] += 1

        entries = payload.get("entries", [])
        total = len(entries)
        for index, item in enumerate(entries, start=1):
            entry_id = str(item["id"])
            title = str(item["title"]).strip()
            category_id = category_map.get(item.get("category_id") or "")
            image_relative: str | None = None
            source_name = item.get("image")
            if source_name:
                image_relative = self._store_imported_image(
                    staged.get(Path(str(source_name)).name), entry_id
                )
                if image_relative:
                    result["images"] += 1

            existing_entry = self.repo.get_entry(entry_id)
            if existing_entry is not None:
                self.repo.update_entry(
                    entry_id,
                    title=title,
                    description=str(item.get("description", "")),
                    type=str(item.get("type", "")),
                )
                self.repo.set_entry_category(entry_id, category_id)
                if image_relative:
                    old = existing_entry.image_path
                    self.repo.set_entry_image(entry_id, image_relative)
                    if old and old != image_relative:
                        self._safe_remove_image(old)
                self.repo.delete_links_for_entry(entry_id)
                result["skipped"] += 1
            else:
                self.repo.create_entry(
                    title=title,
                    description=str(item.get("description", "")),
                    type=str(item.get("type", "")),
                    category_id=category_id,
                    image_path=image_relative,
                    entry_id=entry_id,
                    created_at=item.get("created_at") or None,
                    updated_at=item.get("updated_at") or None,
                )
                result["entries"] += 1

            for position, link in enumerate(item.get("links", [])):
                url = str(link.get("url", "")).strip()
                if not url:
                    continue
                self.repo.add_link(
                    entry_id,
                    str(link.get("title") or url),
                    url,
                    link_id=link.get("id") or new_id(),
                    position=position,
                )
            tag_ids = [
                tag_map[tag_id] for tag_id in item.get("tags", []) if tag_id in tag_map
            ]
            self.repo.set_entry_tags(entry_id, tag_ids)
            if progress:
                progress("entries", index, total)
        return result

    def _store_imported_image(self, staged: Path | None, entry_id: str) -> str | None:
        if staged is None or not staged.is_file():
            return None
        relative = f"entries/{new_id().replace('-', '')}.png"
        target = self.paths.image_file(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(staged, target)
        except OSError as exc:
            raise BackupError(f"Не удалось сохранить изображение: {exc}") from exc
        return relative

    def _safe_remove_image(self, relative: str) -> None:
        try:
            if relative in self.repo.all_image_paths():
                return
        except sqlite3.Error:
            return
        for path in (
            self.paths.image_file(relative),
            self.paths.thumbnail_file(relative),
        ):
            try:
                if path.is_file():
                    path.unlink()
            except (OSError, ValueError):
                continue

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------
    def verify_archive(self, source: str | Path) -> bool:
        try:
            for relative in self.inspect_archive(source).images:
                pass
            return True
        except BackupError as exc:
            logger.warning("Archive verification failed: %s", exc)
            return False

    def list_auto_backups(self) -> list[Path]:
        if not self.paths.auto_backups_dir.exists():
            return []
        return sorted(
            self.paths.auto_backups_dir.glob("*.db"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def checksum(self, path: str | Path) -> str:
        return sha256_file(Path(path))

    def export_copy(self, target: str | Path) -> Path:
        """Portable archive written to a user-chosen location."""
        return self.create_archive(target)
