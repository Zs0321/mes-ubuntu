"""
增强日志系统
- 系统日志记录
- 用户登录日志
- 访问日志记录
- 保存到网络存储的log文件夹
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional
from functools import wraps
import traceback
from flask import request, session, g


class EnhancedLogger:
    """增强日志记录器"""
    
    def __init__(self, log_path: str = "log"):
        """
        初始化增强日志记录器
        
        Args:
            log_path: 日志保存路径（相对于WebDAV base path）
        """
        self.log_path = log_path
        self.logger = logging.getLogger('QRTestScanner')
        
    def _get_client(self):
        """获取WebDAV客户端"""
        try:
            from app import get_webdav_client
            return get_webdav_client(use_current_user=False)
        except:
            return None
    
    def _get_current_user(self) -> Dict:
        """获取当前用户信息"""
        try:
            from flask import session
            return session.get('user', {})
        except:
            return {}
    
    def _ensure_log_directory(self, client):
        """确保日志目录存在"""
        if client:
            try:
                if not client.exists(self.log_path):
                    client.create_directory(self.log_path)
                    self.logger.info(f"[日志系统] 创建日志目录: {self.log_path}")
                return True
            except Exception as e:
                self.logger.error(f"[日志系统] 创建日志目录失败: {e}")
                return False
        return False
    
    def _get_log_filename(self, log_type: str) -> str:
        """获取日志文件名"""
        today = date.today().strftime('%Y-%m-%d')
        return f"{log_type}_{today}.log"
    
    def _write_log_entry(self, log_type: str, entry: Dict[str, Any]):
        """写入日志条目"""
        client = self._get_client()
        
        if client and self._ensure_log_directory(client):
            try:
                # 网络存储日志
                log_filename = self._get_log_filename(log_type)
                log_file_path = f"{self.log_path}/{log_filename}"
                
                # 读取现有日志
                existing_content = client.read_file(log_file_path)
                
                # 格式化日志条目为单行JSON
                log_line = json.dumps(entry, ensure_ascii=False, separators=(',', ':'))
                
                if existing_content:
                    # 追加到现有内容
                    new_content = existing_content + '\n' + log_line
                else:
                    # 创建新文件
                    new_content = log_line
                
                # 写入文件
                client.write_file(log_file_path, new_content)
                
                self.logger.debug(f"[日志系统] 写入日志: {log_type} -> {log_file_path}")
                
            except Exception as e:
                self.logger.error(f"[日志系统] 写入网络日志失败: {e}")
                self._write_local_log(log_type, entry)
        else:
            # 备用本地日志
            self._write_local_log(log_type, entry)
    
    def _write_local_log(self, log_type: str, entry: Dict[str, Any]):
        """写入本地备用日志"""
        try:
            log_dir = Path(__file__).parent / "logs"
            log_dir.mkdir(exist_ok=True)
            
            log_filename = self._get_log_filename(log_type)
            log_file = log_dir / log_filename
            
            # 格式化日志条目为单行JSON
            log_line = json.dumps(entry, ensure_ascii=False, separators=(',', ':'))
            
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_line + '\n')
                
            self.logger.debug(f"[日志系统] 写入本地日志: {log_type} -> {log_file}")
            
        except Exception as e:
            self.logger.error(f"[日志系统] 写入本地日志失败: {e}")
    
    def log_system_event(self, event_type: str, message: str, details: Dict = None, 
                        level: str = 'INFO', success: bool = True):
        """记录系统事件日志"""
        user = self._get_current_user()
        
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': 'SYSTEM',
            'event_type': event_type,
            'level': level.upper(),
            'message': message,
            'details': details or {},
            'success': success,
            'user_id': user.get('username', 'system'),
            'user_name': user.get('display_name', '系统'),
            'session_id': session.get('_permanent', {}) if 'session' in globals() else None,
            'remote_addr': request.remote_addr if 'request' in globals() else None
        }
        
        self._write_log_entry('system', entry)
        
        # 同时输出到控制台
        log_msg = f"[{event_type}] {message}"
        if level.upper() == 'ERROR':
            self.logger.error(log_msg)
        elif level.upper() == 'WARNING':
            self.logger.warning(log_msg)
        else:
            self.logger.info(log_msg)
    
    def log_user_login(self, username: str, success: bool, protocol: str = None, 
                      error_message: str = None, user_agent: str = None):
        """记录用户登录日志"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': 'LOGIN',
            'username': username,
            'success': success,
            'protocol': protocol,
            'error_message': error_message,
            'remote_addr': request.remote_addr if 'request' in globals() else None,
            'user_agent': user_agent or (request.headers.get('User-Agent') if 'request' in globals() else None),
            'session_id': session.get('_permanent', {}) if 'session' in globals() else None
        }
        
        self._write_log_entry('login', entry)
        
        # 输出到控制台
        status = "成功" if success else "失败"
        log_msg = f"[用户登录] {username} 登录{status}"
        if protocol:
            log_msg += f" (协议: {protocol.upper()})"
        if error_message:
            log_msg += f" - {error_message}"
            
        if success:
            self.logger.info(log_msg)
        else:
            self.logger.warning(log_msg)
    
    def log_access(self, endpoint: str, method: str = 'GET', response_code: int = 200,
                  duration_ms: float = None, params: Dict = None):
        """记录访问日志"""
        user = self._get_current_user()
        
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': 'ACCESS',
            'endpoint': endpoint,
            'method': method.upper(),
            'response_code': response_code,
            'duration_ms': duration_ms,
            'user_id': user.get('username', 'anonymous'),
            'user_name': user.get('display_name', '匿名用户'),
            'remote_addr': request.remote_addr if 'request' in globals() else None,
            'user_agent': request.headers.get('User-Agent') if 'request' in globals() else None,
            'params': params or {},
            'session_id': session.get('_permanent', {}) if 'session' in globals() else None
        }
        
        self._write_log_entry('access', entry)
        
        # 输出到控制台（简化信息）
        log_msg = f"[访问日志] {user.get('display_name', '匿名')} {method} {endpoint} -> {response_code}"
        if duration_ms:
            log_msg += f" ({duration_ms:.1f}ms)"
            
        self.logger.debug(log_msg)
    
    def log_operation(self, operation: str, target: str, details: str = '', 
                     success: bool = True, data: Dict = None):
        """记录用户操作日志（兼容原有接口）"""
        user = self._get_current_user()
        
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': 'OPERATION',
            'operation': operation,
            'target': target,
            'details': details,
            'success': success,
            'data': data or {},
            'user_id': user.get('username', 'unknown'),
            'user_name': user.get('display_name', '未知用户'),
            'remote_addr': request.remote_addr if 'request' in globals() else None,
            'session_id': session.get('_permanent', {}) if 'session' in globals() else None
        }
        
        self._write_log_entry('operation', entry)
        
        # 输出到控制台
        status = "成功" if success else "失败"
        log_msg = f"[操作日志] {user.get('display_name', '未知')} {operation} {target} - {status}"
        if details:
            log_msg += f" ({details})"
            
        if success:
            self.logger.info(log_msg)
        else:
            self.logger.warning(log_msg)
    
    def read_logs(self, log_type: str = None, date_str: str = None, 
                 limit: int = 100) -> List[Dict]:
        """读取日志"""
        client = self._get_client()
        logs = []
        
        if client:
            try:
                if log_type and date_str:
                    # 读取特定类型和日期的日志
                    log_filename = f"{log_type}_{date_str}.log"
                    log_file_path = f"{self.log_path}/{log_filename}"
                    content = client.read_file(log_file_path)
                    
                    if content:
                        for line in content.strip().split('\n'):
                            if line.strip():
                                try:
                                    log_entry = json.loads(line)
                                    logs.append(log_entry)
                                except json.JSONDecodeError:
                                    continue
                else:
                    # 读取所有日志文件
                    try:
                        items = client.list_directory(self.log_path)
                        log_files = [item['name'] for item in items 
                                   if item['name'].endswith('.log')]
                        
                        # 按文件名排序（日期倒序）
                        log_files.sort(reverse=True)
                        
                        for log_file in log_files[:10]:  # 最多读取10个文件
                            log_file_path = f"{self.log_path}/{log_file}"
                            content = client.read_file(log_file_path)
                            
                            if content:
                                for line in content.strip().split('\n'):
                                    if line.strip():
                                        try:
                                            log_entry = json.loads(line)
                                            logs.append(log_entry)
                                        except json.JSONDecodeError:
                                            continue
                                            
                    except Exception as e:
                        self.logger.error(f"[日志系统] 读取日志目录失败: {e}")
                        
            except Exception as e:
                self.logger.error(f"[日志系统] 读取网络日志失败: {e}")
                
        # 按时间戳倒序排序并限制数量
        logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return logs[:limit]


# 全局日志实例
enhanced_logger = EnhancedLogger()


def log_access_decorator(f):
    """访问日志装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = datetime.now()
        
        try:
            result = f(*args, **kwargs)
            
            # 计算执行时间
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            # 记录访问日志
            enhanced_logger.log_access(
                endpoint=request.endpoint or f.__name__,
                method=request.method,
                response_code=200,
                duration_ms=duration,
                params=dict(request.args) if request.args else None
            )
            
            return result
            
        except Exception as e:
            # 记录错误访问
            duration = (datetime.now() - start_time).total_seconds() * 1000
            enhanced_logger.log_access(
                endpoint=request.endpoint or f.__name__,
                method=request.method,
                response_code=500,
                duration_ms=duration
            )
            
            # 记录系统错误
            enhanced_logger.log_system_event(
                event_type='ERROR',
                message=f'访问 {request.endpoint or f.__name__} 时发生异常',
                details={
                    'error': str(e),
                    'traceback': traceback.format_exc()
                },
                level='ERROR',
                success=False
            )
            
            raise
            
    return decorated_function