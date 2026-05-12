"""
system_logs 写入服务（异步队列 + 后台线程批量落库）

设计目标：
- 请求线程：只做轻量事件构造 + 入队；队列满时丢弃（不阻塞请求）。
- 后台线程：批量 INSERT，定期清理（30 天），WAL 模式。
"""

from __future__ import annotations

import atexit
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import system_logs_db


def now_ms() -> int:
    return int(time.time() * 1000)


def _safe_str(v: Any, *, max_len: int = 1024) -> Optional[str]:
    if v is None:
        return None
    s = str(v)
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


@dataclass
class SystemLogEvent:
    ts: int
    kind: str
    level: str = "INFO"
    success: Optional[bool] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    query_keys: Optional[str] = None
    status_code: Optional[int] = None
    duration_ms: Optional[int] = None
    action: Optional[str] = None
    target: Optional[str] = None
    message: Optional[str] = None
    details_json: Optional[Any] = None

    def to_row(self) -> Dict[str, Any]:
        return {
            "ts": int(self.ts),
            "kind": _safe_str(self.kind, max_len=32) or "system",
            "level": _safe_str(self.level, max_len=16) or "INFO",
            "success": self.success,
            "user_id": _safe_str(self.user_id, max_len=64),
            "username": _safe_str(self.username, max_len=128),
            "display_name": _safe_str(self.display_name, max_len=128),
            "ip": _safe_str(self.ip, max_len=64),
            "user_agent": _safe_str(self.user_agent, max_len=512),
            "request_id": _safe_str(self.request_id, max_len=64),
            "method": _safe_str(self.method, max_len=16),
            "path": _safe_str(self.path, max_len=512),
            "query_keys": _safe_str(self.query_keys, max_len=512),
            "status_code": self.status_code,
            "duration_ms": self.duration_ms,
            "action": _safe_str(self.action, max_len=128),
            "target": _safe_str(self.target, max_len=256),
            "message": _safe_str(self.message, max_len=1024),
            "details_json": self.details_json,
        }


class SystemLogsWriter:
    def __init__(
        self,
        *,
        db_path: Path,
        retention_days: int = 30,
        max_queue: int = 5000,
        batch_size: int = 200,
        flush_interval_sec: float = 1.0,
        cleanup_interval_sec: float = 3600.0,
    ) -> None:
        self.db_path = Path(db_path)
        self.retention_days = int(retention_days)
        self.q: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=int(max_queue))
        self.batch_size = int(batch_size)
        self.flush_interval_sec = float(flush_interval_sec)
        self.cleanup_interval_sec = float(cleanup_interval_sec)

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="system-logs-writer", daemon=True)

        self.dropped = 0
        self.written = 0
        self._lock = threading.Lock()

        system_logs_db.ensure_system_logs_db(self.db_path)
        self._thread.start()
        atexit.register(self.shutdown)

    def enqueue(self, row: Dict[str, Any]) -> None:
        if self._stop.is_set():
            return
        try:
            self.q.put_nowait(row)
        except queue.Full:
            with self._lock:
                self.dropped += 1

    def enqueue_event(self, ev: SystemLogEvent) -> None:
        self.enqueue(ev.to_row())

    def shutdown(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        try:
            self._thread.join(timeout=3.0)
        except Exception:
            pass
        # Best-effort final flush (in current thread).
        self._flush_drain(max_items=2000)

    def _flush_drain(self, *, max_items: int) -> None:
        buf: List[Dict[str, Any]] = []
        while len(buf) < max_items:
            try:
                buf.append(self.q.get_nowait())
            except queue.Empty:
                break
        if buf:
            n = system_logs_db.insert_system_logs(self.db_path, buf)
            with self._lock:
                self.written += n

    def _run(self) -> None:
        buf: List[Dict[str, Any]] = []
        last_flush = time.time()
        last_cleanup = 0.0

        while not self._stop.is_set():
            timeout = max(0.05, self.flush_interval_sec / 2)
            try:
                item = self.q.get(timeout=timeout)
                buf.append(item)
            except queue.Empty:
                pass

            now = time.time()
            should_flush = len(buf) >= self.batch_size or (buf and (now - last_flush) >= self.flush_interval_sec)
            if should_flush:
                try:
                    n = system_logs_db.insert_system_logs(self.db_path, buf)
                    with self._lock:
                        self.written += n
                except Exception:
                    # 不让日志写入异常影响主线程；这里吞掉异常即可（必要时后续加内部 logger）。
                    pass
                buf = []
                last_flush = now

            if self.retention_days > 0 and (now - last_cleanup) >= self.cleanup_interval_sec:
                try:
                    system_logs_db.cleanup_system_logs(self.db_path, retention_days=self.retention_days)
                except Exception:
                    pass
                last_cleanup = now

