package com.testcenter.qrscanner

import android.view.View
import com.testcenter.qrscanner.auth.AuthenticationService
import com.testcenter.qrscanner.auth.PermissionService
import com.testcenter.qrscanner.ui.PermissionUIController
import com.testcenter.qrscanner.utils.AppLogger

/**
 * MainActivity 权限控制扩展
 * 
 * 使用说明：
 * 1. 在 MainActivity 中添加以下变量：
 *    private lateinit var authenticationService: AuthenticationService
 *    private lateinit var permissionUIController: PermissionUIController
 * 
 * 2. 在 onCreate 中初始化（在 setContentView 之后）：
 *    authenticationService = AuthenticationService(this)
 *    permissionUIController = PermissionUIController(authenticationService)
 * 
 * 3. 在 onCreate 末尾调用：
 *    applyPermissionControls()
 */

/**
 * 应用权限控制到 MainActivity 的 UI 元素
 */
fun MainActivity.applyPermissionControls(
    authService: AuthenticationService,
    permissionUI: PermissionUIController,
    binding: com.testcenter.qrscanner.databinding.ActivityMainBinding
) {
    // 记录权限摘要
    permissionUI.logPermissionSummary()
    
    // 控制扫描按钮（物料记录权限）
    permissionUI.controlButtonByPermission(
        binding.btnScanProduct,
        PermissionService.Permission.MOBILE_MATERIAL_RECORD,
        hideIfNoPermission = true
    )
    
    // 控制手动输入按钮（物料记录权限）
    permissionUI.controlButtonByPermission(
        binding.btnManualInputProduct,
        PermissionService.Permission.MOBILE_MATERIAL_RECORD,
        hideIfNoPermission = true
    )
    
    // 控制相机按钮（相机访问权限）
    val btnPhotoCapture = binding.btnPhotoCapture
    permissionUI.controlButtonByPermission(
        btnPhotoCapture,
        PermissionService.Permission.MOBILE_CAMERA_ACCESS,
        hideIfNoPermission = true
    )
    
    // 控制工序记录选项卡（工序记录权限）
    val processTab = binding.tabLayout.getTabAt(1)
    permissionUI.controlTabByPermission(
        processTab,
        PermissionService.Permission.MOBILE_PROCESS_RECORD
    )
    
    AppLogger.log("MainActivity", "Permission controls applied successfully")
}

/**
 * 检查物料记录权限
 */
fun MainActivity.checkMaterialRecordPermission(
    permissionUI: PermissionUIController
): Boolean {
    return permissionUI.checkPermissionWithMessage(
        this,
        PermissionService.Permission.MOBILE_MATERIAL_RECORD,
        "您没有物料记录权限，请联系管理员"
    )
}

/**
 * 检查相机访问权限
 */
fun MainActivity.checkCameraAccessPermission(
    permissionUI: PermissionUIController
): Boolean {
    return permissionUI.checkPermissionWithMessage(
        this,
        PermissionService.Permission.MOBILE_CAMERA_ACCESS,
        "您没有相机访问权限，请联系管理员"
    )
}

/**
 * 检查修改已存在物料权限
 */
fun MainActivity.checkModifyExistingMaterialPermission(
    permissionUI: PermissionUIController
): Boolean {
    return permissionUI.checkPermissionWithMessage(
        this,
        PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL,
        "您没有修改已存在物料的权限"
    )
}
