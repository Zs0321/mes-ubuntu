"""
扩展缓存策略 - 用户会话和查询结果缓存

提供更多缓存功能：
- 用户会话缓存
- 查询结果缓存
- 静态资源缓存
"""

import json
import hashlib
from typing import Optional, Dict, Any, Callable
from functools import wraps
import logging
import sys
from pathlib import Path

# 添加 app_web 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.redis_config import RedisManager
from services.performance_monitor import monitor

logger = logging.getLogger(__name__)


class ExtendedCacheService:
    """扩展缓存服务"""

    # 缓存过期时间（秒）
    USER_SESSION_TTL = 86400  # 24 小时
    QUERY_RESULT_TTL = 600  # 10 分钟
    STATIC_RESOURCE_TTL = 3600  # 1 小时
    API_RESPONSE_TTL = 300  # 5 分钟

    def __init__(self):
        self.redis = RedisManager.get_instance()

    def _is_available(self) -> bool:
        """检查缓存是否可用"""
        return self.redis is not None and RedisManager.is_available()

    def get_user_session(self, user_id: str) -> Optional[Dict]:
        """
        获取用户会话缓存

        Args:
            user_id: 用户 ID

        Returns:
            用户会话数据
        """
        if not self._is_available():
            monitor.record_cache_miss()
            return None

        try:
            key = f"session:user:{user_id}"
            data = self.redis.get(key)

            if data:
                monitor.record_cache_hit()
                return json.loads(data)
            else:
                monitor.record_cache_miss()

        except Exception as e:
            logger.warning(f"获取用户会话缓存失败: {e}")
            monitor.record_cache_miss()

        return None

    def set_user_session(self, user_id: str, session_data: Dict) -> bool:
        """
        设置用户会话缓存

        Args:
            user_id: 用户 ID
            session_data: 会话数据

        Returns:
            是否成功
        """
        if not self._is_available():
            return False

        try:
            key = f"session:user:{user_id}"
            self.redis.setex(
                key,
                self.USER_SESSION_TTL,
                json.dumps(session_data, ensure_ascii=False)
            )
            return True
        except Exception as e:
            logger.warning(f"设置用户会话缓存失败: {e}")
            return False

    def invalidate_user_session(self, user_id: str) -> bool:
        """
        使用户会话缓存失效

        Args:
            user_id: 用户 ID

        Returns:
            是否成功
        """
        if not self._is_available():
            return False

        try:
            key = f"session:user:{user_id}"
            self.redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"使用户会话缓存失效失败: {e}")
            return False

    def get_query_result(self, query_key: str) -> Optional[Any]:
        """
        获取查询结果缓存

        Args:
            query_key: 查询键

        Returns:
            查询结果
        """
        if not self._is_available():
            monitor.record_cache_miss()
            return None

        try:
            key = f"query:result:{query_key}"
            data = self.redis.get(key)

            if data:
                monitor.record_cache_hit()
                return json.loads(data)
            else:
                monitor.record_cache_miss()

        except Exception as e:
            logger.warning(f"获取查询结果缓存失败: {e}")
            monitor.record_cache_miss()

        return None

    def set_query_result(self, query_key: str, result: Any, ttl: Optional[int] = None) -> bool:
        """
        设置查询结果缓存

        Args:
            query_key: 查询键
            result: 查询结果
            ttl: 过期时间（秒），默认使用 QUERY_RESULT_TTL

        Returns:
            是否成功
        """
        if not self._is_available():
            return False

        try:
            key = f"query:result:{query_key}"
            ttl = ttl or self.QUERY_RESULT_TTL
            self.redis.setex(
                key,
                ttl,
                json.dumps(result, ensure_ascii=False)
            )
            return True
        except Exception as e:
            logger.warning(f"设置查询结果缓存失败: {e}")
            return False

    def get_api_response(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """
        获取 API 响应缓存

        Args:
            endpoint: API 端点
            params: 请求参数

        Returns:
            API 响应
        """
        if not self._is_available():
            monitor.record_cache_miss()
            return None

        try:
            # 生成缓存键
            cache_key = self._generate_cache_key(endpoint, params)
            key = f"api:response:{cache_key}"
            data = self.redis.get(key)

            if data:
                monitor.record_cache_hit()
                return json.loads(data)
            else:
                monitor.record_cache_miss()

        except Exception as e:
            logger.warning(f"获取 API 响应缓存失败: {e}")
            monitor.record_cache_miss()

        return None

    def set_api_response(self, endpoint: str, params: Dict, response: Dict, ttl: Optional[int] = None) -> bool:
        """
        设置 API 响应缓存

        Args:
            endpoint: API 端点
            params: 请求参数
            response: API 响应
            ttl: 过期时间（秒），默认使用 API_RESPONSE_TTL

        Returns:
            是否成功
        """
        if not self._is_available():
            return False

        try:
            cache_key = self._generate_cache_key(endpoint, params)
            key = f"api:response:{cache_key}"
            ttl = ttl or self.API_RESPONSE_TTL
            self.redis.setex(
                key,
                ttl,
                json.dumps(response, ensure_ascii=False)
            )
            return True
        except Exception as e:
            logger.warning(f"设置 API 响应缓存失败: {e}")
            return False

    def _generate_cache_key(self, endpoint: str, params: Dict) -> str:
        """
        生成缓存键

        Args:
            endpoint: API 端点
            params: 请求参数

        Returns:
            缓存键（MD5 哈希）
        """
        # 将端点和参数组合成字符串
        key_string = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        # 生成 MD5 哈希
        return hashlib.md5(key_string.encode()).hexdigest()

    def clear_pattern(self, pattern: str) -> int:
        """
        清理匹配模式的所有缓存

        Args:
            pattern: 匹配模式（例如 "query:*"）

        Returns:
            清理的键数量
        """
        if not self._is_available():
            return 0

        try:
            count = 0
            for key in self.redis.scan_iter(match=pattern):
                self.redis.delete(key)
                count += 1
            logger.info(f"清理了 {count} 个匹配 {pattern} 的缓存键")
            return count
        except Exception as e:
            logger.warning(f"清理缓存失败: {e}")
            return 0


def cache_query_result(ttl: int = 600, key_func: Optional[Callable] = None):
    """
    查询结果缓存装饰器

    Args:
        ttl: 缓存过期时间（秒）
        key_func: 自定义键生成函数

    Example:
        @cache_query_result(ttl=300)
        def get_user_data(user_id):
            return db.query(user_id)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = ExtendedCacheService()

            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

            # 尝试从缓存获取
            cached_result = cache.get_query_result(cache_key)
            if cached_result is not None:
                return cached_result

            # 执行函数
            result = func(*args, **kwargs)

            # 设置缓存
            if result is not None:
                cache.set_query_result(cache_key, result, ttl=ttl)

            return result

        return wrapper
    return decorator


def cache_api_response(ttl: int = 300):
    """
    API 响应缓存装饰器

    Args:
        ttl: 缓存过期时间（秒）

    Example:
        @cache_api_response(ttl=600)
        def get_photos_api(inspection_id, limit):
            return {'photos': [...]}
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = ExtendedCacheService()

            # 生成缓存键
            endpoint = func.__name__
            params = {'args': args, 'kwargs': kwargs}

            # 尝试从缓存获取
            cached_response = cache.get_api_response(endpoint, params)
            if cached_response is not None:
                return cached_response

            # 执行函数
            response = func(*args, **kwargs)

            # 设置缓存
            if response is not None:
                cache.set_api_response(endpoint, params, response, ttl=ttl)

            return response

        return wrapper
    return decorator
