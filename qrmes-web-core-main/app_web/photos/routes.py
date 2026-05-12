"""
照片模块路由 - 统一的 API 端点

整合了：
- photo_api.py: 同步照片 API
- async_photo_api.py: 异步照片 API
"""

import os
import sys
from pathlib import Path
from flask import request, jsonify, send_file, current_app
import logging

# 添加 app_web 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from . import photos_bp
from .services import PhotoService, ThumbnailService, CacheService
from .cache import PhotoCacheManager

logger = logging.getLogger(__name__)

# 初始化服务
DATA_DIR = os.getenv('DATA_DIR', 'data')
thumbnail_service = ThumbnailService(cache_dir=Path(DATA_DIR) / 'thumbnails')
cache_service = CacheService()


@photos_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    return jsonify({
        'status': 'ok',
        'module': 'photos',
        'cache_available': cache_service._is_available()
    })


@photos_bp.route('/list', methods=['GET'])
def list_photos():
    """
    获取照片列表（分页）

    Query Parameters:
        - inspection_id: 质检 ID（可选）
        - project_id: 项目 ID（可选）
        - limit: 每页数量（默认 50，最大 200）
        - cursor: 游标 ID（用于分页）
    """
    try:
        inspection_id = request.args.get('inspection_id')
        project_id = request.args.get('project_id')
        limit = request.args.get('limit', 50, type=int)
        cursor_id = request.args.get('cursor', type=int)

        # 获取数据库路径
        db_path = Path(current_app.config.get('DATABASE_PATH', 'data/unified.db'))
        photo_service = PhotoService(db_path)

        # 查询照片列表
        photos, next_cursor = photo_service.get_photos_paginated(
            inspection_id=inspection_id,
            project_id=project_id,
            limit=limit,
            cursor_id=cursor_id
        )

        return jsonify({
            'success': True,
            'photos': photos,
            'count': len(photos),
            'next_cursor': next_cursor,
            'has_more': next_cursor is not None
        })

    except Exception as e:
        logger.error(f"获取照片列表失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500


@photos_bp.route('/<photo_id>', methods=['GET'])
def get_photo(photo_id: str):
    """
    获取照片详情

    Path Parameters:
        - photo_id: 照片 ID
    """
    try:
        db_path = Path(current_app.config.get('DATABASE_PATH', 'data/unified.db'))
        photo_service = PhotoService(db_path)

        photo = photo_service.get_photo_by_id(photo_id)

        if not photo:
            return jsonify({'error': '照片不存在'}), 404

        return jsonify({
            'success': True,
            'photo': photo
        })

    except Exception as e:
        logger.error(f"获取照片详情失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500


@photos_bp.route('/<photo_id>/file', methods=['GET'])
def get_photo_file(photo_id: str):
    """
    获取照片文件

    Path Parameters:
        - photo_id: 照片 ID
    """
    try:
        db_path = Path(current_app.config.get('DATABASE_PATH', 'data/unified.db'))
        photo_service = PhotoService(db_path)

        photo = photo_service.get_photo_by_id(photo_id)

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


@photos_bp.route('/<photo_id>/thumbnail', methods=['GET'])
def get_photo_thumbnail(photo_id: str):
    """
    获取照片缩略图

    Path Parameters:
        - photo_id: 照片 ID

    Query Parameters:
        - size: 缩略图尺寸 (small/medium/large，默认 medium)
    """
    try:
        size = request.args.get('size', 'medium')

        db_path = Path(current_app.config.get('DATABASE_PATH', 'data/unified.db'))
        photo_service = PhotoService(db_path)

        photo = photo_service.get_photo_by_id(photo_id)

        if not photo:
            return jsonify({'error': '照片不存在'}), 404

        file_path = Path(photo['file_path'])
        if not file_path.exists():
            return jsonify({'error': '照片文件不存在'}), 404

        # 生成缩略图
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


@photos_bp.route('/recent', methods=['GET'])
def get_recent_photos():
    """
    获取最近上传的照片

    Query Parameters:
        - limit: 数量限制（默认 20，最大 100）
    """
    try:
        limit = request.args.get('limit', 20, type=int)

        db_path = Path(current_app.config.get('DATABASE_PATH', 'data/unified.db'))
        photo_service = PhotoService(db_path)

        photos = photo_service.get_recent_photos(limit=limit)

        return jsonify({
            'success': True,
            'photos': photos,
            'count': len(photos)
        })

    except Exception as e:
        logger.error(f"获取最近照片失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500


@photos_bp.route('/count', methods=['GET'])
def get_photo_count():
    """
    获取照片总数

    Query Parameters:
        - inspection_id: 质检 ID（可选）
        - project_id: 项目 ID（可选）
    """
    try:
        inspection_id = request.args.get('inspection_id')
        project_id = request.args.get('project_id')

        db_path = Path(current_app.config.get('DATABASE_PATH', 'data/unified.db'))
        photo_service = PhotoService(db_path)

        count = photo_service.get_photo_count(
            inspection_id=inspection_id,
            project_id=project_id
        )

        return jsonify({
            'success': True,
            'count': count
        })

    except Exception as e:
        logger.error(f"获取照片数量失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500
