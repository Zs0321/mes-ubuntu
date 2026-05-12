#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
照片管理API模块
提供照片上传、元数据管理和查看功能
"""

import os
import json
import time
import uuid
import re
import sqlite3
from threading import Lock
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import quote, unquote
from flask import Blueprint, request, jsonify, send_file, current_app, session
from werkzeug.utils import secure_filename
from werkzeug.exceptions import BadRequest, NotFound
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建蓝图
photo_bp = Blueprint('photo_api', __name__, url_prefix='/api/photos')

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'bmp', 'gif'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# 初始化缩略图服务
from services.thumbnail_service import ThumbnailService
DATA_DIR = os.getenv('DATA_DIR', 'data')
thumbnail_service = ThumbnailService(cache_dir=Path(DATA_DIR) / 'thumbnails')

_DATA_MANAGER = None
_DATA_MANAGER_INIT_DONE = False
_DATA_MANAGER_LOCK = Lock()


def _get_unified_db_path() -> Path:
    """统一使用 PHOTOS_DIR 同级目录下的 unified.db，避免 cwd 变化导致错库。"""
    photos_root = Path(current_app.config.get('PHOTOS_DIR', 'picture')).resolve()
    return photos_root.parent / 'unified.db'


def _get_data_manager():
    """惰性初始化 DataAccessManager，并确保表结构已创建。"""
    global _DATA_MANAGER, _DATA_MANAGER_INIT_DONE
    from data_access_layer import DataAccessManager

    db_path = _get_unified_db_path()
    if _DATA_MANAGER is None or Path(getattr(_DATA_MANAGER, 'db_path', '')) != db_path:
        _DATA_MANAGER = DataAccessManager(db_path)
        _DATA_MANAGER_INIT_DONE = False

    if not _DATA_MANAGER_INIT_DONE:
        with _DATA_MANAGER_LOCK:
            if not _DATA_MANAGER_INIT_DONE:
                if not _DATA_MANAGER.initialize_database():
                    raise RuntimeError(f"初始化数据库失败: {db_path}")
                _DATA_MANAGER_INIT_DONE = True

    return _DATA_MANAGER


def _get_photo_index_db_path() -> Path:
    override = current_app.config.get("PHOTO_INDEX_DB_PATH")
    if override:
        return Path(override)
    try:
        import photo_index
        return Path(photo_index.DEFAULT_DB_PATH)
    except Exception:
        return Path(__file__).parent / "cache" / "photos" / "photo_index.db"


def _remove_photo_index_entry(file_paths: List[Path]) -> None:
    try:
        import photo_index

        paths = [str(p) for p in file_paths if p]
        if not paths:
            return
        removed = photo_index.remove_paths(paths, db_path=_get_photo_index_db_path())
        logger.info("照片索引删除完成: removed=%s paths=%s", removed, paths)
    except Exception as exc:
        logger.warning("删除照片索引失败，已忽略: %s", exc)


def _normalize_name(value: str) -> str:
    text = str(value or '').strip().lower()
    text = re.sub(r'[\s_-]+', '', text)
    return re.sub(r'[^\w\u4e00-\u9fff]+', '', text)


def _sanitize_folder_component(value: str) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    text = re.sub(r'[\\/*?:"<>|.]', '_', text)
    return text.strip().strip('.')


def _folder_match(folder_name: str, expected: str) -> bool:
    if not expected:
        return True
    if not folder_name:
        return False
    if folder_name == expected:
        return True

    expected_candidates = {
        expected,
        _sanitize_folder_component(expected),
    }
    folder_candidates = {
        folder_name,
        folder_name.split('_', 1)[0] if '_' in folder_name else folder_name,
        folder_name.rsplit('_', 1)[0] if '_' in folder_name else folder_name,
    }

    expected_normalized_values = {
        _normalize_name(value)
        for value in expected_candidates
        if value
    }
    folder_normalized_values = {
        _normalize_name(value)
        for value in folder_candidates
        if value
    }

    if folder_normalized_values.intersection(expected_normalized_values):
        return True

    for folder_key in folder_normalized_values:
        if not folder_key:
            continue
        for expected_key in expected_normalized_values:
            if not expected_key:
                continue
            if folder_key.startswith(expected_key) or folder_key.endswith(expected_key):
                return True
    return False


def _normalize_step(value: str) -> str:
    text = str(value or '').strip().lower()
    return re.sub(r'[^\w\u4e00-\u9fff]+', '', text)


def _extract_process_step(file_name: str, serial: str) -> str:
    stem = Path(file_name).stem
    prefix = f"{serial}_"
    if not stem.startswith(prefix):
        return ''
    remainder = stem[len(prefix):]
    if '_' not in remainder:
        return remainder

    parts = remainder.split('_')
    if len(parts) >= 4 and parts[-1].isdigit() and parts[-2].isdigit() and parts[-3].isdigit():
        if len(parts[-3]) == 8 and len(parts[-2]) == 6:
            return '_'.join(parts[:-3])
    if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
        if len(parts[-2]) == 8 and len(parts[-1]) == 6:
            return '_'.join(parts[:-2])
    if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) == 14:
        return '_'.join(parts[:-1])
    return remainder.rsplit('_', 1)[0]


def _build_compat_photo_payload(
    photo_file: Path,
    photos_root: Path,
    captured_at_sec: Optional[int] = None,
    process_step: Optional[str] = None,
) -> Dict[str, Any]:
    rel_path = photo_file.relative_to(photos_root)
    rel_path_encoded = quote(str(rel_path).replace(os.sep, '/'))
    serial_name = photo_file.parent.name
    mtime_sec = int(captured_at_sec) if captured_at_sec is not None else int(photo_file.stat().st_mtime)
    parsed_process_step = process_step or _extract_process_step(photo_file.name, serial_name)

    return {
        'fileName': photo_file.name,
        'filePath': str(photo_file),
        'productSerial': serial_name,
        'processStep': parsed_process_step,
        'captureTime': datetime.fromtimestamp(mtime_sec).isoformat(),
        'thumbnailUrl': f'/api/photos/thumbnail-direct?path={rel_path_encoded}',
        'fullUrl': f'/api/photos/compressed-direct?path={rel_path_encoded}',
    }


def _query_compat_photos_from_index(
    photos_root: Path,
    project_name: str,
    product_type: str,
    product_serial: str,
    process_step: str,
    limit: int,
) -> List[Dict[str, Any]]:
    db_path = _get_photo_index_db_path()
    if not db_path.exists():
        return []

    normalized_target_step = _normalize_step(process_step)
    params: List[Any] = []
    where_sql = ""
    if product_serial:
        where_sql = "WHERE serial_number = ?"
        params.append(product_serial)

    batch_size = limit if not (project_name or product_type or process_step) else min(max(limit * 5, 500), 5000)
    offset = 0
    matched: List[Dict[str, Any]] = []

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        with conn:
            while len(matched) < limit:
                rows = conn.execute(
                    f"""
                    SELECT file_path, mtime_sec, project_name, product_name, serial_number, filename
                    FROM photo_file_index
                    {where_sql}
                    ORDER BY mtime_sec DESC
                    LIMIT ? OFFSET ?
                    """,
                    tuple(params + [int(batch_size), int(offset)]),
                ).fetchall()
                if not rows:
                    break

                for row in rows:
                    file_path = Path(row['file_path'])
                    if not file_path.exists() or not file_path.is_file():
                        continue
                    if not _folder_match(str(row['project_name'] or ''), project_name):
                        continue
                    if not _folder_match(str(row['product_name'] or ''), product_type):
                        continue
                    parsed_process_step = _extract_process_step(
                        str(row['filename'] or file_path.name),
                        str(row['serial_number'] or file_path.parent.name),
                    )
                    if normalized_target_step and _normalize_step(parsed_process_step) != normalized_target_step:
                        continue

                    matched.append(
                        _build_compat_photo_payload(
                            file_path,
                            photos_root,
                            captured_at_sec=int(row['mtime_sec'] or 0),
                            process_step=parsed_process_step,
                        )
                    )
                    if len(matched) >= limit:
                        break

                if not (project_name or product_type or process_step):
                    break
                offset += batch_size
                if offset >= 20000:
                    break
    except sqlite3.DatabaseError as exc:
        logger.warning("兼容照片列表读取索引失败，回退兜底逻辑: %s", exc)
        return []

    return matched[:limit]


def _query_compat_photos_by_serial_fallback(
    photos_root: Path,
    project_name: str,
    product_type: str,
    product_serial: str,
    process_step: str,
    limit: int,
) -> List[Dict[str, Any]]:
    if not product_serial or not photos_root.exists():
        return []

    normalized_target_step = _normalize_step(process_step)
    candidate_files: List[Path] = []

    for project_dir in photos_root.iterdir():
        if not project_dir.is_dir():
            continue
        if project_name and not _folder_match(project_dir.name, project_name):
            continue

        for product_dir in project_dir.iterdir():
            if not product_dir.is_dir():
                continue
            if product_type and not _folder_match(product_dir.name, product_type):
                continue

            serial_dir = product_dir / product_serial
            if not serial_dir.exists() or not serial_dir.is_dir():
                continue

            for pattern in ('*.jpg', '*.jpeg', '*.png', '*.bmp', '*.gif'):
                candidate_files.extend(serial_dir.glob(pattern))

    candidate_files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

    photos: List[Dict[str, Any]] = []
    for photo_file in candidate_files:
        if not photo_file.exists() or not photo_file.is_file():
            continue

        parsed_process_step = _extract_process_step(photo_file.name, product_serial)
        if normalized_target_step and _normalize_step(parsed_process_step) != normalized_target_step:
            continue

        photos.append(
            _build_compat_photo_payload(
                photo_file,
                photos_root,
                process_step=parsed_process_step,
            )
        )
        if len(photos) >= limit:
            break

    return photos

def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_filename(filename: str) -> str:
    """清理文件名中的非法字符"""
    import re
    # 保留中文字符、英文字母、数字、下划线和连字符
    return re.sub(r'[^\w\u4e00-\u9fa5_-]', '_', filename)


def _is_truthy_flag(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "y"}


def _build_parseable_photo_base(product_serial: str, process_step: str) -> str:
    """
    生成可被工序解析器识别的文件名前缀。
    格式: {serial}_{step}_{yyyyMMdd_HHmmss}
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_serial = sanitize_filename(product_serial)
    sanitized_step = sanitize_filename(process_step)
    return f"{sanitized_serial}_{sanitized_step}_{timestamp}"


def _select_upload_filename(
    original_filename: str,
    product_serial: str,
    process_step: str,
    photo_dir: Path,
) -> str:
    """
    选择最终落盘文件名：
    1) 优先复用客户端文件名（仅当其本身符合工序命名规范且未冲突）；
    2) 否则使用服务端可解析命名，并在冲突时追加三位序号。
    """
    original_name = Path(original_filename or "").name
    ext = Path(original_name).suffix.lower()
    if ext.startswith("."):
        ext_no_dot = ext[1:]
    else:
        ext_no_dot = ""
    if ext_no_dot not in ALLOWED_EXTENSIONS:
        ext = ".jpg"

    sanitized_serial = sanitize_filename(product_serial)
    sanitized_client_stem = sanitize_filename(Path(original_name).stem)
    client_pattern = re.compile(
        rf"^{re.escape(sanitized_serial)}_.+_\d{{8}}_\d{{6}}(?:_\d+)?$",
        flags=re.IGNORECASE,
    )
    if sanitized_client_stem and client_pattern.match(sanitized_client_stem):
        client_candidate = f"{sanitized_client_stem}{ext}"
        if not (photo_dir / client_candidate).exists():
            return client_candidate

    base = _build_parseable_photo_base(product_serial, process_step)
    primary = f"{base}{ext}"
    if not (photo_dir / primary).exists():
        return primary

    for seq in range(1, 1000):
        candidate = f"{base}_{seq:03d}{ext}"
        if not (photo_dir / candidate).exists():
            return candidate

    # 理论上不会到这里，仍给出可解析兜底名称
    return f"{base}_{int(time.time() * 1000) % 1000:03d}{ext}"

def create_photo_directory(product_serial: str, project_name: str = None, 
                          project_code: str = None, product_type: str = None, 
                          model_number: str = None) -> Path:
    """
    创建照片存储目录
    目录结构: picture/{项目名称+项目号}/{产品类型+产品型号}/{序列号}/
    """
    # 获取照片存储根目录
    photos_root = Path(current_app.config.get('PHOTOS_DIR', 'picture'))
    
    # 构建项目目录名: {项目名称}_{项目号}
    if project_name and project_code:
        project_dir = sanitize_filename(f"{project_name}_{project_code}")
    else:
        project_dir = "default_project"
    
    # 构建产品类型目录名: {产品类型}_{产品型号}
    if product_type and model_number:
        product_dir = sanitize_filename(f"{product_type}_{model_number}")
    elif product_type:
        product_dir = sanitize_filename(product_type)
    else:
        product_dir = "default_product"
    
    # 序列号目录
    serial_dir = sanitize_filename(product_serial)
    
    # 完整路径: picture/{项目}/{产品类型}/{序列号}/
    photo_dir = photos_root / project_dir / product_dir / serial_dir
    photo_dir.mkdir(parents=True, exist_ok=True)
    
    return photo_dir

@photo_bp.route('/upload', methods=['POST'])
def upload_photo():
    """上传照片文件"""
    try:
        # 检查请求中是否包含文件
        if 'photo' not in request.files:
            return jsonify({'error': '没有找到照片文件'}), 400
        
        file = request.files['photo']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        # 获取表单数据
        product_serial = request.form.get('productSerial')
        process_step = request.form.get('processStep')
        project_name = request.form.get('projectName', '')
        project_code = request.form.get('projectCode', '')
        product_type = request.form.get('productType', '')
        model_number = request.form.get('modelNumber', '')

        if not process_step:
            process_step = (
                request.form.get('captureCategory')
                or request.form.get('photoCategory')
                or '产品拍照'
            )

        if not product_serial or not process_step:
            return jsonify({'error': '缺少必要参数'}), 400
        
        # 检查文件类型和大小
        if not allowed_file(file.filename):
            return jsonify({'error': '不支持的文件类型'}), 400
        
        # 检查文件大小
        file.seek(0, 2)  # 移动到文件末尾
        file_size = file.tell()
        file.seek(0)  # 重置到文件开头
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({'error': f'文件大小超过限制 ({MAX_FILE_SIZE // (1024*1024)}MB)'}), 400
        
        # 创建存储目录: picture/{项目}/{产品类型}/{序列号}/
        photo_dir = create_photo_directory(
            product_serial=product_serial,
            project_name=project_name,
            project_code=project_code,
            product_type=product_type,
            model_number=model_number
        )
        filename = _select_upload_filename(
            original_filename=file.filename,
            product_serial=product_serial,
            process_step=process_step,
            photo_dir=photo_dir,
        )
        file_path = photo_dir / filename
        if file.filename and Path(file.filename).name != filename:
            logger.info("照片文件名重写: original=%s -> stored=%s", Path(file.filename).name, filename)
        
        # 保存文件
        file.save(str(file_path))
        
        logger.info(f"照片上传成功: {filename}, 大小: {file_size} bytes")

        # 服务端兜底：上传成功即写入 process_photos，避免 metadata 接口失败导致“有文件无记录”
        fallback_photo_id = None
        try:
            data_manager = _get_data_manager()
            fallback_photo_id = data_manager.process_photo_repo.save_photo_metadata(
                product_serial=product_serial,
                process_step=process_step,
                file_path=str(file_path),
                file_name=filename,
                file_size=file_size,
                captured_by=(
                    request.form.get("capturedBy")
                    or request.form.get("captured_by")
                    or request.form.get("operatorId")
                    or request.form.get("operator_id")
                    or request.form.get("operator")
                    or session.get("username")
                    or "system"
                ),
                metadata={
                    "source": (
                        request.form.get("source")
                        or request.form.get("captureSource")
                        or request.form.get("channel")
                        or "upload_fallback"
                    ),
                    "projectName": project_name or "",
                    "projectCode": project_code or "",
                    "productType": product_type or "",
                    "modelNumber": model_number or "",
                    "stationId": request.form.get("stationId") or request.form.get("station_id") or "",
                    "uploadMode": request.form.get("uploadMode") or request.form.get("upload_mode") or "",
                },
            )
        except Exception as meta_exc:
            logger.warning("上传兜底元数据写入失败（不影响上传成功）: %s", meta_exc)

        skip_qc_enqueue = _is_truthy_flag(
            request.form.get("skipQcEnqueue")
            or request.form.get("skip_qc_enqueue")
            or request.form.get("skipTaskEnqueue")
            or request.form.get("skip_task_enqueue")
        )

        # 同步写入 Motor QC 工序任务（用于任务中心异步识别）
        # 任务主键按项目 ID/Code 归一，避免使用展示名导致任务页查不到
        project_id_for_task = (project_code or project_name or "").strip()
        task_enqueued = False
        task_id = None
        task_status = None
        if (not skip_qc_enqueue) and project_id_for_task and project_id_for_task.lower() != "default_project":
            try:
                from motor_qc.services.task_service import QCTaskService

                task = QCTaskService().upsert_task_for_photo(
                    project_id=project_id_for_task,
                    serial_number=product_serial.strip(),
                    process_name=process_step.strip(),
                    photo_path=str(file_path),
                    product_type=(product_type or "").strip(),
                )
                logger.info(
                    "Motor QC任务入队成功: task_id=%s project=%s serial=%s process=%s",
                    getattr(task, "id", None),
                    project_id_for_task,
                    product_serial,
                    process_step,
                )
                task_enqueued = True
                task_id = getattr(task, "id", None)
                task_status = getattr(task, "status", None)
            except Exception as task_exc:
                logger.warning(
                    "Motor QC任务入队失败（不影响上传成功）: project=%s serial=%s process=%s err=%s",
                    project_id_for_task,
                    product_serial,
                    process_step,
                    task_exc,
                )
        elif skip_qc_enqueue:
            logger.info(
                "Motor QC任务入队已跳过: project=%s serial=%s process=%s",
                project_id_for_task,
                product_serial,
                process_step,
            )
        
        return jsonify({
            'success': True,
            'filename': filename,
            'filePath': str(file_path),
            'fileSize': file_size,
            'message': '照片上传成功',
            'taskEnqueued': task_enqueued,
            'task_id': task_id,
            'task_status': task_status,
            'photo_id': fallback_photo_id,
        })
        
    except Exception as e:
        logger.error(f"照片上传失败: {e}")
        return jsonify({'error': f'上传失败: {str(e)}'}), 500

@photo_bp.route('/metadata', methods=['POST'])
def save_photo_metadata():
    """保存照片元数据"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '无效的JSON数据'}), 400
        
        # 验证必要字段
        required_fields = ['productSerial', 'processStep', 'filePath', 'fileName', 'fileSize', 'capturedBy']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'缺少必要字段: {field}'}), 400
        
        # 获取数据访问管理器
        data_manager = _get_data_manager()
        
        # 保存照片元数据
        photo_id = data_manager.process_photo_repo.save_photo_metadata(
            product_serial=data['productSerial'],
            process_step=data['processStep'],
            file_path=data['filePath'],
            file_name=data['fileName'],
            file_size=data['fileSize'],
            captured_by=data['capturedBy'],
            metadata=data.get('metadata', {})
        )
        
        if photo_id:
            logger.info(f"照片元数据保存成功: {data['fileName']} (ID: {photo_id})")
            return jsonify({
                'success': True,
                'photoId': photo_id,
                'message': '照片元数据保存成功'
            })
        else:
            return jsonify({'error': '保存照片元数据失败'}), 500
            
    except Exception as e:
        logger.error(f"保存照片元数据失败: {e}")
        return jsonify({'error': f'保存失败: {str(e)}'}), 500

@photo_bp.route('/product/<product_serial>', methods=['GET'])
def get_product_photos(product_serial: str):
    """获取产品的所有照片"""
    try:
        data_manager = _get_data_manager()
        
        photos = data_manager.process_photo_repo.get_photos_by_product(product_serial)
        
        # 添加照片访问URL
        for photo in photos:
            photo['url'] = f"/api/photos/file/{photo['id']}"
            photo['thumbnailUrl'] = f"/api/photos/thumbnail/{photo['id']}"
        
        return jsonify({
            'success': True,
            'photos': photos,
            'count': len(photos)
        })
        
    except Exception as e:
        logger.error(f"获取产品照片失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500

@photo_bp.route('/process/<process_step>', methods=['GET'])
def get_process_photos(process_step: str):
    """获取工序的所有照片"""
    try:
        limit = request.args.get('limit', 100, type=int)
        
        data_manager = _get_data_manager()
        
        photos = data_manager.process_photo_repo.get_photos_by_process_step(process_step, limit)
        
        # 添加照片访问URL
        for photo in photos:
            photo['url'] = f"/api/photos/file/{photo['id']}"
            photo['thumbnailUrl'] = f"/api/photos/thumbnail/{photo['id']}"
        
        return jsonify({
            'success': True,
            'photos': photos,
            'count': len(photos)
        })
        
    except Exception as e:
        logger.error(f"获取工序照片失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500

@photo_bp.route('/file/<int:photo_id>', methods=['GET'])
def get_photo_file(photo_id: int):
    """获取照片文件"""
    try:
        data_manager = _get_data_manager()
        
        # 获取照片元数据
        photo = data_manager.process_photo_repo.get_photo_by_id(photo_id)
        
        if not photo:
            return jsonify({'error': '照片不存在'}), 404
        
        file_path = Path(photo['file_path'])
        if not file_path.exists():
            return jsonify({'error': '照片文件不存在'}), 404
        
        return send_file(
            str(file_path),
            mimetype='image/jpeg',
            as_attachment=False,
            download_name=photo['file_name']
        )
        
    except Exception as e:
        logger.error(f"获取照片文件失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500

@photo_bp.route('/thumbnail/<int:photo_id>', methods=['GET'])
def get_photo_thumbnail(photo_id: int):
    """获取照片缩略图"""
    try:
        size = request.args.get('size', 'medium')  # small/medium/large

        data_manager = _get_data_manager()

        # 获取照片元数据
        photo = data_manager.process_photo_repo.get_photo_by_id(photo_id)

        if not photo:
            return jsonify({'error': '照片不存在'}), 404

        file_path = Path(photo['file_path'])
        if not file_path.exists():
            return jsonify({'error': '照片文件不存在'}), 404

        # 使用新的缩略图服务生成缩略图
        thumbnail_path = thumbnail_service.get_thumbnail(
            str(file_path),
            size=size
        )

        if not thumbnail_path:
            # 缩略图生成失败，返回原图
            logger.warning(f"缩略图生成失败，返回原图: {photo_id}")
            return send_file(
                str(file_path),
                mimetype='image/jpeg',
                as_attachment=False
            )

        return send_file(
            str(thumbnail_path),
            mimetype='image/jpeg',
            as_attachment=False
        )

    except Exception as e:
        logger.error(f"获取照片缩略图失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500

@photo_bp.route('/upload-status/<int:photo_id>', methods=['PUT'])
def update_upload_status(photo_id: int):
    """更新照片上传状态"""
    try:
        data = request.get_json()
        uploaded = data.get('uploaded', True)
        
        data_manager = _get_data_manager()
        
        success = data_manager.process_photo_repo.update_upload_status(photo_id, uploaded)
        
        if success:
            return jsonify({
                'success': True,
                'message': '上传状态更新成功'
            })
        else:
            return jsonify({'error': '更新上传状态失败'}), 500
            
    except Exception as e:
        logger.error(f"更新上传状态失败: {e}")
        return jsonify({'error': f'更新失败: {str(e)}'}), 500

@photo_bp.route('/<int:photo_id>', methods=['DELETE'])
def delete_photo(photo_id: int):
    """删除照片"""
    try:
        data_manager = _get_data_manager()
        
        # 获取照片信息
        photo = data_manager.process_photo_repo.get_photo_by_id(photo_id)
        
        if not photo:
            return jsonify({'error': '照片不存在'}), 404
        
        # 删除文件
        file_path = Path(photo['file_path'])
        if file_path.exists():
            file_path.unlink()
        
        # 删除缩略图
        thumbnail_path = get_thumbnail_path(file_path)
        if thumbnail_path.exists():
            thumbnail_path.unlink()
        
        # 删除数据库记录
        success = data_manager.process_photo_repo.delete_photo(photo_id)
        if success:
            _remove_photo_index_entry([file_path])
        
        if success:
            logger.info(f"照片删除成功: {photo['file_name']}")
            return jsonify({
                'success': True,
                'message': '照片删除成功'
            })
        else:
            return jsonify({'error': '删除照片记录失败'}), 500
            
    except Exception as e:
        logger.error(f"删除照片失败: {e}")
        return jsonify({'error': f'删除失败: {str(e)}'}), 500

@photo_bp.route('/delete-file', methods=['POST'])
def delete_photo_file():
    """通过文件路径删除照片"""
    try:
        data = request.get_json()
        if not data or 'filePath' not in data:
            return jsonify({'error': '缺少文件路径参数'}), 400
        
        file_path_str = str(data['filePath']).strip()
        photos_root = Path(current_app.config.get('PHOTOS_DIR', 'picture')).resolve()

        # 兼容历史索引中的绝对路径：
        # 若包含 /picture/ 段，则统一重映射到当前 PHOTOS_DIR 下的相对路径。
        normalized = file_path_str.replace('\\', '/')
        marker = '/picture/'
        marker_idx = normalized.lower().find(marker)
        if marker_idx >= 0:
            rel_path = normalized[marker_idx + len(marker):].lstrip('/')
            file_path = photos_root / rel_path
        else:
            raw_path = Path(file_path_str)
            if raw_path.is_absolute():
                file_path = raw_path
            else:
                file_path = photos_root / file_path_str.lstrip('/\\')

        resolved_path = file_path.resolve()

        # 安全检查：确保文件在照片根目录下
        if not (
            str(resolved_path) == str(photos_root)
            or str(resolved_path).startswith(str(photos_root) + os.sep)
        ):
            return jsonify({'error': '非法的文件路径'}), 403
        
        if not resolved_path.exists():
            return jsonify({'error': '照片文件不存在'}), 404
        if not resolved_path.is_file():
            return jsonify({'error': '目标不是照片文件'}), 400
        
        # 删除文件
        resolved_path.unlink()
        logger.info(f"照片文件删除成功: {resolved_path}")
        
        # 删除缩略图
        thumbnail_path = get_thumbnail_path(resolved_path)
        if thumbnail_path.exists():
            thumbnail_path.unlink()
            logger.info(f"缩略图删除成功: {thumbnail_path}")

        # 同步删除索引记录，避免 recent 列表短时间内显示“已删除照片”
        _remove_photo_index_entry([resolved_path, Path(file_path_str)])
        
        return jsonify({
            'success': True,
            'message': '照片删除成功'
        })
        
    except Exception as e:
        logger.error(f"删除照片文件失败: {e}")
        return jsonify({'error': f'删除失败: {str(e)}'}), 500

def generate_thumbnail(image_path: Path, size: tuple = (300, 300)) -> Path:
    """生成照片缩略图（使用缓存管理器）"""
    try:
        from photo_cache_manager import PhotoCacheManager
        
        # 使用缓存管理器
        cache_manager = PhotoCacheManager()
        thumbnail_path = cache_manager.get_thumbnail(image_path, size)
        
        if thumbnail_path:
            return thumbnail_path
        else:
            # 如果生成失败，返回原图路径
            return image_path
        
    except Exception as e:
        logger.error(f"生成缩略图失败: {e}")
        return image_path

@photo_bp.route('/search', methods=['GET'])
def search_photos():
    """搜索照片"""
    try:
        # 获取查询参数
        product_serial = request.args.get('productSerial')
        process_step = request.args.get('processStep')
        captured_by = request.args.get('capturedBy')
        date_from = request.args.get('dateFrom', type=int)
        date_to = request.args.get('dateTo', type=int)
        limit = request.args.get('limit', 100, type=int)
        
        data_manager = _get_data_manager()
        
        photos = data_manager.process_photo_repo.get_photos_with_filters(
            product_serial=product_serial,
            process_step=process_step,
            captured_by=captured_by,
            date_from=date_from,
            date_to=date_to,
            limit=limit
        )
        
        # 添加照片访问URL
        for photo in photos:
            photo['url'] = f"/api/photos/file/{photo['id']}"
            photo['thumbnailUrl'] = f"/api/photos/thumbnail/{photo['id']}"
        
        return jsonify({
            'success': True,
            'photos': photos,
            'count': len(photos)
        })
        
    except Exception as e:
        logger.error(f"搜索照片失败: {e}")
        return jsonify({'error': f'搜索失败: {str(e)}'}), 500


@photo_bp.route('/list', methods=['GET'])
def list_photos_compat():
    """
    移动端兼容：按项目/产品类型/序列号查询照片列表
    - 参数: projectName, productType, productSerial, limit
    - 响应字段兼容 Android: fileName/filePath/productSerial/captureTime/thumbnailUrl/fullUrl
    """
    try:
        started_at = time.time()
        project_name = (request.args.get('projectName') or '').strip()
        product_type = (request.args.get('productType') or '').strip()
        product_serial = (request.args.get('productSerial') or '').strip()
        process_step = (request.args.get('processStep') or '').strip()
        limit = request.args.get('limit', 200, type=int)
        if limit <= 0:
            limit = 200
        limit = min(limit, 1000)

        photos_root = Path(current_app.config.get('PHOTOS_DIR', 'picture'))
        if not photos_root.exists():
            return jsonify({'success': True, 'photos': [], 'count': 0})
        photos = _query_compat_photos_from_index(
            photos_root=photos_root,
            project_name=project_name,
            product_type=product_type,
            product_serial=product_serial,
            process_step=process_step,
            limit=limit,
        )
        source = 'index'

        if not photos and product_serial:
            photos = _query_compat_photos_by_serial_fallback(
                photos_root=photos_root,
                project_name=project_name,
                product_type=product_type,
                product_serial=product_serial,
                process_step=process_step,
                limit=limit,
            )
            if photos:
                source = 'serial_fallback'

        duration_ms = int((time.time() - started_at) * 1000)
        logger.info(
            "[photo_compat_list] source=%s project=%r product=%r serial=%r process=%r limit=%s count=%s duration_ms=%s",
            source,
            project_name,
            product_type,
            product_serial,
            process_step,
            limit,
            len(photos),
            duration_ms,
        )

        return jsonify({
            'success': True,
            'photos': photos,
            'count': len(photos),
        })
    except Exception as e:
        logger.error(f"兼容照片列表查询失败: {e}")
        return jsonify({'success': False, 'error': f'查询失败: {str(e)}'}), 500

@photo_bp.route('/statistics', methods=['GET'])
def get_photo_statistics():
    """获取照片统计信息"""
    try:
        data_manager = _get_data_manager()
        
        stats = data_manager.process_photo_repo.get_photo_statistics()
        
        return jsonify({
            'success': True,
            'statistics': stats
        })
        
    except Exception as e:
        logger.error(f"获取照片统计失败: {e}")
        return jsonify({'error': f'获取统计失败: {str(e)}'}), 500

@photo_bp.route('/<int:photo_id>/metadata', methods=['PUT'])
def update_photo_metadata(photo_id: int):
    """更新照片元数据"""
    try:
        data = request.get_json()
        if not data or 'metadata' not in data:
            return jsonify({'error': '无效的元数据'}), 400
        
        data_manager = _get_data_manager()
        
        success = data_manager.process_photo_repo.update_photo_metadata(photo_id, data['metadata'])
        
        if success:
            return jsonify({
                'success': True,
                'message': '照片元数据更新成功'
            })
        else:
            return jsonify({'error': '更新照片元数据失败'}), 500
            
    except Exception as e:
        logger.error(f"更新照片元数据失败: {e}")
        return jsonify({'error': f'更新失败: {str(e)}'}), 500

@photo_bp.route('/<int:photo_id>', methods=['GET'])
def get_photo_details(photo_id: int):
    """获取照片详细信息"""
    try:
        data_manager = _get_data_manager()
        
        photo = data_manager.process_photo_repo.get_photo_by_id(photo_id)
        
        if not photo:
            return jsonify({'error': '照片不存在'}), 404
        
        # 添加照片访问URL
        photo['url'] = f"/api/photos/file/{photo['id']}"
        photo['thumbnailUrl'] = f"/api/photos/thumbnail/{photo['id']}"
        
        return jsonify({
            'success': True,
            'photo': photo
        })
        
    except Exception as e:
        logger.error(f"获取照片详情失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500

@photo_bp.route('/scan-directory', methods=['GET'])
def scan_photo_directory():
    """
    扫描照片目录，获取所有照片文件
    目录结构: picture/{项目}/{产品类型}/{序列号}/
    """
    try:
        photos_root = Path(current_app.config.get('PHOTOS_DIR', 'picture'))
        
        if not photos_root.exists():
            return jsonify({
                'success': True,
                'photos': [],
                'count': 0,
                'message': '照片目录不存在'
            })
        
        photos = []
        photo_id = 1
        
        # 初始化缓存管理器（用于预生成缩略图）
        try:
            from photo_cache_manager import PhotoCacheManager
            cache_manager = PhotoCacheManager()
            pregenerate_thumbnails = True
        except Exception as e:
            logger.warning(f"无法初始化缓存管理器: {e}")
            cache_manager = None
            pregenerate_thumbnails = False
        
        # 遍历目录结构: picture/{项目}/{产品类型}/{序列号}/
        for project_dir in photos_root.iterdir():
            if not project_dir.is_dir():
                continue
                
            for product_dir in project_dir.iterdir():
                if not product_dir.is_dir():
                    continue
                    
                for serial_dir in product_dir.iterdir():
                    if not serial_dir.is_dir():
                        continue
                        
                    # 遍历序列号目录下的所有照片
                    for photo_file in serial_dir.glob('*.jpg'):
                        # 检查文件是否真实存在且可读
                        if not photo_file.exists() or not photo_file.is_file():
                            logger.warning(f"跳过无效文件: {photo_file}")
                            continue
                        
                        # 预生成缩略图（后端缓存）
                        if pregenerate_thumbnails and cache_manager:
                            try:
                                # 生成缩略图并缓存
                                cache_manager.get_thumbnail(photo_file, size=(300, 300))
                                # 生成压缩图并缓存
                                cache_manager.get_compressed_image(photo_file, max_width=1200, quality=85)
                            except Exception as thumb_error:
                                logger.warning(f"预生成缩略图失败 {photo_file.name}: {thumb_error}")
                        
                        # 解析文件名: {序列号}_{工序名称}_{时间戳}.jpg
                        file_name = photo_file.name
                        parts = file_name.replace('.jpg', '').split('_')
                        
                        if len(parts) >= 2:
                            product_serial = parts[0]
                            process_step = parts[1]
                            timestamp = '_'.join(parts[2:]) if len(parts) > 2 else ''
                        else:
                            product_serial = serial_dir.name
                            process_step = '未知工序'
                            timestamp = ''
                        
                        # 获取文件信息
                        file_stat = photo_file.stat()
                        
                        # 计算相对路径并进行 URL 编码，避免中文/空格等特殊字符导致访问失败
                        rel_path = photo_file.relative_to(photos_root)
                        rel_path_str = quote(str(rel_path).replace(os.sep, '/'))

                        photos.append({
                            'id': photo_id,
                            'file_name': file_name,
                            'file_path': str(photo_file),
                            'file_size': file_stat.st_size,
                            'product_serial': product_serial,
                            'process_step': process_step,
                            'project_name': project_dir.name,
                            'product_type': product_dir.name,
                            'captured_at': int(file_stat.st_mtime * 1000),
                            'uploaded_at': int(file_stat.st_mtime * 1000),
                            'url': f"/api/photos/compressed-direct?path={rel_path_str}",  # 使用压缩图片
                            'originalUrl': f"/api/photos/file-direct?path={rel_path_str}",  # 原图URL
                            'thumbnailUrl': f"/api/photos/thumbnail-direct?path={rel_path_str}",
                            'exists': True  # 标记文件存在
                        })
                        photo_id += 1
        
        # 按拍摄时间倒序排序
        photos.sort(key=lambda x: x['captured_at'], reverse=True)
        
        logger.info(f"扫描完成: 找到 {len(photos)} 张照片，预生成缩略图: {pregenerate_thumbnails}")
        
        return jsonify({
            'success': True,
            'photos': photos,
            'count': len(photos),
            'thumbnails_cached': pregenerate_thumbnails
        })
        
    except Exception as e:
        logger.error(f"扫描照片目录失败: {e}")
        return jsonify({'error': f'扫描失败: {str(e)}'}), 500

@photo_bp.route('/file-direct', methods=['GET'])
def get_photo_file_direct():
    """直接通过文件路径获取照片"""
    try:
        rel_path_raw = request.args.get('path')
        if not rel_path_raw:
            return jsonify({'error': '缺少路径参数'}), 400

        # 兼容前端已做过 URL 编码的情况
        rel_path = unquote(rel_path_raw)
        
        photos_root = Path(current_app.config.get('PHOTOS_DIR', 'picture'))
        file_path = photos_root / rel_path
        
        if not file_path.exists() or not file_path.is_file():
            return jsonify({'error': '照片文件不存在'}), 404
        
        # 安全检查：确保文件在照片根目录下
        if not str(file_path.resolve()).startswith(str(photos_root.resolve())):
            return jsonify({'error': '非法的文件路径'}), 403
        
        return send_file(
            str(file_path),
            mimetype='image/jpeg',
            as_attachment=False,
            download_name=file_path.name
        )
        
    except Exception as e:
        logger.error(f"获取照片文件失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500

@photo_bp.route('/thumbnail-direct', methods=['GET'])
def get_photo_thumbnail_direct():
    """直接通过文件路径获取照片缩略图"""
    try:
        rel_path_raw = request.args.get('path')
        if not rel_path_raw:
            return jsonify({'error': '缺少路径参数'}), 400

        # 兼容前端已做过 URL 编码的情况
        rel_path = unquote(rel_path_raw)
        
        photos_root = Path(current_app.config.get('PHOTOS_DIR', 'picture'))
        file_path = photos_root / rel_path
        
        if not file_path.exists() or not file_path.is_file():
            return jsonify({'error': '照片文件不存在'}), 404
        
        # 安全检查
        if not str(file_path.resolve()).startswith(str(photos_root.resolve())):
            return jsonify({'error': '非法的文件路径'}), 403
        
        # 生成缩略图
        thumbnail_path = generate_thumbnail(file_path)
        
        return send_file(
            str(thumbnail_path),
            mimetype='image/jpeg',
            as_attachment=False
        )
        
    except Exception as e:
        logger.error(f"获取照片缩略图失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500

@photo_bp.route('/compressed-direct', methods=['GET'])
def get_photo_compressed_direct():
    """获取压缩后的照片用于Web显示"""
    try:
        rel_path_raw = request.args.get('path')
        if not rel_path_raw:
            logger.error("缺少路径参数")
            return jsonify({'error': '缺少路径参数'}), 400

        rel_path = unquote(rel_path_raw)
        logger.info(f"请求压缩图片: {rel_path}")
        
        photos_root = Path(current_app.config.get('PHOTOS_DIR', 'picture'))
        file_path = photos_root / rel_path
        
        if not file_path.exists() or not file_path.is_file():
            logger.error(f"照片文件不存在: {file_path}")
            return jsonify({'error': '照片文件不存在', 'path': str(file_path)}), 404
        
        # 安全检查
        if not str(file_path.resolve()).startswith(str(photos_root.resolve())):
            logger.error(f"非法的文件路径: {file_path}")
            return jsonify({'error': '非法的文件路径'}), 403
        
        # 获取压缩图片
        try:
            from photo_cache_manager import PhotoCacheManager
            cache_manager = PhotoCacheManager()
            compressed_path = cache_manager.get_compressed_image(file_path, max_width=1200, quality=85)
            
            if compressed_path and compressed_path.exists():
                logger.info(f"返回压缩图片: {compressed_path}")
                return send_file(
                    str(compressed_path),
                    mimetype='image/jpeg',
                    as_attachment=False
                )
        except Exception as compress_error:
            logger.warning(f"压缩图片失败，返回原图: {compress_error}")
        
        # 如果压缩失败或不存在，返回原图
        logger.info(f"返回原图: {file_path}")
        return send_file(
            str(file_path),
            mimetype='image/jpeg',
            as_attachment=False
        )
        
    except Exception as e:
        logger.error(f"获取压缩照片失败: {e}", exc_info=True)
        return jsonify({'error': f'获取失败: {str(e)}'}), 500

@photo_bp.route('/cache/stats', methods=['GET'])
def get_cache_stats():
    """获取缓存统计信息"""
    try:
        from photo_cache_manager import PhotoCacheManager
        cache_manager = PhotoCacheManager()
        stats = cache_manager.get_cache_stats()
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"获取缓存统计失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500

@photo_bp.route('/cache/clear', methods=['POST'])
def clear_cache():
    """清空照片缓存"""
    try:
        from photo_cache_manager import PhotoCacheManager
        cache_manager = PhotoCacheManager()
        cache_manager.clear_cache()
        
        return jsonify({
            'success': True,
            'message': '缓存已清空'
        })
        
    except Exception as e:
        logger.error(f"清空缓存失败: {e}")
        return jsonify({'error': f'清空失败: {str(e)}'}), 500

def get_thumbnail_path(image_path: Path) -> Path:
    """获取缩略图路径"""
    thumbnail_dir = image_path.parent / 'thumbnails'
    return thumbnail_dir / f"thumb_{image_path.name}"

# 错误处理
@photo_bp.errorhandler(413)
def too_large(e):
    return jsonify({'error': '文件大小超过限制'}), 413

@photo_bp.errorhandler(400)
def bad_request(e):
    return jsonify({'error': '请求格式错误'}), 400

@photo_bp.errorhandler(404)
def not_found(e):
    return jsonify({'error': '资源不存在'}), 404

@photo_bp.errorhandler(500)
def internal_error(e):
    return jsonify({'error': '服务器内部错误'}), 500
