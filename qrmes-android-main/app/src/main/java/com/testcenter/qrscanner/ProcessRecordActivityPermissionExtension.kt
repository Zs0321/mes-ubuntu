package com.testcenter.qrscanner

import android.widget.Toast
import com.testcenter.qrscanner.auth.AuthenticationService
import com.testcenter.qrscanner.auth.PermissionService
import com.testcenter.qrscanner.ui.PermissionUIController
import com.testcenter.qrscanner.utils.AppLogger

/**
 * ProcessRecordActivity 权限控制扩展
 * 
 * 使用说明：
 * 1. 在 ProcessRecordActivity 中添加以下变量：
 *    private lateinit var authenticationService: AuthenticationService
 *    private lateinit var permissionUIController: PermissionUIController
 * 
 * 2. 在 onCreate 中初始化（在 setContentView 之后）：
 *    authenticationService = AuthenticationService(this)
 *    permissionUIController = PermissionUIController(authenticationService)
 * 
 * 3. 在 onCreate 中检查权限（在 setupUI 之前）：
 *    if (!checkProcessRecordPermission()) {
 *        return
 *    }
 * 
 * 4. 在 setupUI 末尾调用：
 *    applyPermissionControls()
 */

/**
 * 检查工序记录权限（用于 Activity 入口检查）
 * @return true 如果有权限，false 如果没有权限（会自动关闭 Activity）
 */
fun ProcessRecordActivity.checkProcessRecordPermission(
    authService: AuthenticationService
): Boolean {
    // 获取当前用户
    val currentUser = authService.getCurrentUser()
    AppLogger.log("ProcessRecordActivity", "[权限检查] 当前用户: ${currentUser?.synologyUsername ?: "null"}, 角色: ${currentUser?.role?.name ?: "null"}")
    
    // 获取所有权限
    val allPermissions = authService.getPermissionService().getCurrentUserPermissions()
    AppLogger.log("ProcessRecordActivity", "[权限检查] 用户拥有的权限数量: ${allPermissions.size}")
    allPermissions.forEach { permission ->
        AppLogger.log("ProcessRecordActivity", "[权限检查]   - ${permission.name}")
    }
    
    // 检查工序记录权限
    val hasPermission = authService.hasPermission(
        PermissionService.Permission.MOBILE_PROCESS_RECORD
    )
    
    AppLogger.log("ProcessRecordActivity", "[权限检查] MOBILE_PROCESS_RECORD 权限: ${if (hasPermission) "有" else "无"}")
    
    if (!hasPermission) {
        Toast.makeText(
            this,
            "您没有工序记录权限，请联系管理员",
            Toast.LENGTH_LONG
        ).show()
        AppLogger.log("ProcessRecordActivity", "[权限检查] ✗ 访问被拒绝：没有 MOBILE_PROCESS_RECORD 权限")
        finish()
        return false
    }
    
    AppLogger.log("ProcessRecordActivity", "[权限检查] ✓ 权限检查通过")
    return true
}

/**
 * 应用权限控制到 ProcessRecordActivity 的 UI 元素
 */
fun ProcessRecordActivity.applyPermissionControls(
    permissionUI: PermissionUIController,
    binding: com.testcenter.qrscanner.databinding.ActivityProcessRecordBinding
) {
    // 记录权限摘要
    permissionUI.logPermissionSummary()
    
    // 控制扫描按钮（工序记录权限）
    permissionUI.controlButtonByPermission(
        binding.btnScanProduct,
        PermissionService.Permission.MOBILE_PROCESS_RECORD,
        hideIfNoPermission = false  // 禁用而不是隐藏，因为用户已经进入了这个页面
    )
    
    AppLogger.log("ProcessRecordActivity", "Permission controls applied successfully")
}

/**
 * 检查相机访问权限（用于拍照前检查）
 */
fun ProcessRecordActivity.checkCameraAccessPermission(
    permissionUI: PermissionUIController
): Boolean {
    return permissionUI.checkPermissionWithMessage(
        this,
        PermissionService.Permission.MOBILE_CAMERA_ACCESS,
        "您没有相机访问权限，无法拍照"
    )
}

/**
 * 检查工序记录权限（用于操作前检查）
 */
fun ProcessRecordActivity.checkProcessRecordOperationPermission(
    permissionUI: PermissionUIController
): Boolean {
    return permissionUI.checkPermissionWithMessage(
        this,
        PermissionService.Permission.MOBILE_PROCESS_RECORD,
        "您没有工序记录权限"
    )
}
