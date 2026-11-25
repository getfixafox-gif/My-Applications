"""Small shared widgets."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from app.ui.styles.theme import palette


def themed_icon(name: str, color: str | None = None, size: int = 20, theme: str = "dark") -> QIcon:
    from app.ui.styles.icons import svg_icon

    return svg_icon(name, color or palette(theme)["text"], size)


def make_icon_button(
    name: str,
    color: str,
    tooltip: str,
    *,
    size: int = 28,
    icon_size: int = 18,
    flat: bool = True,
    object_name: str | None = None,
) -> QPushButton:
    from app.ui.styles.icons import svg_icon

    button = QPushButton()
    button.setIcon(svg_icon(name, color, icon_size))
    button.setIconSize(QSize(icon_size, icon_size))
    button.setFixedSize(size, size)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(tooltip)
    button.setObjectName(object_name or ("FlatIconButton" if flat else "IconButton"))
    return button


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    return line


class ElidedLabel(QLabel):
    """Label that elides long text instead of forcing the layout to grow."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        super().setText(self._full_text)
        self._apply_elide()

    def full_text(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        metrics = self.fontMetrics()
        available = max(0, self.width() - 2)
        if not self._full_text:
            super().setText("")
            return
        elided = metrics.elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, available or 10_000
        )
        super().setText(elided)


class FlowLayout(QLayout):
    """Left-to-right layout that wraps items onto new lines."""

    heightChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802 - Qt naming
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802 - Qt naming
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):  # noqa: N802 - Qt naming
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802 - Qt naming
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt naming
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt naming
        return self._do_layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt naming
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt naming
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _do_layout(self, rect: QRect, apply: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y = effective.x(), effective.y()
        line_height = 0
        for item in self._items:
            widget = item.widget()
            # ``isHidden`` (not ``isVisible``) keeps freshly created widgets in
            # the layout pass: they are not visible until their parent shows up.
            if widget is not None and widget.isHidden():
                continue
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > effective.right() + 1 and line_height > 0:
                x = effective.x()
                y += line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            if apply:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


def tinted_pixmap(data: bytes, size: int, radius: int = 8) -> QPixmap:
    """Round the corners of an image for list thumbnails."""
    pixmap = QPixmap()
    if not data or not pixmap.loadFromData(data):
        return QPixmap()
    scaled = pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    from PySide6.QtGui import QPainterPath

    path = QPainterPath()
    path.addRoundedRect(x, y, scaled.width(), scaled.height(), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(x, y, scaled)
    painter.end()
    return result


def placeholder_icon(size: int, letter: str, theme: str = "dark") -> QPixmap:
    """Generated placeholder with the first letter of the entry title."""
    colors = palette(theme)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor(colors["accent_soft"]))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, size, size, size * 0.28, size * 0.28)
    painter.setPen(QColor(colors["accent"]))
    font = painter.font()
    font.setPixelSize(int(size * 0.44))
    font.setBold(True)
    painter.setFont(font)
    text = (letter or "?").strip()[:1].upper() or "?"
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return pixmap


class TagChip(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("TagChip")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)


class SectionHeader(QWidget):
    """Section title with an optional trailing widget."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.label = QLabel(title)
        self.label.setObjectName("SectionTitle")
        layout.addWidget(self.label)
        layout.addStretch(1)
        self.layout_ref = layout

    def add_action(self, widget: QWidget) -> None:
        self.layout_ref.addWidget(widget)
