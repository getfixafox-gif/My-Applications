"""Dialog for adding and editing a single link."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.i18n import tr
from app.services.entry_service import LinkDraft
from app.ui.styles.theme import palette
from app.utils.validators import ValidationError, validate_link_pair


class LinkDialog(QDialog):
    def __init__(
        self,
        theme: str = "dark",
        link: LinkDraft | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle(
            tr("Изменить ссылку", "Edit link") if link else tr("Новая ссылка", "New link")
        )
        self.setModal(True)
        self.setMinimumWidth(440)
        self._result: LinkDraft | None = None
        self._build(link)

    def _build(self, link: LinkDraft | None) -> None:
        colors = palette(self.theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.title_edit = QLineEdit(link.title if link else "")
        self.title_edit.setPlaceholderText(tr("Например: Официальный сайт", "e.g. Official website"))
        form.addRow(tr("Название", "Title"), self.title_edit)

        self.url_edit = QLineEdit(link.url if link else "")
        self.url_edit.setPlaceholderText("https://example.com")
        form.addRow(tr("Адрес", "URL"), self.url_edit)
        layout.addLayout(form)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {colors['danger']};")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        hint = QLabel(
            tr(
                "Поддерживаются http, https, ftp и mailto. Протокол https добавляется автоматически.",
                "http, https, ftp and mailto are supported. https is added automatically.",
            )
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 11px;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox()
        self.ok_button = QPushButton(tr("Сохранить", "Save"))
        self.ok_button.setObjectName("PrimaryButton")
        self.ok_button.setDefault(True)
        cancel = QPushButton(tr("Отмена", "Cancel"))
        buttons.addButton(self.ok_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.url_edit.returnPressed.connect(self._accept)

    def _accept(self) -> None:
        try:
            title, url = validate_link_pair(self.title_edit.text(), self.url_edit.text())
        except ValidationError as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self._result = LinkDraft(title=title, url=url)
        self.accept()

    def result_link(self) -> LinkDraft | None:
        return self._result


def ask_link(theme: str, link: LinkDraft | None = None, parent=None) -> LinkDraft | None:
    dialog = LinkDialog(theme=theme, link=link, parent=parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.result_link()
    return None
