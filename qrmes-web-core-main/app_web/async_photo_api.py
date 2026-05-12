#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
异步照片加载 API
支持渐进式加载和懒加载
"""

from flask import Blueprint, jsonify, send_file, request, current_app
from pathlib import Path
import logging
import threading
import time
import sqlite3
from typing import Dict, List, Optional, Tuple
from photo_cache_manager import PhotoCacheManager
from photo_cache_fallback import PhotoCacheFallback

logger = logging.getLogger(__name__)


def _build_file_etag(file_path: Path) -> str:
    stat = file_path.stat()
    return f'W/"{stat.st_mtime_ns:x}-{stat.st_size:x}"'


async_photo_bp = Blueprint('async_photo_api', __name__, url_prefix='/api/photos/async')

# 全局缓存管理器
cache_manager = PhotoCacheManager()

# ========== Photo Index Background Refresh ==========

# 轻量后台刷新（单进程内）。多进程部署时，每个 worker 都可能各自刷新一次，但通过 TTL 限制频率。
_INDEX_REFRESH_TTL_SEC = 60
_indexer_lock = threading.Lock()
_indexer_running = False
_last_refresh_started_ts = 0.0
_last_refresh_finished_ts = 0.0
_last_refresh_error = None

_STATS_ALL_CACHE_TTL_SEC = 300
_stats_all_cache_lock = threading.Lock()
_stats_all_cache: Optional[Dict[str, int]] = None
_stats_all_cache_ts = 0.0
_stats_all_refreshing = False


def _get_photos_root() -> Path:
    photos_dir = current_app.config.get("PHOTOS_DIR")
    if photos_dir:
        return Path(photos_dir)
    # ?????? mesapp.py ?????????????????
    from qrmes_shared_core.config import config
    from qrmes_shared_core.data_dir_utils import resolve_data_dir

    data_root = resolve_data_dir(
        nas_local_base_path=config.nas_local_base_path,
        repo_root=Path(__file__).resolve().parent.parent,
    )
    return data_root / "picture"

def _get_index_db_path() -> Path:
    # 允许测试/部署覆盖（例如放到 DATA_DIR）
    override = current_app.config.get("PHOTO_INDEX_DB_PATH")
    if override:
        return Path(override)
    try:
        import photo_index

        return Path(photo_index.DEFAULT_DB_PATH)
    except Exception:
        # 极端兜底：仍然放在 app_web/cache 下
        return Path(__file__).parent / "cache" / "photos" / "photo_index.db"


def _get_unified_db_path() -> Path:
    photos_root = _get_photos_root().resolve()
    return photos_root.parent / "unified.db"


def _normalize_file_path(path_value: str) -> str:
    return str(path_value or "").strip().replace("\\", "/")


def _serial_matches_query(serial_name: str, query: str) -> bool:
    query_text = str(query or "").strip().casefold()
    if not query_text:
        return True
    return query_text in str(serial_name or "").strip().casefold()


def _chunk_list(values: List[str], chunk_size: int = 300):
    for idx in range(0, len(values), chunk_size):
        yield values[idx:idx + chunk_size]


def _load_uploader_map(file_paths: List[str]) -> Dict[str, Dict[str, str]]:
    """
    基于 process_photos + users 查询上传人信息，按 file_path 归并。
    返回:
      { normalized_file_path: { "capturedBy": "...", "uploader": "..." } }
    """
    normalized_paths = []
    seen = set()
    for path_value in file_paths:
        normalized = _normalize_file_path(path_value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_paths.append(normalized)

    if not normalized_paths:
        return {}

    db_path = _get_unified_db_path()
    if not db_path.exists():
        return {}

    uploader_map: Dict[str, Dict[str, str]] = {}
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            for chunk in _chunk_list(normalized_paths):
                placeholders = ",".join("?" for _ in chunk)
                sql = f"""
                    SELECT
                        REPLACE(pp.file_path, '\\\\', '/') AS normalized_path,
                        pp.captured_by AS captured_by,
                        COALESCE(
                            uid.display_name,
                            uname.display_name,
                            uid.synology_username,
                            uname.synology_username,
                            pp.captured_by,
                            ''
                        ) AS uploader_name
                    FROM process_photos pp
                    LEFT JOIN users uid
                        ON pp.captured_by = uid.id
                    LEFT JOIN users uname
                        ON pp.captured_by = uname.synology_username
                    WHERE REPLACE(pp.file_path, '\\\\', '/') IN ({placeholders})
                    ORDER BY pp.captured_at DESC, pp.id DESC
                """
                rows = conn.execute(sql, chunk).fetchall()
                for row in rows:
                    normalized = _normalize_file_path(row["normalized_path"])
                    if not normalized or normalized in uploader_map:
                        continue
                    uploader_map[normalized] = {
                        "capturedBy": str(row["captured_by"] or ""),
                        "uploader": str(row["uploader_name"] or ""),
                    }
    except Exception as exc:
        logger.warning(f"加载上传人信息失败，已回退默认值: {exc}")
        return {}

    return uploader_map


def _attach_uploader_info(photos: List[dict]) -> None:
    if not photos:
        return

    file_paths = []
    for photo in photos:
        file_path = photo.get("id") or photo.get("filePath") or photo.get("file_path")
        if file_path:
            file_paths.append(str(file_path))

    uploader_map = _load_uploader_map(file_paths)

    for photo in photos:
        file_path = photo.get("id") or photo.get("filePath") or photo.get("file_path")
        normalized = _normalize_file_path(file_path)
        uploader_info = uploader_map.get(normalized)
        if uploader_info:
            photo["capturedBy"] = uploader_info.get("capturedBy", "")
            photo["uploader"] = uploader_info.get("uploader", "")
        else:
            photo.setdefault("capturedBy", "")
            photo.setdefault("uploader", "系统")


def _query_distinct_index_values(
    db_path: Path,
    column: str,
    project_name: str = "",
    limit: int = 3000,
) -> List[str]:
    allowed_columns = {"project_name", "product_name"}
    if column not in allowed_columns or not db_path.exists():
        return []

    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            sql = f"""
                SELECT DISTINCT TRIM(COALESCE({column}, '')) AS value
                FROM photo_file_index
                WHERE TRIM(COALESCE({column}, '')) != ''
            """
            params: List[object] = []
            if project_name and column == "product_name":
                sql += " AND project_name = ?"
                params.append(project_name)
            sql += " ORDER BY value COLLATE NOCASE LIMIT ?"
            params.append(int(limit))
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [str(row["value"]) for row in rows if str(row["value"]).strip()]
    except Exception as exc:
        logger.warning(f"读取索引下拉选项失败({column}): {exc}")
        return []


def _scan_distinct_projects_products(
    photos_root: Path,
    project_name: str = "",
    limit: int = 3000,
) -> Dict[str, List[str]]:
    projects = set()
    products = set()

    if project_name:
        target_dir = photos_root / project_name
        if target_dir.exists() and target_dir.is_dir():
            projects.add(project_name)
            for product_dir in target_dir.iterdir():
                if product_dir.is_dir():
                    products.add(product_dir.name)
                    if len(products) >= limit:
                        break
        return {
            "projects": sorted(projects, key=lambda v: v.lower()),
            "products": sorted(products, key=lambda v: v.lower()),
        }

    if not photos_root.exists():
        return {"projects": [], "products": []}

    for project_dir in photos_root.iterdir():
        if not project_dir.is_dir():
            continue
        projects.add(project_dir.name)
        if len(projects) >= limit:
            break
        for product_dir in project_dir.iterdir():
            if product_dir.is_dir():
                products.add(product_dir.name)
                if len(products) >= limit:
                    break

    return {
        "projects": sorted(projects, key=lambda v: v.lower()),
        "products": sorted(products, key=lambda v: v.lower()),
    }


def _load_uploader_options(limit: int = 1000) -> List[str]:
    db_path = _get_unified_db_path()
    if not db_path.exists():
        return []

    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT DISTINCT
                    TRIM(COALESCE(
                        uid.display_name,
                        uname.display_name,
                        uid.synology_username,
                        uname.synology_username,
                        pp.captured_by,
                        ''
                    )) AS uploader
                FROM process_photos pp
                LEFT JOIN users uid
                    ON pp.captured_by = uid.id
                LEFT JOIN users uname
                    ON pp.captured_by = uname.synology_username
                WHERE TRIM(COALESCE(
                    uid.display_name,
                    uname.display_name,
                    uid.synology_username,
                    uname.synology_username,
                    pp.captured_by,
                    ''
                )) != ''
                ORDER BY uploader COLLATE NOCASE
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [str(row["uploader"]) for row in rows if str(row["uploader"]).strip()]
    except Exception as exc:
        logger.warning(f"加载上传人下拉选项失败: {exc}")
        return []


def _index_has_any_rows(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute("SELECT 1 FROM photo_file_index LIMIT 1;").fetchone()
        return row is not None
    except Exception:
        return False


def _get_index_age_sec(db_path: Path) -> int:
    try:
        # 优先用“本进程内最近一次 refresh finished”
        if _last_refresh_finished_ts > 0:
            return int(time.time() - _last_refresh_finished_ts)
        if db_path.exists():
            return int(time.time() - db_path.stat().st_mtime)
    except Exception:
        pass
    return -1


def _refresh_index_in_thread(photos_root: Path, db_path: Path) -> None:
    global _indexer_running, _last_refresh_finished_ts, _last_refresh_error

    try:
        import photo_index

        photo_index.scan_and_update(
            base_path=photos_root,
            search_pattern="*/*/*",
            days=None,
            limit_hint=None,
            db_path=db_path,
        )
    except Exception as e:
        _last_refresh_error = str(e)
        logger.error(f"[photo_index] 后台刷新失败: {e}", exc_info=True)
    finally:
        with _indexer_lock:
            _indexer_running = False
            _last_refresh_finished_ts = time.time()


def _store_stats_all_cache(stats: Dict[str, int]) -> None:
    global _stats_all_cache, _stats_all_cache_ts
    with _stats_all_cache_lock:
        _stats_all_cache = dict(stats or {})
        _stats_all_cache_ts = time.time()


def _get_stats_all_cache_snapshot() -> Tuple[Optional[Dict[str, int]], float]:
    with _stats_all_cache_lock:
        cached = dict(_stats_all_cache) if _stats_all_cache is not None else None
        cached_ts = _stats_all_cache_ts
    return cached, cached_ts


def _refresh_stats_all_in_thread(db_path: Path) -> None:
    global _stats_all_refreshing
    try:
        import photo_index

        stats_all = photo_index.query_stats(days=None, db_path=db_path)
        _store_stats_all_cache(stats_all)
    except Exception as exc:
        logger.warning(f"[photo_index] 全量统计后台刷新失败: {exc}", exc_info=True)
    finally:
        with _stats_all_cache_lock:
            _stats_all_refreshing = False


def _schedule_stats_all_refresh(db_path: Path) -> bool:
    global _stats_all_refreshing
    with _stats_all_cache_lock:
        if _stats_all_refreshing:
            return False
        _stats_all_refreshing = True

    thread = threading.Thread(
        target=_refresh_stats_all_in_thread,
        args=(db_path,),
        daemon=True,
        name="photo-stats-all-refresh",
    )
    thread.start()
    return True


def _load_stats_all_fast(db_path: Path, fallback: Dict[str, int]) -> Dict[str, int]:
    cached, cached_ts = _get_stats_all_cache_snapshot()
    if cached:
        if (time.time() - cached_ts) > _STATS_ALL_CACHE_TTL_SEC:
            _schedule_stats_all_refresh(db_path)
        return cached

    _schedule_stats_all_refresh(db_path)
    return dict(fallback or {})


def _maybe_start_index_refresh(photos_root: Path, db_path: Path) -> bool:
    """
    尝试启动后台刷新。返回 True 表示本次请求触发了刷新。
    """
    global _indexer_running, _last_refresh_started_ts, _last_refresh_error

    now = time.time()
    with _indexer_lock:
        if _indexer_running:
            return False
        if _last_refresh_started_ts and (now - _last_refresh_started_ts) < _INDEX_REFRESH_TTL_SEC:
            return False

        _indexer_running = True
        _last_refresh_started_ts = now
        _last_refresh_error = None

        t = threading.Thread(
            target=_refresh_index_in_thread,
            args=(photos_root, db_path),
            daemon=True,
            name="photo-index-refresh",
        )
        t.start()
        return True


@async_photo_bp.route('/list', methods=['GET'])
def list_photos():
    """
    获取照片列表（仅元数据，不加载图片）
    返回缩略图和原图的 URL，由前端按需加载
    """
    try:
        serial_number = request.args.get('serialNumber')
        project_name = request.args.get('projectName')
        
        if not serial_number:
            return jsonify({'error': '缺少序列号'}), 400
        
        # 构建照片目录路径
        photos_dir = _get_photos_root()
        
        # 查找照片目录
        photo_paths = []
        for project_dir in photos_dir.glob('*'):
            if not project_dir.is_dir():
                continue
            
            for product_dir in project_dir.glob('*'):
                if not product_dir.is_dir():
                    continue
                
                serial_dir = product_dir / serial_number
                if serial_dir.exists():
                    # 找到匹配的序列号目录
                    for photo_file in serial_dir.glob('*.jpg'):
                        photo_paths.append(photo_file)
        
        # 构建响应数据
        photos = []
        for photo_path in photo_paths:
            # 提取工序名称
            filename = photo_path.stem
            parts = filename.split('_')
            process_step = parts[1] if len(parts) > 1 else '未知工序'
            
            # 构建 URL - 直接使用路径字符串，Flask 会自动处理编码
            photo_path_str = str(photo_path)
            
            photos.append({
                'id': photo_path_str,
                'filename': photo_path.name,
                'serialNumber': serial_number,
                'processStep': process_step,
                'thumbnailUrl': f'/api/photos/async/thumbnail?path={photo_path_str}',
                'fullUrl': f'/api/photos/async/full?path={photo_path_str}',
                'size': photo_path.stat().st_size,
                'timestamp': int(photo_path.stat().st_mtime * 1000)  # 转换为毫秒
            })

        _attach_uploader_info(photos)
        
        return jsonify({
            'success': True,
            'count': len(photos),
            'photos': photos
        })
        
    except Exception as e:
        logger.error(f'获取照片列表失败: {e}')
        return jsonify({'error': str(e)}), 500

@async_photo_bp.route('/thumbnail', methods=['GET'])
def get_thumbnail():
    """
    获取缩略图（异步加载）
    优先返回缓存，缓存不存在时快速生成
    """
    try:
        photo_path = request.args.get('path')
        if not photo_path:
            return jsonify({'error': '缺少照片路径'}), 400
        
        image_path = Path(photo_path)
        
        # 使用降级策略获取缩略图
        file_path, is_cached, error = PhotoCacheFallback.get_thumbnail_with_fallback(
            cache_manager, image_path, size=(300, 300)
        )
        
        candidate_path = Path(file_path) if file_path else None
        cache_status = 'HIT' if is_cached else 'MISS'

        if candidate_path and not candidate_path.exists() and image_path.exists():
            logger.warning(f'缩略图缓存文件缺失，回退原图: {candidate_path}')
            candidate_path = image_path
            cache_status = 'FALLBACK'

        if candidate_path and candidate_path.exists():
            try:
                response = send_file(candidate_path, mimetype='image/jpeg')
                response.headers['X-Cache-Status'] = cache_status
                # 添加更强的缓存控制，避免 ERR_CACHE_READ_FAILURE
                response.headers['Cache-Control'] = 'public, max-age=86400, must-revalidate'
                response.headers['Pragma'] = 'public'
                # 添加 ETag 支持更好的缓存验证（避免每次读取整个文件计算 md5）
                response.headers['ETag'] = _build_file_etag(candidate_path)
                return response
            except FileNotFoundError:
                if candidate_path != image_path and image_path.exists():
                    logger.warning(f'缩略图发送时文件丢失，回退原图: {candidate_path}')
                    response = send_file(image_path, mimetype='image/jpeg')
                    response.headers['X-Cache-Status'] = 'FALLBACK'
                    response.headers['Cache-Control'] = 'public, max-age=86400, must-revalidate'
                    response.headers['Pragma'] = 'public'
                    response.headers['ETag'] = _build_file_etag(image_path)
                    return response
                raise
        else:
            return jsonify({'error': error or '图片不存在'}), 404
            
    except Exception as e:
        logger.error(f'获取缩略图失败: {e}')
        return jsonify({'error': str(e)}), 500

@async_photo_bp.route('/full', methods=['GET'])
def get_full_image():
    """
    获取完整图片（异步加载）
    返回压缩后的图片，适合 Web 显示
    """
    try:
        photo_path = request.args.get('path')
        if not photo_path:
            return jsonify({'error': '缺少照片路径'}), 400
        
        image_path = Path(photo_path)
        
        # 使用降级策略获取压缩图
        file_path, is_cached, error = PhotoCacheFallback.get_compressed_with_fallback(
            cache_manager, image_path, max_width=1200, quality=85
        )
        
        if file_path:
            try:
                response = send_file(file_path, mimetype='image/jpeg')
                response.headers['X-Cache-Status'] = 'HIT' if is_cached else 'MISS'
                response.headers['Cache-Control'] = 'public, max-age=86400'
                response.headers['ETag'] = _build_file_etag(file_path)
                # 不在响应头中包含中文错误信息，避免 UnicodeEncodeError
                return response
            except FileNotFoundError:
                if file_path != image_path and image_path.exists():
                    logger.warning(f'压缩图发送时文件丢失，回退原图: {file_path}')
                    response = send_file(image_path, mimetype='image/jpeg')
                    response.headers['X-Cache-Status'] = 'FALLBACK'
                    response.headers['Cache-Control'] = 'public, max-age=86400'
                    response.headers['ETag'] = _build_file_etag(image_path)
                    return response
                raise
        else:
            return jsonify({'error': error or '图片不存在'}), 404
            
    except Exception as e:
        logger.error(f'获取完整图片失败: {e}')
        return jsonify({'error': str(e)}), 500

@async_photo_bp.route('/original', methods=['GET'])
def get_original_image():
    """
    获取原始图片（按需加载）
    用于下载或高清查看
    """
    try:
        photo_path = request.args.get('path')
        if not photo_path:
            return jsonify({'error': '缺少照片路径'}), 400
        
        image_path = Path(photo_path)
        
        if not image_path.exists():
            return jsonify({'error': '图片不存在'}), 404
        
        response = send_file(image_path, mimetype='image/jpeg')
        response.headers['Cache-Control'] = 'public, max-age=86400'
        response.headers['ETag'] = _build_file_etag(image_path)
        return response
        
    except Exception as e:
        logger.error(f'获取原始图片失败: {e}')
        return jsonify({'error': str(e)}), 500

@async_photo_bp.route('/batch-thumbnails', methods=['POST'])
def get_batch_thumbnails():
    """
    批量获取缩略图 URL
    用于优化多图片页面的初始加载
    """
    try:
        data = request.get_json()
        photo_paths = data.get('paths', [])
        
        if not photo_paths:
            return jsonify({'error': '缺少照片路径列表'}), 400
        
        results = []
        for photo_path in photo_paths:
            image_path = Path(photo_path)
            
            # 检查缓存是否存在
            file_hash = cache_manager.get_file_hash(image_path)
            thumbnail_name = f"thumb_{file_hash}_300x300.jpg"
            thumbnail_path = cache_manager.thumbnail_dir / thumbnail_name
            
            results.append({
                'path': photo_path,
                'thumbnailUrl': f'/api/photos/async/thumbnail?path={photo_path}',
                'cached': thumbnail_path.exists(),
                'exists': image_path.exists()
            })
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        logger.error(f'批量获取缩略图失败: {e}')
        return jsonify({'error': str(e)}), 500

@async_photo_bp.route('/scan-directory-async', methods=['GET'])
def scan_directory_async():
    """
    异步扫描照片目录（不阻塞响应）
    立即返回照片列表，后台异步生成缓存
    """
    try:
        # 获取参数
        project_name = request.args.get('projectName', '')
        product_name = request.args.get('productName', '')
        serial_number = request.args.get('serialNumber', '')
        process_step_filter = request.args.get('processStep', '')
        uploader_filter = request.args.get('uploader', '')
        date_from = request.args.get('dateFrom', '')
        date_to = request.args.get('dateTo', '')

        date_from_ts = None
        date_to_ts = None
        try:
            if date_from:
                date_from_ts = int(time.mktime(time.strptime(date_from, "%Y-%m-%d")) * 1000)
        except Exception:
            logger.warning(f"无效的 dateFrom 参数: {date_from}")
            date_from_ts = None
        try:
            if date_to:
                date_to_ts = int(time.mktime(time.strptime(date_to, "%Y-%m-%d")) * 1000) + (24 * 60 * 60 * 1000 - 1)
        except Exception:
            logger.warning(f"无效的 dateTo 参数: {date_to}")
            date_to_ts = None
        
        # 构建搜索路径（优先使用 mesapp.py 中的 app.config['PHOTOS_DIR']）
        base_path = _get_photos_root()
        
        # 查找照片
        photos = []
        
        # 根据参数构建搜索模式
        if project_name and product_name:
            # 同时指定项目 + 产品时，限定在对应项目目录下，避免跨项目混入
            search_pattern = f'{project_name}/{product_name}/*'
        elif product_name:
            # 搜索产品下的所有序列号
            search_pattern = f'*/{product_name}/*'
        elif project_name:
            # 搜索项目下的所有产品
            search_pattern = f'{project_name}/*/*'
        else:
            # 搜索所有
            search_pattern = '*/*/*'
        
        # 扫描目录
        for serial_dir in base_path.glob(search_pattern):
            if not serial_dir.is_dir():
                continue
            
            # 获取路径信息
            path_parts = serial_dir.parts
            if len(path_parts) >= 3:
                current_project = path_parts[-3]
                current_product = path_parts[-2]
                current_serial = path_parts[-1]
            else:
                continue

            if serial_number and not _serial_matches_query(current_serial, serial_number):
                continue
            
            # 扫描照片文件
            for photo_file in serial_dir.glob('*.jpg'):
                file_timestamp = int(photo_file.stat().st_mtime * 1000)

                # 提取工序信息
                filename = photo_file.stem
                parts = filename.split('_')
                process_step = parts[1] if len(parts) > 1 else '未知工序'

                if process_step_filter and process_step != process_step_filter:
                    continue
                if date_from_ts is not None and file_timestamp < date_from_ts:
                    continue
                if date_to_ts is not None and file_timestamp > date_to_ts:
                    continue
                
                # 构建 URL - 直接使用路径字符串，Flask 会自动处理编码
                photo_path_str = str(photo_file)
                
                photos.append({
                    'id': photo_path_str,
                    'filename': photo_file.name,
                    'projectName': current_project,
                    'productName': current_product,
                    'serialNumber': current_serial,
                    'processStep': process_step,
                    'thumbnailUrl': f'/api/photos/async/thumbnail?path={photo_path_str}',
                    'fullUrl': f'/api/photos/async/full?path={photo_path_str}',
                    'originalUrl': f'/api/photos/async/original?path={photo_path_str}',
                    'size': photo_file.stat().st_size,
                    'timestamp': file_timestamp  # 转换为毫秒
                })

        _attach_uploader_info(photos)

        if uploader_filter:
            target_uploader = str(uploader_filter).strip().lower()
            photos = [
                p for p in photos
                if str(p.get('uploader') or '').strip().lower() == target_uploader
            ]
        photos.sort(key=lambda item: int(item.get('timestamp') or 0), reverse=True)
        
        return jsonify({
            'success': True,
            'message': '照片列表获取成功，缓存将在后台生成',
            'totalCount': len(photos),
            'photos': photos,
            'cacheInfo': {
                'willGenerateInBackground': True,
                'useAsyncLoading': True
            }
        })
        
    except Exception as e:
        logger.error(f'异步扫描目录失败: {e}')
        return jsonify({'error': str(e)}), 500


@async_photo_bp.route('/filter-options', methods=['GET'])
def filter_options():
    """返回照片筛选下拉所需的全量选项（项目/产品/上传人）。"""
    try:
        project_name = (request.args.get('projectName') or '').strip()
        photos_root = _get_photos_root()
        db_path = _get_index_db_path()

        projects = _query_distinct_index_values(db_path, "project_name")
        products = _query_distinct_index_values(db_path, "product_name", project_name=project_name)

        if not projects or not products:
            scanned = _scan_distinct_projects_products(photos_root, project_name=project_name)
            if not projects:
                projects = scanned.get("projects", [])
            if not products:
                products = scanned.get("products", [])

        uploaders = _load_uploader_options()

        return jsonify(
            {
                "success": True,
                "options": {
                    "projects": projects,
                    "products": products,
                    "uploaders": uploaders,
                },
            }
        )
    except Exception as e:
        logger.error(f"获取照片筛选选项失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@async_photo_bp.route('/cache-stats', methods=['GET'])
def get_cache_stats():
    """获取缓存统计信息"""
    try:
        stats = cache_manager.get_cache_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        logger.error(f'获取缓存统计失败: {e}')
        return jsonify({'error': str(e)}), 500


@async_photo_bp.route('/recent', methods=['GET'])
def recent_photos():
    """
    获取最近照片（默认 2 天 / 200 张）
    - 直接从 SQLite 索引查询，快速返回
    - 索引未就绪时：不阻塞，返回空列表并标记 indexReady=false，同时在后台触发刷新
    """
    try:
        days = request.args.get("days", type=int) or 2
        limit = request.args.get("limit", type=int) or 200

        # 基本参数约束，避免异常值导致压力
        if days < 1:
            days = 1
        if days > 3650:
            days = 3650
        if limit < 1:
            limit = 1
        if limit > 2000:
            limit = 2000

        photos_root = _get_photos_root()
        db_path = _get_index_db_path()

        index_ready = _index_has_any_rows(db_path)
        refreshing = False

        if not index_ready:
            # 索引不存在/为空：后台构建，不阻塞请求
            refreshing = _maybe_start_index_refresh(photos_root, db_path) or _indexer_running
            return jsonify(
                {
                    "success": True,
                    "photos": [],
                    "stats": {
                        "totalPhotos": 0,
                        "totalSizeBytes": 0,
                        "productCount": 0,
                        "processCount": 0,
                        "dateCount": 0,
                    },
                    "statsAll": {
                        "totalPhotos": 0,
                        "totalSizeBytes": 0,
                        "productCount": 0,
                        "processCount": 0,
                        "dateCount": 0,
                    },
                    "cacheInfo": {
                        "indexReady": False,
                        "refreshingInBackground": bool(refreshing),
                        "indexAgeSec": _get_index_age_sec(db_path),
                    },
                }
            )

        # 索引已就绪：直接查询 recent
        try:
            import photo_index

            photos = photo_index.query_recent(days=days, limit=limit, db_path=db_path)
            _attach_uploader_info(photos)
            stats = photo_index.query_recent_stats(days=days, db_path=db_path)
            stats_all = _load_stats_all_fast(db_path, fallback=stats)
        except Exception as e:
            logger.error(f"[photo_index] recent 查询失败: {e}", exc_info=True)
            photos = []
            stats = {
                "totalPhotos": 0,
                "totalSizeBytes": 0,
                "productCount": 0,
                "processCount": 0,
                "dateCount": 0,
            }
            stats_all = {
                "totalPhotos": 0,
                "totalSizeBytes": 0,
                "productCount": 0,
                "processCount": 0,
                "dateCount": 0,
            }
        else:
            if not _get_stats_all_cache_snapshot()[0]:
                _store_stats_all_cache(stats_all)

        # 轻量保鲜：索引“太旧”时触发后台刷新，但不阻塞
        if _get_index_age_sec(db_path) > _INDEX_REFRESH_TTL_SEC:
            refreshing = _maybe_start_index_refresh(photos_root, db_path) or _indexer_running
        else:
            refreshing = _indexer_running

        return jsonify(
            {
                "success": True,
                "photos": photos,
                "stats": stats,
                "statsAll": stats_all,
                "cacheInfo": {
                    "indexReady": True,
                    "refreshingInBackground": bool(refreshing),
                    "indexAgeSec": _get_index_age_sec(db_path),
                },
            }
        )

    except Exception as e:
        logger.error(f"获取 recent 照片失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
