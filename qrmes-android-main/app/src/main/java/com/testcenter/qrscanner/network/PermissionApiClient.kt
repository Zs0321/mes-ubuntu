package com.testcenter.qrscanner.network

import android.util.Base64
import android.util.Log
import com.testcenter.qrscanner.auth.PermissionService
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

/**
 * 权限 API 客户端。
 * 用于从后端服务查询用户权限，并转换成 APK 内部权限集合。
 */
class PermissionApiClient(
    private val baseUrl: String,
    private val username: String? = null,
    private val password: String? = null
) {
    companion object {
        private const val TAG = "PermissionApiClient"
        private const val TIMEOUT_MS = 10000
    }

    data class UserPermissions(
        val username: String,
        val role: String,
        val permissions: Map<String, Boolean>,
        val timestamp: String
    )

    suspend fun fetchUserPermissions(username: String): UserPermissions? = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "[权限查询] 开始查询用户权限: $username from $baseUrl")

            val url = URL("$baseUrl/api/user/$username/permissions")
            val connection = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = TIMEOUT_MS
                readTimeout = TIMEOUT_MS
                setRequestProperty("Accept", "application/json")
                if (!this@PermissionApiClient.username.isNullOrEmpty() && !this@PermissionApiClient.password.isNullOrEmpty()) {
                    val credentials = "${this@PermissionApiClient.username}:${this@PermissionApiClient.password}"
                    val encoded = Base64.encodeToString(credentials.toByteArray(Charsets.UTF_8), Base64.NO_WRAP)
                    setRequestProperty("Authorization", "Basic $encoded")
                }
            }

            val responseCode = connection.responseCode
            AppLogger.log(TAG, "[权限查询] HTTP 响应码: $responseCode")

            if (responseCode == HttpURLConnection.HTTP_OK) {
                val response = BufferedReader(InputStreamReader(connection.inputStream)).use { it.readText() }
                AppLogger.log(TAG, "[权限查询] 收到响应: ${response.take(200)}...")

                val jsonResponse = JSONObject(response)
                val permissionsJson = jsonResponse.getJSONObject("permissions")
                val permissions = mutableMapOf<String, Boolean>()
                permissionsJson.keys().forEach { key ->
                    permissions[key] = permissionsJson.getBoolean(key)
                }

                val userPermissions = UserPermissions(
                    username = jsonResponse.getString("username"),
                    role = jsonResponse.getString("role"),
                    permissions = permissions,
                    timestamp = jsonResponse.getString("timestamp")
                )

                AppLogger.log(
                    TAG,
                    "[权限查询] 成功获取权限: role=${userPermissions.role}, permissions=${permissions.size}项"
                )
                return@withContext userPermissions
            }

            val errorBody = try {
                BufferedReader(InputStreamReader(connection.errorStream)).use { it.readText() }
            } catch (_: Exception) {
                "无法读取错误响应"
            }
            AppLogger.log(TAG, "[权限查询] HTTP 错误: $responseCode, body: $errorBody")
            return@withContext null
        } catch (e: Exception) {
            AppLogger.log(TAG, "[权限查询] 查询失败", e)
            Log.e(TAG, "Failed to fetch user permissions", e)
            return@withContext null
        }
    }

    /**
     * 将 API 响应转换为 Permission 集合。
     * 即使用户是管理员，也以后端返回的细粒度权限为准，不再自动放开全部权限。
     */
    fun convertToPermissionSet(userPermissions: UserPermissions): Set<PermissionService.Permission> {
        val permissions = mutableSetOf<PermissionService.Permission>()

        if (userPermissions.role == "admin") {
            AppLogger.log(TAG, "[权限转换] 用户是管理员，但以后端返回的细粒度权限为准")
        }

        val permissionMap = userPermissions.permissions

        if (permissionMap["can_view_records"] == true) {
            permissions.add(PermissionService.Permission.WEB_VIEW_RECORDS)
        }

        if (permissionMap["can_create_material_record"] == true) {
            permissions.add(PermissionService.Permission.MOBILE_MATERIAL_RECORD)
        }
        if (permissionMap["can_modify_existing_material"] == true) {
            permissions.add(PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL)
        }

        if (permissionMap["can_create_process_record"] == true) {
            permissions.add(PermissionService.Permission.MOBILE_PROCESS_RECORD)
        }
        if (permissionMap["can_access_camera"] == true) {
            permissions.add(PermissionService.Permission.MOBILE_CAMERA_ACCESS)
        }

        if (permissionMap["can_modify_web_records"] == true) {
            permissions.add(PermissionService.Permission.WEB_MODIFY_RECORDS)
        }
        if (permissionMap["can_delete_records"] == true) {
            permissions.add(PermissionService.Permission.WEB_DELETE_RECORDS)
        }
        if (permissionMap["can_manage_users"] == true) {
            permissions.add(PermissionService.Permission.WEB_MANAGE_USERS)
        }
        if (permissionMap["can_manage_projects"] == true) {
            permissions.add(PermissionService.Permission.WEB_MANAGE_PROJECTS)
        }
        if (permissionMap["can_manage_process_config"] == true) {
            permissions.add(PermissionService.Permission.WEB_MANAGE_PROCESS_CONFIG)
        }
        if (permissionMap["can_external_login"] == true) {
            permissions.add(PermissionService.Permission.WEB_EXTERNAL_LOGIN)
        }

        AppLogger.log(TAG, "[权限转换] 转换完成: ${permissions.size}项权限")
        permissions.forEach {
            AppLogger.log(TAG, "[权限转换]   - ${it.name}")
        }

        return permissions
    }
}
