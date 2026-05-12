package com.testcenter.qrscanner.security

import android.content.Context
import com.testcenter.qrscanner.utils.AppLogger
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

/**
 * 操作审计日志记录器
 * 记录所有敏感操作和安全事件
 */
class AuditLogger(private val context: Context) {
    
    companion object {
        private const val TAG = "AuditLogger"
        private const val AUDIT_DIR = "audit_logs"
    }
    
    private val auditDir: File by lazy {
        File(context.filesDir, AUDIT_DIR).apply {
            if (!exists()) {
                mkdirs()
            }
        }
    }
    
    /**
     * 事件类型
     */
    enum class EventType {
        AUTHENTICATION,     // 认证
        AUTHORIZATION,      // 授权
        FILE_UPLOAD,        // 文件上传
        DATA_ACCESS,        // 数据访问
        DATA_MODIFICATION,  // 数据修改
        CONFIGURATION,      // 配置变更
        SECURITY_VIOLATION  // 安全违规
    }
    
    /**
     * 操作结果
     */
    enum class OperationResult {
        SUCCESS,    // 成功
        FAILURE,    // 失败
        DENIED      // 拒绝
    }
    
    /**
     * 审计日志条目
     */
    data class AuditLogEntry(
        val timestamp: String,
        val eventType: EventType,
        val username: String,
        val operation: String,
        val target: String,
        val result: OperationResult,
        val details: Map<String, String> = emptyMap(),
        val deviceInfo: String = ""
    )
    
    /**
     * 记录安全事件
     */
    fun logSecurityEvent(
        eventType: EventType,
        username: String,
        operation: String,
        target: String = "",
        result: OperationResult = OperationResult.SUCCESS,
        details: Map<String, String> = emptyMap()
    ) {
        val timestamp = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.getDefault()).format(Date())
        val deviceInfo = getDeviceInfo()
        
        val logEntry = AuditLogEntry(
            timestamp = timestamp,
            eventType = eventType,
            username = username,
            operation = operation,
            target = target,
            result = result,
            details = details,
            deviceInfo = deviceInfo
        )
        
        // 记录到应用日志
        val logLevel = if (result == OperationResult.SUCCESS) "INFO" else "WARNING"
        AppLogger.log(
            TAG,
            "[$logLevel] [安全审计] $eventType | $username | $operation | $target | $result"
        )
        
        // 写入审计日志文件
        writeToAuditLog(logEntry)
    }
    
    /**
     * 记录认证尝试
     */
    fun logAuthenticationAttempt(
        username: String,
        success: Boolean,
        errorMessage: String = ""
    ) {
        logSecurityEvent(
            eventType = EventType.AUTHENTICATION,
            username = username,
            operation = "login",
            result = if (success) OperationResult.SUCCESS else OperationResult.FAILURE,
            details = if (errorMessage.isNotEmpty()) mapOf("error" to errorMessage) else emptyMap()
        )
    }
    
    /**
     * 记录权限检查
     */
    fun logPermissionCheck(
        username: String,
        operation: String,
        target: String,
        allowed: Boolean
    ) {
        logSecurityEvent(
            eventType = EventType.AUTHORIZATION,
            username = username,
            operation = operation,
            target = target,
            result = if (allowed) OperationResult.SUCCESS else OperationResult.DENIED
        )
    }
    
    /**
     * 记录文件上传
     */
    fun logFileUpload(
        username: String,
        filename: String,
        fileSize: Long,
        fileHash: String,
        success: Boolean
    ) {
        logSecurityEvent(
            eventType = EventType.FILE_UPLOAD,
            username = username,
            operation = "upload",
            target = filename,
            result = if (success) OperationResult.SUCCESS else OperationResult.FAILURE,
            details = mapOf(
                "file_size" to fileSize.toString(),
                "file_hash" to fileHash
            )
        )
    }
    
    /**
     * 记录数据访问
     */
    fun logDataAccess(
        username: String,
        operation: String,
        target: String,
        recordCount: Int = 0
    ) {
        logSecurityEvent(
            eventType = EventType.DATA_ACCESS,
            username = username,
            operation = operation,
            target = target,
            result = OperationResult.SUCCESS,
            details = mapOf("record_count" to recordCount.toString())
        )
    }
    
    /**
     * 记录数据修改
     */
    fun logDataModification(
        username: String,
        operation: String,
        target: String,
        success: Boolean,
        changes: Map<String, String> = emptyMap()
    ) {
        logSecurityEvent(
            eventType = EventType.DATA_MODIFICATION,
            username = username,
            operation = operation,
            target = target,
            result = if (success) OperationResult.SUCCESS else OperationResult.FAILURE,
            details = changes
        )
    }
    
    /**
     * 记录配置变更
     */
    fun logConfigurationChange(
        username: String,
        configName: String,
        oldValue: String,
        newValue: String
    ) {
        logSecurityEvent(
            eventType = EventType.CONFIGURATION,
            username = username,
            operation = "modify_config",
            target = configName,
            result = OperationResult.SUCCESS,
            details = mapOf(
                "old_value" to oldValue,
                "new_value" to newValue
            )
        )
    }
    
    /**
     * 记录安全违规
     */
    fun logSecurityViolation(
        username: String,
        operation: String,
        target: String,
        reason: String
    ) {
        logSecurityEvent(
            eventType = EventType.SECURITY_VIOLATION,
            username = username,
            operation = operation,
            target = target,
            result = OperationResult.DENIED,
            details = mapOf("reason" to reason)
        )
    }
    
    /**
     * 写入审计日志文件
     */
    private fun writeToAuditLog(logEntry: AuditLogEntry) {
        try {
            // 按日期创建日志文件
            val dateStr = SimpleDateFormat("yyyyMMdd", Locale.getDefault()).format(Date())
            val logFile = File(auditDir, "audit_$dateStr.log")
            
            // 转换为JSON格式
            val jsonObject = JSONObject().apply {
                put("timestamp", logEntry.timestamp)
                put("event_type", logEntry.eventType.name)
                put("username", logEntry.username)
                put("operation", logEntry.operation)
                put("target", logEntry.target)
                put("result", logEntry.result.name)
                put("device_info", logEntry.deviceInfo)
                
                if (logEntry.details.isNotEmpty()) {
                    val detailsJson = JSONObject()
                    logEntry.details.forEach { (key, value) ->
                        detailsJson.put(key, value)
                    }
                    put("details", detailsJson)
                }
            }
            
            // 追加到日志文件
            logFile.appendText(jsonObject.toString() + "\n")
            
        } catch (e: Exception) {
            AppLogger.log(TAG, "写入审计日志失败: ${e.message}")
        }
    }
    
    /**
     * 获取设备信息
     */
    private fun getDeviceInfo(): String {
        return try {
            val manufacturer = android.os.Build.MANUFACTURER
            val model = android.os.Build.MODEL
            val version = android.os.Build.VERSION.RELEASE
            "$manufacturer $model (Android $version)"
        } catch (e: Exception) {
            "Unknown"
        }
    }
    
    /**
     * 获取审计日志文件列表
     */
    fun getAuditLogFiles(): List<File> {
        return auditDir.listFiles()?.toList() ?: emptyList()
    }
    
    /**
     * 读取审计日志
     */
    fun readAuditLog(date: String): List<AuditLogEntry> {
        val logFile = File(auditDir, "audit_$date.log")
        if (!logFile.exists()) {
            return emptyList()
        }
        
        val entries = mutableListOf<AuditLogEntry>()
        
        try {
            logFile.forEachLine { line ->
                if (line.isNotBlank()) {
                    val jsonObject = JSONObject(line)
                    
                    val details = mutableMapOf<String, String>()
                    if (jsonObject.has("details")) {
                        val detailsJson = jsonObject.getJSONObject("details")
                        detailsJson.keys().forEach { key ->
                            details[key] = detailsJson.getString(key)
                        }
                    }
                    
                    val entry = AuditLogEntry(
                        timestamp = jsonObject.getString("timestamp"),
                        eventType = EventType.valueOf(jsonObject.getString("event_type")),
                        username = jsonObject.getString("username"),
                        operation = jsonObject.getString("operation"),
                        target = jsonObject.getString("target"),
                        result = OperationResult.valueOf(jsonObject.getString("result")),
                        details = details,
                        deviceInfo = jsonObject.optString("device_info", "")
                    )
                    
                    entries.add(entry)
                }
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "读取审计日志失败: ${e.message}")
        }
        
        return entries
    }
    
    /**
     * 清理旧的审计日志（保留最近N天）
     */
    fun cleanupOldLogs(daysToKeep: Int = 90) {
        try {
            val cutoffTime = System.currentTimeMillis() - (daysToKeep * 24 * 60 * 60 * 1000L)
            
            auditDir.listFiles()?.forEach { file ->
                if (file.lastModified() < cutoffTime) {
                    file.delete()
                    AppLogger.log(TAG, "删除旧审计日志: ${file.name}")
                }
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "清理旧审计日志失败: ${e.message}")
        }
    }
}
