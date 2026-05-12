"""配置管理器 - 从 webdav_config.json 读取"""
import os
import json
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class SecretManager:
    """配置管理器 - 从 webdav_config.json 读取配置"""

    # 默认密钥（仅用于开发环境）
    _DEFAULT_SECRET_KEY = 'qrtestscanner-web-secret-key-2025'
    _config_cache = None

    @staticmethod
    def _load_config() -> dict:
        """加载配置文件"""
        if SecretManager._config_cache is not None:
            return SecretManager._config_cache
        
        config_path = Path(__file__).parent.parent / 'webdav_config.json'
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                SecretManager._config_cache = json.load(f)
                return SecretManager._config_cache
        except Exception as e:
            logger.warning(f"无法加载配置文件 {config_path}: {e}")
            return {}

    @staticmethod
    def get_secret_key() -> str:
        """
        获取 Flask secret key
        优先级：环境变量 > 配置文件 > 默认值
        """
        # 1. 优先使用环境变量（用于生产环境）
        key = os.getenv('FLASK_SECRET_KEY')
        if key and len(key) >= 32:
            return key
        
        # 2. 从配置文件读取
        config = SecretManager._load_config()
        key = config.get('flask_secret_key')
        if key and len(key) >= 32:
            return key
        
        # 3. 使用默认值
        logger.debug("使用默认 secret_key（开发环境）")
        return SecretManager._DEFAULT_SECRET_KEY

    @staticmethod
    def get_db_password() -> Optional[str]:
        """获取数据库密码"""
        # 优先使用环境变量
        password = os.getenv('DB_PASSWORD')
        if password:
            return password
        
        # 从配置文件读取
        config = SecretManager._load_config()
        return config.get('db_password')

    @staticmethod
    def get_api_key(service: str) -> Optional[str]:
        """获取第三方 API 密钥"""
        # 优先使用环境变量
        key = os.getenv(f'{service.upper()}_API_KEY')
        if key:
            return key
        
        # 从配置文件读取
        config = SecretManager._load_config()
        return config.get(f'{service.lower()}_api_key')
