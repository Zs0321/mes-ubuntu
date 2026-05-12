#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
照片文件索引（SQLite）

目标：
- 为 /admin/photos 提供“最近照片”快速查询，避免每次页面加载都全量扫描目录
- 以 file_path 为主键，保存 mtime/size 与从路径/文件名解析出的元数据
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


DEFAULT_DB_PATH = Path(__file__).parent / "cache" / "photos" / "photo_index.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # 尽量提升并发读写体验；失败也不影响功能
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    return conn


def ensure_index_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """确保索引 DB 与表结构存在。"""
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS photo_file_index (
              file_path   TEXT PRIMARY KEY,
              mtime_sec   INTEGER NOT NULL,
              size_bytes  INTEGER NOT NULL,
              project_name TEXT,
              product_name TEXT,
              serial_number TEXT,
              process_step TEXT,
              filename    TEXT
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_photo_mtime ON photo_file_index(mtime_sec DESC);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_photo_serial ON photo_file_index(serial_number);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_photo_process ON photo_file_index(process_step);"
        )


def upsert_photo(record: dict[str, Any], db_path: Path = DEFAULT_DB_PATH) -> None:
    """
    写入/更新单条记录。
    record 需要包含：
      file_path, mtime_sec, size_bytes, project_name, product_name,
      serial_number, process_step, filename
    """
    ensure_index_db(db_path)
    with _connect(db_path) as conn:
        _upsert_many(conn, [record])


def _upsert_many(conn: sqlite3.Connection, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    conn.executemany(
        """
        INSERT INTO photo_file_index (
          file_path, mtime_sec, size_bytes, project_name, product_name,
          serial_number, process_step, filename
        )
        VALUES (
          :file_path, :mtime_sec, :size_bytes, :project_name, :product_name,
          :serial_number, :process_step, :filename
        )
        ON CONFLICT(file_path) DO UPDATE SET
          mtime_sec=excluded.mtime_sec,
          size_bytes=excluded.size_bytes,
          project_name=excluded.project_name,
          product_name=excluded.product_name,
          serial_number=excluded.serial_number,
          process_step=excluded.process_step,
          filename=excluded.filename;
        """,
        records,
    )


def query_recent(days: int, limit: int, db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    """按 mtime 倒序查询最近照片。返回字段形状与 scan-directory-async 保持一致。"""
    ensure_index_db(db_path)

    now_sec = int(time.time())
    since_sec = 0
    if days is not None and days > 0:
        since_sec = now_sec - int(days) * 86400

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
              file_path, mtime_sec, size_bytes,
              project_name, product_name, serial_number, process_step, filename
            FROM photo_file_index
            WHERE mtime_sec >= ?
            ORDER BY mtime_sec DESC
            LIMIT ?;
            """,
            (since_sec, int(limit)),
        ).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        file_path = r["file_path"]
        out.append(
            {
                "id": file_path,
                "filename": r["filename"],
                "projectName": r["project_name"],
                "productName": r["product_name"],
                "serialNumber": r["serial_number"],
                "processStep": r["process_step"],
                "thumbnailUrl": f"/api/photos/async/thumbnail?path={file_path}",
                "fullUrl": f"/api/photos/async/full?path={file_path}",
                "originalUrl": f"/api/photos/async/original?path={file_path}",
                "size": int(r["size_bytes"]),
                "timestamp": int(r["mtime_sec"]) * 1000,
            }
        )
    return out


def remove_paths(file_paths: list[str], db_path: Path = DEFAULT_DB_PATH) -> int:
    """按文件路径删除索引记录，返回删除条数。"""
    ensure_index_db(db_path)
    normalized_paths = []
    for path in file_paths or []:
        text = str(path or "").strip()
        if not text:
            continue
        normalized_paths.append(text)

    if not normalized_paths:
        return 0

    deleted = 0
    with _connect(db_path) as conn:
        for path in normalized_paths:
            cursor = conn.execute(
                """
                DELETE FROM photo_file_index
                WHERE file_path = ?
                   OR REPLACE(file_path, '\\', '/') = REPLACE(?, '\\', '/')
                """,
                (path, path),
            )
            deleted += int(cursor.rowcount or 0)
    return deleted


def query_stats(days: Optional[int] = None, db_path: Path = DEFAULT_DB_PATH) -> dict[str, int]:
    """
    查询索引统计。
    - days 为 None: 全量统计
    - days 为正整数: 最近 N 天统计
    """
    ensure_index_db(db_path)

    since_sec = 0
    if isinstance(days, int) and days > 0:
        now_sec = int(time.time())
        since_sec = now_sec - int(days) * 86400

    sql = """
        SELECT
          COUNT(*) AS total_photos,
          COALESCE(SUM(size_bytes), 0) AS total_size_bytes,
          COUNT(DISTINCT CASE
            WHEN serial_number IS NOT NULL AND TRIM(serial_number) != '' THEN serial_number
          END) AS product_count,
          COUNT(DISTINCT CASE
            WHEN process_step IS NOT NULL AND TRIM(process_step) != '' THEN process_step
          END) AS process_count,
          COUNT(DISTINCT strftime('%Y%m%d', mtime_sec, 'unixepoch', 'localtime')) AS date_count
        FROM photo_file_index
    """
    params = ()
    if since_sec > 0:
        sql += " WHERE mtime_sec >= ?"
        params = (since_sec,)

    with _connect(db_path) as conn:
        row = conn.execute(sql, params).fetchone()

    if row is None:
        return {
            "totalPhotos": 0,
            "totalSizeBytes": 0,
            "productCount": 0,
            "processCount": 0,
            "dateCount": 0,
        }

    return {
        "totalPhotos": int(row["total_photos"] or 0),
        "totalSizeBytes": int(row["total_size_bytes"] or 0),
        "productCount": int(row["product_count"] or 0),
        "processCount": int(row["process_count"] or 0),
        "dateCount": int(row["date_count"] or 0),
    }


def query_recent_stats(days: int, db_path: Path = DEFAULT_DB_PATH) -> dict[str, int]:
    """向后兼容：查询最近 N 天统计。"""
    return query_stats(days=days, db_path=db_path)


@dataclass(frozen=True)
class ScanFilters:
    project_name: Optional[str] = None
    product_name: Optional[str] = None
    serial_number: Optional[str] = None


def _serial_matches_query(serial_name: str, query: str | None) -> bool:
    query_text = str(query or "").strip().casefold()
    if not query_text:
        return True
    return query_text in str(serial_name or "").strip().casefold()


def _parse_search_pattern(search_pattern: str) -> ScanFilters:
    """
    兼容 async_photo_api.py 当前的 search_pattern 构建方式：
      serial:  */*/{serial}
      product: */{product}/*
      project: {project}/*/*
      all:     */*/*
    """
    parts = (search_pattern or "").split("/")
    if len(parts) != 3:
        return ScanFilters()

    a, b, c = parts
    if a != "*" and b == "*" and c == "*":
        return ScanFilters(project_name=a)
    if a == "*" and b != "*" and c == "*":
        return ScanFilters(product_name=b)
    if a == "*" and b == "*" and c != "*":
        return ScanFilters(serial_number=c)
    return ScanFilters()


def _derive_process_step(filename: str) -> str:
    # 文件名格式: {serial}_{process}_{timestamp}.jpg（部分历史文件可能不完整）
    stem = filename[:-4] if filename.lower().endswith(".jpg") else filename
    parts = stem.split("_")
    if len(parts) > 1 and parts[1]:
        return parts[1]
    return "未知工序"


def scan_and_update(
    base_path: Path,
    search_pattern: str,
    days: int | None,
    limit_hint: int | None,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """
    扫描 picture 根目录（默认 3 层：project/product/serial）并更新索引。

    - days/limit_hint: 当前仅用于统计/未来扩展（不影响正确性）
    - 返回 stats，用于日志/运维观察
    """
    t0 = time.time()
    ensure_index_db(db_path)

    filters = _parse_search_pattern(search_pattern)
    scanned_dirs = 0
    scanned_files = 0
    indexed = 0
    errors = 0

    if not base_path.exists():
        return {
            "ok": False,
            "reason": "base_path_not_found",
            "basePath": str(base_path),
            "indexed": 0,
            "scanned_dirs": 0,
            "scanned_files": 0,
            "errors": 0,
            "durationSec": round(time.time() - t0, 3),
        }

    records: list[dict[str, Any]] = []

    def want_project(name: str) -> bool:
        return filters.project_name is None or name == filters.project_name

    def want_product(name: str) -> bool:
        return filters.product_name is None or name == filters.product_name

    with _connect(db_path) as conn:
        try:
            for proj in os.scandir(str(base_path)):
                if not proj.is_dir():
                    continue
                project_name = proj.name
                if not want_project(project_name):
                    continue

                for prod in os.scandir(proj.path):
                    if not prod.is_dir():
                        continue
                    product_name = prod.name
                    if not want_product(product_name):
                        continue

                    for ser in os.scandir(prod.path):
                        if not ser.is_dir():
                            continue
                        if filters.serial_number and not _serial_matches_query(ser.name, filters.serial_number):
                            continue
                        scanned_dirs += 1
                        _scan_serial_dir(
                            ser.path,
                            project_name,
                            product_name,
                            ser.name,
                            records,
                        )

            scanned_files = len(records)
            _upsert_many(conn, records)
            indexed = len(records)

            # 清理索引中的历史脏数据：
            # 1) 删除不属于当前 base_path 根目录的记录（例如 PHOTOS_DIR 切换后的旧绝对路径）
            # 2) 删除当前根目录下已不存在的旧文件记录
            normalized_expr = "REPLACE(file_path, '\\\\', '/')"
            scope_prefixes = []
            for candidate in (base_path, base_path.resolve()):
                normalized = str(candidate).replace("\\", "/").rstrip("/")
                if normalized and normalized not in scope_prefixes:
                    scope_prefixes.append(normalized)
            scope_like_values = [f"{prefix}/%" for prefix in scope_prefixes]
            scope_match_sql = " OR ".join(f"{normalized_expr} LIKE ?" for _ in scope_like_values)
            scope_not_match_sql = " AND ".join(f"{normalized_expr} NOT LIKE ?" for _ in scope_like_values)

            if scope_like_values:
                conn.execute(
                    f"DELETE FROM photo_file_index WHERE {scope_not_match_sql}",
                    tuple(scope_like_values),
                )

            conn.execute("DROP TABLE IF EXISTS _tmp_scanned_paths")
            conn.execute("CREATE TEMP TABLE _tmp_scanned_paths(file_path TEXT PRIMARY KEY)")
            conn.executemany(
                "INSERT OR IGNORE INTO _tmp_scanned_paths(file_path) VALUES (?)",
                ((r["file_path"],) for r in records),
            )
            if scope_like_values:
                conn.execute(
                    f"""
                    DELETE FROM photo_file_index
                    WHERE ({scope_match_sql})
                      AND file_path NOT IN (SELECT file_path FROM _tmp_scanned_paths)
                    """,
                    tuple(scope_like_values),
                )
            conn.execute("DROP TABLE IF EXISTS _tmp_scanned_paths")
        except Exception:
            errors += 1
            raise

    return {
        "ok": True,
        "basePath": str(base_path),
        "filters": {
            "projectName": filters.project_name,
            "productName": filters.product_name,
            "serialNumber": filters.serial_number,
            "days": days,
            "limitHint": limit_hint,
        },
        "indexed": indexed,
        "scanned_dirs": scanned_dirs,
        "scanned_files": scanned_files,
        "errors": errors,
        "durationSec": round(time.time() - t0, 3),
    }


def _scan_serial_dir(
    serial_dir_path: str,
    project_name: str,
    product_name: str,
    serial_number: str,
    out_records: list[dict[str, Any]],
) -> None:
    for ent in os.scandir(serial_dir_path):
        if not ent.is_file():
            continue
        name = ent.name
        if not name.lower().endswith(".jpg"):
            continue
        try:
            st = ent.stat()
            out_records.append(
                {
                    "file_path": ent.path,
                    "mtime_sec": int(st.st_mtime),
                    "size_bytes": int(st.st_size),
                    "project_name": project_name,
                    "product_name": product_name,
                    "serial_number": serial_number,
                    "process_step": _derive_process_step(name),
                    "filename": name,
                }
            )
        except Exception:
            # 单文件失败不影响全局扫描
            continue
