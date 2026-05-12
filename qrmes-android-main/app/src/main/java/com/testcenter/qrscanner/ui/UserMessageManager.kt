package com.testcenter.qrscanner.ui

import android.app.AlertDialog
import android.content.Context
import android.view.LayoutInflater
import android.widget.Toast
import com.google.android.material.snackbar.Snackbar
import android.view.View
import com.testcenter.qrscanner.R
import com.testcenter.qrscanner.network.NetworkErrorHandler

/**
 * 用户消息管理器
 * 统一管理各种异常情况的用户提示
 */
class UserMessageManager(private val context: Context) {
    
    companion object {
        private const val TAG = "UserMessageManager"
    }
    
    /**
     * 消息类型
     */
    enum class MessageType {
        SUCCESS,    // 成功
        INFO,       // 信息
        WARNING,    // 警告
        ERROR       // 错误
    }
    
    /**
     * 显示Toast消息
     */
    fun showToast(message: String, duration: Int = Toast.LENGTH_SHORT) {
        Toast.makeText(context, message, duration).show()
    }
    
    /**
     * 显示Snackbar消息
     */
    fun showSnackbar(view: View, message: String, duration: Int = Snackbar.LENGTH_SHORT) {
        Snackbar.make(view, message, duration).show()
    }
    
    /**
     * 显示带操作的Snackbar
     */
    fun showSnackbarWithAction(
        view: View,
        message: String,
        actionText: String,
        action: () -> Unit,
        duration: Int = Snackbar.LENGTH_LONG
    ) {
        Snackbar.make(view, message, duration)
            .setAction(actionText) { action() }
            .show()
    }
    
    /**
     * 显示网络错误消息
     */
    fun showNetworkError(
        view: View,
        errorResponse: NetworkErrorHandler.ErrorResponse,
        retryAction: (() -> Unit)? = null
    ) {
        when (errorResponse.action) {
            NetworkErrorHandler.ErrorAction.RETRY -> {
                if (retryAction != null) {
                    showSnackbarWithAction(
                        view,
                        errorResponse.userMessage,
                        "重试",
                        retryAction,
                        Snackbar.LENGTH_LONG
                    )
                } else {
                    showSnackbar(view, errorResponse.userMessage, Snackbar.LENGTH_LONG)
                }
            }
            
            NetworkErrorHandler.ErrorAction.ENABLE_OFFLINE_MODE -> {
                showSnackbarWithAction(
                    view,
                    errorResponse.userMessage,
                    "离线模式",
                    { showOfflineModeDialog() },
                    Snackbar.LENGTH_LONG
                )
            }
            
            else -> {
                showSnackbar(view, errorResponse.userMessage, Snackbar.LENGTH_LONG)
            }
        }
    }
    
    /**
     * 显示确认对话框
     */
    fun showConfirmDialog(
        title: String,
        message: String,
        positiveText: String = "确定",
        negativeText: String = "取消",
        onConfirm: () -> Unit,
        onCancel: (() -> Unit)? = null
    ) {
        AlertDialog.Builder(context)
            .setTitle(title)
            .setMessage(message)
            .setPositiveButton(positiveText) { dialog, _ ->
                onConfirm()
                dialog.dismiss()
            }
            .setNegativeButton(negativeText) { dialog, _ ->
                onCancel?.invoke()
                dialog.dismiss()
            }
            .setCancelable(false)
            .show()
    }
    
    /**
     * 显示信息对话框
     */
    fun showInfoDialog(
        title: String,
        message: String,
        buttonText: String = "确定",
        onDismiss: (() -> Unit)? = null
    ) {
        AlertDialog.Builder(context)
            .setTitle(title)
            .setMessage(message)
            .setPositiveButton(buttonText) { dialog, _ ->
                onDismiss?.invoke()
                dialog.dismiss()
            }
            .show()
    }
    
    /**
     * 显示错误对话框
     */
    fun showErrorDialog(
        title: String = "错误",
        message: String,
        buttonText: String = "确定",
        onDismiss: (() -> Unit)? = null
    ) {
        AlertDialog.Builder(context)
            .setTitle(title)
            .setMessage(message)
            .setIcon(android.R.drawable.ic_dialog_alert)
            .setPositiveButton(buttonText) { dialog, _ ->
                onDismiss?.invoke()
                dialog.dismiss()
            }
            .show()
    }
    
    /**
     * 显示加载对话框
     */
    fun showLoadingDialog(message: String = "加载中..."): AlertDialog {
        return AlertDialog.Builder(context)
            .setMessage(message)
            .setCancelable(false)
            .create()
            .apply { show() }
    }
    
    /**
     * 显示离线模式对话框
     */
    private fun showOfflineModeDialog() {
        AlertDialog.Builder(context)
            .setTitle("离线模式")
            .setMessage("当前网络不可用，应用将进入离线模式。\n\n" +
                    "在离线模式下：\n" +
                    "• 可以查看已缓存的数据\n" +
                    "• 可以记录新数据（将在联网后自动上传）\n" +
                    "• 部分功能可能受限")
            .setPositiveButton("了解") { dialog, _ ->
                dialog.dismiss()
            }
            .show()
    }
    
    /**
     * 显示网络连接恢复提示
     */
    fun showNetworkRestoredMessage(view: View, pendingCount: Int) {
        if (pendingCount > 0) {
            showSnackbarWithAction(
                view,
                "网络已恢复，有 $pendingCount 条待上传数据",
                "立即上传",
                { /* 触发上传操作 */ },
                Snackbar.LENGTH_LONG
            )
        } else {
            showSnackbar(view, "网络已恢复", Snackbar.LENGTH_SHORT)
        }
    }
    
    /**
     * 显示权限不足提示
     */
    fun showPermissionDeniedMessage(view: View, operation: String) {
        showSnackbar(
            view,
            "权限不足，无法执行 $operation 操作",
            Snackbar.LENGTH_LONG
        )
    }
    
    /**
     * 显示操作成功提示
     */
    fun showSuccessMessage(message: String) {
        showToast(message, Toast.LENGTH_SHORT)
    }
    
    /**
     * 显示操作失败提示
     */
    fun showFailureMessage(message: String) {
        showToast(message, Toast.LENGTH_LONG)
    }
    
    /**
     * 显示上传进度对话框
     */
    fun showUploadProgressDialog(
        totalCount: Int,
        onCancel: (() -> Unit)? = null
    ): UploadProgressDialog {
        return UploadProgressDialog(context, totalCount, onCancel)
    }
    
    /**
     * 上传进度对话框
     */
    class UploadProgressDialog(
        context: Context,
        private val totalCount: Int,
        private val onCancel: (() -> Unit)?
    ) {
        private val dialog: AlertDialog
        private var currentProgress = 0
        
        init {
            val builder = AlertDialog.Builder(context)
            builder.setTitle("上传中")
            builder.setMessage("正在上传数据 (0/$totalCount)")
            builder.setCancelable(false)
            
            if (onCancel != null) {
                builder.setNegativeButton("取消") { _, _ ->
                    onCancel.invoke()
                }
            }
            
            dialog = builder.create()
            dialog.show()
        }
        
        fun updateProgress(current: Int) {
            currentProgress = current
            dialog.setMessage("正在上传数据 ($current/$totalCount)")
        }
        
        fun dismiss() {
            dialog.dismiss()
        }
    }
}
