"""
输入验证和清理服务

提供防 XSS、路径遍历等安全验证功能
"""

import html
import re
from pathlib import Path
from typing import Optional


class InputValidator:
    """输入验证和清理工具类"""

    # 用户名规则：3-32 字符，字母数字下划线
    USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]{3,32}$')

    # 邮箱规则：基本格式验证
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )

    @staticmethod
    def sanitize_string(value: str, max_length: int = 1000) -> str:
        """
        清理字符串，防止 XSS 攻击

        Args:
            value: 输入字符串
            max_length: 最大长度限制

        Returns:
            清理后的安全字符串
        """
        if not isinstance(value, str):
            return ""

        # 截断长度
        value = value[:max_length]

        # HTML 转义
        value = html.escape(value, quote=True)

        return value.strip()

    @staticmethod
    def validate_email(email: str) -> bool:
        """
        验证邮箱格式

        Args:
            email: 邮箱地址

        Returns:
            是否为有效邮箱
        """
        if not isinstance(email, str):
            return False

        email = email.strip().lower()

        if len(email) > 254:  # RFC 5321
            return False

        return bool(InputValidator.EMAIL_PATTERN.match(email))

    @staticmethod
    def validate_username(username: str) -> bool:
        """
        验证用户名格式

        Args:
            username: 用户名

        Returns:
            是否为有效用户名
        """
        if not isinstance(username, str):
            return False

        return bool(InputValidator.USERNAME_PATTERN.match(username))

    @staticmethod
    def sanitize_path(
        path: str,
        base_dir: Optional[str] = None,
        allow_absolute: bool = False
    ) -> Optional[str]:
        """
        清理文件路径，防止路径遍历攻击

        Args:
            path: 输入路径
            base_dir: 基础目录（如果提供，会验证路径在此目录内）
            allow_absolute: 是否允许绝对路径

        Returns:
            清理后的安全路径，如果不安全则返回 None
        """
        if not isinstance(path, str):
            return None

        # 移除空白字符
        path = path.strip()

        if not path:
            return None

        try:
            # 规范化路径
            normalized = Path(path).resolve()

            # 检查是否为绝对路径
            if not allow_absolute and normalized.is_absolute():
                return None

            # 如果提供了基础目录，验证路径在基础目录内
            if base_dir:
                base = Path(base_dir).resolve()
                try:
                    normalized.relative_to(base)
                except ValueError:
                    # 路径不在基础目录内
                    return None

            # 检查危险模式
            path_str = str(normalized)
            dangerous_patterns = ['..', '~', '$']
            if any(pattern in path_str for pattern in dangerous_patterns):
                return None

            return str(normalized)

        except (ValueError, OSError):
            return None

    @staticmethod
    def sanitize_filename(filename: str) -> Optional[str]:
        """
        清理文件名，移除危险字符

        Args:
            filename: 文件名

        Returns:
            清理后的安全文件名，如果不安全则返回 None
        """
        if not isinstance(filename, str):
            return None

        filename = filename.strip()

        if not filename or filename in ('.', '..'):
            return None

        # 移除路径分隔符和其他危险字符
        dangerous_chars = ['/', '\\', '..', '\0', '\n', '\r']
        for char in dangerous_chars:
            if char in filename:
                return None

        # 只保留安全字符：字母、数字、下划线、连字符、点
        safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)

        # 限制长度
        if len(safe_filename) > 255:
            safe_filename = safe_filename[:255]

        return safe_filename
