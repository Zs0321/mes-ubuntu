from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from functools import wraps

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file, session
from qrmes_shared_core.config import config
from qrmes_shared_core.data_dir_utils import resolve_data_dir

try:
    from .production_progress_service import ProductionProgressService, parse_timestamp
except ImportError:  # pragma: no cover - mesapp.py imports modules from app_web on sys.path
    from production_progress_service import ProductionProgressService, parse_timestamp


production_progress_bp = Blueprint("production_progress", __name__)


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("user"):
            return func(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "message": "login required"}), 401
        return redirect("/login")

    return wrapper


def _data_dir() -> Path:
    configured = current_app.config.get("DATA_DIR")
    if configured:
        return Path(configured)
    return resolve_data_dir(
        nas_local_base_path=getattr(config, "nas_local_base_path", None),
        repo_root=Path(__file__).resolve().parent.parent,
    )


def _service() -> ProductionProgressService:
    injected = current_app.config.get("PRODUCTION_PROGRESS_SERVICE")
    if injected is not None:
        return injected
    db_path = current_app.config.get("PRODUCTION_PROGRESS_DB_PATH")
    photo_db_path = current_app.config.get("PRODUCTION_PROGRESS_PHOTO_DB_PATH")
    return ProductionProgressService(
        data_dir=_data_dir(),
        db_path=Path(db_path) if db_path else None,
        photo_db_path=Path(photo_db_path) if photo_db_path else None,
    )


def _current_username() -> str:
    user = session.get("user") or {}
    return str(user.get("username") or user.get("synology_username") or "").strip()


def _json_payload() -> Dict[str, Any]:
    return request.get_json(silent=True) or {}


def _event_payload(event_type: str):
    data = _json_payload()
    serial = str(data.get("serial") or data.get("product_serial") or data.get("productSerial") or "").strip()
    process_step = str(data.get("process_step") or data.get("processStep") or "").strip()
    if not serial:
        return jsonify({"success": False, "message": "serial is required"}), 400
    if not process_step:
        return jsonify({"success": False, "message": "process_step is required"}), 400
    try:
        event = _service().record_event(
            product_serial=serial,
            process_step=process_step,
            event_type=event_type,
            project_name=str(data.get("project_name") or data.get("projectName") or "").strip(),
            product_type=str(data.get("product_type") or data.get("productType") or "").strip(),
            process_order=int(data.get("process_order") or data.get("processOrder") or 0),
            operator=str(data.get("operator") or _current_username()).strip(),
            occurred_at=parse_timestamp(data.get("occurred_at") or data.get("occurredAt")),
            source=str(data.get("source") or "web").strip() or "web",
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "event": event})


@production_progress_bp.get("/production-progress")
@login_required
def production_progress_page():
    return render_template("production_progress.html")


@production_progress_bp.get("/production-progress/<path:serial>")
@login_required
def production_progress_detail_page(serial: str):
    return render_template("production_progress_detail.html", serial=serial)


@production_progress_bp.get("/api/production-progress/board")
@login_required
def production_progress_board():
    service = _service()
    payload = service.get_board(
        serial=str(request.args.get("serial") or "").strip(),
        project=str(request.args.get("project") or request.args.get("project_name") or "").strip(),
        product_type=str(request.args.get("product_type") or request.args.get("productType") or "").strip(),
        status=str(request.args.get("status") or "").strip(),
        limit=int(request.args.get("limit") or 100),
    )
    return jsonify(payload)


@production_progress_bp.get("/api/production-progress/options")
@login_required
def production_progress_options():
    return jsonify(_service().list_options())


@production_progress_bp.post("/api/production-progress/scan")
@login_required
def production_progress_scan():
    return _event_payload("scan")


@production_progress_bp.post("/api/production-progress/complete")
@login_required
def production_progress_complete():
    return _event_payload("complete")


@production_progress_bp.post("/api/production-progress/upload")
@login_required
def production_progress_upload():
    serial = str(request.form.get("serial") or request.form.get("product_serial") or request.form.get("productSerial") or "").strip()
    process_step = str(request.form.get("process_step") or request.form.get("processStep") or "").strip()
    file_storage = request.files.get("file")
    if not serial:
        return jsonify({"success": False, "message": "serial is required"}), 400
    if not process_step:
        return jsonify({"success": False, "message": "process_step is required"}), 400
    if not file_storage or not file_storage.filename:
        return jsonify({"success": False, "message": "file is required"}), 400
    try:
        attachment = _service().save_file_storage(
            product_serial=serial,
            process_step=process_step,
            storage=file_storage,
            uploaded_by=str(request.form.get("uploaded_by") or request.form.get("uploadedBy") or _current_username()).strip(),
            metadata={
                "projectName": str(request.form.get("project_name") or request.form.get("projectName") or "").strip(),
                "productType": str(request.form.get("product_type") or request.form.get("productType") or "").strip(),
                "source": "production_progress_upload",
            },
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "attachment": attachment})


@production_progress_bp.get("/api/production-progress/attachment/<int:attachment_id>")
@login_required
def production_progress_attachment(attachment_id: int):
    try:
        path = _service().resolve_document_path(attachment_id)
    except FileNotFoundError:
        return jsonify({"success": False, "message": "attachment not found"}), 404
    except PermissionError:
        return jsonify({"success": False, "message": "attachment path is invalid"}), 403
    return send_file(str(path), as_attachment=False, download_name=path.name)


@production_progress_bp.get("/api/production-progress/<path:serial>")
@login_required
def production_progress_detail(serial: str):
    try:
        return jsonify(_service().get_detail(serial))
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
