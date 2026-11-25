"""Application logging setup."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "myapplications"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(log_dir: Path, level: str = "INFO") -> logging.Logger:
    """Configure console + rotating file logging and return the app logger."""
    log_dir.mkdir(parents=True, exist_ok=True)
    normalized = level.upper() if str(level).upper() in LOG_LEVELS else "INFO"

    root = logging.getLogger()
    root.setLevel(getattr(logging, normalized, logging.INFO))

    # Avoid duplicate handlers when setup runs more than once (e.g. tests).
    for handler in list(root.handlers):
        if getattr(handler, "_my_app_handler", False):
            root.removeHandler(handler)
            handler.close()

    file_handler = RotatingFileHandler(
        log_dir / "application.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    file_handler._my_app_handler = True  # type: ignore[attr-defined]

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
    console_handler._my_app_handler = True  # type: ignore[attr-defined]

    root.addHandler(file_handler)
    root.addHandler(console_handler)

    logger = logging.getLogger(LOGGER_NAME)
    logger.debug("Logging configured (level=%s, dir=%s)", normalized, log_dir)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    if not name:
        return logging.getLogger(LOGGER_NAME)
    if name.startswith(LOGGER_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def set_log_level(level: str) -> None:
    normalized = level.upper() if str(level).upper() in LOG_LEVELS else "INFO"
    for handler in logging.getLogger().handlers:
        handler.setLevel(getattr(logging, normalized, logging.INFO))
    logging.getLogger().setLevel(getattr(logging, normalized, logging.INFO))
