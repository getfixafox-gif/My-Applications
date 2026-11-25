"""Category business logic."""

from __future__ import annotations

import sqlite3

from app.database.connection import Database, DatabaseError
from app.database.repository import Repository
from app.events import CATEGORY_CHANGED, bus
from app.models import Category
from app.utils.logger import get_logger
from app.utils.validators import ValidationError, clean_category_name

logger = get_logger("categories")

DEFAULT_CATEGORIES = (
    "Программы",
    "Игры",
    "Сайты",
    "Инструменты",
    "Разработка",
    "Графика",
)


class CategoryService:
    def __init__(self, database: Database, repository: Repository) -> None:
        self.db = database
        self.repo = repository

    def list_categories(self) -> list[Category]:
        try:
            return self.repo.list_categories()
        except sqlite3.Error as exc:
            logger.error("Cannot list categories: %s", exc)
            raise DatabaseError(f"Не удалось получить категории: {exc}") from exc

    def get(self, category_id: str) -> Category | None:
        try:
            return self.repo.get_category(category_id)
        except sqlite3.Error as exc:
            logger.error("Cannot read category: %s", exc)
            return None

    def create(self, name: str) -> Category:
        clean = clean_category_name(name)
        existing = self.repo.find_category_by_name(clean)
        if existing is not None:
            raise ValidationError("Категория с таким названием уже существует")
        try:
            with self.db.transaction():
                category = self.repo.create_category(clean)
        except sqlite3.IntegrityError as exc:
            raise ValidationError("Категория с таким названием уже существует") from exc
        except sqlite3.Error as exc:
            raise DatabaseError(f"Не удалось создать категорию: {exc}") from exc
        logger.info("Category created: %s", category.name)
        bus.emit(CATEGORY_CHANGED)
        return category

    def rename(self, category_id: str, name: str) -> Category:
        clean = clean_category_name(name)
        category = self.repo.get_category(category_id)
        if category is None:
            raise ValidationError("Категория не найдена")
        existing = self.repo.find_category_by_name(clean)
        if existing is not None and existing.id != category_id:
            raise ValidationError("Категория с таким названием уже существует")
        try:
            with self.db.transaction():
                self.repo.rename_category(category_id, clean)
        except sqlite3.IntegrityError as exc:
            raise ValidationError("Категория с таким названием уже существует") from exc
        except sqlite3.Error as exc:
            raise DatabaseError(f"Не удалось переименовать категорию: {exc}") from exc
        bus.emit(CATEGORY_CHANGED)
        return self.repo.get_category(category_id) or category

    def delete(self, category_id: str) -> bool:
        """Delete a category. Entries are kept and become uncategorised."""
        category = self.repo.get_category(category_id)
        if category is None:
            return False
        try:
            with self.db.transaction():
                self.repo.delete_category(category_id)
        except sqlite3.Error as exc:
            raise DatabaseError(f"Не удалось удалить категорию: {exc}") from exc
        logger.info("Category deleted: %s", category.name)
        bus.emit(CATEGORY_CHANGED)
        return True

    def usage(self, category_id: str) -> int:
        return self.repo.category_usage(category_id)

    def ensure_defaults(self) -> None:
        """Create the example categories on a brand-new database only."""
        try:
            if self.repo.list_categories():
                return
            with self.db.transaction():
                for name in DEFAULT_CATEGORIES:
                    if self.repo.find_category_by_name(name) is None:
                        self.repo.create_category(name)
            logger.info("Default categories created")
            bus.emit(CATEGORY_CHANGED)
        except sqlite3.Error as exc:  # pragma: no cover - defensive
            logger.warning("Cannot create default categories: %s", exc)
