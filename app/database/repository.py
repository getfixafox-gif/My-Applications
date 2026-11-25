"""Data access layer: the only place that speaks SQL."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.database.connection import Database
from app.models import Category, Entry, EntrySummary, Link, Tag
from app.utils.helpers import new_id, utc_now_iso
from app.utils.logger import get_logger

logger = get_logger("repository")

SORT_SQL = {
    "updated_desc": "e.updated_at DESC, e.title_key ASC",
    "updated_asc": "e.updated_at ASC, e.title_key ASC",
    "title_asc": "e.title_key ASC",
    "title_desc": "e.title_key DESC",
    "created_desc": "e.created_at DESC, e.title_key ASC",
    "created_asc": "e.created_at ASC, e.title_key ASC",
}


def normalize_key(text: str) -> str:
    """Case-insensitive key used for unique names and title sorting."""
    return (text or "").strip().casefold()


@dataclass(slots=True)
class EntryFilter:
    search: str = ""
    category_id: str | None = None
    tag_ids: tuple[str, ...] = ()
    sort: str = "updated_desc"


def _entry_from_row(row: sqlite3.Row) -> Entry:
    keys = row.keys()
    return Entry(
        id=row["id"],
        title=row["title"],
        description=row["description"] or "",
        type=row["type"] or "",
        category_id=row["category_id"],
        image_path=row["image_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        category_name=row["category_name"] if "category_name" in keys else None,
    )


def _link_from_row(row: sqlite3.Row) -> Link:
    return Link(
        id=row["id"],
        entry_id=row["entry_id"],
        title=row["title"],
        url=row["url"],
        position=row["position"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _category_from_row(row: sqlite3.Row) -> Category:
    keys = row.keys()
    return Category(
        id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        entry_count=row["entry_count"] if "entry_count" in keys else 0,
    )


def _tag_from_row(row: sqlite3.Row) -> Tag:
    keys = row.keys()
    return Tag(
        id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        entry_count=row["entry_count"] if "entry_count" in keys else 0,
    )


class Repository:
    """CRUD operations for entries, links, categories and tags."""

    def __init__(self, database: Database) -> None:
        self.db = database

    # ------------------------------------------------------------------
    # Entries
    # ------------------------------------------------------------------
    def list_entries(self, filters: EntryFilter | None = None) -> list[EntrySummary]:
        filters = filters or EntryFilter()
        clauses: list[str] = []
        params: list = []

        search = (filters.search or "").strip()
        if search:
            clauses.append("e.title_key LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(normalize_key(search))}%")
        if filters.category_id:
            clauses.append("e.category_id = ?")
            params.append(filters.category_id)
        if filters.tag_ids:
            placeholders = ",".join("?" for _ in filters.tag_ids)
            clauses.append(
                f"e.id IN (SELECT entry_id FROM entry_tags WHERE tag_id IN ({placeholders}) "
                f"GROUP BY entry_id HAVING COUNT(DISTINCT tag_id) = ?)"
            )
            params.extend(filters.tag_ids)
            params.append(len(set(filters.tag_ids)))

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = SORT_SQL.get(filters.sort, SORT_SQL["updated_desc"])
        sql = (
            "SELECT e.id, e.title, e.image_path, e.type, e.updated_at, e.category_id "
            f"FROM entries e {where} ORDER BY {order}"
        )
        rows = self.db.query_all(sql, tuple(params))
        return [
            EntrySummary(
                id=row["id"],
                title=row["title"],
                image_path=row["image_path"],
                type=row["type"] or "",
                updated_at=row["updated_at"],
                category_id=row["category_id"],
            )
            for row in rows
        ]

    def count_entries(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM entries", default=0) or 0)

    def get_entry(self, entry_id: str) -> Entry | None:
        row = self.db.query_one(
            "SELECT e.*, c.name AS category_name FROM entries e "
            "LEFT JOIN categories c ON c.id = e.category_id WHERE e.id = ?",
            (entry_id,),
        )
        if row is None:
            return None
        entry = _entry_from_row(row)
        entry.links = self.list_links(entry.id)
        entry.tags = self.list_tags_for_entry(entry.id)
        return entry

    def entry_exists(self, entry_id: str) -> bool:
        return bool(self.db.scalar("SELECT 1 FROM entries WHERE id = ?", (entry_id,)))

    def find_entry_by_title(self, title: str) -> Entry | None:
        """Look up an entry by its normalised title."""
        row = self.db.query_one(
            "SELECT id FROM entries WHERE title_key = ? LIMIT 1", (normalize_key(title),)
        )
        return self.get_entry(row["id"]) if row else None

    def create_entry(
        self,
        *,
        title: str,
        description: str = "",
        type: str = "",
        category_id: str | None = None,
        image_path: str | None = None,
        entry_id: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> Entry:
        now = utc_now_iso()
        eid = entry_id or new_id()
        created = created_at or now
        self.db.execute(
            "INSERT INTO entries (id, title, title_key, description, type, category_id, "
            "image_path, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                eid,
                title,
                normalize_key(title),
                description,
                type,
                category_id,
                image_path,
                created,
                updated_at or created,
            ),
        )
        entry = self.get_entry(eid)
        assert entry is not None
        return entry

    def update_entry(
        self,
        entry_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        type: str | None = None,
        image_path: str | None = None,
        touch: bool = True,
        updated_at: str | None = None,
    ) -> bool:
        assignments: list[str] = []
        params: list = []
        if title is not None:
            assignments.extend(["title = ?", "title_key = ?"])
            params.extend([title, normalize_key(title)])
        if description is not None:
            assignments.append("description = ?")
            params.append(description)
        if type is not None:
            assignments.append("type = ?")
            params.append(type)
        if image_path is not None:
            assignments.append("image_path = ?")
            params.append(image_path)
        if touch:
            assignments.append("updated_at = ?")
            params.append(updated_at or utc_now_iso())
        if not assignments:
            return False
        params.append(entry_id)
        cursor = self.db.execute(
            f"UPDATE entries SET {', '.join(assignments)} WHERE id = ?", tuple(params)
        )
        return cursor.rowcount > 0

    def set_entry_category(self, entry_id: str, category_id: str | None) -> None:
        self.db.execute(
            "UPDATE entries SET category_id = ?, updated_at = ? WHERE id = ?",
            (category_id, utc_now_iso(), entry_id),
        )

    def set_entry_image(self, entry_id: str, image_path: str | None) -> None:
        self.db.execute(
            "UPDATE entries SET image_path = ?, updated_at = ? WHERE id = ?",
            (image_path, utc_now_iso(), entry_id),
        )

    def touch_entry(self, entry_id: str) -> None:
        self.db.execute(
            "UPDATE entries SET updated_at = ? WHERE id = ?", (utc_now_iso(), entry_id)
        )

    def delete_entry(self, entry_id: str) -> bool:
        cursor = self.db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        return cursor.rowcount > 0

    def all_image_paths(self) -> set[str]:
        rows = self.db.query_all(
            "SELECT image_path FROM entries WHERE image_path IS NOT NULL AND image_path <> ''"
        )
        return {row["image_path"] for row in rows}

    # ------------------------------------------------------------------
    # Links
    # ------------------------------------------------------------------
    def list_links(self, entry_id: str) -> list[Link]:
        rows = self.db.query_all(
            "SELECT * FROM links WHERE entry_id = ? ORDER BY position ASC, rowid ASC",
            (entry_id,),
        )
        return [_link_from_row(row) for row in rows]

    def get_link(self, link_id: str) -> Link | None:
        row = self.db.query_one("SELECT * FROM links WHERE id = ?", (link_id,))
        return _link_from_row(row) if row else None

    def add_link(
        self,
        entry_id: str,
        title: str,
        url: str,
        *,
        link_id: str | None = None,
        position: int | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> Link:
        now = utc_now_iso()
        lid = link_id or new_id()
        if position is None:
            position = int(
                self.db.scalar(
                    "SELECT COALESCE(MAX(position), -1) + 1 FROM links WHERE entry_id = ?",
                    (entry_id,),
                    default=0,
                )
                or 0
            )
        self.db.execute(
            "INSERT INTO links (id, entry_id, title, url, position, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (lid, entry_id, title, url, position, created_at or now, updated_at or now),
        )
        link = self.get_link(lid)
        assert link is not None
        return link

    def update_link(self, link_id: str, title: str, url: str) -> bool:
        cursor = self.db.execute(
            "UPDATE links SET title = ?, url = ?, updated_at = ? WHERE id = ?",
            (title, url, utc_now_iso(), link_id),
        )
        return cursor.rowcount > 0

    def delete_link(self, link_id: str) -> bool:
        cursor = self.db.execute("DELETE FROM links WHERE id = ?", (link_id,))
        return cursor.rowcount > 0

    def delete_links_for_entry(self, entry_id: str) -> None:
        self.db.execute("DELETE FROM links WHERE entry_id = ?", (entry_id,))

    def reorder_links(self, ordered_ids: list[str]) -> None:
        now = utc_now_iso()
        for position, link_id in enumerate(ordered_ids):
            self.db.execute(
                "UPDATE links SET position = ?, updated_at = ? WHERE id = ?",
                (position, now, link_id),
            )

    def count_links(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM links", default=0) or 0)

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------
    def list_categories(self) -> list[Category]:
        rows = self.db.query_all(
            "SELECT c.*, (SELECT COUNT(*) FROM entries e WHERE e.category_id = c.id) "
            "AS entry_count FROM categories c ORDER BY c.name_key ASC"
        )
        return [_category_from_row(row) for row in rows]

    def get_category(self, category_id: str) -> Category | None:
        row = self.db.query_one("SELECT * FROM categories WHERE id = ?", (category_id,))
        return _category_from_row(row) if row else None

    def find_category_by_name(self, name: str) -> Category | None:
        row = self.db.query_one(
            "SELECT * FROM categories WHERE name_key = ?", (normalize_key(name),)
        )
        return _category_from_row(row) if row else None

    def create_category(self, name: str, *, category_id: str | None = None) -> Category:
        cid = category_id or new_id()
        self.db.execute(
            "INSERT INTO categories (id, name, name_key, created_at) VALUES (?, ?, ?, ?)",
            (cid, name, normalize_key(name), utc_now_iso()),
        )
        category = self.get_category(cid)
        assert category is not None
        return category

    def rename_category(self, category_id: str, name: str) -> bool:
        cursor = self.db.execute(
            "UPDATE categories SET name = ?, name_key = ? WHERE id = ?",
            (name, normalize_key(name), category_id),
        )
        return cursor.rowcount > 0

    def delete_category(self, category_id: str) -> bool:
        """Delete a category; entries keep working with ``category_id = NULL``."""
        cursor = self.db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        return cursor.rowcount > 0

    def category_usage(self, category_id: str) -> int:
        return int(
            self.db.scalar(
                "SELECT COUNT(*) FROM entries WHERE category_id = ?",
                (category_id,),
                default=0,
            )
            or 0
        )

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------
    def list_tags(self) -> list[Tag]:
        rows = self.db.query_all(
            "SELECT t.*, (SELECT COUNT(*) FROM entry_tags et WHERE et.tag_id = t.id) "
            "AS entry_count FROM tags t ORDER BY t.name_key ASC"
        )
        return [_tag_from_row(row) for row in rows]

    def get_tag(self, tag_id: str) -> Tag | None:
        row = self.db.query_one("SELECT * FROM tags WHERE id = ?", (tag_id,))
        return _tag_from_row(row) if row else None

    def find_tag_by_name(self, name: str) -> Tag | None:
        row = self.db.query_one("SELECT * FROM tags WHERE name_key = ?", (normalize_key(name),))
        return _tag_from_row(row) if row else None

    def create_tag(self, name: str, *, tag_id: str | None = None) -> Tag:
        tid = tag_id or new_id()
        self.db.execute(
            "INSERT INTO tags (id, name, name_key, created_at) VALUES (?, ?, ?, ?)",
            (tid, name, normalize_key(name), utc_now_iso()),
        )
        tag = self.get_tag(tid)
        assert tag is not None
        return tag

    def rename_tag(self, tag_id: str, name: str) -> bool:
        cursor = self.db.execute(
            "UPDATE tags SET name = ?, name_key = ? WHERE id = ?",
            (name, normalize_key(name), tag_id),
        )
        return cursor.rowcount > 0

    def delete_tag(self, tag_id: str) -> bool:
        cursor = self.db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        return cursor.rowcount > 0

    def list_tags_for_entry(self, entry_id: str) -> list[Tag]:
        rows = self.db.query_all(
            "SELECT t.* FROM tags t JOIN entry_tags et ON et.tag_id = t.id "
            "WHERE et.entry_id = ? ORDER BY t.name_key ASC",
            (entry_id,),
        )
        return [_tag_from_row(row) for row in rows]

    def set_entry_tags(self, entry_id: str, tag_ids: list[str]) -> None:
        self.db.execute("DELETE FROM entry_tags WHERE entry_id = ?", (entry_id,))
        seen: set[str] = set()
        for tag_id in tag_ids:
            if tag_id in seen:
                continue
            seen.add(tag_id)
            self.db.execute(
                "INSERT OR IGNORE INTO entry_tags (entry_id, tag_id) VALUES (?, ?)",
                (entry_id, tag_id),
            )

    def tag_usage(self, tag_id: str) -> int:
        return int(
            self.db.scalar(
                "SELECT COUNT(*) FROM entry_tags WHERE tag_id = ?", (tag_id,), default=0
            )
            or 0
        )

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO app_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        return self.db.scalar("SELECT value FROM app_meta WHERE key = ?", (key,), default=default)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
