package com.testcenter.qrscanner.sync

import android.content.Context
import com.testcenter.qrscanner.auth.DatabasePermissionReader
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.PreferencesManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.IOException
import java.net.SocketTimeoutException
import java.util.concurrent.TimeUnit

/**
 * 权限同步管理器
 *
 * 负责从服务器API实时查询用户权限并缓存到本地
 *
 * 功能：
 * - APP启动时强制同步权限（阻塞式）
 * - 从服务器API查询最新权限信息
 * - 缓存权限到 SharedPreferences
 * - 提供完整的错误处理和日志记录
 *
 * 优势：
 * - 实时性：直接查询数据库，管理员修改立即生效
 * - 高效：单次HTTP请求，数据量小（~250 bytes）
 * - 稳定：HTTP API比WebDAV文件操作更可靠
 * - 正确：数据库事务保证数据一致性
 */
class PermissionSyncManager(
    private val context: android.content.Context,
    private val preferencesManager: PreferencesManager
) {
    companion object {
        private const val TAG = "PermissionSyncManager"
        private const val CONNECT_TIMEOUT_SECONDS = 5L
        private const val READ_TIMEOUT_SECONDS = 10L
    }

    // HTTP客户端（配置超时）
    private val httpClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .readTimeout(READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .build()
    }

    /**
     * 同步用户权限
     *
     * 根据后端类型选择不同的同步策略：
     * - SMB: 使用 HTTP API 查询（实时）
     * - WebDAV: 下载权限配置文件（缓存）
     *
     * @return PermissionSyncResult 同步结果（成功或失败）
     */
    suspend fun syncPermissions(): PermissionSyncResult {
        return withContext(Dispatchers.IO) {
            try {
                // 1. 获取用户名
                val username = preferencesManager.getUsername()
                if (username.isNullOrBlank()) {
                    AppLogger.log(TAG, "Sync failed: No username found")
                    return@withContext PermissionSyncResult.Failure("未找到用户名")
                }

                AppLogger.log(TAG, "Syncing permissions for user: $username using backend: api")
                syncPermissionsViaApi(username)
            } catch (e: Exception) {
                AppLogger.log(TAG, "Sync unexpected error", e)
                return@withContext PermissionSyncResult.Failure("未知错误: ${e.message}")
            }
        }
    }

    /**
     * 通过 HTTP API 同步权限（SMB 模式）
     */
    private suspend fun syncPermissionsViaApi(username: String): PermissionSyncResult {
        return try {
            // 获取 API 基础 URL（自动判断内外网）
            val apiBaseUrl = preferencesManager.getApiBaseUrl()
            AppLogger.log(TAG, "Using API base URL: $apiBaseUrl")

            // 构建API请求
            val apiUrl = "$apiBaseUrl/api/user/$username/permissions"
            AppLogger.log(TAG, "Fetching permissions from API: $apiUrl")

            val request = Request.Builder()
                .url(apiUrl)
                .get()
                .build()

            // 执行HTTP请求
            val response = httpClient.newCall(request).execute()

            if (response.isSuccessful) {
                val responseBody = response.body?.string()
                if (responseBody.isNullOrBlank()) {
                    AppLogger.log(TAG, "API sync failed: Empty response body")
                    return PermissionSyncResult.Failure("服务器返回空响应")
                }

                // 解析权限数据
                val permissions = parsePermissions(responseBody)

                // 缓存到本地
                cachePermissions(permissions)

                AppLogger.log(TAG,
                    "API sync successful - User: $username, Role: ${permissions.role}")

                PermissionSyncResult.Success(permissions)
            } else {
                val errorMsg = "HTTP ${response.code}: ${response.message}"
                AppLogger.log(TAG, "API sync failed: $errorMsg")
                PermissionSyncResult.Failure(errorMsg)
            }
        } catch (e: SocketTimeoutException) {
            AppLogger.log(TAG, "API sync timeout", e)
            PermissionSyncResult.Failure("网络超时，请检查连接")
        } catch (e: IOException) {
            AppLogger.log(TAG, "API sync network error", e)
            PermissionSyncResult.Failure("网络错误: ${e.message}")
        }
    }

    /**
     * 通过下载数据库文件同步权限（WebDAV 模式）
     */
    private suspend fun syncPermissionsViaFile(username: String): PermissionSyncResult {
        return try {
            AppLogger.log(TAG, "Syncing permissions via database download for user: $username")

            // 使用 DatabasePermissionReader 读取权限数据库
            val dbReader = DatabasePermissionReader(context, preferencesManager)
            val permissions = dbReader.readUserPermissions(username)

            if (permissions != null) {
                // 缓存到本地
                cachePermissions(permissions)

                AppLogger.log(TAG,
                    "Database sync successful - User: $username, Role: ${permissions.role}")

                PermissionSyncResult.Success(permissions)
            } else {
                AppLogger.log(TAG, "Database sync failed: User not found in database")

                // 尝试使用缓存的权限
                val cachedPermissions = getCachedPermissions(username)
                if (cachedPermissions != null) {
                    AppLogger.log(TAG, "Using cached permissions for user: $username")
                    PermissionSyncResult.Success(cachedPermissions)
                } else {
                    PermissionSyncResult.Failure("未找到用户权限配置")
                }
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "Database sync error", e)

            // 尝试使用缓存的权限
            val cachedPermissions = getCachedPermissions(username)
            if (cachedPermissions != null) {
                AppLogger.log(TAG, "Database sync failed, using cached permissions for user: $username")
                PermissionSyncResult.Success(cachedPermissions)
            } else {
                PermissionSyncResult.Failure("权限同步失败: ${e.message}")
            }
        }
    }



    /**
     * 获取缓存的权限
     */
    private fun getCachedPermissions(username: String): UserPermissions? {
        return try {
            val cachedJson = preferencesManager.getCachedPermissionsJson()
            if (!cachedJson.isNullOrBlank()) {
                parsePermissions(cachedJson)
            } else {
                null
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "Failed to get cached permissions", e)
            null
        }
    }

    /**
     * 解析服务器返回的权限JSON
     *
     * 预期格式：
     * {
     *   "username": "zhiqiang.zhu",
     *   "role": "admin",
     *   "permissions": {
     *     "can_modify_records": true,
     *     "can_delete_records": true,
     *     "can_manage_users": true,
     *     "can_access_all_projects": true
     *   },
     *   "timestamp": "2025-10-19T23:54:00.163893"
     * }
     */
    private fun parsePermissions(json: String): UserPermissions {
        val jsonObject = JSONObject(json)
        val permissionsObject = jsonObject.getJSONObject("permissions")

        return UserPermissions(
            username = jsonObject.getString("username"),
            role = jsonObject.getString("role"),
            canModifyRecords = permissionsObject.getBoolean("can_modify_records"),
            canDeleteRecords = permissionsObject.getBoolean("can_delete_records"),
            canManageUsers = permissionsObject.getBoolean("can_manage_users"),
            canAccessAllProjects = permissionsObject.getBoolean("can_access_all_projects"),
            timestamp = jsonObject.getString("timestamp")
        )
    }

    /**
     * 缓存权限到 SharedPreferences
     */
    private fun cachePermissions(permissions: UserPermissions) {
        preferencesManager.cacheUserPermissions(
            role = permissions.role,
            permissionsJson = permissions.toJson(),
            timestamp = System.currentTimeMillis()
        )

        AppLogger.log(TAG, "Permissions cached: role=${permissions.role}")
    }
}


/**
 * 用户权限数据类
 *
 * 存储从服务器查询的用户权限信息
 */
data class UserPermissions(
    val username: String,
    val role: String,  // "admin" or "user"
    val canModifyRecords: Boolean,
    val canDeleteRecords: Boolean,
    val canManageUsers: Boolean,
    val canAccessAllProjects: Boolean,
    val timestamp: String
) {
    /**
     * 转换为JSON字符串用于缓存
     */
    fun toJson(): String {
        return JSONObject().apply {
            put("username", username)
            put("role", role)
            put("permissions", JSONObject().apply {
                put("can_modify_records", canModifyRecords)
                put("can_delete_records", canDeleteRecords)
                put("can_manage_users", canManageUsers)
                put("can_access_all_projects", canAccessAllProjects)
            })
            put("timestamp", timestamp)
        }.toString()
    }

    /**
     * 是否为管理员
     */
    fun isAdmin(): Boolean = role == "admin"
}

/**
 * 权限同步结果
 *
 * 使用密封类表示同步的两种可能结果
 */
sealed class PermissionSyncResult {
    /**
     * 同步成功
     */
    data class Success(val permissions: UserPermissions) : PermissionSyncResult()

    /**
     * 同步失败
     */
    data class Failure(override val errorMessage: String) : PermissionSyncResult()

    /**
     * 是否成功
     */
    val success: Boolean
        get() = this is Success

    /**
     * 获取错误消息（如果失败）
     */
    open val errorMessage: String?
        get() = (this as? Failure)?.errorMessage
}
