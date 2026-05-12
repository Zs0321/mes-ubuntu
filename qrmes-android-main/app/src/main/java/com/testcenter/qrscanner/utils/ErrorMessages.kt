package com.testcenter.qrscanner.utils

import android.content.Context

/**
 * Utility object for providing localized, user-friendly error messages.
 */
object ErrorMessages {

    /**
     * Maps technical login or network errors into concise user-facing Chinese.
     */
    fun getLocalizedMessage(error: String, context: Context): String {
        val message = error.trim()

        return when {
            message.contains("用户名或密码错误", ignoreCase = true) ||
                message.contains("401", ignoreCase = true) ||
                message.contains("103", ignoreCase = true) ->
                "用户名或密码错误，请重新输入。"

            message.contains("用户未在用户管理中启用", ignoreCase = true) ||
                message.contains("未在用户管理", ignoreCase = true) ||
                message.contains("403", ignoreCase = true) ->
                "当前账号未在用户管理名单中启用，请联系管理员开通。"

            message.contains("首次登录", ignoreCase = true) ||
                message.contains("必须修改密码", ignoreCase = true) ||
                message.contains("require_password_change", ignoreCase = true) ->
                "当前账号需要先修改默认密码后才能继续使用。"

            message.contains("timeout", ignoreCase = true) ||
                message.contains("SocketTimeout", ignoreCase = true) ->
                "登录请求超时，请检查网络后重试。"

            message.contains("UnknownHost", ignoreCase = true) ||
                message.contains("Unable to resolve host", ignoreCase = true) ->
                "无法连接服务器，请检查网络或服务器地址。"

            message.contains("Connection refused", ignoreCase = true) ->
                "服务器拒绝连接，请确认 172.16.30.10:8891 服务正常。"

            message.contains("Network is unreachable", ignoreCase = true) ||
                message.contains("No route to host", ignoreCase = true) ->
                "当前网络无法访问服务器，请检查手机网络连接。"

            message.contains("SSL", ignoreCase = true) ||
                message.contains("certificate", ignoreCase = true) ||
                message.contains("PKIX", ignoreCase = true) ||
                message.contains("CertPathValidator", ignoreCase = true) ->
                "服务器证书校验失败，请联系管理员检查 HTTPS 配置。"

            message.contains("HTTP 404", ignoreCase = true) ||
                message.contains("登录接口不可用", ignoreCase = true) ->
                "登录接口不可用，请确认服务器部署正常。"

            message.contains("HTTP 5", ignoreCase = true) ||
                message.contains("服务器处理登录请求失败", ignoreCase = true) ->
                "服务器处理登录请求失败，请稍后再试。"

            message.isBlank() ->
                "登录失败，请稍后重试。"

            message.startsWith("登录") ->
                message

            else -> "登录失败：$message"
        }
    }

    fun getSynologyAuthStatusMessage(isAttempting: Boolean): String {
        return if (isAttempting) {
            "正在尝试 DSM 认证..."
        } else {
            "DSM 认证失败，正在尝试备用方式..."
        }
    }

    fun getAuthMethodName(method: String): String {
        return when (method.uppercase()) {
            "API" -> "本地API"
            "SYNOLOGY" -> "DSM"
            "WEBDAV" -> "WebDAV"
            "SMB" -> "SMB"
            else -> method
        }
    }
}
