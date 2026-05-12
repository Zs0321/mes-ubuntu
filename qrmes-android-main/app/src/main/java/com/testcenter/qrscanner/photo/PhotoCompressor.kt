package com.testcenter.qrscanner.photo

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import androidx.exifinterface.media.ExifInterface
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.io.IOException

/**
 * 照片压缩工具
 * 优化照片大小和质量，提升上传性能
 */
class PhotoCompressor(private val context: Context) {
    
    companion object {
        private const val TAG = "PhotoCompressor"
        
        // 默认压缩配置
        private const val DEFAULT_MAX_WIDTH = 1920
        private const val DEFAULT_MAX_HEIGHT = 1080
        private const val DEFAULT_QUALITY = 85
        private const val MAX_FILE_SIZE_MB = 2
    }
    
    /**
     * 压缩配置
     */
    data class CompressionConfig(
        val maxWidth: Int = DEFAULT_MAX_WIDTH,
        val maxHeight: Int = DEFAULT_MAX_HEIGHT,
        val quality: Int = DEFAULT_QUALITY,
        val maxFileSizeMB: Int = MAX_FILE_SIZE_MB
    )
    
    /**
     * 压缩结果
     */
    data class CompressionResult(
        val success: Boolean,
        val compressedFile: File? = null,
        val originalSize: Long = 0,
        val compressedSize: Long = 0,
        val compressionRatio: Float = 0f,
        val error: String? = null
    )
    
    /**
     * 压缩照片文件
     */
    suspend fun compressPhoto(
        sourceFile: File,
        config: CompressionConfig = CompressionConfig()
    ): CompressionResult = withContext(Dispatchers.IO) {
        try {
            if (!sourceFile.exists()) {
                return@withContext CompressionResult(
                    success = false,
                    error = "源文件不存在"
                )
            }
            
            val originalSize = sourceFile.length()
            AppLogger.log(TAG, "开始压缩照片: ${sourceFile.name}, 原始大小: ${originalSize / 1024}KB")
            
            // 检查是否需要压缩
            if (originalSize <= config.maxFileSizeMB * 1024 * 1024) {
                AppLogger.log(TAG, "文件大小符合要求，无需压缩")
                return@withContext CompressionResult(
                    success = true,
                    compressedFile = sourceFile,
                    originalSize = originalSize,
                    compressedSize = originalSize,
                    compressionRatio = 1.0f
                )
            }
            
            // 读取并解码图片
            val options = BitmapFactory.Options().apply {
                inJustDecodeBounds = true
            }
            BitmapFactory.decodeFile(sourceFile.absolutePath, options)
            
            // 计算采样率
            val sampleSize = calculateSampleSize(
                options.outWidth,
                options.outHeight,
                config.maxWidth,
                config.maxHeight
            )
            
            // 解码图片
            options.inJustDecodeBounds = false
            options.inSampleSize = sampleSize
            options.inPreferredConfig = Bitmap.Config.RGB_565
            
            var bitmap = BitmapFactory.decodeFile(sourceFile.absolutePath, options)
                ?: return@withContext CompressionResult(
                    success = false,
                    error = "无法解码图片"
                )
            
            // 处理图片旋转
            bitmap = rotateImageIfRequired(bitmap, sourceFile)
            
            // 如果图片仍然过大，进一步缩放
            if (bitmap.width > config.maxWidth || bitmap.height > config.maxHeight) {
                bitmap = scaleBitmap(bitmap, config.maxWidth, config.maxHeight)
            }
            
            // 创建压缩后的文件
            val compressedFile = File(
                sourceFile.parent,
                "compressed_${sourceFile.name}"
            )
            
            // 保存压缩后的图片
            var quality = config.quality
            var compressedSize: Long
            
            do {
                FileOutputStream(compressedFile).use { out ->
                    bitmap.compress(Bitmap.CompressFormat.JPEG, quality, out)
                }
                
                compressedSize = compressedFile.length()
                
                // 如果文件仍然过大，降低质量
                if (compressedSize > config.maxFileSizeMB * 1024 * 1024 && quality > 50) {
                    quality -= 10
                    AppLogger.log(TAG, "文件仍然过大，降低质量到 $quality")
                } else {
                    break
                }
            } while (quality >= 50)
            
            bitmap.recycle()
            
            val compressionRatio = compressedSize.toFloat() / originalSize.toFloat()
            
            AppLogger.log(TAG, "压缩完成: 原始 ${originalSize / 1024}KB -> 压缩后 ${compressedSize / 1024}KB, 压缩率: ${(compressionRatio * 100).toInt()}%")
            
            CompressionResult(
                success = true,
                compressedFile = compressedFile,
                originalSize = originalSize,
                compressedSize = compressedSize,
                compressionRatio = compressionRatio
            )
            
        } catch (e: Exception) {
            AppLogger.log(TAG, "压缩照片失败: ${e.message}")
            CompressionResult(
                success = false,
                error = e.message
            )
        }
    }
    
    /**
     * 计算采样率
     */
    private fun calculateSampleSize(
        width: Int,
        height: Int,
        maxWidth: Int,
        maxHeight: Int
    ): Int {
        var sampleSize = 1
        
        if (width > maxWidth || height > maxHeight) {
            val widthRatio = width / maxWidth
            val heightRatio = height / maxHeight
            sampleSize = if (widthRatio > heightRatio) widthRatio else heightRatio
        }
        
        return sampleSize
    }
    
    /**
     * 缩放Bitmap
     */
    private fun scaleBitmap(bitmap: Bitmap, maxWidth: Int, maxHeight: Int): Bitmap {
        val width = bitmap.width
        val height = bitmap.height
        
        val scale = Math.min(
            maxWidth.toFloat() / width,
            maxHeight.toFloat() / height
        )
        
        if (scale >= 1.0f) {
            return bitmap
        }
        
        val newWidth = (width * scale).toInt()
        val newHeight = (height * scale).toInt()
        
        val scaledBitmap = Bitmap.createScaledBitmap(bitmap, newWidth, newHeight, true)
        
        if (scaledBitmap != bitmap) {
            bitmap.recycle()
        }
        
        return scaledBitmap
    }
    
    /**
     * 根据EXIF信息旋转图片
     */
    private fun rotateImageIfRequired(bitmap: Bitmap, file: File): Bitmap {
        try {
            val exif = ExifInterface(file.absolutePath)
            val orientation = exif.getAttributeInt(
                ExifInterface.TAG_ORIENTATION,
                ExifInterface.ORIENTATION_NORMAL
            )
            
            val rotation = when (orientation) {
                ExifInterface.ORIENTATION_ROTATE_90 -> 90f
                ExifInterface.ORIENTATION_ROTATE_180 -> 180f
                ExifInterface.ORIENTATION_ROTATE_270 -> 270f
                else -> return bitmap
            }
            
            val matrix = Matrix()
            matrix.postRotate(rotation)
            
            val rotatedBitmap = Bitmap.createBitmap(
                bitmap,
                0,
                0,
                bitmap.width,
                bitmap.height,
                matrix,
                true
            )
            
            if (rotatedBitmap != bitmap) {
                bitmap.recycle()
            }
            
            return rotatedBitmap
            
        } catch (e: IOException) {
            AppLogger.log(TAG, "读取EXIF信息失败: ${e.message}")
            return bitmap
        }
    }
    
    /**
     * 批量压缩照片
     */
    suspend fun compressPhotos(
        sourceFiles: List<File>,
        config: CompressionConfig = CompressionConfig(),
        progressCallback: ((Int, Int) -> Unit)? = null
    ): List<CompressionResult> = withContext(Dispatchers.IO) {
        val results = mutableListOf<CompressionResult>()
        
        sourceFiles.forEachIndexed { index, file ->
            val result = compressPhoto(file, config)
            results.add(result)
            progressCallback?.invoke(index + 1, sourceFiles.size)
        }
        
        results
    }
}
