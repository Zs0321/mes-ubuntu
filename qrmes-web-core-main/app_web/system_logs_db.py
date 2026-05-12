"""
SQLite 结构化日志存储（system_logs）

说明：
- app_web 不是标准 Python package，本模块会被 app_web/mesapp.py 直接 import。
- 目标：提供“初始化 + 批量写入 + 分页查询 + 保留期清理”的最小可用能力。
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


SCHEMA_VERSION = 1


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row

    # Pragmas tuned for write-heavy, read-mostly audit logs.
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=2000;")
    return conn


def ensure_system_logs_db(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                kind TEXT NOT NULL,
                level TEXT NOT NULL,
                success INTEGER,
                user_id TEXT,
                username TEXT,
                display_name TEXT,
                ip TEXT,
                user_agent TEXT,
                request_id TEXT,
                method TEXT,
                path TEXT,
                query_keys TEXT,
                status_code INTEGER,
                duration_ms INTEGER,
                action TEXT,
                target TEXT,
                message TEXT,
                details_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_logs_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO system_logs_meta(key, value) VALUES(?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_ts ON system_logs(ts)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_system_logs_kind_ts ON system_logs(kind, ts)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_system_logs_user_ts ON system_logs(username, ts)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_system_logs_path_ts ON system_logs(path, ts)"
        )


def insert_system_logs(db_path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    rows_list = list(rows)
    if not rows_list:
        return 0

    def _norm_details(v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, str):
            return v
        try:
            return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return str(v)

    params: List[Tuple[Any, ...]] = []
    for r in rows_list:
        params.append(
            (
                int(r.get("ts") or 0),
                str(r.get("kind") or "system"),
                str(r.get("level") or "INFO"),
                None if r.get("success") is None else (1 if bool(r.get("success")) else 0),
                r.get("user_id"),
                r.get("username"),
                r.get("display_name"),
                r.get("ip"),
                r.get("user_agent"),
                r.get("request_id"),
                r.get("method"),
                r.get("path"),
                r.get("query_keys"),
                r.get("status_code"),
                r.get("duration_ms"),
                r.get("action"),
                r.get("target"),
                r.get("message"),
                _norm_details(r.get("details_json")),
            )
        )

    with _connect(db_path) as conn:
        cur = conn.executemany(
            """
            INSERT INTO system_logs(
                ts, kind, level, success,
                user_id, username, display_name,
                ip, user_agent, request_id,
                method, path, query_keys,
                status_code, duration_ms,
                action, target, message, details_json
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?, ?, ?
            )
            """,
            params,
        )
        return cur.rowcount if cur.rowcount is not None else len(params)


@dataclass(frozen=True)
class LogCursor:
    ts: int
    id: int


def query_system_logs(
    db_path: Path,
    *,
    limit: int = 50,
    cursor: Optional[LogCursor] = None,
    kind: Optional[str] = None,
    level: Optional[str] = None,
    username: Optional[str] = None,
    path_prefix: Optional[str] = None,
    status_code: Optional[int] = None,
    from_ts: Optional[int] = None,
    to_ts: Optional[int] = None,
    q: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[LogCursor]]:
    limit = int(limit or 50)
    if limit <= 0:
        limit = 50
    limit = min(limit, 200)

    where: List[str] = []
    args: List[Any] = []

    if kind:
        where.append("kind = ?")
        args.append(kind)
    if level:
        where.append("level = ?")
        args.append(level)
    if username:
        where.append("username = ?")
        args.append(username)
    if path_prefix:
        where.append("path LIKE ?")
        args.append(f"{path_prefix}%")
    if status_code is not None:
        where.append("status_code = ?")
        args.append(int(status_code))
    if from_ts is not None:
        where.append("ts >= ?")
        args.append(int(from_ts))
    if to_ts is not None:
        where.append("ts <= ?")
        args.append(int(to_ts))

    if cursor:
        # Keyset pagination: (ts DESC, id DESC)
        where.append("(ts < ? OR (ts = ? AND id < ?))")
        args.extend([int(cursor.ts), int(cursor.ts), int(cursor.id)])

    if q:
        # Simple search (avoid full table scan by keeping it optional + limited result set).
        like = f"%{q}%"
        where.append(
            "("
            "path LIKE ? OR message LIKE ? OR action LIKE ? OR target LIKE ? OR details_json LIKE ?"
            ")"
        )
        args.extend([like, like, like, like, like])

    sql = "SELECT * FROM system_logs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ts DESC, id DESC LIMIT ?"
    args.append(limit)

    with _connect(db_path) as conn:
        cur = conn.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]

    next_cursor: Optional[LogCursor] = None
    if rows:
        last = rows[-1]
        next_cursor = LogCursor(ts=int(last["ts"]), id=int(last["id"]))

    return rows, next_cursor


def cleanup_system_logs(db_path: Path, *, retention_days: int) -> int:
    retention_days = int(retention_days)
    if retention_days <= 0:
        return 0

    # ts is ms.
    cutoff_ms = int(time.time() * 1000) - retention_days * 24 * 3600 * 1000

    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM system_logs WHERE ts < ?", (cutoff_ms,))
        return cur.rowcount if cur.rowcount is not None else 0

