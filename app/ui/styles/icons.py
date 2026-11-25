"""Icon factory: a single internal SVG set keeps icon styling consistent."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

#: All paths are drawn on a 24x24 grid with a 1.8px stroke.
_PATHS = {
    "settings": (
        '<circle cx="12" cy="12" r="3.2"/>'
        '<path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 '
        '1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.11a1.7 1.7 0 0 0-1.11-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83'
        'l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.11A1.7 1.7 0 0 0 4.66 8.9a1.7 1.7 0 0 0-.34-1.87'
        'l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.11a1.7 1.7 0 0 0 1 1.55 '
        '1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9v.11a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4'
        'h-.11a1.7 1.7 0 0 0-1.49 1z"/>'
    ),
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    "edit": (
        '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>'
    ),
    "trash": (
        '<path d="M3 6h18"/><path d="M8 6V4h8v2"/>'
        '<path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/>'
    ),
    "external": (
        '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
        '<path d="M15 3h6v6"/><path d="M10 14L21 3"/>'
    ),
    "link": (
        '<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1.5 1.5"/>'
        '<path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1.5-1.5"/>'
    ),
    "image": (
        '<rect x="3" y="4" width="18" height="16" rx="3"/>'
        '<circle cx="8.5" cy="9.5" r="1.6"/>'
        '<path d="M21 16l-5-5-9 9"/>'
    ),
    "image-off": (
        '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M4 20L20 4"/>'
    ),
    "tag": (
        '<path d="M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0l-7.2-7.2a2 2 0 0 1-.6-1.4V4a1 1 0 0 1 1-1h8a2 2 0 0 1 1.4.6'
        'l7.4 7.4a2 2 0 0 1 0 2.8z"/><circle cx="7.5" cy="7.5" r="1.3"/>'
    ),
    "folder": (
        '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
    ),
    "backup": (
        '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/>'
    ),
    "restore": (
        '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 3v6h6"/>'
    ),
    "download": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 20h16"/>',
    "upload": '<path d="M12 21V9"/><path d="M7 14l5-5 5 5"/><path d="M4 4h16"/>',
    "check": '<path d="M4 12.5l5 5L20 6.5"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "chevron-up": '<path d="M5 15l7-7 7 7"/>',
    "chevron-down": '<path d="M5 9l7 7 7-7"/>',
    "arrow-up": '<path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>',
    "arrow-down": '<path d="M12 5v14"/><path d="M5 12l7 7 7-7"/>',
    "database": (
        '<ellipse cx="12" cy="6" rx="8" ry="3"/>'
        '<path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/>'
        '<path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>'
    ),
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><path d="M12 8h.01"/>',
    "sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2'
        'M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'
    ),
    "moon": '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
    "app": (
        '<rect x="3" y="3" width="18" height="18" rx="4"/>'
        '<path d="M8 3v18"/><path d="M12 8h5M12 12h5M12 16h3"/>'
    ),
    "globe": (
        '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/>'
        '<path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18z"/>'
    ),
    "mail": '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M4 7l8 6 8-6"/>',
    "gamepad": (
        '<rect x="2" y="7" width="20" height="10" rx="5"/>'
        '<path d="M7 10v4M5 12h4"/><circle cx="16" cy="11" r="1"/><circle cx="18.5" cy="13.5" r="1"/>'
    ),
    "code": '<path d="M9 18l-6-6 6-6"/><path d="M15 6l6 6-6 6"/>',
    "palette": (
        '<path d="M12 21a9 9 0 1 1 9-9c0 2-1.5 3-3 3h-1.5a2 2 0 0 0-1.4 3.4A2 2 0 0 1 12 21z"/>'
        '<circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7.5" r="1"/><circle cx="14.5" cy="7.5" r="1"/>'
    ),
    "tool": (
        '<path d="M14.7 6.3a4 4 0 0 0 5 5L21 21l-3 0-9.7-9.7a4 4 0 0 1-5-5L6 9l3-3z"/>'
    ),
    "sparkle": '<path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/>',
}

_CACHE: dict[tuple[str, str, int], QIcon] = {}


def _svg(name: str, color: str) -> str:
    body = _PATHS.get(name, _PATHS["link"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        f'fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


def svg_icon(name: str, color: str = "#e8eaee", size: int = 20) -> QIcon:
    """Coloured vector icon (cached per name/colour/size)."""
    key = (name, color, size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    renderer = QSvgRenderer(QByteArray(_svg(name, color).encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    icon = QIcon(pixmap)
    _CACHE[key] = icon
    return icon


def app_icon() -> QIcon:
    from app.ui.styles.app_icon import APP_ICON_SVG

    renderer = QSvgRenderer(QByteArray(APP_ICON_SVG.encode("utf-8")))
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def clear_cache() -> None:
    _CACHE.clear()
