package com.testcenter.qrscanner.material

import android.content.Context
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.testcenter.qrscanner.R
import com.testcenter.qrscanner.adapter.ComponentAdapter
import com.testcenter.qrscanner.data.ProductRecord
import com.testcenter.qrscanner.ui.PermissionDialogManager

/**
 * 物料界面控制器
 * 处理物料记录界面的权限控制显示逻辑
 */
class MaterialUIController(private val context: Context) {
    
    companion object {
        private const val TAG = "MaterialUIController"
    }
    
    private val permissionDialogManager = PermissionDialogManager(context)

    /**
     * 应用只读模式到界面
     */
    fun applyReadOnlyMode(
        productInfoLayout: View,
        tvProductSerial: TextView,
        tvOperatorName: TextView,
        tvProjectName: TextView,
        spinnerProductType: Spinner,
        recyclerViewComponents: RecyclerView,
        btnPhotoCapture: MaterialButton,
        productRecord: ProductRecord?,
        permissionMessage: String
    ) {
        // 显示权限提示信息
        showPermissionInfo(permissionMessage)
        
        // 禁用所有输入控件
        disableInputControls(
            spinnerProductType,
            recyclerViewComponents,
            btnPhotoCapture
        )
        
        // 显示已存在的记录数据
        if (productRecord != null) {
            displayExistingRecord(
                tvProductSerial,
                tvOperatorName,
                tvProjectName,
                spinnerProductType,
                productRecord
            )
        }
        
        // 添加只读模式标识
        addReadOnlyIndicator(productInfoLayout)
    }

    /**
     * 恢复编辑模式
     */
    fun applyEditMode(
        productInfoLayout: View,
        spinnerProductType: Spinner,
        recyclerViewComponents: RecyclerView,
        btnPhotoCapture: MaterialButton
    ) {
        // 启用所有输入控件
        enableInputControls(
            spinnerProductType,
            recyclerViewComponents,
            btnPhotoCapture
        )
        
        // 移除只读模式标识
        removeReadOnlyIndicator(productInfoLayout)
    }

    /**
     * 显示权限信息对话框
     */
    private fun showPermissionInfo(message: String) {
        MaterialAlertDialogBuilder(context)
            .setTitle("权限提示")
            .setMessage(message)
            .setIcon(R.drawable.ic_lock)
            .setPositiveButton("确定") { dialog, _ ->
                dialog.dismiss()
            }
            .show()
    }

    /**
     * 禁用输入控件
     */
    private fun disableInputControls(
        spinnerProductType: Spinner,
        recyclerViewComponents: RecyclerView,
        btnPhotoCapture: MaterialButton
    ) {
        // 禁用产品类型选择器
        spinnerProductType.isEnabled = false
        
        // 禁用组件列表的交互
        recyclerViewComponents.isEnabled = false
        
        // 禁用拍照按钮
        btnPhotoCapture.isEnabled = false
        btnPhotoCapture.text = "只读模式 - 无法拍照"
        
        // 如果有ComponentAdapter，设置为只读模式
        val adapter = recyclerViewComponents.adapter
        if (adapter is ComponentAdapter) {
            adapter.setReadOnlyMode(true)
        }
    }

    /**
     * 启用输入控件
     */
    private fun enableInputControls(
        spinnerProductType: Spinner,
        recyclerViewComponents: RecyclerView,
        btnPhotoCapture: MaterialButton
    ) {
        // 启用产品类型选择器
        spinnerProductType.isEnabled = true
        
        // 启用组件列表的交互
        recyclerViewComponents.isEnabled = true
        
        // 启用拍照按钮
        btnPhotoCapture.isEnabled = true
        btnPhotoCapture.text = "拍照记录"
        
        // 如果有ComponentAdapter，设置为编辑模式
        val adapter = recyclerViewComponents.adapter
        if (adapter is ComponentAdapter) {
            adapter.setReadOnlyMode(false)
        }
    }

    /**
     * 显示已存在的记录数据
     */
    private fun displayExistingRecord(
        tvProductSerial: TextView,
        tvOperatorName: TextView,
        tvProjectName: TextView,
        spinnerProductType: Spinner,
        productRecord: ProductRecord
    ) {
        // 显示产品序列号
        tvProductSerial.text = productRecord.productSerial
        
        // 显示操作员信息
        tvOperatorName.text = productRecord.operator ?: "未知操作员"
        
        // 显示项目名称
        tvProjectName.text = productRecord.projectName ?: "未知项目"
        
        // 设置产品类型（如果spinner有对应选项）
        try {
            val productType = productRecord.productType
            if (productType != null) {
                val adapter = spinnerProductType.adapter
                if (adapter != null) {
                    for (i in 0 until adapter.count) {
                        if (adapter.getItem(i).toString() == productType) {
                            spinnerProductType.setSelection(i)
                            break
                        }
                    }
                }
            }
        } catch (e: Exception) {
            // 忽略设置产品类型的错误
        }
    }

    /**
     * 添加只读模式标识
     */
    private fun addReadOnlyIndicator(productInfoLayout: View) {
        // 查找是否已经有只读标识
        val existingIndicator = productInfoLayout.findViewWithTag<TextView>("readonly_indicator")
        if (existingIndicator != null) {
            return // 已经存在，不重复添加
        }

        // 创建只读模式标识
        val readOnlyIndicator = TextView(context).apply {
            text = "🔒 只读模式 - 普通用户无法修改已存在记录"
            setTextColor(context.getColor(android.R.color.holo_orange_dark))
            textSize = 14f
            setPadding(16, 8, 16, 8)
            setBackgroundColor(context.getColor(android.R.color.holo_orange_light))
            tag = "readonly_indicator"
        }

        // 添加到布局顶部
        if (productInfoLayout is android.view.ViewGroup) {
            productInfoLayout.addView(readOnlyIndicator, 0)
        }
    }

    /**
     * 移除只读模式标识
     */
    private fun removeReadOnlyIndicator(productInfoLayout: View) {
        val indicator = productInfoLayout.findViewWithTag<TextView>("readonly_indicator")
        if (indicator != null && productInfoLayout is android.view.ViewGroup) {
            productInfoLayout.removeView(indicator)
        }
    }

    /**
     * 显示权限拒绝提示
     */
    fun showPermissionDeniedDialog(message: String, onRetry: (() -> Unit)? = null) {
        permissionDialogManager.showPermissionDeniedDialog(
            message = message,
            onRetry = onRetry
        )
    }

    /**
     * 显示权限信息Toast
     */
    fun showPermissionToast(message: String, isError: Boolean = false) {
        val duration = if (isError) Toast.LENGTH_LONG else Toast.LENGTH_SHORT
        Toast.makeText(context, message, duration).show()
    }

    /**
     * 创建权限状态指示器
     */
    fun createPermissionStatusView(
        userRole: String,
        canModify: Boolean,
        productSerial: String? = null
    ): View {
        return permissionDialogManager.createPermissionStatusView(
            userRole = userRole,
            canModify = canModify,
            productSerial = productSerial
        )
    }

    /**
     * 显示只读模式提示对话框
     */
    fun showReadOnlyModeDialog(
        productSerial: String,
        userRole: String,
        onContinue: (() -> Unit)? = null
    ) {
        permissionDialogManager.showReadOnlyModeDialog(
            productSerial = productSerial,
            userRole = userRole,
            onContinue = onContinue
        )
    }

    /**
     * 显示权限不足时的修改尝试提示
     */
    fun showModificationAttemptDeniedDialog(
        productSerial: String,
        operation: String,
        onRetryAsAdmin: (() -> Unit)? = null
    ) {
        val reason = "普通用户不能修改已存在的产品记录 ($productSerial)"
        permissionDialogManager.showOperationBlockedDialog(
            operation = operation,
            reason = reason,
            onRetryAsAdmin = onRetryAsAdmin
        )
    }

    /**
     * 显示会话过期对话框
     */
    fun showSessionExpiredDialog(onReLogin: (() -> Unit)? = null) {
        permissionDialogManager.showSessionExpiredDialog(onReLogin)
    }

    /**
     * 显示权限验证失败对话框
     */
    fun showPermissionValidationFailedDialog(
        error: String,
        onRetry: (() -> Unit)? = null
    ) {
        permissionDialogManager.showPermissionValidationFailedDialog(error, onRetry)
    }

    /**
     * 显示修改尝试被阻止的对话框
     */
    fun showModificationBlockedDialog(productSerial: String = "") {
        permissionDialogManager.showMaterialModificationDeniedDialog(
            productSerial = productSerial,
            onContactAdmin = {
                // 可以在这里实现联系管理员的功能
                showPermissionToast("请联系系统管理员获取权限", true)
            }
        )
    }

    /**
     * 显示权限详情对话框
     */
    fun showPermissionDetailsDialog() {
        permissionDialogManager.showPermissionDetailsDialog()
    }
}