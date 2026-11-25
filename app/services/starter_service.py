"""Seeding the starter catalog on a fresh installation.

The starter entries are added exactly once: the database records the applied
version in ``app_meta``. Users who delete them never see them again, and an
existing catalogue is never touched.
"""

from __future__ import annotations

import sqlite3

from app.data.starter_catalog import STARTER_ENTRIES, STARTER_VERSION
from app.database.connection import Database, DatabaseError
from app.database.repository import Repository
from app.events import STORAGE_CHANGED, bus
from app.models import Entry
from app.services.category_service import CategoryService
from app.services.tag_service import TagService
from app.utils.logger import get_logger
from app.utils.validators import ValidationError

logger = get_logger("starter")

META_KEY = "starter_catalog_version"


class StarterService:
    """Adds the bundled starter entries to an empty catalogue."""

    def __init__(
        self,
        database: Database,
        repository: Repository,
        categories: CategoryService,
        tags: TagService,
    ) -> None:
        self.db = database
        self.repo = repository
        self.categories = categories
        self.tags = tags

    def applied_version(self) -> int:
        try:
            value = self.repo.get_meta(META_KEY)
        except sqlite3.Error as exc:  # pragma: no cover - defensive
            logger.warning("Cannot read starter catalog version: %s", exc)
            return 0
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def is_available(self) -> bool:
        """``True`` when the starter catalog has not been added yet."""
        return self.applied_version() < STARTER_VERSION

    def seed(self, *, force: bool = False) -> int:
        """Add the starter entries and return how many were created.

        With ``force`` the entries are added even to a non-empty catalogue;
        duplicates are still skipped by title.
        """
        if not force:
            if not self.is_available():
                return 0
            if self.repo.count_entries() > 0:
                # An existing catalogue is never touched; remember that the
                # starter list was considered so it is not offered again.
                self._mark_applied()
                return 0

        category_ids = {category.name: category.id for category in self.categories.list_categories()}
        created = 0
        try:
            with self.db.transaction():
                for item in STARTER_ENTRIES:
                    if self.repo.find_entry_by_title(item.title) is not None:
                        continue
                    category_id = category_ids.get(item.category)
                    entry = self.repo.create_entry(
                        title=item.title,
                        description=item.description,
                        type=item.type,
                        category_id=category_id,
                    )
                    for position, link in enumerate(item.links):
                        self.repo.add_link(
                            entry.id, link.title, link.url, position=position
                        )
                    tag_ids = []
                    for name in item.tags:
                        try:
                            tag_ids.append(self.tags.get_or_create(name).id)
                        except (ValidationError, DatabaseError) as exc:
                            logger.warning("Starter tag %r skipped: %s", name, exc)
                    if tag_ids:
                        self.repo.set_entry_tags(entry.id, tag_ids)
                    created += 1
                self.repo.set_meta(META_KEY, str(STARTER_VERSION))
        except sqlite3.Error as exc:
            logger.error("Cannot create starter catalog: %s", exc)
            raise DatabaseError(f"Не удалось добавить стартовый каталог: {exc}") from exc

        if created:
            logger.info("Starter catalog: %s entries added", created)
            bus.emit(STORAGE_CHANGED)
        return created

    def entries(self) -> list[Entry]:
        """Starter entries that already exist in the catalogue."""
        result = []
        for item in STARTER_ENTRIES:
            entry = self.repo.find_entry_by_title(item.title)
            if entry is not None:
                result.append(entry)
        return result

    def _mark_applied(self) -> None:
        try:
            with self.db.transaction():
                self.repo.set_meta(META_KEY, str(STARTER_VERSION))
        except sqlite3.Error as exc:  # pragma: no cover - defensive
            logger.warning("Cannot record starter catalog version: %s", exc)
