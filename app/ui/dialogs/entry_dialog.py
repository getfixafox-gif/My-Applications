"""Entry create / edit dialog with live image preview and link management."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from app.models import Entry
from app.services.entry_service import EntryDraft, LinkDraft
from app.ui.dialogs.link_dialog import ask_link
from app.ui.styles.theme import palette
from app.ui.widgets.common import ElidedLabel, make_icon_button, placeholder_icon
from app.ui.widgets.tag_editor import TagEditor
from app.utils.validators import ValidationError, clean_title, MAX_TITLE

IMAGE_FILTER = "Изображения (*.png *.jpg *.jpeg *.webp *.ico *.gif *.bmp *.tif *.tiff)"


class LinkEditRow(QWidget):
    changed = None

    def __init__(self, draft: LinkDraft, colors: dict, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.draft = draft
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        number = QLabel(str(index + 1))
        number.setFixedWidth(18)
        number.setStyleSheet(f"color: {colors['muted']};")
        layout.addWidget(number)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)
        title = ElidedLabel(draft.title)
        title.setStyleSheet("font-weight: 600;")
        url = ElidedLabel(draft.url)
        url.setObjectName("MutedLabel")
        url.setStyleSheet("font-size: 11px;")
        text_layout.addWidget(title)
        text_layout.addWidget(url)
        layout.addLayout(text_layout, 1)

        up = make_icon_button("chevron-up", colors["muted"], tr("Выше", "Move up"), size=24, icon_size=15)
        up.clicked.connect(lambda: self._move(-1))
        layout.addWidget(up)
        down = make_icon_button("chevron-down", colors["muted"], tr("Ниже", "Move down"), size=24, icon_size=15)
        down.clicked.connect(lambda: self._move(1))
        layout.addWidget(down)
        edit = make_icon_button("edit", colors["muted"], tr("Изменить", "Edit"), size=24, icon_size=14)
        edit.clicked.connect(self._edit)
        layout.addWidget(edit)
        remove = make_icon_button("trash", colors["muted"], tr("Удалить", "Delete"), size=24, icon_size=14)
        remove.clicked.connect(self._remove)
        layout.addWidget(remove)

        self.reorder_callback = None
        self.edit_callback = None
        self.delete_callback = None

    def _move(self, delta: int) -> None:
        if callable(self.reorder_callback):
            self.reorder_callback(self.draft, delta)

    def _edit(self) -> None:
        if callable(self.edit_callback):
            self.edit_callback(self.draft)

    def _remove(self) -> None:
        if callable(self.delete_callback):
            self.delete_callback(self.draft)


class EntryDialog(QDialog):
    def __init__(
        self,
        theme: str = "dark",
        *,
        context=None,
        entry: Entry | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.theme = theme
        self.context = context
        self.entry = entry
        self._links: list[LinkDraft] = []
        self._tag_ids: list[str] = []
        self._image_action = "keep"
        self._image_source: str | None = None
        self._current_image: str | None = entry.image_path if entry else None
        self.setModal(True)
        self.setMinimumSize(600, 680)
        self.setWindowTitle(
            tr("Редактирование записи", "Edit entry") if entry else tr("Новая запись", "New entry")
        )
        self._build()
        self._populate()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        colors = palette(self.theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(22, 20, 22, 18)
        self.content_layout.setSpacing(14)

        # -- image header ------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(14)
        self.preview = QLabel()
        self.preview.setFixedSize(88, 88)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)

        image_buttons = QVBoxLayout()
        image_buttons.setSpacing(6)
        self.image_button = QPushButton(tr("Выбрать изображение…", "Choose image…"))
        self.image_button.clicked.connect(self._choose_image)
        image_buttons.addWidget(self.image_button)
        self.image_reset_button = QPushButton(tr("Без изображения", "No image"))
        self.image_reset_button.setObjectName("DangerButton")
        self.image_reset_button.clicked.connect(self._clear_image)
        image_buttons.addWidget(self.image_reset_button)
        hint = QLabel(tr("PNG, JPG, WEBP, ICO", "PNG, JPG, WEBP, ICO"))
        hint.setObjectName("MutedLabel")
        hint.setStyleSheet("font-size: 11px;")
        image_buttons.addWidget(hint)
        image_buttons.addStretch(1)
        header.addLayout(image_buttons, 1)
        self.content_layout.addLayout(header)

        # -- main form ---------------------------------------------------
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.title_edit = QLineEdit()
        self.title_edit.setMaxLength(MAX_TITLE)
        self.title_edit.setPlaceholderText(tr("Обязательное поле", "Required field"))
        form.addRow(tr("Название *", "Title *"), self.title_edit)

        self.type_edit = QLineEdit()
        self.type_edit.setPlaceholderText(tr("Например: Программа, Игра, Сайт", "e.g. App, Game, Website"))
        form.addRow(tr("Тип объекта", "Object type"), self.type_edit)

        self.category_combo = QComboBox()
        form.addRow(tr("Категория", "Category"), self.category_combo)

        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText(
            tr("Многострочное описание…", "Multiline description…")
        )
        self.description_edit.setMinimumHeight(130)
        form.addRow(tr("Описание", "Description"), self.description_edit)
        self.content_layout.addLayout(form)

        # -- tags --------------------------------------------------------
        tags_label = QLabel(tr("ТЕГИ", "TAGS"))
        tags_label.setObjectName("SectionTitle")
        self.content_layout.addWidget(tags_label)
        self.tag_editor = TagEditor(self.theme)
        self.content_layout.addWidget(self.tag_editor)

        # -- links -------------------------------------------------------
        links_header = QHBoxLayout()
        links_label = QLabel(tr("ССЫЛКИ", "LINKS"))
        links_label.setObjectName("SectionTitle")
        links_header.addWidget(links_label)
        links_header.addStretch(1)
        add_link = QPushButton(tr("＋ Добавить ссылку", "＋ Add link"))
        add_link.setObjectName("ChipButton")
        add_link.clicked.connect(self._add_link)
        links_header.addWidget(add_link)
        self.content_layout.addLayout(links_header)

        self.links_container = QWidget()
        self.links_layout = QVBoxLayout(self.links_container)
        self.links_layout.setContentsMargins(0, 0, 0, 0)
        self.links_layout.setSpacing(8)
        self.content_layout.addWidget(self.links_container)
        self.no_links_label = QLabel(tr("Ссылок пока нет", "No links yet"))
        self.no_links_label.setObjectName("MutedLabel")
        self.content_layout.addWidget(self.no_links_label)
        self.content_layout.addStretch(1)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # -- footer ------------------------------------------------------
        footer = QWidget()
        footer.setStyleSheet(f"background-color: {colors['panel']};")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(22, 12, 22, 14)
        footer_layout.setSpacing(8)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {colors['danger']};")
        self.error_label.hide()
        footer_layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(tr("Отмена", "Cancel"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.save_button = QPushButton(
            tr("Сохранить", "Save") if self.entry else tr("Создать", "Create")
        )
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._save)
        buttons.addWidget(self.save_button)
        footer_layout.addLayout(buttons)
        layout.addWidget(footer)

    # ------------------------------------------------------------------
    def _populate(self) -> None:
        context = self.context
        if context is not None:
            self.category_combo.addItem(tr("Без категории", "No category"), None)
            for category in context.categories.list_categories():
                self.category_combo.addItem(category.name, category.id)
            suggestion_names = [tag.name for tag in context.tags.list_tags()]

            def resolve(name: str):
                try:
                    tag = context.tags.get_or_create(name)
                except Exception:  # noqa: BLE001 - invalid tag name
                    return None
                return tag.id, tag.name

            self.tag_editor.set_resolver(resolve)
            self.tag_editor.set_suggestions(suggestion_names)

        if self.entry is not None:
            self.title_edit.setText(self.entry.title)
            self.type_edit.setText(self.entry.type)
            self.description_edit.setPlainText(self.entry.description)
            if self.entry.category_id:
                index = self.category_combo.findData(self.entry.category_id)
                if index >= 0:
                    self.category_combo.setCurrentIndex(index)
            self.tag_editor.set_tags([(tag.id, tag.name) for tag in self.entry.tags])
            self._links = [
                LinkDraft(title=link.title, url=link.url, id=link.id)
                for link in self.entry.links
            ]
        self._update_preview()
        self._rebuild_links()
        self.title_edit.setFocus()

    # -- image -----------------------------------------------------------
    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Выберите изображение", "Choose an image"), "", IMAGE_FILTER
        )
        if not path:
            return
        self._image_action = "replace"
        self._image_source = path
        self._update_preview()

    def _clear_image(self) -> None:
        self._image_action = "remove"
        self._image_source = None
        self._update_preview()

    def _update_preview(self) -> None:
        pixmap = None
        if self._image_action == "replace" and self._image_source:
            data = None
            try:
                from PIL import Image, ImageOps
                import io

                with Image.open(self._image_source) as image:
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((176, 176))
                    buffer = io.BytesIO()
                    image.convert("RGBA").save(buffer, format="PNG")
                    data = buffer.getvalue()
            except Exception:  # noqa: BLE001 - corrupted file preview
                data = None
            if data:
                from app.ui.widgets.common import tinted_pixmap

                pixmap = tinted_pixmap(data, 88, radius=18)
                if pixmap.isNull():
                    pixmap = None
            if pixmap is None:
                pixmap = placeholder_icon(88, "!", self.theme)
                self.error_label.setText(
                    tr("Не удалось прочитать изображение", "Cannot read this image")
                )
                self.error_label.show()
        elif self._image_action == "keep" and self._current_image and self.context is not None:
            data = self.context.images.load_bytes(self._current_image, thumbnail=True)
            if data:
                from app.ui.widgets.common import tinted_pixmap

                pixmap = tinted_pixmap(data, 88, radius=18)
                if pixmap.isNull():
                    pixmap = None
        if pixmap is None:
            title = self.title_edit.text().strip()
            pixmap = placeholder_icon(88, title or "?", self.theme)
        self.preview.setPixmap(pixmap)

    # -- links -----------------------------------------------------------
    def _add_link(self) -> None:
        draft = ask_link(self.theme, parent=self)
        if draft is None:
            return
        if any(link.url == draft.url for link in self._links):
            self.error_label.setText(tr("Такая ссылка уже добавлена", "This link already exists"))
            self.error_label.show()
            return
        self._links.append(draft)
        self._rebuild_links()

    def _edit_link(self, draft: LinkDraft) -> None:
        updated = ask_link(self.theme, draft, parent=self)
        if updated is None:
            return
        if any(link is not draft and link.url == updated.url for link in self._links):
            self.error_label.setText(tr("Такая ссылка уже добавлена", "This link already exists"))
            self.error_label.show()
            return
        draft.title = updated.title
        draft.url = updated.url
        self._rebuild_links()

    def _delete_link(self, draft: LinkDraft) -> None:
        self._links = [link for link in self._links if link is not draft]
        self._rebuild_links()

    def _move_link(self, draft: LinkDraft, delta: int) -> None:
        try:
            index = next(i for i, link in enumerate(self._links) if link is draft)
        except StopIteration:
            return
        target = index + delta
        if 0 <= target < len(self._links):
            self._links[index], self._links[target] = self._links[target], self._links[index]
            self._rebuild_links()

    def _rebuild_links(self) -> None:
        colors = palette(self.theme)
        while self.links_layout.count():
            item = self.links_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, draft in enumerate(self._links):
            row = LinkEditRow(draft, colors, index)
            row.reorder_callback = self._move_link
            row.edit_callback = self._edit_link
            row.delete_callback = self._delete_link
            self.links_layout.addWidget(row)
        self.no_links_label.setVisible(not self._links)

    # -- saving ----------------------------------------------------------
    def _save(self) -> None:
        self.error_label.hide()
        try:
            clean_title(self.title_edit.text())
        except ValidationError as exc:
            self._show_error(str(exc))
            self.title_edit.setFocus()
            return
        if self._image_action == "replace" and not self._image_source:
            self._show_error(tr("Выберите файл изображения", "Choose an image file"))
            return
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()

    def build_draft(self) -> EntryDraft:
        draft = EntryDraft(
            title=self.title_edit.text(),
            description=self.description_edit.toPlainText(),
            type=self.type_edit.text(),
            category_id=self.category_combo.currentData(),
            tag_ids=self.tag_editor.tag_ids(),
            links=list(self._links),
            image_action=self._image_action,
            image_source=self._image_source,
        )
        return draft
