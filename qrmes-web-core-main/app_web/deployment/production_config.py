"""
生产环境配置文件
用于配置生产环境的数据库、文件存储和群晖服务器访问
"""

import os
from pathlib import Path

class ProductionConfig:
    """生产环境配置"""
    
    # ==================== 基础配置 ====================
    ENV = 'production'
    DEBUG = False
    TESTING = False
    
    # Flask密钥（生产环境必须更改）
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'CHANGE-THIS-IN-PRODUCTION'
    
    # ==================== 数据库配置 ====================
    # H2数据库配置
    H2_DATABASE_PATH = '/volume2/MES/data/product_records.db'
    H2_API_ENABLED = True
    H2_API_TIMEOUT = 30  # 秒
    
    # SQLite本地缓存数据库（用于用户权限等）
    SQLITE_DATABASE_PATH = '/volume2/MES/data/users.db'
    
    # ==================== 文件存储配置 ====================
    # 使用NAS本机路径（推荐）
    USE_WEBDAV = False
    NAS_LOCAL_BASE_PATH = '/volume2/MES/files'
    
    # 项目配置文件路径
    PROJECTS_FILE = f'{NAS_LOCAL_BASE_PATH}/projects.json'
    PROJECTS_CONFIG_DIR = f'{NAS_LOCAL_BASE_PATH}/projects'
    
    # CSV记录文件路径
    CSV_DIR = f'{NAS_LOCAL_BASE_PATH}/record'
    
    # 工序照片存储路径
    PHOTO_STORAGE_PATH = f'{NAS_LOCAL_BASE_PATH}/photos'
    PHOTO_MAX_SIZE_MB = 10  # 单张照片最大10MB
    PHOTO_ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
    
    # ==================== 群晖API配置 ====================
    # 群晖DSM API配置
    SYNOLOGY_HOST = os.environ.get('SYNOLOGY_HOST', '172.16.30.2')
    SYNOLOGY_PORT = os.environ.get('SYNOLOGY_PORT', '5000')
    SYNOLOGY_USE_HTTPS = os.environ.get('SYNOLOGY_USE_HTTPS', 'false').lower() == 'true'
    SYNOLOGY_API_VERSION = '6'
    
    # 群晖API超时设置
    SYNOLOGY_TIMEOUT = 10  # 秒
    
    # ==================== WebDAV配置（备用） ====================
    # 如果需要使用WebDAV而非本机路径
    WEBDAV_URL = os.environ.get('WEBDAV_URL', 'http://172.16.30.2:5005')
    WEBDAV_USERNAME = os.environ.get('WEBDAV_USERNAME', '')
    WEBDAV_PASSWORD = os.environ.get('WEBDAV_PASSWORD', '')
    WEBDAV_BASE_PATH = '/MES/files'
    
    # ==================== 应用服务配置 ====================
    # 服务器配置
    HOST = '0.0.0.0'
    PORT = 8891
    
    # 会话配置
    PERMANENT_SESSION_LIFETIME = 3600 * 24  # 24小时
    SESSION_COOKIE_SECURE = False  # 如果使用HTTPS，设置为True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # ==================== 日志配置 ====================
    LOG_LEVEL = 'INFO'
    LOG_FILE = '/var/log/mesapp.log'
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5
    
    # ==================== 安全配置 ====================
    # 密码哈希配置
    PASSWORD_HASH_METHOD = 'pbkdf2:sha256'
    PASSWORD_SALT_LENGTH = 16
    
    # 操作审计日志
    AUDIT_LOG_ENABLED = True
    AUDIT_LOG_FILE = '/var/log/mesapp_audit.log'
    
    # 文件上传安全
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    
    # ==================== 性能配置 ====================
    # 缓存配置
    CACHE_ENABLED = True
    CACHE_TYPE = 'simple'  # 可选: 'redis', 'memcached'
    CACHE_DEFAULT_TIMEOUT = 300  # 5分钟
    
    # 权限缓存
    PERMISSION_CACHE_TIMEOUT = 600  # 10分钟
    
    # ==================== 备份配置 ====================
    BACKUP_ENABLED = True
    BACKUP_DIR = '/volume2/MES/backups'
    BACKUP_RETENTION_DAYS = 30
    
    @classmethod
    def init_app(cls, app):
        """初始化应用配置"""
        # 确保必要的目录存在
        directories = [
            cls.NAS_LOCAL_BASE_PATH,
            cls.PROJECTS_CONFIG_DIR,
            cls.CSV_DIR,
            cls.PHOTO_STORAGE_PATH,
            cls.BACKUP_DIR,
            Path(cls.LOG_FILE).parent,
            Path(cls.SQLITE_DATABASE_PATH).parent,
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
        
        # 配置日志
        import logging
        from logging.handlers import RotatingFileHandler
        
        handler = RotatingFileHandler(
            cls.LOG_FILE,
            maxBytes=cls.LOG_MAX_BYTES,
            backupCount=cls.LOG_BACKUP_COUNT
        )
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        handler.setLevel(getattr(logging, cls.LOG_LEVEL))
        
        app.logger.addHandler(handler)
        app.logger.setLevel(getattr(logging, cls.LOG_LEVEL))
        
        # 配置审计日志
        if cls.AUDIT_LOG_ENABLED:
            audit_handler = RotatingFileHandler(
                cls.AUDIT_LOG_FILE,
                maxBytes=cls.LOG_MAX_BYTES,
                backupCount=cls.LOG_BACKUP_COUNT
            )
            audit_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(message)s'
            ))
            
            audit_logger = logging.getLogger('audit')
            audit_logger.addHandler(audit_handler)
            audit_logger.setLevel(logging.INFO)


# 环境变量配置映射
config_by_name = {
    'production': ProductionConfig,
}


def get_config(env_name='production'):
    """获取配置对象"""
    return config_by_name.get(env_name, ProductionConfig)
