package com.testcenter.qrscanner.material

import android.content.Context
import android.util.Log
import com.testcenter.qrscanner.auth.AuthenticationService
import com.testcenter.qrscanner.auth.PermissionService
import com.testcenter.qrscanner.database.UnifiedDataManager
import com.testcenter.qrscanner.data.ProductRecord
import com.testcenter.qrscanner.ui.PermissionDialogManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * 物料记录管理器
 * 处理物料信息的权限控制和记录管理
 */
class MaterialRecordManager(
    private val context: Context,
    private val authenticationService: AuthenticationService,
    private val unifiedDataManager: UnifiedDataManager
) {
    
    companion object {
        private const val TAG = "MaterialRecordManager"
    }
    
    private val permissionDialogManager = PermissionDialogManager(context)

    /**
     * 记录检查结果
     */
    data class RecordCheckResult(
        val exists: Boolean,
        val canModify: Boolean,
        val record: ProductRecord? = null,
        val message: String? = null
    )

    /**
     * 物料修改权限结果
     */
    data class MaterialModifyResult(
        val allowed: Boolean,
        val message: String,
        val isReadOnlyMode: Boolean = false
    )

    /**
     * 检查产品序列号是否已存在记录
     * 
     * 权限判断逻辑：
     * 1. 记录不存在 → 允许创建（首次输入）
     * 2. 记录存在但所有物料为空 → 允许创建（首次输入）
     * 3. 记录存在且所有物料已填写 → 需要修改权限（完整记录）
     * 4. 记录存在但部分物料已填写 → 允许继续完成（未完成记录）
     */
    suspend fun checkProductRecord(productSerial: String): RecordCheckResult {
        return withContext(Dispatchers.IO) {
            try {
                Log.d(TAG, "检查产品记录: $productSerial")

                // 查询数据库中是否存在该产品记录
                val existingRecord = unifiedDataManager.getRecord(productSerial)
                
                if (existingRecord == null) {
                    // 情况1：记录不存在
                    Log.d(TAG, "产品记录不存在: $productSerial")
                    return@withContext RecordCheckResult(
                        exists = false,
                        canModify = true,
                        record = null,
                        message = "新产品记录，可以创建"
                    )
                }
                
                // 记录存在，检查物料数据的完整性
                val materials = existingRecord.materials
                val filledMaterialsCount = materials.values.count { it.isNotBlank() }
                val totalMaterialsCount = materials.size
                
                Log.d(TAG, "产品记录存在: $productSerial, 已填写物料: $filledMaterialsCount/$totalMaterialsCount")
                
                when {
                    filledMaterialsCount == 0 -> {
                        // 情况2：记录存在但所有物料为空（首次输入）
                        Log.d(TAG, "产品记录存在但无物料数据，视为首次输入: $productSerial")
                        RecordCheckResult(
                            exists = false,
                            canModify = true,
                            record = null,
                            message = "首次输入，可以创建"
                        )
                    }
                    
                    filledMaterialsCount == totalMaterialsCount -> {
                        // 情况3：所有物料都已填写（完整记录）
                        Log.i(TAG, "产品记录完整: $productSerial, 所有物料已填写")
                        val canModify = authenticationService.canModifyExistingRecord(productSerial)
                        
                        RecordCheckResult(
                            exists = true,
                            canModify = canModify,
                            record = existingRecord,
                            message = if (canModify) {
                                "完整记录，您有权限修改"
                            } else {
                                "完整记录，普通用户无法修改"
                            }
                        )
                    }
                    
                    else -> {
                        // 情况4：部分物料已填写（未完成记录）
                        Log.i(TAG, "产品记录未完成: $productSerial, 已填写 $filledMaterialsCount/$totalMaterialsCount")
                        RecordCheckResult(
                            exists = false, // 视为未完成，允许继续输入
                            canModify = true,
                            record = existingRecord, // 返回现有记录以便恢复
                            message = "未完成记录（$filledMaterialsCount/$totalMaterialsCount），可以继续完成"
                        )
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "检查产品记录失败: ${e.message}", e)
                RecordCheckResult(
                    exists = false,
                    canModify = false,
                    record = null,
                    message = "检查记录时发生错误: ${e.message}"
                )
            }
        }
    }

    /**
     * 验证物料信息修改权限
     * 
     * 权限逻辑：
     * 1. 首次输入（无物料数据）：只需要基本的物料记录权限
     * 2. 未完成记录（部分物料已填写）：只需要基本的物料记录权限，允许继续完成
     * 3. 完整记录（所有物料已填写）：需要修改权限（通常是管理员）
     */
    suspend fun validateMaterialModifyPermission(productSerial: String): MaterialModifyResult {
        return withContext(Dispatchers.IO) {
            try {
                // 检查用户是否已登录
                if (!authenticationService.isLoggedIn()) {
                    return@withContext MaterialModifyResult(
                        allowed = false,
                        message = "用户未登录，无法进行物料记录操作"
                    )
                }

                val currentUser = authenticationService.getCurrentUser()
                if (currentUser == null) {
                    return@withContext MaterialModifyResult(
                        allowed = false,
                        message = "无法获取当前用户信息"
                    )
                }

                // 检查基本的物料记录权限
                val hasBasicPermission = authenticationService.hasPermission(
                    PermissionService.Permission.MOBILE_MATERIAL_RECORD
                )

                if (!hasBasicPermission) {
                    return@withContext MaterialModifyResult(
                        allowed = false,
                        message = "用户没有物料记录权限"
                    )
                }

                // 检查产品记录的完整性状态
                val recordCheck = checkProductRecord(productSerial)

                if (recordCheck.exists) {
                    // 完整记录（所有物料已填写），检查修改权限
                    if (recordCheck.canModify) {
                        MaterialModifyResult(
                            allowed = true,
                            message = "管理员用户，可以修改完整记录"
                        )
                    } else {
                        MaterialModifyResult(
                            allowed = false,
                            message = "普通用户不能修改完整记录，将以只读模式显示",
                            isReadOnlyMode = true
                        )
                    }
                } else {
                    // 新记录、首次输入或未完成记录，允许创建/继续完成
                    val message = if (recordCheck.record != null) {
                        "未完成记录，可以继续完成"
                    } else {
                        "新产品记录，可以创建"
                    }
                    
                    MaterialModifyResult(
                        allowed = true,
                        message = message
                    )
                }
            } catch (e: Exception) {
                Log.e(TAG, "验证物料修改权限失败: ${e.message}", e)
                MaterialModifyResult(
                    allowed = false,
                    message = "权限验证时发生错误: ${e.message}"
                )
            }
        }
    }

    /**
     * 检查并应用权限控制逻辑
     */
    suspend fun applyPermissionControl(
        productSerial: String,
        onPermissionResult: (MaterialModifyResult) -> Unit
    ) {
        try {
            Log.i(TAG, "应用权限控制: $productSerial")
            
            val permissionResult = validateMaterialModifyPermission(productSerial)
            
            Log.d(TAG, "权限验证结果: allowed=${permissionResult.allowed}, " +
                    "readOnly=${permissionResult.isReadOnlyMode}, message=${permissionResult.message}")
            
            onPermissionResult(permissionResult)
            
        } catch (e: Exception) {
            Log.e(TAG, "应用权限控制失败: ${e.message}", e)
            onPermissionResult(
                MaterialModifyResult(
                    allowed = false,
                    message = "权限控制应用失败: ${e.message}"
                )
            )
        }
    }

    /**
     * 获取产品记录的详细信息（用于只读模式显示）
     */
    suspend fun getProductRecordDetails(productSerial: String): ProductRecord? {
        return withContext(Dispatchers.IO) {
            try {
                unifiedDataManager.getRecord(productSerial)
            } catch (e: Exception) {
                Log.e(TAG, "获取产品记录详情失败: ${e.message}", e)
                null
            }
        }
    }

    /**
     * 保存物料记录（带权限检查）
     */
    suspend fun saveMaterialRecord(
        productSerial: String,
        materialData: Map<String, Any>
    ): SaveResult {
        return withContext(Dispatchers.IO) {
            try {
                // 再次验证权限
                val permissionResult = validateMaterialModifyPermission(productSerial)
                
                if (!permissionResult.allowed) {
                    return@withContext SaveResult(
                        success = false,
                        message = "保存失败：${permissionResult.message}"
                    )
                }

                // 执行保存操作
                // Create ProductRecord from materialData
                val productRecord = ProductRecord(
                    productSerial = productSerial,
                    productType = materialData["productType"]?.toString() ?: "",
                    projectName = materialData["projectName"]?.toString() ?: "",
                    operator = materialData["operator"]?.toString() ?: "",
                    scanTime = System.currentTimeMillis(),
                    materials = materialData.mapValues { it.value.toString() }
                )
                val success = unifiedDataManager.saveRecord(productRecord)
                
                if (success) {
                    Log.i(TAG, "物料记录保存成功: $productSerial")
                    SaveResult(
                        success = true,
                        message = "物料记录保存成功"
                    )
                } else {
                    Log.w(TAG, "物料记录保存失败: $productSerial")
                    SaveResult(
                        success = false,
                        message = "物料记录保存失败"
                    )
                }
            } catch (e: Exception) {
                Log.e(TAG, "保存物料记录异常: ${e.message}", e)
                SaveResult(
                    success = false,
                    message = "保存时发生异常: ${e.message}"
                )
            }
        }
    }

    /**
     * 保存结果
     */
    data class SaveResult(
        val success: Boolean,
        val message: String
    )

    /**
     * 获取当前用户的权限信息摘要
     */
    fun getCurrentUserPermissionSummary(): String {
        val currentUser = authenticationService.getCurrentUser()
        return if (currentUser != null) {
            val role = when (currentUser.role.name) {
                "ADMIN" -> "管理员"
                "USER" -> "普通用户"
                else -> "未知角色"
            }
            "当前用户：${currentUser.displayName} ($role)"
        } else {
            "未登录用户"
        }
    }

    /**
     * 检查用户是否有基本的物料记录权限
     */
    fun hasBasicMaterialRecordPermission(): Boolean {
        return authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD)
    }

    /**
     * 处理权限不足时的用户界面提示
     */
    fun handlePermissionDeniedUI(
        productSerial: String,
        attemptedOperation: String,
        onRetryAsAdmin: (() -> Unit)? = null
    ) {
        val currentUser = authenticationService.getCurrentUser()
        val userRole = currentUser?.role?.name?.let { roleName ->
            when (roleName) {
                "ADMIN" -> "管理员"
                "USER" -> "普通用户"
                else -> "未知角色"
            }
        } ?: "未登录用户"

        when (attemptedOperation) {
            "MODIFY_EXISTING_RECORD" -> {
                permissionDialogManager.showMaterialModificationDeniedDialog(
                    productSerial = productSerial,
                    onContactAdmin = {
                        showContactAdminOptions()
                    }
                )
            }
            "SCAN_COMPONENT" -> {
                permissionDialogManager.showOperationBlockedDialog(
                    operation = "扫描组件二维码",
                    reason = "该产品记录已存在，普通用户无法修改组件信息",
                    onRetryAsAdmin = onRetryAsAdmin
                )
            }
            "MANUAL_INPUT" -> {
                permissionDialogManager.showOperationBlockedDialog(
                    operation = "手动输入组件信息",
                    reason = "该产品记录已存在，普通用户无法修改组件信息",
                    onRetryAsAdmin = onRetryAsAdmin
                )
            }
            "PHOTO_CAPTURE" -> {
                permissionDialogManager.showOperationBlockedDialog(
                    operation = "拍照记录",
                    reason = "该产品记录已存在，普通用户无法修改相关信息",
                    onRetryAsAdmin = onRetryAsAdmin
                )
            }
            else -> {
                permissionDialogManager.showPermissionDeniedDialog(
                    message = "权限不足，无法执行操作：$attemptedOperation"
                )
            }
        }
    }

    /**
     * 显示联系管理员的选项
     */
    private fun showContactAdminOptions() {
        // 这里可以实现具体的联系管理员功能
        // 比如显示管理员联系方式、发送邮件等
        permissionDialogManager.showPermissionDeniedDialog(
            title = "联系管理员",
            message = """
                请通过以下方式联系系统管理员：
                
                1. 联系IT部门申请权限升级
                2. 使用管理员账户重新登录
                3. 查看系统使用手册获取更多信息
                
                管理员可以在Web后台系统中管理用户权限。
            """.trimIndent()
        )
    }

    /**
     * 显示只读模式说明对话框
     */
    fun showReadOnlyModeExplanation(
        productSerial: String,
        onContinueInReadOnlyMode: (() -> Unit)? = null
    ) {
        val currentUser = authenticationService.getCurrentUser()
        val userRole = currentUser?.role?.name?.let { roleName ->
            when (roleName) {
                "ADMIN" -> "管理员"
                "USER" -> "普通用户"
                else -> "未知角色"
            }
        } ?: "未登录用户"

        permissionDialogManager.showReadOnlyModeDialog(
            productSerial = productSerial,
            userRole = userRole,
            onContinue = onContinueInReadOnlyMode
        )
    }

    /**
     * 处理权限验证失败的情况
     */
    fun handlePermissionValidationError(
        error: String,
        onRetry: (() -> Unit)? = null
    ) {
        Log.e(TAG, "权限验证失败: $error")
        
        // 检查是否是会话过期错误
        if (error.contains("session", ignoreCase = true) || 
            error.contains("expired", ignoreCase = true) ||
            error.contains("token", ignoreCase = true)) {
            
            permissionDialogManager.showSessionExpiredDialog {
                // 重新登录逻辑
                onRetry?.invoke()
            }
        } else {
            permissionDialogManager.showPermissionValidationFailedDialog(
                error = error,
                onRetry = onRetry
            )
        }
    }

    /**
     * 显示用户权限状态信息
     */
    fun showUserPermissionStatus() {
        permissionDialogManager.showUserPermissionStatusDialog(authenticationService)
    }
}