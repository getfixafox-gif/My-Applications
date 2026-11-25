"""Application entry point: builds the context and shows the main window."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from app.application import create_context
from app.i18n import tr
from app.ui.styles.theme import build_stylesheet
from app.utils.logger import get_logger
from app.version import APP_NAME, APP_VERSION


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="my-applications", description=APP_NAME)
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Каталог данных приложения (по умолчанию — платформенный путь)",
    )
    parser.add_argument("--version", action="store_true", help="Показать версию и выйти")
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)
    if args.version:
        print(f"{APP_NAME} {APP_VERSION}")
        return 0

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("MyApplications")
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")

    data_dir = Path(args.data_dir) if args.data_dir else None
    try:
        context = create_context(data_dir)
    except Exception as exc:  # noqa: BLE001 - fatal startup error
        QMessageBox.critical(
            None,
            tr("Ошибка запуска", "Startup error"),
            tr(
                f"Не удалось запустить приложение:\n{exc}",
                f"The application failed to start:\n{exc}",
            ),
        )
        return 1

    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    app.setStyleSheet(build_stylesheet(context.config.get("theme", "dark")))

    from app.ui.styles.icons import app_icon

    app.setWindowIcon(app_icon())

    from app.ui.windows.main_window import MainWindow

    window = MainWindow(context)
    window.show()

    exit_code = app.exec()
    try:
        context.shutdown()
    except Exception:  # noqa: BLE001 - shutdown must never crash
        get_logger().exception("Shutdown error")
    return exit_code


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
