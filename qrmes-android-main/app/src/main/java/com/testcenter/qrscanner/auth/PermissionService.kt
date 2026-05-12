package com.testcenter.qrscanner.auth

import android.util.Log

/**
 * 权限验证服务。
 * 提供基于角色和后端细粒度权限的访问控制能力。
 */
class PermissionService(private val localUserManager: LocalUserManager) {

    companion object {
        private const val TAG = "PermissionService"
    }

    // 从 API 加载的自定义权限，优先级高于角色默认权限。
    private var apiLoadedPermissions: Set<Permission>? = null
    private var apiLoadedUsername: String? = null

    /**
     * 权限枚举。
     */
    enum class Permission {
        // Web 后台权限
        WEB_VIEW_RECORDS,
        WEB_MODIFY_RECORDS,
        WEB_DELETE_RECORDS,
        WEB_MANAGE_USERS,
        WEB_MANAGE_PROJECTS,
        WEB_MANAGE_PROCESS_CONFIG,
        WEB_EXTERNAL_LOGIN,
        WEB_VIEW_LOGS,
        WEB_SYSTEM_SETTINGS,

        // 移动端权限
        MOBILE_MATERIAL_RECORD,
        MOBILE_MODIFY_EXISTING_MATERIAL,
        MOBILE_PROCESS_RECORD,
        MOBILE_CAMERA_ACCESS,

        // API 权限
        API_RECORDS_READ,
        API_RECORDS_WRITE,
        API_RECORDS_DELETE,
        API_PROJECTS_READ,
        API_PROJECTS_WRITE,
        API_USERS_READ,
        API_USERS_WRITE
    }

    // 角色默认权限映射。管理员仍有较高默认权限，但如果后端返回了细粒度权限，则以后端为准。
    private val rolePermissions = mapOf(
        LocalUserManager.UserRole.ADMIN to setOf(
            Permission.WEB_VIEW_RECORDS,
            Permission.WEB_MODIFY_RECORDS,
            Permission.WEB_DELETE_RECORDS,
            Permission.WEB_MANAGE_USERS,
            Permission.WEB_MANAGE_PROJECTS,
            Permission.WEB_MANAGE_PROCESS_CONFIG,
            Permission.WEB_VIEW_LOGS,
            Permission.WEB_SYSTEM_SETTINGS,
            Permission.MOBILE_MATERIAL_RECORD,
            Permission.MOBILE_MODIFY_EXISTING_MATERIAL,
            Permission.MOBILE_PROCESS_RECORD,
            Permission.MOBILE_CAMERA_ACCESS,
            Permission.API_RECORDS_READ,
            Permission.API_RECORDS_WRITE,
            Permission.API_RECORDS_DELETE,
            Permission.API_PROJECTS_READ,
            Permission.API_PROJECTS_WRITE,
            Permission.API_USERS_READ,
            Permission.API_USERS_WRITE
        ),
        LocalUserManager.UserRole.USER to setOf(
            Permission.WEB_VIEW_RECORDS,
            Permission.WEB_MODIFY_RECORDS,
            Permission.MOBILE_MATERIAL_RECORD,
            Permission.MOBILE_PROCESS_RECORD,
            Permission.MOBILE_CAMERA_ACCESS,
            Permission.API_RECORDS_READ,
            Permission.API_RECORDS_WRITE,
            Permission.API_PROJECTS_READ
        )
    )

    /**
     * 设置从 API 加载的权限。
     * 这些权限会覆盖默认角色权限。
     */
    fun setApiLoadedPermissions(username: String, permissions: Set<Permission>) {
        apiLoadedUsername = username
        apiLoadedPermissions = permissions
        Log.d(TAG, "[API权限] 已设置用户 $username 的 API 权限: ${permissions.size} 项")
        permissions.forEach {
            Log.d(TAG, "[API权限]   - ${it.name}")
        }
        try {
            localUserManager.saveUserPermissions(username, permissions.map { it.name }.toSet())
        } catch (e: Exception) {
            Log.e(TAG, "[API权限] 缓存权限失败: ${e.message}", e)
        }
    }

    /**
     * 清除 API 加载的权限。
     */
    fun clearApiLoadedPermissions() {
        val username = apiLoadedUsername
        apiLoadedUsername = null
        apiLoadedPermissions = null
        Log.d(TAG, "[API权限] 已清除 API 权限")
        if (username != null) {
            try {
                localUserManager.clearUserPermissions(username)
            } catch (e: Exception) {
                Log.e(TAG, "[API权限] 清除缓存权限失败: ${e.message}", e)
            }
        }
    }

    /**
     * 检查用户是否具有指定权限。
     */
    fun hasPermission(user: LocalUserManager.LocalUser?, permission: Permission): Boolean {
        if (user == null) {
            val defaultPermissions = rolePermissions[LocalUserManager.UserRole.USER] ?: emptySet()
            val hasPermission = permission in defaultPermissions
            Log.d(TAG, "[权限检查-默认] 无用户对象，使用 USER 默认权限，${permission.name}=${if (hasPermission) "允许" else "拒绝"}")
            return hasPermission
        }

        if (apiLoadedUsername == user.synologyUsername && apiLoadedPermissions != null && apiLoadedPermissions!!.isNotEmpty()) {
            val hasPermission = permission in apiLoadedPermissions!!
            Log.d(TAG, "[权限检查-API] 用户 ${user.synologyUsername} 对 ${permission.name} 的权限=${if (hasPermission) "允许" else "拒绝"}")
            return hasPermission
        }

        val userPermissions = rolePermissions[user.role] ?: emptySet()
        val hasPermission = permission in userPermissions
        Log.d(TAG, "[权限检查-角色] 用户 ${user.synologyUsername} (${user.role.name}) 对 ${permission.name} 的权限=${if (hasPermission) "允许" else "拒绝"}")
        return hasPermission
    }

    /**
     * 检查当前用户是否具有指定权限。
     */
    fun hasPermission(permission: Permission): Boolean {
        val currentUser = localUserManager.getCurrentUser()
        return hasPermission(currentUser, permission)
    }

    /**
     * 根据用户 ID 检查权限。
     */
    fun hasPermissionByUserId(userId: String, permission: Permission): Boolean {
        val user = localUserManager.getUserById(userId)
        return hasPermission(user, permission)
    }

    /**
     * 获取用户的全部权限。
     */
    fun getUserPermissions(user: LocalUserManager.LocalUser?): Set<Permission> {
        if (user == null) {
            return rolePermissions[LocalUserManager.UserRole.USER] ?: emptySet()
        }

        if (apiLoadedUsername == user.synologyUsername && apiLoadedPermissions != null && apiLoadedPermissions!!.isNotEmpty()) {
            return apiLoadedPermissions!!
        }

        return rolePermissions[user.role] ?: emptySet()
    }

    /**
     * 获取当前用户的全部权限。
     */
    fun getCurrentUserPermissions(): Set<Permission> {
        val currentUser = localUserManager.getCurrentUser()
        return getUserPermissions(currentUser)
    }

    /**
     * 检查用户是否可以修改已存在记录。
     */
    @Suppress("UNUSED_PARAMETER")
    fun canModifyExistingRecord(user: LocalUserManager.LocalUser?, productSerial: String): Boolean {
        if (user == null) {
            return false
        }
        return hasPermission(user, Permission.MOBILE_MODIFY_EXISTING_MATERIAL)
    }

    /**
     * 检查当前用户是否可以修改已存在记录。
     */
    fun canModifyExistingRecord(productSerial: String): Boolean {
        val currentUser = localUserManager.getCurrentUser()
        return canModifyExistingRecord(currentUser, productSerial)
    }

    /**
     * 检查用户是否为管理员。
     */
    fun isAdmin(user: LocalUserManager.LocalUser?): Boolean {
        return user?.role == LocalUserManager.UserRole.ADMIN
    }

    /**
     * 检查当前用户是否为管理员。
     */
    fun isCurrentUserAdmin(): Boolean {
        val currentUser = localUserManager.getCurrentUser()
        return isAdmin(currentUser)
    }

    /**
     * 获取权限描述。
     */
    fun getPermissionDescription(permission: Permission): String {
        return when (permission) {
            Permission.WEB_VIEW_RECORDS -> "查看Web后台记录"
            Permission.WEB_MODIFY_RECORDS -> "修改Web后台记录"
            Permission.WEB_DELETE_RECORDS -> "删除Web后台记录"
            Permission.WEB_MANAGE_USERS -> "管理用户"
            Permission.WEB_MANAGE_PROJECTS -> "管理项目"
            Permission.WEB_MANAGE_PROCESS_CONFIG -> "管理工序配置"
            Permission.WEB_EXTERNAL_LOGIN -> "外网登录"
            Permission.WEB_VIEW_LOGS -> "查看日志"
            Permission.WEB_SYSTEM_SETTINGS -> "系统设置"
            Permission.MOBILE_MATERIAL_RECORD -> "移动端物料记录"
            Permission.MOBILE_MODIFY_EXISTING_MATERIAL -> "修改已存在物料"
            Permission.MOBILE_PROCESS_RECORD -> "移动端工序记录"
            Permission.MOBILE_CAMERA_ACCESS -> "相机访问"
            Permission.API_RECORDS_READ -> "读取记录API"
            Permission.API_RECORDS_WRITE -> "写入记录API"
            Permission.API_RECORDS_DELETE -> "删除记录API"
            Permission.API_PROJECTS_READ -> "读取项目API"
            Permission.API_PROJECTS_WRITE -> "写入项目API"
            Permission.API_USERS_READ -> "读取用户API"
            Permission.API_USERS_WRITE -> "写入用户API"
        }
    }

    /**
     * 获取角色描述。
     */
    fun getRoleDescription(role: LocalUserManager.UserRole): String {
        return when (role) {
            LocalUserManager.UserRole.ADMIN -> "管理员"
            LocalUserManager.UserRole.USER -> "普通用户"
        }
    }

    /**
     * 权限校验结果。
     */
    data class PermissionResult(
        val allowed: Boolean,
        val message: String? = null
    )

    /**
     * 验证权限并返回详细结果。
     */
    fun validatePermission(permission: Permission): PermissionResult {
        val currentUser = localUserManager.getCurrentUser()
        if (currentUser == null) {
            return PermissionResult(
                allowed = false,
                message = "用户未登录"
            )
        }

        return if (hasPermission(currentUser, permission)) {
            PermissionResult(allowed = true)
        } else {
            PermissionResult(
                allowed = false,
                message = "权限不足：需要${getPermissionDescription(permission)}权限"
            )
        }
    }

    /**
     * 验证修改已存在记录的权限。
     */
    fun validateModifyExistingRecord(productSerial: String): PermissionResult {
        val currentUser = localUserManager.getCurrentUser()
        if (currentUser == null) {
            return PermissionResult(
                allowed = false,
                message = "用户未登录"
            )
        }

        return if (canModifyExistingRecord(currentUser, productSerial)) {
            PermissionResult(allowed = true)
        } else {
            PermissionResult(
                allowed = false,
                message = "权限不足：普通用户不能修改已存在的记录"
            )
        }
    }
}
