"""Search helpers built on top of the entry filter."""

from __future__ import annotations

from app.database.repository import EntryFilter
from app.models import EntrySummary
from app.services.entry_service import EntryService


class SearchService:
    """Thin façade that keeps search semantics in one place."""

    def __init__(self, entries: EntryService) -> None:
        self.entries = entries

    def search(
        self,
        text: str = "",
        *,
        category_id: str | None = None,
        tag_ids: tuple[str, ...] = (),
        sort: str = "updated_desc",
    ) -> list[EntrySummary]:
        filters = EntryFilter(
            search=text.strip(),
            category_id=category_id or None,
            tag_ids=tuple(tag_ids),
            sort=sort,
        )
        return self.entries.list_entries(filters)
