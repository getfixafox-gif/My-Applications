"""Domain models (plain dataclasses, no database access)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Category:
    id: str
    name: str
    created_at: str = ""
    entry_count: int = 0

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.name


@dataclass(slots=True)
class Tag:
    id: str
    name: str
    created_at: str = ""
    entry_count: int = 0

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.name


@dataclass(slots=True)
class Link:
    id: str
    entry_id: str
    title: str
    url: str
    position: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class Entry:
    id: str
    title: str
    description: str = ""
    type: str = ""
    category_id: str | None = None
    image_path: str | None = None
    created_at: str = ""
    updated_at: str = ""
    links: list[Link] = field(default_factory=list)
    tags: list[Tag] = field(default_factory=list)
    category_name: str | None = None

    @property
    def has_image(self) -> bool:
        return bool(self.image_path)


@dataclass(slots=True)
class EntrySummary:
    """Lightweight entry representation used by the catalog list."""

    id: str
    title: str
    image_path: str | None
    type: str
    updated_at: str
    category_id: str | None = None
