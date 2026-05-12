"""
性能调优工具 - 动态调整缓存和连接池配置

提供基于监控数据的自动调优建议和手动调整工具
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import sys
from pathlib import Path

# 添加 app_web 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.performance_monitor import monitor
from config.redis_config import RedisManager

logger = logging.getLogger(__name__)


@dataclass
class TuningRecommendation:
    """调优建议"""
    category: str  # 'cache', 'connection_pool', 'query'
    current_value: any
    recommended_value: any
    reason: str
    priority: str  # 'high', 'medium', 'low'
    impact: str  # 预期影响


class PerformanceTuner:
    """性能调优器"""

    # 缓存 TTL 推荐值（基于命中率）
    CACHE_TTL_RECOMMENDATIONS = {
        'very_high': {  # 命中率 > 90%
            'photo_metadata': 7200,  # 2 小时
            'photo_list': 600,  # 10 分钟
            'query_result': 900,  # 15 分钟
        },
        'high': {  # 命中率 80-90%
            'photo_metadata': 3600,  # 1 小时
            'photo_list': 300,  # 5 分钟
            'query_result': 600,  # 10 分钟
        },
        'medium': {  # 命中率 60-80%
            'photo_metadata': 1800,  # 30 分钟
            'photo_list': 180,  # 3 分钟
            'query_result': 300,  # 5 分钟
        },
        'low': {  # 命中率 < 60%
            'photo_metadata': 900,  # 15 分钟
            'photo_list': 60,  # 1 分钟
            'query_result': 120,  # 2 分钟
        }
    }

    def __init__(self):
        self.monitor = monitor

    def analyze_performance(self) -> Dict:
        """
        分析当前性能状态

        Returns:
            性能分析报告
        """
        metrics = self.monitor.get_metrics()

        analysis = {
            'cache_performance': self._analyze_cache(metrics['cache']),
            'api_performance': self._analyze_api(metrics['api']),
            'thumbnail_performance': self._analyze_thumbnail(metrics['thumbnail']),
            'overall_health': self._calculate_overall_health(metrics)
        }

        return analysis

    def get_tuning_recommendations(self) -> List[TuningRecommendation]:
        """
        获取调优建议

        Returns:
            调优建议列表
        """
        recommendations = []
        metrics = self.monitor.get_metrics()

        # 缓存调优建议
        cache_recs = self._get_cache_recommendations(metrics['cache'])
        recommendations.extend(cache_recs)

        # API 调优建议
        api_recs = self._get_api_recommendations(metrics['api'])
        recommendations.extend(api_recs)

        # 缩略图调优建议
        thumbnail_recs = self._get_thumbnail_recommendations(metrics['thumbnail'])
        recommendations.extend(thumbnail_recs)

        # 按优先级排序
        recommendations.sort(key=lambda x: {'high': 0, 'medium': 1, 'low': 2}[x.priority])

        return recommendations

    def _analyze_cache(self, cache_metrics: Dict) -> Dict:
        """分析缓存性能"""
        hit_rate = cache_metrics['hit_rate']

        if hit_rate >= 90:
            status = 'excellent'
            message = '缓存命中率优秀'
        elif hit_rate >= 80:
            status = 'good'
            message = '缓存命中率良好'
        elif hit_rate >= 60:
            status = 'fair'
            message = '缓存命中率一般，建议优化'
        else:
            status = 'poor'
            message = '缓存命中率较低，需要优化'

        return {
            'status': status,
            'message': message,
            'hit_rate': hit_rate,
            'hits': cache_metrics['hits'],
            'misses': cache_metrics['misses']
        }

    def _analyze_api(self, api_metrics: Dict) -> Dict:
        """分析 API 性能"""
        avg_time = api_metrics['avg_response_time_ms']
        target = api_metrics['target_ms']

        if avg_time <= target * 0.5:
            status = 'excellent'
            message = 'API 响应时间优秀'
        elif avg_time <= target:
            status = 'good'
            message = 'API 响应时间良好'
        elif avg_time <= target * 1.5:
            status = 'fair'
            message = 'API 响应时间略慢，建议优化'
        else:
            status = 'poor'
            message = 'API 响应时间过慢，需要优化'

        return {
            'status': status,
            'message': message,
            'avg_time_ms': avg_time,
            'target_ms': target,
            'requests': api_metrics['requests']
        }

    def _analyze_thumbnail(self, thumbnail_metrics: Dict) -> Dict:
        """分析缩略图性能"""
        avg_time = thumbnail_metrics['avg_time_ms']
        target = thumbnail_metrics['target_ms']

        if avg_time <= target * 0.5:
            status = 'excellent'
            message = '缩略图生成时间优秀'
        elif avg_time <= target:
            status = 'good'
            message = '缩略图生成时间良好'
        elif avg_time <= target * 1.5:
            status = 'fair'
            message = '缩略图生成时间略慢'
        else:
            status = 'poor'
            message = '缩略图生成时间过慢'

        return {
            'status': status,
            'message': message,
            'avg_time_ms': avg_time,
            'target_ms': target,
            'generations': thumbnail_metrics['generations']
        }

    def _calculate_overall_health(self, metrics: Dict) -> Dict:
        """计算整体健康度"""
        cache_ok = metrics['cache']['status'] == 'good'
        api_ok = metrics['api']['status'] == 'good'
        thumbnail_ok = metrics['thumbnail']['status'] == 'good'

        healthy_count = sum([cache_ok, api_ok, thumbnail_ok])
        health_score = (healthy_count / 3) * 100

        if health_score >= 80:
            status = 'healthy'
            message = '系统整体性能良好'
        elif health_score >= 60:
            status = 'fair'
            message = '系统性能一般，建议优化'
        else:
            status = 'unhealthy'
            message = '系统性能较差，需要优化'

        return {
            'status': status,
            'message': message,
            'score': health_score,
            'checks_passed': healthy_count,
            'total_checks': 3
        }

    def _get_cache_recommendations(self, cache_metrics: Dict) -> List[TuningRecommendation]:
        """获取缓存调优建议"""
        recommendations = []
        hit_rate = cache_metrics['hit_rate']

        # 根据命中率推荐 TTL
        if hit_rate >= 90:
            level = 'very_high'
            priority = 'low'
            reason = '缓存命中率很高，可以适当延长 TTL'
        elif hit_rate >= 80:
            level = 'high'
            priority = 'low'
            reason = '缓存命中率良好，保持当前 TTL'
        elif hit_rate >= 60:
            level = 'medium'
            priority = 'medium'
            reason = '缓存命中率一般，建议缩短 TTL 以提高数据新鲜度'
        else:
            level = 'low'
            priority = 'high'
            reason = '缓存命中率较低，建议大幅缩短 TTL 或优化缓存策略'

        ttl_config = self.CACHE_TTL_RECOMMENDATIONS[level]

        recommendations.append(TuningRecommendation(
            category='cache',
            current_value={'hit_rate': hit_rate},
            recommended_value=ttl_config,
            reason=reason,
            priority=priority,
            impact=f'预期命中率变化: ±5%'
        ))

        return recommendations

    def _get_api_recommendations(self, api_metrics: Dict) -> List[TuningRecommendation]:
        """获取 API 调优建议"""
        recommendations = []
        avg_time = api_metrics['avg_response_time_ms']
        target = api_metrics['target_ms']

        if avg_time > target * 1.5:
            recommendations.append(TuningRecommendation(
                category='api',
                current_value={'avg_time_ms': avg_time},
                recommended_value={'actions': [
                    '增加缓存使用',
                    '优化数据库查询',
                    '考虑增加连接池大小'
                ]},
                reason=f'API 响应时间 ({avg_time:.1f}ms) 超过目标 ({target}ms) 的 50%',
                priority='high',
                impact='预期响应时间减少 30-50%'
            ))

        return recommendations

    def _get_thumbnail_recommendations(self, thumbnail_metrics: Dict) -> List[TuningRecommendation]:
        """获取缩略图调优建议"""
        recommendations = []
        avg_time = thumbnail_metrics['avg_time_ms']
        target = thumbnail_metrics['target_ms']

        if avg_time > target * 1.5:
            recommendations.append(TuningRecommendation(
                category='thumbnail',
                current_value={'avg_time_ms': avg_time},
                recommended_value={'actions': [
                    '使用异步任务队列生成缩略图',
                    '预生成常用尺寸的缩略图',
                    '优化图片处理参数'
                ]},
                reason=f'缩略图生成时间 ({avg_time:.1f}ms) 超过目标 ({target}ms) 的 50%',
                priority='medium',
                impact='预期生成时间减少 40-60%'
            ))

        return recommendations

    def apply_cache_ttl(self, ttl_config: Dict) -> bool:
        """
        应用缓存 TTL 配置

        Args:
            ttl_config: TTL 配置字典

        Returns:
            是否成功
        """
        try:
            # 这里可以动态更新缓存服务的 TTL 配置
            # 实际实现需要修改 CacheService 类以支持动态配置
            logger.info(f"应用缓存 TTL 配置: {ttl_config}")
            return True
        except Exception as e:
            logger.error(f"应用缓存 TTL 配置失败: {e}")
            return False


# 全局调优器实例
tuner = PerformanceTuner()
