from __future__ import annotations

from threading import Event, Thread
from typing import Any

from findmyfuel.sync import SyncService


class BackgroundRefreshLoop:
    def __init__(self, sync_service: SyncService, interval_minutes: int) -> None:
        self.sync_service = sync_service
        self.interval_minutes = interval_minutes
        self._stop_event = Event()
        self._thread: Thread | None = None

    @property
    def enabled(self) -> bool:
        return self.interval_minutes > 0

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = Thread(target=self._run, name="findmyfuel-refresh", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval_minutes": self.interval_minutes,
            "running": bool(self._thread and self._thread.is_alive()),
        }

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.sync_service.refresh()
            except Exception:
                pass
            if self._stop_event.wait(self.interval_minutes * 60):
                break
