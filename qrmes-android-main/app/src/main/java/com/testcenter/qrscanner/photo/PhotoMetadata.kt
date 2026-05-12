package com.testcenter.qrscanner.photo

import org.json.JSONObject
import java.util.*

/**
 * 照片元数据模型
 */
data class PhotoMetadata(
    val id: Long? = null,
    val productSerial: String,
    val processStep: String,
    val filePath: String,
    val fileName: String,
    val fileSize: Long,
    val capturedBy: String,
    val capturedAt: Long = System.currentTimeMillis(),
    val uploadedAt: Long? = null,
    val metadata: Map<String, Any> = emptyMap()
) {
    
    /**
     * 转换为JSON字符串
     */
    fun toJson(): String {
        val json = JSONObject()
        json.put("id", id)
        json.put("productSerial", productSerial)
        json.put("processStep", processStep)
        json.put("filePath", filePath)
        json.put("fileName", fileName)
        json.put("fileSize", fileSize)
        json.put("capturedBy", capturedBy)
        json.put("capturedAt", capturedAt)
        json.put("uploadedAt", uploadedAt)
        
        // 添加额外的元数据
        val metadataJson = JSONObject()
        metadata.forEach { (key, value) ->
            metadataJson.put(key, value)
        }
        json.put("metadata", metadataJson)
        
        return json.toString()
    }
    
    /**
     * 是否已上传
     */
    fun isUploaded(): Boolean = uploadedAt != null
    
    /**
     * 获取拍摄时间的格式化字符串
     */
    fun getCapturedTimeString(): String {
        return java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
            .format(Date(capturedAt))
    }
    
    companion object {
        /**
         * 从JSON字符串创建PhotoMetadata
         */
        fun fromJson(jsonString: String): PhotoMetadata? {
            return try {
                val json = JSONObject(jsonString)
                val metadataJson = json.optJSONObject("metadata")
                val metadataMap = mutableMapOf<String, Any>()
                
                metadataJson?.let { meta ->
                    meta.keys().forEach { key ->
                        metadataMap[key] = meta.get(key)
                    }
                }
                
                PhotoMetadata(
                    id = if (json.has("id") && !json.isNull("id")) json.getLong("id") else null,
                    productSerial = json.getString("productSerial"),
                    processStep = json.getString("processStep"),
                    filePath = json.getString("filePath"),
                    fileName = json.getString("fileName"),
                    fileSize = json.getLong("fileSize"),
                    capturedBy = json.getString("capturedBy"),
                    capturedAt = json.getLong("capturedAt"),
                    uploadedAt = if (json.has("uploadedAt") && !json.isNull("uploadedAt")) 
                        json.getLong("uploadedAt") else null,
                    metadata = metadataMap
                )
            } catch (e: Exception) {
                null
            }
        }
        
        /**
         * 创建新的照片元数据
         */
        fun create(
            productSerial: String,
            processStep: String,
            filePath: String,
            fileName: String,
            fileSize: Long,
            capturedBy: String,
            additionalMetadata: Map<String, Any> = emptyMap()
        ): PhotoMetadata {
            return PhotoMetadata(
                productSerial = productSerial,
                processStep = processStep,
                filePath = filePath,
                fileName = fileName,
                fileSize = fileSize,
                capturedBy = capturedBy,
                capturedAt = System.currentTimeMillis(),
                metadata = additionalMetadata
            )
        }
    }
}

/**
 * 照片上传状态枚举
 */
enum class PhotoUploadStatus {
    PENDING,    // 待上传
    UPLOADING,  // 上传中
    UPLOADED,   // 已上传
    FAILED      // 上传失败
}

/**
 * 照片上传任务
 */
data class PhotoUploadTask(
    val metadata: PhotoMetadata,
    val localFile: java.io.File,
    var status: PhotoUploadStatus = PhotoUploadStatus.PENDING,
    var retryCount: Int = 0,
    var lastError: String? = null,
    val maxRetries: Int = 3
) {
    
    /**
     * 是否可以重试
     */
    fun canRetry(): Boolean = retryCount < maxRetries && status == PhotoUploadStatus.FAILED
    
    /**
     * 增加重试次数
     */
    fun incrementRetry() {
        retryCount++
    }
    
    /**
     * 重置重试状态
     */
    fun resetRetry() {
        retryCount = 0
        lastError = null
        status = PhotoUploadStatus.PENDING
    }
}