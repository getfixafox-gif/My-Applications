"""Shared pytest fixtures: isolated data directories and app contexts."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Headless Qt for UI smoke tests.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.application import create_context  # noqa: E402


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture()
def context(data_dir: Path):
    ctx = create_context(data_dir)
    yield ctx
    ctx.shutdown()


@pytest.fixture()
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
