package com.testcenter.qrscanner.auth

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * 认证服务
 * 整合群晖认证、本地用户管理和权限验证功能
 */
class AuthenticationService(private val context: Context) {
    
    companion object {
        private const val TAG = "AuthenticationService"
        private const val DEFAULT_SYNOLOGY_URL = "https://172.16.30.10:5001"
        
        // Default URLs for reference
        const val DEFAULT_SYNOLOGY_DSM_URL = "https://172.16.30.10:5001"  // DSM API
        const val DEFAULT_WEBDAV_URL = "https://panovation.i234.me:5006"  // WebDAV service
    }

    private var synologyAuthClient: SynologyAuthClient? = null
    private val localUserManager = LocalUserManager(context)
    private val permissionService = PermissionService(localUserManager)

    /**
     * 初始化认证服务
     */
    fun initialize(synologyUrl: String = DEFAULT_SYNOLOGY_URL) {
        synologyAuthClient = SynologyAuthClient(synologyUrl)
        Log.i(TAG, "认证服务初始化完成: $synologyUrl")
        loadCachedPermissionsForCurrentUser()
    }

    /**
     * 用户登录
     * @param username 用户名
     * @param password 密码
     * @param synologyUrl 可选的群晖DSM服务器URL (例如: https://172.16.30.10:5001)
     * @return LoginResult 包含登录结果和是否应该回退到传统认证的标志
     */
    suspend fun login(username: String, password: String, synologyUrl: String? = null): LoginResult {
        return withContext(Dispatchers.IO) {
            try {
                // 如果synologyUrl为空或空白，表示应该跳过群晖认证，直接回退到传统认证
                if (synologyUrl.isNullOrBlank()) {
                    Log.i(TAG, "群晖URL未配置，建议回退到传统认证 (WebDAV/SMB)")
                    return@withContext LoginResult(
                        success = false,
                        error = "群晖DSM地址未配置",
                        shouldFallback = true
                    )
                }

                // 如果提供了新的URL，重新初始化客户端
                synologyAuthClient = SynologyAuthClient(synologyUrl)

                val client = synologyAuthClient
                if (client == null) {
                    Log.w(TAG, "认证服务未初始化，建议回退到传统认证")
                    return@withContext LoginResult(
                        success = false,
                        error = "群晖DSM认证服务未初始化",
                        shouldFallback = true
                    )
                }

                Log.i(TAG, "开始群晖DSM用户登录: $username")

                // 认证并映射用户
                val localUser = localUserManager.authenticateAndMapUser(client, username, password)

                if (localUser != null) {
                    Log.i(TAG, "群晖DSM用户登录成功: $username (角色: ${localUser.role.name})")
                    loadCachedPermissions(username)
                    LoginResult(
                        success = true,
                        user = localUser,
                        shouldFallback = false
                    )
                } else {
                    Log.w(TAG, "群晖DSM用户登录失败: $username - 用户名或密码错误")
                    LoginResult(
                        success = false,
                        error = "群晖DSM登录失败：用户名或密码错误",
                        shouldFallback = false  // 认证失败不应该回退，这是凭据问题
                    )
                }
            } catch (e: Exception) {
                Log.e(TAG, "群晖DSM登录过程异常: ${e.message}", e)
                // 网络或服务器错误应该触发回退
                val shouldFallback = e.message?.contains("timeout", ignoreCase = true) == true ||
                                   e.message?.contains("connection", ignoreCase = true) == true ||
                                   e.message?.contains("UnknownHost", ignoreCase = true) == true
                LoginResult(
                    success = false,
                    error = "群晖DSM登录异常: ${e.message}",
                    shouldFallback = shouldFallback
                )
            }
        }
    }

    /**
     * 用户登出
     */
    suspend fun logout(): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val client = synologyAuthClient
                if (client != null) {
                    localUserManager.logout(client)
                } else {
                    localUserManager.clearSession()
                    true
                }
            } catch (e: Exception) {
                Log.e(TAG, "登出异常: ${e.message}", e)
                // 即使异常也要清除本地会话
                localUserManager.clearSession()
                false
            }
        }
    }

    /**
     * 检查是否已登录
     */
    fun isLoggedIn(): Boolean {
        return localUserManager.isLoggedIn()
    }

    /**
     * 获取当前用户
     */
    fun getCurrentUser(): LocalUserManager.LocalUser? {
        return localUserManager.getCurrentUser()
    }

    /**
     * 获取权限服务
     */
    fun getPermissionService(): PermissionService {
        return permissionService
    }

    /**
     * 获取本地用户管理器
     */
    fun getLocalUserManager(): LocalUserManager {
        return localUserManager
    }

    /**
     * 验证会话有效性
     */
    suspend fun validateSession(): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val sessionId = localUserManager.getCurrentSessionId()
                val client = synologyAuthClient

                if (sessionId == null || client == null) {
                    return@withContext false
                }

                val userInfo = client.validateSession(sessionId)
                userInfo != null
            } catch (e: Exception) {
                Log.e(TAG, "会话验证异常: ${e.message}", e)
                false
            }
        }
    }

    /**
     * 测试群晖服务器连接
     */
    suspend fun testConnection(synologyUrl: String): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val testClient = SynologyAuthClient(synologyUrl)
                testClient.testConnection()
            } catch (e: Exception) {
                Log.e(TAG, "连接测试异常: ${e.message}", e)
                false
            }
        }
    }

    /**
     * 登录结果数据类
     * @param success 登录是否成功
     * @param user 登录成功时的用户对象
     * @param error 登录失败时的错误信息
     * @param shouldFallback 是否应该回退到传统认证方式 (WebDAV/SMB)
     */
    data class LoginResult(
        val success: Boolean,
        val user: LocalUserManager.LocalUser? = null,
        val error: String? = null,
        val shouldFallback: Boolean = false
    )

    /**
     * 权限检查快捷方法
     */
    fun hasPermission(permission: PermissionService.Permission): Boolean {
        return permissionService.hasPermission(permission)
    }

    /**
     * 检查是否可以修改已存在记录
     */
    fun canModifyExistingRecord(productSerial: String): Boolean {
        return permissionService.canModifyExistingRecord(productSerial)
    }

    /**
     * 检查当前用户是否为管理员
     */
    fun isCurrentUserAdmin(): Boolean {
        return permissionService.isCurrentUserAdmin()
    }

    fun loadCachedPermissions(username: String) {
        if (username.isBlank()) {
            return
        }
        try {
            val cached = localUserManager.getUserPermissions(username)
            if (!cached.isNullOrEmpty()) {
                val mapped = cached.mapNotNull { key ->
                    PermissionService.Permission.values().find { it.name == key }
                }.toSet()
                if (mapped.isNotEmpty()) {
                    permissionService.setApiLoadedPermissions(username, mapped)
                    Log.d(TAG, "从缓存加载权限: $username -> ${mapped.size} 项")
                } else {
                    Log.d(TAG, "缓存权限为空，将使用默认角色权限: $username")
                }
            } else {
                Log.d(TAG, "无缓存权限，将使用默认角色权限: $username")
            }
        } catch (e: Exception) {
            Log.e(TAG, "加载缓存权限失败: ${e.message}", e)
        }
    }

    fun loadCachedPermissionsForCurrentUser() {
        val currentUser = localUserManager.getCurrentUser()
        val username = currentUser?.synologyUsername ?: return
        loadCachedPermissions(username)
    }

    /**
     * 清除权限缓存（用于调试或重置）
     */
    fun clearPermissionCache() {
        try {
            permissionService.clearApiLoadedPermissions()
            localUserManager.clearAllPermissions()
            Log.i(TAG, "权限缓存已清除，将使用默认角色权限")
        } catch (e: Exception) {
            Log.e(TAG, "清除权限缓存失败: ${e.message}", e)
        }
    }

    /**
     * 获取用户统计信息
     */
    fun getUserStatistics(): Map<String, Int> {
        return localUserManager.getUserStatistics()
    }

    /**
     * 清除所有用户数据（用于重置或调试）
     */
    fun clearAllUserData() {
        try {
            localUserManager.clearSession()
            // 这里可以添加清除用户缓存的逻辑
            Log.i(TAG, "所有用户数据已清除")
        } catch (e: Exception) {
            Log.e(TAG, "清除用户数据失败: ${e.message}", e)
        }
    }
}
