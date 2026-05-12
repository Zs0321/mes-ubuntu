package com.testcenter.qrscanner.repository

import android.content.Context
import android.os.Environment
import com.testcenter.qrscanner.api.ApkInfo
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream

/**
 * APK 更新数据仓库
 * 替代 SMBFileManager.listApkFiles() / downloadApk()
 */
class ApkUpdateRepository(private val context: Context) {
    
    companion object {
        private const val TAG = "ApkUpdateRepository"
    }
    
    private val apiService by lazy { ApiClient.getApiService(context) }
    
    /**
     * 获取 APK 列表
     */
    suspend fun listApkFiles(): Result<List<ApkInfo>> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "获取 APK 列表...")
            val response = apiService.listApks()
            
            if (response.isSuccessful) {
                val body = response.body()
                if (body?.success == true) {
                    AppLogger.log(TAG, "获取成功: ${body.count} 个 APK")
                    Result.success(body.apks)
                } else {
                    Result.failure(Exception("API 返回失败"))
                }
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "获取 APK 列表失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 获取最新版本 APK 信息
     */
    suspend fun getLatestApk(appName: String? = null): Result<ApkInfo?> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "获取最新 APK 信息...")
            val response = apiService.getLatestApk(appName)
            
            if (response.isSuccessful) {
                val body = response.body()
                if (body?.success == true) {
                    Result.success(body.apk)
                } else {
                    Result.failure(Exception("API 返回失败"))
                }
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "获取最新 APK 失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 检查更新
     */
    suspend fun checkUpdate(
        currentVersionCode: Int,
        currentVersionName: String,
        appName: String? = null
    ): Result<UpdateCheckResult> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "检查更新: 当前版本 $currentVersionName ($currentVersionCode)")
            val response = apiService.checkUpdate(currentVersionCode, currentVersionName, appName)
            
            if (response.isSuccessful) {
                val body = response.body()
                if (body?.success == true) {
                    val result = UpdateCheckResult(
                        hasUpdate = body.hasUpdate,
                        latestVersion = body.latestVersion,
                        message = body.message ?: ""
                    )
                    AppLogger.log(TAG, "检查结果: ${result.message}")
                    Result.success(result)
                } else {
                    Result.failure(Exception("API 返回失败"))
                }
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "检查更新失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 下载 APK 文件
     */
    suspend fun downloadApk(filename: String): Result<File> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "下载 APK: $filename")
            val response = apiService.downloadApk(filename)
            
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    // 保存到下载目录
                    val downloadsDir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
                        ?: throw Exception("无法获取下载目录")
                    
                    val file = File(downloadsDir, filename)
                    
                    FileOutputStream(file).use { output ->
                        body.byteStream().use { input ->
                            input.copyTo(output)
                        }
                    }
                    
                    AppLogger.log(TAG, "下载成功: ${file.absolutePath}")
                    Result.success(file)
                } else {
                    Result.failure(Exception("响应体为空"))
                }
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "下载 APK 失败: ${e.message}", e)
            Result.failure(e)
        }
    }
}

/**
 * 更新检查结果
 */
data class UpdateCheckResult(
    val hasUpdate: Boolean,
    val latestVersion: ApkInfo?,
    val message: String
)
