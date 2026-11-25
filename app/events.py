"""Small application-wide event bus (loose coupling between layers)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from app.utils.logger import get_logger

logger = get_logger("events")

ENTRY_CREATED = "entry_created"
ENTRY_UPDATED = "entry_updated"
ENTRY_DELETED = "entry_deleted"
CATEGORY_CHANGED = "category_changed"
TAG_CHANGED = "tag_changed"
SETTINGS_CHANGED = "settings_changed"
BACKUP_FINISHED = "backup_finished"
STORAGE_CHANGED = "storage_changed"


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def subscribe(self, event: str, callback: Callable[..., Any]) -> None:
        if callback not in self._listeners[event]:
            self._listeners[event].append(callback)

    def unsubscribe(self, event: str, callback: Callable[..., Any]) -> None:
        if callback in self._listeners[event]:
            self._listeners[event].remove(callback)

    def emit(self, event: str, **payload: Any) -> None:
        for callback in list(self._listeners.get(event, ())):
            try:
                callback(**payload)
            except Exception:  # noqa: BLE001 - listeners must not break the app
                logger.exception("Listener for %s failed", event)


bus = EventBus()
