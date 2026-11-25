"""Settings, paths and logging tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.paths import AppPaths, default_data_dir
from app.settings.config_manager import ConfigManager
from app.settings.defaults import DEFAULT_SETTINGS


def test_paths_created(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "storage").ensure()
    assert paths.database_file.parent.exists()
    assert paths.entries_images_dir.is_dir()
    assert paths.thumbnails_dir.is_dir()
    assert paths.backups_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.config_dir.is_dir()


def test_default_data_dir_windows(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MY_APPLICATIONS_HOME", str(tmp_path / "custom"))
    assert default_data_dir() == tmp_path / "custom"


def test_xdg_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MY_APPLICATIONS_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    expected = Path.home() / ".local" / "share" / "MyApplications"
    assert default_data_dir() == expected


def test_config_roundtrip(tmp_path: Path) -> None:
    manager = ConfigManager(tmp_path / "settings.json")
    manager.load()
    manager.update({"theme": "light", "autobackup_keep": 5, "language": "en"})
    reloaded = ConfigManager(tmp_path / "settings.json")
    reloaded.load()
    assert reloaded.get("theme") == "light"
    assert reloaded.get("autobackup_keep") == 5
    assert reloaded.get("language") == "en"


def test_config_rejects_invalid_values(tmp_path: Path) -> None:
    manager = ConfigManager(tmp_path / "settings.json")
    manager.load()
    manager.update(
        {
            "theme": "neon",
            "language": "klingon",
            "autobackup_keep": -10,
            "autobackup_interval_hours": 7,
            "log_level": "TRACE",
        }
    )
    assert manager.get("theme") == DEFAULT_SETTINGS["theme"]
    assert manager.get("language") == DEFAULT_SETTINGS["language"]
    assert manager.get("autobackup_keep") == 1
    assert manager.get("autobackup_interval_hours") in (6, 12)
    assert manager.get("log_level") == DEFAULT_SETTINGS["log_level"]


def test_corrupted_settings_recovered(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{ this is not json", encoding="utf-8")
    manager = ConfigManager(path)
    manager.load()
    assert manager.get("theme") == "dark"
    backups = list(tmp_path.glob("settings.broken-*.json"))
    assert backups, "broken settings file should be preserved"


def test_settings_unknown_keys_preserved(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"theme": "light", "custom": {"a": 1}}), encoding="utf-8")
    manager = ConfigManager(path)
    manager.load()
    assert manager.get("custom") == {"a": 1}


def test_unknown_keys_survive_save(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    manager = ConfigManager(path)
    manager.load()
    manager.update({"theme": "light"})
    manager.update({"another": [1, 2]})
    reloaded = ConfigManager(path)
    reloaded.load()
    assert reloaded.get("another") == [1, 2]


def test_storage_usage(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "store").ensure()
    (paths.entries_images_dir / "a.png").write_bytes(b"x" * 100)
    usage = paths.storage_usage()
    assert usage["images"] >= 100
    assert usage["total"] >= usage["images"]


def test_image_relative_guards(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "store").ensure()
    with pytest.raises(ValueError):
        paths.image_file("../escape.png")
    with pytest.raises(ValueError):
        paths.image_file("C:/windows/system32/x.png")
    assert paths.thumbnail_relative("entries/a.png") == "thumbnails/a.png"
