package com.testcenter.qrscanner.repository

import android.content.Context
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.api.ComponentData
import com.testcenter.qrscanner.api.ProductRecordData
import com.testcenter.qrscanner.api.SaveProductRecordRequest
import com.testcenter.qrscanner.api.SerialBindingRepairRequest
import com.testcenter.qrscanner.api.SerialLearningConfirmRequest
import com.testcenter.qrscanner.api.SerialRecommendationCandidate
import com.testcenter.qrscanner.api.SerialRecommendationData
import com.testcenter.qrscanner.network.FileManager
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.SerialNormalizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 产品记录数据仓库
 * 替代 SMBFileManager.saveProductRecord() / queryProductRecord()
 * 使用 H2 API 进行数据存储
 */
class ProductRecordRepository(private val context: Context) {
    
    companion object {
        private const val TAG = "ProductRecordRepository"
        private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
    }
    
    private val apiService by lazy { ApiClient.getApiService(context) }

    data class SerialRecommendation(
        val productSerial: String,
        val recommendedProjectName: String,
        val recommendedProductType: String,
        val confidence: Double,
        val shouldConfirm: Boolean,
        val autoApply: Boolean,
        val reason: String?,
        val candidates: List<SerialRecommendationCandidate>
    )
    
    /**
     * 查询产品记录 (返回 FileManager.ProductRecord 兼容类型)
     */
    suspend fun queryProductRecord(productSerial: String): Result<FileManager.ProductRecord?> = withContext(Dispatchers.IO) {
        try {
            val normalizedSerial = SerialNormalizer.normalize(productSerial)
            if (normalizedSerial.isEmpty()) {
                return@withContext Result.success(null)
            }
            AppLogger.log(TAG, "查询产品记录: $normalizedSerial")
            val response = apiService.queryProductRecord(normalizedSerial)
            
            if (response.isSuccessful) {
                val body = response.body()
                if (body?.success == true && body.record != null) {
                    // 服务端返回 success=true 且有 record 数据
                    AppLogger.log(TAG, "找到记录: $normalizedSerial")
                    val record = convertToProductRecord(body.record)
                    Result.success(record)
                } else {
                    AppLogger.log(TAG, "记录不存在: $normalizedSerial")
                    Result.success(null)
                }
            } else if (response.code() == 404) {
                Result.success(null)
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "查询产品记录失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 将 API 返回的数据转换为 FileManager.ProductRecord 格式
     */
    private fun convertToProductRecord(data: ProductRecordData): FileManager.ProductRecord {
        val components = mutableMapOf<String, String>()
        
        // 优先从 materials 字段解析（H2 API 返回的格式）
        if (!data.materials.isNullOrBlank()) {
            try {
                val materialsJson = org.json.JSONObject(data.materials)
                val keys = materialsJson.keys()
                while (keys.hasNext()) {
                    val key = keys.next()
                    val value = materialsJson.optString(key, "")
                    if (value.isNotEmpty() && value != "null" && value != "nan") {
                        components[key] = value
                    }
                }
                AppLogger.log(TAG, "从 materials 解析了 ${components.size} 个组件")
            } catch (e: Exception) {
                AppLogger.log(TAG, "解析 materials 失败: ${e.message}")
            }
        }
        
        // 如果 materials 为空，尝试从 components 字段获取
        if (components.isEmpty()) {
            data.components?.forEach { comp ->
                components[comp.name] = comp.serial ?: ""
            }
        }
        
        return FileManager.ProductRecord(
            productSerial = data.productSerial,
            productType = data.productType ?: "",
            projectName = data.projectName ?: "",
            operator = data.operator ?: "",
            scanTime = data.scanTime ?: "",
            components = components
        )
    }
    
    /**
     * 检查产品记录是否存在
     */
    suspend fun recordExists(productSerial: String): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            val result = queryProductRecord(productSerial)
            result.fold(
                onSuccess = { record -> Result.success(record != null) },
                onFailure = { e -> Result.failure(e) }
            )
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    /**
     * 直接保存产品记录（推荐使用）
     * 替代旧的 CSV 格式保存方式
     * 
     * @param productSerial 产品序列号
     * @param productType 产品类型
     * @param projectName 项目名称
     * @param operator 操作员
     * @param materials 物料数据 (物料名称 -> 序列号)
     */
    suspend fun saveProductRecord(
        productSerial: String,
        productType: String,
        projectName: String,
        operator: String,
        materials: Map<String, String>,
        allowBindingUpdate: Boolean = false
    ): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            val normalizedSerial = SerialNormalizer.normalize(productSerial)
            if (normalizedSerial.isEmpty()) {
                return@withContext Result.failure(Exception("产品序列号为空"))
            }
            AppLogger.log(TAG, "保存产品记录: $normalizedSerial, 产品类型: $productType, 物料数量: ${materials.size}")
            
            // 转换为 ComponentData 列表
            val components = materials.map { (name, serial) ->
                ComponentData(name = name, serial = serial, scanTime = null)
            }
            
            saveProductRecordInternal(
                productSerial = normalizedSerial,
                productType = productType,
                projectName = projectName,
                operator = operator,
                components = components,
                allowBindingUpdate = allowBindingUpdate
            )
        } catch (e: Exception) {
            AppLogger.log(TAG, "保存产品记录失败: ${e.message}", e)
            Result.failure(e)
        }
    }

    suspend fun getSerialRecommendation(
        productSerial: String,
        currentProject: String?,
        currentProductType: String?
    ): Result<SerialRecommendation?> = withContext(Dispatchers.IO) {
        try {
            val normalizedSerial = SerialNormalizer.normalize(productSerial)
            if (normalizedSerial.isEmpty()) {
                return@withContext Result.success(null)
            }
            val response = apiService.getSerialRecommendation(
                serial = normalizedSerial,
                currentProject = currentProject,
                currentProductType = currentProductType
            )
            if (!response.isSuccessful) {
                return@withContext Result.failure(
                    Exception("HTTP ${response.code()}: ${response.message()}")
                )
            }

            val body = response.body()
            if (body?.success != true || body.recommendation == null) {
                return@withContext Result.success(null)
            }

            val recommendation = convertRecommendation(body.recommendation)
            Result.success(recommendation)
        } catch (e: Exception) {
            AppLogger.log(TAG, "获取序列号推荐失败: ${e.message}", e)
            Result.failure(e)
        }
    }

    suspend fun confirmSerialLearning(
        productSerial: String,
        projectName: String,
        productType: String,
        operator: String?,
        source: String,
        conflict: Boolean,
        candidates: List<SerialRecommendationCandidate> = emptyList()
    ): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            val normalizedSerial = SerialNormalizer.normalize(productSerial)
            if (normalizedSerial.isEmpty()) {
                return@withContext Result.failure(Exception("产品序列号为空"))
            }
            val request = SerialLearningConfirmRequest(
                productSerial = normalizedSerial,
                projectName = projectName,
                productType = productType,
                operator = operator,
                source = source,
                conflict = conflict,
                candidates = candidates
            )
            val response = apiService.confirmSerialLearning(request)
            if (response.isSuccessful && response.body()?.success == true) {
                Result.success(true)
            } else {
                Result.failure(
                    Exception(response.body()?.error ?: response.body()?.message ?: response.message())
                )
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "写回序列号学习失败: ${e.message}", e)
            Result.failure(e)
        }
    }

    suspend fun repairSerialBinding(
        productSerial: String,
        projectName: String,
        productType: String,
        operator: String?,
        source: String = "manual_repair"
    ): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            val normalizedSerial = SerialNormalizer.normalize(productSerial)
            if (normalizedSerial.isEmpty()) {
                return@withContext Result.failure(Exception("产品序列号为空"))
            }
            val request = SerialBindingRepairRequest(
                productSerial = normalizedSerial,
                projectName = projectName,
                productType = productType,
                operator = operator,
                source = source
            )
            val response = apiService.repairSerialBinding(request)
            if (response.isSuccessful && response.body()?.success == true) {
                Result.success(true)
            } else {
                Result.failure(
                    Exception(response.body()?.error ?: response.body()?.message ?: response.message())
                )
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "手动修复绑定失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 内部方法：保存产品记录到服务器
     */
    private suspend fun saveProductRecordInternal(
        productSerial: String,
        productType: String,
        projectName: String,
        operator: String,
        components: List<ComponentData>? = null,
        allowBindingUpdate: Boolean = false
    ): Result<Boolean> {
        try {
            val normalizedSerial = SerialNormalizer.normalize(productSerial)
            if (normalizedSerial.isEmpty()) {
                return Result.failure(Exception("产品序列号为空"))
            }
            AppLogger.log(TAG, "保存产品记录: $normalizedSerial, 组件数量: ${components?.size ?: 0}")
            
            // 将 components 转换为 materials 格式 (name -> serial)
            val materials = components?.associate { it.name to (it.serial ?: "") } ?: emptyMap()
            AppLogger.log(TAG, "Materials: $materials")
            
            // 使用毫秒时间戳（服务端期望的格式）
            val scanTimeMillis = System.currentTimeMillis()
            
            val request = SaveProductRecordRequest(
                productSerial = normalizedSerial,
                productType = productType,
                projectName = projectName,
                operator = operator,
                scanTime = scanTimeMillis.toString(),  // 服务端期望毫秒时间戳字符串
                components = components,
                allowBindingUpdate = allowBindingUpdate,
                materials = materials
            )
            
            val response = apiService.saveProductRecord(request)
            
            return if (response.isSuccessful && response.body()?.success == true) {
                AppLogger.log(TAG, "保存成功: $normalizedSerial")
                Result.success(true)
            } else {
                val errorMsg = response.body()?.error ?: response.body()?.message ?: response.message()
                AppLogger.log(TAG, "保存失败: $normalizedSerial, 错误: $errorMsg")
                Result.failure(Exception("保存失败: $errorMsg"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "保存产品记录失败: ${e.message}", e)
            return Result.failure(e)
        }
    }

    private fun convertRecommendation(data: SerialRecommendationData): SerialRecommendation? {
        val projectName = data.recommendedProjectName?.trim().orEmpty()
        val productType = data.recommendedProductType?.trim().orEmpty()
        if (projectName.isEmpty() || productType.isEmpty()) {
            return null
        }
        return SerialRecommendation(
            productSerial = data.productSerial,
            recommendedProjectName = projectName,
            recommendedProductType = productType,
            confidence = data.confidence ?: 0.0,
            shouldConfirm = data.shouldConfirm ?: false,
            autoApply = data.autoApply ?: false,
            reason = data.reason,
            candidates = data.candidates ?: emptyList()
        )
    }
}
