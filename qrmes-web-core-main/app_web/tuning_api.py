"""
性能调优 API - 提供调优建议和配置调整接口
"""

from flask import Blueprint, jsonify, request
import logging

from services.performance_tuner import tuner

logger = logging.getLogger(__name__)

# 创建调优 Blueprint
tuning_bp = Blueprint('tuning', __name__, url_prefix='/api/tuning')


@tuning_bp.route('/analyze', methods=['GET'])
def analyze_performance():
    """
    分析当前性能状态

    Returns:
        性能分析报告
    """
    try:
        analysis = tuner.analyze_performance()
        return jsonify({
            'success': True,
            'analysis': analysis
        })
    except Exception as e:
        logger.error(f"性能分析失败: {e}")
        return jsonify({'error': f'分析失败: {str(e)}'}), 500


@tuning_bp.route('/recommendations', methods=['GET'])
def get_recommendations():
    """
    获取调优建议

    Returns:
        调优建议列表
    """
    try:
        recommendations = tuner.get_tuning_recommendations()

        # 转换为字典格式
        recs_dict = [
            {
                'category': rec.category,
                'current_value': rec.current_value,
                'recommended_value': rec.recommended_value,
                'reason': rec.reason,
                'priority': rec.priority,
                'impact': rec.impact
            }
            for rec in recommendations
        ]

        return jsonify({
            'success': True,
            'recommendations': recs_dict,
            'count': len(recs_dict)
        })
    except Exception as e:
        logger.error(f"获取调优建议失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500


@tuning_bp.route('/apply-cache-ttl', methods=['POST'])
def apply_cache_ttl():
    """
    应用缓存 TTL 配置

    Request Body:
        {
            "photo_metadata": 3600,
            "photo_list": 300,
            "query_result": 600
        }

    Returns:
        应用结果
    """
    try:
        ttl_config = request.get_json()

        if not ttl_config:
            return jsonify({'error': '缺少 TTL 配置'}), 400

        success = tuner.apply_cache_ttl(ttl_config)

        if success:
            return jsonify({
                'success': True,
                'message': 'TTL 配置已应用',
                'config': ttl_config
            })
        else:
            return jsonify({'error': '应用 TTL 配置失败'}), 500

    except Exception as e:
        logger.error(f"应用 TTL 配置失败: {e}")
        return jsonify({'error': f'应用失败: {str(e)}'}), 500


@tuning_bp.route('/health-report', methods=['GET'])
def get_health_report():
    """
    获取完整的健康报告

    Returns:
        包含分析和建议的完整报告
    """
    try:
        analysis = tuner.analyze_performance()
        recommendations = tuner.get_tuning_recommendations()

        recs_dict = [
            {
                'category': rec.category,
                'current_value': rec.current_value,
                'recommended_value': rec.recommended_value,
                'reason': rec.reason,
                'priority': rec.priority,
                'impact': rec.impact
            }
            for rec in recommendations
        ]

        return jsonify({
            'success': True,
            'report': {
                'analysis': analysis,
                'recommendations': recs_dict,
                'summary': {
                    'overall_health': analysis['overall_health']['status'],
                    'health_score': analysis['overall_health']['score'],
                    'high_priority_issues': len([r for r in recommendations if r.priority == 'high']),
                    'total_recommendations': len(recommendations)
                }
            }
        })
    except Exception as e:
        logger.error(f"获取健康报告失败: {e}")
        return jsonify({'error': f'获取失败: {str(e)}'}), 500
