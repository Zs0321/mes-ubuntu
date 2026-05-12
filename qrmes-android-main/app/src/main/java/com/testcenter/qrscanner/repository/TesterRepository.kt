package com.testcenter.qrscanner.repository

import android.content.Context
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.api.SaveTestersRequest
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * 测试人员数据仓库
 * 替代 SMBFileManager.fetchTesterList()
 */
class TesterRepository(private val context: Context) {
    
    companion object {
        private const val TAG = "TesterRepository"
    }
    
    private val apiService by lazy { ApiClient.getApiService(context) }
    
    /**
     * 获取测试人员列表
     */
    suspend fun fetchTesterList(): Result<List<String>> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "获取测试人员列表...")
            val response = apiService.getTesters()
            
            if (response.isSuccessful) {
                val body = response.body()
                if (body?.success == true) {
                    AppLogger.log(TAG, "获取成功: ${body.count} 人")
                    Result.success(body.testers)
                } else {
                    Result.failure(Exception("API 返回失败"))
                }
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "获取测试人员列表失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 保存测试人员列表
     */
    suspend fun saveTesterList(testers: List<String>): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "保存测试人员列表: ${testers.size} 人")
            val response = apiService.saveTesters(SaveTestersRequest(testers))
            
            if (response.isSuccessful && response.body()?.success == true) {
                AppLogger.log(TAG, "保存成功")
                Result.success(true)
            } else {
                Result.failure(Exception("保存失败: ${response.body()?.error ?: response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "保存测试人员列表失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 添加测试人员
     */
    suspend fun addTester(name: String): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "添加测试人员: $name")
            val response = apiService.addTester(name)
            
            if (response.isSuccessful && response.body()?.success == true) {
                AppLogger.log(TAG, "添加成功")
                Result.success(true)
            } else {
                Result.failure(Exception("添加失败: ${response.body()?.error ?: response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "添加测试人员失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 删除测试人员
     */
    suspend fun removeTester(name: String): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "删除测试人员: $name")
            val response = apiService.removeTester(name)
            
            if (response.isSuccessful && response.body()?.success == true) {
                AppLogger.log(TAG, "删除成功")
                Result.success(true)
            } else {
                Result.failure(Exception("删除失败: ${response.body()?.error ?: response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "删除测试人员失败: ${e.message}", e)
            Result.failure(e)
        }
    }
}
