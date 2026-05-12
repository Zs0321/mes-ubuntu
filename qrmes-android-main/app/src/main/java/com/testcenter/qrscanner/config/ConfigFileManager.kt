package com.testcenter.qrscanner.config

import android.content.Context
import com.google.gson.Gson
import com.google.gson.GsonBuilder
import com.google.gson.annotations.SerializedName
import com.testcenter.qrscanner.utils.AppLogger
import java.io.File
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.*

/**
 * 配置文件管理器
 * 支持版本管理和结构化配置文件读写
 */
class ConfigFileManager(private val context: Context) {
    
    private val gson: Gson = GsonBuilder()
        .setPrettyPrinting()
        .setDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'")
        .create()
    
    private val configDir: File
        get() = File(context.filesDir, "config").apply { 
            if (!exists()) mkdirs() 
        }
    
    private val versionsDir: File
        get() = File(configDir, "versions").apply { 
            if (!exists()) mkdirs() 
        }
    
    private val backupsDir: File
        get() = File(configDir, "backups").apply { 
            if (!exists()) mkdirs() 
        }
    
    /**
     * 配置文件结构
     */
    data class ConfigFile(
        @SerializedName("version")
        val version: String = "1.0",
        
        @SerializedName("configVersion")
        var configVersion: Int = 1,
        
        @SerializedName("projectName")
        val projectName: String,
        
        @SerializedName("description")
        val description: String? = null,
        
        @SerializedName("createdAt")
        val createdAt: String = getCurrentTimestamp(),
        
        @SerializedName("updatedAt")
        var updatedAt: String = getCurrentTimestamp(),
        
        @SerializedName("createdBy")
        val createdBy: String = "mobile_app",
        
        @SerializedName("materialAttributes")
        val materialAttributes: MutableList<MaterialAttribute> = mutableListOf(),
        
        @SerializedName("processAttributes")
        val processAttributes: MutableList<ProcessAttribute> = mutableListOf(),
        
        @SerializedName("metadata")
        val metadata: ConfigMetadata = ConfigMetadata()
    ) {
        companion object {
            private fun getCurrentTimestamp(): String {
                return SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.getDefault())
                    .format(Date())
            }
        }
    }
    
    /**
     * 物料属性
     */
    data class MaterialAttribute(
        @SerializedName("id")
        val id: String,
        
        @SerializedName("name")
        val name: String,
        
        @SerializedName("type")
        val type: String = "component",
        
        @SerializedName("required")
        val required: Boolean = true,
        
        @SerializedName("qrCodeFormat")
        val qrCodeFormat: String = "CODE128",
        
        @SerializedName("description")
        val description: String? = null
    )
    
    /**
     * 工序属性
     */
    data class ProcessAttribute(
        @SerializedName("id")
        val id: String,
        
        @SerializedName("name")
        val name: String,
        
        @SerializedName("description")
        val description: String? = null,
        
        @SerializedName("order")
        val order: Int,
        
        @SerializedName("required")
        val required: Boolean = true,
        
        @SerializedName("photoRequired")
        val photoRequired: Boolean = true,
        
        @SerializedName("estimatedDuration")
        val estimatedDuration: Int = 0
    )
    
    /**
     * 配置元数据
     */
    data class ConfigMetadata(
        @SerializedName("configFormat")
        val configFormat: String = "v1.0",
        
        @SerializedName("supportedFeatures")
        val supportedFeatures: List<String> = listOf(
            "materialAttributes", 
            "processAttributes", 
            "versionControl"
        ),
        
        @SerializedName("lastBackup")
        var lastBackup: String? = null,
        
        @SerializedName("totalVersions")
        var totalVersions: Int = 1
    )
    
    /**
     * 读取配置文件
     */
    fun readConfigFile(projectName: String): ConfigFile? {
        return try {
            val configFile = getConfigFile(projectName)
            if (!configFile.exists()) {
                AppLogger.log("ConfigFileManager", "Config file not found: $projectName")
                return null
            }
            
            val json = configFile.readText()
            val config = gson.fromJson(json, ConfigFile::class.java)
            
            AppLogger.log("ConfigFileManager", "Read config file: $projectName (version: ${config.configVersion})")
            config
        } catch (e: Exception) {
            AppLogger.log("ConfigFileManager", "Failed to read config file: $projectName", e)
            null
        }
    }
    
    /**
     * 写入配置文件
     */
    fun writeConfigFile(config: ConfigFile): Boolean {
        return try {
            val configFile = getConfigFile(config.projectName)
            
            // 如果文件已存在，先备份
            if (configFile.exists()) {
                createBackup(config.projectName)
            }
            
            // 更新版本信息
            config.configVersion += 1
            config.updatedAt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.getDefault())
                .format(Date())
            
            // 验证配置结构
            if (!validateConfigStructure(config)) {
                AppLogger.log("ConfigFileManager", "Config validation failed: ${config.projectName}")
                return false
            }
            
            // 保存版本历史
            saveVersionHistory(config)
            
            // 写入配置文件
            val json = gson.toJson(config)
            configFile.writeText(json)
            
            AppLogger.log("ConfigFileManager", "Wrote config file: ${config.projectName} (version: ${config.configVersion})")
            true
        } catch (e: Exception) {
            AppLogger.log("ConfigFileManager", "Failed to write config file: ${config.projectName}", e)
            false
        }
    }
    
    /**
     * 创建默认配置文件
     */
    fun createDefaultConfig(projectName: String): ConfigFile {
        val defaultMaterials = mutableListOf(
            MaterialAttribute(
                id = "material_001",
                name = "主要物料",
                type = "component",
                required = true,
                qrCodeFormat = "CODE128",
                description = "产品主要组成物料"
            )
        )
        
        val defaultProcesses = mutableListOf(
            ProcessAttribute(
                id = "process_001",
                name = "热套工序",
                description = "热套装配工序",
                order = 1,
                required = true,
                photoRequired = true,
                estimatedDuration = 300
            ),
            ProcessAttribute(
                id = "process_002",
                name = "总装工序",
                description = "最终总装工序",
                order = 2,
                required = true,
                photoRequired = true,
                estimatedDuration = 600
            )
        )
        
        return ConfigFile(
            projectName = projectName,
            description = "${projectName}项目配置",
            materialAttributes = defaultMaterials,
            processAttributes = defaultProcesses
        )
    }
    
    /**
     * 验证配置文件结构
     */
    private fun validateConfigStructure(config: ConfigFile): Boolean {
        try {
            // 验证必需字段
            if (config.projectName.isBlank()) {
                AppLogger.log("ConfigFileManager", "Project name is required")
                return false
            }
            
            if (config.version.isBlank()) {
                AppLogger.log("ConfigFileManager", "Version is required")
                return false
            }
            
            // 验证物料属性
            for (material in config.materialAttributes) {
                if (material.id.isBlank() || material.name.isBlank()) {
                    AppLogger.log("ConfigFileManager", "Material attribute missing required fields")
                    return false
                }
            }
            
            // 验证工序属性
            for (process in config.processAttributes) {
                if (process.id.isBlank() || process.name.isBlank()) {
                    AppLogger.log("ConfigFileManager", "Process attribute missing required fields")
                    return false
                }
            }
            
            // 验证ID唯一性
            val materialIds = config.materialAttributes.map { it.id }
            if (materialIds.size != materialIds.distinct().size) {
                AppLogger.log("ConfigFileManager", "Duplicate material IDs found")
                return false
            }
            
            val processIds = config.processAttributes.map { it.id }
            if (processIds.size != processIds.distinct().size) {
                AppLogger.log("ConfigFileManager", "Duplicate process IDs found")
                return false
            }
            
            return true
        } catch (e: Exception) {
            AppLogger.log("ConfigFileManager", "Config validation error", e)
            return false
        }
    }
    
    /**
     * 创建备份
     */
    private fun createBackup(projectName: String): Boolean {
        return try {
            val configFile = getConfigFile(projectName)
            if (!configFile.exists()) {
                return false
            }
            
            val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())
            val backupFile = File(backupsDir, "${projectName}_${timestamp}.json")
            
            configFile.copyTo(backupFile, overwrite = true)
            
            // 清理旧备份
            cleanupOldBackups(projectName)
            
            AppLogger.log("ConfigFileManager", "Created backup: ${backupFile.name}")
            true
        } catch (e: Exception) {
            AppLogger.log("ConfigFileManager", "Failed to create backup: $projectName", e)
            false
        }
    }
    
    /**
     * 清理旧备份
     */
    private fun cleanupOldBackups(projectName: String, keepCount: Int = 10) {
        try {
            val backupFiles = backupsDir.listFiles { _, name ->
                name.startsWith("${projectName}_") && name.endsWith(".json")
            }?.toList() ?: return
            
            // 按修改时间排序（最新的在前）
            val sortedFiles = backupFiles.sortedByDescending { it.lastModified() }
            
            // 删除超出保留数量的备份
            for (i in keepCount until sortedFiles.size) {
                sortedFiles[i].delete()
                AppLogger.log("ConfigFileManager", "Deleted old backup: ${sortedFiles[i].name}")
            }
        } catch (e: Exception) {
            AppLogger.log("ConfigFileManager", "Failed to cleanup old backups", e)
        }
    }
    
    /**
     * 保存版本历史
     */
    private fun saveVersionHistory(config: ConfigFile) {
        try {
            val versionFile = File(versionsDir, "${config.projectName}_v${config.configVersion}.json")
            val json = gson.toJson(config)
            versionFile.writeText(json)
            
            AppLogger.log("ConfigFileManager", "Saved version history: ${versionFile.name}")
        } catch (e: Exception) {
            AppLogger.log("ConfigFileManager", "Failed to save version history", e)
        }
    }
    
    /**
     * 获取版本历史
     */
    fun getVersionHistory(projectName: String): List<ConfigVersionInfo> {
        return try {
            val versionFiles = versionsDir.listFiles { _, name ->
                name.startsWith("${projectName}_v") && name.endsWith(".json")
            }?.toList() ?: emptyList()
            
            val versions = mutableListOf<ConfigVersionInfo>()
            for (file in versionFiles) {
                try {
                    val json = file.readText()
                    val config = gson.fromJson(json, ConfigFile::class.java)
                    versions.add(
                        ConfigVersionInfo(
                            version = config.configVersion,
                            updatedAt = config.updatedAt,
                            filename = file.name,
                            fileSize = file.length()
                        )
                    )
                } catch (e: Exception) {
                    AppLogger.log("ConfigFileManager", "Failed to read version file: ${file.name}", e)
                }
            }
            
            // 按版本号排序
            versions.sortedByDescending { it.version }
        } catch (e: Exception) {
            AppLogger.log("ConfigFileManager", "Failed to get version history", e)
            emptyList()
        }
    }
    
    /**
     * 恢复指定版本
     */
    fun restoreVersion(projectName: String, version: Int): Boolean {
        return try {
            val versionFile = File(versionsDir, "${projectName}_v${version}.json")
            if (!versionFile.exists()) {
                AppLogger.log("ConfigFileManager", "Version file not found: ${versionFile.name}")
                return false
            }
            
            // 先备份当前配置
            createBackup(projectName)
            
            // 读取版本配置
            val json = versionFile.readText()
            val config = gson.fromJson(json, ConfigFile::class.java)
            
            // 更新为新版本
            config.configVersion = config.configVersion + 1
            config.updatedAt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.getDefault())
                .format(Date())
            
            // 保存为当前配置
            writeConfigFile(config)
            
            AppLogger.log("ConfigFileManager", "Restored version $version for project: $projectName")
            true
        } catch (e: Exception) {
            AppLogger.log("ConfigFileManager", "Failed to restore version", e)
            false
        }
    }
    
    /**
     * 导出配置文件
     */
    fun exportConfig(projectName: String, exportFile: File): Boolean {
        return try {
            val config = readConfigFile(projectName) ?: return false
            
            val exportData = mapOf(
                "exportedAt" to SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.getDefault()).format(Date()),
                "exportedBy" to "ConfigFileManager",
                "originalProject" to projectName,
                "config" to config
            )
            
            val json = gson.toJson(exportData)
            exportFile.writeText(json)
            
            AppLogger.log("ConfigFileManager", "Exported config: $projectName -> ${exportFile.name}")
            true
        } catch (e: Exception) {
            AppLogger.log("ConfigFileManager", "Failed to export config", e)
            false
        }
    }
    
    /**
     * 导入配置文件
     */
    fun importConfig(importFile: File, targetProjectName: String? = null): Boolean {
        return try {
            if (!importFile.exists()) {
                AppLogger.log("ConfigFileManager", "Import file not found: ${importFile.name}")
                return false
            }
            
            val json = importFile.readText()
            val importData = gson.fromJson(json, Map::class.java)
            
            // 检查是否是导出格式
            val config = if (importData.containsKey("config")) {
                gson.fromJson(gson.toJson(importData["config"]), ConfigFile::class.java)
            } else {
                gson.fromJson(json, ConfigFile::class.java)
            }
            
            // 确定目标项目名称
            val projectName = targetProjectName ?: config.projectName
            
            // 更新项目信息
            val updatedConfig = config.copy(
                projectName = projectName,
                updatedAt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.getDefault()).format(Date())
            )
            
            // 如果目标项目已存在，先备份
            if (getConfigFile(projectName).exists()) {
                createBackup(projectName)
            }
            
            // 保存导入的配置
            writeConfigFile(updatedConfig)
            
            AppLogger.log("ConfigFileManager", "Imported config: ${importFile.name} -> $projectName")
            true
        } catch (e: Exception) {
            AppLogger.log("ConfigFileManager", "Failed to import config", e)
            false
        }
    }
    
    /**
     * 获取配置文件
     */
    private fun getConfigFile(projectName: String): File {
        val sanitizedName = projectName.replace(Regex("[\\\\/:*?\"<>|]"), "_")
        return File(configDir, "${sanitizedName}.json")
    }
    
    /**
     * 版本信息
     */
    data class ConfigVersionInfo(
        val version: Int,
        val updatedAt: String,
        val filename: String,
        val fileSize: Long
    )
}