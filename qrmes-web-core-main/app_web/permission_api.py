"""
权限相关API端点
提供前端权限控制所需的用户权限信息
"""

import logging
from flask import Blueprint, jsonify, session, request
from typing import Dict, List, Any

from qrmes_shared_core.user_management_service import UserManagementService, LocalUser, UserRole
from qrmes_shared_core.permission_service import PermissionService, Permission

logger = logging.getLogger(__name__)

def create_permission_api(user_service: UserManagementService, permission_service: PermissionService) -> Blueprint:
    """
    创建权限API蓝图
    
    Args:
        user_service: 用户管理服务实例
        permission_service: 权限服务实例
        
    Returns:
        Flask蓝图对象
    """
    
    permission_api = Blueprint('permission_api', __name__, url_prefix='/api')
    
    def get_current_user() -> LocalUser:
        """获取当前登录用户"""
        if 'user_id' not in session:
            return None
        
        user_id = session['user_id']
        return user_service.get_user_by_id(user_id)
    
    @permission_api.route('/user/current-permissions', methods=['GET'])
    def get_current_user_permissions():
        """
        获取当前用户的权限信息
        
        Returns:
            JSON响应包含用户信息和权限列表
        """
        try:
            user = get_current_user()
            
            if not user:
                return jsonify({
                    'success': False,
                    'message': '用户未登录',
                    'error_code': 'NOT_AUTHENTICATED'
                }), 401
            
            # 获取用户权限
            user_permissions = permission_service.get_user_permissions(user)
            permissions_list = [perm.value for perm in user_permissions]
            
            # 构建响应数据
            response_data = {
                'success': True,
                'user': {
                    'id': user.id,
                    'synology_username': user.synology_username,
                    'display_name': user.display_name,
                    'role': user.role.value,
                    'last_login_at': user.last_login_at,
                    'email': user.email
                },
                'permissions': permissions_list,
                'is_admin': user.role == UserRole.ADMIN
            }
            
            logger.debug(f"返回用户权限信息: {user.synology_username}")
            return jsonify(response_data)
            
        except Exception as e:
            logger.error(f"获取用户权限信息失败: {e}")
            return jsonify({
                'success': False,
                'message': '获取权限信息失败',
                'error_code': 'PERMISSION_FETCH_ERROR'
            }), 500
    
    @permission_api.route('/user/check-permission', methods=['POST'])
    def check_user_permission():
        """
        检查用户是否具有特定权限
        
        Request Body:
            {
                "permission": "web:delete_records"
            }
            
        Returns:
            JSON响应包含权限检查结果
        """
        try:
            user = get_current_user()
            
            if not user:
                return jsonify({
                    'success': False,
                    'message': '用户未登录',
                    'error_code': 'NOT_AUTHENTICATED'
                }), 401
            
            data = request.get_json()
            if not data or 'permission' not in data:
                return jsonify({
                    'success': False,
                    'message': '缺少权限参数',
                    'error_code': 'MISSING_PERMISSION_PARAMETER'
                }), 400
            
            permission_str = data['permission']
            
            # 查找对应的权限枚举
            permission_enum = None
            for perm in Permission:
                if perm.value == permission_str:
                    permission_enum = perm
                    break
            
            if not permission_enum:
                return jsonify({
                    'success': False,
                    'message': f'未知权限: {permission_str}',
                    'error_code': 'UNKNOWN_PERMISSION'
                }), 400
            
            # 检查权限
            has_permission = permission_service.has_permission(user, permission_enum)
            
            return jsonify({
                'success': True,
                'has_permission': has_permission,
                'permission': permission_str,
                'user_role': user.role.value
            })
            
        except Exception as e:
            logger.error(f"检查用户权限失败: {e}")
            return jsonify({
                'success': False,
                'message': '权限检查失败',
                'error_code': 'PERMISSION_CHECK_ERROR'
            }), 500
    
    @permission_api.route('/user/permissions-list', methods=['GET'])
    def get_permissions_list():
        """
        获取所有可用权限列表
        
        Returns:
            JSON响应包含权限列表和描述
        """
        try:
            permissions_info = []
            
            # 权限描述映射
            permission_descriptions = {
                Permission.WEB_VIEW_RECORDS: '查看Web后台记录',
                Permission.WEB_MODIFY_RECORDS: '修改Web后台记录',
                Permission.WEB_DELETE_RECORDS: '删除Web后台记录',
                Permission.WEB_VIEW_DOCUMENTS: '查看PDF文档',
                Permission.WEB_MANAGE_DOCUMENTS: '上传/删除PDF文档',
                Permission.WEB_RUN_QC: '执行QC质检与查看报表',
                Permission.WEB_MANAGE_USERS: '管理用户',
                Permission.WEB_MANAGE_PROJECTS: '管理项目',
                Permission.WEB_MANAGE_PROCESS_CONFIG: '管理工序配置',
                Permission.WEB_VIEW_LOGS: '查看系统日志',
                Permission.WEB_SYSTEM_SETTINGS: '系统设置',
                Permission.WEB_FINANCE_QUOTE: '\u8d22\u52a1\u62a5\u4ef7',
                Permission.WEB_QUALITY_PHOTO_DELETE: '删除质量工作台工序照片',
                Permission.WEB_VIEW_SOP: '查看SOP文档',
                Permission.WEB_MANAGE_SOP: '管理SOP文档',
                Permission.WEB_APPROVE_SOP: 'SOP审批权限',
                Permission.WEB_VIEW_SOP_RECYCLE: '查看SOP回收站',
                Permission.MOBILE_MATERIAL_RECORD: '移动端物料记录',
                Permission.MOBILE_MATERIAL_INBOUND: '\u7269\u6599\u5165\u5e93',
                Permission.MOBILE_MODIFY_EXISTING_MATERIAL: '修改已存在物料',
                Permission.MOBILE_PROCESS_RECORD: '移动端工序记录',
                Permission.MOBILE_CAMERA_ACCESS: '相机访问权限',
                Permission.API_RECORDS_READ: 'API记录读取',
                Permission.API_RECORDS_WRITE: 'API记录写入',
                Permission.API_RECORDS_DELETE: 'API记录删除',
                Permission.API_PROJECTS_READ: 'API项目读取',
                Permission.API_PROJECTS_WRITE: 'API项目写入',
                Permission.API_USERS_READ: 'API用户读取',
                Permission.API_USERS_WRITE: 'API用户写入'
            }
            
            for permission in Permission:
                permissions_info.append({
                    'value': permission.value,
                    'description': permission_descriptions.get(permission, permission.value),
                    'category': permission.value.split(':')[0] if ':' in permission.value else 'other'
                })
            
            return jsonify({
                'success': True,
                'permissions': permissions_info
            })
            
        except Exception as e:
            logger.error(f"获取权限列表失败: {e}")
            return jsonify({
                'success': False,
                'message': '获取权限列表失败',
                'error_code': 'PERMISSIONS_LIST_ERROR'
            }), 500

    # ============== 管理端权限配置接口 ==============

    @permission_api.route('/admin/permissions/resources', methods=['GET'])
    def get_permission_resources():
        """返回所有权限资源，用于前端渲染"""
        try:
            resources: Dict[str, List[Dict[str, Any]]] = {}
            for perm in Permission:
                category, action = perm.value.split(':', 1) if ':' in perm.value else ('other', perm.value)
                resources.setdefault(category, []).append({
                    'value': perm.value,
                    'action': action,
                    'description': perm.name
                })

            return jsonify({'success': True, 'resources': resources})
        except Exception as e:
            logger.error(f"获取权限资源失败: {e}")
            return jsonify({'success': False, 'message': '获取权限资源失败'}), 500

    @permission_api.route('/admin/permissions/users/<user_id>', methods=['GET'])
    def get_user_permission_details(user_id: str):
        """获取指定用户的权限评估详情"""
        try:
            user = user_service.get_user_by_id(user_id)
            if not user:
                return jsonify({'success': False, 'message': '用户不存在'}), 404

            effective = permission_service.evaluate_permissions(user_id, user)
            role_permissions = {perm.value for perm in permission_service._role_permissions.get(user.role, set())}
            group_permissions = user_service.get_group_permissions_for_user(user_id)
            user_overrides = user_service.get_user_permissions_override(user_id)

            return jsonify({
                'success': True,
                'user': user.to_dict(),
                'effective': effective,
                'role_permissions': list(role_permissions),
                'group_permissions': group_permissions,
                'user_overrides': user_overrides
            })
        except Exception as e:
            logger.error(f"获取用户权限详情失败: {e}")
            return jsonify({'success': False, 'message': '获取用户权限详情失败'}), 500

    @permission_api.route('/admin/permissions/users/<user_id>', methods=['PUT'])
    def update_user_permissions(user_id: str):
        """更新用户显式权限配置"""
        try:
            data = request.get_json() or {}
            changes = data.get('changes', {})
            if not isinstance(changes, dict):
                return jsonify({'success': False, 'message': 'changes 参数必须为对象'}), 400

            success = user_service.save_user_permissions(user_id, changes)
            if not success:
                return jsonify({'success': False, 'message': '保存用户权限失败'}), 500

            permission_service.evaluate_permissions(user_id)

            return jsonify({'success': True, 'message': '用户权限已更新'})
        except Exception as e:
            logger.error(f"更新用户权限失败: {e}")
            return jsonify({'success': False, 'message': '更新用户权限失败'}), 500

    @permission_api.route('/admin/permissions/groups/<group_id>', methods=['GET'])
    def get_group_permission_details(group_id: str):
        """获取指定群组的显式权限配置"""
        try:
            group = user_service.get_group_by_id(group_id)
            if not group:
                return jsonify({'success': False, 'message': '群组不存在'}), 404

            permissions_map = user_service.get_group_permissions(group_id)

            return jsonify({
                'success': True,
                'group': group,
                'permissions': permissions_map
            })
        except Exception as e:
            logger.error(f"获取群组权限详情失败: {e}")
            return jsonify({'success': False, 'message': '获取群组权限详情失败'}), 500

    @permission_api.route('/admin/permissions/groups/<group_id>', methods=['PUT'])
    def update_group_permissions(group_id: str):
        """更新群组显式权限配置"""
        try:
            data = request.get_json() or {}
            changes = data.get('changes', {})
            if not isinstance(changes, dict):
                return jsonify({'success': False, 'message': 'changes 参数必须为对象'}), 400

            success = user_service.save_group_permissions(group_id, changes)
            if not success:
                return jsonify({'success': False, 'message': '保存群组权限失败'}), 500

            return jsonify({'success': True, 'message': '群组权限已更新'})
        except Exception as e:
            logger.error(f"更新群组权限失败: {e}")
            return jsonify({'success': False, 'message': '更新群组权限失败'}), 500

    @permission_api.route('/user/role-permissions', methods=['GET'])
    def get_role_permissions():
        """
        获取各角色的权限配置
        
        Returns:
            JSON响应包含角色权限映射
        """
        try:
            role_permissions = {}
            
            # 获取管理员权限
            admin_permissions = permission_service.get_user_permissions(
                LocalUser(
                    id='temp',
                    synology_username='temp',
                    display_name='temp',
                    role=UserRole.ADMIN,
                    created_at=0,
                    updated_at=0
                )
            )
            role_permissions['admin'] = [perm.value for perm in admin_permissions]
            
            # 获取普通用户权限
            user_permissions = permission_service.get_user_permissions(
                LocalUser(
                    id='temp',
                    synology_username='temp',
                    display_name='temp',
                    role=UserRole.USER,
                    created_at=0,
                    updated_at=0
                )
            )
            role_permissions['user'] = [perm.value for perm in user_permissions]
            
            return jsonify({
                'success': True,
                'role_permissions': role_permissions
            })
            
        except Exception as e:
            logger.error(f"获取角色权限配置失败: {e}")
            return jsonify({
                'success': False,
                'message': '获取角色权限配置失败',
                'error_code': 'ROLE_PERMISSIONS_ERROR'
            }), 500
    
    @permission_api.route('/user/current-info', methods=['GET'])
    def get_current_user_info():
        """
        获取当前用户基本信息
        
        Returns:
            JSON响应包含用户基本信息
        """
        try:
            user = get_current_user()
            
            if not user:
                return jsonify({
                    'success': False,
                    'message': '用户未登录',
                    'error_code': 'NOT_AUTHENTICATED'
                }), 401
            
            return jsonify({
                'success': True,
                'user': {
                    'id': user.id,
                    'synology_username': user.synology_username,
                    'display_name': user.display_name,
                    'role': user.role.value,
                    'last_login_at': user.last_login_at,
                    'email': user.email,
                    'created_at': user.created_at,
                    'updated_at': user.updated_at
                }
            })
            
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return jsonify({
                'success': False,
                'message': '获取用户信息失败',
                'error_code': 'USER_INFO_ERROR'
            }), 500
    
    # ==================== 用户管理API ====================
    
    @permission_api.route('/users', methods=['GET'])
    def get_all_users():
        """
        获取所有用户列表（仅管理员）
        
        Returns:
            JSON响应包含用户列表
        """
        try:
            current_user = get_current_user()
            
            if not current_user:
                return jsonify({
                    'success': False,
                    'message': '用户未登录'
                }), 401
            
            # 检查管理员权限
            if current_user.role != UserRole.ADMIN:
                return jsonify({
                    'success': False,
                    'message': '权限不足，仅管理员可访问'
                }), 403
            
            # 获取所有用户
            users = user_service.get_all_users()
            
            users_data = [{
                'id': u.id,
                'synology_username': u.synology_username,
                'display_name': u.display_name,
                'role': u.role.value,
                'email': u.email,
                'last_login_at': u.last_login_at,
                'created_at': u.created_at,
                'updated_at': u.updated_at
            } for u in users]
            
            return jsonify({
                'success': True,
                'users': users_data,
                'total': len(users_data)
            })
            
        except Exception as e:
            logger.error(f"获取用户列表失败: {e}")
            return jsonify({
                'success': False,
                'message': '获取用户列表失败'
            }), 500
    
    @permission_api.route('/users/<user_id>', methods=['GET'])
    def get_user_by_id(user_id):
        """
        获取指定用户信息（仅管理员）
        
        Args:
            user_id: 用户ID
            
        Returns:
            JSON响应包含用户信息
        """
        try:
            current_user = get_current_user()
            
            if not current_user:
                return jsonify({
                    'success': False,
                    'message': '用户未登录'
                }), 401
            
            # 检查权限：管理员或查看自己的信息
            if current_user.role != UserRole.ADMIN and current_user.id != user_id:
                return jsonify({
                    'success': False,
                    'message': '权限不足'
                }), 403
            
            user = user_service.get_user_by_id(user_id)
            
            if not user:
                return jsonify({
                    'success': False,
                    'message': '用户不存在'
                }), 404
            
            return jsonify({
                'success': True,
                'user': {
                    'id': user.id,
                    'synology_username': user.synology_username,
                    'display_name': user.display_name,
                    'role': user.role.value,
                    'email': user.email,
                    'last_login_at': user.last_login_at,
                    'created_at': user.created_at,
                    'updated_at': user.updated_at
                }
            })
            
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return jsonify({
                'success': False,
                'message': '获取用户信息失败'
            }), 500
    
    @permission_api.route('/users', methods=['POST'])
    def create_user():
        """
        创建新用户（仅管理员）
        
        Request Body:
            {
                "synology_username": "username",
                "display_name": "显示名称",
                "role": "user",  // "admin" or "user"
                "email": "email@example.com"
            }
            
        Returns:
            JSON响应包含创建的用户信息
        """
        try:
            current_user = get_current_user()
            
            if not current_user:
                return jsonify({
                    'success': False,
                    'message': '用户未登录'
                }), 401
            
            # 检查管理员权限
            if current_user.role != UserRole.ADMIN:
                return jsonify({
                    'success': False,
                    'message': '权限不足，仅管理员可创建用户'
                }), 403
            
            data = request.get_json()
            
            # 验证必需字段
            if not data or 'synology_username' not in data:
                return jsonify({
                    'success': False,
                    'message': '缺少必需字段: synology_username'
                }), 400
            
            synology_username = data['synology_username']
            display_name = data.get('display_name', synology_username)
            role_str = data.get('role', 'user')
            email = data.get('email')
            
            # 验证角色
            try:
                role = UserRole(role_str)
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': f'无效的角色: {role_str}'
                }), 400
            
            # 创建用户
            new_user = user_service.create_user(
                synology_username=synology_username,
                display_name=display_name,
                role=role,
                email=email
            )
            
            if not new_user:
                return jsonify({
                    'success': False,
                    'message': '创建用户失败，用户名可能已存在'
                }), 400
            
            logger.info(f"管理员 {current_user.synology_username} 创建了新用户: {synology_username}")
            
            return jsonify({
                'success': True,
                'message': '用户创建成功',
                'user': {
                    'id': new_user.id,
                    'synology_username': new_user.synology_username,
                    'display_name': new_user.display_name,
                    'role': new_user.role.value,
                    'email': new_user.email
                }
            }), 201
            
        except Exception as e:
            logger.error(f"创建用户失败: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return jsonify({
                'success': False,
                'message': '创建用户失败'
            }), 500
    
    @permission_api.route('/users/<user_id>', methods=['PUT'])
    def update_user(user_id):
        """
        更新用户信息（仅管理员）
        
        Args:
            user_id: 用户ID
            
        Request Body:
            {
                "display_name": "新显示名称",
                "role": "admin",
                "email": "newemail@example.com"
            }
            
        Returns:
            JSON响应包含更新后的用户信息
        """
        try:
            current_user = get_current_user()
            
            if not current_user:
                return jsonify({
                    'success': False,
                    'message': '用户未登录'
                }), 401
            
            # 检查管理员权限
            if current_user.role != UserRole.ADMIN:
                return jsonify({
                    'success': False,
                    'message': '权限不足，仅管理员可更新用户'
                }), 403
            
            data = request.get_json()
            
            if not data:
                return jsonify({
                    'success': False,
                    'message': '缺少更新数据'
                }), 400
            
            # 用户更新功能暂未实现
            return jsonify({
                'success': False,
                'message': '用户更新功能暂未实现'
            }), 501
            
        except Exception as e:
            logger.error(f"更新用户失败: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return jsonify({
                'success': False,
                'message': '更新用户失败'
            }), 500
    
    return permission_api


def register_permission_context_processor(app, permission_service: PermissionService, user_service: UserManagementService):
    """
    注册权限上下文处理器，使权限检查在模板中可用
    
    Args:
        app: Flask应用实例
        permission_service: 权限服务实例
        user_service: 用户管理服务实例
    """
    
    @app.context_processor
    def permission_context():
        """权限上下文处理器"""
        
        def has_permission(permission_or_str) -> bool:
            """检查当前用户是否具有指定权限（支持枚举或字符串）"""
            try:
                if 'user_id' not in session:
                    return False
                
                user_id = session['user_id']
                user = user_service.get_user_by_id(user_id)
                
                if not user:
                    return False
                
                # 支持传入枚举对象或字符串
                if isinstance(permission_or_str, Permission):
                    # 直接使用枚举对象
                    return permission_service.has_permission(user, permission_or_str)
                else:
                    # 字符串，需要查找对应的枚举
                    for perm in Permission:
                        if perm.value == permission_or_str:
                            return permission_service.has_permission(user, perm)
                    
                    return False
                
            except Exception as e:
                logger.error(f"模板权限检查失败: {e}")
                return False
        
        def is_admin() -> bool:
            """检查当前用户是否为管理员"""
            try:
                if 'user_id' not in session:
                    return False
                
                user_id = session['user_id']
                user = user_service.get_user_by_id(user_id)
                
                return user and user.role == UserRole.ADMIN
                
            except Exception as e:
                logger.error(f"模板管理员检查失败: {e}")
                return False
        
        def get_current_user_info() -> Dict[str, Any]:
            """获取当前用户信息"""
            try:
                if 'user_id' not in session:
                    return {}
                
                user_id = session['user_id']
                user = user_service.get_user_by_id(user_id)
                
                if not user:
                    return {}
                
                return {
                    'id': user.id,
                    'synology_username': user.synology_username,
                    'display_name': user.display_name,
                    'role': user.role.value,
                    'is_admin': user.role == UserRole.ADMIN
                }
                
            except Exception as e:
                logger.error(f"获取模板用户信息失败: {e}")
                return {}
        
        return {
            'has_permission': has_permission,
            'is_admin': is_admin,
            'current_user_info': get_current_user_info(),
            'Permission': Permission  # 返回枚举类，使模板可以直接使用 Permission.WEB_APPROVE_SOP
        }
    
    logger.info("权限上下文处理器注册完成")
