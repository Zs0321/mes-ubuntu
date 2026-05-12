package com.testcenter.qrscanner.sync

import android.content.Context
import com.testcenter.qrscanner.config.ConfigFileManager
import com.testcenter.qrscanner.network.FileManager
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.ProjectConfigManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

/**
 * 配置同步服务
 * 负责移动应用与服务器之间的配置同步
 */
class ConfigSyncService(
    private val context: Context,
    private val fileManager: FileManager
) {
    
    private val configFileManager = ConfigFileManager(context)
    private val projectConfigManager = ProjectConfigManager(context)
    
    /**
     * 同步结果
     */
    sealed class SyncResult {
        data class Success(val message: String) : SyncResult()
        data class Conflict(val localConfig: ConfigFileManager.ConfigFile, val serverConfig: ConfigFileManager.ConfigFile) : SyncResult()
        data class Error(val message: String) : SyncResult()
        object NoChanges : SyncResult()
    }
    
    /**
     * 同步策略
     */
    enum class SyncStrategy {
        SERVER_WINS,    // 服务器优先
        LOCAL_WINS,     // 本地优先
        MERGE,          // 合并
        ASK_USER        // 询问用户
    }
    
    /**
     * 配置变更记录
     */
    data class ConfigChange(
        val projectName: String,
        val changeType: ChangeType,
        val timestamp: String,
        val description: String,
        val version: Int
    )
    
    enum class ChangeType {
        CREATED, UPDATED, DELETED, IMPORTED, RESTORED
    }
    
    /**
     * 同步项目配置到服务器
     */
    suspend fun syncToServer(projectName: String): SyncResult = withContext(Dispatchers.IO) {
        try {
            AppLogger.log("ConfigSyncService", "Syncing config to server: $projectName")
            
            // 读取本地配置
            val localConfig = configFileManager.readConfigFile(projectName)
            if (localConfig == null) {
                return@withContext SyncResult.Error("本地配置不存在")
            }
            
            // 检查服务器是否有更新的版本
            val serverConfig = fetchServerConfig(projectName)
            if (serverConfig != null && serverConfig.configVersion > localConfig.configVersion) {
                return@withContext SyncResult.Conflict(localConfig, serverConfig)
            }
            
            // 上传到服务器
            val success = uploadConfigToServer(localConfig)
            if (success) {
                // 记录同步历史
                recordConfigChange(projectName, ChangeType.UPDATED, "同步到服务器")
                SyncResult.Success("配置已同步到服务器")
            } else {
                SyncResult.Error("上传配置到服务器失败")
            }
            
        } catch (e: Exception) {
            AppLogger.log("ConfigSyncService", "Sync to server failed", e)
            SyncResult.Error("同步失败: ${e.message}")
        }
    }
    
    /**
     * 从服务器同步配置
     */
    suspend fun syncFromServer(projectName: String, strategy: SyncStrategy = SyncStrategy.ASK_USER): SyncResult = withContext(Dispatchers.IO) {
        try {
            AppLogger.log("ConfigSyncService", "Syncing config from server: $projectName")
            
            // 获取服务器配置
            val serverConfig = fetchServerConfig(projectName)
            if (serverConfig == null) {
                return@withContext SyncResult.Error("服务器上没有找到配置")
            }
            
            // 检查本地配置
            val localConfig = configFileManager.readConfigFile(projectName)
            
            if (localConfig == null) {
                // 本地没有配置，直接保存服务器配置
                configFileManager.writeConfigFile(serverConfig)
                recordConfigChange(projectName, ChangeType.CREATED, "从服务器同步")
                return@withContext SyncResult.Success("配置已从服务器同步")
            }
            
            // 检查版本冲突
            if (localConfig.configVersion >= serverConfig.configVersion) {
                return@withContext SyncResult.NoChanges
            }
            
            // 根据策略处理冲突
            when (strategy) {
                SyncStrategy.SERVER_WINS -> {
                    configFileManager.writeConfigFile(serverConfig)
                    recordConfigChange(projectName, ChangeType.UPDATED, "服务器版本覆盖本地")
                    SyncResult.Success("已使用服务器版本")
                }
                
                SyncStrategy.LOCAL_WINS -> {
                    // 保持本地版本，但上传到服务器
                    uploadConfigToServer(localConfig)
                    recordConfigChange(projectName, ChangeType.UPDATED, "本地版本上传到服务器")
                    SyncResult.Success("已保持本地版本并同步到服务器")
                }
                
                SyncStrategy.MERGE -> {
                    val mergedConfig = mergeConfigs(localConfig, serverConfig)
                    configFileManager.writeConfigFile(mergedConfig)
                    uploadConfigToServer(mergedConfig)
                    recordConfigChange(projectName, ChangeType.UPDATED, "合并本地和服务器版本")
                    SyncResult.Success("已合并配置")
                }
                
                SyncStrategy.ASK_USER -> {
                    SyncResult.Conflict(localConfig, serverConfig)
                }
            }
            
        } catch (e: Exception) {
            AppLogger.log("ConfigSyncService", "Sync from server failed", e)
            SyncResult.Error("同步失败: ${e.message}")
        }
    }
    
    /**
     * 批量同步所有项目配置
     */
    suspend fun batchSync(projectNames: List<String>, strategy: SyncStrategy = SyncStrategy.MERGE): Map<String, SyncResult> = withContext(Dispatchers.IO) {
        val results = mutableMapOf<String, SyncResult>()
        
        for (projectName in projectNames) {
            try {
                val result = syncFromServer(projectName, strategy)
                results[projectName] = result
                
                AppLogger.log("ConfigSyncService", "Batch sync result for $projectName: $result")
            } catch (e: Exception) {
                results[projectName] = SyncResult.Error("同步失败: ${e.message}")
                AppLogger.log("ConfigSyncService", "Batch sync failed for $projectName", e)
            }
        }
        
        results
    }
    
    /**
     * 从服务器获取配置
     */
    private suspend fun fetchServerConfig(projectName: String): ConfigFileManager.ConfigFile? {
        return try {
            // 使用现有的 ProjectConfigManager 来获取服务器配置
            val projectConfig = projectConfigManager.loadProjectConfigWithSync(projectName, fileManager, forceSync = true)
            
            // 转换为 ConfigFileManager.ConfigFile 格式
            convertToConfigFile(projectConfig)
        } catch (e: Exception) {
            AppLogger.log("ConfigSyncService", "Failed to fetch server config", e)
            null
        }
    }
    
    /**
     * 上传配置到服务器
     */
    private suspend fun uploadConfigToServer(config: ConfigFileManager.ConfigFile): Boolean {
        return try {
            // 转换为 ProjectConfig 格式
            val projectConfig = convertToProjectConfig(config)
            
            // 使用现有的 ProjectConfigManager 上传
            projectConfigManager.uploadConfigToServer(config.projectName, fileManager)
        } catch (e: Exception) {
            AppLogger.log("ConfigSyncService", "Failed to upload config to server", e)
            false
        }
    }
    
    /**
     * 合并本地和服务器配置
     */
    private fun mergeConfigs(
        localConfig: ConfigFileManager.ConfigFile,
        serverConfig: ConfigFileManager.ConfigFile
    ): ConfigFileManager.ConfigFile {
        
        // 合并物料属性（本地优先，服务器补充）
        val mergedMaterials = mutableListOf<ConfigFileManager.MaterialAttribute>()
        mergedMaterials.addAll(localConfig.materialAttributes)
        
        // 添加服务器上有但本地没有的物料
        serverConfig.materialAttributes.forEach { serverMaterial ->
            if (mergedMaterials.none { it.id == serverMaterial.id }) {
                mergedMaterials.add(serverMaterial)
            }
        }
        
        // 合并工序属性（本地优先，服务器补充）
        val mergedProcesses = mutableListOf<ConfigFileManager.ProcessAttribute>()
        mergedProcesses.addAll(localConfig.processAttributes)
        
        // 添加服务器上有但本地没有的工序
        serverConfig.processAttributes.forEach { serverProcess ->
            if (mergedProcesses.none { it.id == serverProcess.id }) {
                mergedProcesses.add(serverProcess)
            }
        }
        
        // 重新排序工序
        mergedProcesses.sortBy { it.order }
        mergedProcesses.forEachIndexed { index, process ->
            mergedProcesses[index] = process.copy(order = index + 1)
        }
        
        // 创建合并后的配置
        return localConfig.copy(
            configVersion = maxOf(localConfig.configVersion, serverConfig.configVersion) + 1,
            updatedAt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.getDefault()).format(Date()),
            materialAttributes = mergedMaterials,
            processAttributes = mergedProcesses,
            metadata = localConfig.metadata.copy(
                totalVersions = localConfig.metadata.totalVersions + 1
            )
        )
    }
    
    /**
     * 记录配置变更历史
     */
    private fun recordConfigChange(projectName: String, changeType: ChangeType, description: String) {
        try {
            val change = ConfigChange(
                projectName = projectName,
                changeType = changeType,
                timestamp = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.getDefault()).format(Date()),
                description = description,
                version = getNextChangeVersion(projectName)
            )
            
            saveConfigChange(change)
            AppLogger.log("ConfigSyncService", "Recorded config change: $change")
        } catch (e: Exception) {
            AppLogger.log("ConfigSyncService", "Failed to record config change", e)
        }
    }
    
    /**
     * 保存配置变更记录
     */
    private fun saveConfigChange(change: ConfigChange) {
        val changesDir = File(context.filesDir, "config/changes").apply { mkdirs() }
        val changeFile = File(changesDir, "${change.projectName}_changes.json")
        
        val changes = if (changeFile.exists()) {
            val existingChanges = mutableListOf<ConfigChange>()
            // 这里可以实现读取现有变更记录的逻辑
            existingChanges
        } else {
            mutableListOf()
        }
        
        changes.add(change)
        
        // 保持最近50条记录
        if (changes.size > 50) {
            changes.removeAt(0)
        }
        
        // 保存到文件（这里简化实现）
        // 实际实现中可以使用 Gson 序列化
    }
    
    /**
     * 获取下一个变更版本号
     */
    private fun getNextChangeVersion(projectName: String): Int {
        // 简化实现，实际中应该从变更历史文件中读取
        return (System.currentTimeMillis() / 1000).toInt()
    }
    
    /**
     * 转换 ProjectConfig 到 ConfigFile
     */
    private fun convertToConfigFile(projectConfig: com.testcenter.qrscanner.data.ProjectConfig): ConfigFileManager.ConfigFile {
        val materials = projectConfig.productTypes.flatMap { productType ->
            productType.materials.map { material ->
                ConfigFileManager.MaterialAttribute(
                    id = "material_${material.name.hashCode()}",
                    name = material.name,
                    type = "component",
                    required = true,
                    qrCodeFormat = "CODE128",
                    description = "物料编号: ${material.partNumber}"
                )
            }
        }.distinctBy { it.id }.toMutableList()
        
        val processes = (projectConfig.processSteps ?: emptyList()).map { processStep ->
            ConfigFileManager.ProcessAttribute(
                id = processStep.id,
                name = processStep.name,
                description = processStep.description,
                order = processStep.order,
                required = processStep.required,
                photoRequired = processStep.photoRequired,
                estimatedDuration = processStep.estimatedDuration
            )
        }.toMutableList()
        
        return ConfigFileManager.ConfigFile(
            projectName = projectConfig.projectName,
            description = "${projectConfig.projectName}项目配置",
            configVersion = projectConfig.version,
            materialAttributes = materials,
            processAttributes = processes
        )
    }
    
    /**
     * 转换 ConfigFile 到 ProjectConfig
     */
    private fun convertToProjectConfig(configFile: ConfigFileManager.ConfigFile): com.testcenter.qrscanner.data.ProjectConfig {
        // 这里需要根据实际的 ProjectConfig 结构进行转换
        // 由于 ProjectConfig 结构比较复杂，这里提供一个简化的转换
        
        val processSteps = configFile.processAttributes.map { processAttr ->
            com.testcenter.qrscanner.data.ProcessStep(
                id = processAttr.id,
                name = processAttr.name,
                description = processAttr.description ?: "",
                order = processAttr.order,
                required = processAttr.required,
                photoRequired = processAttr.photoRequired,
                estimatedDuration = processAttr.estimatedDuration
            )
        }.toMutableList()
        
        // 创建默认的产品类型（简化处理）
        val defaultProductTypes = mutableListOf(
            com.testcenter.qrscanner.data.ProductTypeConfig(
                typeName = "默认产品类型",
                materials = mutableListOf()
            )
        )
        
        return com.testcenter.qrscanner.data.ProjectConfig(
            projectName = configFile.projectName,
            productTypes = defaultProductTypes,
            processSteps = processSteps,
            version = configFile.configVersion,
            lastModified = System.currentTimeMillis()
        )
    }
    
    /**
     * 获取配置变更历史
     */
    fun getConfigChangeHistory(projectName: String): List<ConfigChange> {
        return try {
            val changesDir = File(context.filesDir, "config/changes")
            val changeFile = File(changesDir, "${projectName}_changes.json")
            
            if (changeFile.exists()) {
                // 这里应该实现从文件读取变更历史的逻辑
                // 简化实现，返回空列表
                emptyList()
            } else {
                emptyList()
            }
        } catch (e: Exception) {
            AppLogger.log("ConfigSyncService", "Failed to get config change history", e)
            emptyList()
        }
    }
    
    /**
     * 清理旧的配置变更记录
     */
    fun cleanupOldChanges(keepDays: Int = 30) {
        try {
            val changesDir = File(context.filesDir, "config/changes")
            if (!changesDir.exists()) return
            
            val cutoffTime = System.currentTimeMillis() - (keepDays * 24 * 60 * 60 * 1000L)
            
            changesDir.listFiles()?.forEach { file ->
                if (file.lastModified() < cutoffTime) {
                    file.delete()
                    AppLogger.log("ConfigSyncService", "Deleted old change file: ${file.name}")
                }
            }
        } catch (e: Exception) {
            AppLogger.log("ConfigSyncService", "Failed to cleanup old changes", e)
        }
    }
}