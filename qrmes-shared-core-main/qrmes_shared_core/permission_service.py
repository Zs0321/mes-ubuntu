"""
权限验证服务模块
提供基于角色的访问控制功能
"""

import logging
from typing import Dict, List, Optional, Set
from enum import Enum
from functools import wraps
from flask import session, request, jsonify, redirect, url_for

from .user_management_service import LocalUser, UserRole, UserManagementService

logger = logging.getLogger(__name__)


class Permission(Enum):
    """权限枚举"""
    # Web后台权限
    WEB_VIEW_RECORDS = 'web:view_records'
    WEB_MODIFY_RECORDS = 'web:modify_records'
    WEB_DELETE_RECORDS = 'web:delete_records'
    WEB_VIEW_DOCUMENTS = 'web:view_documents'
    WEB_MANAGE_DOCUMENTS = 'web:manage_documents'
    WEB_RUN_QC = 'web:run_qc'
    WEB_MANAGE_USERS = 'web:manage_users'
    WEB_MANAGE_PROJECTS = 'web:manage_projects'
    WEB_MANAGE_PROCESS_CONFIG = 'web:manage_process_config'
    WEB_VIEW_LOGS = 'web:view_logs'
    WEB_SYSTEM_SETTINGS = 'web:system_settings'
    WEB_FINANCE_QUOTE = 'web:finance_quote'
    WEB_CUSTOMER_COMPLAINTS_AFTER_SALES = 'web:customer_complaints_after_sales'
    WEB_CUSTOMER_COMPLAINTS_QUALITY = 'web:customer_complaints_quality'
    WEB_CUSTOMER_COMPLAINTS_NOTIFY = 'web:customer_complaints_notify'
    
    # 移动端权限
    MOBILE_MATERIAL_RECORD = 'mobile:material_record'
    MOBILE_MATERIAL_INBOUND = 'mobile:material_inbound'
    MOBILE_MODIFY_EXISTING_MATERIAL = 'mobile:modify_existing_material'
    MOBILE_PROCESS_RECORD = 'mobile:process_record'
    MOBILE_CAMERA_ACCESS = 'mobile:camera_access'
    
    # 配置权限（项目配置读写）
    CONFIG_READ = 'config:read'
    CONFIG_WRITE = 'config:write'
    
    # API权限
    API_RECORDS_READ = 'api:records_read'
    API_RECORDS_WRITE = 'api:records_write'
    API_RECORDS_DELETE = 'api:records_delete'
    API_PROJECTS_READ = 'api:projects_read'
    API_PROJECTS_WRITE = 'api:projects_write'
    API_USERS_READ = 'api:users_read'
    API_USERS_WRITE = 'api:users_write'


class PermissionService:
    """权限验证服务"""
    
    def __init__(self, user_management_service: UserManagementService):
        """
        初始化权限服务
        
        Args:
            user_management_service: 用户管理服务实例
        """
        self.user_service = user_management_service
        
        # 定义角色权限映射
        self._role_permissions = {
            UserRole.ADMIN: {
                # 管理员拥有所有权限
                Permission.WEB_VIEW_RECORDS,
                Permission.WEB_MODIFY_RECORDS,
                Permission.WEB_DELETE_RECORDS,
                Permission.WEB_VIEW_DOCUMENTS,
                Permission.WEB_MANAGE_DOCUMENTS,
                Permission.WEB_RUN_QC,
                Permission.WEB_MANAGE_USERS,
                Permission.WEB_MANAGE_PROJECTS,
                Permission.WEB_MANAGE_PROCESS_CONFIG,
                Permission.WEB_VIEW_LOGS,
                Permission.WEB_SYSTEM_SETTINGS,
                Permission.WEB_FINANCE_QUOTE,
                Permission.WEB_CUSTOMER_COMPLAINTS_AFTER_SALES,
                Permission.WEB_CUSTOMER_COMPLAINTS_QUALITY,
                Permission.WEB_CUSTOMER_COMPLAINTS_NOTIFY,
                Permission.MOBILE_MATERIAL_RECORD,
                Permission.MOBILE_MATERIAL_INBOUND,
                Permission.MOBILE_MODIFY_EXISTING_MATERIAL,
                Permission.MOBILE_PROCESS_RECORD,
                Permission.MOBILE_CAMERA_ACCESS,
                Permission.CONFIG_READ,
                Permission.CONFIG_WRITE,
                Permission.API_RECORDS_READ,
                Permission.API_RECORDS_WRITE,
                Permission.API_RECORDS_DELETE,
                Permission.API_PROJECTS_READ,
                Permission.API_PROJECTS_WRITE,
                Permission.API_USERS_READ,
                Permission.API_USERS_WRITE
            },
            UserRole.USER: {
                # 普通用户权限
                Permission.WEB_VIEW_RECORDS,
                Permission.WEB_MODIFY_RECORDS,  # 允许修改记录
                Permission.WEB_VIEW_DOCUMENTS,
                Permission.MOBILE_MATERIAL_RECORD,
                Permission.MOBILE_PROCESS_RECORD,
                Permission.MOBILE_CAMERA_ACCESS,
                Permission.CONFIG_READ,  # 允许读取配置
                Permission.API_RECORDS_READ,
                Permission.API_RECORDS_WRITE,  # 允许写入记录
                Permission.API_PROJECTS_READ
            }
        }
        
        logger.info("权限服务初始化完成")
    
    def _coerce_local_user(self, user) -> Optional[LocalUser]:
        if not user:
            return None
        if isinstance(user, LocalUser):
            return user
        if isinstance(user, dict):
            user_id = str(user.get('id') or '').strip()
            if user_id:
                local_user = self.user_service.get_user_by_id(user_id)
                if local_user:
                    return local_user
            username = str(user.get('synology_username') or user.get('username') or '').strip()
            if username:
                return self.user_service.get_user_by_synology_username(username)
        return None

    def has_permission(self, user: LocalUser, permission: Permission) -> bool:
        """
        检查用户是否具有指定权限
        
        Args:
            user: 本地用户对象
            permission: 权限枚举
            
        Returns:
            是否具有权限
        """
        user = self._coerce_local_user(user)
        if not user:
            return False

        evaluated = self.evaluate_permissions(user.id, user)
        has_perm = evaluated.get(permission.value, False)
        
        # 记录权限检查日志
        result = 'allowed' if has_perm else 'denied'
        try:
            # 尝试记录权限操作日志（如果方法存在）
            if hasattr(self.user_service, 'log_permission_action'):
                self.user_service.log_permission_action(
                    user_id=user.id,
                    action='permission_check',
                    resource=permission.value,
                    result=result,
                    ip_address=self._get_client_ip(),
                    user_agent=self._get_user_agent()
                )
        except Exception as e:
            logger.warning(f"记录权限日志失败: {e}")
        
        logger.debug(f"权限检查: 用户 {user.synology_username} 对 {permission.value} 的权限: {result}")
        return has_perm
    
    def has_permission_by_user_id(self, user_id: str, permission: Permission) -> bool:
        """
        根据用户ID检查权限
        
        Args:
            user_id: 用户ID
            permission: 权限枚举
            
        Returns:
            是否具有权限
        """
        user = self.user_service.get_user_by_id(user_id)
        return self.has_permission(user, permission)
    
    def get_user_permissions(self, user: LocalUser) -> Set[Permission]:
        """
        获取用户的所有权限
        
        Args:
            user: 本地用户对象
            
        Returns:
            权限集合
        """
        user = self._coerce_local_user(user)
        if not user:
            return set()

        evaluated = self.evaluate_permissions(user.id, user)
        permissions: Set[Permission] = set()
        for perm in Permission:
            if evaluated.get(perm.value, False):
                permissions.add(perm)
        return permissions

    def evaluate_permissions(self, user_id: str, user: Optional[LocalUser] = None) -> Dict[str, bool]:
        """综合角色、群组（区分同步/本地）、用户覆写计算最终权限

        优先级：角色默认 < 同步群组 < 本地群组 < 用户显式覆写
        """
        try:
            if not user:
                user = self.user_service.get_user_by_id(user_id)

            if not user:
                return {}

            # 角色默认权限
            role_permissions = {perm.value for perm in self._role_permissions.get(user.role, set())}

            # 优先尝试使用带来源信息的群组权限
            group_infos = []
            if hasattr(self.user_service, 'get_group_permissions_for_user_with_source'):
                try:
                    group_infos = self.user_service.get_group_permissions_for_user_with_source(user.id)
                except Exception as e:
                    logger.warning(f"获取带来源的群组权限失败，降级为旧行为: {e}")

            ds_group_allow: Set[str] = set()
            ds_group_deny: Set[str] = set()
            local_group_allow: Set[str] = set()
            local_group_deny: Set[str] = set()

            if group_infos:
                # 按来源拆分群组权限
                for info in group_infos:
                    perms_map = info.get('permissions') or {}
                    is_local = info.get('is_local', False)
                    for perm_value, effect in perms_map.items():
                        if effect == 'deny':
                            if is_local:
                                local_group_deny.add(perm_value)
                            else:
                                ds_group_deny.add(perm_value)
                        elif effect == 'allow':
                            if is_local:
                                local_group_allow.add(perm_value)
                            else:
                                ds_group_allow.add(perm_value)
            else:
                # 兼容旧实现：不区分本地/同步群组
                group_permissions_map = self.user_service.get_group_permissions_for_user(user.id)
                for permissions in group_permissions_map.values():
                    for perm_value, effect in permissions.items():
                        if effect == 'deny':
                            ds_group_deny.add(perm_value)
                        elif effect == 'allow':
                            ds_group_allow.add(perm_value)

            user_overrides = self.user_service.get_user_permissions_override(user.id)

            is_admin = user.role == UserRole.ADMIN
            if is_admin:
                return {perm.value: True for perm in Permission}

            admin_only_permissions = {
                Permission.WEB_VIEW_LOGS.value,
                Permission.WEB_MANAGE_USERS.value,
                Permission.WEB_SYSTEM_SETTINGS.value,
            }

            evaluated: Dict[str, bool] = {}
            for perm in Permission:
                perm_value = perm.value

                if perm_value in admin_only_permissions:
                    evaluated[perm_value] = is_admin
                    continue

                # 1. 角色默认
                allowed = perm_value in role_permissions

                # 2/3. 非管理员继续按同步/本地群组权限叠加。
                if perm_value in ds_group_deny:
                    allowed = False
                elif perm_value in ds_group_allow:
                    allowed = True

                if perm_value in local_group_deny:
                    allowed = False
                elif perm_value in local_group_allow:
                    allowed = True

                # 4. 用户显式覆写，优先级最高
                override = user_overrides.get(perm_value)
                if override == 'deny':
                    allowed = False
                elif override == 'allow':
                    allowed = True

                evaluated[perm_value] = allowed

            return evaluated

        except Exception as e:
            logger.error(f"计算用户权限失败: {e}")
            return {}
    
    def can_modify_existing_record(self, user: LocalUser, product_serial: str) -> bool:
        """
        检查用户是否可以修改已存在的记录
        
        Args:
            user: 本地用户对象
            product_serial: 产品序列号
            
        Returns:
            是否可以修改
        """
        # 管理员可以修改任何记录
        if user.role == UserRole.ADMIN:
            return True
        
        # 普通用户不能修改已存在的记录
        return False
    
    def _get_client_ip(self) -> Optional[str]:
        """获取客户端IP地址"""
        try:
            if request:
                return request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR'))
        except:
            pass
        return None
    
    def _get_user_agent(self) -> Optional[str]:
        """获取用户代理"""
        try:
            if request:
                return request.headers.get('User-Agent')
        except:
            pass
        return None


# 装饰器函数

def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'success': False, 'message': '请先登录'}), 401
            else:
                return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def permission_required(permission: Permission, user_service: UserManagementService, permission_service: PermissionService):
    """权限验证装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                if request.is_json:
                    return jsonify({'success': False, 'message': '请先登录'}), 401
                else:
                    return redirect(url_for('login'))
            
            user_id = session['user_id']
            user = user_service.get_user_by_id(user_id)
            
            if not user:
                if request.is_json:
                    return jsonify({'success': False, 'message': '用户不存在'}), 401
                else:
                    return redirect(url_for('login'))
            
            if not permission_service.has_permission(user, permission):
                if request.is_json:
                    return jsonify({'success': False, 'message': '权限不足'}), 403
                else:
                    return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(user_service: UserManagementService):
    """管理员权限验证装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                if request.is_json:
                    return jsonify({'success': False, 'message': '请先登录'}), 401
                else:
                    return redirect(url_for('login'))
            
            user_id = session['user_id']
            user = user_service.get_user_by_id(user_id)
            
            if not user or user.role != UserRole.ADMIN:
                if request.is_json:
                    return jsonify({'success': False, 'message': '需要管理员权限'}), 403
                else:
                    return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


class PermissionChecker:
    """权限检查器 - 用于模板和前端"""
    
    def __init__(self, permission_service: PermissionService, user_service: UserManagementService):
        """
        初始化权限检查器
        
        Args:
            permission_service: 权限服务实例
            user_service: 用户管理服务实例
        """
        self.permission_service = permission_service
        self.user_service = user_service
    
    def current_user_has_permission(self, permission: Permission) -> bool:
        """
        检查当前会话用户是否具有指定权限
        
        Args:
            permission: 权限枚举
            
        Returns:
            是否具有权限
        """
        try:
            if 'user_id' not in session:
                return False
            
            user_id = session['user_id']
            user = self.user_service.get_user_by_id(user_id)
            
            if not user:
                return False
            
            return self.permission_service.has_permission(user, permission)
            
        except Exception as e:
            logger.error(f"检查当前用户权限失败: {e}")
            return False
    
    def current_user_is_admin(self) -> bool:
        """
        检查当前用户是否为管理员
        
        Returns:
            是否为管理员
        """
        try:
            if 'user_id' not in session:
                return False
            
            user_id = session['user_id']
            user = self.user_service.get_user_by_id(user_id)
            
            return user and user.role == UserRole.ADMIN
            
        except Exception as e:
            logger.error(f"检查当前用户管理员权限失败: {e}")
            return False
    
    def get_current_user(self) -> Optional[LocalUser]:
        """
        获取当前会话用户
        
        Returns:
            LocalUser对象或None
        """
        try:
            if 'user_id' not in session:
                return None
            
            user_id = session['user_id']
            return self.user_service.get_user_by_id(user_id)
            
        except Exception as e:
            logger.error(f"获取当前用户失败: {e}")
            return None


def create_permission_context_processor(permission_checker: PermissionChecker):
    """
    创建权限上下文处理器，用于在模板中使用权限检查
    
    Args:
        permission_checker: 权限检查器实例
        
    Returns:
        上下文处理器函数
    """
    def permission_context():
        return {
            'has_permission': permission_checker.current_user_has_permission,
            'is_admin': permission_checker.current_user_is_admin,
            'current_user': permission_checker.get_current_user(),
            'Permission': Permission  # 使权限枚举在模板中可用
        }
    
    return permission_context
