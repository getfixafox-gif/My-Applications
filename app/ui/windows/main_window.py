"""Main application window: catalog + detail panes."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QWidget,
)

from app.application import AppContext
from app.database.connection import DatabaseError
from app.database.repository import EntryFilter
from app.events import (
    CATEGORY_CHANGED,
    ENTRY_CREATED,
    ENTRY_DELETED,
    ENTRY_UPDATED,
    STORAGE_CHANGED,
    TAG_CHANGED,
    bus,
)
from app.i18n import entries_label, tr
from app.models import EntrySummary
from app.settings.defaults import SORT_MODES
from app.ui.dialogs.entry_dialog import EntryDialog
from app.ui.dialogs.link_dialog import ask_link
from app.ui.styles.icons import app_icon
from app.ui.styles.theme import build_stylesheet
from app.ui.widgets.detail_panel import DetailPanel
from app.ui.widgets.sidebar import Sidebar
from app.utils.logger import get_logger
from app.utils.tasks import TaskRunner

logger = get_logger("main_window")

SEARCH_DEBOUNCE_MS = 140


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.tasks = TaskRunner()
        self._icon_cache: dict[str, tuple[float, bytes | None]] = {}
        self._selected_id: str | None = None
        self._closing = False
        self._auto_backup_timer = QTimer(self)
        self._auto_backup_timer.setSingleShot(True)
        self._auto_backup_timer.setInterval(1200)
        self._auto_backup_timer.timeout.connect(self._schedule_auto_backup)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self.reload_entries)

        self.setWindowTitle(tr("My Applications", "My Applications"))
        self.setWindowIcon(app_icon())
        self.setMinimumSize(940, 620)
        self.resize(1220, 780)
        self._build()
        self.apply_theme()
        self._connect_events()
        self._restore_geometry()
        self.reload_all()
        self._auto_backup_timer.start()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(10)

        self.sidebar = Sidebar(theme=self.theme)
        self.sidebar.setMinimumWidth(280)
        self.detail = DetailPanel(theme=self.theme)
        self.detail.setMinimumWidth(360)
        self.detail.icon_provider = self._entry_icon_bytes

        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.detail)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([360, 840])
        layout.addWidget(self.splitter)
        self.setCentralWidget(central)

        # -- status bar --------------------------------------------------
        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.storage_label = QLabel()
        self.storage_label.setObjectName("StatusLabel")
        status.addPermanentWidget(self.storage_label)
        self.setStatusBar(status)

        # -- shortcuts ---------------------------------------------------
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.create_entry)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.edit_entry)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.sidebar.focus_search)
        QShortcut(QKeySequence("Delete"), self, activated=self._confirm_delete)
        QShortcut(QKeySequence("Escape"), self, activated=self._clear_search)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.open_settings)

        # -- wiring ------------------------------------------------------
        self.sidebar.addRequested.connect(self.create_entry)
        self.sidebar.entryActivated.connect(self.select_entry)
        self.sidebar.settingsRequested.connect(self.open_settings)
        self.sidebar.manageRequested.connect(self.open_references)
        self.sidebar.filtersChanged.connect(self._on_filters_changed)
        self.detail.editRequested.connect(self.edit_entry)
        self.detail.deleteRequested.connect(self._confirm_delete)
        self.detail.linkOpenRequested.connect(self.open_url)
        self.detail.imageChangeRequested.connect(self.change_icon)
        self.detail.imageRemoveRequested.connect(self.remove_icon)
        self.detail.addLinkRequested.connect(self.add_link_to_entry)
        self.detail.linkEditRequested.connect(self.edit_link)
        self.detail.linkDeleteRequested.connect(self.delete_link)
        self.detail.linkReorderRequested.connect(self.reorder_link)

    @property
    def theme(self) -> str:
        return self.context.config.get("theme", "dark")

    # ------------------------------------------------------------------
    # Theme / geometry
    # ------------------------------------------------------------------
    def apply_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(self.theme))
        self.sidebar.set_theme(self.theme)
        self.detail.set_theme(self.theme)

    def _restore_geometry(self) -> None:
        geometry = self.context.config.get("window_geometry")
        if geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
            except (ValueError, UnicodeEncodeError):
                logger.warning("Cannot restore window geometry")
        state = self.context.config.get("splitter_state")
        if state:
            try:
                self.splitter.restoreState(QByteArray.fromBase64(state.encode("ascii")))
            except (ValueError, UnicodeEncodeError):
                logger.warning("Cannot restore splitter state")
        mode = self.context.config.get("sort_mode", "updated_desc")
        if mode in SORT_MODES:
            self.sidebar.set_sort_mode(mode)

    def save_window_state(self) -> None:
        try:
            geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
            splitter = bytes(self.splitter.saveState().toBase64()).decode("ascii")
            self.context.config.update(
                {
                    "window_geometry": geometry,
                    "splitter_state": splitter,
                    "sort_mode": self.sidebar.sort_mode(),
                }
            )
        except Exception as exc:  # noqa: BLE001 - never block shutdown
            logger.warning("Cannot save window state: %s", exc)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def _connect_events(self) -> None:
        self._event_handlers = (
            (CATEGORY_CHANGED, self._on_categories_changed),
            (TAG_CHANGED, self._on_tags_changed),
            (ENTRY_CREATED, self._on_entry_created),
            (ENTRY_UPDATED, self._on_entry_updated),
            (ENTRY_DELETED, self._on_entry_deleted),
            (STORAGE_CHANGED, self._refresh_storage_status),
        )
        for event, handler in self._event_handlers:
            bus.subscribe(event, handler)

    def _disconnect_events(self) -> None:
        """Unsubscribe from the global bus.

        The bus outlives windows (tests create and destroy several), so a
        stale window must never receive events or it will touch deleted
        Qt objects.
        """
        for event, handler in getattr(self, "_event_handlers", ()):
            bus.unsubscribe(event, handler)
        self._event_handlers = ()

    def _on_categories_changed(self, **_kwargs) -> None:
        if self._closing:
            return
        self.reload_categories()
        self.reload_entries()
        self._refresh_detail()

    def _on_tags_changed(self, **_kwargs) -> None:
        if self._closing:
            return
        self.reload_tags()
        self.reload_entries()
        self._refresh_detail()

    def _on_entry_created(self, entry=None, **_kwargs) -> None:
        if self._closing:
            return
        if entry is not None:
            self._icon_cache.pop(entry.id, None)
        self.reload_entries(select_id=entry.id if entry else None)

    def _on_entry_updated(self, entry=None, **_kwargs) -> None:
        if self._closing:
            return
        if entry is not None:
            self._icon_cache.pop(entry.id, None)
        self.reload_entries()
        if entry is not None and entry.id == self._selected_id:
            self.detail.show_entry(entry)

    def _on_entry_deleted(self, entry_id=None, **_kwargs) -> None:
        if self._closing:
            return
        if entry_id:
            self._icon_cache.pop(entry_id, None)
        if entry_id == self._selected_id:
            self._selected_id = None
            self.detail.show_empty_state()
        self.reload_entries()

    def reload_all(self) -> None:
        self.reload_categories()
        self.reload_tags()
        self.reload_entries()
        self._refresh_storage_status()

    def reload_categories(self) -> None:
        try:
            categories = self.context.categories.list_categories()
        except DatabaseError as exc:
            self._error(str(exc))
            return
        self._category_names = {item.id: item.name for item in categories}
        self.sidebar.set_categories(categories)

    def reload_tags(self) -> None:
        try:
            tags = self.context.tags.list_tags()
        except DatabaseError as exc:
            self._error(str(exc))
            return
        self.sidebar.set_tags(tags)

    def current_filters(self) -> EntryFilter:
        return EntryFilter(
            search=self.sidebar.search_text(),
            category_id=self.sidebar.category_id(),
            tag_ids=self.sidebar.tag_ids(),
            sort=self.sidebar.sort_mode(),
        )

    def reload_entries(self, select_id: str | None = None) -> None:
        try:
            entries = self.context.entries.list_entries(self.current_filters())
            total = self.context.entries.count_entries()
        except DatabaseError as exc:
            self._error(str(exc))
            return
        self._entries = entries
        self.sidebar.set_count(total)
        names = getattr(self, "_category_names", {})
        self.sidebar.set_entries(entries, self._summary_icon_bytes, names)

        target = select_id or self._selected_id
        if target and any(item.id == target for item in entries):
            self.sidebar.select_entry(target)
            return
        if entries:
            if not target or self._selected_id not in {item.id for item in entries}:
                first = entries[0]
                self.sidebar.select_entry(first.id)
                self.select_entry(first.id)
        else:
            self._selected_id = None
            self.detail.show_empty_state()

    def _summary_icon_bytes(self, summary: EntrySummary) -> bytes | None:
        if not summary.image_path:
            return None
        cached = self._icon_cache.get(summary.id)
        mtime = self._image_mtime(summary.image_path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        data = self.context.images.load_bytes(summary.image_path, thumbnail=True)
        self._icon_cache[summary.id] = (mtime, data)
        return data

    def _entry_icon_bytes(self, entry) -> bytes | None:
        return self.context.images.load_bytes(entry.image_path, thumbnail=True)

    def _image_mtime(self, relative: str) -> float:
        path = self.context.images.resolve(relative, thumbnail=True)
        if path is None:
            return -1.0
        try:
            return path.stat().st_mtime
        except OSError:
            return -1.0

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------
    def select_entry(self, entry_id: str) -> None:
        self._selected_id = entry_id
        try:
            entry = self.context.entries.get_entry(entry_id)
        except DatabaseError as exc:
            self._error(str(exc))
            return
        if entry is None:
            self.detail.show_empty_state()
            return
        if self.sidebar.current_entry_id() != entry_id:
            self.sidebar.select_entry(entry_id)
        self.detail.icon_provider = self._entry_icon_bytes
        self.detail.show_entry(entry)

    def _refresh_detail(self) -> None:
        if self._selected_id:
            self.select_entry(self._selected_id)

    @property
    def selected_id(self) -> str | None:
        return self._selected_id

    # ------------------------------------------------------------------
    # Entry actions
    # ------------------------------------------------------------------
    def create_entry(self) -> None:
        dialog = EntryDialog(theme=self.theme, context=self.context, parent=self)
        if dialog.exec() != EntryDialog.DialogCode.Accepted:
            return
        draft = dialog.build_draft()
        try:
            entry = self.context.entries.create_entry(draft)
        except Exception as exc:  # noqa: BLE001 - user-facing message
            self._error(str(exc))
            return
        self._toast(tr(f"Создана запись «{entry.title}»", f"Entry “{entry.title}” created"))
        self.reload_entries(select_id=entry.id)
        self.sidebar.select_entry(entry.id)
        self.select_entry(entry.id)

    def edit_entry(self) -> None:
        if not self._selected_id:
            return
        try:
            entry = self.context.entries.get_entry(self._selected_id)
        except DatabaseError as exc:
            self._error(str(exc))
            return
        if entry is None:
            self._toast(tr("Запись больше не существует", "This entry no longer exists"))
            self.reload_entries()
            return
        dialog = EntryDialog(theme=self.theme, context=self.context, entry=entry, parent=self)
        if dialog.exec() != EntryDialog.DialogCode.Accepted:
            return
        draft = dialog.build_draft()
        try:
            updated = self.context.entries.update_entry(entry.id, draft)
        except Exception as exc:  # noqa: BLE001
            self._error(str(exc))
            return
        self._toast(tr("Изменения сохранены", "Changes saved"))
        self.reload_entries(select_id=updated.id)
        self.select_entry(updated.id)

    def _confirm_delete(self) -> None:
        entry_id = self._selected_id
        if not entry_id:
            return
        try:
            entry = self.context.entries.get_entry(entry_id)
        except DatabaseError as exc:
            self._error(str(exc))
            return
        if entry is None:
            return
        answer = QMessageBox.question(
            self,
            tr("Удаление записи", "Delete entry"),
            tr(
                f"Удалить запись «{entry.title}»?\n\nСвязанные ссылки и теги будут удалены, "
                "изображения — только если они не используются другими записями.",
                f"Delete entry “{entry.title}”?\n\nRelated links and tags will be removed; "
                "images only if they are not used by other entries.",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.context.entries.delete_entry(entry_id)
        except Exception as exc:  # noqa: BLE001
            self._error(str(exc))
            return
        self._toast(tr("Запись удалена", "Entry deleted"))
        self._selected_id = None
        self.reload_entries()

    def add_link_to_entry(self) -> None:
        if not self._selected_id:
            return
        draft = ask_link(self.theme, parent=self)
        if draft is None:
            return
        self._update_entry_links(add=[draft])

    def edit_link(self, link_id: str) -> None:
        if not self._selected_id:
            return
        links = self.context.repository.list_links(self._selected_id)
        current = next((link for link in links if link.id == link_id), None)
        if current is None:
            return
        from app.services.entry_service import LinkDraft

        draft = ask_link(
            self.theme, LinkDraft(title=current.title, url=current.url, id=current.id), parent=self
        )
        if draft is None:
            return
        self._update_entry_links(update=(link_id, draft))

    def delete_link(self, link_id: str) -> None:
        answer = QMessageBox.question(
            self,
            tr("Удаление ссылки", "Delete link"),
            tr("Удалить эту ссылку?", "Delete this link?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._update_entry_links(remove=link_id)

    def reorder_link(self, link_id: str, delta: int) -> None:
        if not self._selected_id:
            return
        links = list(self.context.repository.list_links(self._selected_id))
        ids = [link.id for link in links]
        try:
            index = ids.index(link_id)
        except ValueError:
            return
        target = index + delta
        if not 0 <= target < len(ids):
            return
        ids[index], ids[target] = ids[target], ids[index]
        try:
            with self.context.database.transaction():
                self.context.repository.reorder_links(ids)
                self.context.repository.touch_entry(self._selected_id)
        except Exception as exc:  # noqa: BLE001
            self._error(str(exc))
            return
        self.select_entry(self._selected_id)
        self.reload_entries(select_id=self._selected_id)

    def _update_entry_links(self, *, add=None, update=None, remove=None) -> None:
        """Apply a link change to the currently selected entry."""
        entry_id = self._selected_id
        if not entry_id:
            return
        try:
            entry = self.context.entries.get_entry(entry_id)
            if entry is None:
                return
            from app.services.entry_service import EntryDraft, LinkDraft

            links = [LinkDraft(title=l.title, url=l.url, id=l.id) for l in entry.links]
            if add is not None:
                if any(link.url == add.url for link in links):
                    self._toast(tr("Такая ссылка уже есть", "This link already exists"))
                    return
                links.append(add)
            if update is not None:
                link_id, draft = update
                links = [
                    LinkDraft(title=draft.title, url=draft.url, id=link_id)
                    if link.id == link_id
                    else link
                    for link in links
                ]
            if remove is not None:
                links = [link for link in links if link.id != remove]
            draft_entry = EntryDraft(
                title=entry.title,
                description=entry.description,
                type=entry.type,
                category_id=entry.category_id,
                tag_ids=[tag.id for tag in entry.tags],
                links=links,
                image_action="keep",
            )
            updated = self.context.entries.update_entry(entry_id, draft_entry)
        except Exception as exc:  # noqa: BLE001
            self._error(str(exc))
            return
        self.detail.show_entry(updated)
        self.reload_entries(select_id=entry_id)

    def open_url(self, url: str) -> None:
        """Open a stored link in the system browser."""
        if not url:
            return
        logger.info("Opening URL %s", url)
        if not DetailPanel.open_external(url):
            try:
                webbrowser.open(url)
            except Exception as exc:  # noqa: BLE001
                self._error(tr(f"Не удалось открыть ссылку: {exc}", f"Cannot open link: {exc}"))

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------
    def change_icon(self) -> None:
        if not self._selected_id:
            return
        from PySide6.QtWidgets import QFileDialog

        from app.ui.dialogs.entry_dialog import IMAGE_FILTER

        path, _ = QFileDialog.getOpenFileName(
            self, tr("Выберите изображение", "Choose an image"), "", IMAGE_FILTER
        )
        if not path:
            return
        try:
            self.context.entries.set_image(self._selected_id, path)
        except Exception as exc:  # noqa: BLE001
            self._error(str(exc))
            return
        self._icon_cache.pop(self._selected_id, None)
        self._toast(tr("Иконка обновлена", "Icon updated"))
        self.select_entry(self._selected_id)
        self.reload_entries(select_id=self._selected_id)

    def remove_icon(self) -> None:
        if not self._selected_id:
            return
        try:
            self.context.entries.remove_image(self._selected_id)
        except Exception as exc:  # noqa: BLE001
            self._error(str(exc))
            return
        self._icon_cache.pop(self._selected_id, None)
        self._toast(tr("Иконка удалена", "Icon removed"))
        self.select_entry(self._selected_id)
        self.reload_entries(select_id=self._selected_id)

    # ------------------------------------------------------------------
    # Misc UI
    # ------------------------------------------------------------------
    def _on_filters_changed(self) -> None:
        self._search_timer.start()

    def _clear_search(self) -> None:
        if self.sidebar.search_text():
            self.sidebar.search_edit.clear()

    def open_settings(self) -> None:
        from app.ui.windows.settings_window import SettingsDialog

        dialog = SettingsDialog(self.context, parent=self)
        dialog.exec()
        if dialog.theme_changed or dialog.language_changed:
            self.apply_theme()
            self.reload_all()
            if self._selected_id:
                self.select_entry(self._selected_id)
        elif dialog.storage_changed:
            self.reload_all()
            if self._selected_id:
                self.select_entry(self._selected_id)

    def open_references(self) -> None:
        from app.ui.dialogs.reference_dialog import ReferenceDialog

        ReferenceDialog(self.context, theme=self.theme, parent=self).exec()
        self.reload_categories()
        self.reload_tags()
        self.reload_entries(select_id=self._selected_id)

    def _refresh_storage_status(self, **_kwargs) -> None:
        usage = self.context.paths.storage_usage()
        from app.utils.helpers import format_size

        self.storage_label.setText(
            tr(
                f"Локальное хранилище · {format_size(usage['total'])} · {entries_label(self.context.entries.count_entries())}",
                f"Local storage · {format_size(usage['total'])} · {entries_label(self.context.entries.count_entries())}",
            )
        )
        self.storage_label.setToolTip(str(self.context.paths.root))

    def _toast(self, message: str) -> None:
        self.statusBar().showMessage(message, 4000)

    # ------------------------------------------------------------------
    # Automatic backups
    # ------------------------------------------------------------------
    def _schedule_auto_backup(self) -> None:
        """Create a background snapshot when the configured interval elapsed."""
        if self._closing:
            return
        try:
            if not self.context.backups.is_due():
                return
        except Exception as exc:  # noqa: BLE001 - never block startup
            logger.warning("Cannot evaluate backup schedule: %s", exc)
            return
        logger.info("Automatic backup is due; scheduling")
        self.tasks.run(
            self.context.backups.run_auto_backup,
            on_finished=self._on_auto_backup_done,
            on_failed=lambda message: logger.error("Automatic backup failed: %s", message),
        )

    def _on_auto_backup_done(self, path) -> None:
        if not path or self._closing:
            return
        try:
            from app.utils.helpers import format_size

            size = Path(path).stat().st_size if Path(path).exists() else 0
            self._toast(
                tr(
                    f"Автоматическая резервная копия создана ({format_size(size)})",
                    f"Automatic backup created ({format_size(size)})",
                )
            )
            self._refresh_storage_status()
        except RuntimeError:  # window already destroyed
            logger.debug("Window closed before the backup notification")

    def _error(self, message: str) -> None:
        logger.error("UI error: %s", message)
        if self._closing:
            return
        QMessageBox.warning(self, tr("Ошибка", "Error"), message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._closing = True
        self._auto_backup_timer.stop()
        self._search_timer.stop()
        self._disconnect_events()
        self.save_window_state()
        super().closeEvent(event)
