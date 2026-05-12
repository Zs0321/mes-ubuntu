"""
用户认证模块
"""

from functools import wraps
from pathlib import Path
import time
from flask import session, redirect, url_for, flash, request, jsonify, current_app
from typing import Optional, Dict, List, Any, Tuple
from .webdav_client import WebDAVClient
from .config import config
from .data_dir_utils import resolve_data_dir
from .synology_auth_client import SynologyAuthService
from .user_management_service import UserManagementService, LocalUser
import base64
import json
import hashlib
import logging

logger = logging.getLogger(__name__)

_AUTH_SERVICE_CACHE: Dict[str, Tuple[UserManagementService, SynologyAuthService]] = {}
_BASIC_AUTH_CACHE: Dict[str, Dict[str, Any]] = {}
_BASIC_AUTH_CACHE_TTL_SECONDS = 600


def _resolve_users_db_path() -> Path:
    try:
        injected = current_app.config.get("WEB_USERS_DB_PATH")
        if injected:
            return Path(injected)
    except Exception:
        pass

    repo_root = Path(__file__).resolve().parent.parent
    data_dir = resolve_data_dir(
        nas_local_base_path=getattr(config, "nas_local_base_path", None),
        repo_root=repo_root,
        create=False,
    )
    return data_dir / "web_users.db"


def _get_auth_services() -> Tuple[UserManagementService, SynologyAuthService]:
    db_path = _resolve_users_db_path()
    cache_key = f"{db_path}|{config.synology_api_url}|{config.synology_api_verify_ssl}"
    cached = _AUTH_SERVICE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    synology_auth = SynologyAuthService(
        base_url=config.synology_api_url,
        verify_ssl=config.synology_api_verify_ssl,
    )
    user_service = UserManagementService(db_path, synology_auth)
    services = (user_service, synology_auth)
    _AUTH_SERVICE_CACHE[cache_key] = services
    return services


def _local_user_to_auth_dict(user: LocalUser) -> Dict[str, Any]:
    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    return {
        "id": user.id,
        "username": user.synology_username,
        "synology_username": user.synology_username,
        "display_name": user.display_name or user.synology_username,
        "role": role_value,
        "email": user.email,
        "must_change_password": bool(getattr(user, "must_change_password", False)),
        "is_active": bool(getattr(user, "is_active", True)),
    }


def authenticate_managed_user(
    username: str,
    password: str,
    user_service: Optional[UserManagementService] = None,
    synology_auth: Optional[SynologyAuthService] = None,
    allow_password_change_required: bool = False,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not username or not password:
        return None, "用户名或密码不能为空"

    user_service = user_service or _get_auth_services()[0]
    local_user, error_message = user_service.authenticate_local_user(
        username=username,
        password=password,
        allow_password_change_required=allow_password_change_required,
    )
    if not local_user:
        logger.warning(f"[Managed Auth] 本地认证失败: {username} - {error_message}")
        return None, error_message

    refreshed_user = user_service.get_user_by_synology_username(username) or local_user
    return _local_user_to_auth_dict(refreshed_user), None


class UserManager:
    """用户管理器"""
    
    @staticmethod
    def _get_client() -> Optional[WebDAVClient]:
        """获取 WebDAV 客户端"""
        if not config.use_webdav or not config.webdav_username or not config.webdav_password:
            return None
        
        try:
            return WebDAVClient(
                base_url=config.webdav_url,
                username=config.webdav_username,
                password=config.webdav_password,
                base_path=config.webdav_base_path
            )
        except Exception as e:
            logger.error(f"Failed to create WebDAV client: {e}")
            return None
    
    @staticmethod
    def _hash_password(password: str) -> str:
        """密码哈希"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def get_users() -> Dict[str, Dict]:
        """获取所有用户"""
        client = UserManager._get_client()
        
        if client:
            # 从 WebDAV 读取
            data = client.read_json('users.json')
            if data:
                return data.get('users', {})
            return {}
        else:
            # 从本地文件读取
            from pathlib import Path
            users_file = Path(__file__).parent.parent / "app" / "files" / "users.json"
            if users_file.exists():
                try:
                    with open(users_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        return data.get('users', {})
                except Exception as e:
                    logger.error(f"Error reading users: {e}")
            return {}
    
    @staticmethod
    def get_user(username: str) -> Optional[Dict]:
        """
        获取单个用户信息
        
        Args:
            username: 用户名
            
        Returns:
            用户信息字典，如果用户不存在则返回 None
        """
        users = UserManager.get_users()
        user_data = users.get(username)
        
        if user_data:
            # 返回用户信息，包含用户名
            return {
                'username': username,
                **user_data
            }
        return None
    
    @staticmethod
    def save_users(users: Dict[str, Dict]) -> bool:
        """保存用户列表"""
        client = UserManager._get_client()
        data = {'users': users}
        
        if client:
            # 保存到 WebDAV
            return client.write_json('users.json', data)
        else:
            # 保存到本地文件
            from pathlib import Path
            users_file = Path(__file__).parent.parent / "app" / "files" / "users.json"
            users_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(users_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Error saving users: {e}")
                return False
    
    @staticmethod
    def authenticate(username: str, password: str, protocol: str = None) -> Optional[Dict]:
        """验证用户登录 - 支持 SMB 和 WebDAV"""
        from .config import config
        
        # 如果未指定协议，使用配置文件中的默认协议
        if not protocol:
            protocol = config.protocol
        
        protocol = protocol.lower()
        
        logger.info(f"[认证调试] 开始验证用户: '{username}', 协议: {protocol.upper()}")
        
        if not username or not password:
            logger.warning(f"[认证调试] 用户名或密码为空")
            return None
        
        try:
            # 根据协议创建相应的客户端
            if protocol == 'smb':
                from .smb_client import SMBClient
                logger.info(f"[认证调试] 使用 SMB 协议")
                logger.info(f"[认证调试] SMB配置 - 服务器: {config.smb_server}, 共享: {config.smb_share_name}, 路径: {config.smb_base_path}")
                
                test_client = SMBClient(
                    server=config.smb_server,
                    share_name=config.smb_share_name,
                    username=username,
                    password=password,
                    base_path=config.smb_base_path
                )
            else:  # webdav
                logger.info(f"[认证调试] 使用 WebDAV 协议")
                logger.info(f"[认证调试] WebDAV配置 - URL: {config.webdav_url}, 基础路径: {config.webdav_base_path}")
                
                test_client = WebDAVClient(
                    base_url=config.webdav_url,
                    username=username,
                    password=password,
                    base_path=config.webdav_base_path
                )
            
            logger.info(f"[认证调试] 客户端创建成功，开始测试连接...")
            # 测试连接
            connection_result = test_client.test_connection()
            logger.info(f"[认证调试] 连接测试结果: {connection_result}")
            
            if connection_result:
                logger.info(f"[认证调试] {protocol.upper()} 连接成功 - 用户: {username}")
                
                # 检查是否是管理员（配置文件中的账号）
                is_admin = (username == config.webdav_username)
                logger.info(f"[认证调试] 管理员检查 - 是否管理员: {is_admin}")
                
                user_info = {
                    'username': username,
                    'display_name': username,
                    'role': 'admin' if is_admin else 'user',
                    'email': '',
                    'protocol': protocol
                }
                
                logger.info(f"[认证调试] 返回用户信息: {user_info}")
                return user_info
            else:
                logger.warning(f"[认证调试] {protocol.upper()} 连接测试失败 - 用户: {username}")
                return None
                
        except Exception as e:
            logger.error(f"[认证调试] {protocol.upper()} 认证异常 - 用户: {username}, 错误: {str(e)}")
            logger.error(f"[认证调试] 异常详情: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[认证调试] 堆栈跟踪:\n{traceback.format_exc()}")
            return None
    
    @staticmethod
    def create_user(username: str, password: str, display_name: str = '',
                   role: str = 'user', email: str = '') -> bool:
        """创建新用户"""
        users = UserManager.get_users()
        
        if username in users:
            return False
        
        users[username] = {
            'password': UserManager._hash_password(password),
            'display_name': display_name or username,
            'role': role,
            'email': email,
            'created_at': datetime.now().isoformat()
        }
        
        return UserManager.save_users(users)
    
    @staticmethod
    def update_user(username: str, updates: Dict) -> bool:
        """更新用户信息"""
        users = UserManager.get_users()
        
        if username not in users:
            return False
        
        # 更新密码需要哈希
        if 'password' in updates:
            updates['password'] = UserManager._hash_password(updates['password'])
        
        users[username].update(updates)
        return UserManager.save_users(users)
    
    @staticmethod
    def delete_user(username: str) -> bool:
        """删除用户"""
        users = UserManager.get_users()
        
        if username not in users:
            return False
        
        del users[username]
        return UserManager.save_users(users)
    
    @staticmethod
    def init_default_users():
        """初始化默认用户（本地密码模式下无需额外预置）"""
        logger.info("当前使用本地密码模式，默认密码由用户管理数据库维护")


class OperationLogger:
    """操作日志记录器"""
    
    @staticmethod
    def _get_client() -> Optional[WebDAVClient]:
        """获取 WebDAV 客户端"""
        return UserManager._get_client()
    
    @staticmethod
    def log_operation(username: str, operation: str, target: str, 
                     details: str = '', success: bool = True):
        """记录操作日志"""
        from datetime import datetime
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'username': username,
            'operation': operation,  # 如：'创建项目', '删除物料', '导出数据'
            'target': target,        # 操作对象
            'details': details,      # 详细信息
            'success': success
        }
        
        # 读取现有日志
        client = OperationLogger._get_client()
        
        if client:
            # 从 WebDAV 读取
            logs = client.read_json('operation_logs.json')
            if not logs:
                logs = {'logs': []}
            
            # 添加新日志
            logs['logs'].append(log_entry)
            
            # 只保留最近 1000 条日志
            if len(logs['logs']) > 1000:
                logs['logs'] = logs['logs'][-1000:]
            
            # 保存到 WebDAV
            client.write_json('operation_logs.json', logs)
            logger.info(f"Operation logged: {username} - {operation} - {target}")
        else:
            # 保存到本地文件
            from pathlib import Path
            logs_file = Path(__file__).parent.parent / "app" / "files" / "operation_logs.json"
            logs_file.parent.mkdir(parents=True, exist_ok=True)
            
            logs = {'logs': []}
            if logs_file.exists():
                try:
                    with open(logs_file, 'r', encoding='utf-8') as f:
                        logs = json.load(f)
                except:
                    pass
            
            logs['logs'].append(log_entry)
            
            # 只保留最近 1000 条
            if len(logs['logs']) > 1000:
                logs['logs'] = logs['logs'][-1000:]
            
            try:
                with open(logs_file, 'w', encoding='utf-8') as f:
                    json.dump(logs, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Error saving operation log: {e}")
    
    @staticmethod
    def get_logs(username: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """获取操作日志"""
        client = OperationLogger._get_client()
        
        if client:
            # 从 WebDAV 读取
            data = client.read_json('operation_logs.json')
            if data:
                logs = data.get('logs', [])
            else:
                logs = []
        else:
            # 从本地文件读取
            from pathlib import Path
            logs_file = Path(__file__).parent.parent / "app" / "files" / "operation_logs.json"
            logs = []
            if logs_file.exists():
                try:
                    with open(logs_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        logs = data.get('logs', [])
                except Exception as e:
                    logger.error(f"Error reading logs: {e}")
        
        # 按用户名筛选
        if username:
            logs = [log for log in logs if log.get('username') == username]
        
        # 按时间倒序，返回最近的
        logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return logs[:limit]


def get_user_from_basic_auth(synology_auth=None, user_service=None, skip_auth_verify=False):
    """
    ? Basic Auth ??????
    ??????? Basic Auth ???
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Basic '):
        return None

    try:
        encoded = auth_header[6:]
        decoded = base64.b64decode(encoded).decode('utf-8')
        username, password = decoded.split(':', 1)

        if not user_service or not synology_auth:
            user_service, synology_auth = _get_auth_services()

        if skip_auth_verify:
            logger.debug(f"[Basic Auth] 已忽略 skip_auth_verify，继续校验用户: {username}")

        auth_user, error_message = authenticate_managed_user(
            username=username,
            password=password,
            user_service=user_service,
            synology_auth=synology_auth,
        )
        if auth_user:
            logger.debug(f"[Basic Auth] 认证成功: {username}")
            return auth_user

        logger.warning(f"[Basic Auth] 认证失败: {username} - {error_message}")
        return None
    except Exception as e:
        logger.warning(f"[Basic Auth] 异常: {e}")
        return None


def login_required(f):
    """
    ????????
    ?? Flask session ???? Basic Auth?
    ??????? DSM ?????????????????????
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' in session:
            if session['user'].get('must_change_password') and request.endpoint not in {'change_password', 'logout'}:
                if request.path.startswith('/api/'):
                    return jsonify({'success': False, 'message': '首次登录请先修改密码'}), 403
                flash('首次登录请先修改密码', 'warning')
                return redirect(url_for('change_password'))
            return f(*args, **kwargs)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Basic '):
            try:
                user_service, synology_auth = _get_auth_services()
                auth_user = get_user_from_basic_auth(
                    synology_auth=synology_auth,
                    user_service=user_service,
                )
                if auth_user:
                    protocol = (
                        request.headers.get('X-Storage-Protocol')
                        or request.headers.get('X-Protocol')
                        or ''
                    ).strip().lower()
                    request.mobile_user = {
                        **auth_user,
                        'username': auth_user.get('username') or auth_user.get('synology_username'),
                        'protocol': protocol,
                        '_is_mobile': True,
                    }
                    logger.debug(f"[login_required] Basic Auth 通过: {request.mobile_user.get('username')}")
                    return f(*args, **kwargs)
            except Exception as e:
                logger.warning(f"[login_required] Basic Auth 解析失败: {e}")

        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'message': '请先登录'}), 401

        flash('请先登录', 'warning')
        return redirect(url_for('login'))
    return decorated_function


def admin_required(f):
    """管理员权限验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            # 检查是否是 API 请求
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': '请先登录'}), 401
            flash('请先登录', 'warning')
            return redirect(url_for('login'))
        
        if session['user'].get('role') != 'admin':
            # 检查是否是 API 请求
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': '需要管理员权限'}), 403
            flash('需要管理员权限', 'error')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


# 导入 datetime（用于时间戳）
from datetime import datetime
