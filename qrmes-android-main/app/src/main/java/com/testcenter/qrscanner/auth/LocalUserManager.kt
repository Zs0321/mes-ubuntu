package com.testcenter.qrscanner.auth

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.*

/**
 * 本地用户管理器
 * 维护群晖账户与系统角色的映射关系，管理用户权限级别
 */
class LocalUserManager(private val context: Context) {
    
    companion object {
        private const val TAG = "LocalUserManager"
        private const val PREFS_NAME = "user_management"
        private const val KEY_CURRENT_USER = "current_user"
        private const val KEY_USER_CACHE = "user_cache"
        private const val KEY_SESSION_ID = "session_id"
        private const val KEY_LOGIN_TIME = "login_time"
        private const val KEY_PERMISSIONS_CACHE = "permissions_cache"
        private const val KEY_LAST_PERMISSION_USERNAME = "last_permission_username"
        private const val SESSION_TIMEOUT = 24 * 60 * 60 * 1000L // 24小时
    }

    /**
     * 用户角色枚举
     */
    enum class UserRole {
        ADMIN, USER
    }

    /**
     * 本地用户数据模型
     */
    data class LocalUser(
        val id: String,
        val synologyUsername: String,
        val displayName: String,
        val role: UserRole,
        val createdAt: Long,
        val updatedAt: Long,
        val lastLoginAt: Long? = null,
        val email: String? = null
    )

    private val prefs: SharedPreferences = try {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            PREFS_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    } catch (e: Exception) {
        Log.e(TAG, "EncryptedSharedPreferences 初始化失败，回退到普通存储", e)
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    }
    private val gson = Gson()

    /**
     * 认证群晖用户并映射到本地用户
     */
    suspend fun authenticateAndMapUser(
        synologyAuthClient: SynologyAuthClient,
        username: String,
        password: String
    ): LocalUser? {
        return withContext(Dispatchers.IO) {
            Log.i(TAG, "开始认证并映射用户: $username")

            // 使用群晖认证服务进行认证
            val authResult = synologyAuthClient.authenticate(username, password)

            if (!authResult.success) {
                Log.w(TAG, "群晖认证失败: $username - ${authResult.error}")
                return@withContext null
            }

            // 认证成功，获取或创建本地用户
            var localUser = getUserBySynologyUsername(username)

            if (localUser != null) {
                // 更新最后登录时间
                localUser = updateLastLogin(localUser.id)
                Log.i(TAG, "现有用户登录: $username")
            } else {
                // 创建新的本地用户
                localUser = createLocalUserFromSynology(username, authResult.userInfo)
                if (localUser != null) {
                    Log.i(TAG, "创建新用户: $username")
                } else {
                    Log.e(TAG, "创建本地用户失败: $username")
                    return@withContext null
                }
            }

            // 保存会话信息
            if (authResult.sessionId != null && localUser != null) {
                saveSession(localUser, authResult.sessionId)
            }

            localUser
        }
    }

    /**
     * 从群晖用户信息创建本地用户
     */
    private fun createLocalUserFromSynology(
        synologyUsername: String,
        userInfo: SynologyAuthClient.UserInfo?
    ): LocalUser? {
        return try {
            val currentTime = System.currentTimeMillis()
            val userId = UUID.randomUUID().toString()

            // 确定用户角色（默认为普通用户）
            var role = UserRole.USER

            // 如果用户信息中包含管理员组，则设为管理员
            if (userInfo?.groups != null) {
                val adminGroups = listOf("administrators", "admin", "wheel")
                val userGroups = userInfo.groups.map { it.lowercase() }
                if (adminGroups.any { it in userGroups }) {
                    role = UserRole.ADMIN
                }
            }

            // 创建本地用户对象
            val localUser = LocalUser(
                id = userId,
                synologyUsername = synologyUsername,
                displayName = userInfo?.displayName ?: synologyUsername,
                role = role,
                createdAt = currentTime,
                updatedAt = currentTime,
                lastLoginAt = currentTime,
                email = userInfo?.email
            )

            // 保存到本地存储
            if (saveUserToCache(localUser)) {
                Log.i(TAG, "成功创建本地用户: $synologyUsername (角色: ${role.name})")
                localUser
            } else {
                Log.e(TAG, "保存本地用户到缓存失败: $synologyUsername")
                null
            }
        } catch (e: Exception) {
            Log.e(TAG, "创建本地用户异常: ${e.message}", e)
            null
        }
    }

    /**
     * 保存用户到本地缓存
     */
    private fun saveUserToCache(user: LocalUser): Boolean {
        return try {
            val userCache = getUserCache().toMutableMap()
            userCache[user.synologyUsername] = user
            
            val json = gson.toJson(userCache)
            prefs.edit().putString(KEY_USER_CACHE, json).apply()
            
            true
        } catch (e: Exception) {
            Log.e(TAG, "保存用户到缓存失败: ${e.message}", e)
            false
        }
    }

    private fun getPermissionsCache(): MutableMap<String, MutableSet<String>> {
        return try {
            val json = prefs.getString(KEY_PERMISSIONS_CACHE, null)
            if (json.isNullOrEmpty()) {
                mutableMapOf()
            } else {
                val type = object : TypeToken<Map<String, List<String>>>() {}.type
                val raw: Map<String, List<String>>? = gson.fromJson(json, type)
                val cache = mutableMapOf<String, MutableSet<String>>()
                raw?.forEach { (key, value) ->
                    cache[key] = value.toMutableSet()
                }
                cache
            }
        } catch (e: Exception) {
            Log.e(TAG, "获取权限缓存失败: ${e.message}", e)
            mutableMapOf()
        }
    }

    fun saveUserPermissions(username: String, permissions: Set<String>) {
        try {
            if (username.isBlank()) {
                return
            }
            val cache = getPermissionsCache()
            cache[username] = permissions.toMutableSet()
            val json = gson.toJson(cache.mapValues { it.value.toList() })
            prefs.edit()
                .putString(KEY_PERMISSIONS_CACHE, json)
                .putString(KEY_LAST_PERMISSION_USERNAME, username)
                .apply()
            Log.d(TAG, "权限缓存已保存: $username -> ${permissions.size} 项")
        } catch (e: Exception) {
            Log.e(TAG, "保存权限缓存失败: ${e.message}", e)
        }
    }

    fun getUserPermissions(username: String): Set<String>? {
        return try {
            if (username.isBlank()) {
                null
            } else {
                getPermissionsCache()[username]?.toSet()
            }
        } catch (e: Exception) {
            Log.e(TAG, "获取用户权限缓存失败: ${e.message}", e)
            null
        }
    }

    fun clearUserPermissions(username: String) {
        try {
            if (username.isBlank()) {
                return
            }
            val cache = getPermissionsCache()
            if (cache.remove(username) != null) {
                val editor = prefs.edit()
                if (cache.isEmpty()) {
                    editor.remove(KEY_PERMISSIONS_CACHE)
                } else {
                    val json = gson.toJson(cache.mapValues { it.value.toList() })
                    editor.putString(KEY_PERMISSIONS_CACHE, json)
                }
                val lastUsername = prefs.getString(KEY_LAST_PERMISSION_USERNAME, null)
                if (lastUsername == username) {
                    editor.remove(KEY_LAST_PERMISSION_USERNAME)
                }
                editor.apply()
                Log.d(TAG, "权限缓存已清除: $username")
            }
        } catch (e: Exception) {
            Log.e(TAG, "清除权限缓存失败: ${e.message}", e)
        }
    }

    fun clearAllPermissions() {
        try {
            prefs.edit()
                .remove(KEY_PERMISSIONS_CACHE)
                .remove(KEY_LAST_PERMISSION_USERNAME)
                .apply()
            Log.d(TAG, "全部权限缓存已清除")
        } catch (e: Exception) {
            Log.e(TAG, "清除全部权限缓存失败: ${e.message}", e)
        }
    }

    fun getLastPermissionUsername(): String? {
        return prefs.getString(KEY_LAST_PERMISSION_USERNAME, null)
    }

    /**
     * 根据群晖用户名获取本地用户
     */
    fun getUserBySynologyUsername(synologyUsername: String): LocalUser? {
        return try {
            val userCache = getUserCache()
            userCache[synologyUsername]
        } catch (e: Exception) {
            Log.e(TAG, "查询用户失败: ${e.message}", e)
            null
        }
    }

    /**
     * 根据用户ID获取本地用户
     */
    fun getUserById(userId: String): LocalUser? {
        return try {
            val userCache = getUserCache()
            userCache.values.find { it.id == userId }
        } catch (e: Exception) {
            Log.e(TAG, "查询用户失败: ${e.message}", e)
            null
        }
    }

    /**
     * 获取所有本地用户
     */
    fun getAllUsers(): List<LocalUser> {
        return try {
            getUserCache().values.toList()
        } catch (e: Exception) {
            Log.e(TAG, "查询所有用户失败: ${e.message}", e)
            emptyList()
        }
    }

    /**
     * 更新用户角色
     */
    fun updateUserRole(userId: String, newRole: UserRole): Boolean {
        return try {
            val userCache = getUserCache().toMutableMap()
            val user = userCache.values.find { it.id == userId }
            
            if (user != null) {
                val updatedUser = user.copy(
                    role = newRole,
                    updatedAt = System.currentTimeMillis()
                )
                userCache[user.synologyUsername] = updatedUser
                
                val json = gson.toJson(userCache)
                prefs.edit().putString(KEY_USER_CACHE, json).apply()
                
                Log.i(TAG, "用户角色更新成功: $userId -> ${newRole.name}")
                true
            } else {
                Log.w(TAG, "用户不存在，角色更新失败: $userId")
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "更新用户角色失败: ${e.message}", e)
            false
        }
    }

    /**
     * 更新用户最后登录时间
     */
    private fun updateLastLogin(userId: String): LocalUser? {
        return try {
            val userCache = getUserCache().toMutableMap()
            val user = userCache.values.find { it.id == userId }
            
            if (user != null) {
                val currentTime = System.currentTimeMillis()
                val updatedUser = user.copy(
                    lastLoginAt = currentTime,
                    updatedAt = currentTime
                )
                userCache[user.synologyUsername] = updatedUser
                
                val json = gson.toJson(userCache)
                prefs.edit().putString(KEY_USER_CACHE, json).apply()
                
                updatedUser
            } else {
                null
            }
        } catch (e: Exception) {
            Log.e(TAG, "更新最后登录时间失败: ${e.message}", e)
            null
        }
    }

    /**
     * 删除用户
     */
    fun deleteUser(userId: String): Boolean {
        return try {
            val userCache = getUserCache().toMutableMap()
            val user = userCache.values.find { it.id == userId }
            
            if (user != null) {
                userCache.remove(user.synologyUsername)
                
                val json = gson.toJson(userCache)
                prefs.edit().putString(KEY_USER_CACHE, json).apply()
                
                Log.i(TAG, "用户删除成功: $userId")
                true
            } else {
                Log.w(TAG, "用户不存在，删除失败: $userId")
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "删除用户失败: ${e.message}", e)
            false
        }
    }

    /**
     * 保存会话信息
     */
    private fun saveSession(user: LocalUser, sessionId: String) {
        try {
            prefs.edit()
                .putString(KEY_CURRENT_USER, gson.toJson(user))
                .putString(KEY_SESSION_ID, sessionId)
                .putLong(KEY_LOGIN_TIME, System.currentTimeMillis())
                .apply()
            
            Log.d(TAG, "会话信息保存成功: ${user.synologyUsername}")
        } catch (e: Exception) {
            Log.e(TAG, "保存会话信息失败: ${e.message}", e)
        }
    }

    /**
     * 获取当前登录用户
     */
    fun getCurrentUser(): LocalUser? {
        return try {
            val userJson = prefs.getString(KEY_CURRENT_USER, null)
            if (userJson != null) {
                val user = gson.fromJson(userJson, LocalUser::class.java)
                
                // 检查会话是否过期
                val loginTime = prefs.getLong(KEY_LOGIN_TIME, 0)
                if (System.currentTimeMillis() - loginTime > SESSION_TIMEOUT) {
                    Log.w(TAG, "会话已过期")
                    clearSession()
                    return null
                }
                
                user
            } else {
                null
            }
        } catch (e: Exception) {
            Log.e(TAG, "获取当前用户失败: ${e.message}", e)
            null
        }
    }

    /**
     * 获取当前会话ID
     */
    fun getCurrentSessionId(): String? {
        return try {
            val sessionId = prefs.getString(KEY_SESSION_ID, null)
            
            // 检查会话是否过期
            val loginTime = prefs.getLong(KEY_LOGIN_TIME, 0)
            if (System.currentTimeMillis() - loginTime > SESSION_TIMEOUT) {
                Log.w(TAG, "会话已过期")
                clearSession()
                return null
            }
            
            sessionId
        } catch (e: Exception) {
            Log.e(TAG, "获取当前会话ID失败: ${e.message}", e)
            null
        }
    }

    /**
     * 检查是否已登录
     */
    fun isLoggedIn(): Boolean {
        val user = getCurrentUser()
        val sessionId = getCurrentSessionId()
        return user != null && sessionId != null
    }

    /**
     * 清除会话信息
     */
    fun clearSession() {
        try {
            prefs.edit()
                .remove(KEY_CURRENT_USER)
                .remove(KEY_SESSION_ID)
                .remove(KEY_LOGIN_TIME)
                .apply()
            
            Log.d(TAG, "会话信息已清除")
        } catch (e: Exception) {
            Log.e(TAG, "清除会话信息失败: ${e.message}", e)
        }
    }

    /**
     * 保存当前用户（用于SMB/WebDAV登录，不需要sessionId）
     */
    fun saveCurrentUser(user: LocalUser) {
        try {
            prefs.edit()
                .putString(KEY_CURRENT_USER, gson.toJson(user))
                .putString(KEY_SESSION_ID, "smb_webdav_${UUID.randomUUID()}")
                .putLong(KEY_LOGIN_TIME, System.currentTimeMillis())
                .apply()
            
            // 同时保存到用户缓存
            saveUserToCache(user)
            
            Log.d(TAG, "当前用户保存成功: ${user.synologyUsername}")
        } catch (e: Exception) {
            Log.e(TAG, "保存当前用户失败: ${e.message}", e)
        }
    }

    /**
     * 登出
     */
    suspend fun logout(synologyAuthClient: SynologyAuthClient): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val sessionId = getCurrentSessionId()
                var logoutSuccess = true
                
                if (sessionId != null) {
                    logoutSuccess = synologyAuthClient.logout(sessionId)
                }
                
                clearSession()
                
                Log.i(TAG, "用户登出${if (logoutSuccess) "成功" else "部分成功（本地会话已清除）"}")
                true
            } catch (e: Exception) {
                Log.e(TAG, "登出失败: ${e.message}", e)
                // 即使远程登出失败，也要清除本地会话
                clearSession()
                false
            }
        }
    }

    /**
     * 获取用户缓存
     */
    private fun getUserCache(): Map<String, LocalUser> {
        return try {
            val json = prefs.getString(KEY_USER_CACHE, null)
            if (json != null) {
                val type = object : TypeToken<Map<String, LocalUser>>() {}.type
                gson.fromJson(json, type) ?: emptyMap()
            } else {
                emptyMap()
            }
        } catch (e: Exception) {
            Log.e(TAG, "获取用户缓存失败: ${e.message}", e)
            emptyMap()
        }
    }

    /**
     * 获取用户统计信息
     */
    fun getUserStatistics(): Map<String, Int> {
        return try {
            val users = getAllUsers()
            mapOf(
                "total_users" to users.size,
                "admin_users" to users.count { it.role == UserRole.ADMIN },
                "regular_users" to users.count { it.role == UserRole.USER },
                "recent_active_users" to users.count { 
                    it.lastLoginAt != null && 
                    System.currentTimeMillis() - it.lastLoginAt < 7 * 24 * 60 * 60 * 1000L 
                }
            )
        } catch (e: Exception) {
            Log.e(TAG, "获取用户统计失败: ${e.message}", e)
            mapOf(
                "total_users" to 0,
                "admin_users" to 0,
                "regular_users" to 0,
                "recent_active_users" to 0
            )
        }
    }
}