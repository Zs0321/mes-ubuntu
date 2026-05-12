"""
群晖认证客户端模块
实现与群晖DSM API的通信接口，提供用户身份验证、会话管理和令牌处理功能
"""

import requests
import json
import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
from urllib.parse import urljoin
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from requests.packages.urllib3 import disable_warnings

logger = logging.getLogger(__name__)

@dataclass
class AuthResult:
    """认证结果数据类"""
    success: bool
    token: Optional[str] = None
    refresh_token: Optional[str] = None
    user_info: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    session_id: Optional[str] = None


@dataclass
class UserInfo:
    """用户信息数据类"""
    username: str
    display_name: str
    email: Optional[str] = None
    groups: Optional[list] = None
    uid: Optional[int] = None


@dataclass
class TokenPair:
    """令牌对数据类"""
    access_token: str
    refresh_token: str
    expires_in: int


class SynologyAuthClient:
    """群晖认证客户端"""
    
    def __init__(self, base_url: str, timeout: int = 30, verify_ssl: bool = True):
        """
        初始化群晖认证客户端
        
        Args:
            base_url: 群晖DSM的基础URL，如 https://your-nas.com:5001
            timeout: 请求超时时间（秒）
            verify_ssl: 是否验证SSL证书，默认为True
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.timeout = timeout
        self.last_error: Optional[str] = None
        
        # 设置请求头
        self.session.headers.update({
            'User-Agent': 'QRTestScanner-WebApp/1.0',
            'Accept': 'application/json'
        })
        
        # API端点
        self.auth_api = '/webapi/auth.cgi'
        self.info_api = '/webapi/query.cgi'
        
        if not self.verify_ssl:
            disable_warnings(InsecureRequestWarning)
            logger.warning("SSL验证已关闭，存在安全风险。仅在受信任的内部网络中使用此配置。")
        logger.info(f"初始化群晖认证客户端: {self.base_url}")
    
    def _make_request(self, endpoint: str, params: Dict[str, Any], method: str = "GET") -> Optional[Dict[str, Any]]:
        """
        发送API请求
        
        Args:
            endpoint: API端点
            params: 请求参数
            
        Returns:
            API响应数据或None
        """
        try:
            self.last_error = None
            url = urljoin(self.base_url, endpoint)
            logger.debug(f"发送请求到: {url}, 参数: {params}")
            
            request_method = (method or "GET").upper()
            request_kwargs = {
                "timeout": self.timeout,
                "verify": self.verify_ssl,
            }
            if request_method == "POST":
                request_kwargs["data"] = params
                request_kwargs["headers"] = {"Content-Type": "application/x-www-form-urlencoded"}
            else:
                request_kwargs["params"] = params

            response = self.session.request(request_method, url, **request_kwargs)
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"收到响应: {data}")
            
            return data
            
        except requests.exceptions.Timeout:
            logger.error(f"请求超时: {url}")
            self.last_error = "请求超时，请检查群晖服务连通性"
            return None
        except requests.exceptions.SSLError as e:
            # 常见场景：以 IP 访问时，证书域名为外网域名，导致主机名校验失败
            ssl_error = str(e)
            if self.verify_ssl:
                logger.warning(f"SSL 校验失败，自动降级重试(verify=False): {ssl_error}")
                try:
                    retry_kwargs = {
                        "timeout": self.timeout,
                        "verify": False,
                    }
                    if request_method == "POST":
                        retry_kwargs["data"] = params
                        retry_kwargs["headers"] = {"Content-Type": "application/x-www-form-urlencoded"}
                    else:
                        retry_kwargs["params"] = params
                    response = self.session.request(request_method, url, **retry_kwargs)
                    response.raise_for_status()
                    data = response.json()
                    logger.debug(f"SSL降级重试成功: {data}")
                    logger.warning("当前请求已使用 verify=False 兜底，请在受信任内网使用并尽快修复证书配置")
                    self.last_error = None
                    return data
                except Exception as retry_error:
                    logger.error(f"SSL降级重试失败: {retry_error}")
                    self.last_error = f"SSL证书校验失败且重试失败: {retry_error}"
                    return None

            logger.error(f"SSL错误: {ssl_error}")
            self.last_error = f"SSL证书校验失败: {ssl_error}"
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"连接失败: {url}")
            self.last_error = "无法连接到群晖服务器"
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP错误: {e}")
            self.last_error = f"HTTP错误: {e}"
            return None
        except json.JSONDecodeError:
            logger.error("响应不是有效的JSON格式")
            self.last_error = "群晖接口响应格式异常（非JSON）"
            return None
        except Exception as e:
            logger.error(f"请求异常: {e}")
            self.last_error = f"请求异常: {e}"
            return None
    
    def get_api_info(self) -> Optional[Dict[str, Any]]:
        """
        获取API信息
        
        Returns:
            API信息字典或None
        """
        params = {
            'api': 'SYNO.API.Info',
            'version': '1',
            'method': 'query',
            'query': 'SYNO.API.Auth'
        }
        
        response = self._make_request(self.info_api, params)
        if response and response.get('success'):
            return response.get('data', {})
        
        logger.warning("获取API信息失败")
        return None
    
    def authenticate(self, username: str, password: str) -> AuthResult:
        """
        用户身份验证
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            AuthResult对象包含认证结果
        """
        logger.info(f"开始认证用户: {username}")
        self.last_error = None
        
        if not username or not password:
            return AuthResult(
                success=False,
                error="用户名或密码不能为空"
            )
        
        try:
            last_error_code = None
            last_error_msg = None
            for version in ("3", "2"):
                params = {
                    'api': 'SYNO.API.Auth',
                    'version': version,
                    'method': 'login',
                    'account': username,
                    'passwd': password,
                    'session': 'QRTestScanner',
                    'format': 'sid'
                }
                response = self._make_request(self.auth_api, params, method="POST")

                if not response:
                    detail = self.last_error or "无法连接到群晖服务器"
                    return AuthResult(
                        success=False,
                        error=detail
                    )

                if response.get('success'):
                    data = response.get('data', {})
                    session_id = data.get('sid')

                    if session_id:
                        user_info = self._get_user_info(username, session_id)

                        logger.info(f"用户 {username} 认证成功")
                        return AuthResult(
                            success=True,
                            token=session_id,
                            session_id=session_id,
                            user_info=user_info.__dict__ if user_info else None
                        )
                    return AuthResult(
                        success=False,
                        error="认证成功但未获取到会话ID"
                    )

                last_error_code = response.get('error', {}).get('code', 'unknown')
                last_error_msg = self._get_error_message(last_error_code)
                if str(last_error_code) == "400" and version != "2":
                    logger.info(f"用户 {username} 登录接口版本 {version} 不兼容，回退到 version=2")
                    continue
                break

            logger.warning(f"用户 {username} 认证失败: {last_error_msg} (代码: {last_error_code})")
            self.last_error = last_error_msg
            return AuthResult(
                success=False,
                error=last_error_msg
            )
                
        except Exception as e:
            logger.error(f"认证过程异常: {e}")
            self.last_error = f"认证过程发生异常: {e}"
            return AuthResult(
                success=False,
                error=f"认证过程发生异常: {str(e)}"
            )
    
    def _get_user_info(self, username: str, session_id: str) -> Optional[UserInfo]:
        """
        获取用户详细信息
        
        Args:
            username: 用户名
            session_id: 会话ID
            
        Returns:
            UserInfo对象或None
        """
        try:
            # 尝试获取用户信息（如果API支持）
            params = {
                'api': 'SYNO.Core.User',
                'version': '1',
                'method': 'get',
                '_sid': session_id
            }
            
            response = self._make_request('/webapi/entry.cgi', params)
            
            if response and response.get('success'):
                data = response.get('data', {})
                return UserInfo(
                    username=username,
                    display_name=data.get('fullname', username),
                    email=data.get('email'),
                    groups=data.get('groups', []),
                    uid=data.get('uid')
                )
            else:
                # 如果无法获取详细信息，返回基本信息
                return UserInfo(
                    username=username,
                    display_name=username,
                    email=None,
                    groups=[],
                    uid=None
                )
                
        except Exception as e:
            logger.warning(f"获取用户信息失败: {e}")
            return UserInfo(
                username=username,
                display_name=username,
                email=None,
                groups=[],
                uid=None
            )
    
    def validate_session(self, session_id: str) -> Optional[UserInfo]:
        """
        验证会话有效性
        
        Args:
            session_id: 会话ID
            
        Returns:
            UserInfo对象或None（如果会话无效）
        """
        if not session_id:
            return None
        
        try:
            # 尝试使用会话ID获取信息来验证会话
            params = {
                'api': 'SYNO.API.Info',
                'version': '1',
                'method': 'query',
                'query': 'all',
                '_sid': session_id
            }
            
            response = self._make_request(self.info_api, params)
            
            if response and response.get('success'):
                logger.debug(f"会话 {session_id} 验证成功")
                # 这里无法直接获取用户名，需要在调用时提供
                return UserInfo(username="unknown", display_name="unknown")
            else:
                logger.warning(f"会话 {session_id} 验证失败")
                return None
                
        except Exception as e:
            logger.error(f"会话验证异常: {e}")
            return None
    
    def logout(self, session_id: str) -> bool:
        """
        登出并销毁会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否成功登出
        """
        if not session_id:
            return True
        
        try:
            params = {
                'api': 'SYNO.API.Auth',
                'version': '1',
                'method': 'logout',
                'session': 'QRTestScanner',
                '_sid': session_id
            }
            
            response = self._make_request(self.auth_api, params)
            
            if response and response.get('success'):
                logger.info(f"会话 {session_id} 登出成功")
                return True
            else:
                logger.warning(f"会话 {session_id} 登出失败")
                return False
                
        except Exception as e:
            logger.error(f"登出异常: {e}")
            return False
    
    def refresh_token(self, refresh_token: str) -> Optional[TokenPair]:
        """
        刷新令牌（群晖DSM不直接支持JWT刷新，这里提供接口兼容性）
        
        Args:
            refresh_token: 刷新令牌
            
        Returns:
            新的TokenPair或None
        """
        # 群晖DSM使用会话ID而不是JWT令牌
        # 这个方法主要用于接口兼容性
        logger.warning("群晖DSM不支持令牌刷新，请重新认证")
        return None
    
    def test_connection(self) -> bool:
        """
        测试与群晖服务器的连接
        
        Returns:
            连接是否成功
        """
        try:
            api_info = self.get_api_info()
            if api_info:
                logger.info("群晖服务器连接测试成功")
                return True
            else:
                logger.warning("群晖服务器连接测试失败")
                return False
                
        except Exception as e:
            logger.error(f"连接测试异常: {e}")
            return False
    
    def _get_error_message(self, error_code: str) -> str:
        """
        根据错误代码获取错误消息
        
        Args:
            error_code: 错误代码
            
        Returns:
            错误消息
        """
        error_messages = {
            '103': '用户名或密码错误',
            '400': '无效的参数',
            '401': '用户名或密码错误',
            '402': '访问被拒绝',
            '403': '一次性密码未提供',
            '404': '一次性密码认证失败',
            '405': '用户被禁用',
            '406': '权限被拒绝',
            '407': '一次性密码已过期',
            '408': '密码已过期',
            '409': '密码必须更改',
            '410': '账户被锁定',
            '411': '账户已过期',
            '412': '密码历史不符合要求',
            '413': '密码强度不符合要求',
            '414': '密码字符不符合要求',
            '415': '密码不能包含用户名',
            '416': '密码不能包含用户描述',
            '417': '密码已被使用',
            '418': '密码必须包含字母',
            '419': '密码必须包含数字',
            '420': '密码必须包含特殊字符',
            '421': '密码必须包含大写字母',
            '422': '密码必须包含小写字母'
        }
        
        return error_messages.get(str(error_code), f'未知错误 (代码: {error_code})')


class SynologyAuthService:
    """群晖认证服务 - 高级封装"""
    
    def __init__(self, base_url: str, timeout: int = 30, verify_ssl: bool = True):
        """
        初始化群晖认证服务
        
        Args:
            base_url: 群晖DSM的基础URL
            timeout: 请求超时时间
            verify_ssl: 是否验证SSL证书
        """
        self.client = SynologyAuthClient(base_url, timeout, verify_ssl)
        self._session_cache = {}  # 简单的会话缓存
        self.last_error: Optional[str] = None

    @staticmethod
    def _format_admin_api_error(api_name: str, error: Dict[str, Any]) -> str:
        """将 DSM API 错误码转换为可读错误信息。"""
        code = str((error or {}).get('code', 'unknown'))
        permission_codes = {'105', '106', '117', '119'}
        if code in permission_codes:
            return f"{api_name} 权限不足（错误码 {code}），请使用群晖管理员账户"
        return f"{api_name} 失败（错误码 {code}）"
        
    def authenticate(self, username: str, password: str) -> AuthResult:
        """
        用户认证（带缓存）
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            AuthResult对象
        """
        self.last_error = None
        result = self.client.authenticate(username, password)
        if not result.success:
            self.last_error = result.error
        
        if result.success and result.session_id:
            # 缓存会话信息
            self._session_cache[result.session_id] = {
                'username': username,
                'user_info': result.user_info,
                'created_at': time.time()
            }
        
        return result
    
    def validate_session(self, session_id: str) -> Optional[UserInfo]:
        """
        验证会话（带缓存）
        
        Args:
            session_id: 会话ID
            
        Returns:
            UserInfo对象或None
        """
        # 检查缓存
        if session_id in self._session_cache:
            cache_info = self._session_cache[session_id]
            # 检查缓存是否过期（1小时）
            if time.time() - cache_info['created_at'] < 3600:
                user_info_dict = cache_info['user_info']
                if user_info_dict:
                    return UserInfo(**user_info_dict)
        
        # 缓存未命中或过期，验证会话
        user_info = self.client.validate_session(session_id)
        return user_info
    
    def logout(self, session_id: str) -> bool:
        """
        登出并清理缓存
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否成功登出
        """
        # 清理缓存
        if session_id in self._session_cache:
            del self._session_cache[session_id]
        
        return self.client.logout(session_id)
    
    def test_connection(self) -> bool:
        """
        测试连接
        
        Returns:
            连接是否成功
        """
        return self.client.test_connection()
    
    def get_cached_user_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        从缓存获取用户信息
        
        Args:
            session_id: 会话ID
            
        Returns:
            用户信息字典或None
        """
        if session_id in self._session_cache:
            return self._session_cache[session_id]
        return None
    
    def list_all_users(self, admin_username: str, admin_password: str) -> Optional[list]:
        """
        获取所有群晖用户列表（需要管理员权限）
        
        Args:
            admin_username: 管理员用户名
            admin_password: 管理员密码
            
        Returns:
            用户列表或None
        """
        logger.info(f"开始获取群晖用户列表（管理员: {admin_username}）")
        self.last_error = None
        
        # 先进行管理员认证
        auth_result = self.client.authenticate(admin_username, admin_password)
        
        if not auth_result.success:
            logger.error(f"管理员认证失败: {auth_result.error}")
            self.last_error = auth_result.error
            return None
        
        try:
            # 使用管理员会话获取用户列表（包含群组信息）
            params = {
                'api': 'SYNO.Core.User',
                'version': '1',
                'method': 'list',
                '_sid': auth_result.session_id,
                # email/description/expired/group 信息通常出现在 additional 字段中
                'additional': '["email","description","expired","group"]'
            }
            
            response = self.client._make_request('/webapi/entry.cgi', params)
            
            if response and response.get('success'):
                users_data = response.get('data', {}).get('users', [])
                logger.info(f"✓ 成功获取 {len(users_data)} 个群晖用户")
                
                # 转换为标准格式
                users = []
                for user_data in users_data:
                    # 1. 提取 additional 字段中的扩展信息
                    additional = user_data.get('additional') or {}
                    if not isinstance(additional, dict):
                        additional = {}

                    # 2. 提取群组信息
                    #    根据 DSM API 文档，用户的群组信息通常在 additional.group 中，结构可能是：
                    #    {"local": ["group1","group2"], "ldap": [...]} 或简单的字符串/列表
                    groups_raw = additional.get('group', [])
                    groups: list = []

                    if isinstance(groups_raw, list):
                        # 已经是字符串列表
                        groups = [g for g in groups_raw if isinstance(g, str)]
                    elif isinstance(groups_raw, dict):
                        # 合并所有 value 中的字符串/字符串列表
                        collected = []
                        for value in groups_raw.values():
                            if isinstance(value, list):
                                collected.extend([g for g in value if isinstance(g, str)])
                            elif isinstance(value, str):
                                collected.append(value)
                        groups = collected
                    elif isinstance(groups_raw, str):
                        groups = [groups_raw]

                    # 兼容旧字段：如果顶层也有 group 字段，则补充进去
                    if not groups:
                        legacy_group = user_data.get('group')
                        if isinstance(legacy_group, list):
                            groups = [g for g in legacy_group if isinstance(g, str)]
                        elif isinstance(legacy_group, str):
                            groups = [legacy_group]
                        elif isinstance(legacy_group, dict):
                            tmp = []
                            for value in legacy_group.values():
                                if isinstance(value, list):
                                    tmp.extend([g for g in value if isinstance(g, str)])
                                elif isinstance(value, str):
                                    tmp.append(value)
                            groups = tmp

                    if groups:
                        logger.debug("群晖用户 %s 群组: %s", user_data.get('name'), groups)
                    
                    user_info = {
                        'username': user_data.get('name'),
                        'display_name': user_data.get('fullname', user_data.get('name')),
                        'email': user_data.get('email') or additional.get('email'),
                        'description': user_data.get('description') or additional.get('description'),
                        'is_admin': user_data.get('is_admin', False),
                        'expired': user_data.get('expired', additional.get('expired', False)),
                        'uid': user_data.get('uid'),
                        'groups': groups
                    }
                    users.append(user_info)
                
                # 登出管理员会话
                self.client.logout(auth_result.session_id)
                
                return users
            else:
                error = response.get('error', {}) if response else {}
                logger.error(f"获取用户列表失败: {error}")
                if response:
                    self.last_error = self._format_admin_api_error("获取群晖用户列表", error)
                else:
                    self.last_error = self.client.last_error or "获取群晖用户列表失败"
                return None
                
        except Exception as e:
            logger.error(f"获取用户列表异常: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            self.last_error = f"获取群晖用户列表异常: {e}"
            return None

    def list_all_groups(self, admin_username: str, admin_password: str) -> Optional[list]:
        """获取所有群晖群组及成员列表"""
        logger.info(f"开始获取群晖群组列表（管理员: {admin_username}）")
        self.last_error = None

        auth_result = self.client.authenticate(admin_username, admin_password)

        if not auth_result.success:
            logger.error(f"管理员认证失败: {auth_result.error}")
            self.last_error = auth_result.error
            return None

        try:
            params = {
                'api': 'SYNO.Core.Group',
                'version': '1',
                'method': 'list',
                '_sid': auth_result.session_id,
                'additional': 'member,member_desc,user,users'
            }

            response = self.client._make_request('/webapi/entry.cgi', params)

            if response and response.get('success'):
                groups_data = response.get('data', {}).get('groups', [])
                logger.info(f"✓ 成功获取 {len(groups_data)} 个群晖群组")

                groups = []
                groups_with_members_from_api = 0
                groups_with_members_fetched = 0
                
                for idx, group_data in enumerate(groups_data):
                    group_name = group_data.get('name')
                    
                    # 检查 API 返回的数据中是否已包含成员信息
                    existing_members = group_data.get('members') or group_data.get('additional', {}).get('member') or group_data.get('additional', {}).get('users')
                    
                    if existing_members:
                        groups_with_members_from_api += 1
                        if idx < 3:
                            logger.info(f"群组 {group_name} 从API直接获取到成员: {type(existing_members).__name__}, 数量: {len(existing_members) if isinstance(existing_members, list) else 'N/A'}")
                    else:
                        # 尝试单独获取成员
                        group_members = self._fetch_group_members(auth_result.session_id, group_name)
                        if group_members:
                            groups_with_members_fetched += 1
                            group_data['members'] = group_members
                            if idx < 3:
                                logger.info(f"群组 {group_name} 单独获取到成员: {len(group_members)} 个")
                        else:
                            if idx < 3:
                                logger.info(f"群组 {group_name} 未获取到成员")

                    groups.append({
                        'synology_group_id': group_data.get('gid'),
                        'name': group_name,
                        'display_name': group_name,
                        'description': group_data.get('description', ''),
                        'members': group_data.get('members', [])
                    })
                
                logger.info(f"群组成员获取统计: API直接返回 {groups_with_members_from_api} 个, 单独获取 {groups_with_members_fetched} 个")

                self.client.logout(auth_result.session_id)

                return groups
            else:
                error = response.get('error', {}) if response else {}
                logger.error(f"获取群组列表失败: {error}")
                if response:
                    self.last_error = self._format_admin_api_error("获取群晖群组列表", error)
                else:
                    self.last_error = self.client.last_error or "获取群晖群组列表失败"
                return None

        except Exception as e:
            logger.error(f"获取群组列表异常: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            self.last_error = f"获取群晖群组列表异常: {e}"
            return None

    def _fetch_group_members(self, session_id: str, group_name: Optional[str]) -> list:
        """补充获取群组成员列表，兼容不同API结构"""
        if not group_name:
            return []

        try:
            # 尝试方法1: SYNO.Core.Group.Member API
            params = {
                'api': 'SYNO.Core.Group.Member',
                'version': '1',
                'method': 'list',
                '_sid': session_id,
                'group': group_name  # 有些版本用 group 而不是 group_name
            }

            response = self.client._make_request('/webapi/entry.cgi', params)
            
            # 如果失败，尝试 group_name 参数
            if not response or not response.get('success'):
                params['group_name'] = group_name
                del params['group']
                response = self.client._make_request('/webapi/entry.cgi', params)

            # 尝试方法2: SYNO.Core.Group 的 get 方法
            if not response or not response.get('success'):
                fallback_params = {
                    'api': 'SYNO.Core.Group',
                    'version': '1',
                    'method': 'get',
                    '_sid': session_id,
                    'name': group_name,
                    'additional': '["member"]'
                }
                response = self.client._make_request('/webapi/entry.cgi', fallback_params)

            members = []
            if response and response.get('success'):
                data = response.get('data', {})
                if isinstance(data, dict):
                    # 尝试多种可能的字段名
                    if 'users' in data:
                        members = data['users']
                    elif 'members' in data:
                        members = data['members']
                    elif 'member' in data:
                        members = data['member']
                    elif 'list' in data:
                        members = data['list']
                    # 检查 additional 字段
                    elif 'additional' in data and isinstance(data['additional'], dict):
                        members = data['additional'].get('member', []) or data['additional'].get('members', [])

            normalized = []
            for item in members or []:
                if isinstance(item, str):
                    normalized.append(item)
                elif isinstance(item, dict):
                    username = item.get('username') or item.get('name')
                    if username:
                        normalized.append(username)
                elif isinstance(item, list):
                    for sub in item:
                        if isinstance(sub, str):
                            normalized.append(sub)
                        elif isinstance(sub, dict):
                            username = sub.get('username') or sub.get('name')
                            if username:
                                normalized.append(username)

            if normalized:
                logger.debug(f"群组 {group_name} 成员列表: {normalized}")
            else:
                logger.debug(f"群组 {group_name} 未获取到成员信息")

            return normalized

        except Exception as e:
            logger.error(f"获取群组 {group_name} 成员失败: {e}")
            return []
