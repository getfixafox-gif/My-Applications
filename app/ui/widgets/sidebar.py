"""Left catalog panel: search, filters, entry list, add button."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import entries_label, tr
from app.models import EntrySummary
from app.ui.styles.theme import palette
from app.ui.widgets.common import (
    ElidedLabel,
    make_icon_button,
    placeholder_icon,
    tinted_pixmap,
)

SORT_LABELS = (
    ("updated_desc", "Сначала новые", "Newest first"),
    ("updated_asc", "Сначала старые", "Oldest first"),
    ("title_asc", "Название: А–Я", "Title: A–Z"),
    ("title_desc", "Название: Я–А", "Title: Z–A"),
    ("created_desc", "Недавно добавленные", "Recently added"),
    ("created_asc", "Давно добавленные", "Added long ago"),
)

ITEM_HEIGHT = 58


class EntryListItem(QWidget):
    """Row of the catalog: rounded icon + title + secondary line."""

    def __init__(
        self,
        summary: EntrySummary,
        icon_data: bytes | None,
        theme: str,
        secondary: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EntryListItem")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 10, 6)
        layout.setSpacing(10)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(36, 36)
        self.icon_label.setStyleSheet("background: transparent;")
        self.set_icon(icon_data, summary.title, theme)
        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        self.title_label = ElidedLabel(summary.title)
        self.title_label.setStyleSheet("font-weight: 600; background: transparent;")
        self.secondary_label = ElidedLabel(secondary)
        self.secondary_label.setObjectName("MutedLabel")
        self.secondary_label.setStyleSheet("font-size: 11px; background: transparent;")
        text_layout.addWidget(self.title_label)
        if secondary:
            text_layout.addWidget(self.secondary_label)
        else:
            self.secondary_label.hide()
        layout.addLayout(text_layout, 1)

    def set_icon(self, icon_data: bytes | None, title: str, theme: str) -> None:
        if icon_data:
            pixmap = tinted_pixmap(icon_data, 36, radius=9)
        else:
            pixmap = placeholder_icon(36, title, theme)
        if pixmap.isNull():
            pixmap = placeholder_icon(36, title, theme)
        self.icon_label.setPixmap(pixmap)


class Sidebar(QFrame):
    entryActivated = Signal(str)
    addRequested = Signal()
    settingsRequested = Signal()
    manageRequested = Signal()
    filtersChanged = Signal()

    def __init__(self, theme: str = "dark", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.theme = theme
        self._tags: list = []
        self._selected_tag_ids: set[str] = set()
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        colors = palette(self.theme)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(12)

        # -- header ------------------------------------------------------
        header = QWidget()
        header.setObjectName("SidebarHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        logo = QLabel("My Applications")
        logo.setObjectName("AppTitle")
        header_layout.addWidget(logo)
        header_layout.addStretch(1)
        self.settings_button = make_icon_button(
            "settings", colors["muted"], tr("Настройки", "Settings")
        )
        self.settings_button.clicked.connect(self.settingsRequested.emit)
        header_layout.addWidget(self.settings_button)
        outer.addWidget(header)
        self.logo = logo

        # -- catalog header ----------------------------------------------
        title_row = QWidget()
        title_layout = QHBoxLayout(title_row)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(8)
        catalog = QLabel(tr("КАТАЛОГ", "CATALOG"))
        catalog.setObjectName("CatalogTitle")
        title_layout.addWidget(catalog)
        self.count_label = QLabel(entries_label(0))
        self.count_label.setObjectName("CountLabel")
        title_layout.addWidget(self.count_label)
        title_layout.addStretch(1)
        self.manage_button = make_icon_button(
            "folder", colors["muted"], tr("Категории и теги", "Categories and tags")
        )
        self.manage_button.clicked.connect(self.manageRequested.emit)
        title_layout.addWidget(self.manage_button)
        outer.addWidget(title_row)

        # -- search ------------------------------------------------------
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("Поиск по названию…", "Search by title…"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(lambda _text: self.filtersChanged.emit())
        outer.addWidget(self.search_edit)

        # -- filters -----------------------------------------------------
        filters = QWidget()
        filter_layout = QVBoxLayout(filters)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(6)

        row_one = QHBoxLayout()
        row_one.setContentsMargins(0, 0, 0, 0)
        row_one.setSpacing(6)

        self.category_combo = QComboBox()
        self.category_combo.setToolTip(tr("Фильтр по категории", "Filter by category"))
        self.category_combo.setMinimumWidth(140)
        self.category_combo.currentIndexChanged.connect(
            lambda _index: self.filtersChanged.emit()
        )
        row_one.addWidget(self.category_combo, 1)

        self.tag_button = QToolButton()
        self.tag_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.tag_button.setText(tr("Теги", "Tags"))
        self.tag_button.setToolTip(tr("Фильтр по тегам", "Filter by tags"))
        self.tag_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tag_button.setMinimumWidth(78)
        self.tag_button.setStyleSheet(
            f"QToolButton {{ background-color: {colors['panel_alt']}; "
            f"border: 1px solid {colors['border']}; border-radius: 9px; "
            f"padding: 6px 10px; color: {colors['text']}; }}"
            f"QToolButton:hover {{ border-color: {colors['accent']}; }}"
        )
        self.tag_menu = QMenu(self.tag_button)
        self.tag_button.setMenu(self.tag_menu)
        row_one.addWidget(self.tag_button)
        filter_layout.addLayout(row_one)

        self.sort_combo = QComboBox()
        self.sort_combo.setToolTip(tr("Сортировка", "Sorting"))
        for mode, ru, en in SORT_LABELS:
            self.sort_combo.addItem(tr(ru, en), mode)
        self.sort_combo.currentIndexChanged.connect(
            lambda _index: self.filtersChanged.emit()
        )
        filter_layout.addWidget(self.sort_combo)
        outer.addWidget(filters)

        # -- list --------------------------------------------------------
        self.list_widget = QListWidget()
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setSpacing(0)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.currentItemChanged.connect(self._on_current_changed)
        outer.addWidget(self.list_widget, 1)

        self.empty_label = QLabel(
            tr("Пока нет записей.\nДобавьте первую.", "No entries yet.\nAdd the first one.")
        )
        self.empty_label.setObjectName("MutedLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.hide()
        outer.addWidget(self.empty_label)

        # -- add ---------------------------------------------------------
        self.add_button = QPushButton(tr("Добавить", "Add"))
        self.add_button.setObjectName("AddEntryButton")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.setIconSize(QSize(16, 16))
        self.add_button.clicked.connect(self.addRequested.emit)
        outer.addWidget(self.add_button)

    # ------------------------------------------------------------------
    def set_theme(self, theme: str) -> None:
        self.theme = theme
        colors = palette(theme)
        self.tag_button.setStyleSheet(
            f"QToolButton {{ background-color: {colors['panel_alt']}; "
            f"border: 1px solid {colors['border']}; border-radius: 9px; "
            f"padding: 6px 10px; color: {colors['text']}; }}"
            f"QToolButton:hover {{ border-color: {colors['accent']}; }}"
        )
        if not self.search_edit.text():
            self.search_edit.setPlaceholderText(
                tr("Поиск по названию…", "Search by title…")
            )
        self._relabel_sort()
        self.refresh_icons(theme)

    def refresh_icons(self, theme: str) -> None:
        colors = palette(theme)
        from app.ui.styles.icons import svg_icon

        self.settings_button.setIcon(svg_icon("settings", colors["muted"], 18))
        self.manage_button.setIcon(svg_icon("folder", colors["muted"], 18))
        self.add_button.setIcon(svg_icon("plus", "#ffffff", 16))
        self.search_edit.setClearButtonEnabled(True)

    def _relabel_sort(self) -> None:
        current = self.sort_combo.currentData()
        self.sort_combo.blockSignals(True)
        self.sort_combo.clear()
        for mode, ru, en in SORT_LABELS:
            self.sort_combo.addItem(tr(ru, en), mode)
        index = self.sort_combo.findData(current)
        self.sort_combo.setCurrentIndex(index if index >= 0 else 0)
        self.sort_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def set_categories(self, categories: list) -> None:
        current = self.category_combo.currentData()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem(tr("Все категории", "All categories"), None)
        for category in categories:
            self.category_combo.addItem(category.name, category.id)
        index = self.category_combo.findData(current)
        self.category_combo.setCurrentIndex(index if index >= 0 else 0)
        self.category_combo.blockSignals(False)

    def set_tags(self, tags: list) -> None:
        self._tags = list(tags)
        self._selected_tag_ids &= {tag.id for tag in tags}
        self.tag_menu.clear()
        if not tags:
            empty = QAction(tr("Нет тегов", "No tags"), self.tag_menu)
            empty.setEnabled(False)
            self.tag_menu.addAction(empty)
        else:
            clear = QAction(tr("Сбросить фильтр", "Clear filter"), self.tag_menu)
            clear.triggered.connect(self.clear_tag_filter)
            self.tag_menu.addAction(clear)
            self.tag_menu.addSeparator()
            for tag in tags:
                action = QAction(tag.name, self.tag_menu)
                action.setCheckable(True)
                action.setChecked(tag.id in self._selected_tag_ids)
                action.toggled.connect(
                    lambda checked, tag_id=tag.id: self._toggle_tag(tag_id, checked)
                )
                self.tag_menu.addAction(action)
        self._update_tag_button()

    def _toggle_tag(self, tag_id: str, checked: bool) -> None:
        if checked:
            self._selected_tag_ids.add(tag_id)
        else:
            self._selected_tag_ids.discard(tag_id)
        self._update_tag_button()
        self.filtersChanged.emit()

    def clear_tag_filter(self) -> None:
        self._selected_tag_ids.clear()
        for action in self.tag_menu.actions():
            if action.isCheckable():
                action.blockSignals(True)
                action.setChecked(False)
                action.blockSignals(False)
        self._update_tag_button()
        self.filtersChanged.emit()

    def _update_tag_button(self) -> None:
        count = len(self._selected_tag_ids)
        if count:
            self.tag_button.setText(tr(f"Теги · {count}", f"Tags · {count}"))
            self.tag_button.setProperty("active", True)
        else:
            self.tag_button.setText(tr("Теги", "Tags"))
            self.tag_button.setProperty("active", False)

    def set_count(self, count: int) -> None:
        self.count_label.setText(entries_label(count))

    def set_entries(
        self,
        entries: list[EntrySummary],
        icon_lookup,
        category_names: dict[str, str],
    ) -> None:
        selected = self.current_entry_id()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for summary in entries:
            item = QListWidgetItem(self.list_widget)
            item.setData(Qt.ItemDataRole.UserRole, summary.id)
            item.setSizeHint(QSize(0, ITEM_HEIGHT))
            secondary_parts = []
            if summary.type:
                secondary_parts.append(summary.type)
            elif summary.category_id:
                secondary_parts.append(category_names.get(summary.category_id, ""))
            widget = EntryListItem(
                summary,
                icon_lookup(summary),
                self.theme,
                " · ".join(part for part in secondary_parts if part),
            )
            self.list_widget.setItemWidget(item, widget)
        self.list_widget.blockSignals(False)

        self.empty_label.setVisible(not entries)
        self.empty_label.setText(
            tr(
                "Ничего не найдено.\nИзмените запрос или фильтры.",
                "Nothing found.\nChange the query or filters.",
            )
            if self.search_edit.text().strip() or self._selected_tag_ids
            else tr("Пока нет записей.\nДобавьте первую.", "No entries yet.\nAdd the first one.")
        )
        if selected:
            self.select_entry(selected)

    def current_entry_id(self) -> str | None:
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def select_entry(self, entry_id: str) -> None:
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == entry_id:
                self.list_widget.blockSignals(True)
                self.list_widget.setCurrentItem(item)
                self.list_widget.blockSignals(False)
                return

    def _on_current_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is not None:
            self.entryActivated.emit(current.data(Qt.ItemDataRole.UserRole))

    # -- state -----------------------------------------------------------
    def search_text(self) -> str:
        return self.search_edit.text()

    def category_id(self) -> str | None:
        return self.category_combo.currentData()

    def sort_mode(self) -> str:
        return self.sort_combo.currentData() or "updated_desc"

    def tag_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._selected_tag_ids))

    def set_sort_mode(self, mode: str) -> None:
        index = self.sort_combo.findData(mode)
        if index >= 0:
            self.sort_combo.blockSignals(True)
            self.sort_combo.setCurrentIndex(index)
            self.sort_combo.blockSignals(False)

    def focus_search(self) -> None:
        self.search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_edit.selectAll()
