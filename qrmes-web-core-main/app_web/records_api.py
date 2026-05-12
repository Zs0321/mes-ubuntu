"""记录查询、导出、删除 API"""
from flask import Blueprint, request, jsonify, send_file, render_template
from pathlib import Path
import logging
from qrmes_shared_core.auth import login_required, get_current_user

logger = logging.getLogger(__name__)

records_bp = Blueprint('records', __name__)

# 注意：这个蓝图将在 mesapp.py 中注册
# 实际的路由实现将从 mesapp.py 移动过来

@records_bp.route('/records')
@login_required
def records_page():
    """记录管理页面"""
    from mesapp import DataManager
    projects_list = DataManager.get_projects()
    user = get_current_user()
    return render_template('records.html', projects=projects_list, user=user)

@records_bp.route('/api/records', methods=['GET'])
@login_required
def api_get_records():
    """查询记录列表（只查询 H2 数据库）"""
    from mesapp import h2_db_manager, init_h2_service, logger as mesapp_logger
    
    # 参数解析
    project_name = request.args.get('project')
    product_serial = request.args.get('serial')
    operator = request.args.get('operator')
    date_from = request.args.get('dateFrom')
    date_to = request.args.get('dateTo')
    
    # 处理空字符串
    if project_name == '':
        project_name = None
    
    try:
        # 只查询 H2 数据库
        if not h2_db_manager:
            init_h2_service()
        
        if h2_db_manager:
            records = h2_db_manager.query_records(
                project_name=project_name,
                product_serial=product_serial,
                operator=operator,
                date_from=date_from,
                date_to=date_to
            )
            
            return jsonify({
                "success": True,
                "records": records,
                "count": len(records),
                "dataSource": "h2"
            })
        else:
            return jsonify({
                "success": False,
                "message": "H2数据库不可用",
                "records": [],
                "count": 0
            }), 503
            
    except Exception as e:
        mesapp_logger.error(f"查询记录失败: {e}")
        return jsonify({
            "success": False,
            "message": f"查询失败: {str(e)}",
            "records": [],
            "count": 0
        }), 500

@records_bp.route('/api/records/delete/<product_serial>', methods=['DELETE'])
@login_required
def api_delete_record(product_serial: str):
    """删除记录"""
    from mesapp import h2_db_manager, logger as mesapp_logger
    
    try:
        if h2_db_manager:
            success = h2_db_manager.delete_record(product_serial)
            if success:
                return jsonify({
                    "success": True,
                    "message": f"记录 {product_serial} 已删除"
                })
            else:
                return jsonify({
                    "success": False,
                    "message": "删除失败"
                }), 404
        else:
            return jsonify({
                "success": False,
                "message": "H2数据库不可用"
            }), 503
            
    except Exception as e:
        mesapp_logger.error(f"删除记录失败: {e}")
        return jsonify({
            "success": False,
            "message": f"删除失败: {str(e)}"
        }), 500

@records_bp.route('/api/records/export', methods=['POST'])
@login_required
def api_export_records():
    """导出记录"""
    from mesapp import h2_db_manager, logger as mesapp_logger
    import tempfile
    from datetime import date
    
    try:
        data = request.get_json()
        project_name = data.get('project')
        product_serial = data.get('serial')
        operator = data.get('operator')
        date_from = data.get('dateFrom')
        date_to = data.get('dateTo')
        
        # 查询记录
        if h2_db_manager:
            records = h2_db_manager.query_records(
                project_name=project_name,
                product_serial=product_serial,
                operator=operator,
                date_from=date_from,
                date_to=date_to
            )
            
            if not records:
                return jsonify({
                    "success": False,
                    "message": "没有找到符合条件的记录"
                }), 404
            
            # 导出到 Excel
            output_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
            from mesapp import DataManager
            if DataManager.export_to_excel(records, output_file.name):
                return send_file(
                    output_file.name,
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    as_attachment=True,
                    download_name=f"扫描记录_{date.today().isoformat()}.xlsx"
                )
            else:
                return jsonify({
                    "success": False,
                    "message": "导出失败"
                }), 500
        else:
            return jsonify({
                "success": False,
                "message": "H2数据库不可用"
            }), 503
            
    except Exception as e:
        mesapp_logger.error(f"导出记录失败: {e}")
        return jsonify({
            "success": False,
            "message": f"导出失败: {str(e)}"
        }), 500

@records_bp.route('/api/stats/total_records', methods=['GET'])
@login_required
def api_get_total_records():
    """获取记录总数统计"""
    from mesapp import h2_db_manager
    
    try:
        if h2_db_manager:
            stats = h2_db_manager.get_stats()
            return jsonify({
                "success": True,
                "total": stats.get('total_records', 0)
            })
        else:
            return jsonify({
                "success": True,
                "total": 0
            })
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
