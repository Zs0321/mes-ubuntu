"""PDF 文档管理 API"""
from flask import Blueprint, request, jsonify, send_file, render_template, session
from pathlib import Path
from datetime import datetime
import json
import logging
import os
import re
import sqlite3
from urllib.parse import quote as url_quote
from typing import Any, Dict, List, Optional

from qrmes_shared_core.permission_guard import require_permission_value
from qrmes_shared_core.auth import login_required

logger = logging.getLogger(__name__)

document_bp = Blueprint('document', __name__, url_prefix='/api/documents')

documents_page_bp = Blueprint('documents_page', __name__)


def _validate_path_segment(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Invalid {field_name}")
    v = value.strip()
    if not v:
        raise ValueError(f"Missing {field_name}")
    if "/" in v or "\\" in v or ".." in v or "\x00" in v:
        raise ValueError(f"Invalid {field_name}")
    return v


def _safe_join(base_dir: Path, rel_path: str) -> Path:
    base = base_dir.resolve()
    candidate = (base_dir / rel_path).resolve()
    base_prefix = str(base) + os.sep
    if str(candidate) == str(base) or str(candidate).startswith(base_prefix):
        return candidate
    raise PermissionError("Path traversal blocked")


def _extract_process_name_from_filename(filename: str) -> str:
    """从文件名中提取工序名。

    兼容两种格式：
    - 新格式：{process}__{serial}__{YYYYMMDD}_{HHMMSS}.pdf
    - 旧格式：{process}_{YYYYMMDD}_{HHMMSS}.pdf
    """
    stem = Path(filename).stem
    match = re.match(r"^(.+)__.+__\d{8}_\d{6}$", stem)
    if match:
        return match.group(1)
    match = re.match(r"^(.+)_\d{8}_\d{6}$", stem)
    if match:
        return match.group(1)
    return stem


def _build_document_filename(process_name: str, product_serial: str, timestamp: str) -> str:
    """构造包含序列号的文档文件名，便于按文件名检索。"""
    return f"{process_name}__{product_serial}__{timestamp}.pdf"


@documents_page_bp.route('/documents')
@require_permission_value('web:view_documents')
def documents_page():
    """文档管理页面"""
    return render_template('documents.html')

def get_documents_dir():
    """获取文档存储目录"""
    from flask import current_app
    configured = current_app.config.get('DOCUMENTS_DIR')
    if configured:
        base_dir = Path(configured)
    else:
        from qrmes_shared_core.config import config
        from qrmes_shared_core.data_dir_utils import resolve_data_dir

        data_root = resolve_data_dir(
            nas_local_base_path=config.nas_local_base_path,
            repo_root=Path(__file__).resolve().parent.parent,
        )
        base_dir = data_root / "documents"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def get_projects_dir() -> Path:
    """获取项目配置目录（默认与 documents 同级的 projects）。"""
    from flask import current_app
    configured = current_app.config.get('PROJECTS_DIR')
    if configured:
        return Path(configured)
    return get_documents_dir().parent / "projects"


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _normalize_attachment_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"photo", "pdf", "both"} else "photo"


def _process_visible_for_documents(step: Dict[str, Any]) -> bool:
    """文档页只显示支持 PDF 上传的工序。"""
    return _normalize_attachment_type(step.get("attachmentType")) in {"pdf", "both"}


def _load_serials_from_records_db(
    data_root: Path,
    project_name: Optional[str],
    product_type: Optional[str],
    max_items: int,
) -> List[str]:
    """从系统记录库读取序列号，并按项目/产品类型过滤。"""
    if max_items <= 0:
        return []

    db_path = data_root / "record" / "product_records.db"
    if not db_path.exists():
        return []

    conn = None
    serials: List[str] = []
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        table_columns = set()
        try:
            cursor.execute("PRAGMA table_info(product_records)")
            for row in cursor.fetchall():
                if len(row) >= 2 and row[1]:
                    table_columns.add(str(row[1]))
        except Exception:
            table_columns = set()

        if "product_serial" not in table_columns:
            return []

        where_clauses = ["product_serial IS NOT NULL", "TRIM(product_serial) != ''"]
        params: List[Any] = []

        if project_name and "project_name" in table_columns:
            where_clauses.append("project_name = ?")
            params.append(project_name)

        if product_type and "product_type" in table_columns:
            where_clauses.append("product_type = ?")
            params.append(product_type)

        sql = (
            "SELECT DISTINCT product_serial "
            "FROM product_records "
            f"WHERE {' AND '.join(where_clauses)} "
            "LIMIT ?"
        )
        params.append(int(max_items))
        cursor.execute(sql, tuple(params))

        for row in cursor.fetchall():
            value = (row[0] or "").strip()
            if value:
                _append_unique(serials, value)
    except Exception as e:
        logger.warning(f"读取记录库序列号失败，已跳过: {e}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    return serials


def _load_serials_from_picture_dirs(
    data_root: Path,
    project_name: Optional[str],
    product_type: Optional[str],
    max_items: int,
) -> List[str]:
    """从 picture 目录读取序列号目录名，并按项目/产品类型过滤。"""
    if max_items <= 0:
        return []

    picture_dir = data_root / "picture"
    if not picture_dir.exists():
        return []

    serials: List[str] = []
    try:
        for project_dir in sorted(picture_dir.iterdir()):
            if not project_dir.is_dir():
                continue
            if project_name and project_dir.name != project_name:
                continue
            for product_dir in sorted(project_dir.iterdir()):
                if not product_dir.is_dir():
                    continue
                if product_type and product_dir.name != product_type:
                    continue
                for serial_dir in sorted(product_dir.iterdir()):
                    if not serial_dir.is_dir():
                        continue
                    _append_unique(serials, serial_dir.name)
                    if len(serials) >= max_items:
                        return serials
    except Exception as e:
        logger.warning(f"读取 picture 序列号失败，已跳过: {e}")

    return serials


def _build_document_options(
    selected_project: Optional[str] = None,
    selected_product_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    构建文档页面联动选项：
    - projects -> productTypes -> processSteps（仅 attachmentType=pdf/both）
    - serialNumbers（仅在已选 project+productType 时返回该范围内的序列号）
    """
    docs_dir = get_documents_dir()
    projects_dir = get_projects_dir()

    project_order: List[str] = []
    projects_file = docs_dir.parent / "projects.json"
    if projects_file.exists():
        try:
            with open(projects_file, "r", encoding="utf-8-sig") as f:
                project_data = json.load(f)
                if isinstance(project_data, list):
                    for name in project_data:
                        if isinstance(name, str) and name.strip():
                            _append_unique(project_order, name.strip())
        except Exception as e:
            logger.warning(f"读取 projects.json 失败，继续使用配置文件: {e}")

    project_map: Dict[str, Dict[str, Any]] = {}

    def ensure_project(project_name: str) -> Dict[str, Any]:
        name = (project_name or "").strip()
        if not name:
            return {"name": "", "_product_map": {}}
        if name not in project_map:
            project_map[name] = {"name": name, "_product_map": {}}
        return project_map[name]

    def ensure_product(project: Dict[str, Any], type_name: str) -> Dict[str, Any]:
        pname = (type_name or "").strip()
        if not pname:
            return {"name": "", "processSteps": []}
        product_map = project["_product_map"]
        if pname not in product_map:
            product_map[pname] = {"name": pname, "processSteps": []}
        return product_map[pname]

    if projects_dir.exists():
        for config_file in sorted(projects_dir.glob("*.json")):
            try:
                with open(config_file, "r", encoding="utf-8-sig") as f:
                    config = json.load(f)
                project_name = (config.get("projectName") or config_file.stem).strip()
                if not project_name:
                    continue
                project = ensure_project(project_name)
                _append_unique(project_order, project_name)

                for product_type in config.get("productTypes", []) or []:
                    type_name = (product_type.get("typeName") or "").strip()
                    if not type_name:
                        continue
                    product = ensure_product(project, type_name)
                    for step in product_type.get("processSteps", []) or []:
                        if not _process_visible_for_documents(step):
                            continue
                        process_name = (step.get("name") or "").strip()
                        if process_name:
                            _append_unique(product["processSteps"], process_name)
            except Exception as e:
                logger.warning(f"读取项目配置失败，已跳过 {config_file}: {e}")

    serial_numbers: List[str] = []
    max_serials = 5000
    max_process_scan = 5000
    process_scan_count = 0

    if docs_dir.exists():
        for project_dir in sorted(docs_dir.iterdir()):
            if not project_dir.is_dir():
                continue
            if selected_project and project_dir.name != selected_project:
                continue
            project = ensure_project(project_dir.name)
            _append_unique(project_order, project_dir.name)

            for product_dir in sorted(project_dir.iterdir()):
                if not product_dir.is_dir():
                    continue
                if selected_product_type and product_dir.name != selected_product_type:
                    continue
                product = ensure_product(project, product_dir.name)

                for serial_dir in sorted(product_dir.iterdir()):
                    if not serial_dir.is_dir():
                        continue
                    if selected_project and selected_product_type and len(serial_numbers) < max_serials:
                        _append_unique(serial_numbers, serial_dir.name)

                    for pdf_file in serial_dir.glob("*.pdf"):
                        if process_scan_count >= max_process_scan:
                            break
                        process_name = _extract_process_name_from_filename(pdf_file.name)
                        if process_name:
                            _append_unique(product["processSteps"], process_name)
                        process_scan_count += 1

                    if process_scan_count >= max_process_scan:
                        break

                if process_scan_count >= max_process_scan:
                    break

            if process_scan_count >= max_process_scan:
                break

    if selected_project and selected_product_type:
        remaining = max_serials - len(serial_numbers)
        if remaining > 0:
            for serial in _load_serials_from_records_db(
                docs_dir.parent,
                selected_project,
                selected_product_type,
                remaining,
            ):
                _append_unique(serial_numbers, serial)
                if len(serial_numbers) >= max_serials:
                    break

        remaining = max_serials - len(serial_numbers)
        if remaining > 0:
            for serial in _load_serials_from_picture_dirs(
                docs_dir.parent,
                selected_project,
                selected_product_type,
                remaining,
            ):
                _append_unique(serial_numbers, serial)
                if len(serial_numbers) >= max_serials:
                    break

    if process_scan_count >= max_process_scan:
        logger.info(f"文档选项构建已达到工序扫描上限: {max_process_scan}")

    seen_projects = set()
    projects: List[Dict[str, Any]] = []
    for project_name in project_order:
        if project_name in seen_projects:
            continue
        project = project_map.get(project_name)
        if not project:
            continue
        seen_projects.add(project_name)
        product_types = list(project["_product_map"].values())
        projects.append({
            "name": project_name,
            "productTypes": product_types,
        })

    for project_name, project in project_map.items():
        if project_name in seen_projects:
            continue
        product_types = list(project["_product_map"].values())
        projects.append({
            "name": project_name,
            "productTypes": product_types,
        })

    return {
        "projects": projects,
        "serialNumbers": serial_numbers,
    }

@document_bp.route('/upload', methods=['POST'])
@login_required
def upload_document():
    """上传 PDF 文档"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # 验证文件类型
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Only PDF files allowed'}), 400

    # 获取参数
    try:
        project_name = _validate_path_segment(request.form.get('projectName', ''), 'projectName')
        product_type = _validate_path_segment(request.form.get('productType', ''), 'productType')
        product_serial = _validate_path_segment(request.form.get('productSerial', ''), 'productSerial')
        process_name = _validate_path_segment(request.form.get('processName', ''), 'processName')
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    # 构建存储路径
    docs_dir = get_documents_dir()
    project_dir = _safe_join(docs_dir, str(Path(project_name) / product_type / product_serial))
    project_dir.mkdir(parents=True, exist_ok=True)

    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = _build_document_filename(process_name, product_serial, timestamp)
    file_path = project_dir / filename

    # 保存文件
    file.save(str(file_path))

    logger.info(f"PDF uploaded: {file_path}")

    # Link to Motor QC: record a completed inspection for PDF uploads.
    # This is best-effort to avoid breaking uploads when QC DB isn't configured.
    try:
        from app_web.motor_qc.models import InspectionRecord, db  # type: ignore

        inspector_id = session.get("username") or ""
        if not inspector_id:
            try:
                u = session.get("user") or {}
                if isinstance(u, dict):
                    inspector_id = u.get("username") or u.get("display_name") or ""
            except Exception:
                inspector_id = ""
        if not inspector_id:
            inspector_id = str(session.get("user_id") or "unknown")

        record = InspectionRecord(
            project_code=project_name,
            process_step=process_name,
            photo_path=str(file_path),
            inspector_id=inspector_id,
            inspection_result="PDF文档已上传",
            defects_found=[],
            status="completed",
            inspected_at=datetime.utcnow(),
        )
        db.session.add(record)
        db.session.commit()
    except Exception as e:
        logger.warning(f"Skip QC link for PDF upload: {e}")

    return jsonify({
        'success': True,
        'filename': filename,
        'path': str(file_path.relative_to(docs_dir))
    }), 201

@document_bp.route('/list', methods=['GET'])
@login_required
def list_documents():
    """查询文档列表"""
    docs_dir = get_documents_dir()

    # 获取筛选参数
    project_name = request.args.get('projectName')
    product_type = request.args.get('productType')
    product_serial = request.args.get('productSerial')
    process_name = request.args.get('processName')

    documents = []

    # 遍历目录查找 PDF
    try:
        rel = Path()
        if project_name:
            rel = rel / _validate_path_segment(project_name, 'projectName')
            if product_type:
                rel = rel / _validate_path_segment(product_type, 'productType')
                if product_serial:
                    rel = rel / _validate_path_segment(product_serial, 'productSerial')
        search_dir = _safe_join(docs_dir, str(rel)) if str(rel) else docs_dir
    except ValueError as e:
        return jsonify({'error': str(e), 'documents': []}), 400
    except PermissionError:
        return jsonify({'error': '非法的文件路径', 'documents': []}), 403

    if search_dir.exists():
        for pdf_file in search_dir.rglob('*.pdf'):
            rel_path = pdf_file.relative_to(docs_dir)
            parts = rel_path.parts
            current_process_name = _extract_process_name_from_filename(pdf_file.name)

            if process_name and current_process_name != process_name:
                continue

            doc_info = {
                'filename': pdf_file.name,
                'path': str(rel_path),
                'size': pdf_file.stat().st_size,
                'modified': datetime.fromtimestamp(pdf_file.stat().st_mtime).isoformat(),
                'processName': current_process_name,
            }

            # 解析路径获取项目信息
            if len(parts) >= 3:
                doc_info['projectName'] = parts[0]
                doc_info['productType'] = parts[1]
                doc_info['productSerial'] = parts[2]

            documents.append(doc_info)

    return jsonify({'documents': documents}), 200


@document_bp.route('/options', methods=['GET'])
@require_permission_value('web:view_documents')
def get_document_options():
    """获取文档管理页面的联动选项。"""
    try:
        project_name = (request.args.get("projectName") or "").strip()
        product_type = (request.args.get("productType") or "").strip()

        if project_name:
            try:
                project_name = _validate_path_segment(project_name, "projectName")
            except ValueError as e:
                return jsonify({
                    "success": False,
                    "error": str(e),
                    "options": {"projects": [], "serialNumbers": []},
                }), 400

        if product_type:
            try:
                product_type = _validate_path_segment(product_type, "productType")
            except ValueError as e:
                return jsonify({
                    "success": False,
                    "error": str(e),
                    "options": {"projects": [], "serialNumbers": []},
                }), 400

        return jsonify({
            "success": True,
            "options": _build_document_options(
                selected_project=project_name or None,
                selected_product_type=product_type or None,
            ),
        }), 200
    except Exception as e:
        logger.error(f"获取文档页面选项失败: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "options": {
                "projects": [],
                "serialNumbers": [],
            }
        }), 500


@document_bp.route('/report-status', methods=['GET'])
@require_permission_value('web:view_documents')
def get_report_status():
    """查询指定项目/产品类型下所有序列号的报告上传状态。"""
    try:
        project_name = _validate_path_segment(request.args.get('projectName', ''), 'projectName')
        product_type = _validate_path_segment(request.args.get('productType', ''), 'productType')
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'statuses': [],
        }), 400

    process_name = (request.args.get('processName') or '').strip()
    if process_name:
        try:
            process_name = _validate_path_segment(process_name, 'processName')
        except ValueError as e:
            return jsonify({
                'success': False,
                'error': str(e),
                'statuses': [],
            }), 400

    options = _build_document_options(
        selected_project=project_name,
        selected_product_type=product_type,
    )
    serial_numbers = options.get('serialNumbers') or []

    docs_dir = get_documents_dir()
    statuses: List[Dict[str, Any]] = []
    uploaded_serials = 0
    missing_serials = 0

    for serial in serial_numbers:
        status = {
            'serialNumber': serial,
            'hasReport': False,
            'reportCount': 0,
            'latestModified': None,
        }
        try:
            serial_dir = _safe_join(docs_dir, str(Path(project_name) / product_type / serial))
        except PermissionError:
            statuses.append(status)
            missing_serials += 1
            continue

        if serial_dir.exists():
            latest_ts = None
            for pdf_file in serial_dir.glob('*.pdf'):
                current_process = _extract_process_name_from_filename(pdf_file.name)
                if process_name and current_process != process_name:
                    continue
                status['reportCount'] += 1
                ts = pdf_file.stat().st_mtime
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts

            if status['reportCount'] > 0:
                status['hasReport'] = True
                status['latestModified'] = datetime.fromtimestamp(latest_ts).isoformat() if latest_ts else None

        if status['hasReport']:
            uploaded_serials += 1
        else:
            missing_serials += 1

        statuses.append(status)

    return jsonify({
        'success': True,
        'projectName': project_name,
        'productType': product_type,
        'processName': process_name or '',
        'totalSerials': len(serial_numbers),
        'uploadedSerials': uploaded_serials,
        'missingSerials': missing_serials,
        'statuses': statuses,
    }), 200


@document_bp.route('/download/<path:filename>', methods=['GET'])
@login_required
def download_document(filename):
    """下载文档"""
    docs_dir = get_documents_dir()
    try:
        file_path = _safe_join(docs_dir, filename)
    except PermissionError:
        return jsonify({'error': '非法的文件路径'}), 403

    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404

    return send_file(str(file_path), as_attachment=True)


@document_bp.route('/view/<path:filename>', methods=['GET'])
@require_permission_value('web:view_documents')
def view_document(filename):
    """在线查看文档（浏览器内预览）"""
    docs_dir = get_documents_dir()
    try:
        file_path = _safe_join(docs_dir, filename)
    except PermissionError:
        return jsonify({'error': '非法的文件路径'}), 403

    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404

    response = send_file(str(file_path), as_attachment=False, mimetype='application/pdf')
    encoded_name = url_quote(file_path.name, safe='')
    response.headers['Content-Disposition'] = (
        f"inline; filename=\"document.pdf\"; filename*=UTF-8''{encoded_name}"
    )
    return response


@document_bp.route('/delete/<path:filename>', methods=['DELETE'])
@require_permission_value('web:manage_documents')
def delete_document(filename):
    """删除文档"""
    docs_dir = get_documents_dir()
    try:
        file_path = _safe_join(docs_dir, filename)
    except PermissionError:
        return jsonify({'error': '非法的文件路径'}), 403

    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404

    file_path.unlink()
    logger.info(f"PDF deleted: {file_path}")

    return jsonify({'success': True}), 200

@document_bp.route('/stats', methods=['GET'])
@require_permission_value('web:view_documents')
def get_stats():
    """获取统计信息"""
    docs_dir = get_documents_dir()

    total_count = len(list(docs_dir.rglob('*.pdf')))
    total_size = sum(f.stat().st_size for f in docs_dir.rglob('*.pdf'))

    return jsonify({
        'total_documents': total_count,
        'total_size_bytes': total_size
    }), 200
