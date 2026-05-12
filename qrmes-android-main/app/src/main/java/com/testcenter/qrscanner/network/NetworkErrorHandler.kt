package com.testcenter.qrscanner.network

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import com.testcenter.qrscanner.utils.AppLogger
import java.io.IOException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLException

/**
 * 网络错误处理器
 * 统一处理网络连接失败、超时等异常情况
 */
class NetworkErrorHandler(private val context: Context) {
    
    companion object {
        private const val TAG = "NetworkErrorHandler"
    }
    
    /**
     * 网络错误类型
     */
    enum class NetworkErrorType {
        NO_INTERNET,           // 无网络连接
        CONNECTION_TIMEOUT,    // 连接超时
        SERVER_UNREACHABLE,    // 服务器无法访问
        SSL_ERROR,             // SSL证书错误
        AUTHENTICATION_FAILED, // 认证失败
        PERMISSION_DENIED,     // 权限拒绝
        SERVER_ERROR,          // 服务器内部错误
        UNKNOWN                // 未知错误
    }
    
    /**
     * 错误响应数据类
     */
    data class ErrorResponse(
        val type: NetworkErrorType,
        val code: String,
        val message: String,
        val userMessage: String,
        val action: ErrorAction,
        val retryable: Boolean = false
    )
    
    /**
     * 错误处理动作
     */
    enum class ErrorAction {
        RETRY,              // 重试操作
        RE_LOGIN,           // 重新登录
        REDIRECT_LOGIN,     // 跳转到登录页
        SHOW_MESSAGE,       // 仅显示消息
        ENABLE_OFFLINE_MODE // 启用离线模式
    }
    
    /**
     * 检查网络连接状态
     */
    fun isNetworkAvailable(): Boolean {
        val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = connectivityManager.activeNetwork ?: return false
        val capabilities = connectivityManager.getNetworkCapabilities(network) ?: return false
        
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
               capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }
    
    /**
     * 获取网络类型
     */
    fun getNetworkType(): String {
        val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = connectivityManager.activeNetwork ?: return "无网络"
        val capabilities = connectivityManager.getNetworkCapabilities(network) ?: return "未知"
        
        return when {
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "WiFi"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "移动数据"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "以太网"
            else -> "其他"
        }
    }
    
    /**
     * 处理异常并返回错误响应
     */
    fun handleException(exception: Exception): ErrorResponse {
        AppLogger.log(TAG, "处理异常: ${exception.javaClass.simpleName} - ${exception.message}")
        
        return when (exception) {
            is UnknownHostException -> {
                if (!isNetworkAvailable()) {
                    ErrorResponse(
                        type = NetworkErrorType.NO_INTERNET,
                        code = "NET_001",
                        message = "No internet connection available",
                        userMessage = "网络连接不可用，请检查网络设置",
                        action = ErrorAction.ENABLE_OFFLINE_MODE,
                        retryable = true
                    )
                } else {
                    ErrorResponse(
                        type = NetworkErrorType.SERVER_UNREACHABLE,
                        code = "NET_002",
                        message = "Server unreachable: ${exception.message}",
                        userMessage = "无法连接到服务器，请稍后重试",
                        action = ErrorAction.RETRY,
                        retryable = true
                    )
                }
            }
            
            is SocketTimeoutException -> {
                ErrorResponse(
                    type = NetworkErrorType.CONNECTION_TIMEOUT,
                    code = "NET_003",
                    message = "Connection timeout: ${exception.message}",
                    userMessage = "连接超时，请检查网络状况后重试",
                    action = ErrorAction.RETRY,
                    retryable = true
                )
            }
            
            is SSLException -> {
                ErrorResponse(
                    type = NetworkErrorType.SSL_ERROR,
                    code = "NET_004",
                    message = "SSL error: ${exception.message}",
                    userMessage = "安全连接失败，请检查服务器证书配置",
                    action = ErrorAction.SHOW_MESSAGE,
                    retryable = false
                )
            }
            
            is IOException -> {
                ErrorResponse(
                    type = NetworkErrorType.SERVER_UNREACHABLE,
                    code = "NET_005",
                    message = "IO error: ${exception.message}",
                    userMessage = "网络通信失败，请检查网络连接",
                    action = ErrorAction.RETRY,
                    retryable = true
                )
            }
            
            else -> {
                ErrorResponse(
                    type = NetworkErrorType.UNKNOWN,
                    code = "NET_999",
                    message = "Unknown error: ${exception.message}",
                    userMessage = "发生未知错误: ${exception.message ?: "未知原因"}",
                    action = ErrorAction.SHOW_MESSAGE,
                    retryable = false
                )
            }
        }
    }
    
    /**
     * 处理HTTP错误代码
     */
    fun handleHttpError(statusCode: Int, responseBody: String? = null): ErrorResponse {
        AppLogger.log(TAG, "处理HTTP错误: $statusCode")
        
        return when (statusCode) {
            401 -> ErrorResponse(
                type = NetworkErrorType.AUTHENTICATION_FAILED,
                code = "HTTP_401",
                message = "Authentication failed",
                userMessage = "认证失败，请重新登录",
                action = ErrorAction.REDIRECT_LOGIN,
                retryable = false
            )
            
            403 -> ErrorResponse(
                type = NetworkErrorType.PERMISSION_DENIED,
                code = "HTTP_403",
                message = "Permission denied",
                userMessage = "权限不足，无法执行此操作",
                action = ErrorAction.SHOW_MESSAGE,
                retryable = false
            )
            
            404 -> ErrorResponse(
                type = NetworkErrorType.SERVER_ERROR,
                code = "HTTP_404",
                message = "Resource not found",
                userMessage = "请求的资源不存在",
                action = ErrorAction.SHOW_MESSAGE,
                retryable = false
            )
            
            408 -> ErrorResponse(
                type = NetworkErrorType.CONNECTION_TIMEOUT,
                code = "HTTP_408",
                message = "Request timeout",
                userMessage = "请求超时，请重试",
                action = ErrorAction.RETRY,
                retryable = true
            )
            
            500, 502, 503, 504 -> ErrorResponse(
                type = NetworkErrorType.SERVER_ERROR,
                code = "HTTP_$statusCode",
                message = "Server error: $statusCode",
                userMessage = "服务器错误，请稍后重试",
                action = ErrorAction.RETRY,
                retryable = true
            )
            
            else -> ErrorResponse(
                type = NetworkErrorType.UNKNOWN,
                code = "HTTP_$statusCode",
                message = "HTTP error: $statusCode",
                userMessage = "请求失败 (错误代码: $statusCode)",
                action = ErrorAction.SHOW_MESSAGE,
                retryable = false
            )
        }
    }
    
    /**
     * 获取用户友好的错误提示
     */
    fun getUserFriendlyMessage(exception: Exception): String {
        return handleException(exception).userMessage
    }
    
    /**
     * 判断错误是否可重试
     */
    fun isRetryable(exception: Exception): Boolean {
        return handleException(exception).retryable
    }
}
