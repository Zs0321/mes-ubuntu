from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Any


class RepairTaskManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: dict[str, dict[str, Any]] = {}

    def create(self, kind: str, target: str) -> dict[str, Any]:
        task_id = uuid.uuid4().hex
        task = {
            'task_id': task_id,
            'kind': kind,
            'target': target,
            'status': 'queued',
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'updated_at': datetime.now().isoformat(timespec='seconds'),
            'message': '',
            'result': {},
        }
        with self._lock:
            self._tasks[task_id] = task
        return dict(task)

    def update(self, task_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(task_id)
            task.update(fields)
            task['updated_at'] = datetime.now().isoformat(timespec='seconds')
            return dict(task)

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None
