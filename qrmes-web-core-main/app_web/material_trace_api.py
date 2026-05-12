from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import requests
from flask import Blueprint, current_app, jsonify, render_template, request

from qrmes_shared_core.auth import login_required
from qrmes_shared_core.config import config
from qrmes_shared_core.data_dir_utils import resolve_data_dir


material_trace_bp = Blueprint("material_trace", __name__)


class MaterialTraceClient:
    def __init__(self, base_url: str | None = None, timeout: int = 30):
        self.base_url = (base_url or os.getenv("KINGDEE_TRACE_API_BASE") or "http://127.0.0.1:9010").rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def request(self, method: str, path: str, **kwargs):
        response = self.session.request(
            method,
            f"{self.base_url}/api/traceability/{path.lstrip('/')}",
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()


def create_material_trace_client() -> MaterialTraceClient:
    timeout = int(os.getenv("KINGDEE_TRACE_API_TIMEOUT_SECS") or "30")
    return MaterialTraceClient(timeout=timeout)


def _data_dir() -> Path:
    configured = current_app.config.get("DATA_DIR")
    if configured:
        return Path(configured)
    return resolve_data_dir(
        nas_local_base_path=getattr(config, "nas_local_base_path", None),
        repo_root=Path(__file__).resolve().parent.parent,
        create=False,
    )


def _web_users_db_path() -> Path:
    configured = current_app.config.get("WEB_USERS_DB_PATH")
    if configured:
        return Path(configured)
    return _data_dir() / "web_users.db"


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    except sqlite3.DatabaseError:
        return set()


def _db_exists_with_table(db_path: Path, table_name: str) -> bool:
    if not db_path.exists():
        return False
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "select 1 from sqlite_master where type='table' and name=?",
                (table_name,),
            ).fetchone()
        return row is not None
    except sqlite3.DatabaseError:
        return False


def _product_model_db_candidates(data_dir: Path) -> list[Path]:
    candidates = [
        data_dir / "product_config.db",
        data_dir / "project_config.db",
        data_dir / "project_configs.db",
        data_dir / "projects" / "product_config.db",
        data_dir / "projects" / "project_config.db",
        data_dir / "projects" / "project_configs.db",
    ]
    seen: set[Path] = set()
    result: list[Path] = []
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def list_inspector_candidates(keyword: str = "", limit: int = 100) -> list[dict]:
    db_path = _web_users_db_path()
    if not db_path.exists():
        return []
    keyword = keyword.strip().lower()
    limit = min(max(int(limit or 100), 1), 500)
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            columns = _table_columns(conn, "users")
            if "users" not in {
                str(row["name"])
                for row in conn.execute("select name from sqlite_master where type='table'").fetchall()
            }:
                return []
            username_col = "synology_username" if "synology_username" in columns else "username"
            display_col = "display_name" if "display_name" in columns else ""
            select_display = f", {display_col} as display_name" if display_col else ", '' as display_name"
            where = ""
            if "is_active" in columns:
                where = "where coalesce(is_active, 1) = 1"
            order_expr = "id" if "id" in columns else "rowid"
            rows = conn.execute(
                f"""
                select {username_col} as username{select_display}
                from users
                {where}
                order by {order_expr}
                limit ?
                """,
                (limit,),
            ).fetchall()
    except sqlite3.DatabaseError:
        return []

    result = []
    for row in rows:
        username = str(row["username"] or "").strip()
        display_name = str(row["display_name"] or "").strip()
        label = display_name or username
        if not label:
            continue
        haystack = f"{username} {display_name}".lower()
        if keyword and keyword not in haystack:
            continue
        result.append({"username": username, "display_name": display_name, "label": label})
    return result


def list_product_model_candidates(keyword: str = "", limit: int = 100) -> list[dict]:
    keyword = keyword.strip().lower()
    limit = min(max(int(limit or 100), 1), 500)
    db_path = next((path for path in _product_model_db_candidates(_data_dir()) if _db_exists_with_table(path, "product_types")), None)
    if db_path is None:
        return []
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            columns = _table_columns(conn, "product_types")
            if not {"type_name", "model_number"} <= columns:
                return []
            has_projects = _db_exists_with_table(db_path, "projects")
            project_join = "left join projects p on p.id = pt.project_id" if has_projects and "project_id" in columns else ""
            project_select = "coalesce(p.project_name, '') as project_name" if project_join else "'' as project_name"
            rows = conn.execute(
                f"""
                select {project_select}, pt.type_name, pt.model_number
                from product_types pt
                {project_join}
                order by coalesce(pt.model_number, ''), pt.type_name
                limit ?
                """,
                (limit,),
            ).fetchall()
    except sqlite3.DatabaseError:
        return []

    result = []
    seen = set()
    for row in rows:
        type_name = str(row["type_name"] or "").strip()
        model_number = str(row["model_number"] or "").strip()
        project_name = str(row["project_name"] or "").strip()
        label = model_number or type_name
        if not label:
            continue
        haystack = f"{project_name} {type_name} {model_number}".lower()
        if keyword and keyword not in haystack:
            continue
        key = (project_name, type_name, model_number)
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "project_name": project_name,
            "type_name": type_name,
            "model_number": model_number,
            "label": label,
        })
    return result


@material_trace_bp.get("/material-trace")
@login_required
def material_trace_page():
    return render_template(
        "material_trace.html",
        trace_api_prefix="/api/material-trace",
        zebra_material_url="/zebra-print/material",
        zebra_qr_endpoint="/api/zebra/qr",
    )


@material_trace_bp.get("/api/material-trace-support/inspectors")
def material_trace_inspectors():
    rows = list_inspector_candidates(
        keyword=str(request.args.get("keyword") or ""),
        limit=int(request.args.get("limit", "100") or "100"),
    )
    return jsonify({"rows": rows})


@material_trace_bp.get("/api/material-trace-support/product-models")
def material_trace_product_models():
    rows = list_product_model_candidates(
        keyword=str(request.args.get("keyword") or ""),
        limit=int(request.args.get("limit", "100") or "100"),
    )
    return jsonify({"rows": rows})


@material_trace_bp.route("/api/material-trace/<path:path>", methods=["GET", "POST"])
def material_trace_proxy(path: str):
    client = create_material_trace_client()
    try:
        if request.method == "GET":
            data = client.request("GET", path, params=request.args)
        else:
            data = client.request("POST", path, json=request.get_json(silent=True) or {})
        return jsonify(data)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        try:
            payload = exc.response.json()
        except Exception:
            payload = {"error": "TRACE_API_HTTP_ERROR", "message": str(exc)}
        return jsonify(payload), status
    except requests.RequestException as exc:
        return jsonify({
            "error": "TRACE_API_UNAVAILABLE",
            "message": str(exc),
            "target": client.base_url,
        }), 502
