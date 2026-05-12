#!/usr/bin/env python3
"""
本地认证服务
替代群晖认证，使用本地用户名密码认证
支持SMB和WebDAV协议
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class AuthResult:
    """认证结果"""
    success: bool
    message: str
    user_info: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None


class LocalAuthService:
    """本地认证服务"""
    
    def __init__(self):
        """初始化本地认证服务"""
        logger.info("初始化本地认证服务")
    
    @staticmethod
    def hash_password(password: str, salt: str = "") -> str:
        """
        密码哈希
        
        Args:
            password: 明文密码
            salt: 盐值（可选）
        
        Returns:
            哈希后的密码
        """
        # 使用SHA256哈希
        hash_obj = hashlib.sha256()
        hash_obj.update((password + salt).encode('utf-8'))
        return hash_obj.hexdigest()
    
    def authenticate(self, username: str, password: str) -> AuthResult:
        """
        认证用户
        
        Args:
            username: 用户名
            password: 密码
        
        Returns:
            认证结果
        """
        try:
            # 基本验证
            if not username or not password:
                return AuthResult(
                    success=False,
                    message="用户名和密码不能为空",
                    error_code="EMPTY_CREDENTIALS"
                )
            
            # 用户名长度验证
            if len(username) < 3 or len(username) > 50:
                return AuthResult(
                    success=False,
                    message="用户名长度必须在3-50个字符之间",
                    error_code="INVALID_USERNAME_LENGTH"
                )
            
            # 密码长度验证
            if len(password) < 4:
                return AuthResult(
                    success=False,
                    message="密码长度至少4个字符",
                    error_code="INVALID_PASSWORD_LENGTH"
                )
            
            # 返回成功结果（实际密码验证在UserManagementService中进行）
            return AuthResult(
                success=True,
                message="认证成功",
                user_info={
                    'username': username,
                    'display_name': username
                }
            )
            
        except Exception as e:
            logger.error(f"认证过程出错: {e}")
            return AuthResult(
                success=False,
                message=f"认证失败: {str(e)}",
                error_code="AUTH_ERROR"
            )
    
    def validate_credentials_format(self, username: str, password: str) -> tuple[bool, str]:
        """
        验证凭据格式
        
        Args:
            username: 用户名
            password: 密码
        
        Returns:
            (是否有效, 错误消息)
        """
        if not username or not password:
            return False, "用户名和密码不能为空"
        
        if len(username) < 3:
            return False, "用户名长度至少3个字符"
        
        if len(username) > 50:
            return False, "用户名长度不能超过50个字符"
        
        if len(password) < 4:
            return False, "密码长度至少4个字符"
        
        if len(password) > 100:
            return False, "密码长度不能超过100个字符"
        
        return True, ""


# 向后兼容的别名
class SynologyAuthService(LocalAuthService):
    """向后兼容的别名"""
    pass


# 导出类型
UserInfo = Dict[str, Any]
