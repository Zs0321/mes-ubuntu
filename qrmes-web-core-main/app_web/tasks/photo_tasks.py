"""
异步照片处理任务

提供后台照片分析、批量操作等异步任务
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional
import logging

# 添加 app_web 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from celery_config import celery_app
from services.thumbnail_service import ThumbnailService
from services.photo_service import PhotoService
from services.performance_monitor import monitor

logger = logging.getLogger(__name__)


@celery_app.task(name='tasks.photo.generate_thumbnail', bind=True, max_retries=3)
def generate_thumbnail_async(self, photo_id: str, size: str = 'medium'):
    """
    异步生成缩略图

    Args:
        photo_id: 照片 ID
        size: 缩略图尺寸

    Returns:
        缩略图路径或错误信息
    """
    try:
        import time
        start_time = time.time()

        # 获取照片信息
        db_path = Path('data/unified.db')
        photo_service = PhotoService(db_path)
        photo = photo_service.get_photo_by_id(photo_id)

        if not photo:
            return {'success': False, 'error': '照片不存在'}

        # 生成缩略图
        thumbnail_service = ThumbnailService(cache_dir=Path('data/thumbnails'))
        thumbnail_path = thumbnail_service.get_thumbnail(
            photo['file_path'],
            size=size
        )

        duration = time.time() - start_time
        monitor.record_thumbnail_generation(duration)

        if thumbnail_path:
            return {
                'success': True,
                'photo_id': photo_id,
                'thumbnail_path': str(thumbnail_path),
                'duration': duration
            }
        else:
            return {'success': False, 'error': '缩略图生成失败'}

    except Exception as e:
        logger.error(f"异步生成缩略图失败: {e}")
        # 重试
        raise self.retry(exc=e, countdown=60)


@celery_app.task(name='tasks.photo.batch_generate_thumbnails')
def batch_generate_thumbnails(photo_ids: List[str], size: str = 'medium'):
    """
    批量生成缩略图

    Args:
        photo_ids: 照片 ID 列表
        size: 缩略图尺寸

    Returns:
        处理结果统计
    """
    results = {
        'total': len(photo_ids),
        'success': 0,
        'failed': 0,
        'errors': []
    }

    for photo_id in photo_ids:
        try:
            result = generate_thumbnail_async.apply_async(
                args=[photo_id, size],
                priority=3  # 较低优先级
            )
            results['success'] += 1
        except Exception as e:
            results['failed'] += 1
            results['errors'].append({
                'photo_id': photo_id,
                'error': str(e)
            })
            logger.error(f"批量生成缩略图失败 {photo_id}: {e}")

    return results


@celery_app.task(name='tasks.photo.analyze_photo')
def analyze_photo(photo_id: str):
    """
    分析照片（占位符，可扩展为 AI 分析）

    Args:
        photo_id: 照片 ID

    Returns:
        分析结果
    """
    try:
        # 获取照片信息
        db_path = Path('data/unified.db')
        photo_service = PhotoService(db_path)
        photo = photo_service.get_photo_by_id(photo_id)

        if not photo:
            return {'success': False, 'error': '照片不存在'}

        # 这里可以添加 AI 分析逻辑
        # 例如：质量检测、缺陷识别等

        return {
            'success': True,
            'photo_id': photo_id,
            'analysis': {
                'quality': 'good',
                'defects': []
            }
        }

    except Exception as e:
        logger.error(f"照片分析失败: {e}")
        return {'success': False, 'error': str(e)}


@celery_app.task(name='tasks.batch.cleanup_old_thumbnails')
def cleanup_old_thumbnails(days: int = 30):
    """
    清理旧的缩略图缓存

    Args:
        days: 保留天数

    Returns:
        清理统计
    """
    try:
        import time
        from datetime import datetime, timedelta

        thumbnail_dir = Path('data/thumbnails')
        if not thumbnail_dir.exists():
            return {'success': True, 'deleted': 0}

        cutoff_time = time.time() - (days * 24 * 3600)
        deleted_count = 0

        for thumbnail_file in thumbnail_dir.glob('*.jpg'):
            if thumbnail_file.stat().st_mtime < cutoff_time:
                thumbnail_file.unlink()
                deleted_count += 1

        logger.info(f"清理了 {deleted_count} 个旧缩略图")

        return {
            'success': True,
            'deleted': deleted_count,
            'cutoff_days': days
        }

    except Exception as e:
        logger.error(f"清理缩略图失败: {e}")
        return {'success': False, 'error': str(e)}


@celery_app.task(name='tasks.batch.refresh_cache')
def refresh_cache(inspection_id: Optional[str] = None):
    """
    刷新缓存

    Args:
        inspection_id: 质检 ID（可选）

    Returns:
        刷新结果
    """
    try:
        from services.cache_service import CacheService

        cache = CacheService()

        if not cache._is_available():
            return {'success': False, 'error': 'Redis 不可用'}

        # 清理指定质检的缓存
        if inspection_id:
            # 这里可以添加更精细的缓存清理逻辑
            pass

        return {
            'success': True,
            'inspection_id': inspection_id
        }

    except Exception as e:
        logger.error(f"刷新缓存失败: {e}")
        return {'success': False, 'error': str(e)}
