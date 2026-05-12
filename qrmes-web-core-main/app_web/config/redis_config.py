"""Redis 配置和连接管理"""
import redis
from typing import Optional
import logging
import os

logger = logging.getLogger(__name__)


class RedisManager:
    """Redis 连接管理器"""

    _instance: Optional[redis.Redis] = None

    @classmethod
    def get_instance(cls, host: str = None, port: int = None, db: int = None) -> Optional[redis.Redis]:
        """
        获取 Redis 单例实例

        Args:
            host: Redis 主机地址（默认从环境变量或 localhost）
            port: Redis 端口（默认从环境变量或 6379）
            db: Redis 数据库编号（默认从环境变量或 0）

        Returns:
            Redis 实例，连接失败返回 None
        """
        if cls._instance is None:
            # 从环境变量或参数获取配置
            redis_host = host or os.getenv('REDIS_HOST', 'localhost')
            redis_port = port or int(os.getenv('REDIS_PORT', '6379'))
            redis_db = db or int(os.getenv('REDIS_DB', '0'))

            try:
                cls._instance = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
                # 测试连接
                cls._instance.ping()
                logger.info(f"Redis 连接成功: {redis_host}:{redis_port}")
            except redis.ConnectionError as e:
                logger.warning(f"Redis 连接失败: {e}，将使用无缓存模式")
                cls._instance = None
            except Exception as e:
                logger.error(f"Redis 初始化错误: {e}")
                cls._instance = None

        return cls._instance

    @classmethod
    def is_available(cls) -> bool:
        """检查 Redis 是否可用"""
        if cls._instance is None:
            return False
        try:
            cls._instance.ping()
            return True
        except:
            return False

    @classmethod
    def reset(cls):
        """重置连接（用于测试）"""
        cls._instance = None
