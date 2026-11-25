"""Database package: connections, schema and repositories."""

from app.database.connection import Database, DatabaseError
from app.database.migrations import initialize_schema
from app.database.repository import EntryFilter, Repository

__all__ = ["Database", "DatabaseError", "EntryFilter", "Repository", "initialize_schema"]
