package com.testcenter.qrscanner.photo

import android.content.Context
import android.net.Uri
import android.os.Environment
import com.testcenter.qrscanner.utils.AppLogger
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.text.SimpleDateFormat
import java.util.*

/**
 * 照片存储管理器
 * 负责照片文件的命名、存储和目录管理
 */
class PhotoStorageManager(private val context: Context) {
    
    companion object {
        private const val TAG = "PhotoStorageManager"
        private const val PHOTOS_DIR = "ProcessPhotos"
        private const val TEMP_DIR = "temp"
        private const val DATE_FORMAT = "yyyyMMdd_HHmmss"
        private const val DIR_DATE_FORMAT = "yyyy/MM"
    }
    
    private val dateFormatter = SimpleDateFormat(DATE_FORMAT, Locale.getDefault())
    private val dirDateFormatter = SimpleDateFormat(DIR_DATE_FORMAT, Locale.getDefault())
    
    /**
     * 生成照片文件名
     * 格式: {产品序列号}_{工序名称}_{时间戳}.jpg
     */
    fun generatePhotoFileName(productSerial: String, processStepName: String): String {
        val timestamp = dateFormatter.format(Date())
        val sanitizedSerial = sanitizeFileName(productSerial)
        val sanitizedStep = sanitizeFileName(processStepName)
        return "${sanitizedSerial}_${sanitizedStep}_${timestamp}.jpg"
    }
    
    /**
     * 创建按日期和产品组织的目录结构
     * 结构: /ProcessPhotos/{年}/{月}/{产品序列号}/
     */
    fun createPhotoDirectory(productSerial: String): File {
        val currentDate = Date()
        val dateDir = dirDateFormatter.format(currentDate)
        val sanitizedSerial = sanitizeFileName(productSerial)
        
        val photoDir = File(getPhotosRootDir(), "$dateDir/$sanitizedSerial")
        
        if (!photoDir.exists()) {
            val created = photoDir.mkdirs()
            AppLogger.log(TAG, "创建照片目录: ${photoDir.absolutePath}, 成功: $created")
        }
        
        return photoDir
    }
    
    /**
     * 获取临时存储目录
     */
    fun getTempDirectory(): File {
        val tempDir = File(getPhotosRootDir(), TEMP_DIR)
        if (!tempDir.exists()) {
            tempDir.mkdirs()
        }
        return tempDir
    }
    
    /**
     * 保存照片到临时目录
     */
    fun savePhotoToTemp(inputStream: InputStream, fileName: String): File? {
        return try {
            val tempDir = getTempDirectory()
            val tempFile = File(tempDir, fileName)
            
            FileOutputStream(tempFile).use { output ->
                inputStream.copyTo(output)
            }
            
            AppLogger.log(TAG, "照片保存到临时目录: ${tempFile.absolutePath}")
            tempFile
        } catch (e: Exception) {
            AppLogger.log(TAG, "保存照片到临时目录失败: ${e.message}")
            null
        }
    }
    
    /**
     * 将照片从临时目录移动到正式目录
     */
    fun movePhotoFromTemp(tempFile: File, productSerial: String, processStepName: String): File? {
        return try {
            val photoDir = createPhotoDirectory(productSerial)
            val fileName = generatePhotoFileName(productSerial, processStepName)
            val finalFile = File(photoDir, fileName)
            
            val moved = tempFile.renameTo(finalFile)
            if (moved) {
                AppLogger.log(TAG, "照片移动到正式目录: ${finalFile.absolutePath}")
                finalFile
            } else {
                // 如果重命名失败，尝试复制
                tempFile.copyTo(finalFile, overwrite = true)
                tempFile.delete()
                AppLogger.log(TAG, "照片复制到正式目录: ${finalFile.absolutePath}")
                finalFile
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "移动照片失败: ${e.message}")
            null
        }
    }
    
    /**
     * 直接保存照片到正式目录
     */
    fun savePhotoToFinal(inputStream: InputStream, productSerial: String, processStepName: String): File? {
        return try {
            val photoDir = createPhotoDirectory(productSerial)
            val fileName = generatePhotoFileName(productSerial, processStepName)
            val photoFile = File(photoDir, fileName)
            
            FileOutputStream(photoFile).use { output ->
                inputStream.copyTo(output)
            }
            
            AppLogger.log(TAG, "照片直接保存: ${photoFile.absolutePath}")
            photoFile
        } catch (e: Exception) {
            AppLogger.log(TAG, "直接保存照片失败: ${e.message}")
            null
        }
    }
    
    /**
     * 获取产品的所有照片文件
     */
    fun getProductPhotos(productSerial: String): List<File> {
        val photos = mutableListOf<File>()
        val rootDir = getPhotosRootDir()
        
        // 遍历所有年月目录
        rootDir.listFiles()?.forEach { yearDir ->
            if (yearDir.isDirectory && yearDir.name.matches(Regex("\\d{4}"))) {
                yearDir.listFiles()?.forEach { monthDir ->
                    if (monthDir.isDirectory && monthDir.name.matches(Regex("\\d{2}"))) {
                        val productDir = File(monthDir, sanitizeFileName(productSerial))
                        if (productDir.exists() && productDir.isDirectory) {
                            productDir.listFiles { file ->
                                file.isFile && file.name.endsWith(".jpg", ignoreCase = true)
                            }?.let { files ->
                                photos.addAll(files)
                            }
                        }
                    }
                }
            }
        }
        
        return photos.sortedBy { it.lastModified() }
    }
    
    /**
     * 清理临时目录中的过期文件
     */
    fun cleanupTempFiles(maxAgeHours: Int = 24) {
        val tempDir = getTempDirectory()
        val cutoffTime = System.currentTimeMillis() - (maxAgeHours * 60 * 60 * 1000)
        
        tempDir.listFiles()?.forEach { file ->
            if (file.lastModified() < cutoffTime) {
                val deleted = file.delete()
                AppLogger.log(TAG, "清理临时文件: ${file.name}, 成功: $deleted")
            }
        }
    }
    
    /**
     * 获取照片存储根目录
     */
    private fun getPhotosRootDir(): File {
        // 优先使用外部存储，如果不可用则使用内部存储
        val externalDir = context.getExternalFilesDir(Environment.DIRECTORY_PICTURES)
        val rootDir = if (externalDir != null && Environment.getExternalStorageState() == Environment.MEDIA_MOUNTED) {
            File(externalDir, PHOTOS_DIR)
        } else {
            File(context.filesDir, PHOTOS_DIR)
        }
        
        if (!rootDir.exists()) {
            rootDir.mkdirs()
        }
        
        return rootDir
    }
    
    /**
     * 清理文件名中的非法字符
     */
    private fun sanitizeFileName(fileName: String): String {
        return fileName.replace(Regex("[^a-zA-Z0-9\\u4e00-\\u9fa5_-]"), "_")
    }
    
    /**
     * 获取照片文件信息
     */
    fun getPhotoInfo(photoFile: File): PhotoInfo? {
        return if (photoFile.exists() && photoFile.isFile) {
            PhotoInfo(
                file = photoFile,
                fileName = photoFile.name,
                filePath = photoFile.absolutePath,
                fileSize = photoFile.length(),
                lastModified = photoFile.lastModified()
            )
        } else {
            null
        }
    }
}

/**
 * 照片文件信息数据类
 */
data class PhotoInfo(
    val file: File,
    val fileName: String,
    val filePath: String,
    val fileSize: Long,
    val lastModified: Long
)