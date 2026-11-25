"""Dialog for managing categories and tags."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr


class _EditableList(QWidget):
    """List of names with add / rename / delete actions."""

    def __init__(
        self,
        *,
        title: str,
        add_label: str,
        theme: str,
        on_create,
        on_rename,
        on_delete,
        usage_label,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.on_create = on_create
        self.on_rename = on_rename
        self.on_delete = on_delete
        self.usage_label = usage_label
        self.theme = theme
        self._items: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QLabel(title)
        header.setObjectName("SectionTitle")
        layout.addWidget(header)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(200)
        layout.addWidget(self.list_widget, 1)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.input = QLineEdit()
        self.input.setPlaceholderText(add_label)
        self.input.returnPressed.connect(self._create)
        row.addWidget(self.input, 1)
        add = QPushButton(tr("Добавить", "Add"))
        add.setObjectName("PrimaryButton")
        add.clicked.connect(self._create)
        row.addWidget(add)
        layout.addLayout(row)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        rename = QPushButton(tr("Переименовать", "Rename"))
        rename.clicked.connect(self._rename)
        actions.addWidget(rename)
        remove = QPushButton(tr("Удалить", "Delete"))
        remove.setObjectName("DangerButton")
        remove.clicked.connect(self._delete)
        actions.addWidget(remove)
        actions.addStretch(1)
        layout.addLayout(actions)

    def set_items(self, items: list) -> None:
        self._items = list(items)
        current = self.list_widget.currentRow()
        self.list_widget.clear()
        for item in self._items:
            display = f"{item.name}   ·   {self.usage_label(item)}"
            row = QListWidgetItem(display)
            row.setData(Qt.ItemDataRole.UserRole, item.id)
            self.list_widget.addItem(row)
        if self._items:
            self.list_widget.setCurrentRow(min(max(0, current), len(self._items) - 1))

    def _selected(self):
        item = self.list_widget.currentItem()
        if item is None:
            return None
        item_id = item.data(Qt.ItemDataRole.UserRole)
        return next((entry for entry in self._items if entry.id == item_id), None)

    def _create(self) -> None:
        name = self.input.text().strip()
        if not name:
            return
        if self.on_create(name):
            self.input.clear()

    def _rename(self) -> None:
        selected = self._selected()
        if selected is None:
            self._warn(tr("Выберите элемент списка", "Select an item"))
            return
        name, ok = QInputDialog.getText(
            self, tr("Переименовать", "Rename"), tr("Новое название:", "New name:"), text=selected.name
        )
        if ok and name.strip():
            self.on_rename(selected, name.strip())

    def _delete(self) -> None:
        selected = self._selected()
        if selected is None:
            self._warn(tr("Выберите элемент списка", "Select an item"))
            return
        self.on_delete(selected)

    def _warn(self, message: str) -> None:
        QMessageBox.information(self, tr("Внимание", "Attention"), message)


class ReferenceDialog(QDialog):
    """Categories + tags manager used from the sidebar."""

    def __init__(self, context, theme: str = "dark", parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.theme = theme
        self.setWindowTitle(tr("Категории и теги", "Categories and tags"))
        self.setModal(True)
        self.setMinimumSize(540, 520)
        self._build()
        self._reload()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        self.tabs = QComboBox()
        self.tabs.addItem(tr("Категории", "Categories"), "categories")
        self.tabs.addItem(tr("Теги", "Tags"), "tags")
        self.tabs.currentIndexChanged.connect(self._switch)
        layout.addWidget(self.tabs)

        self.categories_widget = _EditableList(
            title=tr("КАТЕГОРИИ", "CATEGORIES"),
            add_label=tr("Название новой категории", "New category name"),
            theme=self.theme,
            on_create=self._create_category,
            on_rename=self._rename_category,
            on_delete=self._delete_category,
            usage_label=lambda item: tr(f"{item.entry_count} записей", f"{item.entry_count} entries"),
        )
        self.tags_widget = _EditableList(
            title=tr("ТЕГИ", "TAGS"),
            add_label=tr("Название нового тега", "New tag name"),
            theme=self.theme,
            on_create=self._create_tag,
            on_rename=self._rename_tag,
            on_delete=self._delete_tag,
            usage_label=lambda item: tr(f"{item.entry_count} записей", f"{item.entry_count} entries"),
        )
        layout.addWidget(self.categories_widget, 1)
        layout.addWidget(self.tags_widget, 1)
        self.tags_widget.hide()

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setObjectName("ErrorLabel")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        close = QPushButton(tr("Готово", "Done"))
        close.setObjectName("PrimaryButton")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)

    def _switch(self) -> None:
        show_categories = self.tabs.currentData() == "categories"
        self.categories_widget.setVisible(show_categories)
        self.tags_widget.setVisible(not show_categories)

    def _reload(self) -> None:
        self.categories_widget.set_items(self.context.categories.list_categories())
        self.tags_widget.set_items(self.context.tags.list_tags())

    # -- callbacks -------------------------------------------------------
    def _error(self, exc: Exception) -> None:
        """Show validation errors inline: no modal dialog blocks the flow."""
        self.error_label.setText(str(exc))
        self.error_label.show()

    def _clear_error(self) -> None:
        self.error_label.clear()
        self.error_label.hide()

    def _create_category(self, name: str) -> bool:
        self._clear_error()
        try:
            self.context.categories.create(name)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            self._error(exc)
            return False
        self._reload()
        return True

    def _rename_category(self, category, name: str) -> None:
        self._clear_error()
        try:
            self.context.categories.rename(category.id, name)
        except Exception as exc:  # noqa: BLE001
            self._error(exc)
            return
        self._reload()

    def _delete_category(self, category) -> None:
        usage = self.context.categories.usage(category.id)
        message = tr(
            f"Удалить категорию «{category.name}»?",
            f"Delete category “{category.name}”?",
        )
        if usage:
            message += "\n\n" + tr(
                f"Записи ({usage}) останутся в каталоге без категории.",
                f"{usage} entries will stay in the catalog without a category.",
            )
        if QMessageBox.question(
            self,
            tr("Удаление категории", "Delete category"),
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.context.categories.delete(category.id)
        except Exception as exc:  # noqa: BLE001
            self._error(exc)
            return
        self._reload()

    def _create_tag(self, name: str) -> bool:
        self._clear_error()
        try:
            self.context.tags.create(name)
        except Exception as exc:  # noqa: BLE001
            self._error(exc)
            return False
        self._reload()
        return True

    def _rename_tag(self, tag, name: str) -> None:
        self._clear_error()
        try:
            self.context.tags.rename(tag.id, name)
        except Exception as exc:  # noqa: BLE001
            self._error(exc)
            return
        self._reload()

    def _delete_tag(self, tag) -> None:
        usage = self.context.tags.usage(tag.id)
        if QMessageBox.question(
            self,
            tr("Удаление тега", "Delete tag"),
            tr(
                f"Удалить тег «{tag.name}»?" + (f"\n\nОн будет убран из {usage} записей." if usage else ""),
                f"Delete tag “{tag.name}”?" + (f"\n\nIt will be removed from {usage} entries." if usage else ""),
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.context.tags.delete(tag.id)
        except Exception as exc:  # noqa: BLE001
            self._error(exc)
            return
        self._reload()
