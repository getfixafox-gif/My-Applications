"""Right detail panel: header, links, description."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.i18n import links_label, tr
from app.models import Entry, Link
from app.ui.styles.theme import palette
from app.ui.widgets.common import (
    ElidedLabel,
    FlowLayout,
    TagChip,
    divider,
    make_icon_button,
    placeholder_icon,
    tinted_pixmap,
)
from app.utils.helpers import format_datetime
from app.utils.logger import get_logger

logger = get_logger("detail")


def link_icon_name(url: str) -> str:
    lowered = (url or "").lower()
    if lowered.startswith("mailto:"):
        return "mail"
    host = lowered.split("//", 1)[-1].split("/", 1)[0]
    for marker, icon in (
        ("github", "code"),
        ("gitlab", "code"),
        ("steam", "gamepad"),
        ("store.", "gamepad"),
        ("mail", "mail"),
        ("docs.", "info"),
    ):
        if marker in host:
            return icon
    return "globe"


class LinkRow(QFrame):
    openRequested = Signal(str)
    editRequested = Signal(str)
    deleteRequested = Signal(str)

    def __init__(
        self, link: Link, theme: str, *, editable: bool = True, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("LinkCard")
        self.link = link
        self.theme = theme
        colors = palette(theme)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 10, 9)
        layout.setSpacing(10)

        icon = QLabel()
        icon.setObjectName("LinkIcon")
        icon.setFixedSize(22, 22)
        from app.ui.styles.icons import svg_icon

        icon.setPixmap(svg_icon(link_icon_name(link.url), colors["accent"], 18).pixmap(18, 18))
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        title = ElidedLabel(link.title or link.url)
        title.setObjectName("LinkTitle")
        url_label = ElidedLabel(link.url)
        url_label.setObjectName("LinkUrl")
        text_layout.addWidget(title)
        text_layout.addWidget(url_label)
        layout.addLayout(text_layout, 1)

        if editable:
            up = make_icon_button(
                "chevron-up", colors["muted"], tr("Выше", "Move up"), size=24, icon_size=16
            )
            up.clicked.connect(lambda: self._reorder(-1))
            layout.addWidget(up)
            down = make_icon_button(
                "chevron-down", colors["muted"], tr("Ниже", "Move down"), size=24, icon_size=16
            )
            down.clicked.connect(lambda: self._reorder(1))
            layout.addWidget(down)

            edit = make_icon_button(
                "edit", colors["muted"], tr("Изменить ссылку", "Edit link"), size=24, icon_size=15
            )
            edit.clicked.connect(lambda: self.editRequested.emit(self.link.id))
            layout.addWidget(edit)

            remove = make_icon_button(
                "trash", colors["muted"], tr("Удалить ссылку", "Delete link"), size=24, icon_size=15
            )
            remove.clicked.connect(lambda: self.deleteRequested.emit(self.link.id))
            layout.addWidget(remove)

        open_button = make_icon_button(
            "external", colors["accent"], tr("Открыть в браузере", "Open in browser"), size=28
        )
        open_button.clicked.connect(self._open)
        layout.addWidget(open_button)
        self.open_button = open_button

    def _reorder(self, delta: int) -> None:
        callback = getattr(self, "reorder_callback", None)
        if callable(callback):
            callback(self.link.id, delta)

    def _open(self) -> None:
        self.openRequested.emit(self.link.url)


class DetailPanel(QFrame):
    editRequested = Signal()
    deleteRequested = Signal()
    linkOpenRequested = Signal(str)
    imageChangeRequested = Signal()
    imageRemoveRequested = Signal()
    addLinkRequested = Signal()
    linkEditRequested = Signal(str)
    linkDeleteRequested = Signal(str)
    linkReorderRequested = Signal(str, int)

    def __init__(self, theme: str = "dark", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailPanel")
        self.theme = theme
        self.entry: Entry | None = None
        self._build()
        self.show_empty_state()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        colors = palette(self.theme)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("DetailContent")
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(26, 24, 26, 22)
        self.content_layout.setSpacing(16)

        # -- header ------------------------------------------------------
        header = QWidget()
        header.setObjectName("DetailHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(16)

        self.image_label = QLabel()
        self.image_label.setFixedSize(84, 84)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background: transparent;")
        header_layout.addWidget(self.image_label, 0, Qt.AlignmentFlag.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(6)
        self.title_label = QLabel()
        self.title_label.setObjectName("EntryTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        text_layout.addWidget(self.title_label)

        self.type_label = QLabel()
        self.type_label.setObjectName("EntryType")
        self.type_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        type_row = QHBoxLayout()
        type_row.setContentsMargins(0, 0, 0, 0)
        type_row.setSpacing(8)
        type_row.addWidget(self.type_label)
        self.category_label = QLabel()
        self.category_label.setObjectName("CountLabel")
        type_row.addWidget(self.category_label)
        type_row.addStretch(1)
        text_layout.addLayout(type_row)

        self.updated_label = QLabel()
        self.updated_label.setObjectName("MutedLabel")
        self.updated_label.setStyleSheet("font-size: 11px;")
        text_layout.addWidget(self.updated_label)
        text_layout.addStretch(1)
        header_layout.addLayout(text_layout, 1)

        actions = QVBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(4)
        self.edit_button = make_icon_button(
            "edit", colors["muted"], tr("Редактировать (Ctrl+E)", "Edit (Ctrl+E)"), size=34, icon_size=18
        )
        self.edit_button.clicked.connect(self.editRequested.emit)
        actions.addWidget(self.edit_button)
        self.delete_button = make_icon_button(
            "trash", colors["muted"], tr("Удалить запись", "Delete entry"), size=34, icon_size=18
        )
        self.delete_button.clicked.connect(self.deleteRequested.emit)
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        header_layout.addLayout(actions)
        self.content_layout.addWidget(header)

        # -- image actions ----------------------------------------------
        image_actions = QWidget()
        image_layout = QHBoxLayout(image_actions)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(6)
        self.change_image_button = QPushButton(tr("Сменить иконку", "Change icon"))
        self.change_image_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_image_button.clicked.connect(self.imageChangeRequested.emit)
        image_layout.addWidget(self.change_image_button)
        self.remove_image_button = QPushButton(tr("Убрать иконку", "Remove icon"))
        self.remove_image_button.setObjectName("DangerButton")
        self.remove_image_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_image_button.clicked.connect(self.imageRemoveRequested.emit)
        image_layout.addWidget(self.remove_image_button)
        image_layout.addStretch(1)
        self.image_actions = image_actions
        self.content_layout.addWidget(image_actions)

        self.content_layout.addWidget(divider())

        # -- links -------------------------------------------------------
        links_header = QHBoxLayout()
        links_header.setContentsMargins(0, 0, 0, 0)
        self.links_title = QLabel(tr("ССЫЛКИ", "LINKS"))
        self.links_title.setObjectName("SectionTitle")
        links_header.addWidget(self.links_title)
        links_header.addStretch(1)
        self.add_link_button = QPushButton(tr("＋ Ссылка", "＋ Link"))
        self.add_link_button.setObjectName("ChipButton")
        self.add_link_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_link_button.clicked.connect(self.addLinkRequested.emit)
        links_header.addWidget(self.add_link_button)
        self.content_layout.addLayout(links_header)

        self.links_container = QWidget()
        self.links_layout = QVBoxLayout(self.links_container)
        self.links_layout.setContentsMargins(0, 0, 0, 0)
        self.links_layout.setSpacing(6)
        self.content_layout.addWidget(self.links_container)
        self.empty_links_label = QLabel(tr("Ссылки не добавлены", "No links added"))
        self.empty_links_label.setObjectName("MutedLabel")
        self.content_layout.addWidget(self.empty_links_label)

        # -- tags --------------------------------------------------------
        self.tags_section = QWidget()
        tags_layout = QVBoxLayout(self.tags_section)
        tags_layout.setContentsMargins(0, 0, 0, 0)
        tags_layout.setSpacing(6)
        self.tags_title = QLabel(tr("ТЕГИ", "TAGS"))
        self.tags_title.setObjectName("SectionTitle")
        tags_layout.addWidget(self.tags_title)
        self.tags_container = QWidget()
        self.tags_flow = FlowLayout(self.tags_container, spacing=6)
        tags_layout.addWidget(self.tags_container)
        self.content_layout.addWidget(self.tags_section)

        self.content_layout.addWidget(divider())

        # -- description -------------------------------------------------
        self.description_title = QLabel(tr("ОПИСАНИЕ", "DESCRIPTION"))
        self.description_title.setObjectName("SectionTitle")
        self.content_layout.addWidget(self.description_title)
        self.description_label = QLabel()
        self.description_label.setObjectName("DescriptionText")
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.description_label.setOpenExternalLinks(False)
        self.description_label.linkActivated.connect(self._open_url)
        self.description_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.content_layout.addWidget(self.description_label)
        self.content_layout.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        self.scroll_area = scroll

        # -- empty state -------------------------------------------------
        self.empty_widget = QWidget()
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setContentsMargins(40, 40, 40, 40)
        empty_layout.setSpacing(10)
        empty_layout.addStretch(1)
        self.empty_icon = QLabel()
        self.empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_icon)
        empty_title = QLabel(tr("Запись не выбрана", "No entry selected"))
        empty_title.setObjectName("EntryTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        hint = QLabel(
            tr(
                "Выберите запись в каталоге слева\nили добавьте новую.",
                "Pick an entry in the catalog on the left\nor add a new one.",
            )
        )
        hint.setObjectName("MutedLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(hint)
        empty_layout.addStretch(2)
        outer.addWidget(self.empty_widget, 1)
        self.empty_widget.hide()

    # ------------------------------------------------------------------
    def set_theme(self, theme: str) -> None:
        self.theme = theme
        colors = palette(theme)
        from app.ui.styles.icons import svg_icon

        self.edit_button.setIcon(svg_icon("edit", colors["muted"], 18))
        self.delete_button.setIcon(svg_icon("trash", colors["muted"], 18))
        self.empty_icon.setPixmap(placeholder_icon(72, "?", theme))
        if self.entry is not None:
            self.show_entry(self.entry)

    # ------------------------------------------------------------------
    def show_empty_state(self) -> None:
        self.entry = None
        self.scroll_area.hide()
        self.empty_widget.show()
        self.empty_icon.setPixmap(placeholder_icon(72, "?", self.theme))

    def show_entry(self, entry: Entry) -> None:
        self.entry = entry
        self.empty_widget.hide()
        self.scroll_area.show()

        self.title_label.setText(entry.title)
        if entry.type:
            self.type_label.setText(entry.type)
            self.type_label.show()
        else:
            self.type_label.hide()
        if entry.category_name:
            self.category_label.setText(f"· {entry.category_name}")
            self.category_label.show()
        else:
            self.category_label.hide()
        updated = format_datetime(entry.updated_at)
        self.updated_label.setText(
            tr(f"Изменено {updated}", f"Updated {updated}") if updated else ""
        )
        self.image_label.setPixmap(
            self._entry_pixmap(entry)
        )
        self.change_image_button.setVisible(True)
        self.remove_image_button.setVisible(bool(entry.image_path))

        self._rebuild_links(entry)
        self._rebuild_tags(entry)
        self._set_description(entry)

    def _entry_pixmap(self, entry: Entry) -> QPixmap:
        loader = getattr(self, "icon_provider", None)
        data = loader(entry) if callable(loader) else None
        if data:
            pixmap = tinted_pixmap(data, 84, radius=18)
            if not pixmap.isNull():
                return pixmap
        return placeholder_icon(84, entry.title, self.theme)

    def _rebuild_links(self, entry: Entry) -> None:
        while self.links_layout.count():
            item = self.links_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not entry.links:
            self.empty_links_label.show()
            self.links_title.setText(tr("ССЫЛКИ", "LINKS"))
            return
        self.empty_links_label.hide()
        self.links_title.setText(
            tr(f"ССЫЛКИ · {links_label(len(entry.links))}", f"LINKS · {links_label(len(entry.links))}")
        )
        for link in entry.links:
            row = LinkRow(link, self.theme)
            row.openRequested.connect(self._open_url)
            row.editRequested.connect(self.linkEditRequested.emit)
            row.deleteRequested.connect(self.linkDeleteRequested.emit)
            row.reorder_callback = self.linkReorderRequested.emit
            self.links_layout.addWidget(row)

    def _rebuild_tags(self, entry: Entry) -> None:
        while self.tags_flow.count():
            item = self.tags_flow.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not entry.tags:
            self.tags_section.hide()
            return
        self.tags_section.show()
        for tag in entry.tags:
            chip = TagChip(f"#{tag.name}")
            self.tags_flow.addWidget(chip)

    def _set_description(self, entry: Entry) -> None:
        text = (entry.description or "").strip()
        if not text:
            self.description_title.hide()
            self.description_label.hide()
            return
        self.description_title.show()
        self.description_label.show()
        if text.lstrip().lower().startswith("<") and ">" in text:
            self.description_label.setTextFormat(Qt.TextFormat.RichText)
            self.description_label.setText(text)
        else:
            self.description_label.setTextFormat(Qt.TextFormat.PlainText)
            self.description_label.setText(text)

    def _open_url(self, url: str) -> None:
        self.linkOpenRequested.emit(url)

    def add_link_from(self) -> None:
        if self.entry is not None:
            self.addLinkRequested.emit()

    @staticmethod
    def open_external(url: str) -> bool:
        try:
            return QDesktopServices.openUrl(QUrl(url))
        except Exception as exc:  # noqa: BLE001 - defensive
            logger.error("Cannot open URL %s: %s", url, exc)
            return False
