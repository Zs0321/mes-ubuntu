package com.testcenter.qrscanner.worker

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import androidx.work.Data
import com.testcenter.qrscanner.network.FileManagerFactory
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.PreferencesManager
import com.testcenter.qrscanner.utils.ProjectConfigManager
import com.testcenter.qrscanner.utils.ProjectManager

/**
 * 后台定时同步项目配置的 Worker
 */
class ConfigSyncWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        const val WORK_NAME = "ConfigSyncWork"
        const val KEY_PROJECT_NAME = "project_name"
        const val KEY_FORCE_SYNC = "force_sync"
        const val KEY_RESULT_MESSAGE = "result_message"
        const val KEY_RESULT_VERSION = "result_version"
    }

    override suspend fun doWork(): Result {
        AppLogger.log("ConfigSyncWorker", "Starting config sync work")
        
        try {
            val preferencesManager = PreferencesManager(applicationContext)
            val projectManager = ProjectManager(applicationContext)
            val projectConfigManager = ProjectConfigManager(applicationContext)
            // 获取要同步的项目名称（可以从输入参数获取，或使用当前选中的项目）
            val projectName = inputData.getString(KEY_PROJECT_NAME) 
                ?: projectManager.getSelectedProject()
            
            if (projectName == null) {
                AppLogger.log("ConfigSyncWorker", "No project selected, skipping sync")
                return Result.success(createOutputData("未选择项目", 0))
            }
            
            val forceSync = inputData.getBoolean(KEY_FORCE_SYNC, false)
            
            // 获取 FileManager
            val fileManager = FileManagerFactory.create(
                context = applicationContext,
                preferencesManager.getUsername(),
                preferencesManager.getPassword()
            )
            // 执行同步
            val result = projectConfigManager.syncConfigFromServer(projectName, fileManager, forceSync)
            return when (result) {
                is ProjectConfigManager.SyncResult.Success -> {
                    val message = "配置同步成功: $projectName (v${result.config.version})"
                    AppLogger.log("ConfigSyncWorker", message)
                    Result.success(createOutputData(message, result.config.version))
                }
                is ProjectConfigManager.SyncResult.AlreadyLatest -> {
                    val message = "配置已是最新: $projectName (v${result.config.version})"
                    AppLogger.log("ConfigSyncWorker", message)
                    Result.success(createOutputData(message, result.config.version))
                }
                is ProjectConfigManager.SyncResult.NotFound -> {
                    val message = "服务器上未找到配置: $projectName"
                    AppLogger.log("ConfigSyncWorker", message)
                    Result.retry()
                }
                is ProjectConfigManager.SyncResult.Error -> {
                    val message = "同步错误: ${result.message}"
                    AppLogger.log("ConfigSyncWorker", message)
                    Result.retry()
                }
                is ProjectConfigManager.SyncResult.Conflict -> {
                    val message = "配置冲突: $projectName"
                    AppLogger.log("ConfigSyncWorker", message)
                    // 自动解决冲突，使用服务器版本
                    val resolved = projectConfigManager.resolveConflict(
                        projectName,
                        ProjectConfigManager.ConflictResolutionStrategy.USE_SERVER,
                        fileManager
                    )
                    if (resolved != null) {
                        val success = projectConfigManager.saveProjectConfig(resolved, true, fileManager)
                        if (success) {
                            val successMsg = "已自动解决冲突并使用服务器版本: $projectName (v${resolved.version})"
                            AppLogger.log("ConfigSyncWorker", successMsg)
                            Result.success(createOutputData(successMsg, resolved.version))
                        } else {
                            Result.retry()
                        }
                    } else {
                        Result.retry()
                    }
                }
            }
        } catch (e: Exception) {
            AppLogger.log("ConfigSyncWorker", "Error in config sync work: ${e.message}", e)
            return Result.retry()
        }
    }
    
    private fun createOutputData(message: String, version: Int): Data {
        return Data.Builder()
            .putString(KEY_RESULT_MESSAGE, message)
            .putInt(KEY_RESULT_VERSION, version)
            .build()
    }
}
