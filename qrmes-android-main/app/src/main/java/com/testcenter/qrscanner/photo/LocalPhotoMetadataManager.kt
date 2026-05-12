package com.testcenter.qrscanner.photo

import android.content.Context
import android.content.SharedPreferences
import com.testcenter.qrscanner.utils.AppLogger
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * 本地照片元数据管理器
 * 负责在本地存储和管理照片元数据，支持离线操作
 */
class LocalPhotoMetadataManager(private val context: Context) {
    
    companion object {
        private const val TAG = "LocalPhotoMetadataManager"
        private const val PREFS_NAME = "photo_metadata"
        private const val KEY_METADATA_LIST = "metadata_list"
        private const val KEY_UPLOAD_QUEUE = "upload_queue"
    }
    
    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    
    /**
     * 保存照片元数据到本地
     */
    fun savePhotoMetadata(metadata: PhotoMetadata): Boolean {
        return try {
            val metadataList = getLocalMetadataList().toMutableList()
            
            // 检查是否已存在相同的照片
            val existingIndex = metadataList.indexOfFirst { 
                it.filePath == metadata.filePath 
            }
            
            if (existingIndex >= 0) {
                // 更新现有记录
                metadataList[existingIndex] = metadata
                AppLogger.log(TAG, "更新本地照片元数据: ${metadata.fileName}")
            } else {
                // 添加新记录
                metadataList.add(metadata)
                AppLogger.log(TAG, "保存本地照片元数据: ${metadata.fileName}")
            }
            
            saveMetadataList(metadataList)
            true
        } catch (e: Exception) {
            AppLogger.log(TAG, "保存照片元数据失败: ${e.message}")
            false
        }
    }
    
    /**
     * 获取产品的所有照片元数据
     */
    fun getProductPhotos(productSerial: String): List<PhotoMetadata> {
        return getLocalMetadataList().filter { it.productSerial == productSerial }
    }
    
    /**
     * 获取工序的所有照片元数据
     */
    fun getProcessPhotos(processStep: String): List<PhotoMetadata> {
        return getLocalMetadataList().filter { it.processStep == processStep }
    }
    
    /**
     * 根据文件路径获取照片元数据
     */
    fun getPhotoByPath(filePath: String): PhotoMetadata? {
        return getLocalMetadataList().find { it.filePath == filePath }
    }
    
    /**
     * 获取所有未上传的照片
     */
    fun getPendingUploadPhotos(): List<PhotoMetadata> {
        return getLocalMetadataList().filter { !it.isUploaded() }
    }
    
    /**
     * 更新照片上传状态
     */
    fun updateUploadStatus(filePath: String, uploaded: Boolean): Boolean {
        return try {
            val metadataList = getLocalMetadataList().toMutableList()
            val index = metadataList.indexOfFirst { it.filePath == filePath }
            
            if (index >= 0) {
                val metadata = metadataList[index]
                val updatedMetadata = metadata.copy(
                    uploadedAt = if (uploaded) System.currentTimeMillis() else null
                )
                metadataList[index] = updatedMetadata
                saveMetadataList(metadataList)
                
                AppLogger.log(TAG, "更新照片上传状态: ${metadata.fileName}, 已上传: $uploaded")
                true
            } else {
                AppLogger.log(TAG, "未找到照片元数据: $filePath")
                false
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "更新上传状态失败: ${e.message}")
            false
        }
    }
    
    /**
     * 删除照片元数据
     */
    fun deletePhotoMetadata(filePath: String): Boolean {
        return try {
            val metadataList = getLocalMetadataList().toMutableList()
            val removed = metadataList.removeAll { it.filePath == filePath }
            
            if (removed) {
                saveMetadataList(metadataList)
                AppLogger.log(TAG, "删除照片元数据: $filePath")
            }
            
            removed
        } catch (e: Exception) {
            AppLogger.log(TAG, "删除照片元数据失败: ${e.message}")
            false
        }
    }
    
    /**
     * 清理已删除文件的元数据
     */
    fun cleanupDeletedFiles(): Int {
        val metadataList = getLocalMetadataList().toMutableList()
        val initialSize = metadataList.size
        
        // 移除文件不存在的元数据
        metadataList.removeAll { metadata ->
            val file = File(metadata.filePath)
            !file.exists()
        }
        
        val removedCount = initialSize - metadataList.size
        if (removedCount > 0) {
            saveMetadataList(metadataList)
            AppLogger.log(TAG, "清理已删除文件的元数据: $removedCount 条")
        }
        
        return removedCount
    }
    
    /**
     * 获取照片统计信息
     */
    fun getPhotoStatistics(): PhotoStatistics {
        val metadataList = getLocalMetadataList()
        val totalPhotos = metadataList.size
        val uploadedPhotos = metadataList.count { it.isUploaded() }
        val pendingPhotos = totalPhotos - uploadedPhotos
        
        // 按工序统计
        val byProcess = metadataList.groupBy { it.processStep }
            .mapValues { it.value.size }
        
        // 按产品统计
        val byProduct = metadataList.groupBy { it.productSerial }
            .mapValues { it.value.size }
        
        // 计算总文件大小
        val totalSize = metadataList.sumOf { it.fileSize }
        
        return PhotoStatistics(
            totalPhotos = totalPhotos,
            uploadedPhotos = uploadedPhotos,
            pendingPhotos = pendingPhotos,
            totalSize = totalSize,
            byProcess = byProcess,
            byProduct = byProduct
        )
    }
    
    /**
     * 添加照片到上传队列
     */
    fun addToUploadQueue(metadata: PhotoMetadata) {
        val uploadQueue = getUploadQueue().toMutableList()
        
        // 检查是否已在队列中
        if (!uploadQueue.any { it.filePath == metadata.filePath }) {
            uploadQueue.add(metadata)
            saveUploadQueue(uploadQueue)
            AppLogger.log(TAG, "添加到上传队列: ${metadata.fileName}")
        }
    }
    
    /**
     * 从上传队列中移除照片
     */
    fun removeFromUploadQueue(filePath: String) {
        val uploadQueue = getUploadQueue().toMutableList()
        val removed = uploadQueue.removeAll { it.filePath == filePath }
        
        if (removed) {
            saveUploadQueue(uploadQueue)
            AppLogger.log(TAG, "从上传队列移除: $filePath")
        }
    }
    
    /**
     * 获取上传队列
     */
    fun getUploadQueue(): List<PhotoMetadata> {
        return try {
            val queueJson = prefs.getString(KEY_UPLOAD_QUEUE, "[]") ?: "[]"
            val jsonArray = JSONArray(queueJson)
            
            (0 until jsonArray.length()).mapNotNull { index ->
                val jsonString = jsonArray.getString(index)
                PhotoMetadata.fromJson(jsonString)
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "获取上传队列失败: ${e.message}")
            emptyList()
        }
    }
    
    /**
     * 清空上传队列
     */
    fun clearUploadQueue() {
        prefs.edit().remove(KEY_UPLOAD_QUEUE).apply()
        AppLogger.log(TAG, "清空上传队列")
    }
    
    /**
     * 导出所有元数据为JSON
     */
    fun exportMetadata(): String {
        val metadataList = getLocalMetadataList()
        val jsonArray = JSONArray()
        
        metadataList.forEach { metadata ->
            jsonArray.put(metadata.toJson())
        }
        
        return jsonArray.toString(2)
    }
    
    /**
     * 从JSON导入元数据
     */
    fun importMetadata(jsonString: String): Boolean {
        return try {
            val jsonArray = JSONArray(jsonString)
            val metadataList = mutableListOf<PhotoMetadata>()
            
            for (i in 0 until jsonArray.length()) {
                val metadataJson = jsonArray.getString(i)
                PhotoMetadata.fromJson(metadataJson)?.let { metadata ->
                    metadataList.add(metadata)
                }
            }
            
            saveMetadataList(metadataList)
            AppLogger.log(TAG, "导入照片元数据: ${metadataList.size} 条")
            true
        } catch (e: Exception) {
            AppLogger.log(TAG, "导入照片元数据失败: ${e.message}")
            false
        }
    }
    
    /**
     * 获取本地元数据列表
     */
    private fun getLocalMetadataList(): List<PhotoMetadata> {
        return try {
            val metadataJson = prefs.getString(KEY_METADATA_LIST, "[]") ?: "[]"
            val jsonArray = JSONArray(metadataJson)
            
            (0 until jsonArray.length()).mapNotNull { index ->
                val jsonString = jsonArray.getString(index)
                PhotoMetadata.fromJson(jsonString)
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "获取本地元数据列表失败: ${e.message}")
            emptyList()
        }
    }
    
    /**
     * 保存元数据列表
     */
    private fun saveMetadataList(metadataList: List<PhotoMetadata>) {
        val jsonArray = JSONArray()
        metadataList.forEach { metadata ->
            jsonArray.put(metadata.toJson())
        }
        
        prefs.edit()
            .putString(KEY_METADATA_LIST, jsonArray.toString())
            .apply()
    }
    
    /**
     * 保存上传队列
     */
    private fun saveUploadQueue(uploadQueue: List<PhotoMetadata>) {
        val jsonArray = JSONArray()
        uploadQueue.forEach { metadata ->
            jsonArray.put(metadata.toJson())
        }
        
        prefs.edit()
            .putString(KEY_UPLOAD_QUEUE, jsonArray.toString())
            .apply()
    }
}

/**
 * 照片统计信息数据类
 */
data class PhotoStatistics(
    val totalPhotos: Int,
    val uploadedPhotos: Int,
    val pendingPhotos: Int,
    val totalSize: Long,
    val byProcess: Map<String, Int>,
    val byProduct: Map<String, Int>
)