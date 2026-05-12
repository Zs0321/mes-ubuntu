package com.testcenter.qrscanner.photo

import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import com.testcenter.qrscanner.utils.AppLogger
import java.io.File
import java.io.FileOutputStream

/**
 * 照片缓存管理器
 * 负责照片的磁盘缓存和公共目录保存
 */
class PhotoCacheManager(private val context: Context) {
    
    companion object {
        private const val TAG = "PhotoCacheManager"
        private const val CACHE_DIR_NAME = "photo_cache"
        private const val MAX_CACHE_SIZE_MB = 100 // 最大缓存100MB
        private const val MAX_CACHE_AGE_DAYS = 7 // 缓存保留7天
        private const val CLEANUP_INTERVAL_MS = 10 * 60 * 1000L // 每 10 分钟最多清理一次
    }

    // 追踪缓存大小，避免每次都遍历文件系统
    @Volatile
    private var estimatedCacheSize: Long = -1L
    @Volatile
    private var lastCleanupTime: Long = 0L
    
    private val cacheDir: File by lazy {
        val dir = File(context.cacheDir, CACHE_DIR_NAME)
        if (!dir.exists()) {
            dir.mkdirs()
        }
        dir
    }
    
    /**
     * 获取缓存的照片文件
     */
    fun getCachedPhoto(productSerial: String, fileName: String): File? {
        val cacheFile = File(getCacheDirectory(productSerial), fileName)
        return if (cacheFile.exists()) {
            AppLogger.log(TAG, "找到缓存照片: ${cacheFile.absolutePath}")
            cacheFile
        } else {
            AppLogger.log(TAG, "缓存照片不存在: ${cacheFile.absolutePath}")
            null
        }
    }
    
    /**
     * 缓存照片到磁盘
     */
    fun cachePhoto(productSerial: String, fileName: String, photoBytes: ByteArray): File? {
        return try {
            val productCacheDir = getCacheDirectory(productSerial)
            val cacheFile = File(productCacheDir, fileName)

            FileOutputStream(cacheFile).use { output ->
                output.write(photoBytes)
            }

            // 增量更新估算大小
            if (estimatedCacheSize >= 0) {
                estimatedCacheSize += photoBytes.size
            }

            AppLogger.log(TAG, "照片已缓存: ${cacheFile.absolutePath} (${photoBytes.size} bytes)")

            // 节流：不要每次写入都清理
            cleanupCacheIfNeeded()

            cacheFile
        } catch (e: Exception) {
            AppLogger.log(TAG, "缓存照片失败: ${e.message}", e)
            null
        }
    }
    
    /**
     * 保存照片到公共目录（相册）
     */
    fun saveToPublicDirectory(sourceFile: File, fileName: String): Boolean {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                // Android 10及以上使用MediaStore
                val contentValues = ContentValues().apply {
                    put(MediaStore.Images.Media.DISPLAY_NAME, fileName)
                    put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                    put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/QRScanner")
                }
                
                val uri = context.contentResolver.insert(
                    MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                    contentValues
                )
                
                if (uri != null) {
                    context.contentResolver.openOutputStream(uri)?.use { output ->
                        sourceFile.inputStream().use { input ->
                            input.copyTo(output)
                        }
                    }
                    AppLogger.log(TAG, "照片已保存到相册: $fileName")
                    true
                } else {
                    AppLogger.log(TAG, "创建MediaStore URI失败")
                    false
                }
            } else {
                // Android 9及以下直接保存到Pictures目录
                val picturesDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES)
                val qrScannerDir = File(picturesDir, "QRScanner")
                if (!qrScannerDir.exists()) {
                    qrScannerDir.mkdirs()
                }
                
                val destFile = File(qrScannerDir, fileName)
                sourceFile.copyTo(destFile, overwrite = true)
                
                // 通知媒体扫描器
                val intent = android.content.Intent(android.content.Intent.ACTION_MEDIA_SCANNER_SCAN_FILE)
                intent.data = android.net.Uri.fromFile(destFile)
                context.sendBroadcast(intent)
                
                AppLogger.log(TAG, "照片已保存到相册: ${destFile.absolutePath}")
                true
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "保存照片到相册失败: ${e.message}", e)
            false
        }
    }
    
    /**
     * 获取产品的缓存目录
     */
    private fun getCacheDirectory(productSerial: String): File {
        val productDir = File(cacheDir, sanitizeFileName(productSerial))
        if (!productDir.exists()) {
            productDir.mkdirs()
        }
        return productDir
    }
    
    /**
     * 清理缓存（如果超过限制）
     */
    private fun cleanupCacheIfNeeded() {
        try {
            val now = System.currentTimeMillis()
            // 节流：距上次清理不足间隔则跳过
            if (now - lastCleanupTime < CLEANUP_INTERVAL_MS) return

            // 首次或过期时才做完整扫描
            if (estimatedCacheSize < 0) {
                estimatedCacheSize = calculateCacheSize()
            }

            val maxSizeBytes = MAX_CACHE_SIZE_MB * 1024 * 1024L
            if (estimatedCacheSize > maxSizeBytes) {
                AppLogger.log(TAG, "缓存超过限制 (${estimatedCacheSize / 1024 / 1024}MB > ${MAX_CACHE_SIZE_MB}MB)，开始清理")
                cleanupOldCache()
                // 清理后重新计算
                estimatedCacheSize = calculateCacheSize()
            }
            lastCleanupTime = now
        } catch (e: Exception) {
            AppLogger.log(TAG, "清理缓存失败: ${e.message}", e)
        }
    }
    
    /**
     * 计算缓存总大小
     */
    private fun calculateCacheSize(): Long {
        var totalSize = 0L
        cacheDir.walkTopDown().forEach { file ->
            if (file.isFile) {
                totalSize += file.length()
            }
        }
        return totalSize
    }
    
    /**
     * 清理旧缓存
     */
    private fun cleanupOldCache() {
        val cutoffTime = System.currentTimeMillis() - (MAX_CACHE_AGE_DAYS * 24 * 60 * 60 * 1000L)
        var deletedCount = 0
        var deletedSize = 0L
        
        cacheDir.walkTopDown().forEach { file ->
            if (file.isFile && file.lastModified() < cutoffTime) {
                val size = file.length()
                if (file.delete()) {
                    deletedCount++
                    deletedSize += size
                }
            }
        }
        
        AppLogger.log(TAG, "清理完成: 删除 $deletedCount 个文件，释放 ${deletedSize / 1024 / 1024}MB 空间")
        
        // 删除空目录
        cacheDir.walkBottomUp().forEach { file ->
            if (file.isDirectory && file.listFiles()?.isEmpty() == true) {
                file.delete()
            }
        }
    }
    
    /**
     * 清空所有缓存
     */
    fun clearAllCache() {
        try {
            var deletedCount = 0
            cacheDir.walkTopDown().forEach { file ->
                if (file.isFile && file.delete()) {
                    deletedCount++
                }
            }
            AppLogger.log(TAG, "清空缓存完成: 删除 $deletedCount 个文件")
        } catch (e: Exception) {
            AppLogger.log(TAG, "清空缓存失败: ${e.message}", e)
        }
    }
    
    /**
     * 获取缓存统计信息
     */
    fun getCacheStats(): CacheStats {
        var fileCount = 0
        var totalSize = 0L
        
        cacheDir.walkTopDown().forEach { file ->
            if (file.isFile) {
                fileCount++
                totalSize += file.length()
            }
        }
        
        return CacheStats(fileCount, totalSize)
    }
    
    private fun sanitizeFileName(fileName: String): String {
        return fileName.replace("[^a-zA-Z0-9\\u4e00-\\u9fa5_-]".toRegex(), "_")
    }
    
    data class CacheStats(
        val fileCount: Int,
        val totalSizeBytes: Long
    ) {
        val totalSizeMB: Float
            get() = totalSizeBytes / (1024f * 1024f)
    }
}
