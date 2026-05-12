"""
监控 API - 性能指标查询端点
"""

from flask import Blueprint, jsonify, request
import logging

from services.performance_monitor import monitor

logger = logging.getLogger(__name__)

# 创建监控 Blueprint
monitoring_bp = Blueprint('monitoring', __name__, url_prefix='/api/monitoring')


@monitoring_bp.route('/metrics', methods=['GET'])
def get_metrics():
    """
    获取当前性能指标

    Returns:
        JSON 格式的性能指标
    """
    try:
        metrics = monitor.get_metrics()
        return jsonify({
            'success': True,
            'metrics': metrics
        })
    except Exception as e:
        logger.error(f"获取性能指标失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500


@monitoring_bp.route('/history', methods=['GET'])
def get_history():
    """
    获取历史性能数据

    Query Parameters:
        - minutes: 获取最近 N 分钟的数据（默认 60）

    Returns:
        JSON 格式的历史数据
    """
    try:
        minutes = request.args.get('minutes', 60, type=int)
        history = monitor.get_history(minutes=minutes)

        return jsonify({
            'success': True,
            'history': history,
            'count': len(history)
        })
    except Exception as e:
        logger.error(f"获取历史数据失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500


@monitoring_bp.route('/snapshot', methods=['POST'])
def create_snapshot():
    """
    创建性能快照

    Returns:
        成功消息
    """
    try:
        monitor.take_snapshot()
        return jsonify({
            'success': True,
            'message': '快照已创建'
        })
    except Exception as e:
        logger.error(f"创建快照失败: {e}")
        return jsonify({'error': f'创建失败: {str(e)}'}), 500


@monitoring_bp.route('/reset', methods=['POST'])
def reset_metrics():
    """
    重置所有性能指标

    Returns:
        成功消息
    """
    try:
        monitor.reset()
        return jsonify({
            'success': True,
            'message': '指标已重置'
        })
    except Exception as e:
        logger.error(f"重置指标失败: {e}")
        return jsonify({'error': f'重置失败: {str(e)}'}), 500


@monitoring_bp.route('/health', methods=['GET'])
def health_check():
    """
    健康检查 - 验证所有指标是否达标

    Returns:
        健康状态和详细信息
    """
    try:
        metrics = monitor.get_metrics()

        # 检查各项指标是否达标
        cache_ok = metrics['cache']['hit_rate'] >= metrics['cache']['target']
        api_ok = metrics['api']['avg_response_time_ms'] <= metrics['api']['target_ms']
        thumbnail_ok = metrics['thumbnail']['avg_time_ms'] <= metrics['thumbnail']['target_ms']

        all_ok = cache_ok and api_ok and thumbnail_ok

        return jsonify({
            'success': True,
            'healthy': all_ok,
            'checks': {
                'cache_hit_rate': {
                    'ok': cache_ok,
                    'current': metrics['cache']['hit_rate'],
                    'target': metrics['cache']['target']
                },
                'api_response_time': {
                    'ok': api_ok,
                    'current': metrics['api']['avg_response_time_ms'],
                    'target': metrics['api']['target_ms']
                },
                'thumbnail_generation': {
                    'ok': thumbnail_ok,
                    'current': metrics['thumbnail']['avg_time_ms'],
                    'target': metrics['thumbnail']['target_ms']
                }
            }
        })
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return jsonify({'error': f'检查失败: {str(e)}'}), 500
