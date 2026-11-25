"""Tag chip editor widget."""

from __future__ import annotations

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import (
    QCompleter,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.styles.theme import palette
from app.ui.widgets.common import FlowLayout
from app.i18n import tr


class TagChipWidget(QFrame):
    removed = Signal(str)

    def __init__(self, tag_id: str, name: str, theme: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tag_id = tag_id
        self.setObjectName("TagChip")
        colors = palette(theme)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)
        label = QLabel(f"#{name}")
        label.setStyleSheet("background: transparent;")
        layout.addWidget(label)
        close = QPushButton("×")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setFixedSize(16, 16)
        close.setToolTip(tr("Убрать тег", "Remove tag"))
        close.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: %s; font-size: 13px; padding: 0; }"
            "QPushButton:hover { color: %s; }" % (colors["muted"], colors["danger"])
        )
        close.clicked.connect(lambda: self.removed.emit(self.tag_id))
        layout.addWidget(close)


class TagEditor(QWidget):
    """Chips plus an inline input with completion over existing tags."""

    changed = Signal()

    def __init__(self, theme: str = "dark", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = theme
        self._chips: list[TagChipWidget] = []
        self._selected: dict[str, str] = {}
        self._suggestions: list[str] = []
        self._resolver = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.chips_container = QWidget()
        self.chips_flow = FlowLayout(self.chips_container, spacing=6)
        layout.addWidget(self.chips_container)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.input = QLineEdit()
        self.input.setPlaceholderText(tr("Добавить тег и нажать Enter…", "Add a tag and press Enter…"))
        self.input.returnPressed.connect(self._commit_input)
        row.addWidget(self.input, 1)
        self.add_button = QPushButton(tr("Добавить", "Add"))
        self.add_button.clicked.connect(self._commit_input)
        row.addWidget(self.add_button)
        layout.addLayout(row)

        self.completer = QCompleter(self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.setModel(QStringListModel([], self.completer))
        self.input.setCompleter(self.completer)

    # ------------------------------------------------------------------
    def set_suggestions(self, names: list[str]) -> None:
        self._suggestions = list(names)
        model = self.completer.model()
        if isinstance(model, QStringListModel):
            model.setStringList(self._suggestions)

    def set_resolver(self, resolver) -> None:
        """``resolver(name) -> (id, name)`` used to create tags on demand."""
        self._resolver = resolver

    def set_tags(self, tags: list[tuple[str, str]]) -> None:
        self._selected.clear()
        for tag_id, name in tags:
            self._selected[tag_id] = name
        self._rebuild()

    def tag_ids(self) -> list[str]:
        return list(self._selected.keys())

    def add_tag(self, tag_id: str, name: str) -> None:
        if tag_id and tag_id not in self._selected:
            self._selected[tag_id] = name
            self._rebuild()
            self.changed.emit()

    def _commit_input(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        parts = [part.strip() for part in text.split(",") if part.strip()]
        added = False
        for part in parts:
            result = None
            if callable(self._resolver):
                try:
                    result = self._resolver(part)
                except Exception:  # noqa: BLE001 - validation errors surface upstream
                    result = None
            if result:
                tag_id, name = result
            else:
                tag_id, name = part.lower(), part
            if tag_id and tag_id not in self._selected:
                self._selected[tag_id] = name
                added = True
        self.input.clear()
        if added:
            self._rebuild()
            self.changed.emit()

    def _remove(self, tag_id: str) -> None:
        self._selected.pop(tag_id, None)
        self._rebuild()
        self.changed.emit()

    def _rebuild(self) -> None:
        while self.chips_flow.count():
            item = self.chips_flow.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._chips.clear()
        for tag_id, name in sorted(self._selected.items(), key=lambda item: item[1].lower()):
            chip = TagChipWidget(tag_id, name, self.theme)
            chip.removed.connect(self._remove)
            self.chips_flow.addWidget(chip)
            self._chips.append(chip)
        self.chips_container.setVisible(bool(self._chips))
