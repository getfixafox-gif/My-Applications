"""SQLite connection management with transactions and thread safety."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.utils.logger import get_logger

logger = get_logger("database")


class DatabaseError(RuntimeError):
    """Raised when a database operation cannot be completed."""


class Database:
    """Owns SQLite connections, one per thread, for a single database file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._local = threading.local()
        self._lock = threading.RLock()
        self._depth = 0
        self._closed = False

    # -- connections -----------------------------------------------------
    def _create_connection(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            str(self.path),
            timeout=15.0,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
            cursor.execute("PRAGMA busy_timeout = 15000")
        finally:
            cursor.close()
        return connection

    def connection(self) -> sqlite3.Connection:
        if self._closed:
            raise DatabaseError("База данных закрыта")
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._create_connection()
            self._local.conn = conn
        return conn

    # -- transactions ----------------------------------------------------
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block inside an immediate transaction.

        Nested calls join the outer transaction, so services can freely compose
        repository operations within one atomic unit.
        """
        with self._lock:
            conn = self.connection()
            outer = self._depth == 0
            if outer:
                conn.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield conn
            except BaseException:
                self._depth -= 1
                if outer:
                    try:
                        conn.execute("ROLLBACK")
                    except sqlite3.Error as exc:  # pragma: no cover - rare
                        logger.error("Rollback failed: %s", exc)
                raise
            else:
                self._depth -= 1
                if outer:
                    conn.execute("COMMIT")

    # -- helpers ---------------------------------------------------------
    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        return self.connection().execute(sql, params)

    def executescript(self, script: str) -> None:
        """Run a multi-statement SQL script.

        ``sqlite3.executescript`` commits any pending transaction implicitly,
        so it must never be used inside :meth:`transaction`.
        """
        self.connection().executescript(script)

    def query_all(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        return self.connection().execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        return self.connection().execute(sql, params).fetchone()

    def scalar(self, sql: str, params: tuple | list = (), default=None):
        row = self.query_one(sql, params)
        if row is None:
            return default
        return row[0]

    def user_version(self) -> int:
        return int(self.scalar("PRAGMA user_version", default=0) or 0)

    def set_user_version(self, version: int) -> None:
        self.execute(f"PRAGMA user_version = {int(version)}")

    def integrity_check(self) -> bool:
        try:
            result = self.scalar("PRAGMA integrity_check", default="")
        except sqlite3.Error as exc:
            logger.error("Integrity check failed: %s", exc)
            return False
        return str(result).lower() == "ok"

    def backup_to(self, target: str | Path) -> None:
        """Consistent copy using the SQLite backup API."""
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        destination = sqlite3.connect(str(target), timeout=30.0)
        try:
            with destination:
                self.connection().backup(destination)
        finally:
            destination.close()

    def close(self) -> None:
        self._closed = True
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error as exc:  # pragma: no cover - rare
                logger.warning("Cannot close database: %s", exc)
            self._local.conn = None

    def reopen(self) -> None:
        self._closed = False

    def checkpoint(self) -> None:
        try:
            self.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error as exc:  # pragma: no cover - rare
            logger.warning("WAL checkpoint failed: %s", exc)
