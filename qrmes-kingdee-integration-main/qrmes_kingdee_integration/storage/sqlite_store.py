from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class SQLiteSyncStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                '''
                create table if not exists kingdee_objects (
                    dataset text not null,
                    business_key text not null,
                    form_id text not null,
                    payload_json text not null,
                    source text not null,
                    created_at integer not null,
                    updated_at integer not null,
                    primary key (dataset, business_key)
                )
                '''
            )
            conn.execute(
                '''
                create table if not exists kingdee_change_queue (
                    id integer primary key autoincrement,
                    dataset text not null,
                    business_key text not null,
                    form_id text not null,
                    action text not null,
                    payload_json text not null,
                    status text not null,
                    remote_payload_json text,
                    created_at integer not null,
                    updated_at integer not null
                )
                '''
            )

    def upsert_object(self, *, dataset: str, business_key: str, form_id: str, payload: dict[str, Any], source: str) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                '''
                insert into kingdee_objects(dataset, business_key, form_id, payload_json, source, created_at, updated_at)
                values(?, ?, ?, ?, ?, ?, ?)
                on conflict(dataset, business_key) do update set
                    form_id=excluded.form_id,
                    payload_json=excluded.payload_json,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                ''',
                (dataset, business_key, form_id, json.dumps(payload, ensure_ascii=False), source, now, now),
            )

    def get_object(self, dataset: str, business_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                'select * from kingdee_objects where dataset=? and business_key=?',
                (dataset, business_key),
            ).fetchone()
        return self._map_object_row(row) if row else None

    def list_objects(self, dataset: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                'select * from kingdee_objects where dataset=? order by business_key asc limit ?',
                (dataset, int(limit)),
            ).fetchall()
        return [self._map_object_row(row) for row in rows]

    def enqueue_change(self, *, dataset: str, business_key: str, form_id: str, action: str, payload: dict[str, Any]) -> int:
        now = int(time.time())
        with self._connect() as conn:
            cur = conn.execute(
                '''
                insert into kingdee_change_queue(dataset, business_key, form_id, action, payload_json, status, created_at, updated_at)
                values(?, ?, ?, ?, ?, 'pending', ?, ?)
                ''',
                (dataset, business_key, form_id, action, json.dumps(payload, ensure_ascii=False), now, now),
            )
            return int(cur.lastrowid)

    def list_pending_changes(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "select * from kingdee_change_queue where status='pending' order by id asc limit ?",
                (int(limit),),
            ).fetchall()
        return [self._map_queue_row(row) for row in rows]

    def mark_change_done(self, queue_id: int, remote_payload: dict[str, Any] | None = None) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                'update kingdee_change_queue set status=?, remote_payload_json=?, updated_at=? where id=?',
                ('done', json.dumps(remote_payload or {}, ensure_ascii=False), now, int(queue_id)),
            )

    def _map_object_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            'dataset': row['dataset'],
            'business_key': row['business_key'],
            'form_id': row['form_id'],
            'payload': json.loads(row['payload_json']),
            'source': row['source'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
        }

    def _map_queue_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            'id': row['id'],
            'dataset': row['dataset'],
            'business_key': row['business_key'],
            'form_id': row['form_id'],
            'action': row['action'],
            'payload': json.loads(row['payload_json']),
            'status': row['status'],
            'remote_payload': json.loads(row['remote_payload_json']) if row['remote_payload_json'] else None,
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
        }
