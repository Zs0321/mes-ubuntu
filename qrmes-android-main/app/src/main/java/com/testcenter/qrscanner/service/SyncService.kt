package com.testcenter.qrscanner.service

import android.content.Context
import com.testcenter.qrscanner.data.TestDatabase
import com.testcenter.qrscanner.network.FileManager
import com.testcenter.qrscanner.network.FileManagerFactory
import com.testcenter.qrscanner.repository.TestRepository
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class SyncService(private val context: Context) {
    
    private val database = TestDatabase.getDatabase(context)
    private val repository = TestRepository(database.testRecordDao())
    private var fileManager: FileManager = FileManagerFactory.create(context)
    
    fun syncToNetworkShare(onResult: ((Boolean, Int) -> Unit)? = null) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val unsyncedRecords = repository.getUnsyncedRecords()
                AppLogger.log("SYNC_SERVICE", "Fetched unsynced records: count=${unsyncedRecords.size}")
                if (unsyncedRecords.isNotEmpty()) {
                    val preview = unsyncedRecords.take(3).joinToString("; ") { r ->
                        "${r.serialNumber}|tester=${r.tester}|completed=${r.isCompleted}|created=${r.createdAt}|end=${r.endTime}"
                    }
                    AppLogger.log("SYNC_SERVICE", "Preview (first up to 3): $preview")
                }
                if (unsyncedRecords.isNotEmpty()) {
                    // Recreate in case backend preference changed at runtime
                    fileManager = FileManagerFactory.create(context)
                    val success = fileManager.syncTestRecords(unsyncedRecords)
                    if (success) {
                        // 标记为已同步
                        unsyncedRecords.forEach { record ->
                            repository.markAsSynced(record.id)
                        }
                        kotlinx.coroutines.withContext(Dispatchers.Main) {
                            onResult?.invoke(true, unsyncedRecords.size)
                        }
                    } else {
                        kotlinx.coroutines.withContext(Dispatchers.Main) {
                            onResult?.invoke(false, 0)
                        }
                    }
                } else {
                    // 没有需要上传的数据
                    kotlinx.coroutines.withContext(Dispatchers.Main) {
                        onResult?.invoke(true, 0)
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
                // 如果网络同步失败，尝试保存到本地
                saveToLocalFallback()
                kotlinx.coroutines.withContext(Dispatchers.Main) {
                    onResult?.invoke(false, 0)
                }
            }
        }
    }
    
    private suspend fun saveToLocalFallback() {
        try {
            val unsyncedRecords = repository.getUnsyncedRecords()
            if (unsyncedRecords.isNotEmpty()) {
                val filePath = fileManager.saveToLocalStorage(unsyncedRecords)
                if (filePath != null) {
                    // 可以通知用户文件已保存到本地
                    println("数据已保存到本地文件: $filePath")
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
}
