"""Business logic for entries: validation, links, tags, images."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.database.connection import Database, DatabaseError
from app.database.repository import EntryFilter, Repository
from app.events import (
    ENTRY_CREATED,
    ENTRY_DELETED,
    ENTRY_UPDATED,
    STORAGE_CHANGED,
    bus,
)
from app.images.image_processor import ImageError, ImageProcessor
from app.models import Entry, EntrySummary
from app.paths import AppPaths
from app.services.category_service import CategoryService
from app.services.tag_service import TagService
from app.utils.helpers import utc_now_iso
from app.utils.logger import get_logger
from app.utils.validators import (
    ValidationError,
    clean_description,
    clean_title,
    clean_type,
    validate_link_pair,
)

logger = get_logger("entries")


@dataclass(slots=True)
class LinkDraft:
    title: str = ""
    url: str = ""
    id: str | None = None


@dataclass(slots=True)
class EntryDraft:
    title: str = ""
    description: str = ""
    type: str = ""
    category_id: str | None = None
    tag_ids: list[str] = field(default_factory=list)
    links: list[LinkDraft] = field(default_factory=list)
    #: ``keep`` | ``replace`` | ``remove``
    image_action: str = "keep"
    image_source: str | None = None


class EntryService:
    def __init__(
        self,
        database: Database,
        repository: Repository,
        paths: AppPaths,
        images: ImageProcessor,
        categories: CategoryService,
        tags: TagService,
    ) -> None:
        self.db = database
        self.repo = repository
        self.paths = paths
        self.images = images
        self.categories = categories
        self.tags = tags

    # -- reading ---------------------------------------------------------
    def list_entries(self, filters: EntryFilter | None = None) -> list[EntrySummary]:
        try:
            return self.repo.list_entries(filters)
        except sqlite3.Error as exc:
            logger.error("Cannot list entries: %s", exc)
            raise DatabaseError(f"Не удалось получить список записей: {exc}") from exc

    def count_entries(self) -> int:
        try:
            return self.repo.count_entries()
        except sqlite3.Error as exc:
            logger.error("Cannot count entries: %s", exc)
            return 0

    def get_entry(self, entry_id: str) -> Entry | None:
        try:
            return self.repo.get_entry(entry_id)
        except sqlite3.Error as exc:
            logger.error("Cannot read entry %s: %s", entry_id, exc)
            raise DatabaseError(f"Не удалось прочитать запись: {exc}") from exc

    # -- validation ------------------------------------------------------
    def _validate_draft(
        self, draft: EntryDraft, *, for_update: bool
    ) -> tuple[str, str, str]:
        title = clean_title(draft.title)
        description = clean_description(draft.description)
        entry_type = clean_type(draft.type)
        if draft.category_id and self.repo.get_category(draft.category_id) is None:
            draft.category_id = None
        seen_urls: set[str] = set()
        cleaned_links: list[LinkDraft] = []
        for link in draft.links:
            if not str(link.url or "").strip() and not str(link.title or "").strip():
                continue  # empty row, silently skipped
            title_value, url_value = validate_link_pair(link.title, link.url)
            if url_value in seen_urls:
                continue
            seen_urls.add(url_value)
            cleaned_links.append(LinkDraft(title=title_value, url=url_value, id=link.id))
        draft.links = cleaned_links
        draft.title = title
        draft.description = description
        draft.type = entry_type
        return title, description, entry_type

    def _apply_image(
        self,
        draft: EntryDraft,
        current_relative: str | None,
        *,
        is_new: bool,
    ) -> tuple[str | None, str | None]:
        """Resolve the image for a draft.

        Returns ``(relative_path, new_file_relative)`` where the second item is
        the freshly created file that must be removed if the transaction fails.
        """
        action = draft.image_action or "keep"
        if action == "remove":
            return None, None
        if action == "replace":
            source = draft.image_source
            if not source:
                return current_relative, None
            relative = self.images.import_image(source)
            return relative, relative
        return current_relative, None

    # -- creating --------------------------------------------------------
    def create_entry(self, draft: EntryDraft) -> Entry:
        try:
            title, description, entry_type = self._validate_draft(draft, for_update=False)
        except ValidationError as exc:
            raise ValidationError(str(exc)) from exc

        new_image: str | None = None
        try:
            image_relative, new_image = self._apply_image(draft, None, is_new=True)
            with self.db.transaction():
                entry = self.repo.create_entry(
                    title=title,
                    description=description,
                    type=entry_type,
                    category_id=draft.category_id,
                    image_path=image_relative,
                )
                for index, link in enumerate(draft.links):
                    self.repo.add_link(
                        entry.id, link.title, link.url, position=index
                    )
                self.repo.set_entry_tags(entry.id, draft.tag_ids)
            full = self.repo.get_entry(entry.id)
            assert full is not None
        except (sqlite3.Error, DatabaseError) as exc:
            self._discard_file(new_image)
            logger.error("Cannot create entry: %s", exc)
            raise DatabaseError(f"Не удалось создать запись: {exc}") from exc
        except ImageError:
            raise
        except Exception:
            self._discard_file(new_image)
            raise

        logger.info("Entry created: %s", full.title)
        bus.emit(ENTRY_CREATED, entry=full)
        bus.emit(STORAGE_CHANGED)
        return full

    # -- updating --------------------------------------------------------
    def update_entry(self, entry_id: str, draft: EntryDraft) -> Entry:
        current = self.repo.get_entry(entry_id)
        if current is None:
            raise ValidationError("Запись не найдена")

        try:
            title, description, entry_type = self._validate_draft(draft, for_update=True)
        except ValidationError as exc:
            raise ValidationError(str(exc)) from exc

        new_image: str | None = None
        old_image = current.image_path
        try:
            image_relative, new_image = self._apply_image(
                draft, current.image_path, is_new=False
            )
            with self.db.transaction():
                self.repo.update_entry(
                    entry_id,
                    title=title,
                    description=description,
                    type=entry_type,
                    image_path=image_relative,
                )
                self.repo.set_entry_category(entry_id, draft.category_id)
                self._sync_links(entry_id, draft.links)
                self.repo.set_entry_tags(entry_id, draft.tag_ids)
                self.repo.touch_entry(entry_id)
            full = self.repo.get_entry(entry_id)
            assert full is not None
        except (sqlite3.Error, DatabaseError) as exc:
            self._discard_file(new_image)
            logger.error("Cannot update entry: %s", exc)
            raise DatabaseError(f"Не удалось сохранить запись: {exc}") from exc
        except Exception:
            self._discard_file(new_image)
            raise

        if new_image and old_image and new_image != old_image:
            self._delete_image_if_unused(old_image)
        elif old_image and image_relative is None:
            self._delete_image_if_unused(old_image)

        logger.info("Entry updated: %s", full.title)
        bus.emit(ENTRY_UPDATED, entry=full)
        bus.emit(STORAGE_CHANGED)
        return full

    def _sync_links(self, entry_id: str, links: list[LinkDraft]) -> None:
        existing = {link.id: link for link in self.repo.list_links(entry_id)}
        keep_ids: set[str] = set()
        for index, draft_link in enumerate(links):
            if draft_link.id and draft_link.id in existing:
                self.repo.update_link(draft_link.id, draft_link.title, draft_link.url)
                keep_ids.add(draft_link.id)
                self.db.execute(
                    "UPDATE links SET position = ?, updated_at = ? WHERE id = ?",
                    (index, utc_now_iso(), draft_link.id),
                )
            else:
                self.repo.add_link(
                    entry_id, draft_link.title, draft_link.url, position=index
                )
        for link_id in set(existing) - keep_ids:
            self.repo.delete_link(link_id)

    # -- quick actions ---------------------------------------------------
    def set_image(self, entry_id: str, source: str | Path) -> str:
        """Replace the icon of an existing entry."""
        current = self.repo.get_entry(entry_id)
        if current is None:
            raise ValidationError("Запись не найдена")
        relative = self.images.import_image(source)
        try:
            with self.db.transaction():
                self.repo.set_entry_image(entry_id, relative)
        except (sqlite3.Error, DatabaseError) as exc:
            self._discard_file(relative)
            raise DatabaseError(f"Не удалось сохранить иконку: {exc}") from exc
        if current.image_path and current.image_path != relative:
            self._delete_image_if_unused(current.image_path)
        bus.emit(ENTRY_UPDATED, entry=self.repo.get_entry(entry_id))
        bus.emit(STORAGE_CHANGED)
        return relative

    def remove_image(self, entry_id: str) -> None:
        current = self.repo.get_entry(entry_id)
        if current is None or not current.image_path:
            return
        old = current.image_path
        with self.db.transaction():
            self.repo.set_entry_image(entry_id, None)
        self._delete_image_if_unused(old)
        bus.emit(ENTRY_UPDATED, entry=self.repo.get_entry(entry_id))
        bus.emit(STORAGE_CHANGED)

    def set_category(self, entry_id: str, category_id: str | None) -> None:
        with self.db.transaction():
            self.repo.set_entry_category(entry_id, category_id)
        bus.emit(ENTRY_UPDATED, entry=self.repo.get_entry(entry_id))

    def add_tags(self, entry_id: str, tag_ids: list[str]) -> None:
        current = self.repo.list_tags_for_entry(entry_id)
        merged = [tag.id for tag in current] + list(tag_ids)
        with self.db.transaction():
            self.repo.set_entry_tags(entry_id, merged)
        bus.emit(ENTRY_UPDATED, entry=self.repo.get_entry(entry_id))

    # -- deleting --------------------------------------------------------
    def delete_entry(self, entry_id: str) -> bool:
        current = self.repo.get_entry(entry_id)
        if current is None:
            return False
        try:
            with self.db.transaction():
                deleted = self.repo.delete_entry(entry_id)
        except (sqlite3.Error, DatabaseError) as exc:
            logger.error("Cannot delete entry %s: %s", entry_id, exc)
            raise DatabaseError(f"Не удалось удалить запись: {exc}") from exc
        if deleted and current.image_path:
            self._delete_image_if_unused(current.image_path)
        if deleted:
            logger.info("Entry deleted: %s", current.title)
            bus.emit(ENTRY_DELETED, entry_id=entry_id)
            bus.emit(STORAGE_CHANGED)
        return deleted

    # -- file housekeeping -----------------------------------------------
    def _delete_image_if_unused(self, relative: str | None) -> None:
        """Delete an image file only when no other entry references it."""
        if not relative:
            return
        try:
            used = relative in self.repo.all_image_paths()
        except sqlite3.Error as exc:
            logger.warning("Cannot verify image usage, keeping %s: %s", relative, exc)
            return
        if used:
            logger.debug("Image %s still used by other entries; kept", relative)
            return
        self.images.delete(relative)

    def _discard_file(self, relative: str | None) -> None:
        if relative:
            self.images.delete(relative)

    def cleanup_orphan_images(self) -> int:
        """Remove files in ``Images/`` that no entry references.

        Returns the number of removed files.
        """
        try:
            used = self.repo.all_image_paths()
        except sqlite3.Error as exc:
            logger.error("Cannot collect image references: %s", exc)
            return 0
        referenced: set[Path] = set()
        for relative in used:
            try:
                referenced.add(self.paths.image_file(relative))
                referenced.add(self.paths.thumbnail_file(relative))
            except ValueError:
                continue
        removed = 0
        for base in (self.paths.entries_images_dir, self.paths.thumbnails_dir):
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if not path.is_file() or path in referenced:
                    continue
                try:
                    path.unlink()
                    removed += 1
                except OSError as exc:
                    logger.warning("Cannot delete orphan image %s: %s", path, exc)
        if removed:
            logger.info("Removed %s orphan image file(s)", removed)
            bus.emit(STORAGE_CHANGED)
        return removed
