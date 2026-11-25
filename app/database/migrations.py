"""Schema creation and forward-only migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from app.database.connection import Database, DatabaseError
from app.utils.logger import get_logger
from app.version import DB_SCHEMA_VERSION

logger = get_logger("migrations")

SCHEMA_FILE = Path(__file__).with_name("schema.sql")

#: Ordered migrations applied after the base schema exists.
#: Each entry is ``(target_version, callable)``. Version 1 is the base schema.
MIGRATIONS: list[tuple[int, Callable[[Database], None]]] = []


def _read_schema() -> str:
    try:
        return SCHEMA_FILE.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - packaging error
        raise DatabaseError(f"Не удалось прочитать схему базы данных: {exc}") from exc


def initialize_schema(database: Database) -> int:
    """Create the schema when missing and apply pending migrations."""
    try:
        current = database.user_version()
        if current == 0:
            script = _read_schema()
            database.executescript(script)
            database.set_user_version(DB_SCHEMA_VERSION)
            logger.info("Database schema created (version %s)", DB_SCHEMA_VERSION)
            return DB_SCHEMA_VERSION

        if current > DB_SCHEMA_VERSION:
            logger.warning(
                "Database schema version %s is newer than supported version %s",
                current,
                DB_SCHEMA_VERSION,
            )
            return current

        for target, migrate in MIGRATIONS:
            if current < target <= DB_SCHEMA_VERSION:
                logger.info("Applying migration to version %s", target)
                migrate(database)
                database.set_user_version(target)
                current = target

        # Ensure optional tables/indexes always exist (idempotent DDL).
        database.executescript(_read_schema())
        if current < DB_SCHEMA_VERSION:
            database.set_user_version(DB_SCHEMA_VERSION)
            current = DB_SCHEMA_VERSION
        return current
    except sqlite3.Error as exc:
        raise DatabaseError(f"Ошибка инициализации базы данных: {exc}") from exc
