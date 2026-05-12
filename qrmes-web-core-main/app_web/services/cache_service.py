"""缓存服务 - 照片元数据缓存"""
import json
from typing import Optional, List, Dict, Any
from functools import wraps
import logging
import sys
from pathlib import Path

# 添加 app_web 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.redis_config import RedisManager

logger = logging.getLogger(__name__)

# 延迟导入监控器以避免循环依赖
_monitor = None

def get_monitor():
    """延迟获取监控器实例"""
    global _monitor
    if _monitor is None:
        try:
            from services.performance_monitor import monitor
            _monitor = monitor
        except ImportError:
            _monitor = None
    return _monitor


class CacheService:
    """缓存服务"""

    # 缓存过期时间（秒）
    PHOTO_METADATA_TTL = 3600  # 1 小时
    PHOTO_LIST_TTL = 300  # 5 分钟
    USER_SESSION_TTL = 86400  # 24 小时

    def __init__(self):
        self.redis = RedisManager.get_instance()

    def _is_available(self) -> bool:
        """检查缓存是否可用"""
        return self.redis is not None and RedisManager.is_available()

    def get_photo_metadata(self, photo_id: str) -> Optional[Dict]:
        """获取照片元数据缓存"""
        if not self._is_available():
            monitor = get_monitor()
            if monitor:
                monitor.record_cache_miss()
            return None

        try:
            key = f"photo:metadata:{photo_id}"
            data = self.redis.get(key)

            monitor = get_monitor()
            if data:
                if monitor:
                    monitor.record_cache_hit()
                return json.loads(data)
            else:
                if monitor:
                    monitor.record_cache_miss()
        except Exception as e:
            logger.warning(f"获取缓存失败: {e}")
            monitor = get_monitor()
            if monitor:
                monitor.record_cache_miss()

        return None

    def set_photo_metadata(self, photo_id: str, metadata: Dict) -> bool:
        """设置照片元数据缓存"""
        if not self._is_available():
            return False

        try:
            key = f"photo:metadata:{photo_id}"
            self.redis.setex(
                key,
                self.PHOTO_METADATA_TTL,
                json.dumps(metadata, ensure_ascii=False)
            )
            return True
        except Exception as e:
            logger.warning(f"设置缓存失败: {e}")
            return False

    def get_photo_list(self, cache_key: str) -> Optional[List[Dict]]:
        """获取照片列表缓存"""
        if not self._is_available():
            return None

        try:
            key = f"photo:list:{cache_key}"
            data = self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"获取列表缓存失败: {e}")

        return None

    def set_photo_list(self, cache_key: str, photos: List[Dict]) -> bool:
        """设置照片列表缓存"""
        if not self._is_available():
            return False

        try:
            key = f"photo:list:{cache_key}"
            self.redis.setex(
                key,
                self.PHOTO_LIST_TTL,
                json.dumps(photos, ensure_ascii=False)
            )
            return True
        except Exception as e:
            logger.warning(f"设置列表缓存失败: {e}")
            return False

    def invalidate_photo(self, photo_id: str) -> bool:
        """使照片缓存失效"""
        if not self._is_available():
            return False

        try:
            # 删除照片元数据缓存
            self.redis.delete(f"photo:metadata:{photo_id}")
            # 删除所有照片列表缓存（简单粗暴）
            pattern = "photo:list:*"
            for key in self.redis.scan_iter(match=pattern):
                self.redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"使缓存失效失败: {e}")
            return False


def cached(ttl: int = 300, key_prefix: str = "cache"):
    """缓存装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = CacheService()

            # 生成缓存键
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(kwargs)}"

            # 尝试从缓存获取
            if cache._is_available():
                try:
                    data = cache.redis.get(cache_key)
                    if data:
                        return json.loads(data)
                except:
                    pass

            # 执行函数
            result = func(*args, **kwargs)

            # 设置缓存
            if cache._is_available() and result is not None:
                try:
                    cache.redis.setex(
                        cache_key,
                        ttl,
                        json.dumps(result, ensure_ascii=False)
                    )
                except:
                    pass

            return result

        return wrapper
    return decorator
