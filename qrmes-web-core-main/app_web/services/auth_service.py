"""认证服务 - 密码管理"""
import bcrypt
import hashlib
from typing import Tuple
import logging

logger = logging.getLogger(__name__)

class PasswordManager:
    """密码管理器 - 支持从 SHA256 迁移到 bcrypt"""

    @staticmethod
    def hash_password(password: str) -> str:
        """使用 bcrypt 哈希密码"""
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    @staticmethod
    def verify_password(password: str, hashed: str) -> Tuple[bool, bool]:
        """
        验证密码

        Returns:
            (is_valid, needs_rehash)
            - is_valid: 密码是否正确
            - needs_rehash: 是否需要重新哈希（旧格式）
        """
        # 检测旧的 SHA256 格式（64 个十六进制字符）
        if len(hashed) == 64 and all(c in '0123456789abcdef' for c in hashed):
            # 旧格式验证
            old_hash = hashlib.sha256(password.encode()).hexdigest()
            is_valid = old_hash == hashed
            if is_valid:
                logger.info("检测到旧格式密码，需要升级")
            return (is_valid, True)  # 需要重新哈希

        # bcrypt 验证
        try:
            is_valid = bcrypt.checkpw(
                password.encode('utf-8'),
                hashed.encode('utf-8')
            )
            return (is_valid, False)  # 不需要重新哈希
        except Exception as e:
            logger.error(f"密码验证失败: {e}")
            return (False, False)

    @staticmethod
    def needs_rehash(hashed: str) -> bool:
        """检查密码是否需要重新哈希"""
        return len(hashed) == 64 and all(c in '0123456789abcdef' for c in hashed)
