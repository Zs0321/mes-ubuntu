"""
异步任务模块

导出所有异步任务
"""

from .photo_tasks import (
    generate_thumbnail_async,
    batch_generate_thumbnails,
    analyze_photo,
    cleanup_old_thumbnails,
    refresh_cache
)

__all__ = [
    'generate_thumbnail_async',
    'batch_generate_thumbnails',
    'analyze_photo',
    'cleanup_old_thumbnails',
    'refresh_cache'
]
