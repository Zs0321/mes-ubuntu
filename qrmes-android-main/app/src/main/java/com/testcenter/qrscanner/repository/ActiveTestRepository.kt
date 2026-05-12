package com.testcenter.qrscanner.repository

import android.content.Context
import com.testcenter.qrscanner.api.ActiveTest
import com.testcenter.qrscanner.api.ActiveTestRequest
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * 活动测试数据仓库
 * 替代 SMBFileManager.fetchActiveTests() / saveActiveTests()
 */
class ActiveTestRepository(private val context: Context) {
    
    companion object {
        private const val TAG = "ActiveTestRepository"
    }
    
    private val apiService by lazy { ApiClient.getApiService(context) }
    
    /**
     * 获取所有活动测试
     */
    suspend fun fetchActiveTests(): Result<List<ActiveTest>> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "获取活动测试列表...")
            val response = apiService.getActiveTests()
            
            if (response.isSuccessful) {
                val body = response.body()
                if (body?.success == true) {
                    AppLogger.log(TAG, "获取成功: ${body.count} 条")
                    Result.success(body.tests)
                } else {
                    Result.failure(Exception("API 返回失败"))
                }
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "获取活动测试列表失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 获取指定序列号的活动测试
     */
    suspend fun getActiveTest(serial: String): Result<ActiveTest?> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "获取活动测试: $serial")
            val response = apiService.getActiveTest(serial)
            
            if (response.isSuccessful) {
                val body = response.body()
                if (body?.success == true) {
                    Result.success(body.test)
                } else {
                    Result.failure(Exception("API 返回失败"))
                }
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "获取活动测试失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 开始测试（添加或更新活动测试）
     */
    suspend fun startTest(serial: String, tester: String): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "开始测试: $serial, 测试员: $tester")
            val request = ActiveTestRequest(serial = serial, tester = tester)
            val response = apiService.upsertActiveTest(request)
            
            if (response.isSuccessful && response.body()?.success == true) {
                AppLogger.log(TAG, "开始测试成功")
                Result.success(true)
            } else {
                Result.failure(Exception("开始测试失败: ${response.body()?.error ?: response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "开始测试失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 结束测试（删除活动测试）
     */
    suspend fun endTest(serial: String): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "结束测试: $serial")
            val response = apiService.removeActiveTest(serial)
            
            if (response.isSuccessful && response.body()?.success == true) {
                AppLogger.log(TAG, "结束测试成功")
                Result.success(true)
            } else {
                Result.failure(Exception("结束测试失败: ${response.body()?.error ?: response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "结束测试失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 检查产品是否正在被测试
     */
    suspend fun isProductBeingTested(serial: String): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            val response = apiService.getActiveTest(serial)
            if (response.isSuccessful) {
                val body = response.body()
                Result.success(body?.exists == true)
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "检查活动测试失败: ${e.message}", e)
            Result.failure(e)
        }
    }
}
