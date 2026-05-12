package com.testcenter.qrscanner.auth

import android.util.Log
import com.testcenter.qrscanner.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * 群晖认证客户端
 * 实现与群晖DSM API的通信接口，提供用户身份验证、会话管理和令牌处理功能
 */
class SynologyAuthClient(
    private val baseUrl: String,
    private val timeout: Int = 10000  // 10 seconds timeout as per requirements
) {
    companion object {
        private const val TAG = "SynologyAuthClient"
        private const val AUTH_API = "/webapi/auth.cgi"
        private const val INFO_API = "/webapi/query.cgi"
    }

    /**
     * 认证结果数据类
     */
    data class AuthResult(
        val success: Boolean,
        val token: String? = null,
        val refreshToken: String? = null,
        val userInfo: UserInfo? = null,
        val error: String? = null,
        val sessionId: String? = null
    )

    /**
     * 用户信息数据类
     */
    data class UserInfo(
        val username: String,
        val displayName: String,
        val email: String? = null,
        val groups: List<String>? = null,
        val uid: Int? = null
    )

    /**
     * 令牌对数据类
     */
    data class TokenPair(
        val accessToken: String,
        val refreshToken: String,
        val expiresIn: Int
    )

    /**
     * 发送API请求（GET，用于非敏感查询）
     */
    private suspend fun makeGetRequest(endpoint: String, params: Map<String, String>): JSONObject? {
        return withContext(Dispatchers.IO) {
            try {
                val urlBuilder = StringBuilder("${baseUrl.trimEnd('/')}$endpoint")

                if (params.isNotEmpty()) {
                    urlBuilder.append("?")
                    params.entries.forEachIndexed { index, entry ->
                        if (index > 0) urlBuilder.append("&")
                        urlBuilder.append("${URLEncoder.encode(entry.key, "UTF-8")}=${URLEncoder.encode(entry.value, "UTF-8")}")
                    }
                }

                val url = URL(urlBuilder.toString())
                if (BuildConfig.DEBUG) Log.d(TAG, "发送GET请求到: ${url.path}")

                val connection = url.openConnection() as HttpURLConnection
                connection.apply {
                    requestMethod = "GET"
                    connectTimeout = timeout
                    readTimeout = timeout
                    setRequestProperty("User-Agent", "QRTestScanner-Android/1.0")
                    setRequestProperty("Accept", "application/json")
                }

                readResponse(connection)
            } catch (e: Exception) {
                Log.e(TAG, "请求异常: ${e.message}")
                null
            }
        }
    }

    /**
     * 发送API请求（POST，用于含凭证的敏感操作）
     */
    private suspend fun makePostRequest(endpoint: String, params: Map<String, String>): JSONObject? {
        return withContext(Dispatchers.IO) {
            try {
                val url = URL("${baseUrl.trimEnd('/')}$endpoint")
                if (BuildConfig.DEBUG) Log.d(TAG, "发送POST请求到: ${url.path}")

                val connection = url.openConnection() as HttpURLConnection
                connection.apply {
                    requestMethod = "POST"
                    connectTimeout = timeout
                    readTimeout = timeout
                    doOutput = true
                    setRequestProperty("User-Agent", "QRTestScanner-Android/1.0")
                    setRequestProperty("Accept", "application/json")
                    setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
                }

                // 将参数写入请求体而非 URL
                val postData = params.entries.joinToString("&") { entry ->
                    "${URLEncoder.encode(entry.key, "UTF-8")}=${URLEncoder.encode(entry.value, "UTF-8")}"
                }
                OutputStreamWriter(connection.outputStream).use { it.write(postData) }

                readResponse(connection)
            } catch (e: Exception) {
                Log.e(TAG, "请求异常: ${e.message}")
                null
            }
        }
    }

    /**
     * 读取 HTTP 响应
     */
    private fun readResponse(connection: HttpURLConnection): JSONObject? {
        val responseCode = connection.responseCode
        if (BuildConfig.DEBUG) Log.d(TAG, "响应代码: $responseCode")

        return if (responseCode == HttpURLConnection.HTTP_OK) {
            val response = BufferedReader(InputStreamReader(connection.inputStream)).use { it.readText() }
            // 不记录完整响应（可能含 session ID 等敏感信息）
            if (BuildConfig.DEBUG) Log.d(TAG, "收到响应 (${response.length} bytes)")
            connection.disconnect()
            JSONObject(response)
        } else {
            Log.e(TAG, "HTTP错误: $responseCode")
            connection.disconnect()
            null
        }
    }

    /**
     * 获取API信息
     */
    suspend fun getApiInfo(): JSONObject? {
        val params = mapOf(
            "api" to "SYNO.API.Info",
            "version" to "1",
            "method" to "query",
            "query" to "SYNO.API.Auth"
        )

        val response = makeGetRequest(INFO_API, params)
        return if (response?.optBoolean("success") == true) {
            response.optJSONObject("data")
        } else {
            Log.w(TAG, "获取API信息失败")
            null
        }
    }

    /**
     * 用户身份验证
     */
    suspend fun authenticate(username: String, password: String): AuthResult {
        Log.i(TAG, "开始认证用户: $username")

        if (username.isBlank() || password.isBlank()) {
            return AuthResult(
                success = false,
                error = "用户名或密码不能为空"
            )
        }

        val params = mapOf(
            "api" to "SYNO.API.Auth",
            "version" to "3",
            "method" to "login",
            "account" to username,
            "passwd" to password,
            "session" to "QRTestScanner",
            "format" to "sid"
        )

        return try {
            val response = makePostRequest(AUTH_API, params)

            if (response == null) {
                AuthResult(
                    success = false,
                    error = "无法连接到群晖服务器"
                )
            } else if (response.optBoolean("success")) {
                val data = response.optJSONObject("data")
                val sessionId = data?.optString("sid")

                if (!sessionId.isNullOrEmpty()) {
                    // 获取用户详细信息
                    val userInfo = getUserInfo(username, sessionId)

                    Log.i(TAG, "用户 $username 认证成功")
                    AuthResult(
                        success = true,
                        token = sessionId,
                        sessionId = sessionId,
                        userInfo = userInfo
                    )
                } else {
                    AuthResult(
                        success = false,
                        error = "认证成功但未获取到会话ID"
                    )
                }
            } else {
                val errorCode = response.optJSONObject("error")?.optString("code", "unknown")
                val errorMsg = getErrorMessage(errorCode ?: "unknown")

                Log.w(TAG, "用户 $username 认证失败: $errorMsg (代码: $errorCode)")
                AuthResult(
                    success = false,
                    error = errorMsg
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "认证过程异常: ${e.message}", e)
            AuthResult(
                success = false,
                error = "认证过程发生异常: ${e.message}"
            )
        }
    }

    /**
     * 获取用户详细信息
     */
    private suspend fun getUserInfo(username: String, sessionId: String): UserInfo? {
        return try {
            val params = mapOf(
                "api" to "SYNO.Core.User",
                "version" to "1",
                "method" to "get",
                "_sid" to sessionId
            )

            val response = makeGetRequest("/webapi/entry.cgi", params)

            if (response?.optBoolean("success") == true) {
                val data = response.optJSONObject("data")
                UserInfo(
                    username = username,
                    displayName = data?.optString("fullname", username) ?: username,
                    email = data?.optString("email"),
                    groups = data?.optJSONArray("groups")?.let { array ->
                        (0 until array.length()).map { array.getString(it) }
                    },
                    uid = data?.optInt("uid")
                )
            } else {
                // 如果无法获取详细信息，返回基本信息
                UserInfo(
                    username = username,
                    displayName = username,
                    email = null,
                    groups = emptyList(),
                    uid = null
                )
            }
        } catch (e: Exception) {
            Log.w(TAG, "获取用户信息失败: ${e.message}", e)
            UserInfo(
                username = username,
                displayName = username,
                email = null,
                groups = emptyList(),
                uid = null
            )
        }
    }

    /**
     * 验证会话有效性
     */
    suspend fun validateSession(sessionId: String): UserInfo? {
        if (sessionId.isBlank()) {
            return null
        }

        return try {
            val params = mapOf(
                "api" to "SYNO.API.Info",
                "version" to "1",
                "method" to "query",
                "query" to "all",
                "_sid" to sessionId
            )

            val response = makeGetRequest(INFO_API, params)

            if (response?.optBoolean("success") == true) {
                Log.d(TAG, "会话验证成功")
                // 这里无法直接获取用户名，需要在调用时提供
                UserInfo(username = "unknown", displayName = "unknown")
            } else {
                Log.w(TAG, "会话验证失败")
                null
            }
        } catch (e: Exception) {
            Log.e(TAG, "会话验证异常: ${e.message}", e)
            null
        }
    }

    /**
     * 登出并销毁会话
     */
    suspend fun logout(sessionId: String): Boolean {
        if (sessionId.isBlank()) {
            return true
        }

        return try {
            val params = mapOf(
                "api" to "SYNO.API.Auth",
                "version" to "1",
                "method" to "logout",
                "session" to "QRTestScanner",
                "_sid" to sessionId
            )

            val response = makeGetRequest(AUTH_API, params)

            if (response?.optBoolean("success") == true) {
                Log.i(TAG, "登出成功")
                true
            } else {
                Log.w(TAG, "登出失败")
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "登出异常: ${e.message}", e)
            false
        }
    }

    /**
     * 测试与群晖服务器的连接
     */
    suspend fun testConnection(): Boolean {
        return try {
            val apiInfo = getApiInfo()
            if (apiInfo != null) {
                Log.i(TAG, "群晖服务器连接测试成功")
                true
            } else {
                Log.w(TAG, "群晖服务器连接测试失败")
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "连接测试异常: ${e.message}", e)
            false
        }
    }

    /**
     * 根据错误代码获取错误消息
     */
    private fun getErrorMessage(errorCode: String): String {
        return when (errorCode) {
            "400" -> "无效的参数"
            "401" -> "用户名或密码错误"
            "402" -> "访问被拒绝"
            "403" -> "一次性密码未提供"
            "404" -> "一次性密码认证失败"
            "405" -> "用户被禁用"
            "406" -> "权限被拒绝"
            "407" -> "一次性密码已过期"
            "408" -> "密码已过期"
            "409" -> "密码必须更改"
            "410" -> "账户被锁定"
            "411" -> "账户已过期"
            "412" -> "密码历史不符合要求"
            "413" -> "密码强度不符合要求"
            "414" -> "密码字符不符合要求"
            "415" -> "密码不能包含用户名"
            "416" -> "密码不能包含用户描述"
            "417" -> "密码已被使用"
            "418" -> "密码必须包含字母"
            "419" -> "密码必须包含数字"
            "420" -> "密码必须包含特殊字符"
            "421" -> "密码必须包含大写字母"
            "422" -> "密码必须包含小写字母"
            else -> "未知错误 (代码: $errorCode)"
        }
    }
}