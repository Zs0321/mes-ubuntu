package com.testcenter.qrscanner.worker

import android.content.Context
import androidx.work.*
import com.testcenter.qrscanner.utils.AppLogger
import java.util.concurrent.TimeUnit

/**
 * 配置同步调度器
 * 负责安排和管理后台定时同步任务
 */
object ConfigSyncScheduler {
    
    /**
     * 启动定期同步任务
     * @param intervalHours 同步间隔（小时）
     * @param intervalMinutes 同步间隔（分钟）- 如果 intervalHours > 0，此参数忽略
     * @param forceSync 是否强制同步
     */
    fun schedulePeriodicSync(
        context: Context,
        intervalHours: Long = 0,
        intervalMinutes: Long = 30,  // 默认30分钟同步一次
        forceSync: Boolean = false
    ) {
        val interval = if (intervalHours > 0) intervalHours else intervalMinutes
        val timeUnit = if (intervalHours > 0) TimeUnit.HOURS else TimeUnit.MINUTES
        val intervalStr = if (intervalHours > 0) "${intervalHours}h" else "${intervalMinutes}m"
        
        AppLogger.log("ConfigSyncScheduler", "Scheduling periodic sync (interval=$intervalStr, force=$forceSync)")
        
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)  // 需要网络连接
            .build()  // 移除电量限制，允许更频繁同步
        
        val inputData = Data.Builder()
            .putBoolean(ConfigSyncWorker.KEY_FORCE_SYNC, forceSync)
            .build()
        
        val syncRequest = PeriodicWorkRequestBuilder<ConfigSyncWorker>(
            interval, timeUnit
        )
            .setConstraints(constraints)
            .setInputData(inputData)
            .setBackoffCriteria(
                BackoffPolicy.LINEAR,
                5, TimeUnit.MINUTES  // 失败后5分钟重试
            )
            .build()
        
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            ConfigSyncWorker.WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,  // 更新现有任务
            syncRequest
        )
        
        AppLogger.log("ConfigSyncScheduler", "Periodic sync scheduled successfully")
    }
    
    /**
     * 立即执行一次同步（一次性任务）
     * @param projectName 项目名称（可选，不指定则使用当前选中项目）
     * @param forceSync 是否强制同步
     */
    fun syncNow(
        context: Context,
        projectName: String? = null,
        forceSync: Boolean = true
    ): Operation {
        AppLogger.log("ConfigSyncScheduler", "Starting immediate sync (project=$projectName, force=$forceSync)")
        
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        
        val inputData = Data.Builder()
            .putBoolean(ConfigSyncWorker.KEY_FORCE_SYNC, forceSync)
        
        projectName?.let { inputData.putString(ConfigSyncWorker.KEY_PROJECT_NAME, it) }
        
        val syncRequest = OneTimeWorkRequestBuilder<ConfigSyncWorker>()
            .setConstraints(constraints)
            .setInputData(inputData.build())
            .build()
        
        return WorkManager.getInstance(context).enqueue(syncRequest)
    }
    
    /**
     * 取消定期同步任务
     */
    fun cancelPeriodicSync(context: Context) {
        AppLogger.log("ConfigSyncScheduler", "Cancelling periodic sync")
        WorkManager.getInstance(context).cancelUniqueWork(ConfigSyncWorker.WORK_NAME)
    }
    
    /**
     * 获取同步任务的状态
     */
    fun getSyncWorkInfo(context: Context) = 
        WorkManager.getInstance(context).getWorkInfosForUniqueWork(ConfigSyncWorker.WORK_NAME)
}
