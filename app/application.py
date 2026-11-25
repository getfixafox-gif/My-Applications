"""Composition root: wires paths, database, services and settings together."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.database.connection import Database, DatabaseError
from app.database.migrations import initialize_schema
from app.database.repository import Repository
from app.i18n import set_language
from app.images.image_processor import ImageProcessor
from app.paths import AppPaths
from app.services.backup_service import BackupService
from app.services.category_service import CategoryService
from app.services.entry_service import EntryService
from app.services.search_service import SearchService
from app.services.tag_service import TagService
from app.settings.config_manager import ConfigManager
from app.storage.backup_manager import BackupManager
from app.storage.file_manager import FileManager
from app.utils.logger import get_logger, set_log_level, setup_logging

logger = get_logger("app")


@dataclass
class AppContext:
    """Everything the UI needs, created once at startup."""

    paths: AppPaths
    config: ConfigManager
    database: Database
    repository: Repository
    images: ImageProcessor
    categories: CategoryService
    tags: TagService
    entries: EntryService
    search: SearchService
    backups: BackupService
    files: FileManager
    schema_version: int = 0

    def apply_settings(self) -> None:
        set_language(self.config.get("language", "ru"))
        set_log_level(self.config.get("log_level", "INFO"))

    def shutdown(self) -> None:
        try:
            self.database.checkpoint()
            self.database.close()
        except (sqlite3.Error, DatabaseError) as exc:  # pragma: no cover - shutdown path
            logger.warning("Database shutdown issue: %s", exc)


def _recover_database(paths: AppPaths) -> None:
    """Move a corrupted database aside so the app can still start."""
    stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
    target = paths.root / f"database.corrupt-{stamp}.db"
    try:
        paths.database_file.replace(target)
        logger.error("Corrupted database moved to %s", target)
    except OSError as exc:  # pragma: no cover - fatal
        logger.error("Cannot move corrupted database: %s", exc)


def create_context(data_dir: str | Path | None = None) -> AppContext:
    """Build a fully initialised application context."""
    from app.settings.defaults import DEFAULT_SETTINGS

    paths = AppPaths(data_dir).ensure()
    config = ConfigManager(paths.settings_file)
    config.load()
    setup_logging(paths.logs_dir, config.get("log_level", DEFAULT_SETTINGS["log_level"]))
    logger.info("Starting with data directory %s", paths.root)

    database = Database(paths.database_file)
    try:
        schema = initialize_schema(database)
    except DatabaseError as exc:
        logger.error("Database initialisation failed: %s", exc)
        database.close()
        if "file is not a database" in str(exc).lower() or "malformed" in str(exc).lower():
            _recover_database(paths)
            database = Database(paths.database_file)
            schema = initialize_schema(database)
        else:
            raise

    repository = Repository(database)
    images = ImageProcessor(paths)
    categories = CategoryService(database, repository)
    tags = TagService(database, repository)
    entries = EntryService(database, repository, paths, images, categories, tags)
    search = SearchService(entries)
    files = FileManager(paths)
    manager = BackupManager(database, repository, paths)
    backups = BackupService(manager, config)

    context = AppContext(
        paths=paths,
        config=config,
        database=database,
        repository=repository,
        images=images,
        categories=categories,
        tags=tags,
        entries=entries,
        search=search,
        backups=backups,
        files=files,
        schema_version=schema,
    )
    context.apply_settings()
    categories.ensure_defaults()
    return context
