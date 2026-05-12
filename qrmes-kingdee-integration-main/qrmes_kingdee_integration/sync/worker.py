from __future__ import annotations

import threading
import time
from typing import Any


class SyncWorker:
    def __init__(
        self,
        *,
        store: Any,
        pull_services: dict[str, Any],
        outbound_services: dict[str, Any],
        pull_interval_seconds: int = 60,
    ):
        self.store = store
        self.pull_services = pull_services
        self.outbound_services = outbound_services
        self.pull_interval_seconds = max(int(pull_interval_seconds), 1)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> None:
        for service in self.pull_services.values():
            service.sync_from_kingdee(limit=100)
        for service in self.outbound_services.values():
            service.process_pending_changes(limit=100)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name='kingdee-sync-worker')
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self.run_once()
            self._stop_event.wait(self.pull_interval_seconds)
