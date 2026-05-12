"""
统一错误处理模块
提供网络连接失败、异常情况的错误处理和用户友好的错误消息
"""

import logging
import traceback
from functools import wraps
from flask import jsonify, request
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)


class ErrorType:
    """错误类型常量"""
    NETWORK_ERROR = "network_error"
    DATABASE_ERROR = "database_error"
    AUTHENTICATION_ERROR = "authentication_error"
    PERMISSION_ERROR = "permission_error"
    VALIDATION_ERROR = "validation_error"
    FILE_ERROR = "file_error"
    UNKNOWN_ERROR = "unknown_error"


class ErrorResponse:
    """标准错误响应"""
    
    def __init__(
        self,
        error_type: str,
        code: str,
        message: str,
        user_message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.error_type = error_type
        self.code = code
        self.message = message
        self.user_message = user_message
        self.status_code = status_code
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": False,
            "error": {
                "type": self.error_type,
                "code": self.code,
                "message": self.message,
                "user_message": self.user_message,
                "details": self.details
            }
        }
    
    def to_response(self):
        """转换为Flask响应"""
        return jsonify(self.to_dict()), self.status_code


class ErrorHandler:
    """错误处理器"""
    
    @staticmethod
    def handle_network_error(exception: Exception) -> ErrorResponse:
        """处理网络错误"""
        logger.error(f"网络错误: {str(exception)}")
        logger.error(traceback.format_exc())
        
        return ErrorResponse(
            error_type=ErrorType.NETWORK_ERROR,
            code="NET_001",
            message=str(exception),
            user_message="网络连接失败，请检查网络设置后重试",
            status_code=503
        )
    
    @staticmethod
    def handle_database_error(exception: Exception) -> ErrorResponse:
        """处理数据库错误"""
        logger.error(f"数据库错误: {str(exception)}")
        logger.error(traceback.format_exc())
        
        return ErrorResponse(
            error_type=ErrorType.DATABASE_ERROR,
            code="DB_001",
            message=str(exception),
            user_message="数据库操作失败，请稍后重试",
            status_code=500
        )
    
    @staticmethod
    def handle_authentication_error(message: str = "认证失败") -> ErrorResponse:
        """处理认证错误"""
        logger.warning(f"认证错误: {message}")
        
        return ErrorResponse(
            error_type=ErrorType.AUTHENTICATION_ERROR,
            code="AUTH_001",
            message=message,
            user_message="认证失败，请重新登录",
            status_code=401
        )
    
    @staticmethod
    def handle_permission_error(message: str = "权限不足") -> ErrorResponse:
        """处理权限错误"""
        logger.warning(f"权限错误: {message}")
        
        return ErrorResponse(
            error_type=ErrorType.PERMISSION_ERROR,
            code="PERM_001",
            message=message,
            user_message="权限不足，无法执行此操作",
            status_code=403
        )
    
    @staticmethod
    def handle_validation_error(message: str, details: Optional[Dict] = None) -> ErrorResponse:
        """处理验证错误"""
        logger.warning(f"验证错误: {message}")
        
        return ErrorResponse(
            error_type=ErrorType.VALIDATION_ERROR,
            code="VAL_001",
            message=message,
            user_message=message,
            status_code=400,
            details=details
        )
    
    @staticmethod
    def handle_file_error(exception: Exception) -> ErrorResponse:
        """处理文件操作错误"""
        logger.error(f"文件错误: {str(exception)}")
        logger.error(traceback.format_exc())
        
        return ErrorResponse(
            error_type=ErrorType.FILE_ERROR,
            code="FILE_001",
            message=str(exception),
            user_message="文件操作失败，请检查文件是否存在或权限是否正确",
            status_code=500
        )
    
    @staticmethod
    def handle_unknown_error(exception: Exception) -> ErrorResponse:
        """处理未知错误"""
        logger.error(f"未知错误: {str(exception)}")
        logger.error(traceback.format_exc())
        
        return ErrorResponse(
            error_type=ErrorType.UNKNOWN_ERROR,
            code="UNK_001",
            message=str(exception),
            user_message=f"发生未知错误: {str(exception)}",
            status_code=500
        )


def handle_api_errors(f: Callable) -> Callable:
    """
    API错误处理装饰器
    自动捕获并处理API端点中的异常
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except PermissionError as e:
            error_response = ErrorHandler.handle_permission_error(str(e))
            return error_response.to_response()
        except ValueError as e:
            error_response = ErrorHandler.handle_validation_error(str(e))
            return error_response.to_response()
        except FileNotFoundError as e:
            error_response = ErrorHandler.handle_file_error(e)
            return error_response.to_response()
        except IOError as e:
            error_response = ErrorHandler.handle_file_error(e)
            return error_response.to_response()
        except ConnectionError as e:
            error_response = ErrorHandler.handle_network_error(e)
            return error_response.to_response()
        except Exception as e:
            error_response = ErrorHandler.handle_unknown_error(e)
            return error_response.to_response()
    
    return decorated_function


def log_request_info():
    """记录请求信息（用于调试）"""
    logger.info(f"请求方法: {request.method}")
    logger.info(f"请求路径: {request.path}")
    logger.info(f"请求参数: {request.args}")
    logger.info(f"请求来源: {request.remote_addr}")
    logger.info(f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}")


def create_success_response(data: Any = None, message: str = "操作成功") -> Dict[str, Any]:
    """创建成功响应"""
    response = {
        "success": True,
        "message": message
    }
    
    if data is not None:
        response["data"] = data
    
    return response


def create_error_response(
    message: str,
    error_type: str = ErrorType.UNKNOWN_ERROR,
    code: str = "ERR_001",
    details: Optional[Dict] = None
) -> Dict[str, Any]:
    """创建错误响应"""
    return {
        "success": False,
        "error": {
            "type": error_type,
            "code": code,
            "message": message,
            "user_message": message,
            "details": details or {}
        }
    }


class RequestValidator:
    """请求验证器"""
    
    @staticmethod
    def validate_required_fields(data: Dict[str, Any], required_fields: list) -> Optional[str]:
        """验证必需字段"""
        missing_fields = []
        
        for field in required_fields:
            if field not in data or data[field] is None or data[field] == "":
                missing_fields.append(field)
        
        if missing_fields:
            return f"缺少必需字段: {', '.join(missing_fields)}"
        
        return None
    
    @staticmethod
    def validate_field_types(data: Dict[str, Any], field_types: Dict[str, type]) -> Optional[str]:
        """验证字段类型"""
        for field, expected_type in field_types.items():
            if field in data and not isinstance(data[field], expected_type):
                return f"字段 '{field}' 类型错误，期望 {expected_type.__name__}"
        
        return None
    
    @staticmethod
    def validate_file_upload(file) -> Optional[str]:
        """验证文件上传"""
        if not file:
            return "未提供文件"
        
        if file.filename == '':
            return "文件名为空"
        
        # 检查文件扩展名
        allowed_extensions = {'jpg', 'jpeg', 'png', 'gif', 'bmp'}
        if '.' not in file.filename:
            return "文件没有扩展名"
        
        ext = file.filename.rsplit('.', 1)[1].lower()
        if ext not in allowed_extensions:
            return f"不支持的文件类型: {ext}，仅支持 {', '.join(allowed_extensions)}"
        
        return None


class OperationLogger:
    """操作日志记录器（增强版）"""
    
    @staticmethod
    def log_operation(
        username: str,
        operation: str,
        target: str,
        success: bool = True,
        details: str = "",
        error_message: str = ""
    ):
        """记录操作日志"""
        log_level = logging.INFO if success else logging.ERROR
        
        log_message = f"[操作日志] 用户: {username}, 操作: {operation}, 目标: {target}, 结果: {'成功' if success else '失败'}"
        
        if details:
            log_message += f", 详情: {details}"
        
        if error_message:
            log_message += f", 错误: {error_message}"
        
        logger.log(log_level, log_message)
        
        # 这里可以扩展为写入数据库或文件
        try:
            from qrmes_shared_core.auth import OperationLogger as AuthOperationLogger
            AuthOperationLogger.log_operation(
                username=username,
                operation=operation,
                target=target,
                details=details if success else error_message,
                success=success
            )
        except Exception as e:
            logger.error(f"写入操作日志失败: {e}")
