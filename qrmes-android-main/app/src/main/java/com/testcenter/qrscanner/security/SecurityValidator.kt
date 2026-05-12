package com.testcenter.qrscanner.security

import android.content.Context
import com.testcenter.qrscanner.utils.AppLogger
import java.io.File
import java.security.MessageDigest

/**
 * 安全验证器
 * 提供文件上传安全检查和权限验证增强
 */
class SecurityValidator(private val context: Context) {
    
    companion object {
        private const val TAG = "SecurityValidator"
        
        // 允许的文件扩展名
        private val ALLOWED_EXTENSIONS = setOf("jpg", "jpeg", "png", "gif", "bmp", "webp")
        
        // 最大文件大小（字节）
        private const val MAX_FILE_SIZE = 10 * 1024 * 1024L // 10MB
        
        // 图片文件头特征
        private val IMAGE_SIGNATURES = mapOf(
            "jpg" to listOf(byteArrayOf(0xFF.toByte(), 0xD8.toByte(), 0xFF.toByte())),
            "jpeg" to listOf(byteArrayOf(0xFF.toByte(), 0xD8.toByte(), 0xFF.toByte())),
            "png" to listOf(byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)),
            "gif" to listOf(
                byteArrayOf(0x47, 0x49, 0x46, 0x38, 0x37, 0x61), // GIF87a
                byteArrayOf(0x47, 0x49, 0x46, 0x38, 0x39, 0x61)  // GIF89a
            ),
            "bmp" to listOf(byteArrayOf(0x42, 0x4D)),
            "webp" to listOf(byteArrayOf(0x52, 0x49, 0x46, 0x46)) // RIFF
        )
    }
    
    /**
     * 文件验证结果
     */
    data class FileValidationResult(
        val valid: Boolean,
        val error: String? = null,
        val warnings: List<String> = emptyList()
    )
    
    /**
     * 权限验证结果
     */
    data class PermissionValidationResult(
        val allowed: Boolean,
        val reason: String,
        val requiresAudit: Boolean = false
    )
    
    /**
     * 验证文件上传
     */
    fun validateFileUpload(file: File): FileValidationResult {
        val warnings = mutableListOf<String>()
        
        // 检查文件是否存在
        if (!file.exists()) {
            return FileValidationResult(
                valid = false,
                error = "文件不存在"
            )
        }
        
        // 检查文件名
        val filename = file.name
        if (filename.isBlank()) {
            return FileValidationResult(
                valid = false,
                error = "文件名为空"
            )
        }
        
        // 检查文件扩展名
        if (!filename.contains('.')) {
            return FileValidationResult(
                valid = false,
                error = "文件没有扩展名"
            )
        }
        
        val ext = filename.substringAfterLast('.').lowercase()
        if (ext !in ALLOWED_EXTENSIONS) {
            return FileValidationResult(
                valid = false,
                error = "不支持的文件类型: $ext"
            )
        }
        
        // 检查文件大小
        val fileSize = file.length()
        if (fileSize == 0L) {
            return FileValidationResult(
                valid = false,
                error = "文件为空"
            )
        }
        
        if (fileSize > MAX_FILE_SIZE) {
            return FileValidationResult(
                valid = false,
                error = "文件过大: ${fileSize / (1024 * 1024)}MB，最大允许 ${MAX_FILE_SIZE / (1024 * 1024)}MB"
            )
        }
        
        // 验证文件头
        if (!isValidImageHeader(file, ext)) {
            return FileValidationResult(
                valid = false,
                error = "文件头与扩展名不匹配，可能是伪装文件"
            )
        }
        
        AppLogger.log(TAG, "文件验证通过: $filename, 大小: ${fileSize}字节")
        
        return FileValidationResult(
            valid = true,
            warnings = warnings
        )
    }
    
    /**
     * 验证图片文件头
     */
    private fun isValidImageHeader(file: File, ext: String): Boolean {
        try {
            val signatures = IMAGE_SIGNATURES[ext] ?: return false
            
            file.inputStream().use { input ->
                val header = ByteArray(512)
                val bytesRead = input.read(header)
                
                if (bytesRead < 8) {
                    return false
                }
                
                for (signature in signatures) {
                    if (header.startsWith(signature)) {
                        return true
                    }
                }
            }
            
            return false
        } catch (e: Exception) {
            AppLogger.log(TAG, "验证文件头失败: ${e.message}")
            return false
        }
    }
    
    /**
     * 检查字节数组是否以指定前缀开始
     */
    private fun ByteArray.startsWith(prefix: ByteArray): Boolean {
        if (this.size < prefix.size) {
            return false
        }
        
        for (i in prefix.indices) {
            if (this[i] != prefix[i]) {
                return false
            }
        }
        
        return true
    }
    
    /**
     * 计算文件的SHA256哈希值
     */
    fun calculateFileHash(file: File): String {
        try {
            val digest = MessageDigest.getInstance("SHA-256")
            
            file.inputStream().use { input ->
                val buffer = ByteArray(8192)
                var bytesRead: Int
                
                while (input.read(buffer).also { bytesRead = it } != -1) {
                    digest.update(buffer, 0, bytesRead)
                }
            }
            
            val hashBytes = digest.digest()
            return hashBytes.joinToString("") { "%02x".format(it) }
            
        } catch (e: Exception) {
            AppLogger.log(TAG, "计算文件哈希失败: ${e.message}")
            return ""
        }
    }
    
    /**
     * 清理文件名，移除危险字符
     */
    fun sanitizeFilename(filename: String): String {
        var safe = filename
            .replace("..", "")
            .replace("/", "")
            .replace("\\", "")
            .replace(":", "")
            .replace("*", "")
            .replace("?", "")
            .replace("\"", "")
            .replace("<", "")
            .replace(">", "")
            .replace("|", "")
        
        // 限制文件名长度
        if (safe.length > 255) {
            val ext = safe.substringAfterLast('.', "")
            val name = safe.substringBeforeLast('.')
            safe = name.take(255 - ext.length - 1) + "." + ext
        }
        
        return safe
    }
    
    /**
     * 验证用户权限
     */
    fun validatePermission(
        username: String,
        role: String,
        operation: String,
        target: String = ""
    ): PermissionValidationResult {
        // 管理员拥有所有权限
        if (role == "admin") {
            return PermissionValidationResult(
                allowed = true,
                reason = "管理员权限",
                requiresAudit = isSensitiveOperation(operation)
            )
        }
        
        // 普通用户权限检查
        val allowedOperations = setOf(
            "view_record",
            "create_record",
            "view_photo",
            "upload_photo"
        )
        
        if (operation in allowedOperations) {
            return PermissionValidationResult(
                allowed = true,
                reason = "用户权限"
            )
        }
        
        AppLogger.log(TAG, "权限拒绝: 用户 $username (角色: $role) 尝试执行 $operation")
        
        return PermissionValidationResult(
            allowed = false,
            reason = "角色 $role 无权执行 $operation 操作",
            requiresAudit = true
        )
    }
    
    /**
     * 判断是否是敏感操作
     */
    private fun isSensitiveOperation(operation: String): Boolean {
        val sensitiveOperations = setOf(
            "delete_record",
            "modify_record",
            "delete_user",
            "modify_user_role",
            "modify_config",
            "export_data"
        )
        
        return operation in sensitiveOperations
    }
}
