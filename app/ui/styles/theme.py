"""Qt stylesheets for the dark and light themes."""

from __future__ import annotations

DARK = {
    "bg": "#14161a",
    "panel": "#1b1e24",
    "panel_alt": "#22262e",
    "card": "#232830",
    "border": "#2e343f",
    "text": "#e8eaee",
    "muted": "#9aa3b2",
    "accent": "#4f8cff",
    "accent_hover": "#6ba0ff",
    "accent_soft": "#26324a",
    "danger": "#ef6b6b",
    "success": "#5cc98f",
}

LIGHT = {
    "bg": "#f4f6fa",
    "panel": "#ffffff",
    "panel_alt": "#f0f3f8",
    "card": "#eef2f8",
    "border": "#d7dee9",
    "text": "#1d232c",
    "muted": "#68727f",
    "accent": "#2f6fe4",
    "accent_hover": "#1d5cd1",
    "accent_soft": "#e2ebff",
    "danger": "#d64545",
    "success": "#2f9e63",
}


def palette(theme: str) -> dict[str, str]:
    return LIGHT if theme == "light" else DARK


def build_stylesheet(theme: str) -> str:
    c = palette(theme)
    return f"""
* {{
    font-family: "Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", sans-serif;
    outline: none;
}}

QWidget {{
    background-color: {c['bg']};
    color: {c['text']};
    font-size: 13px;
}}

QMainWindow, QDialog {{
    background-color: {c['bg']};
}}

QToolTip {{
    background-color: {c['panel_alt']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 4px 8px;
}}

/* ---------- panels ---------- */
#Sidebar {{
    background-color: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: 14px;
}}

#DetailPanel {{
    background-color: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: 14px;
}}

#SidebarHeader, #DetailHeader {{
    background: transparent;
}}

#AppTitle {{
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.2px;
    background: transparent;
}}

#CatalogTitle {{
    font-size: 12px;
    font-weight: 700;
    color: {c['muted']};
    text-transform: uppercase;
    background: transparent;
}}

#CountLabel, #MutedLabel, #StatusLabel {{
    color: {c['muted']};
    background: transparent;
}}

#ErrorLabel {{
    color: {c['danger']};
    background: transparent;
    font-size: 12px;
}}

#EntryTitle {{
    font-size: 24px;
    font-weight: 700;
    background: transparent;
}}

#EntryType {{
    background-color: {c['accent_soft']};
    color: {c['accent']};
    border-radius: 9px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}

#SectionTitle {{
    color: {c['muted']};
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    background: transparent;
}}

#DescriptionText {{
    background: transparent;
    color: {c['text']};
}}

#Divider {{
    background-color: {c['border']};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

/* ---------- inputs ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {{
    background-color: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 9px;
    padding: 7px 10px;
    color: {c['text']};
    selection-background-color: {c['accent']};
    selection-color: #ffffff;
}}

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {c['accent']};
}}

QLineEdit:disabled, QComboBox:disabled {{
    color: {c['muted']};
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    background-color: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    selection-background-color: {c['accent_soft']};
    selection-color: {c['text']};
    padding: 4px;
}}

/* ---------- buttons ---------- */
QPushButton {{
    background-color: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 9px;
    padding: 7px 14px;
    color: {c['text']};
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {c['card']};
    border-color: {c['accent']};
}}

QPushButton:pressed {{
    background-color: {c['accent_soft']};
}}

QPushButton:disabled {{
    color: {c['muted']};
    border-color: {c['border']};
    background-color: {c['panel']};
}}

QPushButton#PrimaryButton {{
    background-color: {c['accent']};
    border: 1px solid {c['accent']};
    color: #ffffff;
    font-weight: 600;
}}

QPushButton#PrimaryButton:hover {{
    background-color: {c['accent_hover']};
    border-color: {c['accent_hover']};
}}

QPushButton#DangerButton {{
    color: {c['danger']};
    border-color: {c['danger']};
    background: transparent;
}}

QPushButton#DangerButton:hover {{
    background-color: rgba(239, 107, 107, 0.12);
}}

QPushButton#AddEntryButton {{
    background-color: {c['accent']};
    border: none;
    color: #ffffff;
    font-weight: 600;
    padding: 10px 14px;
    border-radius: 10px;
}}

QPushButton#AddEntryButton:hover {{
    background-color: {c['accent_hover']};
}}

QPushButton#IconButton, QPushButton#FlatIconButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 5px;
}}

QPushButton#IconButton:hover, QPushButton#FlatIconButton:hover {{
    background-color: {c['panel_alt']};
    border-color: {c['border']};
}}

QPushButton#ChipButton {{
    background-color: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 12px;
    padding: 3px 10px;
    font-size: 11px;
    color: {c['muted']};
}}

QPushButton#ChipButton:checked {{
    background-color: {c['accent_soft']};
    border-color: {c['accent']};
    color: {c['accent']};
}}

QLabel#TagChip {{
    background-color: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    padding: 2px 9px;
    font-size: 11px;
    color: {c['muted']};
}}

/* ---------- lists ---------- */
QListWidget {{
    background: transparent;
    border: none;
    outline: none;
    padding: 2px;
}}

QListWidget::item {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 0px;
    margin: 2px 0px;
}}

QListWidget::item:hover {{
    background-color: {c['panel_alt']};
}}

QListWidget::item:selected {{
    background-color: {c['accent_soft']};
    border: 1px solid {c['accent']};
    color: {c['text']};
}}

/* ---------- link cards ---------- */
#LinkCard {{
    background-color: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 12px;
}}

#LinkTitle {{
    font-weight: 600;
    background: transparent;
}}

#LinkUrl {{
    color: {c['muted']};
    font-size: 11px;
    background: transparent;
}}

#LinkIcon {{
    background: transparent;
}}

/* ---------- scroll areas ---------- */
QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px 2px 2px 0px;
}}

QScrollBar::handle:vertical {{
    background-color: {c['border']};
    border-radius: 4px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {c['muted']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0px;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0px 2px 2px 2px;
}}

QScrollBar::handle:horizontal {{
    background-color: {c['border']};
    border-radius: 4px;
    min-width: 30px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
    width: 0px;
}}

/* ---------- splitter & tabs ---------- */
QSplitter::handle {{
    background-color: transparent;
    width: 10px;
}}

QSplitter::handle:hover {{
    background-color: {c['accent_soft']};
}}

QTabWidget::pane {{
    border: 1px solid {c['border']};
    border-radius: 12px;
    top: -1px;
    background-color: {c['panel']};
}}

QTabBar::tab {{
    background: transparent;
    color: {c['muted']};
    padding: 8px 16px;
    margin-right: 4px;
    border-radius: 8px;
    font-weight: 600;
}}

QTabBar::tab:selected {{
    background-color: {c['accent_soft']};
    color: {c['accent']};
}}

QTabBar::tab:hover {{
    color: {c['text']};
}}

/* ---------- misc ---------- */
QCheckBox {{
    spacing: 8px;
    background: transparent;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid {c['border']};
    background-color: {c['panel_alt']};
}}

QCheckBox::indicator:checked {{
    background-color: {c['accent']};
    border-color: {c['accent']};
    image: none;
}}

QGroupBox {{
    border: 1px solid {c['border']};
    border-radius: 12px;
    margin-top: 14px;
    padding: 14px 12px 12px 12px;
    font-weight: 600;
    background-color: {c['panel']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {c['muted']};
}}

QMenu {{
    background-color: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    padding: 6px;
}}

QMenu::item {{
    padding: 6px 22px 6px 12px;
    border-radius: 6px;
}}

QMenu::item:selected {{
    background-color: {c['accent_soft']};
}}

QMenu::item:disabled {{
    color: {c['muted']};
}}

QStatusBar {{
    background-color: {c['bg']};
    color: {c['muted']};
    border-top: 1px solid {c['border']};
}}

QStatusBar::item {{
    border: none;
}}

QProgressBar {{
    background-color: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    text-align: center;
    height: 16px;
}}

QProgressBar::chunk {{
    background-color: {c['accent']};
    border-radius: 7px;
}}
"""
