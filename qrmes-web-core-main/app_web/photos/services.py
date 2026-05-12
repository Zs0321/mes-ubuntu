"""
照片服务层 - 整合照片业务逻辑

整合了以下功能：
- PhotoService: 照片查询和分页（来自 services/photo_service.py）
- ThumbnailService: 缩略图生成（来自 services/thumbnail_service.py）
- CacheService: Redis 缓存（来自 services/cache_service.py）
- PhotoCacheManager: 本地缓存管理（来自 photo_cache_manager.py）
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# 添加 app_web 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 导入现有服务
from services.photo_service import PhotoService
from services.thumbnail_service import ThumbnailService
from services.cache_service import CacheService

__all__ = ['PhotoService', 'ThumbnailService', 'CacheService']
