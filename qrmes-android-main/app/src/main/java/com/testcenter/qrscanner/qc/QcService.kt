package com.testcenter.qrscanner.qc

import android.content.Context
import android.util.Base64
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/**
 * QC 质检服务层
 * 封装与后端 QC API 的交互，供 Activity 调用
 */
class QcService(context: Context) {

    private val TAG = "QcService"
    private val appContext = context.applicationContext
    private val apiService by lazy { ApiClient.getApiService(appContext) }

    // 缓存 QC 策略，使用单一对象避免竞态条件
    private val policyMutex = Mutex()
    private data class CachedPolicyEntry(val policy: QcPolicy, val projectName: String)
    @Volatile private var cachedEntry: CachedPolicyEntry? = null

    /**
     * 获取项目的 QC 策略配置
     * 带缓存，同一项目只请求一次，Mutex 保护并发安全
     */
    suspend fun getQcPolicy(projectName: String): QcPolicy {
        // 快速路径：原子读取单一对象，不会出现不一致
        val entry = cachedEntry
        if (entry != null && entry.projectName == projectName) {
            return entry.policy
        }
        // 慢路径：加锁后再次检查并请求
        return policyMutex.withLock {
            val entryAgain = cachedEntry
            if (entryAgain != null && entryAgain.projectName == projectName) {
                return@withLock entryAgain.policy
            }
            withContext(Dispatchers.IO) {
                try {
                    val response = apiService.getQcPolicy(projectName)
                    if (response.isSuccessful) {
                        val body = response.body()
                        if (body?.success == true && body.data != null) {
                            cachedEntry = CachedPolicyEntry(body.data, projectName)
                            AppLogger.log(TAG, "QC 策略加载成功: enabled=${body.data.qcEnabled}, mode=${body.data.enforcementMode}")
                            return@withContext body.data
                        }
                    }
                    AppLogger.log(TAG, "QC 策略加载失败，使用默认配置（QC 关闭）")
                    QcPolicy.DEFAULT
                } catch (e: Exception) {
                    AppLogger.log(TAG, "QC 策略请求异常: ${e.message}", e)
                    QcPolicy.DEFAULT
                }
            }
        }
    }

    /**
     * 检查前面工序的照片和 QC 状态
     * @return QcPreviousCheckResponse，失败时返回 null
     */
    suspend fun checkPreviousSteps(
        productSerial: String,
        processIndex: Int,
        projectName: String,
        productType: String
    ): QcPreviousCheckResponse? {
        return withContext(Dispatchers.IO) {
            try {
                AppLogger.log(TAG, "检查前面工序: serial=$productSerial, index=$processIndex")
                val response = apiService.qcCheckPrevious(
                    serial = productSerial,
                    processIndex = processIndex,
                    projectName = projectName,
                    productType = productType
                )
                if (response.isSuccessful) {
                    val body = response.body()
                    if (body?.success == true) {
                        AppLogger.log(TAG, "前面工序检查完成: allPassed=${body.allPassed}, missing=${body.missingPhotos}")
                        return@withContext body
                    }
                    AppLogger.log(TAG, "前面工序检查返回失败: ${body?.error}")
                }
                AppLogger.log(TAG, "前面工序检查请求失败: ${response.code()}")
                null
            } catch (e: Exception) {
                AppLogger.log(TAG, "前面工序检查异常: ${e.message}", e)
                null
            }
        }
    }

    /**
     * 提交照片进行 QC 分析
     * @param photoBytesList 照片字节数组列表
     * @return QcAnalyzeResponse，失败时返回 ng 状态
     */
    suspend fun analyzePhotos(
        photoBytesList: List<ByteArray>,
        productSerial: String,
        processName: String,
        processIndex: Int,
        projectName: String,
        productType: String
    ): QcAnalyzeResponse {
        return withContext(Dispatchers.IO) {
            try {
                // Base64 编码是 CPU 密集型操作，使用 Default 调度器
                val base64Photos = withContext(Dispatchers.Default) {
                    photoBytesList.map { bytes ->
                        Base64.encodeToString(bytes, Base64.NO_WRAP)
                    }
                }

                AppLogger.log(TAG, "提交 QC 分析: process=$processName, photos=${base64Photos.size}")

                val request = QcAnalyzeRequest(
                    productSerial = productSerial,
                    processName = processName,
                    processIndex = processIndex,
                    projectName = projectName,
                    productType = productType,
                    photoBase64 = base64Photos
                )

                val response = apiService.qcAnalyze(request)
                if (response.isSuccessful) {
                    val body = response.body()
                    if (body != null) {
                        AppLogger.log(TAG, "QC 分析完成: status=${body.status}, confidence=${body.confidence}")
                        return@withContext body
                    }
                }

                AppLogger.log(TAG, "QC 分析请求失败: ${response.code()}")
                QcAnalyzeResponse(
                    success = false,
                    status = "ng",
                    summary = "QC 服务请求失败 (${response.code()})",
                    error = "HTTP ${response.code()}"
                )
            } catch (e: Exception) {
                AppLogger.log(TAG, "QC 分析异常: ${e.message}", e)
                QcAnalyzeResponse(
                    success = false,
                    status = "ng",
                    summary = "QC 服务连接失败: ${e.message}",
                    error = e.message
                )
            }
        }
    }

    /** 清除缓存的策略（切换项目时调用） */
    fun clearCache() {
        cachedEntry = null
    }

    data class QcManualConfirmResult(
        val success: Boolean,
        val message: String,
    )

    suspend fun submitManualConfirmation(
        productSerial: String,
        projectName: String,
        processName: String,
        humanStatus: String,
        humanSummary: String? = null,
    ): QcManualConfirmResult {
        return withContext(Dispatchers.IO) {
            try {
                val response = apiService.qcConfirm(
                    QcManualConfirmRequest(
                        productSerial = productSerial,
                        projectName = projectName,
                        processName = processName,
                        humanStatus = humanStatus,
                        humanSummary = humanSummary,
                    )
                )
                if (response.isSuccessful) {
                    val body = response.body()
                    if (body?.success == true) {
                        return@withContext QcManualConfirmResult(
                            success = true,
                            message = body.message ?: "人工确认已保存"
                        )
                    }
                    return@withContext QcManualConfirmResult(
                        success = false,
                        message = body?.error ?: body?.message ?: "人工确认失败"
                    )
                }
                QcManualConfirmResult(false, "人工确认失败: HTTP ${response.code()}")
            } catch (e: Exception) {
                AppLogger.log(TAG, "人工确认提交异常: ${e.message}", e)
                QcManualConfirmResult(false, "人工确认失败: ${e.message}")
            }
        }
    }
}
