package com.testcenter.qrscanner.ui

import android.view.View
import android.widget.Button
import android.widget.ImageButton
import com.google.android.material.floatingactionbutton.FloatingActionButton
import com.testcenter.qrscanner.auth.AuthenticationService
import com.testcenter.qrscanner.auth.PermissionService
import com.testcenter.qrscanner.utils.AppLogger

/**
 * 权限 UI 控制器
 * 
 * 统一管理基于权限的 UI 显示/隐藏逻辑
 * 
 * 功能：
 * - 根据用户权限显示/隐藏按钮
 * - 根据用户权限启用/禁用功能
 * - 提供统一的权限检查和 UI 更新接口
 */
class PermissionUIController(
    private val authenticationService: AuthenticationService
) {
    companion object {
        private const val TAG = "PermissionUIController"
    }
    
    /**
     * 根据权限控制按钮可见性
     * 
     * @param button 要控制的按钮
     * @param permission 需要的权限
     * @param hideIfNoPermission 无权限时是否隐藏（true=隐藏，false=禁用）
     */
    fun controlButtonByPermission(
        button: View,
        permission: PermissionService.Permission,
        hideIfNoPermission: Boolean = true
    ) {
        val hasPermission = authenticationService.hasPermission(permission)
        
        if (hasPermission) {
            button.visibility = View.VISIBLE
            button.isEnabled = true
            AppLogger.log(TAG, "Button enabled: ${button.javaClass.simpleName}, permission: ${permission.name}")
        } else {
            if (hideIfNoPermission) {
                button.visibility = View.GONE
                AppLogger.log(TAG, "Button hidden: ${button.javaClass.simpleName}, no permission: ${permission.name}")
            } else {
                button.visibility = View.VISIBLE
                button.isEnabled = false
                button.alpha = 0.5f
                AppLogger.log(TAG, "Button disabled: ${button.javaClass.simpleName}, no permission: ${permission.name}")
            }
        }
    }
    
    /**
     * 批量控制多个按钮
     */
    fun controlMultipleButtons(
        buttons: List<Pair<View, PermissionService.Permission>>,
        hideIfNoPermission: Boolean = true
    ) {
        buttons.forEach { (button, permission) ->
            controlButtonByPermission(button, permission, hideIfNoPermission)
        }
    }
    
    /**
     * 检查权限并返回结果
     */
    fun hasPermission(permission: PermissionService.Permission): Boolean {
        return authenticationService.hasPermission(permission)
    }
    
    /**
     * 获取权限摘要（用于调试）
     */
    fun getPermissionSummary(): Map<String, Boolean> {
        return mapOf(
            "物料记录" to hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD),
            "修改已存在物料" to hasPermission(PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL),
            "工序记录" to hasPermission(PermissionService.Permission.MOBILE_PROCESS_RECORD),
            "相机访问" to hasPermission(PermissionService.Permission.MOBILE_CAMERA_ACCESS),
            "查看记录" to hasPermission(PermissionService.Permission.WEB_VIEW_RECORDS),
            "修改记录" to hasPermission(PermissionService.Permission.WEB_MODIFY_RECORDS),
            "删除记录" to hasPermission(PermissionService.Permission.WEB_DELETE_RECORDS)
        )
    }
    
    /**
     * 记录权限摘要到日志
     */
    fun logPermissionSummary() {
        val summary = getPermissionSummary()
        AppLogger.log(TAG, "=== 用户权限摘要 ===")
        summary.forEach { (name, hasPermission) ->
            AppLogger.log(TAG, "$name: ${if (hasPermission) "✓ 允许" else "✗ 拒绝"}")
        }
        AppLogger.log(TAG, "==================")
    }
    
    /**
     * 检查并显示权限错误消息
     * @return true 如果有权限，false 如果没有权限
     */
    fun checkPermissionWithMessage(
        context: android.content.Context,
        permission: PermissionService.Permission,
        customMessage: String? = null
    ): Boolean {
        val hasPermission = authenticationService.hasPermission(permission)
        if (!hasPermission) {
            val message = customMessage ?: "您没有执行此操作的权限"
            android.widget.Toast.makeText(context, message, android.widget.Toast.LENGTH_SHORT).show()
            AppLogger.log(TAG, "Permission denied: ${permission.name}")
        }
        return hasPermission
    }
    
    /**
     * 控制 TabLayout 的 Tab 可见性
     */
    fun controlTabByPermission(
        tab: com.google.android.material.tabs.TabLayout.Tab?,
        permission: PermissionService.Permission
    ) {
        val hasPermission = authenticationService.hasPermission(permission)
        if (!hasPermission) {
            tab?.view?.visibility = View.GONE
            AppLogger.log(TAG, "Tab hidden: no permission ${permission.name}")
        } else {
            tab?.view?.visibility = View.VISIBLE
            AppLogger.log(TAG, "Tab visible: has permission ${permission.name}")
        }
    }
    
    /**
     * 控制 RecyclerView 项目的可见性
     */
    fun shouldShowItem(permission: PermissionService.Permission): Boolean {
        return authenticationService.hasPermission(permission)
    }
}
