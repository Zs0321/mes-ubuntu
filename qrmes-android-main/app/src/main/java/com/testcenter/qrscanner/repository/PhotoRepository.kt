package com.testcenter.qrscanner.repository

import android.content.Context
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.api.PhotoInfo
import com.testcenter.qrscanner.api.PhotoMetadataRequest
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 照片数据仓库
 * 替代 SMBFileManager.uploadPhoto() / listPhotos() / downloadPhoto()
 * 统一使用 REST API 进行照片管理
 */
class PhotoRepository(private val context: Context) {
    
    companion object {
        private const val TAG = "PhotoRepository"
        private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
    }
    
    private val apiService by lazy { ApiClient.getApiService(context) }
    
    /**
     * 上传照片
     */
    suspend fun uploadPhoto(
        photoFile: File,
        productSerial: String,
        projectName: String,
        productType: String,
        processName: String? = null,
        operator: String? = null,
        projectCode: String? = null,
        modelNumber: String? = null,
        skipQcEnqueue: Boolean = false
    ): Result<String> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "上传照片: ${photoFile.name}, 产品: $productSerial")

            // 创建 multipart 请求
            val requestFile = photoFile.asRequestBody("image/jpeg".toMediaTypeOrNull())
            val photoPart = MultipartBody.Part.createFormData("photo", photoFile.name, requestFile)

            val serialBody = productSerial.toRequestBody("text/plain".toMediaTypeOrNull())
            val projectBody = projectName.toRequestBody("text/plain".toMediaTypeOrNull())
            val typeBody = productType.toRequestBody("text/plain".toMediaTypeOrNull())
            val processBody = processName?.toRequestBody("text/plain".toMediaTypeOrNull())
            val codeBody = projectCode?.toRequestBody("text/plain".toMediaTypeOrNull())
            val modelBody = modelNumber?.toRequestBody("text/plain".toMediaTypeOrNull())
            val skipQcBody = if (skipQcEnqueue) {
                "1".toRequestBody("text/plain".toMediaTypeOrNull())
            } else {
                null
            }

            val response = apiService.uploadPhoto(
                photo = photoPart,
                productSerial = serialBody,
                projectName = projectBody,
                productType = typeBody,
                processStep = processBody,
                projectCode = codeBody,
                modelNumber = modelBody,
                skipQcEnqueue = skipQcBody
            )
            
            if (response.isSuccessful) {
                val body = response.body()
                if (body?.success == true) {
                    val filename = body.filename ?: photoFile.name
                    AppLogger.log(TAG, "上传成功: $filename")

                    // 保存元数据
                    savePhotoMetadata(
                        productSerial = productSerial,
                        processName = processName,
                        fileName = filename,
                        filePath = body.filePath,
                        fileSize = photoFile.length(),
                        operator = operator
                    )
                    
                    Result.success(filename)
                } else {
                    Result.failure(Exception("上传失败: ${body?.error ?: "未知错误"}"))
                }
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "上传照片失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 上传照片（从字节数组）
     */
    suspend fun uploadPhoto(
        photoBytes: ByteArray,
        fileName: String,
        productSerial: String,
        projectName: String,
        productType: String,
        processName: String? = null,
        operator: String? = null,
        projectCode: String? = null,
        modelNumber: String? = null,
        skipQcEnqueue: Boolean = false
    ): Result<String> = withContext(Dispatchers.IO) {
        try {
            // 创建临时文件
            val tempFile = File(context.cacheDir, fileName)
            tempFile.writeBytes(photoBytes)

            try {
                val result = uploadPhoto(
                    photoFile = tempFile,
                    productSerial = productSerial,
                    projectName = projectName,
                    productType = productType,
                    processName = processName,
                    operator = operator,
                    projectCode = projectCode,
                    modelNumber = modelNumber,
                    skipQcEnqueue = skipQcEnqueue
                )
                result
            } finally {
                // 清理临时文件
                tempFile.delete()
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "上传照片失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 保存照片元数据
     */
    private suspend fun savePhotoMetadata(
        productSerial: String,
        processName: String?,
        fileName: String,
        filePath: String?,
        fileSize: Long?,
        operator: String?
    ): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            val request = PhotoMetadataRequest(
                productSerial = productSerial,
                processStep = processName,
                filePath = filePath,
                fileName = fileName,
                fileSize = fileSize,
                capturedBy = operator
            )
            
            val response = apiService.savePhotoMetadata(request)
            
            if (response.isSuccessful && response.body()?.success == true) {
                Result.success(true)
            } else {
                Result.failure(Exception("保存元数据失败"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "保存照片元数据失败: ${e.message}", e)
            Result.failure(e)
        }
    }

    /**
     * 对已落盘照片补写元数据。
     * 用于 SMB 回退上传成功后，尽量补齐后端照片索引，避免 NAS 与 API 列表不一致。
     */
    suspend fun recordPhotoMetadata(
        productSerial: String,
        processName: String?,
        fileName: String,
        filePath: String? = null,
        fileSize: Long? = null,
        operator: String? = null
    ): Result<Boolean> = savePhotoMetadata(
        productSerial = productSerial,
        processName = processName,
        fileName = fileName,
        filePath = filePath,
        fileSize = fileSize,
        operator = operator
    )
    
    /**
     * 获取照片列表
     */
    suspend fun listPhotos(
        projectName: String? = null,
        productType: String? = null,
        productSerial: String? = null
    ): Result<List<PhotoInfo>> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "获取照片列表: project=$projectName, type=$productType, serial=$productSerial")
            val response = apiService.listPhotos(projectName, productType, productSerial)
            
            if (response.isSuccessful) {
                val body = response.body()
                if (body?.success == true) {
                    val photos = body.photos ?: emptyList()
                    AppLogger.log(TAG, "获取成功: ${photos.size} 张照片")
                    Result.success(photos)
                } else {
                    Result.success(emptyList())
                }
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "获取照片列表失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 获取产品的照片数量
     */
    suspend fun getPhotoCount(productSerial: String): Result<Int> = withContext(Dispatchers.IO) {
        try {
            val result = listPhotos(productSerial = productSerial)
            result.fold(
                onSuccess = { photos -> Result.success(photos.size) },
                onFailure = { e -> Result.failure(e) }
            )
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
