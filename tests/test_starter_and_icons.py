"""Starter catalogue and icon-fetching behaviour (no network in tests)."""

from __future__ import annotations

import json

import pytest

from app.data.starter_catalog import STARTER_ENTRIES, STARTER_VERSION
from app.services.entry_service import EntryDraft


def test_starter_catalog_is_consistent() -> None:
    assert STARTER_ENTRIES
    titles = [item.title for item in STARTER_ENTRIES]
    assert len(titles) == len(set(titles))
    for item in STARTER_ENTRIES:
        assert item.title and item.description and item.type and item.category
        assert item.links, f"{item.title} has no link"
        for link in item.links:
            assert link.url.startswith(("http://", "https://"))
            assert link.title


def test_seed_adds_entries_once(context) -> None:
    assert context.entries.count_entries() == 0
    assert context.starter.is_available()

    created = context.starter.seed()
    assert created == len(STARTER_ENTRIES)
    assert context.entries.count_entries() == len(STARTER_ENTRIES)
    assert not context.starter.is_available()

    # Second run is a no-op.
    assert context.starter.seed() == 0
    assert context.entries.count_entries() == len(STARTER_ENTRIES)


def test_seed_skips_existing_entries(context) -> None:
    context.entries.create_entry(EntryDraft(title="Steam"))
    assert context.starter.seed() == 0
    assert context.entries.count_entries() == 1
    assert not context.starter.is_available()


def test_seed_force_skips_duplicate_titles(context) -> None:
    context.entries.create_entry(EntryDraft(title="Firefox"))
    created = context.starter.seed(force=True)
    assert created == len(STARTER_ENTRIES) - 1
    titles = [item.title for item in context.entries.list_entries()]
    assert titles.count("Firefox") == 1


def test_seed_sets_links_and_tags(context) -> None:
    context.starter.seed()
    for item in STARTER_ENTRIES:
        found = [entry for entry in context.entries.list_entries() if entry.title == item.title]
        assert len(found) == 1
        detail = context.entries.get_entry(found[0].id)
        assert detail is not None
        assert [link.url for link in detail.links] == [link.url for link in item.links]
        assert detail.image_path is None
        assert {tag.name for tag in detail.tags} == set(item.tags)


def test_seed_applies_categories(context) -> None:
    context.starter.seed()
    for item in STARTER_ENTRIES:
        found = next(
            entry for entry in context.entries.list_entries() if entry.title == item.title
        )
        detail = context.entries.get_entry(found.id)
        assert detail.category_name == item.category


# -- icon fetching -------------------------------------------------------
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
    b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_normalize_site_url_rejects_non_http() -> None:
    from app.images.icon_fetcher import IconFetchError, normalize_site_url

    assert normalize_site_url("example.com") == "https://example.com"
    for bad in ("mailto:user@example.com", "ftp://example.com/file"):
        with pytest.raises(IconFetchError):
            normalize_site_url(bad)


def test_declared_icons_are_ordered() -> None:
    from app.images.icon_fetcher import _declared_icons

    page = """
    <html><head>
      <link rel="icon" href="/small.png" sizes="16x16">
      <link rel="apple-touch-icon" href="/touch.png" sizes="180x180">
      <link rel="stylesheet" href="/style.css">
      <link rel="shortcut icon" href="https://cdn.example.org/fav.ico">
    </head></html>
    """
    icons = _declared_icons(page, "https://example.com/page")
    assert icons[0] == "https://example.com/touch.png"
    assert "https://example.com/style.css" not in icons
    assert "https://cdn.example.org/fav.ico" in icons


def test_looks_like_image_sniffing() -> None:
    from app.images.icon_fetcher import _looks_like_image

    assert _looks_like_image(PNG_BYTES)
    assert _looks_like_image(b"GIF89a" + b"\x00" * 20)
    assert not _looks_like_image(b"<html>not an image</html>")
    assert not _looks_like_image(b"PK\x03\x04zip")


def test_fetch_icon_uses_favicon(monkeypatch) -> None:
    from app.images import icon_fetcher

    calls: list[str] = []

    def fake_page(url: str):
        calls.append(url)
        return []

    def fake_open(url: str, *, accept: str, limit: int):
        calls.append(url)
        if url.endswith("favicon.ico"):
            return PNG_BYTES, "image/png", url
        raise icon_fetcher.IconFetchError("нет файла")

    monkeypatch.setattr(icon_fetcher, "_page_icon_candidates", fake_page)
    monkeypatch.setattr(icon_fetcher, "_open", fake_open)

    result = icon_fetcher.fetch_icon("https://example.com")
    assert result.data == PNG_BYTES
    assert result.url == "https://example.com/favicon.ico"
    assert "https://example.com/favicon.ico" in calls


def test_fetch_icon_reports_network_failure(monkeypatch) -> None:
    from app.images import icon_fetcher

    monkeypatch.setattr(icon_fetcher, "_page_icon_candidates", lambda url: [])

    def fake_open(url: str, *, accept: str, limit: int):
        raise icon_fetcher.IconFetchError("Нет подключения к интернету или сайт недоступен")

    monkeypatch.setattr(icon_fetcher, "_open", fake_open)
    with pytest.raises(icon_fetcher.IconFetchError) as info:
        icon_fetcher.fetch_icon("https://example.com")
    assert "Нет подключения" in str(info.value)


def test_fetch_icon_rejects_html_payload(monkeypatch) -> None:
    from app.images import icon_fetcher

    monkeypatch.setattr(icon_fetcher, "_page_icon_candidates", lambda url: [])

    def fake_open(url: str, *, accept: str, limit: int):
        return b"<html>404</html>", "text/html", url

    monkeypatch.setattr(icon_fetcher, "_open", fake_open)
    with pytest.raises(icon_fetcher.IconFetchError):
        icon_fetcher.fetch_icon("https://example.com")


def test_import_bytes_stores_and_thumbnails(context) -> None:
    relative = context.images.import_bytes(PNG_BYTES)
    assert relative.startswith("entries/")
    assert context.paths.image_file(relative).is_file()
    assert context.images.resolve(relative, thumbnail=True) is not None
    assert context.images.load_bytes(relative)


def test_import_bytes_rejects_garbage(context) -> None:
    from app.images.image_processor import ImageError

    with pytest.raises(ImageError):
        context.images.import_bytes(b"definitely not an image")
    with pytest.raises(ImageError):
        context.images.import_bytes(b"")


def test_entry_created_from_image_bytes(context) -> None:
    entry = context.entries.create_entry(
        EntryDraft(title="Downloaded icon", image_action="replace", image_bytes=PNG_BYTES)
    )
    assert entry.image_path
    assert context.paths.image_file(entry.image_path).is_file()


def test_unknown_entry_title_lookup(context) -> None:
    assert context.repository.find_entry_by_title("missing") is None
    entry = context.entries.create_entry(EntryDraft(title="Findable"))
    assert context.repository.find_entry_by_title("findable") is not None
    assert context.repository.find_entry_by_title("findable").id == entry.id


def test_starter_version_is_int() -> None:
    assert isinstance(STARTER_VERSION, int) and STARTER_VERSION >= 1
    # The value must survive a JSON round-trip for archive metadata.
    assert json.loads(json.dumps({"v": STARTER_VERSION}))["v"] == STARTER_VERSION
