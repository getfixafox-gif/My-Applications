"""Tag business logic."""

from __future__ import annotations

import sqlite3

from app.database.connection import Database, DatabaseError
from app.database.repository import Repository
from app.events import TAG_CHANGED, bus
from app.models import Tag
from app.utils.logger import get_logger
from app.utils.validators import ValidationError, clean_tag_name

logger = get_logger("tags")


class TagService:
    def __init__(self, database: Database, repository: Repository) -> None:
        self.db = database
        self.repo = repository

    def list_tags(self) -> list[Tag]:
        try:
            return self.repo.list_tags()
        except sqlite3.Error as exc:
            logger.error("Cannot list tags: %s", exc)
            raise DatabaseError(f"Не удалось получить теги: {exc}") from exc

    def get(self, tag_id: str) -> Tag | None:
        try:
            return self.repo.get_tag(tag_id)
        except sqlite3.Error as exc:
            logger.error("Cannot read tag: %s", exc)
            return None

    def get_or_create(self, name: str) -> Tag:
        """Resolve a tag by name, creating it when needed (used by the editor)."""
        clean = clean_tag_name(name)
        existing = self.repo.find_tag_by_name(clean)
        if existing is not None:
            return existing
        try:
            with self.db.transaction():
                tag = self.repo.create_tag(clean)
        except sqlite3.IntegrityError:
            found = self.repo.find_tag_by_name(clean)
            if found is None:
                raise ValidationError("Не удалось создать тег")
            return found
        except sqlite3.Error as exc:
            raise DatabaseError(f"Не удалось создать тег: {exc}") from exc
        logger.info("Tag created: %s", tag.name)
        bus.emit(TAG_CHANGED)
        return tag

    def create(self, name: str) -> Tag:
        clean = clean_tag_name(name)
        if self.repo.find_tag_by_name(clean) is not None:
            raise ValidationError("Тег с таким названием уже существует")
        return self.get_or_create(clean)

    def rename(self, tag_id: str, name: str) -> Tag:
        clean = clean_tag_name(name)
        tag = self.repo.get_tag(tag_id)
        if tag is None:
            raise ValidationError("Тег не найден")
        existing = self.repo.find_tag_by_name(clean)
        if existing is not None and existing.id != tag_id:
            raise ValidationError("Тег с таким названием уже существует")
        try:
            with self.db.transaction():
                self.repo.rename_tag(tag_id, clean)
        except sqlite3.IntegrityError as exc:
            raise ValidationError("Тег с таким названием уже существует") from exc
        except sqlite3.Error as exc:
            raise DatabaseError(f"Не удалось переименовать тег: {exc}") from exc
        bus.emit(TAG_CHANGED)
        return self.repo.get_tag(tag_id) or tag

    def delete(self, tag_id: str) -> bool:
        tag = self.repo.get_tag(tag_id)
        if tag is None:
            return False
        try:
            with self.db.transaction():
                self.repo.delete_tag(tag_id)
        except sqlite3.Error as exc:
            raise DatabaseError(f"Не удалось удалить тег: {exc}") from exc
        logger.info("Tag deleted: %s", tag.name)
        bus.emit(TAG_CHANGED)
        return True

    def usage(self, tag_id: str) -> int:
        return self.repo.tag_usage(tag_id)

    def cleanup_unused(self) -> int:
        """Remove tags that are not attached to any entry."""
        removed = 0
        try:
            for tag in self.repo.list_tags():
                if tag.entry_count == 0:
                    with self.db.transaction():
                        self.repo.delete_tag(tag.id)
                    removed += 1
        except sqlite3.Error as exc:
            logger.warning("Cannot clean up unused tags: %s", exc)
        if removed:
            logger.info("Removed %s unused tag(s)", removed)
            bus.emit(TAG_CHANGED)
        return removed
