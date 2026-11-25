"""Background worker helpers so long file operations never freeze the UI."""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from app.utils.logger import get_logger

logger = get_logger("tasks")


class TaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str, int, int)


class Task(QRunnable):
    """Runs ``func`` in the global thread pool.

    The callable receives an optional ``progress`` keyword when it accepts one.
    """

    def __init__(
        self,
        func: Callable[..., Any],
        *args: Any,
        wants_progress: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.wants_progress = wants_progress
        self.signals = TaskSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:  # pragma: no cover - runs in a worker thread
        try:
            if self.wants_progress:
                result = self.func(
                    *self.args,
                    progress=lambda stage, done, total: self.signals.progress.emit(
                        stage, int(done), int(total)
                    ),
                    **self.kwargs,
                )
            else:
                result = self.func(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - reported to the UI
            logger.error("Background task failed: %s\n%s", exc, traceback.format_exc())
            self.signals.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.signals.finished.emit(result)


class TaskRunner:
    """Convenience wrapper around ``QThreadPool``."""

    def __init__(self, pool: QThreadPool | None = None) -> None:
        self.pool = pool or QThreadPool.globalInstance()

    def run(
        self,
        func: Callable[..., Any],
        *args: Any,
        on_finished: Callable[[Any], None] | None = None,
        on_failed: Callable[[str], None] | None = None,
        on_progress: Callable[[str, int, int], None] | None = None,
        wants_progress: bool = False,
        **kwargs: Any,
    ) -> Task:
        task = Task(func, *args, wants_progress=wants_progress, **kwargs)
        if on_finished:
            task.signals.finished.connect(on_finished)
        if on_failed:
            task.signals.failed.connect(on_failed)
        if on_progress:
            task.signals.progress.connect(on_progress)
        self.pool.start(task)
        return task

    @staticmethod
    def wait_for_all() -> None:
        QThreadPool.globalInstance().waitForDone(10_000)
