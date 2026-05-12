from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.traceability.coding import build_qr_payload, generate_batch_code, generate_package_code


IQC_RESULT_TO_STATUS = {
    "qualified": "qualified",
    "concession": "concession",
    "rejected": "rejected",
}


class TraceabilityStore:
    def __init__(self, sync_store: SQLiteSyncStore | str | Path):
        if isinstance(sync_store, SQLiteSyncStore):
            self.sync_store = sync_store
            self.db_path = sync_store.db_path
        else:
            self.sync_store = SQLiteSyncStore(sync_store)
            self.db_path = Path(sync_store)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                create table if not exists material_batch (
                    batch_code text primary key,
                    purchase_no text not null,
                    material_code text not null,
                    supplier_code text not null,
                    receive_date text not null,
                    qty real not null,
                    unit text not null,
                    package_count integer not null,
                    batch_status text not null,
                    trace_mode text not null,
                    supplier_qr_raw text,
                    payload_json text not null,
                    created_at integer not null,
                    updated_at integer not null
                );
                create table if not exists material_package (
                    package_code text primary key,
                    batch_code text not null,
                    package_index integer not null,
                    qty real not null,
                    unit text not null,
                    status text not null,
                    qr_payload_json text not null,
                    payload_json text not null,
                    created_at integer not null,
                    updated_at integer not null
                );
                create table if not exists supplier_qr_map (
                    id integer primary key autoincrement,
                    supplier_code text not null,
                    supplier_qr_raw text not null,
                    batch_code text not null,
                    payload_json text not null,
                    created_at integer not null
                );
                create table if not exists receive_record (
                    id integer primary key autoincrement,
                    receive_no text not null unique,
                    purchase_no text not null,
                    batch_code text not null,
                    material_code text not null,
                    supplier_code text not null,
                    qty real not null,
                    unit text not null,
                    package_count integer not null,
                    operator text,
                    payload_json text not null,
                    created_at integer not null
                );
                create table if not exists iqc_record (
                    id integer primary key autoincrement,
                    iqc_no text not null unique,
                    batch_code text not null,
                    result text not null,
                    report_no text,
                    inspector text,
                    remark text,
                    attachments_json text not null,
                    payload_json text not null,
                    created_at integer not null
                );
                create table if not exists iqc_attachment (
                    id integer primary key autoincrement,
                    attachment_id text not null unique,
                    ref_type text not null,
                    ref_no text not null,
                    batch_code text not null,
                    filename text not null,
                    content_type text,
                    size integer,
                    content_base64 text,
                    payload_json text not null,
                    created_at integer not null
                );
                create table if not exists inventory_stock (
                    id integer primary key autoincrement,
                    stock_key text not null unique,
                    batch_code text not null,
                    package_code text,
                    material_code text not null,
                    qty real not null,
                    unit text not null,
                    status text not null,
                    location_code text,
                    payload_json text not null,
                    created_at integer not null,
                    updated_at integer not null
                );
                create table if not exists stock_move (
                    id integer primary key autoincrement,
                    move_no text not null unique,
                    move_type text not null,
                    code text not null,
                    batch_code text,
                    package_code text,
                    material_code text,
                    qty real not null,
                    unit text,
                    from_status text,
                    to_status text,
                    location_code text,
                    operator text,
                    payload_json text not null,
                    created_at integer not null
                );
                create table if not exists pick_record (
                    id integer primary key autoincrement,
                    pick_no text not null unique,
                    work_order_no text,
                    product_sn text,
                    material_code text not null,
                    code text not null,
                    batch_code text,
                    package_code text,
                    qty real not null,
                    operator text,
                    payload_json text not null,
                    created_at integer not null
                );
                create table if not exists assembly_bind (
                    id integer primary key autoincrement,
                    bind_no text not null unique,
                    product_sn text not null,
                    material_code text not null,
                    batch_code text,
                    package_code text,
                    serial_no text,
                    bind_qty real not null,
                    position_code text,
                    operator text,
                    payload_json text not null,
                    created_at integer not null
                );
                create table if not exists trace_event_log (
                    id integer primary key autoincrement,
                    event_type text not null,
                    ref_code text not null,
                    batch_code text,
                    package_code text,
                    product_sn text,
                    payload_json text not null,
                    created_at integer not null
                );
                create table if not exists material_qrcode (
                    id integer primary key autoincrement,
                    code_type text not null,
                    code text not null unique,
                    batch_code text,
                    package_code text,
                    qr_payload_json text not null,
                    print_status text not null,
                    payload_json text not null,
                    created_at integer not null,
                    updated_at integer not null
                );
                create table if not exists code_sequences (
                    sequence_key text primary key,
                    material_code text not null,
                    supplier_code text not null,
                    sequence_date text not null,
                    current_value integer not null,
                    created_at integer not null,
                    updated_at integer not null
                );
                create table if not exists label_print_task (
                    id integer primary key autoincrement,
                    task_no text not null unique,
                    code_type text not null,
                    code text not null unique,
                    batch_code text,
                    package_code text,
                    qr_payload_json text not null,
                    status text not null,
                    printer_type text not null,
                    payload_json text not null,
                    created_at integer not null,
                    updated_at integer not null
                );
                create table if not exists pcba_transform (
                    id integer primary key autoincrement,
                    transform_no text unique,
                    pcba_batch_code text,
                    source_batch_code text,
                    source_package_code text,
                    product_sn text,
                    qty real,
                    unit text,
                    status text not null default 'draft',
                    payload_json text not null default '{}',
                    created_at integer not null,
                    updated_at integer not null
                );
                create table if not exists test_record (
                    id integer primary key autoincrement,
                    test_no text unique,
                    product_sn text,
                    pcba_batch_code text,
                    result text,
                    report_no text,
                    payload_json text not null default '{}',
                    created_at integer not null,
                    updated_at integer not null
                );
                create table if not exists shipment_record (
                    id integer primary key autoincrement,
                    shipment_no text,
                    box_code text,
                    product_sn text,
                    customer_code text,
                    status text not null default 'draft',
                    payload_json text not null default '{}',
                    created_at integer not null,
                    updated_at integer not null
                );
                """
            )

    def list_purchase_orders(self, keyword: str = "", limit: int = 50) -> list[dict[str, Any]]:
        rows = self.sync_store.list_objects("purchase_order", limit=max(int(limit), 1))
        keyword = keyword.strip().lower()
        if not keyword:
            return rows
        return [
            row for row in rows
            if keyword in row["business_key"].lower()
            or keyword in json.dumps(row.get("payload") or {}, ensure_ascii=False).lower()
        ]

    def receive_label(self, payload: dict[str, Any]) -> dict[str, Any]:
        purchase_no = _required(payload, "purchase_no")
        material_code = _required(payload, "material_code")
        supplier_code = _required(payload, "supplier_code")
        qty = _positive_float(payload.get("qty"), "qty")
        package_count = max(1, int(payload.get("package_count") or 1))
        unit = str(payload.get("unit") or "").strip() or "PCS"
        receive_date = str(payload.get("receive_date") or time.strftime("%Y-%m-%d")).strip()
        operator = str(payload.get("operator") or "").strip()
        supplier_qr_raw = str(payload.get("supplier_qr_raw") or "").strip()
        trace_mode = str(payload.get("trace_mode") or "batch_package").strip()
        now = int(time.time())
        sequence = self._next_daily_sequence(material_code, supplier_code, receive_date)
        batch_code = generate_batch_code(material_code, supplier_code, receive_date, sequence)
        receive_no = f"RCV-{now}-{sequence:04d}"
        batch_qr = build_qr_payload(
            code_type="batch",
            code=batch_code,
            material_code=material_code,
            supplier_code=supplier_code,
            batch_code=batch_code,
            pack_index=None,
            qty=qty,
            unit=unit,
            trace_mode=trace_mode,
        )
        package_qty = qty / package_count
        packages = []
        with self._connect() as conn:
            conn.execute(
                """
                insert into material_batch(
                    batch_code, purchase_no, material_code, supplier_code, receive_date, qty, unit,
                    package_count, batch_status, trace_mode, supplier_qr_raw, payload_json, created_at, updated_at
                ) values(?, ?, ?, ?, ?, ?, ?, ?, 'pending_iqc', ?, ?, ?, ?, ?)
                """,
                (
                    batch_code, purchase_no, material_code, supplier_code, receive_date, qty, unit,
                    package_count, trace_mode, supplier_qr_raw, _json(payload), now, now,
                ),
            )
            conn.execute(
                """
                insert into receive_record(
                    receive_no, purchase_no, batch_code, material_code, supplier_code, qty, unit,
                    package_count, operator, payload_json, created_at
                ) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (receive_no, purchase_no, batch_code, material_code, supplier_code, qty, unit, package_count, operator, _json(payload), now),
            )
            conn.execute(
                """
                insert into inventory_stock(
                    stock_key, batch_code, package_code, material_code, qty, unit, status,
                    location_code, payload_json, created_at, updated_at
                ) values(?, ?, null, ?, ?, ?, 'pending_iqc', null, ?, ?, ?)
                """,
                (batch_code, batch_code, material_code, qty, unit, _json({"source": "receive_label"}), now, now),
            )
            self._insert_qrcode(conn, "batch", batch_code, batch_code, None, batch_qr, now)
            if supplier_qr_raw:
                conn.execute(
                    "insert into supplier_qr_map(supplier_code, supplier_qr_raw, batch_code, payload_json, created_at) values(?, ?, ?, ?, ?)",
                    (supplier_code, supplier_qr_raw, batch_code, _json(payload), now),
                )
            for index in range(1, package_count + 1):
                package_code = generate_package_code(batch_code, index)
                package_qr = build_qr_payload(
                    code_type="package",
                    code=package_code,
                    material_code=material_code,
                    supplier_code=supplier_code,
                    batch_code=batch_code,
                    pack_index=index,
                    qty=package_qty,
                    unit=unit,
                    trace_mode=trace_mode,
                )
                conn.execute(
                    """
                    insert into material_package(
                        package_code, batch_code, package_index, qty, unit, status,
                        qr_payload_json, payload_json, created_at, updated_at
                    ) values(?, ?, ?, ?, ?, 'pending_iqc', ?, ?, ?, ?)
                    """,
                    (package_code, batch_code, index, package_qty, unit, package_qr, _json({"source": "receive_label"}), now, now),
                )
                self._insert_qrcode(conn, "package", package_code, batch_code, package_code, package_qr, now)
                packages.append({"package_code": package_code, "package_index": index, "qty": package_qty, "unit": unit, "qr_payload": package_qr})
            self._insert_event(conn, "receive_label", batch_code, batch_code, None, None, payload, now)
        return {"receive_no": receive_no, "batch_code": batch_code, "batch_qr_payload": batch_qr, "packages": packages}

    def get_batch(self, batch_code: str) -> dict[str, Any] | None:
        batch = self._one("select * from material_batch where batch_code=?", (batch_code,))
        if not batch:
            return None
        return {
            "batch": _row(batch),
            "packages": self._many("select * from material_package where batch_code=? order by package_index", (batch_code,)),
            "inventory": self._many("select * from inventory_stock where batch_code=? order by id", (batch_code,)),
            "qrcodes": self._many("select * from material_qrcode where batch_code=? order by id", (batch_code,)),
            "events": self._many("select * from trace_event_log where batch_code=? order by id", (batch_code,)),
        }

    def record_iqc(self, payload: dict[str, Any]) -> dict[str, Any]:
        batch_code = _required(payload, "batch_code")
        result = _required(payload, "result")
        if result not in IQC_RESULT_TO_STATUS:
            raise ValueError("result must be qualified, concession, or rejected")
        batch = self._require_batch(batch_code)
        status = IQC_RESULT_TO_STATUS[result]
        now = int(time.time())
        iqc_no = f"IQC-{now}-{self._count('iqc_record') + 1:04d}"
        attachments = self._normalize_iqc_attachments(payload.get("attachments"), iqc_no, batch_code, now)
        with self._connect() as conn:
            conn.execute("update material_batch set batch_status=?, updated_at=? where batch_code=?", (status, now, batch_code))
            conn.execute("update material_package set status=?, updated_at=? where batch_code=?", (status, now, batch_code))
            conn.execute("update inventory_stock set status=?, updated_at=? where batch_code=?", (status, now, batch_code))
            conn.execute(
                """
                insert into iqc_record(iqc_no, batch_code, result, report_no, inspector, remark, attachments_json, payload_json, created_at)
                values(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    iqc_no, batch_code, result, payload.get("report_no"), payload.get("inspector"), payload.get("remark"),
                    _json([self._attachment_meta(item) for item in attachments]), _json(payload), now,
                ),
            )
            for attachment in attachments:
                conn.execute(
                    """
                    insert into iqc_attachment(
                        attachment_id, ref_type, ref_no, batch_code, filename,
                        content_type, size, content_base64, payload_json, created_at
                    ) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attachment["attachment_id"],
                        attachment["ref_type"],
                        attachment["ref_no"],
                        attachment["batch_code"],
                        attachment["filename"],
                        attachment.get("content_type"),
                        attachment.get("size"),
                        attachment.get("content_base64"),
                        _json(attachment.get("payload") or {}),
                        now,
                    ),
                )
            self._insert_event(conn, "iqc", batch_code, batch_code, None, None, payload, now)
        return {
            "iqc_no": iqc_no,
            "batch_code": batch_code,
            "batch_status": status,
            "material_code": batch["material_code"],
            "attachments": [self._attachment_meta(item) for item in attachments],
        }

    def putaway(self, payload: dict[str, Any]) -> dict[str, Any]:
        code = _required(payload, "code")
        location_code = _required(payload, "location_code")
        qty = _positive_float(payload.get("qty"), "qty")
        operator = str(payload.get("operator") or "").strip()
        resolved = self._resolve_code(code)
        if resolved["status"] == "rejected":
            raise ValueError("rejected material cannot be put away")
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                "update inventory_stock set status='available', location_code=?, updated_at=? where batch_code=?",
                (location_code, now, resolved["batch_code"]),
            )
            self._insert_stock_move(conn, "putaway", code, resolved, qty, "available", location_code, operator, payload, now)
            self._insert_event(conn, "putaway", code, resolved["batch_code"], resolved.get("package_code"), None, payload, now)
        return {"code": code, "batch_code": resolved["batch_code"], "status": "available", "location_code": location_code}

    def pick(self, payload: dict[str, Any]) -> dict[str, Any]:
        code = _required(payload, "code")
        material_code = _required(payload, "material_code")
        qty = _positive_float(payload.get("qty"), "qty")
        resolved = self._resolve_code(code)
        if resolved["status"] in {"rejected", "frozen", "pending_iqc"}:
            raise ValueError(f"inventory status {resolved['status']} cannot be picked")
        if resolved["material_code"] != material_code:
            raise ValueError("material_code does not match code")
        now = int(time.time())
        pick_no = f"PICK-{now}-{self._count('pick_record') + 1:04d}"
        operator = str(payload.get("operator") or "").strip()
        with self._connect() as conn:
            conn.execute(
                """
                insert into pick_record(pick_no, work_order_no, product_sn, material_code, code, batch_code, package_code, qty, operator, payload_json, created_at)
                values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pick_no, payload.get("work_order_no"), payload.get("product_sn"), material_code, code,
                    resolved["batch_code"], resolved.get("package_code"), qty, operator, _json(payload), now,
                ),
            )
            self._insert_stock_move(conn, "pick", code, resolved, qty, "picked", resolved.get("location_code"), operator, payload, now)
            self._insert_event(conn, "pick", code, resolved["batch_code"], resolved.get("package_code"), payload.get("product_sn"), payload, now)
        return {"pick_no": pick_no, "batch_code": resolved["batch_code"], "package_code": resolved.get("package_code")}

    def assembly_bind(self, payload: dict[str, Any]) -> dict[str, Any]:
        product_sn = _required(payload, "product_sn")
        material_code = _required(payload, "material_code")
        batch_code = str(payload.get("batch_code") or "").strip()
        package_code = str(payload.get("package_code") or "").strip()
        serial_no = str(payload.get("serial_no") or "").strip()
        code = package_code or batch_code or serial_no
        if not code:
            raise ValueError("batch_code, package_code, or serial_no is required")
        bind_qty = _positive_float(payload.get("bind_qty"), "bind_qty")
        now = int(time.time())
        bind_no = f"BIND-{now}-{self._count('assembly_bind') + 1:04d}"
        resolved = self._resolve_code(code) if not serial_no or package_code or batch_code else {"batch_code": batch_code, "package_code": package_code}
        with self._connect() as conn:
            conn.execute(
                """
                insert into assembly_bind(
                    bind_no, product_sn, material_code, batch_code, package_code, serial_no,
                    bind_qty, position_code, operator, payload_json, created_at
                ) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bind_no, product_sn, material_code, resolved.get("batch_code") or batch_code,
                    resolved.get("package_code") or package_code, serial_no, bind_qty, payload.get("position_code"),
                    payload.get("operator"), _json(payload), now,
                ),
            )
            self._insert_event(conn, "assembly_bind", code, resolved.get("batch_code") or batch_code, resolved.get("package_code") or package_code, product_sn, payload, now)
        return {"bind_no": bind_no, "product_sn": product_sn, "batch_code": resolved.get("batch_code") or batch_code, "package_code": resolved.get("package_code") or package_code}

    def trace(self, code: str) -> dict[str, Any]:
        resolved = self._resolve_trace_code(code)
        batch_code = resolved.get("batch_code")
        product_sn = resolved.get("product_sn") or code
        iqc_records = self._many("select * from iqc_record where batch_code=? order by id", (batch_code,)) if batch_code else []
        iqc_attachments = self._list_iqc_attachment_meta(batch_code) if batch_code else []
        attachments_by_ref: dict[str, list[dict[str, Any]]] = {}
        for attachment in iqc_attachments:
            attachments_by_ref.setdefault(str(attachment.get("ref_no") or ""), []).append(attachment)
        for record in iqc_records:
            record["attachments"] = attachments_by_ref.get(str(record.get("iqc_no") or ""), [])
        return {
            "query": {"code": code, "resolved_type": resolved["type"]},
            "batch": _row(self._one("select * from material_batch where batch_code=?", (batch_code,))) if batch_code else None,
            "packages": self._many("select * from material_package where batch_code=? order by package_index", (batch_code,)) if batch_code else [],
            "iqc_records": iqc_records,
            "iqc_attachments": iqc_attachments,
            "inventory": self._many("select * from inventory_stock where batch_code=? order by id", (batch_code,)) if batch_code else [],
            "stock_moves": self._many("select * from stock_move where batch_code=? order by id", (batch_code,)) if batch_code else [],
            "pick_records": self._many("select * from pick_record where batch_code=? or product_sn=? order by id", (batch_code, product_sn)),
            "assembly_binds": self._many("select * from assembly_bind where batch_code=? or package_code=? or product_sn=? order by id", (batch_code, code, product_sn)),
            "events": self._many("select * from trace_event_log where batch_code=? or package_code=? or product_sn=? or ref_code=? order by id", (batch_code, code, product_sn, code)),
        }

    def list_print_tasks(self, status: str = "", limit: int = 100) -> list[dict[str, Any]]:
        limit = min(max(int(limit), 1), 500)
        fields = """
            id, task_no, code_type, code, batch_code, package_code,
            qr_payload_json as qr_payload, status, printer_type,
            payload_json, created_at, updated_at
        """
        if status:
            return self._many(
                f"select {fields} from label_print_task where status=? order by id limit ?",
                (status, limit),
            )
        return self._many(f"select {fields} from label_print_task order by id limit ?", (limit,))

    def _next_daily_sequence(self, material_code: str, supplier_code: str, receive_date: str) -> int:
        prefix = generate_batch_code(material_code, supplier_code, receive_date, 0)[:-4]
        sequence_date = prefix.rstrip("|").split("|")[-1]
        sequence_key = f"{material_code}|{supplier_code}|{sequence_date}"
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                "select current_value from code_sequences where sequence_key=?",
                (sequence_key,),
            ).fetchone()
            if row:
                value = int(row["current_value"]) + 1
                conn.execute(
                    "update code_sequences set current_value=?, updated_at=? where sequence_key=?",
                    (value, now, sequence_key),
                )
                return value

            existing = conn.execute(
                "select batch_code from material_batch where batch_code like ?",
                (f"{prefix}%",),
            ).fetchall()
            max_existing = 0
            for item in existing:
                try:
                    max_existing = max(max_existing, int(str(item["batch_code"]).rsplit("|", 1)[-1]))
                except ValueError:
                    continue
            value = max_existing + 1
            conn.execute(
                """
                insert into code_sequences(
                    sequence_key, material_code, supplier_code, sequence_date,
                    current_value, created_at, updated_at
                ) values(?, ?, ?, ?, ?, ?, ?)
                """,
                (sequence_key, material_code, supplier_code, sequence_date, value, now, now),
            )
            return value

    def _resolve_code(self, code: str) -> dict[str, Any]:
        package = self._one("select * from material_package where package_code=?", (code,))
        if package:
            batch = self._require_batch(package["batch_code"])
            stock = self._stock_for_batch(package["batch_code"])
            return {**_row(batch), "package_code": code, "status": stock.get("status", package["status"]), "location_code": stock.get("location_code")}
        batch = self._one("select * from material_batch where batch_code=?", (code,))
        if batch:
            stock = self._stock_for_batch(code)
            return {**_row(batch), "status": stock.get("status", batch["batch_status"]), "location_code": stock.get("location_code")}
        raise KeyError(f"code not found: {code}")

    def _resolve_trace_code(self, code: str) -> dict[str, Any]:
        package = self._one("select * from material_package where package_code=?", (code,))
        if package:
            return {"type": "package", "batch_code": package["batch_code"]}
        batch = self._one("select * from material_batch where batch_code=?", (code,))
        if batch:
            return {"type": "batch", "batch_code": code}
        bind = self._one("select * from assembly_bind where product_sn=? order by id desc", (code,))
        if bind:
            return {"type": "product_sn", "batch_code": bind["batch_code"], "product_sn": code}
        return {"type": "unknown", "batch_code": None, "product_sn": code}

    def _require_batch(self, batch_code: str) -> sqlite3.Row:
        batch = self._one("select * from material_batch where batch_code=?", (batch_code,))
        if not batch:
            raise KeyError(f"batch not found: {batch_code}")
        return batch

    def _stock_for_batch(self, batch_code: str) -> dict[str, Any]:
        stock = self._one("select * from inventory_stock where batch_code=? order by id desc", (batch_code,))
        return _row(stock) if stock else {}

    def _one(self, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(sql, params).fetchone()

    def _many(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [_row(row) for row in conn.execute(sql, params).fetchall()]

    def _count(self, table: str) -> int:
        with self._connect() as conn:
            return int(conn.execute(f"select count(*) from {table}").fetchone()[0])

    def _normalize_iqc_attachments(self, raw_attachments: Any, iqc_no: str, batch_code: str, now: int) -> list[dict[str, Any]]:
        if not raw_attachments:
            return []
        if not isinstance(raw_attachments, list):
            raw_attachments = [raw_attachments]

        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(raw_attachments, start=1):
            if isinstance(item, str):
                filename = item.strip()
                if not filename:
                    continue
                source = {"filename": filename}
            elif isinstance(item, dict):
                source = item
                filename = str(source.get("filename") or source.get("name") or "").strip()
                if not filename:
                    continue
            else:
                continue

            content_base64 = str(source.get("content_base64") or "").strip()
            try:
                size = int(source.get("size")) if source.get("size") not in (None, "") else None
            except (TypeError, ValueError):
                size = None
            payload = {
                key: value
                for key, value in source.items()
                if key not in {"content_base64", "data_url"}
            }
            normalized.append({
                "attachment_id": str(source.get("attachment_id") or f"IQCATT-{now}-{index:02d}-{uuid.uuid4().hex[:8]}"),
                "ref_type": "iqc",
                "ref_no": iqc_no,
                "batch_code": batch_code,
                "filename": filename,
                "content_type": str(source.get("content_type") or source.get("mime_type") or "").strip(),
                "size": size,
                "content_base64": content_base64,
                "payload": payload,
            })
        return normalized

    def _attachment_meta(self, attachment: dict[str, Any]) -> dict[str, Any]:
        return {
            "attachment_id": attachment.get("attachment_id"),
            "ref_type": attachment.get("ref_type"),
            "ref_no": attachment.get("ref_no"),
            "batch_code": attachment.get("batch_code"),
            "filename": attachment.get("filename"),
            "content_type": attachment.get("content_type"),
            "size": attachment.get("size"),
            "payload": attachment.get("payload") or {},
            "created_at": attachment.get("created_at"),
        }

    def _list_iqc_attachment_meta(self, batch_code: str) -> list[dict[str, Any]]:
        return self._many(
            """
            select id, attachment_id, ref_type, ref_no, batch_code, filename,
                   content_type, size, payload_json, created_at
            from iqc_attachment
            where batch_code=?
            order by id
            """,
            (batch_code,),
        )

    def _insert_qrcode(self, conn, code_type: str, code: str, batch_code: str, package_code: str | None, qr_payload: str, now: int) -> None:
        conn.execute(
            """
            insert into material_qrcode(code_type, code, batch_code, package_code, qr_payload_json, print_status, payload_json, created_at, updated_at)
            values(?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (code_type, code, batch_code, package_code, qr_payload, _json({"source": "receive_label"}), now, now),
        )
        conn.execute(
            """
            insert into label_print_task(
                task_no, code_type, code, batch_code, package_code, qr_payload_json,
                status, printer_type, payload_json, created_at, updated_at
            ) values(?, ?, ?, ?, ?, ?, 'pending', 'zebra', ?, ?, ?)
            """,
            (
                f"LPT-{code_type.upper()}-{code}",
                code_type,
                code,
                batch_code,
                package_code,
                qr_payload,
                _json({"source": "receive_label"}),
                now,
                now,
            ),
        )

    def _insert_stock_move(self, conn, move_type: str, code: str, resolved: dict[str, Any], qty: float, to_status: str, location_code: str | None, operator: str, payload: dict[str, Any], now: int) -> None:
        move_no = f"MV-{move_type.upper()}-{now}-{self._count('stock_move') + 1:04d}"
        conn.execute(
            """
            insert into stock_move(move_no, move_type, code, batch_code, package_code, material_code, qty, unit, from_status, to_status, location_code, operator, payload_json, created_at)
            values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                move_no, move_type, code, resolved.get("batch_code"), resolved.get("package_code"),
                resolved.get("material_code"), qty, resolved.get("unit"), resolved.get("status"),
                to_status, location_code, operator, _json(payload), now,
            ),
        )

    def _insert_event(self, conn, event_type: str, ref_code: str, batch_code: str | None, package_code: str | None, product_sn: str | None, payload: dict[str, Any], now: int) -> None:
        conn.execute(
            "insert into trace_event_log(event_type, ref_code, batch_code, package_code, product_sn, payload_json, created_at) values(?, ?, ?, ?, ?, ?, ?)",
            (event_type, ref_code, batch_code, package_code, product_sn, _json(payload), now),
        )


def _required(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _positive_float(value: Any, key: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a positive number")
    if number <= 0:
        raise ValueError(f"{key} must be a positive number")
    return number


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key in list(data):
        if key.endswith("_json"):
            target = key[:-5]
            try:
                data[target] = json.loads(data.pop(key) or "{}")
            except json.JSONDecodeError:
                data[target] = data.pop(key)
    return data
