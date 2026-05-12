package com.testcenter.qrscanner.repository

import android.content.Context
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.api.ProjectConfig as ApiProjectConfig
import com.testcenter.qrscanner.api.ProjectConfigRequest
import com.testcenter.qrscanner.api.SaveProjectsRequest
import com.testcenter.qrscanner.data.MaterialInfo
import com.testcenter.qrscanner.data.ProcessStep
import com.testcenter.qrscanner.data.ProductTypeConfig
import com.testcenter.qrscanner.data.ProjectConfig
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * 项目数据仓库
 * 替代 SMBFileManager.fetchProjectList() / saveProjectList() / fetchProjectConfig() / saveProjectConfig()
 */
class ProjectRepository(private val context: Context) {
    
    companion object {
        private const val TAG = "ProjectRepository"
    }
    
    private val apiService by lazy { ApiClient.getApiService(context) }
    
    // ==================== 项目列表 ====================
    
    /**
     * 获取项目列表
     */
    suspend fun fetchProjectList(): Result<List<String>> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "获取项目列表...")
            val response = apiService.getProjects()
            
            if (response.isSuccessful) {
                val body = response.body()
                if (body?.success == true) {
                    val projects = body.getProjectList()
                    AppLogger.log(TAG, "获取成功: ${projects.size} 个项目")
                    Result.success(projects)
                } else {
                    Result.failure(Exception("API 返回失败"))
                }
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "获取项目列表失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 保存项目列表
     */
    suspend fun saveProjectList(projects: List<String>): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "保存项目列表: ${projects.size} 个项目")
            val response = apiService.saveProjects(SaveProjectsRequest(projects))
            
            if (response.isSuccessful && response.body()?.success == true) {
                AppLogger.log(TAG, "保存成功")
                Result.success(true)
            } else {
                Result.failure(Exception("保存失败: ${response.body()?.error ?: response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "保存项目列表失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    // ==================== 项目配置 ====================
    
    /**
     * 获取项目配置 (返回 data.ProjectConfig 类型)
     */
    suspend fun fetchProjectConfig(projectName: String): Result<ProjectConfig?> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "获取项目配置: $projectName")
            val response = apiService.getProjectConfig(projectName)
            
            if (response.isSuccessful) {
                val body = response.body()
                if (body?.success == true && body.config != null) {
                    AppLogger.log(TAG, "获取配置成功: $projectName")
                    // 转换 API 类型到 data 类型
                    val config = convertToDataProjectConfig(body.config)
                    Result.success(config)
                } else {
                    AppLogger.log(TAG, "项目配置不存在: $projectName")
                    Result.success(null)
                }
            } else if (response.code() == 404) {
                // 配置不存在
                Result.success(null)
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "获取项目配置失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 将 API 返回的配置转换为 data.ProjectConfig 类型
     */
    private fun convertToDataProjectConfig(apiConfig: ApiProjectConfig): ProjectConfig {
        // 转换产品类型列表
        val productTypes = apiConfig.productTypes?.map { apiProductType ->
            ProductTypeConfig(
                typeName = apiProductType.name ?: "",
                modelNumber = apiProductType.modelNumber ?: "",
                serialRules = apiProductType.serialRules ?: emptyList(),
                forceVersionCheck = apiProductType.forceVersionCheck ?: false,
                materials = apiProductType.materials?.map { apiMaterial ->
                    MaterialInfo(
                        name = apiMaterial.name,
                        partNumber = apiMaterial.partNumber ?: "",
                        qrRuleType = apiMaterial.qrRuleType ?: MaterialInfo.QR_RULE_MOTOR,
                        expectedVersion = apiMaterial.expectedVersion ?: ""
                    )
                }?.toMutableList() ?: mutableListOf(),
                processSteps = apiProductType.processSteps?.map { apiProcess ->
                    ProcessStep(
                        id = apiProcess.id ?: "process_${System.currentTimeMillis()}",
                        name = apiProcess.name,
                        description = apiProcess.description ?: "",
                        order = apiProcess.order ?: 0,
                        productType = apiProcess.productType ?: "",
                        required = apiProcess.required ?: true,
                        photoRequired = apiProcess.requirePhoto ?: true,
                        estimatedDuration = apiProcess.estimatedDuration ?: 300,
                        attachmentType = apiProcess.attachmentType ?: "photo",
                        responsibleDepartments = apiProcess.responsibleDepartments ?: emptyList()
                    )
                }?.toMutableList()
            )
        }?.toMutableList() ?: mutableListOf()
        
        AppLogger.log(TAG, "转换配置: ${apiConfig.projectName}, 产品类型数: ${productTypes.size}")
        productTypes.forEach { pt ->
            AppLogger.log(TAG, "  - 产品类型: ${pt.typeName}, 物料数: ${pt.materials.size}, 工序数: ${pt.safeGetProcessSteps().size}")
        }
        
        return ProjectConfig(
            projectName = apiConfig.projectName ?: "",
            projectCode = apiConfig.projectCode ?: "",
            version = apiConfig.version ?: 1,
            productTypes = productTypes,
            lastModified = apiConfig.lastModified ?: System.currentTimeMillis()
        )
    }
    
    /**
     * 保存项目配置
     * 注意：当前版本暂时只保存基本信息，复杂的产品类型和工序数据需要后续完善
     */
    suspend fun saveProjectConfig(config: ProjectConfig): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "保存项目配置: ${config.projectName}")
            
            // 简化版本：只保存基本信息
            val request = ProjectConfigRequest(
                projectName = config.projectName,
                projectCode = config.projectCode,
                productTypes = null, // TODO: 需要类型转换
                processes = null,    // TODO: 需要类型转换
                version = config.version
            )
            
            val response = apiService.saveProjectConfig(config.projectName, request)
            
            if (response.isSuccessful && response.body()?.success == true) {
                AppLogger.log(TAG, "保存配置成功")
                Result.success(true)
            } else {
                Result.failure(Exception("保存失败: ${response.body()?.error ?: response.message()}"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "保存项目配置失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 获取项目的工序列表
     */
    suspend fun fetchProcessList(projectName: String): Result<List<String>> = withContext(Dispatchers.IO) {
        try {
            val configResult = fetchProjectConfig(projectName)
            if (configResult.isSuccess) {
                val config = configResult.getOrNull()
                val processes = config?.processSteps?.map { it.name } ?: emptyList()
                Result.success(processes)
            } else {
                Result.failure(configResult.exceptionOrNull() ?: Exception("获取配置失败"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "获取工序列表失败: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 获取项目的产品类型列表
     */
    suspend fun fetchProductTypes(projectName: String): Result<List<String>> = withContext(Dispatchers.IO) {
        try {
            val configResult = fetchProjectConfig(projectName)
            if (configResult.isSuccess) {
                val config = configResult.getOrNull()
                val types = config?.productTypes?.map { it.typeName } ?: emptyList()
                Result.success(types)
            } else {
                Result.failure(configResult.exceptionOrNull() ?: Exception("获取配置失败"))
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "获取产品类型列表失败: ${e.message}", e)
            Result.failure(e)
        }
    }
}
