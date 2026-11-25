"""Backup, export and import tests."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.services.entry_service import EntryDraft, LinkDraft
from app.storage.backup_manager import BackupError


def _png(path: Path) -> str:
    Image.new("RGB", (120, 120), (255, 100, 0)).save(path)
    return str(path)


def _seed(context) -> None:
    category = context.categories.create("Backup cat")
    tag = context.tags.get_or_create("backup-tag")
    context.entries.create_entry(
        EntryDraft(
            title="Backed Up",
            description="multi\nline",
            type="Программа",
            category_id=category.id,
            tag_ids=[tag.id],
            links=[LinkDraft("Site", "https://example.com")],
            image_action="replace",
            image_source=_png(context.paths.root / "seed.png"),
        )
    )


def test_archive_contains_expected_structure(context, tmp_path: Path) -> None:
    _seed(context)
    archive = context.backups.create_manual_backup(tmp_path / "backup.zip")
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert {"manifest.json", "database.json", "metadata/backup_info.json"} <= names
        payload = json.loads(zf.read("database.json"))
        metadata = json.loads(zf.read("metadata/backup_info.json"))
    assert payload["format"] == "my-applications-backup"
    assert payload["entries"][0]["title"] == "Backed Up"
    assert payload["entries"][0]["image"].endswith(".png")
    assert metadata["counts"]["entries"] == 1
    assert any(name.startswith("Images/") for name in names)


def test_inspect_reports_counts_and_conflicts(context, tmp_path: Path) -> None:
    _seed(context)
    archive = context.backups.create_manual_backup(tmp_path / "b.zip")
    inspection = context.backups.inspect(archive)
    assert inspection.counts["entries"] == 1
    assert inspection.counts["images"] == 1
    assert inspection.conflicts == 1  # same entry exists locally


def test_restore_into_empty_database(context, tmp_path: Path) -> None:
    _seed(context)
    archive = context.backups.create_manual_backup(tmp_path / "b.zip")

    from app.application import create_context

    other = create_context(tmp_path / "second")
    try:
        result = other.backups.restore(archive, mode="merge")
        assert result["entries"] == 1
        entries = other.entries.list_entries()
        assert [item.title for item in entries] == ["Backed Up"]
        detail = other.entries.get_entry(entries[0].id)
        assert detail.description == "multi\nline"
        assert [link.url for link in detail.links] == ["https://example.com"]
        assert detail.image_path and other.paths.image_file(detail.image_path).exists()
    finally:
        other.shutdown()


def test_merge_does_not_duplicate(context, tmp_path: Path) -> None:
    _seed(context)
    archive = context.backups.create_manual_backup(tmp_path / "b.zip")
    before = context.entries.count_entries()
    result = context.backups.restore(archive, mode="merge")
    assert context.entries.count_entries() == before
    assert result["entries"] == 0
    assert result["skipped"] >= 1


def test_replace_mode_wipes_then_restores(context, tmp_path: Path) -> None:
    _seed(context)
    archive = context.backups.create_manual_backup(tmp_path / "b.zip")
    context.entries.create_entry(EntryDraft(title="Will disappear"))
    assert context.entries.count_entries() == 2

    context.backups.restore(archive, mode="replace")
    titles = [item.title for item in context.entries.list_entries()]
    assert titles == ["Backed Up"]


def test_invalid_zip_rejected(context, tmp_path: Path) -> None:
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"PK\x03\x04 definitely broken")
    with pytest.raises(BackupError):
        context.backups.inspect(broken)


def test_zip_without_database_json_rejected(context, tmp_path: Path) -> None:
    path = tmp_path / "incomplete.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "my-applications-backup"}))
    with pytest.raises(BackupError):
        context.backups.inspect(path)


def test_zip_with_malformed_json_rejected(context, tmp_path: Path) -> None:
    path = tmp_path / "malformed.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "my-applications-backup"}))
        zf.writestr("database.json", "{not json")
    with pytest.raises(BackupError):
        context.backups.inspect(path)


def test_path_traversal_rejected(context, tmp_path: Path) -> None:
    path = tmp_path / "evil.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "my-applications-backup"}))
        zf.writestr("database.json", json.dumps({"entries": []}))
        zf.writestr("../../evil.txt", "boom")
    with pytest.raises(BackupError):
        context.backups.inspect(path)


def test_newer_format_rejected(context, tmp_path: Path) -> None:
    path = tmp_path / "future.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "my-applications-backup"}))
        zf.writestr(
            "database.json",
            json.dumps({"format_version": 999, "entries": [], "categories": [], "tags": []}),
        )
    with pytest.raises(BackupError):
        context.backups.inspect(path)


def test_missing_image_in_archive_rejected(context, tmp_path: Path) -> None:
    path = tmp_path / "noimage.zip"
    payload = {
        "format": "my-applications-backup",
        "format_version": 1,
        "entries": [{"id": "e1", "title": "Ghost", "image": "missing.png", "links": [], "tags": []}],
        "categories": [],
        "tags": [],
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "my-applications-backup"}))
        zf.writestr("database.json", json.dumps(payload))
    with pytest.raises(BackupError):
        context.backups.inspect(path)


def test_failed_import_keeps_existing_data(context, tmp_path: Path) -> None:
    context.entries.create_entry(EntryDraft(title="Keep me"))
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "my-applications-backup"}))
        zf.writestr("database.json", json.dumps({"entries": [{"id": "", "title": ""}]}))
    with pytest.raises(BackupError):
        context.backups.restore(path, mode="replace")
    assert [item.title for item in context.entries.list_entries()] == ["Keep me"]


def test_auto_backup_rotation(context) -> None:
    created = []
    for _ in range(4):
        created.append(context.backups.manager.create_database_backup(prefix="t"))
    kept = context.backups.manager.rotate_auto_backups(2)
    remaining = context.backups.list_auto_backups()
    assert len(created) == 4
    assert len(remaining) == 2
    assert len(kept) == 2


def test_backup_due_logic(context) -> None:
    from datetime import datetime, timedelta, timezone

    context.config.update({"autobackup_enabled": True, "autobackup_interval_hours": 24})
    context.config.update({"last_backup_at": None})
    assert context.backups.is_due()

    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    context.config.update({"last_backup_at": recent})
    assert not context.backups.is_due()

    old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(timespec="seconds")
    context.config.update({"last_backup_at": old})
    assert context.backups.is_due()

    context.config.update({"autobackup_enabled": False})
    assert not context.backups.is_due()


def test_run_auto_backup_creates_snapshot(context) -> None:
    context.config.update({"autobackup_enabled": True, "last_backup_at": None, "autobackup_keep": 3})
    path = context.backups.run_auto_backup()
    assert path is not None and Path(path).exists()
    assert context.config.get("last_backup_at")
    assert context.backups.run_auto_backup() is None
