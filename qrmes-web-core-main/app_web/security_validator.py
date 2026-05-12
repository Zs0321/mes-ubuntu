"""
安全验证模块
实现文件上传安全检查、权限验证增强和操作审计日志
"""

import os
import hashlib
import mimetypes
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage

logger = logging.getLogger(__name__)


class FileSecurityValidator:
    """文件安全验证器"""
    
    # 允许的文件扩展名
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'}
    
    # 允许的MIME类型
    ALLOWED_MIME_TYPES = {
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/bmp',
        'image/webp'
    }
    
    # 最大文件大小（字节）
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    # 危险文件头特征（用于检测伪装文件）
    DANGEROUS_SIGNATURES = {
        b'MZ': 'Windows可执行文件',
        b'\x7fELF': 'Linux可执行文件',
        b'#!/': '脚本文件',
        b'<?php': 'PHP脚本',
        b'<script': 'JavaScript脚本'
    }
    
    @staticmethod
    def validate_file_upload(file: FileStorage) -> Dict[str, Any]:
        """
        验证上传的文件
        返回: {
            'valid': bool,
            'error': str or None,
            'warnings': list
        }
        """
        warnings = []
        
        # 检查文件是否存在
        if not file or not file.filename:
            return {
                'valid': False,
                'error': '未提供文件或文件名为空',
                'warnings': []
            }
        
        # 检查文件名
        filename = secure_filename(file.filename)
        if not filename:
            return {
                'valid': False,
                'error': '文件名无效',
                'warnings': []
            }
        
        # 检查文件扩展名
        if '.' not in filename:
            return {
                'valid': False,
                'error': '文件没有扩展名',
                'warnings': []
            }
        
        ext = filename.rsplit('.', 1)[1].lower()
        if ext not in FileSecurityValidator.ALLOWED_EXTENSIONS:
            return {
                'valid': False,
                'error': f'不支持的文件类型: {ext}',
                'warnings': []
            }
        
        # 检查文件大小
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size == 0:
            return {
                'valid': False,
                'error': '文件为空',
                'warnings': []
            }
        
        if file_size > FileSecurityValidator.MAX_FILE_SIZE:
            return {
                'valid': False,
                'error': f'文件过大: {file_size / (1024*1024):.2f}MB，最大允许 {FileSecurityValidator.MAX_FILE_SIZE / (1024*1024):.0f}MB',
                'warnings': []
            }
        
        # 检查MIME类型
        mime_type = file.content_type
        if mime_type not in FileSecurityValidator.ALLOWED_MIME_TYPES:
            warnings.append(f'MIME类型不在白名单中: {mime_type}')
        
        # 检查文件头（魔数）
        file_header = file.read(512)
        file.seek(0)
        
        # 检测危险文件特征
        for signature, description in FileSecurityValidator.DANGEROUS_SIGNATURES.items():
            if file_header.startswith(signature):
                return {
                    'valid': False,
                    'error': f'检测到危险文件类型: {description}',
                    'warnings': []
                }
        
        # 验证图片文件头
        if not FileSecurityValidator._is_valid_image_header(file_header, ext):
            return {
                'valid': False,
                'error': '文件头与扩展名不匹配，可能是伪装文件',
                'warnings': []
            }
        
        logger.info(f"文件验证通过: {filename}, 大小: {file_size}字节")
        
        return {
            'valid': True,
            'error': None,
            'warnings': warnings
        }
    
    @staticmethod
    def _is_valid_image_header(header: bytes, ext: str) -> bool:
        """验证图片文件头"""
        image_signatures = {
            'jpg': [b'\xff\xd8\xff'],
            'jpeg': [b'\xff\xd8\xff'],
            'png': [b'\x89PNG\r\n\x1a\n'],
            'gif': [b'GIF87a', b'GIF89a'],
            'bmp': [b'BM'],
            'webp': [b'RIFF']
        }
        
        signatures = image_signatures.get(ext, [])
        for signature in signatures:
            if header.startswith(signature):
                return True
        
        return False
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """清理文件名，移除危险字符"""
        # 使用werkzeug的secure_filename
        safe_name = secure_filename(filename)
        
        # 进一步清理
        safe_name = safe_name.replace('..', '')
        safe_name = safe_name.replace('/', '')
        safe_name = safe_name.replace('\\', '')
        
        return safe_name
    
    @staticmethod
    def calculate_file_hash(file: FileStorage) -> str:
        """计算文件的SHA256哈希值"""
        sha256_hash = hashlib.sha256()
        
        file.seek(0)
        for byte_block in iter(lambda: file.read(4096), b""):
            sha256_hash.update(byte_block)
        file.seek(0)
        
        return sha256_hash.hexdigest()


class PermissionSecurityValidator:
    """权限安全验证器"""
    
    # 敏感操作列表
    SENSITIVE_OPERATIONS = {
        'delete_record',
        'modify_record',
        'delete_user',
        'modify_user_role',
        'modify_config',
        'export_data'
    }
    
    @staticmethod
    def validate_permission(
        username: str,
        role: str,
        operation: str,
        target: str = ""
    ) -> Dict[str, Any]:
        """
        验证用户权限
        返回: {
            'allowed': bool,
            'reason': str,
            'requires_audit': bool
        }
        """
        # 管理员拥有所有权限
        if role == 'admin':
            return {
                'allowed': True,
                'reason': '管理员权限',
                'requires_audit': operation in PermissionSecurityValidator.SENSITIVE_OPERATIONS
            }
        
        # 普通用户权限检查
        allowed_operations = {
            'view_record',
            'create_record',
            'view_photo',
            'upload_photo'
        }
        
        if operation in allowed_operations:
            return {
                'allowed': True,
                'reason': '用户权限',
                'requires_audit': False
            }
        
        logger.warning(f"权限拒绝: 用户 {username} (角色: {role}) 尝试执行 {operation}")
        
        return {
            'allowed': False,
            'reason': f'角色 {role} 无权执行 {operation} 操作',
            'requires_audit': True
        }
    
    @staticmethod
    def check_rate_limit(username: str, operation: str, max_requests: int = 100, window_seconds: int = 60) -> bool:
        """
        检查操作频率限制（简单实现）
        实际应用中应使用Redis等缓存系统
        """
        # 这里是简化实现，实际应该使用持久化存储
        # 返回True表示未超过限制
        return True


class AuditLogger:
    """操作审计日志记录器"""
    
    @staticmethod
    def log_security_event(
        event_type: str,
        username: str,
        operation: str,
        target: str = "",
        result: str = "success",
        details: Dict[str, Any] = None,
        ip_address: str = "",
        user_agent: str = ""
    ):
        """
        记录安全事件
        
        event_type: 事件类型 (authentication, authorization, file_upload, data_access, etc.)
        username: 用户名
        operation: 操作类型
        target: 操作目标
        result: 操作结果 (success, failure, denied)
        details: 详细信息
        ip_address: IP地址
        user_agent: 用户代理
        """
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'event_type': event_type,
            'username': username,
            'operation': operation,
            'target': target,
            'result': result,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'details': details or {}
        }
        
        # 记录到日志文件
        log_level = logging.WARNING if result in ['failure', 'denied'] else logging.INFO
        logger.log(
            log_level,
            f"[安全审计] {event_type} | {username} | {operation} | {target} | {result}"
        )
        
        # 这里可以扩展为写入专门的审计日志数据库
        try:
            AuditLogger._write_to_audit_log(log_entry)
        except Exception as e:
            logger.error(f"写入审计日志失败: {e}")
    
    @staticmethod
    def _write_to_audit_log(log_entry: Dict[str, Any]):
        """写入审计日志文件"""
        import json
        from pathlib import Path
        
        # 创建审计日志目录
        audit_dir = Path(__file__).parent / "logs" / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        
        # 按日期创建日志文件
        date_str = datetime.now().strftime("%Y%m%d")
        audit_file = audit_dir / f"audit_{date_str}.log"
        
        # 追加日志
        with open(audit_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    @staticmethod
    def log_authentication_attempt(
        username: str,
        success: bool,
        ip_address: str = "",
        user_agent: str = "",
        error_message: str = ""
    ):
        """记录认证尝试"""
        AuditLogger.log_security_event(
            event_type='authentication',
            username=username,
            operation='login',
            result='success' if success else 'failure',
            details={'error': error_message} if error_message else {},
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @staticmethod
    def log_permission_check(
        username: str,
        operation: str,
        target: str,
        allowed: bool,
        ip_address: str = ""
    ):
        """记录权限检查"""
        AuditLogger.log_security_event(
            event_type='authorization',
            username=username,
            operation=operation,
            target=target,
            result='success' if allowed else 'denied',
            ip_address=ip_address
        )
    
    @staticmethod
    def log_file_upload(
        username: str,
        filename: str,
        file_size: int,
        file_hash: str,
        success: bool,
        ip_address: str = ""
    ):
        """记录文件上传"""
        AuditLogger.log_security_event(
            event_type='file_upload',
            username=username,
            operation='upload',
            target=filename,
            result='success' if success else 'failure',
            details={
                'file_size': file_size,
                'file_hash': file_hash
            },
            ip_address=ip_address
        )
    
    @staticmethod
    def log_data_access(
        username: str,
        operation: str,
        target: str,
        record_count: int = 0,
        ip_address: str = ""
    ):
        """记录数据访问"""
        AuditLogger.log_security_event(
            event_type='data_access',
            username=username,
            operation=operation,
            target=target,
            result='success',
            details={'record_count': record_count},
            ip_address=ip_address
        )


def get_client_ip(request) -> str:
    """获取客户端IP地址"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr or 'unknown'


def get_user_agent(request) -> str:
    """获取用户代理"""
    return request.headers.get('User-Agent', 'unknown')
