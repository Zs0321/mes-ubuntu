"""
工序配置管理API
提供工序配置的增删改查和排序功能
支持配置变更历史记录和同步
"""

from flask import Blueprint, request, jsonify, session
from functools import wraps
import logging
import re
from pathlib import Path
from typing import List, Tuple
from qrmes_shared_core.project_config_manager import ProjectConfigManager, normalize_sub_checks
from qrmes_shared_core.config_history_manager import ConfigHistoryManager, ChangeType
from qrmes_shared_core.user_management_service import UserManagementService
from qrmes_shared_core.synology_auth_client import SynologyAuthService
from qrmes_shared_core.permission_service import PermissionService, Permission
from qrmes_shared_core.config import config
from qrmes_shared_core.auth import get_user_from_basic_auth  # 统一认证模块
from qrmes_shared_core.data_dir_utils import resolve_data_dir

logger = logging.getLogger(__name__)

# 创建蓝图
process_config_bp = Blueprint('process_config', __name__, url_prefix='/api/process-config')


def _normalize_serial_rule_value(value: str) -> str:
    return re.sub(r"[-_\s]+", "", str(value or "").strip())

# ?????? - ??? mesapp.py ???????????
DATA_DIR = resolve_data_dir(
    nas_local_base_path=config.nas_local_base_path,
    repo_root=Path(__file__).resolve().parent.parent,
    logger=logger,
)

logger.info(f"[工序配置API] 使用数据目录: {DATA_DIR}")
config_manager = ProjectConfigManager(DATA_DIR)
history_manager = ConfigHistoryManager(DATA_DIR / "history")

# 初始化权限服务
try:
    _db_path = DATA_DIR / "web_users.db"
    _synology_auth = SynologyAuthService(
        base_url=config.synology_api_url,
        verify_ssl=config.synology_api_verify_ssl
    )
    _user_service = UserManagementService(_db_path, _synology_auth)
    _permission_service = PermissionService(_user_service)
    logger.info("[工序配置API] ✓ 权限服务初始化完成")
except Exception as e:
    logger.error(f"[工序配置API] ✗ 权限服务初始化失败: {e}", exc_info=True)
    _user_service = None
    _permission_service = None

def require_permission(permission_name):
    """
    权限验证装饰器
    支持两种认证方式：
    1. Flask session（Web 端）
    2. Basic Auth（移动端）
    
    Args:
        permission_name: 权限名称（如 'web:manage_process_config'）
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # 检查权限服务是否已初始化
                if _user_service is None or _permission_service is None:
                    logger.error("权限服务未初始化")
                    return jsonify({
                        'success': False,
                        'error': '权限服务未初始化'
                    }), 500
                
                user = None
                synology_username = None
                
                # 方式1: 检查 Flask session（Web 端）
                if 'user' in session:
                    synology_username = session['user'].get('username')
                    if synology_username:
                        user = _user_service.get_user_by_synology_username(synology_username)
                
                # 方式2: 检查 Basic Auth（移动端）
                if user is None:
                    # 对于只读权限，跳过群晖验证（只检查 Basic Auth 头存在）
                    user = get_user_from_basic_auth(_synology_auth, _user_service, skip_auth_verify=False)
                    if user:
                        synology_username = user.get('synology_username') if isinstance(user, dict) else user.synology_username
                
                # 都没有认证
                if user is None:
                    return jsonify({
                        'success': False,
                        'error': '请先登录'
                    }), 401
                
                # 查找权限枚举
                permission_enum = None
                for perm in Permission:
                    if perm.value == permission_name:
                        permission_enum = perm
                        break
                
                if not permission_enum:
                    logger.error(f"未知的权限: {permission_name}")
                    return jsonify({
                        'success': False,
                        'error': '权限配置错误'
                    }), 500
                
                # 检查权限
                permission_user = user
                if isinstance(user, dict):
                    user_id = str(user.get('id') or '').strip()
                    if user_id:
                        permission_user = _user_service.get_user_by_id(user_id)
                    if permission_user is None:
                        username = str(user.get('synology_username') or user.get('username') or '').strip()
                        if username:
                            permission_user = _user_service.get_user_by_synology_username(username)

                if permission_user is None:
                    logger.warning(f"用户 {synology_username} 未在本地用户管理中启用")
                    return jsonify({
                        'success': False,
                        'error': '用户未在用户管理中启用'
                    }), 401

                if not _permission_service.has_permission(permission_user, permission_enum):
                    logger.warning(f"用户 {synology_username} 没有权限: {permission_name}")
                    return jsonify({
                        'success': False,
                        'error': '权限不足'
                    }), 403
                
                return f(*args, **kwargs)
            except Exception as e:
                logger.error(f"权限检查异常: {e}", exc_info=True)
                return jsonify({
                    'success': False,
                    'error': f'权限检查失败: {str(e)}'
                }), 500
        return decorated_function
    return decorator

def require_admin(f):
    """要求管理员权限的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 与auth.py中的admin_required保持一致
        if 'user' not in session:
            return jsonify({
                'success': False,
                'error': '请先登录'
            }), 401
        
        if session['user'].get('role') != 'admin':
            return jsonify({
                'success': False,
                'error': '权限不足，需要管理员权限'
            }), 403
        return f(*args, **kwargs)
    return decorated_function


def _resolve_request_username() -> str:
    """从 session 或 Basic Auth 头中解析当前用户名。"""
    try:
        if 'user' in session:
            username = (session.get('user') or {}).get('username')
            if isinstance(username, str) and username.strip():
                return username.strip()
    except Exception:
        pass

    try:
        user = get_user_from_basic_auth(_synology_auth, _user_service, skip_auth_verify=False)
        if isinstance(user, dict):
            username = user.get('synology_username') or user.get('username')
            if isinstance(username, str) and username.strip():
                return username.strip()
        username = getattr(user, 'synology_username', None)
        if isinstance(username, str) and username.strip():
            return username.strip()
    except Exception:
        pass

    return ""


def _normalize_group_name(raw) -> str:
    return str(raw or "").strip().lower()


def _get_current_user_groups() -> Tuple[List[dict], bool]:
    """返回当前请求用户所属群组列表（id/name/display_name）及用户是否可解析。"""
    if _user_service is None:
        return [], False

    username = _resolve_request_username()
    if not username:
        return [], False

    local_user = _user_service.get_user_by_synology_username(username)
    if not local_user:
        return [], False

    groups = _user_service.get_groups_for_user(local_user.id) or []
    normalized = []
    seen = set()
    for row in groups:
        if not isinstance(row, dict):
            continue
        name = str(row.get('name') or '').strip()
        if not name:
            continue
        key = _normalize_group_name(name)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({
            'id': str(row.get('id') or '').strip(),
            'name': name,
            'display_name': str(row.get('display_name') or name).strip() or name,
        })
    return normalized, True


@process_config_bp.route('/groups/options', methods=['GET'])
@require_permission('config:read')
def get_groups_options():
    """获取工序“责任部门”可选项（来源：账户群组）。"""
    try:
        if _user_service is None:
            return jsonify({
                'success': True,
                'data': {'groups': []}
            })

        groups = _user_service.get_all_groups(include_member_count=False) or []
        options = []
        seen = set()
        for row in groups:
            if not isinstance(row, dict):
                continue
            name = str(row.get('name') or '').strip()
            if not name:
                continue
            key = _normalize_group_name(name)
            if key in seen:
                continue
            seen.add(key)
            options.append({
                'id': str(row.get('id') or '').strip(),
                'name': name,
                'display_name': str(row.get('display_name') or name).strip() or name,
            })

        options.sort(key=lambda item: _normalize_group_name(item.get('display_name') or item.get('name')))
        return jsonify({
            'success': True,
            'data': {'groups': options}
        })
    except Exception as e:
        logger.error(f"获取群组选项失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@process_config_bp.route(
    '/projects/<project_name>/product-types/<path:product_type_name>/responsibility-departments/<path:department_name>',
    methods=['PUT']
)
@require_permission('web:manage_process_config')
def sync_department_membership(project_name, product_type_name, department_name):
    """按责任部门批量同步工序归属。"""
    try:
        data = request.get_json() or {}
        if not isinstance(data, dict):
            return jsonify({
                'success': False,
                'error': '请求体必须为 JSON 对象'
            }), 400

        process_ids = data.get('processIds', [])
        if not isinstance(process_ids, list):
            return jsonify({
                'success': False,
                'error': 'processIds 必须是数组'
            }), 400

        old_config = config_manager.get_project_config(project_name)
        success = config_manager.sync_process_department_membership(
            project_name=project_name,
            product_type_name=product_type_name,
            department_name=department_name,
            process_ids=process_ids,
        )
        if not success:
            return jsonify({
                'success': False,
                'error': '责任部门批量配置失败，可能产品类型不存在'
            }), 400

        new_config = config_manager.get_project_config(project_name)
        history_manager.record_change(
            project_name=project_name,
            change_type=ChangeType.UPDATED,
            description=f"批量更新责任部门: {department_name} -> 产品类型: {product_type_name}",
            user_id=session.get('username'),
            old_config=old_config,
            new_config=new_config
        )

        return jsonify({
            'success': True,
            'message': '责任部门批量配置成功'
        })
    except Exception as e:
        logger.error(f"责任部门批量配置失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@process_config_bp.route('/me/groups', methods=['GET'])
@require_permission('config:read')
def get_current_user_groups():
    """获取当前登录用户所属群组（用于移动端按责任部门过滤工序）。"""
    try:
        username = _resolve_request_username()
        groups, user_found = _get_current_user_groups()
        return jsonify({
            'success': True,
            'data': {
                'username': username,
                'user_found': user_found,
                'groups': groups,
                'group_names': [str(item.get('name') or '') for item in groups if str(item.get('name') or '').strip()],
            }
        })
    except Exception as e:
        logger.error(f"获取当前用户群组失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@process_config_bp.route('/projects', methods=['GET'])
@require_permission('config:read')
def get_projects():
    """获取所有项目列表"""
    try:
        project_names = config_manager.list_projects(
            include_archived=False,
            include_inactive=False,
        )

        projects = []
        for project_name in project_names:
            config = config_manager.get_project_config(project_name)
            if config:
                projects.append({
                    'name': project_name,
                    'displayName': config.get('projectName', project_name),
                    'description': config.get('description', ''),
                    'version': config.get('configVersion', 1),
                    'updatedAt': config.get('updatedAt'),
                    'processCount': len(config.get('processAttributes', []))
                })
        
        return jsonify({
            'success': True,
            'data': projects
        })
        
    except Exception as e:
        logger.error(f"获取项目列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/resolve-serial-rule', methods=['GET'])
@require_permission('config:read')
def resolve_serial_rule():
    """严格按项目配置中的二维码前缀规则解析序列号。"""
    try:
        serial = str(request.args.get('serial') or '').strip()
        normalized_serial = _normalize_serial_rule_value(serial)
        if not serial:
            return jsonify({
                'success': False,
                'error': '缺少参数: serial'
            }), 400

        project_names = config_manager.list_projects(
            include_archived=False,
            include_inactive=False,
        )

        all_matches = []
        for project_name in project_names:
            config = config_manager.get_project_config(project_name)
            if not config:
                continue

            for product_type in config.get('productTypes', []) or []:
                type_name = str(product_type.get('typeName') or '').strip()
                if not type_name:
                    continue

                raw_rules = product_type.get(
                    'serialRules',
                    product_type.get(
                        'serial_rules',
                        product_type.get('serialPrefixes', product_type.get('serial_prefixes'))
                    )
                )
                rules = raw_rules if isinstance(raw_rules, list) else []
                for raw_prefix in rules:
                    prefix = str(raw_prefix or '').strip()
                    normalized_prefix = _normalize_serial_rule_value(prefix)
                    if not normalized_prefix:
                        continue
                    if normalized_serial.lower().startswith(normalized_prefix.lower()):
                        all_matches.append({
                            'projectName': str(config.get('projectName') or project_name).strip() or project_name,
                            'productType': type_name,
                            'prefix': prefix,
                            'length': len(normalized_prefix)
                        })

        if not all_matches:
            return jsonify({
                'success': True,
                'data': {
                    'serial': serial,
                    'matches': []
                }
            })

        max_length = max(item['length'] for item in all_matches)
        filtered = [item for item in all_matches if item['length'] == max_length]
        filtered.sort(key=lambda item: (item['projectName'], item['productType']))

        deduped = []
        seen = set()
        for item in filtered:
            key = f"{item['projectName'].lower()}|{item['productType'].lower()}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return jsonify({
            'success': True,
            'data': {
                'serial': serial,
                'matches': deduped
            }
        })

    except Exception as e:
        logger.error(f"按二维码前缀规则解析序列号失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/processes', methods=['GET'])
@require_permission('config:read')
def get_project_processes(project_name):
    """获取项目的工序配置（支持按产品类型过滤）"""
    try:
        # 获取查询参数
        product_type = request.args.get('productType')
        
        if product_type:
            # 获取指定产品类型的工序
            processes = config_manager.get_product_type_processes(project_name, product_type)
            return jsonify({
                'success': True,
                'data': {
                    'projectName': project_name,
                    'productType': product_type,
                    'processes': processes
                }
            })
        else:
            # 获取所有工序（向后兼容）
            processes = config_manager.get_process_attributes(project_name)
            return jsonify({
                'success': True,
                'data': {
                    'projectName': project_name,
                    'processes': processes
                }
            })
        
    except Exception as e:
        logger.error(f"获取工序配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/processes', methods=['POST'])
@require_permission('web:manage_process_config')
def add_process(project_name):
    """添加工序（要求指定产品类型）"""
    try:
        data = request.get_json() or {}
        if not isinstance(data, dict):
            return jsonify({
                'success': False,
                'error': '请求体必须为 JSON 对象'
            }), 400
        data["subChecks"] = normalize_sub_checks(data.get("subChecks", data.get("subchecks")))
        data.pop("subchecks", None)
        
        # 验证必需字段
        required_fields = ['name', 'description', 'productType']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'缺少必需字段: {field}'
                }), 400
        
        product_type = data['productType']
        
        # 获取旧配置用于记录变更
        old_config = config_manager.get_project_config(project_name)
        
        # 确保配置有projectName字段（修复旧版本配置）
        if old_config and 'projectName' not in old_config:
            old_config['projectName'] = project_name
            config_manager.save_project_config(project_name, old_config)
            logger.info(f"自动修复配置：添加projectName字段到 {project_name}")
        
        # 添加工序到指定产品类型
        success = config_manager.add_process_to_product_type(
            project_name, 
            product_type, 
            data
        )
        
        if success:
            # 获取新配置
            new_config = config_manager.get_project_config(project_name)
            
            # 记录变更历史
            history_manager.record_change(
                project_name=project_name,
                change_type=ChangeType.UPDATED,
                description=f"添加工序: {data.get('name')} 到产品类型: {product_type}",
                user_id=session.get('username'),
                old_config=old_config,
                new_config=new_config
            )
            
            return jsonify({
                'success': True,
                'message': '工序添加成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '工序添加失败，可能产品类型不存在'
            }), 400
            
    except Exception as e:
        logger.error(f"添加工序失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/processes/<process_id>', methods=['PUT'])
@require_permission('web:manage_process_config')
def update_process(project_name, process_id):
    """更新工序（支持产品类型）"""
    try:
        data = request.get_json() or {}
        if not isinstance(data, dict):
            return jsonify({
                'success': False,
                'error': '请求体必须为 JSON 对象'
            }), 400
        if "subChecks" in data or "subchecks" in data:
            data["subChecks"] = normalize_sub_checks(data.get("subChecks", data.get("subchecks")))
            data.pop("subchecks", None)
        
        # 验证必需字段
        if 'productType' not in data:
            return jsonify({
                'success': False,
                'error': '缺少必需字段: productType'
            }), 400
        
        product_type = data['productType']
        
        # 获取旧配置用于记录变更
        old_config = config_manager.get_project_config(project_name)
        
        # 更新工序
        success = config_manager.update_process_in_product_type(
            project_name, 
            product_type, 
            process_id, 
            data
        )
        
        if success:
            # 获取新配置
            new_config = config_manager.get_project_config(project_name)
            
            # 记录变更历史
            history_manager.record_change(
                project_name=project_name,
                change_type=ChangeType.UPDATED,
                description=f"更新工序: {data.get('name', process_id)} 在产品类型: {product_type}",
                user_id=session.get('username'),
                old_config=old_config,
                new_config=new_config
            )
            
            return jsonify({
                'success': True,
                'message': '工序更新成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '工序更新失败，可能工序或产品类型不存在'
            }), 404
            
    except Exception as e:
        logger.error(f"更新工序失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/processes/<process_id>', methods=['DELETE'])
@require_permission('web:manage_process_config')
def delete_process(project_name, process_id):
    """删除工序（支持产品类型）"""
    try:
        # 获取查询参数
        product_type = request.args.get('productType')
        
        if not product_type:
            return jsonify({
                'success': False,
                'error': '缺少必需参数: productType'
            }), 400
        
        # 获取旧配置用于记录变更
        old_config = config_manager.get_project_config(project_name)
        
        # 删除工序
        success = config_manager.delete_process_from_product_type(
            project_name, 
            product_type, 
            process_id
        )
        
        if success:
            # 获取新配置
            new_config = config_manager.get_project_config(project_name)
            
            # 记录变更历史
            history_manager.record_change(
                project_name=project_name,
                change_type=ChangeType.UPDATED,
                description=f"删除工序: {process_id} 从产品类型: {product_type}",
                user_id=session.get('username'),
                old_config=old_config,
                new_config=new_config
            )
            
            return jsonify({
                'success': True,
                'message': '工序删除成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '工序删除失败，可能工序或产品类型不存在'
            }), 404
            
    except Exception as e:
        logger.error(f"删除工序失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/processes/reorder', methods=['POST'])
@require_permission('web:manage_process_config')
def reorder_processes(project_name):
    """重新排序工序（支持产品类型）"""
    try:
        data = request.get_json()
        
        # 验证必需字段
        if 'processOrders' not in data:
            return jsonify({
                'success': False,
                'error': '缺少processOrders字段'
            }), 400
        
        if 'productType' not in data:
            return jsonify({
                'success': False,
                'error': '缺少productType字段'
            }), 400
        
        product_type = data['productType']
        
        # 获取旧配置用于记录变更
        old_config = config_manager.get_project_config(project_name)
        
        # 重新排序工序
        success = config_manager.reorder_processes_in_product_type(
            project_name, 
            product_type, 
            data['processOrders']
        )
        
        if success:
            # 获取新配置
            new_config = config_manager.get_project_config(project_name)
            
            # 记录变更历史
            history_manager.record_change(
                project_name=project_name,
                change_type=ChangeType.UPDATED,
                description=f"重新排序产品类型 {product_type} 的工序",
                user_id=session.get('username'),
                old_config=old_config,
                new_config=new_config
            )
            
            return jsonify({
                'success': True,
                'message': '工序排序更新成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '工序排序更新失败，可能产品类型不存在'
            }), 400
            
    except Exception as e:
        logger.error(f"工序排序失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/config', methods=['GET'])
@require_permission('config:read')
def get_project_config(project_name):
    """获取完整项目配置"""
    try:
        config = config_manager.get_project_config(project_name)
        
        if config:
            return jsonify({
                'success': True,
                'data': config
            })
        else:
            return jsonify({
                'success': False,
                'error': '项目配置不存在'
            }), 404
            
    except Exception as e:
        logger.error(f"获取项目配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/config', methods=['POST'])
@require_admin
def save_project_config(project_name):
    """保存完整项目配置"""
    try:
        existing_config = config_manager.get_project_config(project_name)
        if not existing_config:
            return jsonify({
                'success': False,
                'error': '项目配置不存在，禁止通过保存接口创建新配置'
            }), 404

        data = request.get_json()
        
        # 验证配置结构
        if not config_manager.validate_config_structure(data):
            return jsonify({
                'success': False,
                'error': '配置结构验证失败'
            }), 400
        
        # 保存配置
        success = config_manager.save_project_config(project_name, data)
        
        if success:
            return jsonify({
                'success': True,
                'message': '项目配置保存成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '项目配置保存失败'
            }), 500
            
    except Exception as e:
        logger.error(f"保存项目配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/export', methods=['GET'])
@require_permission('config:read')
def export_project_config(project_name):
    """导出项目配置"""
    try:
        config = config_manager.get_project_config(project_name)
        
        if not config:
            return jsonify({
                'success': False,
                'error': '项目配置不存在'
            }), 404
        
        # 添加导出元数据
        export_data = {
            'exportedAt': config_manager.datetime.now().isoformat(),
            'exportedBy': session.get('username', 'unknown'),
            'originalProject': project_name,
            'config': config
        }
        
        return jsonify({
            'success': True,
            'data': export_data
        })
        
    except Exception as e:
        logger.error(f"导出项目配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/import', methods=['POST'])
@require_admin
def import_project_config(project_name):
    """导入项目配置"""
    try:
        existing_config = config_manager.get_project_config(project_name)
        if not existing_config:
            return jsonify({
                'success': False,
                'error': '项目配置不存在，禁止通过导入接口创建新配置'
            }), 404

        data = request.get_json()
        
        # 检查是否是导出格式
        if 'config' in data:
            config = data['config']
        else:
            config = data
        
        # 验证配置结构
        if not config_manager.validate_config_structure(config):
            return jsonify({
                'success': False,
                'error': '导入的配置结构无效'
            }), 400
        
        # 更新项目名称
        config['projectName'] = project_name
        config['importedAt'] = config_manager.datetime.now().isoformat()
        config['importedBy'] = session.get('username', 'unknown')
        
        # 项目已存在（上面已校验），先备份
        config_manager.create_config_backup(project_name)
        
        # 保存导入的配置
        success = config_manager.save_project_config(project_name, config)
        
        if success:
            return jsonify({
                'success': True,
                'message': '项目配置导入成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '项目配置导入失败'
            }), 500
            
    except Exception as e:
        logger.error(f"导入项目配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/versions', methods=['GET'])
@require_permission('config:read')
def get_config_versions(project_name):
    """获取配置版本历史"""
    try:
        versions = config_manager.get_config_versions(project_name)
        
        return jsonify({
            'success': True,
            'data': {
                'projectName': project_name,
                'versions': versions
            }
        })
        
    except Exception as e:
        logger.error(f"获取配置版本失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/versions/<int:version_num>/restore', methods=['POST'])
@require_admin
def restore_config_version(project_name, version_num):
    """恢复指定版本的配置"""
    try:
        success = config_manager.restore_config_version(project_name, version_num)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'成功恢复到版本 {version_num}'
            })
        else:
            return jsonify({
                'success': False,
                'error': '版本恢复失败，可能版本不存在'
            }), 404
            
    except Exception as e:
        logger.error(f"恢复配置版本失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects', methods=['POST'])
@require_admin
def create_project():
    """创建新项目"""
    try:
        data = request.get_json()
        
        if 'projectName' not in data:
            return jsonify({
                'success': False,
                'error': '缺少项目名称'
            }), 400
        
        project_name = data['projectName']
        
        # 检查项目是否已存在
        if config_manager.get_project_config(project_name):
            return jsonify({
                'success': False,
                'error': '项目已存在'
            }), 409
        
        # 创建项目配置
        success = config_manager.create_project_config(project_name)
        
        if success:
            return jsonify({
                'success': True,
                'message': '项目创建成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '项目创建失败'
            }), 500
            
    except Exception as e:
        logger.error(f"创建项目失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/migrate', methods=['POST'])
@require_admin
def migrate_project_config(project_name):
    """迁移项目配置到新版本结构"""
    try:
        data = request.get_json() or {}
        auto_backup = data.get('autoBackup', True)
        
        # 执行迁移
        result = config_manager.migrate_legacy_config(project_name, auto_backup)
        
        if result['success']:
            # 记录迁移事件
            if result['migrated']:
                history_manager.record_change(
                    project_name=project_name,
                    change_type=ChangeType.UPDATED,
                    description=f"配置迁移到版本2.0: {result['message']}",
                    user_id=session.get('username'),
                    old_config=None,
                    new_config=config_manager.get_project_config(project_name)
                )
            
            return jsonify({
                'success': True,
                'message': result['message'],
                'migrated': result['migrated'],
                'backupFile': result.get('backup_file'),
                'stats': result['stats'],
                'warnings': result['warnings']
            })
        else:
            return jsonify({
                'success': False,
                'error': result['message'],
                'errors': result['errors'],
                'warnings': result['warnings']
            }), 400
            
    except Exception as e:
        logger.error(f"迁移项目配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/validate-migration', methods=['GET'])
@require_permission('config:read')
def validate_project_migration(project_name):
    """验证项目配置迁移的完整性"""
    try:
        validation_result = config_manager.validate_migration(project_name)
        
        return jsonify({
            'success': True,
            'data': validation_result
        })
        
    except Exception as e:
        logger.error(f"验证配置迁移失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/history', methods=['GET'])
@require_permission('config:read')
def get_config_history(project_name):
    """获取配置变更历史"""
    try:
        limit = request.args.get('limit', 50, type=int)
        change_type = request.args.get('changeType')
        
        # 转换变更类型
        change_type_enum = None
        if change_type:
            try:
                change_type_enum = ChangeType(change_type)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': f'无效的变更类型: {change_type}'
                }), 400
        
        history = history_manager.get_change_history(
            project_name=project_name,
            limit=limit,
            change_type=change_type_enum
        )
        
        return jsonify({
            'success': True,
            'data': {
                'projectName': project_name,
                'history': history
            }
        })
        
    except Exception as e:
        logger.error(f"获取配置历史失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/history/<change_id>', methods=['GET'])
@require_permission('config:read')
def get_change_detail(project_name, change_id):
    """获取变更详情"""
    try:
        change_detail = history_manager.get_change_detail(project_name, change_id)
        
        if change_detail:
            return jsonify({
                'success': True,
                'data': change_detail
            })
        else:
            return jsonify({
                'success': False,
                'error': '变更记录不存在'
            }), 404
            
    except Exception as e:
        logger.error(f"获取变更详情失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/sync/status', methods=['GET'])
@require_permission('config:read')
def get_sync_status(project_name):
    """获取同步状态"""
    try:
        sync_history = history_manager.get_sync_history(project_name, limit=10)
        statistics = history_manager.get_project_statistics(project_name)
        
        return jsonify({
            'success': True,
            'data': {
                'projectName': project_name,
                'syncHistory': sync_history,
                'statistics': statistics
            }
        })
        
    except Exception as e:
        logger.error(f"获取同步状态失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/sync/trigger', methods=['POST'])
@require_admin
def trigger_sync(project_name):
    """触发配置同步"""
    try:
        data = request.get_json() or {}
        sync_type = data.get('syncType', 'manual')  # manual, auto, scheduled
        
        # 记录同步触发事件
        sync_id = history_manager.record_sync_event(
            project_name=project_name,
            sync_type=sync_type,
            status='triggered',
            details={
                'triggeredBy': session.get('username'),
                'triggerTime': history_manager.datetime.now().isoformat()
            }
        )
        
        # 这里可以添加实际的同步逻辑
        # 例如：通知移动应用更新配置、推送到其他服务器等
        
        # 模拟同步成功
        history_manager.record_sync_event(
            project_name=project_name,
            sync_type=sync_type,
            status='success',
            details={
                'syncId': sync_id,
                'completedAt': history_manager.datetime.now().isoformat()
            }
        )
        
        return jsonify({
            'success': True,
            'message': '同步已触发',
            'syncId': sync_id
        })
        
    except Exception as e:
        logger.error(f"触发同步失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/compare/<int:version1>/<int:version2>', methods=['GET'])
@require_permission('config:read')
def compare_config_versions(project_name, version1, version2):
    """比较两个配置版本的差异"""
    try:
        # 获取两个版本的配置
        versions = config_manager.get_config_versions(project_name)
        
        config1 = None
        config2 = None
        
        for version in versions:
            if version['version'] == version1:
                config1 = version['config']
            elif version['version'] == version2:
                config2 = version['config']
        
        if not config1 or not config2:
            return jsonify({
                'success': False,
                'error': '指定的版本不存在'
            }), 404
        
        # 比较配置差异
        differences = history_manager.compare_configs(config1, config2)
        
        return jsonify({
            'success': True,
            'data': {
                'projectName': project_name,
                'version1': version1,
                'version2': version2,
                'differences': differences
            }
        })
        
    except Exception as e:
        logger.error(f"比较配置版本失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/projects/<project_name>/statistics', methods=['GET'])
@require_permission('config:read')
def get_project_statistics(project_name):
    """获取项目统计信息"""
    try:
        statistics = history_manager.get_project_statistics(project_name)
        
        return jsonify({
            'success': True,
            'data': statistics
        })
        
    except Exception as e:
        logger.error(f"获取项目统计信息失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@process_config_bp.route('/maintenance/cleanup', methods=['POST'])
@require_admin
def cleanup_old_records():
    """清理旧记录"""
    try:
        data = request.get_json() or {}
        days_to_keep = data.get('daysToKeep', 90)
        
        # 清理配置备份
        config_manager._cleanup_old_backups("*", keep_count=10)
        
        # 清理历史记录
        history_manager.cleanup_old_records(days_to_keep)
        
        return jsonify({
            'success': True,
            'message': f'已清理 {days_to_keep} 天前的旧记录'
        })
        
    except Exception as e:
        logger.error(f"清理旧记录失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# 错误处理
@process_config_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': '资源不存在'
    }), 404

@process_config_bp.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': '服务器内部错误'
    }), 500
