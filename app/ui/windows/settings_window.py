"""Settings window: appearance, storage, backups, versions."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.application import AppContext
from app.i18n import LANGUAGE_TITLES, LANGUAGES, tr
from app.settings.defaults import BACKUP_INTERVALS, LOG_LEVELS, THEMES
from app.storage.backup_manager import BackupError
from app.utils.helpers import format_datetime, format_size
from app.utils.logger import get_logger
from app.utils.tasks import TaskRunner
from app.version import APP_NAME, APP_VERSION, ARCHIVE_FORMAT_VERSION, DB_SCHEMA_VERSION

logger = get_logger("settings_ui")

THEME_TITLES = {"dark": ("Тёмная", "Dark"), "light": ("Светлая", "Light")}
LOG_TITLES = {
    "DEBUG": ("Подробный", "Debug"),
    "INFO": ("Обычный", "Info"),
    "WARNING": ("Только предупреждения", "Warnings"),
    "ERROR": ("Только ошибки", "Errors"),
}
INTERVAL_TITLES = {
    6: ("каждые 6 часов", "every 6 hours"),
    12: ("каждые 12 часов", "every 12 hours"),
    24: ("раз в сутки", "daily"),
    72: ("раз в 3 дня", "every 3 days"),
    168: ("раз в неделю", "weekly"),
}


def _row(label: str, value: str) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QLabel(label))
    layout.addStretch(1)
    value_label = QLabel(value)
    value_label.setObjectName("CountLabel")
    value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    layout.addWidget(value_label)
    return widget


class SettingsDialog(QDialog):
    def __init__(self, context: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.tasks = TaskRunner()
        self.theme_changed = False
        self.language_changed = False
        self.storage_changed = False
        self._busy = False
        self.setWindowTitle(tr("Настройки", "Settings"))
        self.setModal(True)
        self.setMinimumSize(720, 600)
        self._build()
        self._load_values()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general(), tr("Основные", "General"))
        self.tabs.addTab(self._build_storage(), tr("Хранилище", "Storage"))
        self.tabs.addTab(self._build_advanced(), tr("Дополнительные", "Advanced"))
        layout.addWidget(self.tabs, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.status_label = QLabel()
        self.status_label.setObjectName("MutedLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.close_button = QPushButton(tr("Закрыть", "Close"))
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    # -- general ---------------------------------------------------------
    def _build_general(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(14)

        appearance = QGroupBox(tr("Внешний вид", "Appearance"))
        form = QVBoxLayout(appearance)
        form.setSpacing(10)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel(tr("Тема оформления", "Theme")))
        theme_row.addStretch(1)
        self.theme_combo = QComboBox()
        for value in THEMES:
            ru, en = THEME_TITLES[value]
            self.theme_combo.addItem(tr(ru, en), value)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self.theme_combo)
        form.addLayout(theme_row)

        language_row = QHBoxLayout()
        language_row.addWidget(QLabel(tr("Язык интерфейса", "Interface language")))
        language_row.addStretch(1)
        self.language_combo = QComboBox()
        for value in LANGUAGES:
            self.language_combo.addItem(LANGUAGE_TITLES.get(value, value), value)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        language_row.addWidget(self.language_combo)
        form.addLayout(language_row)

        hint = QLabel(
            tr(
                "Изменения применяются сразу и сохраняются автоматически.",
                "Changes apply immediately and are saved automatically.",
            )
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addWidget(hint)
        layout.addWidget(appearance)

        about = QGroupBox(tr("О приложении", "About"))
        about_layout = QVBoxLayout(about)
        about_layout.setSpacing(6)
        about_layout.addWidget(_row(tr("Приложение", "Application"), APP_NAME))
        about_layout.addWidget(_row(tr("Версия приложения", "App version"), APP_VERSION))
        about_layout.addWidget(
            _row(tr("Версия базы данных", "Database version"), str(self.context.schema_version or DB_SCHEMA_VERSION))
        )
        about_layout.addWidget(
            _row(tr("Версия формата архивов", "Archive format version"), str(ARCHIVE_FORMAT_VERSION))
        )
        mode_label = QLabel(
            tr(
                "Приложение работает полностью локально и не использует интернет "
                "без вашего действия.",
                "The application works fully offline and never uses the network "
                "without your action.",
            )
        )
        mode_label.setObjectName("MutedLabel")
        mode_label.setWordWrap(True)
        about_layout.addWidget(mode_label)
        layout.addWidget(about)
        layout.addStretch(1)
        return page

    # -- storage ---------------------------------------------------------
    def _build_storage(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(14)

        location = QGroupBox(tr("Расположение данных", "Data location"))
        location_layout = QVBoxLayout(location)
        location_layout.setSpacing(8)
        self.path_edit = QLineEdit(str(self.context.paths.root))
        self.path_edit.setReadOnly(True)
        location_layout.addWidget(self.path_edit)
        path_buttons = QHBoxLayout()
        open_folder = QPushButton(tr("Открыть папку", "Open folder"))
        open_folder.clicked.connect(self._open_data_folder)
        path_buttons.addWidget(open_folder)
        path_buttons.addStretch(1)
        location_layout.addLayout(path_buttons)
        self.usage_label = QLabel()
        self.usage_label.setObjectName("MutedLabel")
        self.usage_label.setWordWrap(True)
        location_layout.addWidget(self.usage_label)
        layout.addWidget(location)

        backup_group = QGroupBox(tr("Резервное копирование", "Backup"))
        backup_layout = QVBoxLayout(backup_group)
        backup_layout.setSpacing(8)
        manual = QHBoxLayout()
        manual_backup = QPushButton(tr("Создать резервную копию…", "Create backup…"))
        manual_backup.setObjectName("PrimaryButton")
        manual_backup.clicked.connect(self._manual_backup)
        manual.addWidget(manual_backup)
        manual.addStretch(1)
        backup_layout.addLayout(manual)

        import_row = QHBoxLayout()
        export_button = QPushButton(tr("Экспорт ZIP…", "Export ZIP…"))
        export_button.clicked.connect(self._export_archive)
        import_row.addWidget(export_button)
        import_button = QPushButton(tr("Импорт ZIP…", "Import ZIP…"))
        import_button.clicked.connect(self._import_archive)
        import_row.addWidget(import_button)
        restore_button = QPushButton(tr("Восстановить из архива…", "Restore from archive…"))
        restore_button.clicked.connect(self._restore_archive)
        import_row.addWidget(restore_button)
        import_row.addStretch(1)
        backup_layout.addLayout(import_row)

        self.last_backup_label = QLabel()
        self.last_backup_label.setObjectName("MutedLabel")
        self.last_backup_label.setWordWrap(True)
        backup_layout.addWidget(self.last_backup_label)
        layout.addWidget(backup_group)

        maintenance = QGroupBox(tr("Обслуживание", "Maintenance"))
        maintenance_layout = QVBoxLayout(maintenance)
        cleanup_row = QHBoxLayout()
        clean_images = QPushButton(tr("Очистить неиспользуемые изображения", "Clean unused images"))
        clean_images.clicked.connect(self._cleanup_images)
        cleanup_row.addWidget(clean_images)
        cleanup_row.addStretch(1)
        maintenance_layout.addLayout(cleanup_row)
        layout.addWidget(maintenance)
        layout.addStretch(1)
        return page

    # -- advanced --------------------------------------------------------
    def _build_advanced(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(14)

        auto = QGroupBox(tr("Автоматическое резервирование", "Automatic backup"))
        auto_layout = QVBoxLayout(auto)
        auto_layout.setSpacing(10)

        self.autobackup_check = QCheckBox(tr("Включить автоматические копии", "Enable automatic backups"))
        self.autobackup_check.toggled.connect(self._save_advanced)
        auto_layout.addWidget(self.autobackup_check)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel(tr("Периодичность", "Interval")))
        interval_row.addStretch(1)
        self.interval_combo = QComboBox()
        for hours in BACKUP_INTERVALS:
            ru, en = INTERVAL_TITLES[hours]
            self.interval_combo.addItem(tr(ru, en), hours)
        self.interval_combo.currentIndexChanged.connect(self._save_advanced)
        interval_row.addWidget(self.interval_combo)
        auto_layout.addLayout(interval_row)

        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel(tr("Хранить копий", "Keep backups")))
        keep_row.addStretch(1)
        self.keep_spin = QSpinBox()
        self.keep_spin.setRange(1, 100)
        self.keep_spin.valueChanged.connect(self._save_advanced)
        keep_row.addWidget(self.keep_spin)
        auto_layout.addLayout(keep_row)

        self.auto_info_label = QLabel()
        self.auto_info_label.setObjectName("MutedLabel")
        self.auto_info_label.setWordWrap(True)
        auto_layout.addWidget(self.auto_info_label)

        run_now = QHBoxLayout()
        self.run_backup_button = QPushButton(tr("Создать копию сейчас", "Back up now"))
        self.run_backup_button.clicked.connect(self._run_backup_now)
        run_now.addWidget(self.run_backup_button)
        run_now.addStretch(1)
        auto_layout.addLayout(run_now)
        layout.addWidget(auto)

        logging_group = QGroupBox(tr("Логирование", "Logging"))
        logging_layout = QVBoxLayout(logging_group)
        log_row = QHBoxLayout()
        log_row.addWidget(QLabel(tr("Уровень журнала", "Log level")))
        log_row.addStretch(1)
        self.log_combo = QComboBox()
        for level in LOG_LEVELS:
            ru, en = LOG_TITLES[level]
            self.log_combo.addItem(tr(ru, en), level)
        self.log_combo.currentIndexChanged.connect(self._on_log_level_changed)
        log_row.addWidget(self.log_combo)
        logging_layout.addLayout(log_row)
        open_logs = QPushButton(tr("Открыть журналы", "Open logs"))
        open_logs.clicked.connect(self._open_logs_folder)
        logging_layout.addWidget(open_logs, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(logging_group)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------
    # Loading / saving
    # ------------------------------------------------------------------
    def _load_values(self) -> None:
        config = self.context.config
        self.theme_combo.blockSignals(True)
        index = self.theme_combo.findData(config.get("theme", "dark"))
        self.theme_combo.setCurrentIndex(max(0, index))
        self.theme_combo.blockSignals(False)

        self.language_combo.blockSignals(True)
        index = self.language_combo.findData(config.get("language", "ru"))
        self.language_combo.setCurrentIndex(max(0, index))
        self.language_combo.blockSignals(False)

        self.autobackup_check.blockSignals(True)
        self.autobackup_check.setChecked(bool(config.get("autobackup_enabled", True)))
        self.autobackup_check.blockSignals(False)

        self.interval_combo.blockSignals(True)
        index = self.interval_combo.findData(int(config.get("autobackup_interval_hours", 24)))
        self.interval_combo.setCurrentIndex(max(0, index))
        self.interval_combo.blockSignals(False)

        self.keep_spin.blockSignals(True)
        self.keep_spin.setValue(int(config.get("autobackup_keep", 10)))
        self.keep_spin.blockSignals(False)

        self.log_combo.blockSignals(True)
        index = self.log_combo.findData(config.get("log_level", "INFO"))
        self.log_combo.setCurrentIndex(max(0, index))
        self.log_combo.blockSignals(False)

        self._refresh_storage_info()
        self._refresh_backup_info()

    def _refresh_storage_info(self) -> None:
        usage = self.context.paths.storage_usage()
        self.usage_label.setText(
            tr(
                f"База данных: {format_size(usage['database'])} · "
                f"Изображения: {format_size(usage['images'])} · "
                f"Резервные копии: {format_size(usage['backups'])} · "
                f"Всего: {format_size(usage['total'])}",
                f"Database: {format_size(usage['database'])} · "
                f"Images: {format_size(usage['images'])} · "
                f"Backups: {format_size(usage['backups'])} · "
                f"Total: {format_size(usage['total'])}",
            )
        )

    def _refresh_backup_info(self) -> None:
        last = self.context.config.get("last_backup_at")
        last_text = format_datetime(last) if last else tr("ещё не создавалась", "not created yet")
        self.last_backup_label.setText(
            tr(f"Последняя резервная копия: {last_text}", f"Last backup: {last_text}")
        )
        auto_count = len(self.context.backups.list_auto_backups())
        next_run = self.context.backups.next_run_at()
        details = tr(f"Автоматических копий сохранено: {auto_count}", f"Stored automatic backups: {auto_count}")
        if next_run is not None and self.context.config.get("autobackup_enabled", True):
            details += tr(
                f" · Следующая: {next_run.astimezone().strftime('%d.%m.%Y %H:%M')}",
                f" · Next: {next_run.astimezone().strftime('%Y-%m-%d %H:%M')}",
            )
        self.auto_info_label.setText(details)

    # -- callbacks -------------------------------------------------------
    def _on_theme_changed(self) -> None:
        value = self.theme_combo.currentData()
        if value == self.context.config.get("theme"):
            return
        self.context.config.set("theme", value)
        self.theme_changed = True
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            from app.ui.styles.theme import build_stylesheet

            app.setStyleSheet(build_stylesheet(value))
        self._reload_window_theme()

    def _reload_window_theme(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "apply_theme"):
            parent.apply_theme()

    def _on_language_changed(self) -> None:
        value = self.language_combo.currentData()
        if value == self.context.config.get("language"):
            return
        self.context.config.set("language", value)
        self.context.apply_settings()
        self.language_changed = True
        QMessageBox.information(
            self,
            tr("Язык изменён", "Language changed"),
            tr(
                "Язык интерфейса будет полностью обновлён после перезапуска приложения.",
                "The interface language will be fully applied after restarting the application.",
            ),
        )

    def _on_log_level_changed(self) -> None:
        value = self.log_combo.currentData()
        self.context.config.set("log_level", value)
        from app.utils.logger import set_log_level

        set_log_level(value)
        self.status_label.setText(tr("Уровень логирования обновлён", "Log level updated"))

    def _save_advanced(self, *_args) -> None:
        if not hasattr(self, "autobackup_check"):
            return
        self.context.config.update(
            {
                "autobackup_enabled": self.autobackup_check.isChecked(),
                "autobackup_interval_hours": int(self.interval_combo.currentData() or 24),
                "autobackup_keep": int(self.keep_spin.value()),
            }
        )
        self._refresh_backup_info()

    # -- actions ---------------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.progress.setVisible(busy)
        self.close_button.setEnabled(not busy)

    def _open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.context.paths.root)))

    def _open_logs_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.context.paths.logs_dir)))

    def _manual_backup(self) -> None:
        default = self.context.paths.backups_dir / "MyApplications_Backup.zip"
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Сохранить резервную копию", "Save backup"),
            str(default),
            "ZIP (*.zip)",
        )
        if not path:
            return
        self._set_busy(True)
        self.status_label.setText(tr("Создание резервной копии…", "Creating backup…"))
        self.tasks.run(
            self.context.backups.create_manual_backup,
            path,
            wants_progress=True,
            on_finished=self._on_backup_done,
            on_failed=self._on_task_failed,
        )

    def _on_backup_done(self, path) -> None:
        self._set_busy(False)
        self.status_label.setText(tr(f"Резервная копия создана: {path}", f"Backup created: {path}"))
        self._refresh_backup_info()
        self.storage_changed = True

    def _export_archive(self) -> None:
        default = self.context.paths.backups_dir / "MyApplications_Export.zip"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Экспорт данных", "Export data"), str(default), "ZIP (*.zip)"
        )
        if not path:
            return
        self._set_busy(True)
        self.status_label.setText(tr("Экспорт данных…", "Exporting data…"))
        self.tasks.run(
            self.context.backups.export_archive,
            path,
            wants_progress=True,
            on_finished=self._on_export_done,
            on_failed=self._on_task_failed,
        )

    def _on_export_done(self, path) -> None:
        self._set_busy(False)
        self.status_label.setText(tr(f"Данные экспортированы: {path}", f"Data exported: {path}"))

    def _import_archive(self) -> None:
        self._run_restore(dialog_title=tr("Импорт данных", "Import data"))

    def _restore_archive(self) -> None:
        self._run_restore(dialog_title=tr("Восстановление данных", "Restore data"))

    def _run_restore(self, *, dialog_title: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, dialog_title, str(self.context.paths.backups_dir), "ZIP (*.zip)"
        )
        if not path:
            return
        try:
            inspection = self.context.backups.inspect(path)
        except BackupError as exc:
            QMessageBox.warning(self, tr("Ошибка архива", "Archive error"), str(exc))
            return
        counts = inspection.counts
        details = tr(
            f"Записей: {counts['entries']}\nКатегорий: {counts['categories']}\n"
            f"Тегов: {counts['tags']}\nСсылок: {counts['links']}\n"
            f"Изображений: {counts['images']}\n"
            f"Создан: {format_datetime(inspection.created_at) or '—'}\n"
            f"Совпадающих записей: {inspection.conflicts}",
            f"Entries: {counts['entries']}\nCategories: {counts['categories']}\n"
            f"Tags: {counts['tags']}\nLinks: {counts['links']}\n"
            f"Images: {counts['images']}\n"
            f"Created: {format_datetime(inspection.created_at) or '—'}\n"
            f"Matching entries: {inspection.conflicts}",
        )
        box = QMessageBox(self)
        box.setWindowTitle(tr("Проверка архива", "Archive validation"))
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(tr("Архив проверен. Выберите действие:", "Archive validated. Choose an action:"))
        box.setInformativeText(details)
        merge_button = box.addButton(tr("Добавить к текущим", "Merge with current"), QMessageBox.ButtonRole.AcceptRole)
        replace_button = box.addButton(tr("Заменить все данные", "Replace all data"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("Отмена", "Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is merge_button:
            mode = "merge"
        elif clicked is replace_button:
            if QMessageBox.question(
                self,
                tr("Подтверждение", "Confirmation"),
                tr(
                    "Все текущие записи будут заменены данными из архива.\n"
                    "Перед импортом автоматически создаётся копия текущей базы. Продолжить?",
                    "All current entries will be replaced with the archive data.\n"
                    "A snapshot of the current database is created first. Continue?",
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
            mode = "replace"
        else:
            return

        self._set_busy(True)
        self.status_label.setText(tr("Импорт данных…", "Importing data…"))
        self.tasks.run(
            self.context.backups.restore,
            path,
            mode=mode,
            wants_progress=True,
            on_finished=self._on_restore_done,
            on_failed=self._on_task_failed,
        )

    def _on_restore_done(self, result) -> None:
        self._set_busy(False)
        self.storage_changed = True
        self.status_label.setText(
            tr(
                f"Импорт завершён: записей {result['entries']}, категорий {result['categories']}, "
                f"тегов {result['tags']}, изображений {result['images']}",
                f"Import finished: {result['entries']} entries, {result['categories']} categories, "
                f"{result['tags']} tags, {result['images']} images",
            )
        )
        self._refresh_storage_info()
        self._refresh_backup_info()

    def _on_task_failed(self, message: str) -> None:
        self._set_busy(False)
        self.status_label.setText(tr("Операция не выполнена", "Operation failed"))
        QMessageBox.warning(self, tr("Ошибка", "Error"), message)

    def _cleanup_images(self) -> None:
        try:
            removed = self.context.entries.cleanup_orphan_images()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("Ошибка", "Error"), str(exc))
            return
        self.storage_changed = True
        self._refresh_storage_info()
        QMessageBox.information(
            self,
            tr("Очистка завершена", "Cleanup finished"),
            tr(f"Удалено файлов: {removed}", f"Removed files: {removed}"),
        )

    def _run_backup_now(self) -> None:
        self._set_busy(True)
        self.status_label.setText(tr("Создание резервной копии…", "Creating backup…"))

        def job(progress=None):
            path = self.context.backups.manager.create_database_backup(prefix="manual")
            self.context.backups.cleanup_auto()
            from app.utils.helpers import utc_now_iso

            self.context.config.update(
                {"last_backup_at": utc_now_iso(), "last_backup_path": str(path)}
            )
            return path

        self.tasks.run(job, on_finished=self._on_backup_done, on_failed=self._on_task_failed)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._busy:
            event.ignore()
            return
        super().closeEvent(event)
