package com.testcenter.qrscanner.utils

import android.content.Context
import com.google.gson.Gson
import com.testcenter.qrscanner.data.MaterialInfo
import com.testcenter.qrscanner.data.ProductTypeConfig
import com.testcenter.qrscanner.data.ProjectConfig
import com.testcenter.qrscanner.data.ProcessStep
import com.testcenter.qrscanner.network.FileManager
import com.testcenter.qrscanner.repository.ProjectRepository
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/**
 * 项目配置管理器
 * 管理每个项目的独立配置文件
 */
class ProjectConfigManager(private val context: Context) {
    data class SerialRuleMatch(
        val projectName: String,
        val productType: String,
        val prefix: String,
        val length: Int
    )
    
    // 使用 REST API Repository 替代 SMB FileManager
    private val projectRepository = ProjectRepository(context)
    private val configCache = mutableMapOf<String, ProjectConfig>()
    private val serialRuleNormalizePattern = Regex("[-_\\s]+")
    
    private val projectsDir: File
        get() = File(context.filesDir, "projects").apply { 
            if (!exists()) mkdirs() 
        }
    
    /**
     * 获取项目配置文件
     */
    private fun getProjectConfigFile(projectName: String): File {
        val fileName = sanitizeFileName(projectName) + ".json"
        return File(projectsDir, fileName)
    }
    
    /**
     * 清理文件名中的特殊字符
     */
    private fun sanitizeFileName(name: String): String {
        return name.replace(Regex("[\\\\/:*?\"<>|]"), "_")
            .replace(" ", "_")
    }

    private fun normalizeSerialRuleValue(value: String): String {
        return value
            .trim()
            .replace(serialRuleNormalizePattern, "")
    }

    /**
     * 检测本地配置中是否存在可能导致运行时崩溃的脏数据。
     * 目前重点检查工序 responsibleDepartments 为空指针的历史脏数据。
     */
    private fun hasUnsafeStepData(config: ProjectConfig): Boolean {
        return try {
            config.productTypes.any { productType ->
                productType.safeGetProcessSteps().any { step ->
                    (step.responsibleDepartments as? List<*>) == null
                }
            }
        } catch (_: Exception) {
            true
        }
    }
    
    /**
     * 加载项目配置
     * 如果配置文件不存在，返回 null（不再创建默认配置）
     */
    fun loadProjectConfig(projectName: String): ProjectConfig? {
        configCache[projectName]?.let { return it }

        val configFile = getProjectConfigFile(projectName)
        
        return if (configFile.exists()) {
            try {
                val json = configFile.readText()
                ProjectConfig.fromJson(json).also { configCache[projectName] = it }
            } catch (e: Exception) {
                AppLogger.log("ProjectConfigManager", "Failed to load config for $projectName, returning null", e)
                null
            }
        } else {
            configCache.remove(projectName)
            AppLogger.log("ProjectConfigManager", "Config not found for $projectName, returning null")
            null
        }
    }

    fun getCachedProjectNames(): List<String> {
        return try {
            projectsDir.listFiles { file -> file.isFile && file.extension.equals("json", ignoreCase = true) }
                ?.mapNotNull { file ->
                    runCatching {
                        ProjectConfig.fromJson(file.readText()).projectName.trim()
                    }.getOrNull()
                }
                ?.filter { it.isNotEmpty() }
                ?.distinct()
                ?: emptyList()
        } catch (e: Exception) {
            AppLogger.log("ProjectConfigManager", "Failed to list cached project configs", e)
            emptyList()
        }
    }

    fun resolveSerialRuleMatches(
        serialNumber: String,
        projectNames: List<String>
    ): List<SerialRuleMatch> {
        val serial = serialNumber.trim()
        val normalizedSerial = normalizeSerialRuleValue(serial)
        if (serial.isEmpty()) {
            return emptyList()
        }

        val distinctProjects = projectNames
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .distinct()

        val allMatches = mutableListOf<SerialRuleMatch>()
        for (projectName in distinctProjects) {
            val config = loadProjectConfig(projectName) ?: continue
            for (productType in config.productTypes) {
                val typeName = productType.typeName.trim()
                if (typeName.isEmpty()) continue
                for (rawPrefix in productType.serialRules.orEmpty()) {
                    val prefix = rawPrefix.trim()
                    val normalizedPrefix = normalizeSerialRuleValue(prefix)
                    if (normalizedPrefix.isEmpty()) continue
                    if (normalizedSerial.startsWith(normalizedPrefix, ignoreCase = true)) {
                        allMatches.add(
                            SerialRuleMatch(
                                projectName = config.projectName,
                                productType = typeName,
                                prefix = prefix,
                                length = normalizedPrefix.length
                            )
                        )
                    }
                }
            }
        }

        if (allMatches.isEmpty()) {
            return emptyList()
        }

        val maxLength = allMatches.maxOf { it.length }
        return allMatches
            .filter { it.length == maxLength }
            .sortedWith(compareBy<SerialRuleMatch> { it.projectName }.thenBy { it.productType })
            .distinctBy { "${it.projectName.lowercase()}|${it.productType.lowercase()}" }
    }

    suspend fun resolveSerialRuleMatchesWithSync(
        serialNumber: String,
        projectNames: List<String>,
        fileManager: FileManager?
    ): List<SerialRuleMatch> = withContext(Dispatchers.IO) {
        val serial = serialNumber.trim()
        val normalizedSerial = normalizeSerialRuleValue(serial)
        if (serial.isEmpty()) {
            return@withContext emptyList()
        }

        val distinctProjects = projectNames
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .distinct()

        val allMatches = mutableListOf<SerialRuleMatch>()
        for (projectName in distinctProjects) {
            val config = loadProjectConfig(projectName) ?: run {
                if (fileManager == null) {
                    null
                } else {
                    when (val syncResult = syncConfigFromServer(projectName, fileManager, forceSync = false)) {
                        is SyncResult.Success -> syncResult.config
                        is SyncResult.AlreadyLatest -> syncResult.config
                        else -> null
                    }
                }
            } ?: continue

            for (productType in config.productTypes) {
                val typeName = productType.typeName.trim()
                if (typeName.isEmpty()) continue
                for (rawPrefix in productType.serialRules.orEmpty()) {
                    val prefix = rawPrefix.trim()
                    val normalizedPrefix = normalizeSerialRuleValue(prefix)
                    if (normalizedPrefix.isEmpty()) continue
                    if (normalizedSerial.startsWith(normalizedPrefix, ignoreCase = true)) {
                        allMatches.add(
                            SerialRuleMatch(
                                projectName = config.projectName,
                                productType = typeName,
                                prefix = prefix,
                                length = normalizedPrefix.length
                            )
                        )
                    }
                }
            }
        }

        if (allMatches.isEmpty()) {
            return@withContext emptyList()
        }

        val maxLength = allMatches.maxOf { it.length }
        allMatches
            .filter { it.length == maxLength }
            .sortedWith(compareBy<SerialRuleMatch> { it.projectName }.thenBy { it.productType })
            .distinctBy { "${it.projectName.lowercase()}|${it.productType.lowercase()}" }
    }
    
    /**
     * 保存项目配置
     * @param config 项目配置
     * @param autoUpload 是否自动上传到服务器
     * @param fileManager FileManager 实例（如果需要自动上传）
     */
    fun saveProjectConfig(
        config: ProjectConfig,
        autoUpload: Boolean = false,
        fileManager: FileManager? = null
    ): Boolean {
        return try {
            val configFile = getProjectConfigFile(config.projectName)
            configFile.writeText(config.toJson())
            configCache[config.projectName] = config
            AppLogger.log("ProjectConfigManager", "Saved config for ${config.projectName}")
            
            // 如果需要自动上传且提供了 FileManager
            if (autoUpload && fileManager != null) {
                // 使用 lifecycleScope 来启动协程
                if (context is androidx.lifecycle.LifecycleOwner) {
                    val lifecycleOwner = context as androidx.lifecycle.LifecycleOwner
                    lifecycleOwner.lifecycleScope.launch(Dispatchers.IO) {
                        try {
                            val success = uploadConfigToServer(config.projectName, fileManager)
                            if (success) {
                                AppLogger.log("ProjectConfigManager", "Auto-uploaded config to server for ${config.projectName}")
                            }
                        } catch (e: Exception) {
                            AppLogger.log("ProjectConfigManager", "Auto-upload failed: ${e.message}", e)
                        }
                    }
                } else {
                    AppLogger.log("ProjectConfigManager", "Context is not a LifecycleOwner, auto-upload skipped")
                }
            }
            
            true
        } catch (e: Exception) {
            AppLogger.log("ProjectConfigManager", "Failed to save config for ${config.projectName}", e)
            false
        }
    }
    
    /**
     * 创建并保存默认配置
     */
    private fun createAndSaveDefaultConfig(projectName: String): ProjectConfig {
        val config = ProjectConfig.createDefault(projectName)
        saveProjectConfig(config)
        return config
    }
    
    /**
     * 删除项目配置
     */
    fun deleteProjectConfig(projectName: String): Boolean {
        return try {
            val configFile = getProjectConfigFile(projectName)
            val deleted = configFile.delete()
            AppLogger.log("ProjectConfigManager", "Deleted config for $projectName: $deleted")
            deleted
        } catch (e: Exception) {
            AppLogger.log("ProjectConfigManager", "Failed to delete config for $projectName", e)
            false
        }
    }
    
    /**
     * 添加产品类型
     */
    fun addProductType(projectName: String, typeName: String): Boolean {
        val config = loadProjectConfig(projectName) ?: return false
        
        // 检查是否已存在
        if (config.productTypes.any { it.typeName == typeName }) {
            AppLogger.log("ProjectConfigManager", "Product type $typeName already exists")
            return false
        }
        
        // 添加新产品类型（使用空物料列表）
        config.productTypes.add(
            ProductTypeConfig(
                typeName = typeName,
                modelNumber = "",
                materials = mutableListOf(),
                processSteps = mutableListOf()
            )
        )
        return saveProjectConfig(config)
    }
    
    /**
     * 删除产品类型
     */
    fun removeProductType(projectName: String, typeName: String): Boolean {
        val config = loadProjectConfig(projectName) ?: return false
        val removed = config.productTypes.removeIf { it.typeName == typeName }
        
        if (removed) {
            saveProjectConfig(config)
            AppLogger.log("ProjectConfigManager", "Removed product type $typeName")
        }
        
        return removed
    }
    
    /**
     * 添加物料到指定产品类型
     */
    fun addMaterial(projectName: String, productTypeName: String, materialInfo: MaterialInfo): Boolean {
        val config = loadProjectConfig(projectName) ?: return false
        val productType = config.getProductTypeConfig(productTypeName) ?: return false
        
        // 检查是否已存在
        if (productType.materials.any { it.name == materialInfo.name }) {
            AppLogger.log("ProjectConfigManager", "Material ${materialInfo.name} already exists")
            return false
        }
        
        productType.materials.add(materialInfo)
        return saveProjectConfig(config)
    }
    
    /**
     * 删除物料
     */
    fun removeMaterial(projectName: String, productTypeName: String, materialName: String): Boolean {
        val config = loadProjectConfig(projectName) ?: return false
        val productType = config.getProductTypeConfig(productTypeName) ?: return false
        
        val removed = productType.materials.removeIf { it.name == materialName }
        
        if (removed) {
            saveProjectConfig(config)
            AppLogger.log("ProjectConfigManager", "Removed material $materialName")
        }
        
        return removed
    }
    
    /**
     * 更新物料信息
     */
    fun updateMaterial(
        projectName: String, 
        productTypeName: String, 
        oldName: String, 
        newMaterialInfo: MaterialInfo
    ): Boolean {
        val config = loadProjectConfig(projectName) ?: return false
        val productType = config.getProductTypeConfig(productTypeName) ?: return false
        
        val index = productType.materials.indexOfFirst { it.name == oldName }
        if (index == -1) return false
        
        productType.materials[index] = newMaterialInfo
        return saveProjectConfig(config)
    }
    
    /**
     * 获取所有产品类型名称
     */
    fun getProductTypeNames(projectName: String): List<String> {
        val config = loadProjectConfig(projectName) ?: return emptyList()
        return config.productTypes.map { it.typeName }
    }
    
    /**
     * 获取指定产品类型的物料列表
     */
    fun getMaterials(projectName: String, productTypeName: String): List<MaterialInfo> {
        val config = loadProjectConfig(projectName) ?: return emptyList()
        return config.getProductTypeConfig(productTypeName)?.materials ?: emptyList()
    }
    
    /**
     * 从服务器同步项目配置到本地（智能版本比对）
     * @param projectName 项目名称
     * @param fileManager FileManager 实例（WebDAV 或 SMB）
     * @param forceSync 是否强制同步，忽略版本检查
     * @return 同步结果对象
     */
    suspend fun syncConfigFromServer(
        projectName: String, 
        fileManager: FileManager,
        forceSync: Boolean = false
    ): SyncResult {
        return withContext(Dispatchers.IO) {
            try {
                AppLogger.log("ProjectConfigManager", "Syncing config from server for: $projectName (force=$forceSync)")
                
                // 优先使用 REST API
                val apiResult = projectRepository.fetchProjectConfig(projectName)
                var fetchedConfig: ProjectConfig? = null
                
                if (apiResult.isSuccess) {
                    fetchedConfig = apiResult.getOrNull()
                    if (fetchedConfig != null) {
                        AppLogger.log("ProjectConfigManager", "Fetched config via REST API for $projectName")
                    }
                } else {
                    AppLogger.log("ProjectConfigManager", "REST API failed, trying FileManager")
                }
                
                // 如果 REST API 返回 null，尝试 FileManager
                if (fetchedConfig == null) {
                    fetchedConfig = fileManager.fetchProjectConfig(projectName)
                }
                
                // 使用局部不可变变量避免 smart cast 问题
                val serverConfig = fetchedConfig
                
                if (serverConfig == null) {
                    AppLogger.log("ProjectConfigManager", "No config found on server for $projectName")
                    return@withContext SyncResult.NotFound
                }
                
                // 验证服务器配置结构
                val (isValid, validationErrors) = validateConfigStructure(serverConfig)
                if (!isValid) {
                    val errorMsg = "Server config structure validation failed: ${validationErrors.joinToString(", ")}"
                    AppLogger.log("ProjectConfigManager", errorMsg)
                    return@withContext SyncResult.Error(errorMsg)
                }
                
                // 如果不是强制同步，检查版本
                if (!forceSync) {
                    val localConfig = try {
                        loadProjectConfig(projectName)
                    } catch (e: Exception) {
                        null
                    }
                    
                    if (localConfig != null && !serverConfig.isNewerThan(localConfig)) {
                        if (hasUnsafeStepData(localConfig)) {
                            AppLogger.log("ProjectConfigManager", "Local config has unsafe step data, repairing from server copy")
                            saveProjectConfig(serverConfig)
                            return@withContext SyncResult.Success(serverConfig)
                        }
                        AppLogger.log("ProjectConfigManager", "Server config is not newer, using server copy")
                        return@withContext SyncResult.AlreadyLatest(serverConfig)
                    }
                }
                
                // 保存到本地
                saveProjectConfig(serverConfig)
                
                AppLogger.log("ProjectConfigManager", "Successfully synced config from server for $projectName (version=${serverConfig.version})")
                SyncResult.Success(serverConfig)
                
            } catch (e: Exception) {
                AppLogger.log("ProjectConfigManager", "Error syncing config from server: ${e.message}", e)
                SyncResult.Error(e.message ?: "Unknown error")
            }
        }
    }
    
    /**
     * 同步结果
     */
    sealed class SyncResult {
        data class Success(val config: ProjectConfig) : SyncResult()
        data class AlreadyLatest(val config: ProjectConfig) : SyncResult()
        data class Conflict(val localConfig: ProjectConfig, val serverConfig: ProjectConfig) : SyncResult()
        object NotFound : SyncResult()
        data class Error(val message: String) : SyncResult()
    }
    
    /**
     * 批量同步结果明细
     */
    data class ProjectSyncDetail(
        val projectName: String,
        val result: SyncResult
    )

    /**
     * 批量同步最终结果
     */
    data class BatchSyncResult(
        val details: List<ProjectSyncDetail>
    ) {
        fun getSummary(): String {
            val total = details.size
            val success = details.count { it.result is SyncResult.Success }
            val latest = details.count { it.result is SyncResult.AlreadyLatest }
            val notFound = details.count { it.result is SyncResult.NotFound }
            val conflict = details.count { it.result is SyncResult.Conflict }
            val error = details.count { it.result is SyncResult.Error }

            val builder = StringBuilder()
            builder.append("总计: ").append(total)
                .append("\n成功: ").append(success)
                .append("\n已是最新: ").append(latest)
                .append("\n未找到: ").append(notFound)
                .append("\n冲突: ").append(conflict)
                .append("\n失败: ").append(error)
                .append("\n\n明细:\n")

            details.forEach { d ->
                val icon = when (val r = d.result) {
                    is SyncResult.Success -> "✓ v${r.config.version}"
                    is SyncResult.AlreadyLatest -> "= v${r.config.version}"
                    is SyncResult.NotFound -> "?"
                    is SyncResult.Conflict -> "!"
                    is SyncResult.Error -> "✗ ${r.message}"
                }
                builder.append("- ").append(d.projectName).append(" → ").append(icon).append('\n')
            }

            return builder.toString()
        }
    }

    /**
     * 批量同步多个项目配置
     * @param projectNames 项目名称列表
     * @param fileManager 文件管理器
     * @param forceSync 是否强制同步
     * @param onProgress 进度回调 (current, total, projectName, result)
     */
    suspend fun batchSyncConfigs(
        projectNames: List<String>,
        fileManager: FileManager,
        forceSync: Boolean = false,
        onProgress: ((current: Int, total: Int, projectName: String, result: SyncResult) -> Unit)? = null
    ): BatchSyncResult = withContext(Dispatchers.IO) {
        val details = mutableListOf<ProjectSyncDetail>()
        val total = projectNames.size
        var current = 0

        for (name in projectNames) {
            val result = try {
                syncConfigFromServer(name, fileManager, forceSync)
            } catch (e: Exception) {
                AppLogger.log("ProjectConfigManager", "Batch sync error for $name: ${e.message}", e)
                SyncResult.Error(e.message ?: "Unknown error")
            }
            current += 1
            onProgress?.invoke(current, total, name, result)
            details.add(ProjectSyncDetail(name, result))
        }

        BatchSyncResult(details)
    }
    
    /**
     * 冲突解决策略
     */
    enum class ConflictResolutionStrategy {
        USE_SERVER,      // 使用服务器版本
        USE_LOCAL,       // 使用本地版本
        MERGE,           // 合并（本地优先，服务器补充）
        ASK_USER         // 询问用户
    }
    
    /**
     * 上传本地项目配置到服务器 (优先使用 REST API)
     * @param projectName 项目名称
     * @param fileManager FileManager 实例（降级使用）
     * @return 是否上传成功
     */
    suspend fun uploadConfigToServer(projectName: String, fileManager: FileManager): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                AppLogger.log("ProjectConfigManager", "Uploading config to server for: $projectName")
                
                // 加载本地配置
                val localConfig = loadProjectConfig(projectName)
                if (localConfig == null) {
                    AppLogger.log("ProjectConfigManager", "Local config not found for $projectName")
                    return@withContext false
                }
                
                // 优先使用 REST API
                val apiResult = projectRepository.saveProjectConfig(localConfig)
                
                apiResult.fold(
                    onSuccess = {
                        AppLogger.log("ProjectConfigManager", "Successfully uploaded config via REST API for $projectName")
                        return@withContext true
                    },
                    onFailure = { e ->
                        AppLogger.log("ProjectConfigManager", "REST API failed, trying FileManager: ${e.message}")
                    }
                )
                
                // 降级到 FileManager
                val success = fileManager.saveProjectConfig(localConfig)
                
                if (success) {
                    AppLogger.log("ProjectConfigManager", "Successfully uploaded config via FileManager for $projectName")
                } else {
                    AppLogger.log("ProjectConfigManager", "Failed to upload config to server for $projectName")
                }
                
                success
            } catch (e: Exception) {
                AppLogger.log("ProjectConfigManager", "Error uploading config to server: ${e.message}", e)
                false
            }
        }
    }
    
    /**
     * 加载项目配置（优先从服务器同步，失败则使用本地）
     * @param projectName 项目名称
     * @param fileManager FileManager 实例（可选，如果提供则会尝试从服务器同步）
     * @param forceSync 是否强制同步，忽略版本检查
     * @return 项目配置
     */
    suspend fun loadProjectConfigWithSync(
        projectName: String, 
        fileManager: FileManager? = null,
        forceSync: Boolean = false
    ): ProjectConfig = withContext(Dispatchers.IO) {
        // 如果提供了 FileManager，尝试从服务器同步
        if (fileManager != null) {
            try {
                when (val result = syncConfigFromServer(projectName, fileManager, forceSync)) {
                    is SyncResult.Success -> return@withContext result.config
                    is SyncResult.AlreadyLatest -> return@withContext result.config
                    is SyncResult.NotFound -> AppLogger.log("ProjectConfigManager", "Server has no config, using local")
                    is SyncResult.Error -> AppLogger.log("ProjectConfigManager", "Sync error: ${result.message}, using local")
                    is SyncResult.Conflict -> {
                        // 自动解决冲突，使用服务器版本
                        AppLogger.log("ProjectConfigManager", "Conflict detected, auto-resolving with server version")
                        val resolved = resolveConflict(projectName, ConflictResolutionStrategy.USE_SERVER, fileManager)
                        if (resolved != null) {
                            return@withContext resolved
                        }
                        // 如果解决失败，回退到本地
                        val local = loadProjectConfig(projectName)
                        if (local != null) {
                            return@withContext local
                        }
                        // 如果本地也没有，返回默认配置
                        return@withContext ProjectConfig.createDefault(projectName)
                    }
                }
            } catch (e: Exception) {
                AppLogger.log("ProjectConfigManager", "Failed to sync from server, using local: ${e.message}")
            }
        }
        
        // 回退到本地加载
        loadProjectConfig(projectName) ?: ProjectConfig.createDefault(projectName)
    }
    
    /**
     * 检查配置冲突
     * @param projectName 项目名称
     * @param fileManager 文件管理器
     * @return 如果有冲突返回 Conflict 对象，否则返回 null
     */
    suspend fun checkConfigConflict(
        projectName: String,
        fileManager: FileManager
    ): SyncResult.Conflict? = withContext(Dispatchers.IO) {
        try {
            // 检查本地配置是否存在
            val localConfig = loadProjectConfig(projectName) ?: return@withContext null
            
            // 获取服务器配置
            val serverConfig = fileManager.fetchProjectConfig(projectName) ?: return@withContext null
            
            // 检查是否有冲突（双方都有修改）
            if (hasLocalModifications(localConfig) && serverConfig.isNewerThan(localConfig)) {
                // 比较版本
                if (localConfig.version != serverConfig.version) {
                    return@withContext SyncResult.Conflict(localConfig, serverConfig)
                }
            }
            null
        } catch (e: Exception) {
            AppLogger.log("ProjectConfigManager", "Error checking conflict: ${e.message}", e)
            null
        }
    }
    
    /**
     * 检查本地是否有未同步的修改
     */
    private fun hasLocalModifications(config: ProjectConfig): Boolean {
        // 简单实现：检查本地文件的修改时间是否比配置中记录的时间更新
        val configFile = getProjectConfigFile(config.projectName)
        if (!configFile.exists()) return false
        
        val fileModified = configFile.lastModified()
        return fileModified > config.lastModified
    }
    
    /**
     * 解决配置冲突
     * @param projectName 项目名称
     * @param strategy 冲突解决策略
     * @param fileManager FileManager 实例
     * @return 解决后的配置
     */
    suspend fun resolveConflict(
        projectName: String,
        strategy: ConflictResolutionStrategy,
        fileManager: FileManager
    ): ProjectConfig? {
        return withContext(Dispatchers.IO) {
            try {
                val conflict = checkConfigConflict(projectName, fileManager) ?: return@withContext null
                
                val resolvedConfig = when (strategy) {
                    ConflictResolutionStrategy.USE_SERVER -> {
                        AppLogger.log("ProjectConfigManager", "Conflict resolved: using server version")
                        conflict.serverConfig
                    }
                    ConflictResolutionStrategy.USE_LOCAL -> {
                        AppLogger.log("ProjectConfigManager", "Conflict resolved: using local version")
                        conflict.localConfig.createNewVersion()
                    }
                    ConflictResolutionStrategy.MERGE -> {
                        AppLogger.log("ProjectConfigManager", "Conflict resolved: merging")
                        mergeConfigs(conflict.localConfig, conflict.serverConfig)
                    }
                    ConflictResolutionStrategy.ASK_USER -> {
                        // 由调用者处理
                        return@withContext null
                    }
                }
                
                // 保存解决后的配置
                saveProjectConfig(resolvedConfig)
                
                // 如果选择使用本地版本，也上传到服务器
                if (strategy == ConflictResolutionStrategy.USE_LOCAL || strategy == ConflictResolutionStrategy.MERGE) {
                    uploadConfigToServer(projectName, fileManager)
                }
                
                resolvedConfig
            } catch (e: Exception) {
                AppLogger.log("ProjectConfigManager", "Error resolving conflict: ${e.message}", e)
                null
            }
        }
    }
    
    /**
     * 合并两个配置（本地优先）
     */
    private fun mergeConfigs(local: ProjectConfig, server: ProjectConfig): ProjectConfig {
        // 合并产品类型列表
        val mergedProductTypes = mutableListOf<ProductTypeConfig>()
        
        // 添加本地的产品类型
        mergedProductTypes.addAll(local.productTypes)
        
        // 添加服务器上有但本地没有的产品类型
        server.productTypes.forEach { serverType ->
            if (mergedProductTypes.none { it.typeName == serverType.typeName }) {
                mergedProductTypes.add(serverType)
            }
        }
        
        // 创建新版本
        return ProjectConfig(
            projectName = local.projectName,
            productTypes = mergedProductTypes,
            processSteps = mutableListOf(), // 始终为空
            schemaVersion = "2.0",
            version = maxOf(local.version, server.version) + 1,
            lastModified = System.currentTimeMillis()
        )
    }
    
    /**
     * 添加工序步骤
     * @param projectName 项目名称
     * @param productTypeName 产品类型名称
     * @param processStep 工序步骤
     * @return 是否添加成功
     */
    fun addProcessStep(projectName: String, productTypeName: String, processStep: ProcessStep): Boolean {
        val config = loadProjectConfig(projectName) ?: return false
        
        val productType = config.productTypes.find { it.typeName == productTypeName }
        if (productType == null) {
            AppLogger.log("ProjectConfigManager", "Product type $productTypeName not found")
            return false
        }
        
        // 初始化processSteps如果为null
        if (productType.processSteps == null) {
            productType.processSteps = mutableListOf()
        }
        
        // 检查是否已存在相同ID的工序
        if (productType.processSteps!!.any { it.id == processStep.id }) {
            AppLogger.log("ProjectConfigManager", "Process step ${processStep.id} already exists in product type $productTypeName")
            return false
        }
        
        // 确保工序的productType字段正确
        val updatedProcess = processStep.copy(productType = productTypeName)
        productType.processSteps!!.add(updatedProcess)
        
        AppLogger.log("ProjectConfigManager", "Added process step ${processStep.id} to product type $productTypeName")
        return saveProjectConfig(config)
    }
    

    
    /**
     * 删除工序步骤
     * @param projectName 项目名称
     * @param productTypeName 产品类型名称
     * @param processStepId 工序ID
     * @return 是否删除成功
     */
    fun removeProcessStep(projectName: String, productTypeName: String, processStepId: String): Boolean {
        val config = loadProjectConfig(projectName) ?: return false
        
        val productType = config.productTypes.find { it.typeName == productTypeName }
        if (productType == null) {
            AppLogger.log("ProjectConfigManager", "Product type $productTypeName not found")
            return false
        }
        
        val removed = productType.processSteps?.removeIf { it.id == processStepId } ?: false
        
        if (removed) {
            saveProjectConfig(config)
            AppLogger.log("ProjectConfigManager", "Removed process step $processStepId from product type $productTypeName")
        }
        
        return removed
    }
    

    
    /**
     * 更新工序步骤
     * @param projectName 项目名称
     * @param productTypeName 产品类型名称
     * @param processStep 更新后的工序步骤
     * @return 是否更新成功
     */
    fun updateProcessStep(projectName: String, productTypeName: String, processStep: ProcessStep): Boolean {
        val config = loadProjectConfig(projectName) ?: return false
        
        val productType = config.productTypes.find { it.typeName == productTypeName }
        if (productType == null) {
            AppLogger.log("ProjectConfigManager", "Product type $productTypeName not found")
            return false
        }
        
        // 初始化processSteps如果为null
        if (productType.processSteps == null) {
            productType.processSteps = mutableListOf()
        }
        
        val index = productType.processSteps!!.indexOfFirst { it.id == processStep.id }
        
        if (index >= 0) {
            // 确保工序的productType字段正确
            val updatedProcess = processStep.copy(productType = productTypeName)
            productType.processSteps!![index] = updatedProcess
            saveProjectConfig(config)
            AppLogger.log("ProjectConfigManager", "Updated process step ${processStep.id} in product type $productTypeName")
            return true
        }
        
        AppLogger.log("ProjectConfigManager", "Process step ${processStep.id} not found in product type $productTypeName")
        return false
    }
    

    
    /**
     * 获取项目的所有工序步骤
     * 从所有产品类型中收集工序
     */
    fun getProcessSteps(projectName: String): List<ProcessStep> {
        val config = loadProjectConfig(projectName) ?: return emptyList()
        return config.productTypes.flatMap { it.safeGetProcessSteps() }.sortedBy { it.order }
    }
    
    /**
     * 获取指定产品类型的工序步骤
     * @param projectName 项目名称
     * @param productTypeName 产品类型名称
     * @return 该产品类型的工序列表，按顺序排序
     */
    fun getProcessStepsByProductType(projectName: String, productTypeName: String): List<ProcessStep> {
        val config = loadProjectConfig(projectName) ?: return emptyList()
        val productType = config.productTypes.find { it.typeName == productTypeName }
        return productType?.safeGetProcessSteps()?.sortedBy { it.order } ?: emptyList()
    }
    


    
    /**
     * 迁移旧版本配置到新结构
     * @param projectName 项目名称
     * @param autoBackup 是否自动备份原配置
     * @return 迁移结果
     */

    

    
    /**
     * 验证配置结构的完整性
     * @param config 要验证的配置
     * @return 验证结果，包含是否有效和错误信息
     */
    private fun validateConfigStructure(config: ProjectConfig): Pair<Boolean, List<String>> {
        val errors = mutableListOf<String>()
        
        try {
            // 检查基本字段
            if (config.projectName.isBlank()) {
                errors.add("项目名称不能为空")
            }
            
            // 检查产品类型
            if (config.productTypes.isEmpty()) {
                errors.add("配置必须包含至少一个产品类型")
            }
            
            // 检查每个产品类型的工序
            config.productTypes.forEach { productType ->
                if (productType.typeName.isBlank()) {
                    errors.add("产品类型名称不能为空")
                }
                
                // 安全获取工序列表
                val processSteps = productType.safeGetProcessSteps()
                
                // 检查工序ID唯一性
                if (processSteps.isNotEmpty()) {
                    val processIds = processSteps.map { it.id }
                    val duplicateIds = processIds.groupingBy { it }.eachCount().filter { it.value > 1 }
                    if (duplicateIds.isNotEmpty()) {
                        errors.add("产品类型 ${productType.typeName} 中存在重复的工序ID: ${duplicateIds.keys}")
                    }
                    
                    // 检查工序的productType字段是否匹配
                    processSteps.forEach { process ->
                        if (process.productType != productType.typeName) {
                            errors.add("工序 ${process.name} 的productType字段不匹配")
                        }
                    }
                }
            }
            
            return Pair(errors.isEmpty(), errors)
            
        } catch (e: Exception) {
            errors.add("验证过程发生异常: ${e.message}")
            return Pair(false, errors)
        }
    }
    
}
