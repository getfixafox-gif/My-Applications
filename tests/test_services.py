"""Service layer tests: entries, images, categories, tags, search."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.database import EntryFilter
from app.database.connection import DatabaseError
from app.services.entry_service import EntryDraft, LinkDraft
from app.utils.validators import ValidationError


@pytest.fixture()
def image_file(tmp_path: Path) -> Path:
    path = tmp_path / "icon.png"
    Image.new("RGB", (300, 150), (30, 120, 200)).save(path)
    return path


def test_create_entry_with_everything(context, image_file: Path) -> None:
    category = context.categories.create("Тест")
    tag = context.tags.get_or_create("тег")
    draft = EntryDraft(
        title="  My App ",
        description="line1\nline2",
        type="Программа",
        category_id=category.id,
        tag_ids=[tag.id],
        links=[
            LinkDraft("Site", "example.com"),
            LinkDraft("Docs", "https://docs.example.com"),
        ],
        image_action="replace",
        image_source=str(image_file),
    )
    entry = context.entries.create_entry(draft)

    assert entry.title == "My App"
    assert entry.category_id == category.id
    assert [link.url for link in entry.links] == [
        "https://example.com",
        "https://docs.example.com",
    ]
    assert [t.name for t in entry.tags] == ["тег"]
    assert entry.image_path and entry.image_path.startswith("entries/")
    assert context.paths.image_file(entry.image_path).is_file()
    assert context.paths.thumbnail_file(entry.image_path).is_file()


def test_create_requires_title(context) -> None:
    with pytest.raises(ValidationError):
        context.entries.create_entry(EntryDraft(title="   "))


def test_invalid_link_blocks_saving(context) -> None:
    draft = EntryDraft(title="Bad", links=[LinkDraft("x", "javascript:alert(1)")])
    with pytest.raises(ValidationError):
        context.entries.create_entry(draft)
    assert context.entries.count_entries() == 0


def test_duplicate_links_are_deduplicated(context) -> None:
    draft = EntryDraft(
        title="Dup",
        links=[LinkDraft("A", "example.com"), LinkDraft("B", "https://example.com")],
    )
    entry = context.entries.create_entry(draft)
    assert len(entry.links) == 1


def test_update_entry_syncs_links(context) -> None:
    entry = context.entries.create_entry(
        EntryDraft(title="Sync", links=[LinkDraft("one", "https://one.example")])
    )
    first_id = entry.links[0].id
    draft = EntryDraft(
        title="Sync 2",
        links=[
            LinkDraft("two", "https://two.example"),
            LinkDraft("one", "https://one.example", id=first_id),
        ],
    )
    updated = context.entries.update_entry(entry.id, draft)
    assert updated.title == "Sync 2"
    assert [link.title for link in updated.links] == ["two", "one"]


def test_removing_link_from_draft_deletes_it(context) -> None:
    entry = context.entries.create_entry(
        EntryDraft(
            title="Many",
            links=[LinkDraft("a", "https://a.example"), LinkDraft("b", "https://b.example")],
        )
    )
    draft = EntryDraft(
        title="Many",
        links=[LinkDraft("b", "https://b.example", id=entry.links[1].id)],
    )
    updated = context.entries.update_entry(entry.id, draft)
    assert [link.url for link in updated.links] == ["https://b.example"]


def test_delete_entry_removes_own_image(context, image_file: Path) -> None:
    entry = context.entries.create_entry(
        EntryDraft(title="Img", image_action="replace", image_source=str(image_file))
    )
    stored = context.paths.image_file(entry.image_path)
    assert stored.exists()
    context.entries.delete_entry(entry.id)
    assert not stored.exists()


def test_shared_image_is_not_deleted(context) -> None:
    """Two entries may point to the same stored file; it must survive."""
    first = context.entries.create_entry(EntryDraft(title="One"))
    second = context.entries.create_entry(EntryDraft(title="Two"))
    shared = context.entries.images
    relative = shared.import_image(_make_png(context, "shared.png"))
    context.database.execute(
        "UPDATE entries SET image_path = ? WHERE id IN (?, ?)",
        (relative, first.id, second.id),
    )
    path = context.paths.image_file(relative)
    assert path.exists()

    context.entries.delete_entry(first.id)
    assert path.exists(), "image still used by another entry"

    context.entries.delete_entry(second.id)
    assert not path.exists(), "last reference removed the file"


def _make_png(context, name: str) -> Path:
    path = context.paths.root / name
    Image.new("RGB", (64, 64), (10, 200, 100)).save(path)
    return path


def test_image_replacement_deletes_old_file(context) -> None:
    first = context.entries.create_entry(
        EntryDraft(title="A", image_action="replace", image_source=str(_make_png(context, "a.png")))
    )
    old = context.paths.image_file(first.image_path)
    context.entries.set_image(first.id, _make_png(context, "b.png"))
    entry = context.entries.get_entry(first.id)
    assert entry.image_path != first.image_path
    assert not old.exists()
    assert context.paths.image_file(entry.image_path).exists()


def test_remove_image(context) -> None:
    entry = context.entries.create_entry(
        EntryDraft(title="R", image_action="replace", image_source=str(_make_png(context, "r.png")))
    )
    context.entries.remove_image(entry.id)
    entry = context.entries.get_entry(entry.id)
    assert entry.image_path is None


def test_corrupted_image_is_rejected(context, tmp_path: Path) -> None:
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")
    from app.images.image_processor import ImageError

    with pytest.raises(ImageError):
        context.images.import_image(broken)


def test_missing_image_handled_gracefully(context) -> None:
    entry = context.entries.create_entry(EntryDraft(title="No icon"))
    assert context.images.load_bytes(entry.image_path) is None
    assert context.images.load_bytes("entries/does-not-exist.png") is None
    assert context.images.resolve("../../etc/passwd") is None


def test_category_operations(context) -> None:
    category = context.categories.create("Уникальная")
    with pytest.raises(ValidationError):
        context.categories.create("уникальная")
    entry = context.entries.create_entry(
        EntryDraft(title="With category", category_id=category.id)
    )
    renamed = context.categories.rename(category.id, "Новая")
    assert renamed.name == "Новая"
    assert context.categories.usage(category.id) == 1
    context.categories.delete(category.id)
    assert context.entries.get_entry(entry.id).category_id is None


def test_tag_operations(context) -> None:
    tag = context.tags.create("graphics")
    assert context.tags.get_or_create("GRAPHICS").id == tag.id
    entry = context.entries.create_entry(EntryDraft(title="Tagged", tag_ids=[tag.id]))
    assert context.tags.usage(tag.id) == 1
    context.tags.rename(tag.id, "design")
    assert context.tags.get(tag.id).name == "design"
    context.tags.delete(tag.id)
    assert context.entries.get_entry(entry.id).tags == []


def test_search_service_filters(context) -> None:
    category = context.categories.create("Cat")
    tag = context.tags.get_or_create("searchable")
    context.entries.create_entry(
        EntryDraft(title="Alpha Game", category_id=category.id, tag_ids=[tag.id])
    )
    context.entries.create_entry(EntryDraft(title="Beta Tool"))

    assert len(context.search.search("alpha")) == 1
    assert len(context.search.search("")) == 2
    assert len(context.search.search("", category_id=category.id)) == 1
    assert len(context.search.search("", tag_ids=(tag.id,))) == 1
    assert context.search.search("gamma") == []


def test_orphan_image_cleanup(context) -> None:
    orphan = context.paths.entries_images_dir / "orphan.png"
    orphan.write_bytes(b"x")
    used = context.entries.create_entry(
        EntryDraft(title="Used", image_action="replace", image_source=str(_make_png(context, "u.png")))
    )
    removed = context.entries.cleanup_orphan_images()
    assert removed >= 1
    assert not orphan.exists()
    assert context.paths.image_file(used.image_path).exists()


def test_update_missing_entry_raises(context) -> None:
    with pytest.raises(ValidationError):
        context.entries.update_entry("missing-id", EntryDraft(title="X"))


def test_database_error_is_wrapped(context) -> None:
    context.database.close()
    with pytest.raises(DatabaseError):
        context.entries.list_entries(EntryFilter())
