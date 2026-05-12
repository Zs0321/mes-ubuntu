"""
照片缓存管理 - 整合本地缓存和 Redis 缓存

整合了：
- PhotoCacheManager: 本地文件系统缓存
- PhotoCacheFallback: 缓存降级策略
- CacheService: Redis 缓存（已在 services.py 中导出）
"""

import sys
from pathlib import Path

# 添加 app_web 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 导入现有缓存管理器
from photo_cache_manager import PhotoCacheManager
from photo_cache_fallback import PhotoCacheFallback

__all__ = ['PhotoCacheManager', 'PhotoCacheFallback']
