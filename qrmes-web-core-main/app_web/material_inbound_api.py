#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import sqlite3
import zipfile
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

from flask import Blueprint, current_app, jsonify, request, send_file

try:
    from qrmes_shared_core.auth import login_required
except Exception:  # pragma: no cover - fallback for isolated imports
    def login_required(func):
        return func

material_inbound_bp = Blueprint("material_inbound", __name__, url_prefix="/api/material-inbound")

MATERIAL_CONFIG_DB_NAME = "material_config.db"
DELIVERY_NOTE_DIR_NAME = "delivery_notes"
MATERIAL_PHOTO_DIR_NAME = "material_photos"
REPORT_LIBRARY_DIR_NAME = "materials_checking"
INBOUND_DB_DIR_NAME = "material_inbound"
INBOUND_RECORD_DB_NAME = "material_inbound.db"
INBOUND_QUANTITY_DB_NAME = "material_inbound_quantity.db"
REPORT_LIBRARY_DB_NAME = "material_reports.db"
ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "bmp", "gif", "webp"}
ALLOWED_REPORT_EXTENSIONS = {"xls", "xlsx", "xlsm"}
MAX_PHOTO_SIZE = 15 * 1024 * 1024
MAX_REPORT_SIZE = 50 * 1024 * 1024
MATERIAL_CODE_PATTERN = re.compile(r"\b([A-Z]\d{7,})\b", re.IGNORECASE)


def _data_root() -> Path:
    configured = current_app.config.get("MATERIAL_INBOUND_DATA_DIR") or current_app.config.get("DATA_DIR")
    root = Path(str(configured)) if configured else Path("/home/aiyan/QRMES")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _folders() -> Dict[str, Path]:
    root = _data_root()
    folders = {
        "material_config": root / "material_config",
        "delivery_note": root / DELIVERY_NOTE_DIR_NAME,
        "material_photo": root / MATERIAL_PHOTO_DIR_NAME,
        "inbound_db": root / INBOUND_DB_DIR_NAME,
        "report_library": root / REPORT_LIBRARY_DIR_NAME,
    }
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)
    return folders


def _safe_name(value: str, fallback: str = "material") -> str:
    safe = re.sub(r'[\\/:*?"<>|]+', "_", str(value or "").strip())
    return safe.strip(" .") or fallback


def _extension(filename: str) -> str:
    return Path(filename or "").suffix.lower().lstrip(".") or "jpg"


def _match_key(value: Any) -> str:
    return re.sub(r"[-_\s.]+", "", str(value or "")).upper()


def _material_code_from_serial(serial: str) -> str:
    text = str(serial or "").strip().upper()
    match = re.match(r"^([A-Z]\d{7,})", text)
    if match:
        return match.group(1)
    for separator in (".", "_", "-", " "):
        if separator in text:
            prefix = text.split(separator, 1)[0].strip()
            if prefix:
                return prefix
    return text


def _material_candidates(serial: str) -> Tuple[str, List[Dict[str, Any]]]:
    material_code = _material_code_from_serial(serial)
    target_key = _match_key(material_code)
    path = _folders()["material_config"] / MATERIAL_CONFIG_DB_NAME
    if not path.exists():
        raise FileNotFoundError(f"material config database not found: {path}")
    candidates: List[Dict[str, Any]] = []
    seen = set()
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT material_code, material_name
            FROM material_config
            WHERE COALESCE(material_code, '') <> ''
            ORDER BY rowid ASC
            """
        ).fetchall()
    for row in rows:
        code = str(row["material_code"] or "").strip()
        name = str(row["material_name"] or "").strip()
        if not code or _match_key(code) != target_key:
            continue
        key = (code, name)
        if key in seen:
            continue
        seen.add(key)
        candidates.append({
            "materialSerial": serial,
            "materialCode": code,
            "materialName": name,
            "projectName": "",
            "projectCode": "",
            "productType": "",
            "matchedRule": MATERIAL_CONFIG_DB_NAME,
            "processSteps": [],
        })
    return material_code, candidates


def _resolve_payload(serial: str) -> Dict[str, Any]:
    material_code, candidates = _material_candidates(serial)
    first = candidates[0] if candidates else {}
    return {
        "success": True,
        "materialSerial": serial,
        "materialCode": first.get("materialCode") or material_code,
        "materialName": first.get("materialName"),
        "projectName": first.get("projectName") or "",
        "projectCode": first.get("projectCode") or "",
        "productType": first.get("productType") or "",
        "matched": bool(candidates),
        "matchSource": first.get("matchedRule") or MATERIAL_CONFIG_DB_NAME,
        "photoFolder": MATERIAL_PHOTO_DIR_NAME,
        "resultCount": len(candidates),
        "results": candidates,
    }


def _inbound_db_path() -> Path:
    path = _folders()["inbound_db"] / INBOUND_RECORD_DB_NAME
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS material_inbound_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                initial_serial TEXT NOT NULL,
                confirmed_serial TEXT NOT NULL,
                material_code TEXT NOT NULL,
                material_name TEXT NOT NULL,
                project_name TEXT DEFAULT '',
                project_code TEXT DEFAULT '',
                product_type TEXT DEFAULT '',
                process_steps_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
    return path


def _quantity_db_path() -> Path:
    path = _folders()["inbound_db"] / INBOUND_QUANTITY_DB_NAME
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS material_inbound_quantity_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_code TEXT NOT NULL,
                material_name TEXT NOT NULL,
                quantity TEXT NOT NULL,
                record_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_material_inbound_quantity_records_code
            ON material_inbound_quantity_records(material_code, created_at DESC)
        """)
        conn.commit()
    return path


def _report_library_db_path() -> Path:
    path = _folders()["report_library"] / REPORT_LIBRARY_DB_NAME
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS material_report_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_code TEXT NOT NULL,
                normalized_material_code TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                file_extension TEXT NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                file_path TEXT NOT NULL,
                uploaded_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_material_report_records_code
            ON material_report_records(normalized_material_code, uploaded_at DESC)
        """)
        conn.commit()
    return path


def _extract_material_code_from_excel(original_filename: str, payload: bytes) -> str:
    texts: List[str] = [original_filename or ""]
    if payload.startswith(b"PK"):
        try:
            with zipfile.ZipFile(BytesIO(payload)) as archive:
                for name in archive.namelist():
                    lower = name.lower()
                    if lower.startswith("xl/") and (
                        lower.endswith(".xml") or "sharedstrings" in lower
                    ):
                        data = archive.read(name)
                        texts.append(data.decode("utf-8", "ignore"))
        except zipfile.BadZipFile:
            pass
    else:
        texts.append(payload.decode("latin1", "ignore"))
    for text in texts:
        match = MATERIAL_CODE_PATTERN.search(text)
        if match:
            return match.group(1).upper()
    return ""


def _report_record_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": int(row["id"]),
        "materialCode": row["material_code"],
        "originalFilename": row["original_filename"],
        "storedFilename": row["stored_filename"],
        "extension": row["file_extension"],
        "fileSize": int(row["file_size"] or 0),
        "uploadedAt": row["uploaded_at"],
        "folder": REPORT_LIBRARY_DIR_NAME,
        "downloadUrl": f"/api/material-inbound/report-library/{int(row['id'])}/download",
        "deleteUrl": f"/api/material-inbound/report-library/{int(row['id'])}",
        "exists": Path(row["file_path"]).exists(),
    }


def _get_report_record(record_id: int) -> sqlite3.Row | None:
    db_path = _report_library_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT id, material_code, original_filename, stored_filename,
                   file_extension, file_size, file_path, uploaded_at
            FROM material_report_records
            WHERE id = ?
            """,
            (record_id,),
        ).fetchone()


def _save_upload(file_storage: Any, target_path: Path) -> int:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    stream = file_storage.stream
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    if size <= 0:
        raise ValueError("empty upload")
    if size > MAX_PHOTO_SIZE:
        raise ValueError("file too large")
    file_storage.save(target_path)
    return size


def _unique_path(folder: Path, filename: str) -> Path:
    path = folder / filename
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(1, 100):
        candidate = folder / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    return folder / f"{stem}_{datetime.now().strftime('%f')}{suffix}"


def _timestamped_filename(material_code: str, ext: str) -> str:
    return f"{_safe_name(material_code)}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"


@material_inbound_bp.route("/resolve", methods=["GET"])
def resolve_material_inbound():
    serial = (request.args.get("serial") or "").strip()
    if not serial:
        return jsonify({"success": False, "matched": False, "error": "serial is required"}), 400
    try:
        payload = _resolve_payload(serial)
    except FileNotFoundError as exc:
        return jsonify({"success": False, "matched": False, "error": str(exc)}), 500
    if not payload["matched"]:
        return jsonify({**payload, "success": False, "error": "material not matched"}), 404
    return jsonify(payload)


@material_inbound_bp.route("/report-library", methods=["GET"])
@login_required
def list_material_report_library():
    material_code = (request.args.get("materialCode") or "").strip()
    recent_days_raw = (request.args.get("recentDays") or "").strip()
    limit_raw = (request.args.get("limit") or "100").strip()
    try:
        limit = max(1, min(int(limit_raw), 500))
    except ValueError:
        limit = 100
    clauses: List[str] = []
    params: List[Any] = []
    if material_code:
        clauses.append("normalized_material_code = ?")
        params.append(_match_key(material_code))
    if recent_days_raw:
        try:
            recent_days = int(recent_days_raw)
        except ValueError:
            recent_days = 0
        if recent_days > 0:
            clauses.append("uploaded_at >= ?")
            params.append((datetime.now() - timedelta(days=recent_days)).isoformat(timespec="seconds"))
    sql = """
        SELECT id, material_code, original_filename, stored_filename,
               file_extension, file_size, file_path, uploaded_at
        FROM material_report_records
    """
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY uploaded_at DESC, id DESC LIMIT ?"
    params.append(limit)
    db_path = _report_library_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return jsonify({"success": True, "records": [_report_record_to_dict(row) for row in rows]})


@material_inbound_bp.route("/report-library/upload", methods=["POST"])
@login_required
def upload_material_report_library():
    file_storage = request.files.get("file") or request.files.get("report")
    if not file_storage or not file_storage.filename:
        return jsonify({"success": False, "error": "file is required"}), 400
    original_filename = Path(str(file_storage.filename).replace("\\", "/")).name
    ext = _extension(original_filename)
    if ext not in ALLOWED_REPORT_EXTENSIONS:
        return jsonify({"success": False, "error": "only Excel files are supported"}), 400
    payload = file_storage.read()
    if not payload:
        return jsonify({"success": False, "error": "empty upload"}), 400
    if len(payload) > MAX_REPORT_SIZE:
        return jsonify({"success": False, "error": "file too large"}), 400
    material_code = _extract_material_code_from_excel(original_filename, payload)
    if not material_code:
        return jsonify({"success": False, "error": "material code not found in Excel"}), 400
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    stored_filename = f"{_safe_name(material_code)}_{stamp}.{ext}"
    target_path = _unique_path(_folders()["report_library"], stored_filename)
    target_path.write_bytes(payload)
    uploaded_at = datetime.now().isoformat(timespec="seconds")
    db_path = _report_library_db_path()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO material_report_records (
                material_code, normalized_material_code, original_filename,
                stored_filename, file_extension, file_size, file_path, uploaded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                material_code,
                _match_key(material_code),
                original_filename,
                target_path.name,
                ext,
                len(payload),
                str(target_path),
                uploaded_at,
            ),
        )
        conn.commit()
        record_id = cursor.lastrowid
    row = _get_report_record(int(record_id))
    return jsonify({
        "success": True,
        "message": "uploaded",
        "materialCode": material_code,
        "record": _report_record_to_dict(row) if row else None,
    })


@material_inbound_bp.route("/report-library/<int:record_id>/download", methods=["GET"])
@login_required
def download_material_report_library(record_id: int):
    row = _get_report_record(record_id)
    if not row:
        return jsonify({"success": False, "error": "record not found"}), 404
    file_path = Path(row["file_path"])
    if not file_path.exists():
        return jsonify({"success": False, "error": "file not found"}), 404
    return send_file(file_path, as_attachment=True, download_name=row["stored_filename"])


@material_inbound_bp.route("/report-library/<int:record_id>", methods=["DELETE"])
@login_required
def delete_material_report_library(record_id: int):
    row = _get_report_record(record_id)
    if not row:
        return jsonify({"success": False, "error": "record not found"}), 404
    file_path = Path(row["file_path"])
    if file_path.exists():
        file_path.unlink()
    db_path = _report_library_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM material_report_records WHERE id = ?", (record_id,))
        conn.commit()
    return jsonify({"success": True, "message": "deleted"})


@material_inbound_bp.route("/confirm", methods=["POST"])
def confirm_material_inbound():
    payload = request.get_json(silent=True) or {}
    initial_serial = str(payload.get("initialSerial") or payload.get("materialSerial") or "").strip()
    confirmed_serial = str(payload.get("confirmSerial") or payload.get("confirmedSerial") or initial_serial).strip()
    material_code = str(payload.get("materialCode") or _material_code_from_serial(confirmed_serial)).strip()
    material_name = str(payload.get("materialName") or "").strip()
    if not confirmed_serial or not material_code or not material_name:
        return jsonify({"success": False, "error": "confirmed serial, material code and material name are required"}), 400
    created_at = datetime.now().isoformat(timespec="seconds")
    db_path = _inbound_db_path()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("""
            INSERT INTO material_inbound_records (
                initial_serial, confirmed_serial, material_code, material_name,
                project_name, project_code, product_type, process_steps_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            initial_serial,
            confirmed_serial,
            material_code,
            material_name,
            str(payload.get("projectName") or ""),
            str(payload.get("projectCode") or ""),
            str(payload.get("productType") or ""),
            "[]",
            created_at,
        ))
        conn.commit()
        record_id = cursor.lastrowid
    return jsonify({
        "success": True,
        "message": "saved",
        "recordId": record_id,
        "materialSerial": confirmed_serial,
        "materialCode": material_code,
        "materialName": material_name,
        "databaseFolder": INBOUND_DB_DIR_NAME,
        "databaseName": INBOUND_RECORD_DB_NAME,
        "databasePath": str(db_path),
        "createdAt": created_at,
    })


@material_inbound_bp.route("/photo", methods=["POST"])
def upload_material_inbound_photo():
    file_storage = request.files.get("photo") or request.files.get("file")
    if not file_storage:
        return jsonify({"success": False, "error": "photo is required"}), 400
    material_serial = (request.form.get("materialSerial") or "").strip()
    material_code = (request.form.get("materialCode") or _material_code_from_serial(material_serial)).strip()
    material_name = (request.form.get("materialName") or "").strip()
    photo_type = (request.form.get("photoType") or "material").strip().lower()
    if not material_code or not material_name:
        return jsonify({"success": False, "error": "material code and material name are required"}), 400
    ext = _extension(file_storage.filename)
    if ext.lower() not in ALLOWED_PHOTO_EXTENSIONS:
        return jsonify({"success": False, "error": "unsupported photo extension"}), 400
    folders = _folders()
    folder_key = "delivery_note" if photo_type in {"delivery", "delivery_note", "note"} else "material_photo"
    target_folder = folders[folder_key]
    target_path = _unique_path(target_folder, _timestamped_filename(material_code, ext))
    try:
        file_size = _save_upload(file_storage, target_path)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({
        "success": True,
        "message": "uploaded",
        "filename": target_path.name,
        "filePath": str(target_path),
        "folder": target_folder.name,
        "photoType": photo_type,
        "fileSize": file_size,
    })


@material_inbound_bp.route("/record", methods=["POST"])
def record_material_inbound():
    payload = request.get_json(silent=True) or {}
    material_code = str(payload.get("materialCode") or "").strip()
    material_name = str(payload.get("materialName") or "").strip()
    quantity = str(payload.get("quantity") or "").strip()
    if not material_code or not material_name or not quantity:
        return jsonify({"success": False, "error": "material code, material name and quantity are required"}), 400
    now = datetime.now()
    record_date = now.strftime("%Y-%m-%d")
    created_at = now.isoformat(timespec="seconds")
    db_path = _quantity_db_path()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("""
            INSERT INTO material_inbound_quantity_records (
                material_code, material_name, quantity, record_date, created_at
            ) VALUES (?, ?, ?, ?, ?)
        """, (material_code, material_name, quantity, record_date, created_at))
        conn.commit()
        record_id = cursor.lastrowid
    return jsonify({
        "success": True,
        "message": "saved",
        "recordId": record_id,
        "databaseFolder": INBOUND_DB_DIR_NAME,
        "databaseName": INBOUND_QUANTITY_DB_NAME,
        "databasePath": str(db_path),
        "recordDate": record_date,
        "createdAt": created_at,
    })
