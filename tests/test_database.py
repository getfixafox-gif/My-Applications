"""Database and repository tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database import Database, EntryFilter, Repository, initialize_schema
from app.database.migrations import initialize_schema as init_again


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    database = Database(tmp_path / "db.sqlite")
    initialize_schema(database)
    yield Repository(database)
    database.close()


def test_schema_and_version(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")
    version = initialize_schema(database)
    assert version >= 1
    assert database.user_version() == version
    # Running again must be idempotent.
    assert init_again(database) == version
    assert database.integrity_check()
    database.close()


def test_entry_crud(repo: Repository) -> None:
    entry = repo.create_entry(title="Alpha", description="desc", type="App")
    assert repo.count_entries() == 1
    fetched = repo.get_entry(entry.id)
    assert fetched is not None and fetched.title == "Alpha"

    repo.update_entry(entry.id, title="Beta", description="new")
    assert repo.get_entry(entry.id).title == "Beta"

    assert repo.delete_entry(entry.id)
    assert repo.count_entries() == 0
    assert repo.get_entry(entry.id) is None


def test_links_ordering_and_cascade(repo: Repository) -> None:
    entry = repo.create_entry(title="Links")
    first = repo.add_link(entry.id, "One", "https://one.example")
    second = repo.add_link(entry.id, "Two", "https://two.example")
    assert [link.title for link in repo.list_links(entry.id)] == ["One", "Two"]
    assert first.position == 0 and second.position == 1

    repo.reorder_links([second.id, first.id])
    assert [link.id for link in repo.list_links(entry.id)] == [second.id, first.id]

    repo.delete_entry(entry.id)
    assert repo.list_links(entry.id) == []


def test_categories_and_tags(repo: Repository) -> None:
    category = repo.create_category("Games")
    tag_a = repo.create_tag("RPG")
    tag_b = repo.create_tag("Indie")
    entry = repo.create_entry(title="Game", category_id=category.id)
    repo.set_entry_tags(entry.id, [tag_a.id, tag_b.id, tag_a.id])

    detail = repo.get_entry(entry.id)
    assert detail.category_name == "Games"
    assert {tag.name for tag in detail.tags} == {"RPG", "Indie"}
    assert repo.list_tags()[0].entry_count == 1

    repo.delete_category(category.id)
    assert repo.get_entry(entry.id).category_id is None

    repo.delete_tag(tag_a.id)
    assert [tag.name for tag in repo.get_entry(entry.id).tags] == ["Indie"]


def test_unique_category_names_case_insensitive(repo: Repository) -> None:
    repo.create_category("Tools")
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_category("tools")


def test_search_and_sorting(repo: Repository) -> None:
    repo.create_entry(title="Visual Studio Code")
    repo.create_entry(title="vim")
    repo.create_entry(title="100% Pure")
    assert [item.title for item in repo.list_entries(EntryFilter(search="visual"))] == [
        "Visual Studio Code"
    ]
    # LIKE wildcards must be escaped: "%" searches the literal character.
    assert [item.title for item in repo.list_entries(EntryFilter(search="%"))] == ["100% Pure"]
    assert repo.list_entries(EntryFilter(search="_")) == []
    assert [item.title for item in repo.list_entries(EntryFilter(sort="title_asc"))] == [
        "100% Pure",
        "vim",
        "Visual Studio Code",
    ]


def test_filter_by_multiple_tags_requires_all(repo: Repository) -> None:
    a = repo.create_tag("a")
    b = repo.create_tag("b")
    both = repo.create_entry(title="both")
    repo.set_entry_tags(both.id, [a.id, b.id])
    only = repo.create_entry(title="only")
    repo.set_entry_tags(only.id, [a.id])

    result = repo.list_entries(EntryFilter(tag_ids=(a.id, b.id)))
    assert [item.title for item in result] == ["both"]


def test_foreign_keys_enforced(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")
    initialize_schema(database)
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO links (id, entry_id, title, url, position, created_at, updated_at)"
            " VALUES ('l', 'missing', 't', 'u', 0, 'now', 'now')"
        )
    database.close()


def test_transaction_rollback(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")
    initialize_schema(database)
    repo = Repository(database)
    with pytest.raises(RuntimeError):
        with database.transaction():
            repo.create_entry(title="Ghost")
            raise RuntimeError("boom")
    assert repo.count_entries() == 0
    database.close()


def test_meta_storage(repo: Repository) -> None:
    repo.set_meta("k", "v1")
    repo.set_meta("k", "v2")
    assert repo.get_meta("k") == "v2"
    assert repo.get_meta("missing", "fallback") == "fallback"


def test_corrupted_database_is_rejected(tmp_path: Path) -> None:
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"this is definitely not sqlite")
    database = Database(broken)
    with pytest.raises(Exception):
        initialize_schema(database)
    database.close()
