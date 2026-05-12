package com.testcenter.qrscanner.photo

import android.content.Context
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.asRequestBody
import okio.buffer
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicBoolean

/**
 * 照片上传服务
 * 支持异步上传、断点续传和重试机制
 */
class PhotoUploadService(
    private val context: Context,
    private val baseUrl: String = "http://localhost:5000"
) {
    
    companion object {
        private const val TAG = "PhotoUploadService"
        private const val UPLOAD_ENDPOINT = "/api/photos/upload"
        private const val METADATA_ENDPOINT = "/api/photos/metadata"
        private const val MAX_CONCURRENT_UPLOADS = 3
        private const val RETRY_DELAY_MS = 5000L
    }
    
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
        .writeTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
        .readTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
        .build()
    
    private val uploadQueue = ConcurrentLinkedQueue<PhotoUploadTask>()
    private val isProcessing = AtomicBoolean(false)
    private val uploadScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    
    // 上传进度监听器
    private var progressListener: ((PhotoUploadTask, Int) -> Unit)? = null
    private var statusListener: ((PhotoUploadTask, PhotoUploadStatus) -> Unit)? = null
    
    /**
     * 设置上传进度监听器
     */
    fun setProgressListener(listener: (PhotoUploadTask, Int) -> Unit) {
        this.progressListener = listener
    }
    
    /**
     * 设置状态变化监听器
     */
    fun setStatusListener(listener: (PhotoUploadTask, PhotoUploadStatus) -> Unit) {
        this.statusListener = listener
    }
    
    /**
     * 添加照片到上传队列
     */
    fun queuePhotoUpload(task: PhotoUploadTask) {
        uploadQueue.offer(task)
        AppLogger.log(TAG, "照片加入上传队列: ${task.metadata.fileName}")
        
        // 启动处理队列
        processUploadQueue()
    }
    
    /**
     * 批量添加照片到上传队列
     */
    fun queuePhotosUpload(tasks: List<PhotoUploadTask>) {
        tasks.forEach { uploadQueue.offer(it) }
        AppLogger.log(TAG, "批量加入上传队列: ${tasks.size} 张照片")
        processUploadQueue()
    }
    
    /**
     * 处理上传队列
     */
    private fun processUploadQueue() {
        if (isProcessing.compareAndSet(false, true)) {
            uploadScope.launch {
                try {
                    val activeTasks = mutableListOf<Deferred<Unit>>()
                    
                    while (uploadQueue.isNotEmpty() || activeTasks.isNotEmpty()) {
                        // 启动新的上传任务（最多同时进行MAX_CONCURRENT_UPLOADS个）
                        while (activeTasks.size < MAX_CONCURRENT_UPLOADS && uploadQueue.isNotEmpty()) {
                            val task = uploadQueue.poll()
                            if (task != null) {
                                val deferred = async { uploadPhotoWithRetry(task) }
                                activeTasks.add(deferred)
                            }
                        }
                        
                        // 等待至少一个任务完成
                        if (activeTasks.isNotEmpty()) {
                            val completed = activeTasks.first()
                            completed.await()
                            activeTasks.remove(completed)
                        }
                        
                        // 短暂延迟避免过于频繁的检查
                        delay(100)
                    }
                } finally {
                    isProcessing.set(false)
                }
            }
        }
    }
    
    /**
     * 带重试机制的照片上传
     */
    private suspend fun uploadPhotoWithRetry(task: PhotoUploadTask) {
        while (task.canRetry() || task.status == PhotoUploadStatus.PENDING) {
            try {
                updateTaskStatus(task, PhotoUploadStatus.UPLOADING)
                
                // 首先上传照片元数据
                val metadataUploaded = uploadPhotoMetadata(task)
                if (!metadataUploaded) {
                    throw IOException("上传照片元数据失败")
                }
                
                // 然后上传照片文件
                val fileUploaded = uploadPhotoFile(task)
                if (fileUploaded) {
                    updateTaskStatus(task, PhotoUploadStatus.UPLOADED)
                    AppLogger.log(TAG, "照片上传成功: ${task.metadata.fileName}")
                    
                    // 删除本地临时文件
                    if (task.localFile.exists()) {
                        task.localFile.delete()
                        AppLogger.log(TAG, "删除本地临时文件: ${task.localFile.name}")
                    }
                    return
                } else {
                    throw IOException("上传照片文件失败")
                }
                
            } catch (e: Exception) {
                task.lastError = e.message
                task.incrementRetry()
                
                if (task.canRetry()) {
                    AppLogger.log(TAG, "照片上传失败，准备重试 (${task.retryCount}/${task.maxRetries}): ${e.message}")
                    updateTaskStatus(task, PhotoUploadStatus.FAILED)
                    delay(RETRY_DELAY_MS)
                } else {
                    AppLogger.log(TAG, "照片上传最终失败: ${task.metadata.fileName}, 错误: ${e.message}")
                    updateTaskStatus(task, PhotoUploadStatus.FAILED)
                    return
                }
            }
        }
    }
    
    /**
     * 上传照片元数据
     */
    private suspend fun uploadPhotoMetadata(task: PhotoUploadTask): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val json = JSONObject().apply {
                    put("productSerial", task.metadata.productSerial)
                    put("processStep", task.metadata.processStep)
                    put("filePath", task.metadata.filePath)
                    put("fileName", task.metadata.fileName)
                    put("fileSize", task.metadata.fileSize)
                    put("capturedBy", task.metadata.capturedBy)
                    put("capturedAt", task.metadata.capturedAt)
                    put("metadata", JSONObject(task.metadata.metadata))
                }
                
                val requestBody = RequestBody.create(
                    "application/json".toMediaType(),
                    json.toString()
                )
                
                val request = Request.Builder()
                    .url("$baseUrl$METADATA_ENDPOINT")
                    .post(requestBody)
                    .build()
                
                val response = httpClient.newCall(request).execute()
                val success = response.isSuccessful
                
                if (success) {
                    AppLogger.log(TAG, "照片元数据上传成功: ${task.metadata.fileName}")
                } else {
                    AppLogger.log(TAG, "照片元数据上传失败: ${response.code} ${response.message}")
                }
                
                response.close()
                success
            } catch (e: Exception) {
                AppLogger.log(TAG, "上传照片元数据异常: ${e.message}")
                false
            }
        }
    }
    
    /**
     * 上传照片文件
     */
    private suspend fun uploadPhotoFile(task: PhotoUploadTask): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val file = task.localFile
                if (!file.exists()) {
                    AppLogger.log(TAG, "照片文件不存在: ${file.absolutePath}")
                    return@withContext false
                }
                
                val requestBody = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart("productSerial", task.metadata.productSerial)
                    .addFormDataPart("processStep", task.metadata.processStep)
                    .addFormDataPart(
                        "photo",
                        task.metadata.fileName,
                        ProgressRequestBody(
                            file.asRequestBody("image/jpeg".toMediaType()),
                            task
                        ) { progress ->
                            progressListener?.invoke(task, progress)
                        }
                    )
                    .build()
                
                val request = Request.Builder()
                    .url("$baseUrl$UPLOAD_ENDPOINT")
                    .post(requestBody)
                    .build()
                
                val response = httpClient.newCall(request).execute()
                val success = response.isSuccessful
                
                if (success) {
                    AppLogger.log(TAG, "照片文件上传成功: ${task.metadata.fileName}")
                } else {
                    AppLogger.log(TAG, "照片文件上传失败: ${response.code} ${response.message}")
                }
                
                response.close()
                success
            } catch (e: Exception) {
                AppLogger.log(TAG, "上传照片文件异常: ${e.message}")
                false
            }
        }
    }
    
    /**
     * 更新任务状态
     */
    private fun updateTaskStatus(task: PhotoUploadTask, status: PhotoUploadStatus) {
        task.status = status
        statusListener?.invoke(task, status)
    }
    
    /**
     * 获取队列中待上传的照片数量
     */
    fun getPendingUploadCount(): Int = uploadQueue.size
    
    /**
     * 清空上传队列
     */
    fun clearUploadQueue() {
        uploadQueue.clear()
        AppLogger.log(TAG, "清空上传队列")
    }
    
    /**
     * 停止上传服务
     */
    fun shutdown() {
        uploadScope.cancel()
        httpClient.dispatcher.executorService.shutdown()
        AppLogger.log(TAG, "照片上传服务已停止")
    }
}

/**
 * 带进度回调的请求体
 */
private class ProgressRequestBody(
    private val requestBody: RequestBody,
    private val task: PhotoUploadTask,
    private val progressCallback: (Int) -> Unit
) : RequestBody() {
    
    override fun contentType(): MediaType? = requestBody.contentType()
    
    override fun contentLength(): Long = requestBody.contentLength()
    
    override fun writeTo(sink: okio.BufferedSink) {
        val contentLength = contentLength()
        
        val countingSink = object : okio.ForwardingSink(sink) {
            var totalBytesWritten = 0L
            
            override fun write(source: okio.Buffer, byteCount: Long) {
                super.write(source, byteCount)
                totalBytesWritten += byteCount
                
                if (contentLength > 0) {
                    val progress = ((totalBytesWritten * 100) / contentLength).toInt()
                    progressCallback(progress)
                }
            }
        }
        
        val bufferedSink = countingSink.buffer()
        requestBody.writeTo(bufferedSink)
        bufferedSink.flush()
    }
}