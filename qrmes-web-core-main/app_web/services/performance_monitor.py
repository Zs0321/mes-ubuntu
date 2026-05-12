"""
性能监控模块 - 收集和跟踪系统性能指标

监控指标：
- Redis 缓存命中率
- API 响应时间
- 缩略图生成时间
- 数据库查询时间
"""

import time
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque
import threading

logger = logging.getLogger(__name__)


@dataclass
class MetricSnapshot:
    """性能指标快照"""
    timestamp: datetime
    cache_hits: int = 0
    cache_misses: int = 0
    api_requests: int = 0
    api_total_time: float = 0.0
    thumbnail_generations: int = 0
    thumbnail_total_time: float = 0.0
    db_queries: int = 0
    db_total_time: float = 0.0


class PerformanceMonitor:
    """性能监控器 - 单例模式"""

    _instance: Optional['PerformanceMonitor'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True

            # 当前指标
            self.cache_hits = 0
            self.cache_misses = 0
            self.api_requests = 0
            self.api_total_time = 0.0
            self.thumbnail_generations = 0
            self.thumbnail_total_time = 0.0
            self.db_queries = 0
            self.db_total_time = 0.0

            # 历史快照（保留最近 100 个）
            self.snapshots: deque = deque(maxlen=100)

            # 最后快照时间
            self.last_snapshot_time = datetime.now()

            logger.info("性能监控器已初始化")

    def record_cache_hit(self):
        """记录缓存命中"""
        self.cache_hits += 1

    def record_cache_miss(self):
        """记录缓存未命中"""
        self.cache_misses += 1

    def record_api_request(self, duration: float):
        """
        记录 API 请求

        Args:
            duration: 请求耗时（秒）
        """
        self.api_requests += 1
        self.api_total_time += duration

    def record_thumbnail_generation(self, duration: float):
        """
        记录缩略图生成

        Args:
            duration: 生成耗时（秒）
        """
        self.thumbnail_generations += 1
        self.thumbnail_total_time += duration

    def record_db_query(self, duration: float):
        """
        记录数据库查询

        Args:
            duration: 查询耗时（秒）
        """
        self.db_queries += 1
        self.db_total_time += duration

    def get_cache_hit_rate(self) -> float:
        """
        获取缓存命中率

        Returns:
            命中率（0-100）
        """
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return (self.cache_hits / total) * 100

    def get_avg_api_response_time(self) -> float:
        """
        获取平均 API 响应时间

        Returns:
            平均响应时间（毫秒）
        """
        if self.api_requests == 0:
            return 0.0
        return (self.api_total_time / self.api_requests) * 1000

    def get_avg_thumbnail_time(self) -> float:
        """
        获取平均缩略图生成时间

        Returns:
            平均生成时间（毫秒）
        """
        if self.thumbnail_generations == 0:
            return 0.0
        return (self.thumbnail_total_time / self.thumbnail_generations) * 1000

    def get_avg_db_query_time(self) -> float:
        """
        获取平均数据库查询时间

        Returns:
            平均查询时间（毫秒）
        """
        if self.db_queries == 0:
            return 0.0
        return (self.db_total_time / self.db_queries) * 1000

    def take_snapshot(self):
        """创建当前指标快照"""
        snapshot = MetricSnapshot(
            timestamp=datetime.now(),
            cache_hits=self.cache_hits,
            cache_misses=self.cache_misses,
            api_requests=self.api_requests,
            api_total_time=self.api_total_time,
            thumbnail_generations=self.thumbnail_generations,
            thumbnail_total_time=self.thumbnail_total_time,
            db_queries=self.db_queries,
            db_total_time=self.db_total_time
        )
        self.snapshots.append(snapshot)
        self.last_snapshot_time = datetime.now()

        logger.debug(f"性能快照已创建: 缓存命中率 {self.get_cache_hit_rate():.1f}%")

    def get_metrics(self) -> Dict:
        """
        获取当前性能指标

        Returns:
            性能指标字典
        """
        return {
            'cache': {
                'hits': self.cache_hits,
                'misses': self.cache_misses,
                'hit_rate': round(self.get_cache_hit_rate(), 2),
                'target': 80.0,
                'status': 'good' if self.get_cache_hit_rate() >= 80 else 'warning'
            },
            'api': {
                'requests': self.api_requests,
                'avg_response_time_ms': round(self.get_avg_api_response_time(), 2),
                'target_ms': 100.0,
             'status': 'good' if self.get_avg_api_response_time() <= 100 else 'warning'
            },
            'thumbnail': {
                'generations': self.thumbnail_generations,
                'avg_time_ms': round(self.get_avg_thumbnail_time(), 2),
                'target_ms': 100.0,
                'status': 'good' if self.get_avg_thumbnail_time() <= 100 else 'warning'
            },
            'database': {
                'queries': self.db_queries,
                'avg_time_ms': round(self.get_avg_db_query_time(), 2)
            },
            'last_snapshot': self.last_snapshot_time.isoformat()
        }

    def get_history(self, minutes: int = 60) -> List[Dict]:
        """
        获取历史性能数据

        Args:
            minutes: 获取最近 N 分钟的数据

        Returns:
            历史快照列表
        """
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        history = []
        for snapshot in self.snapshots:
            if snapshot.timestamp >= cutoff_time:
                total_cache = snapshot.cache_hits + snapshot.cache_misses
                cache_hit_rate = (snapshot.cache_hits / total_cache * 100) if total_cache > 0 else 0

                avg_api_time = (snapshot.api_total_time / snapshot.api_requests * 1000) if snapshot.api_requests > 0 else 0
                avg_thumbnail_time = (snapshot.thumbnail_total_time / snapshot.thumbnail_generations * 1000) if snapshot.thumbnail_generations > 0 else 0

                history.append({
                    'timestamp': snapshot.timestamp.isoformat(),
                    'cache_hit_rate': round(cache_hit_rate, 2),
                    'avg_api_time_ms': round(avg_api_time, 2),
                    'avg_thumbnail_time_ms': round(avg_thumbnail_time, 2),
                    'api_requests': snapshot.api_requests,
                    'thumbnail_generations': snapshot.thumbnail_generations
                })

        return history

    def reset(self):
        """重置所有指标"""
        self.cache_hits = 0
        self.cache_misses = 0
        self.api_requests = 0
        self.api_total_time = 0.0
        self.thumbnail_generations = 0
        self.thumbnail_total_time = 0.0
        self.db_queries = 0
        self.db_total_time = 0.0

        logger.info("性能监控器已重置")


# 全局监控器实例
monitor = PerformanceMonitor()


def track_time(metric_type: str):
    """
    装饰器：跟踪函数执行时间

    Args:
        metric_type: 指标类型 ('api', 'thumbnail', 'db')
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time

                if metric_type == 'api':
                    monitor.record_api_request(duration)
                elif metric_type == 'thumbnail':
                    monitor.record_thumbnail_generation(duration)
                elif metric_type == 'db':
                    monitor.record_db_query(duration)

        return wrapper
    return decorator
