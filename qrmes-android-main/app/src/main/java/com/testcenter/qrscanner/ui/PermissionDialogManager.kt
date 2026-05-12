package com.testcenter.qrscanner.ui

import android.content.Context
import android.content.DialogInterface
import android.view.LayoutInflater
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.testcenter.qrscanner.R
import com.testcenter.qrscanner.auth.AuthenticationService
import com.testcenter.qrscanner.auth.PermissionService

/**
 * 权限对话框管理器
 * 统一管理所有权限相关的用户界面提示
 */
class PermissionDialogManager(private val context: Context) {
    
    companion object {
        private const val TAG = "PermissionDialogManager"
    }

    /**
     * 显示权限不足的标准对话框
     */
    fun showPermissionDeniedDialog(
        title: String = "权限不足",
        message: String,
        onRetry: (() -> Unit)? = null,
        onCancel: (() -> Unit)? = null
    ): AlertDialog {
        val builder = MaterialAlertDialogBuilder(context)
            .setTitle(title)
            .setMessage(message)
            .setIcon(R.drawable.ic_lock)
            .setCancelable(true)
            .setPositiveButton("确定") { dialog, _ ->
                dialog.dismiss()
                onCancel?.invoke()
            }

        if (onRetry != null) {
            builder.setNeutralButton("重试") { dialog, _ ->
                dialog.dismiss()
                onRetry()
            }
        }

        return builder.show()
    }

    /**
     * 显示物料修改权限被拒绝的对话框
     */
    fun showMaterialModificationDeniedDialog(
        productSerial: String,
        onContactAdmin: (() -> Unit)? = null
    ): AlertDialog {
        val message = """
            产品序列号：$productSerial
            
            普通用户不能修改已存在的产品记录。
            
            原因：
            • 保护生产数据的完整性
            • 确保记录的可追溯性
            • 防止意外的数据修改
            
            如需修改，请联系管理员或使用管理员账户登录。
        """.trimIndent()

        val builder = MaterialAlertDialogBuilder(context)
            .setTitle("无法修改已存在记录")
            .setMessage(message)
            .setIcon(R.drawable.ic_lock)
            .setCancelable(true)
            .setPositiveButton("确定") { dialog, _ ->
                dialog.dismiss()
            }

        if (onContactAdmin != null) {
            builder.setNeutralButton("联系管理员") { dialog, _ ->
                dialog.dismiss()
                onContactAdmin()
            }
        }

        builder.setNegativeButton("查看详情") { dialog, _ ->
            dialog.dismiss()
            showPermissionDetailsDialog()
        }

        return builder.show()
    }

    /**
     * 显示权限详情说明对话框
     */
    fun showPermissionDetailsDialog(): AlertDialog {
        val message = """
            用户权限说明：
            
            管理员用户权限：
            • 查看所有生产记录
            • 创建新的产品记录
            • 修改已存在的产品记录
            • 删除产品记录
            • 管理用户权限
            • 配置系统设置
            
            普通用户权限：
            • 查看所有生产记录
            • 创建新的产品记录
            • 只读模式查看已存在记录
            
            权限设计目的：
            • 保护关键生产数据
            • 确保数据可追溯性
            • 防止意外操作
            • 符合质量管理要求
        """.trimIndent()

        return MaterialAlertDialogBuilder(context)
            .setTitle("权限详情说明")
            .setMessage(message)
            .setIcon(R.drawable.ic_person)
            .setPositiveButton("确定") { dialog, _ ->
                dialog.dismiss()
            }
            .show()
    }

    /**
     * 显示只读模式提示对话框
     */
    fun showReadOnlyModeDialog(
        productSerial: String,
        userRole: String,
        onContinue: (() -> Unit)? = null
    ): AlertDialog {
        val message = """
            产品序列号：$productSerial
            当前用户角色：$userRole
            
            该产品记录已存在，将以只读模式显示。
            
            在只读模式下：
            • 可以查看所有记录信息
            • 无法修改物料信息
            • 无法进行拍照操作
            • 所有输入控件将被禁用
            
            如需修改记录，请使用管理员账户登录。
        """.trimIndent()

        val builder = MaterialAlertDialogBuilder(context)
            .setTitle("只读模式")
            .setMessage(message)
            .setIcon(R.drawable.ic_visibility)
            .setCancelable(true)
            .setPositiveButton("继续查看") { dialog, _ ->
                dialog.dismiss()
                onContinue?.invoke()
            }
            .setNegativeButton("返回") { dialog, _ ->
                dialog.dismiss()
            }

        return builder.show()
    }

    /**
     * 显示权限升级提示对话框
     */
    fun showPermissionUpgradeDialog(
        requiredPermission: String,
        onRequestUpgrade: (() -> Unit)? = null
    ): AlertDialog {
        val message = """
            执行此操作需要更高权限：
            
            所需权限：$requiredPermission
            
            请联系系统管理员：
            • 申请权限升级
            • 或使用管理员账户登录
            
            管理员可以在Web后台系统中管理用户权限。
        """.trimIndent()

        val builder = MaterialAlertDialogBuilder(context)
            .setTitle("需要更高权限")
            .setMessage(message)
            .setIcon(R.drawable.ic_security)
            .setCancelable(true)
            .setPositiveButton("确定") { dialog, _ ->
                dialog.dismiss()
            }

        if (onRequestUpgrade != null) {
            builder.setNeutralButton("申请权限") { dialog, _ ->
                dialog.dismiss()
                onRequestUpgrade()
            }
        }

        return builder.show()
    }

    /**
     * 显示操作被阻止的对话框
     */
    fun showOperationBlockedDialog(
        operation: String,
        reason: String,
        onRetryAsAdmin: (() -> Unit)? = null
    ): AlertDialog {
        val message = """
            操作：$operation
            
            操作被阻止的原因：
            $reason
            
            建议解决方案：
            • 使用管理员账户重新登录
            • 联系系统管理员获取权限
            • 检查操作是否符合规范
        """.trimIndent()

        val builder = MaterialAlertDialogBuilder(context)
            .setTitle("操作被阻止")
            .setMessage(message)
            .setIcon(R.drawable.ic_block)
            .setCancelable(true)
            .setPositiveButton("确定") { dialog, _ ->
                dialog.dismiss()
            }

        if (onRetryAsAdmin != null) {
            builder.setNeutralButton("管理员登录") { dialog, _ ->
                dialog.dismiss()
                onRetryAsAdmin()
            }
        }

        return builder.show()
    }

    /**
     * 显示用户权限状态对话框
     */
    fun showUserPermissionStatusDialog(
        authenticationService: AuthenticationService
    ): AlertDialog {
        val currentUser = authenticationService.getCurrentUser()
        val message = if (currentUser != null) {
            val roleName = when (currentUser.role.name) {
                "ADMIN" -> "管理员"
                "USER" -> "普通用户"
                else -> "未知角色"
            }
            
            val permissions = mutableListOf<String>()
            
            // 检查各种权限
            if (authenticationService.hasPermission(PermissionService.Permission.WEB_VIEW_RECORDS)) {
                permissions.add("• 查看Web后台记录")
            }
            if (authenticationService.hasPermission(PermissionService.Permission.WEB_MODIFY_RECORDS)) {
                permissions.add("• 修改Web后台记录")
            }
            if (authenticationService.hasPermission(PermissionService.Permission.WEB_DELETE_RECORDS)) {
                permissions.add("• 删除Web后台记录")
            }
            if (authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD)) {
                permissions.add("• 移动端物料记录")
            }
            if (authenticationService.hasPermission(PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL)) {
                permissions.add("• 修改已存在记录")
            }
            if (authenticationService.hasPermission(PermissionService.Permission.MOBILE_PROCESS_RECORD)) {
                permissions.add("• 移动端工序记录")
            }
            
            """
                用户信息：
                姓名：${currentUser.displayName}
                用户名：${currentUser.synologyUsername}
                角色：$roleName
                
                当前权限：
                ${permissions.joinToString("\n")}
                
                登录时间：${currentUser.lastLoginAt ?: "未知"}
            """.trimIndent()
        } else {
            "当前没有用户登录"
        }

        return MaterialAlertDialogBuilder(context)
            .setTitle("用户权限状态")
            .setMessage(message)
            .setIcon(R.drawable.ic_person)
            .setPositiveButton("确定") { dialog, _ ->
                dialog.dismiss()
            }
            .show()
    }

    /**
     * 显示权限验证失败的通用对话框
     */
    fun showPermissionValidationFailedDialog(
        error: String,
        onRetry: (() -> Unit)? = null
    ): AlertDialog {
        val message = """
            权限验证过程中发生错误：
            
            错误信息：$error
            
            可能的原因：
            • 网络连接问题
            • 认证服务器异常
            • 用户会话过期
            • 系统配置错误
            
            请稍后重试或联系技术支持。
        """.trimIndent()

        val builder = MaterialAlertDialogBuilder(context)
            .setTitle("权限验证失败")
            .setMessage(message)
            .setIcon(R.drawable.ic_error)
            .setCancelable(true)
            .setPositiveButton("确定") { dialog, _ ->
                dialog.dismiss()
            }

        if (onRetry != null) {
            builder.setNeutralButton("重试") { dialog, _ ->
                dialog.dismiss()
                onRetry()
            }
        }

        return builder.show()
    }

    /**
     * 显示会话过期对话框
     */
    fun showSessionExpiredDialog(
        onReLogin: (() -> Unit)? = null
    ): AlertDialog {
        val message = """
            您的登录会话已过期。
            
            为了保护系统安全，请重新登录以继续使用。
            
            会话过期可能由以下原因导致：
            • 长时间未操作
            • 系统安全策略
            • 网络连接中断
        """.trimIndent()

        val builder = MaterialAlertDialogBuilder(context)
            .setTitle("会话已过期")
            .setMessage(message)
            .setIcon(R.drawable.ic_time)
            .setCancelable(false)
            .setPositiveButton("重新登录") { dialog, _ ->
                dialog.dismiss()
                onReLogin?.invoke()
            }

        return builder.show()
    }

    /**
     * 创建自定义权限提示视图
     */
    fun createPermissionStatusView(
        userRole: String,
        canModify: Boolean,
        productSerial: String? = null
    ): View {
        val inflater = LayoutInflater.from(context)
        val view = inflater.inflate(R.layout.view_permission_status, null)
        
        val statusText = view.findViewById<TextView>(R.id.tvPermissionStatus)
        val detailText = view.findViewById<TextView>(R.id.tvPermissionDetail)
        
        val statusMessage = if (canModify) {
            "✓ $userRole - 可编辑"
        } else {
            "⚠ $userRole - 只读模式"
        }
        
        statusText.text = statusMessage
        
        val detailMessage = if (productSerial != null) {
            if (canModify) {
                "产品 $productSerial 可以修改"
            } else {
                "产品 $productSerial 已存在，只能查看"
            }
        } else {
            if (canModify) {
                "具有完整操作权限"
            } else {
                "权限受限，部分功能不可用"
            }
        }
        
        detailText.text = detailMessage
        
        // 设置颜色主题
        if (canModify) {
            statusText.setTextColor(context.getColor(android.R.color.holo_green_dark))
            view.setBackgroundColor(context.getColor(android.R.color.holo_green_light))
        } else {
            statusText.setTextColor(context.getColor(android.R.color.holo_orange_dark))
            view.setBackgroundColor(context.getColor(android.R.color.holo_orange_light))
        }
        
        return view
    }
}