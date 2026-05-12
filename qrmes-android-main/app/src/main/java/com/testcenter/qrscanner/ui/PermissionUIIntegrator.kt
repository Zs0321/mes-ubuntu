package com.testcenter.qrscanner.ui

import android.content.Context
import android.content.Intent
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.testcenter.qrscanner.LoginActivity
import com.testcenter.qrscanner.auth.AuthenticationService
import com.testcenter.qrscanner.material.MaterialRecordManager
import com.testcenter.qrscanner.material.MaterialUIController
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * 权限UI集成器
 * 统一处理权限检查和UI响应的集成逻辑
 */
class PermissionUIIntegrator(
    private val context: Context,
    private val authenticationService: AuthenticationService,
    private val materialRecordManager: MaterialRecordManager
) {
    
    private val materialUIController = MaterialUIController(context)

    /**
     * 检查并应用产品扫描权限
     */
    fun checkAndApplyProductScanPermission(
        productSerial: String,
        onPermissionGranted: (canModify: Boolean) -> Unit,
        onPermissionDenied: () -> Unit
    ) {
        // 异步检查权限
        CoroutineScope(Dispatchers.Main).launch {
            try {
                val permissionResult = materialRecordManager.validateMaterialModifyPermission(productSerial)
                
                if (permissionResult.allowed) {
                    // 权限允许，可以正常操作
                    onPermissionGranted(true)
                } else if (permissionResult.isReadOnlyMode) {
                    // 只读模式，显示相应提示
                    materialUIController.showReadOnlyModeDialog(
                        productSerial = productSerial,
                        userRole = getCurrentUserRoleDescription()
                    ) {
                        // 用户确认继续只读模式
                        onPermissionGranted(false)
                    }
                } else {
                    // 权限完全拒绝
                    materialUIController.showPermissionDeniedDialog(
                        message = permissionResult.message
                    ) {
                        // 重试或其他操作
                        onPermissionDenied()
                    }
                }
            } catch (e: Exception) {
                // 权限检查异常
                materialUIController.showPermissionValidationFailedDialog(
                    error = "权限验证失败: ${e.message}"
                ) {
                    onPermissionDenied()
                }
            }
        }
    }

    /**
     * 检查并应用组件扫描权限
     */
    fun checkAndApplyComponentScanPermission(
        productSerial: String,
        componentName: String,
        onPermissionGranted: () -> Unit,
        onPermissionDenied: () -> Unit
    ) {
        CoroutineScope(Dispatchers.Main).launch {
            try {
                val permissionResult = materialRecordManager.validateMaterialModifyPermission(productSerial)
                
                if (permissionResult.allowed) {
                    onPermissionGranted()
                } else {
                    // 显示组件扫描权限拒绝对话框
                    materialUIController.showModificationAttemptDeniedDialog(
                        productSerial = productSerial,
                        operation = "扫描组件: $componentName"
                    ) {
                        // 提示用户使用管理员账户重新登录
                        showAdminLoginPrompt()
                    }
                    onPermissionDenied()
                }
            } catch (e: Exception) {
                materialUIController.showPermissionValidationFailedDialog(
                    error = "组件扫描权限验证失败: ${e.message}"
                ) {
                    onPermissionDenied()
                }
            }
        }
    }

    /**
     * 检查并应用手动输入权限
     */
    fun checkAndApplyManualInputPermission(
        productSerial: String,
        inputType: String,
        onPermissionGranted: () -> Unit,
        onPermissionDenied: () -> Unit
    ) {
        CoroutineScope(Dispatchers.Main).launch {
            try {
                val permissionResult = materialRecordManager.validateMaterialModifyPermission(productSerial)
                
                if (permissionResult.allowed) {
                    onPermissionGranted()
                } else {
                    materialUIController.showModificationAttemptDeniedDialog(
                        productSerial = productSerial,
                        operation = "手动输入: $inputType"
                    ) {
                        showAdminLoginPrompt()
                    }
                    onPermissionDenied()
                }
            } catch (e: Exception) {
                materialUIController.showPermissionValidationFailedDialog(
                    error = "手动输入权限验证失败: ${e.message}"
                ) {
                    onPermissionDenied()
                }
            }
        }
    }

    /**
     * 检查并应用拍照权限
     */
    fun checkAndApplyPhotoPermission(
        productSerial: String,
        onPermissionGranted: () -> Unit,
        onPermissionDenied: () -> Unit
    ) {
        CoroutineScope(Dispatchers.Main).launch {
            try {
                val permissionResult = materialRecordManager.validateMaterialModifyPermission(productSerial)
                
                if (permissionResult.allowed) {
                    onPermissionGranted()
                } else {
                    materialUIController.showModificationAttemptDeniedDialog(
                        productSerial = productSerial,
                        operation = "拍照记录"
                    ) {
                        showAdminLoginPrompt()
                    }
                    onPermissionDenied()
                }
            } catch (e: Exception) {
                materialUIController.showPermissionValidationFailedDialog(
                    error = "拍照权限验证失败: ${e.message}"
                ) {
                    onPermissionDenied()
                }
            }
        }
    }

    /**
     * 应用只读模式到界面
     */
    fun applyReadOnlyModeToUI(
        productInfoLayout: View,
        productSerial: String,
        permissionMessage: String
    ) {
        // 显示权限状态
        val currentUser = authenticationService.getCurrentUser()
        val userRole = getCurrentUserRoleDescription()
        
        val statusView = materialUIController.createPermissionStatusView(
            userRole = userRole,
            canModify = false,
            productSerial = productSerial
        )
        
        // 添加到布局顶部
        if (productInfoLayout is ViewGroup) {
            productInfoLayout.addView(statusView, 0)
        }
        
        // 显示权限提示Toast
        materialUIController.showPermissionToast(permissionMessage, true)
    }

    /**
     * 显示权限状态摘要
     */
    fun showPermissionStatusSummary() {
        val summary = materialRecordManager.getCurrentUserPermissionSummary()
        materialUIController.showPermissionToast(summary)
    }

    /**
     * 处理会话过期
     */
    fun handleSessionExpired() {
        materialUIController.showSessionExpiredDialog {
            // 跳转到登录页面
            val intent = Intent(context, LoginActivity::class.java)
            intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            context.startActivity(intent)
        }
    }

    /**
     * 显示管理员登录提示
     */
    private fun showAdminLoginPrompt() {
        materialUIController.showPermissionDeniedDialog(
            message = """
                当前操作需要管理员权限。
                
                请选择以下操作：
                1. 使用管理员账户重新登录
                2. 联系系统管理员获取权限
                3. 以只读模式继续查看
            """.trimIndent()
        ) {
            // 跳转到登录页面
            val intent = Intent(context, LoginActivity::class.java)
            intent.putExtra("require_admin", true)
            context.startActivity(intent)
        }
    }

    /**
     * 获取当前用户角色描述
     */
    private fun getCurrentUserRoleDescription(): String {
        val currentUser = authenticationService.getCurrentUser()
        return if (currentUser != null) {
            when (currentUser.role.name) {
                "ADMIN" -> "管理员"
                "USER" -> "普通用户"
                else -> "未知角色"
            }
        } else {
            "未登录用户"
        }
    }

    /**
     * 显示权限详情
     */
    fun showPermissionDetails() {
        materialUIController.showPermissionDetailsDialog()
    }

    /**
     * 检查基本权限
     */
    fun hasBasicPermissions(): Boolean {
        return materialRecordManager.hasBasicMaterialRecordPermission()
    }

    /**
     * 显示权限不足提示
     */
    fun showInsufficientPermissionMessage(operation: String) {
        materialUIController.showPermissionToast(
            "权限不足，无法执行操作：$operation",
            true
        )
    }
}