package com.testcenter.qrscanner.utils

import android.content.Context
import android.os.Build
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.io.RandomAccessFile
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

object AppLogger {
    @Volatile
    private var initialized = false
    private var logFile: File? = null
    private var webdavLogFile: File? = null
    private var smbLogFile: File? = null
    private var appDataDir: File? = null
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.getDefault())
    private val fileNameFormat = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault())
    private const val MAX_LOG_BYTES_PER_FILE = 2L * 1024L * 1024L // 2MB
    private const val ZIP_PREFIX = "logs_"
    private const val ZIP_SUFFIX = ".zip"
    private const val ZIP_BUFFER_SIZE = 8 * 1024

    @Synchronized
    fun init(context: Context) {
        if (initialized) return
        try {
            // 优先写入 external files；不可用时回退到内部 files，避免机型差异导致日志不可用
            val baseDir = context.getExternalFilesDir(null) ?: context.filesDir
            appDataDir = File(baseDir, "QRTestScanner")
            if (!appDataDir!!.exists() && !appDataDir!!.mkdirs()) {
                throw IllegalStateException("无法创建应用数据目录: ${appDataDir!!.absolutePath}")
            }
            
            // Create logs subdirectory
            val logsDir = File(appDataDir, "logs")
            if (!logsDir.exists() && !logsDir.mkdirs()) {
                throw IllegalStateException("无法创建日志目录: ${logsDir.absolutePath}")
            }
            
            // Create data subdirectory for app data
            val dataDir = File(appDataDir, "data")
            if (!dataDir.exists() && !dataDir.mkdirs()) {
                throw IllegalStateException("无法创建数据目录: ${dataDir.absolutePath}")
            }
            
            // Initialize log files with date stamps
            val today = fileNameFormat.format(Date())
            logFile = File(logsDir, "app_$today.log")
            webdavLogFile = File(logsDir, "webdav_$today.log")
            smbLogFile = File(logsDir, "smb_$today.log")
            
            initialized = true
            log("AppLogger", "Logger initialized.")
            log("AppLogger", "App data directory: ${appDataDir?.absolutePath}")
            log("AppLogger", "Main log file: ${logFile?.absolutePath}")
            log("AppLogger", "WebDAV log file: ${webdavLogFile?.absolutePath}")
            log("AppLogger", "SMB log file: ${smbLogFile?.absolutePath}")
            
            // Clean up old log files (keep last 7 days)
            cleanupOldLogs(logsDir)
        } catch (e: Exception) {
            Log.e("AppLogger", "Failed to init logger", e)
        }
    }

    fun log(tag: String, message: String, throwable: Throwable? = null) {
        val ts = dateFormat.format(Date())
        if (throwable != null) {
            Log.e(tag, message, throwable)
        } else {
            Log.d(tag, message)
        }
        try {
            val sb = StringBuilder()
            sb.append(ts).append(" [").append(tag).append("] ").append(message).append('\n')
            if (throwable != null) {
                sb.append(Log.getStackTraceString(throwable)).append('\n')
            }
            logFile?.appendText(sb.toString())
        } catch (_: Exception) {
            // ignore file IO errors for logging
        }
    }
    
    fun logWebDAV(operation: String, details: String, throwable: Throwable? = null) {
        val ts = dateFormat.format(Date())
        val level = if (throwable != null) "ERROR" else "INFO"
        
        // Log to Android log
        if (throwable != null) {
            Log.e("WebDAV", "[$operation] $details", throwable)
        } else {
            Log.d("WebDAV", "[$operation] $details")
        }
        
        // Log to dedicated WebDAV file
        try {
            val sb = StringBuilder()
            sb.append(ts).append(" [$level] [$operation] ").append(details).append('\n')
            if (throwable != null) {
                sb.append(Log.getStackTraceString(throwable)).append('\n')
            }
            webdavLogFile?.appendText(sb.toString())
        } catch (_: Exception) {
            // ignore file IO errors for logging
        }
    }
    
    fun getAppDataDirectory(): File? = appDataDir
    
    fun getLogDirectory(): File? = appDataDir?.let { File(it, "logs") }

    @Synchronized
    fun clearCurrentLogs(context: Context): Int {
        if (!initialized) {
            init(context)
        }

        val logsDir = getLogDirectory() ?: return 0
        var clearedCount = 0

        logsDir.listFiles()?.forEach { file ->
            if (file.isFile && file.name.endsWith(".log")) {
                runCatching {
                    FileOutputStream(file, false).use { }
                    clearedCount += 1
                }
            }
        }

        context.cacheDir
            .listFiles { f -> f.isFile && f.name.startsWith(ZIP_PREFIX) && f.name.endsWith(ZIP_SUFFIX) }
            ?.forEach { file ->
                runCatching {
                    if (file.delete()) {
                        clearedCount += 1
                    }
                }
            }

        return clearedCount
    }
    
    private fun cleanupOldLogs(logsDir: File) {
        try {
            val cutoffTime = System.currentTimeMillis() - (7 * 24 * 60 * 60 * 1000L) // 7 days ago
            logsDir.listFiles()?.forEach { file ->
                if (file.isFile && file.name.endsWith(".log") && file.lastModified() < cutoffTime) {
                    file.delete()
                    Log.d("AppLogger", "Deleted old log file: ${file.name}")
                }
            }
        } catch (e: Exception) {
            Log.e("AppLogger", "Failed to cleanup old logs", e)
        }
    }
    
    fun logSMB(operation: String, details: String, throwable: Throwable? = null) {
        val ts = dateFormat.format(Date())
        val level = if (throwable != null) "ERROR" else "INFO"
        
        // Log to Android log
        if (throwable != null) {
            Log.e("SMB", "[$operation] $details", throwable)
        } else {
            Log.d("SMB", "[$operation] $details")
        }
        
        // Log to dedicated SMB file
        try {
            val sb = StringBuilder()
            sb.append(ts).append(" [$level] [$operation] ").append(details).append('\n')
            if (throwable != null) {
                sb.append(Log.getStackTraceString(throwable)).append('\n')
            }
            smbLogFile?.appendText(sb.toString())
        } catch (_: Exception) {
            // ignore file IO errors for logging
        }
    }
    
    fun logFileOperation(operation: String, filePath: String, success: Boolean, details: String = "") {
        val status = if (success) "SUCCESS" else "FAILED"
        val message = "File $operation: $filePath - $status" + if (details.isNotEmpty()) " - $details" else ""
        log("FileOp", message)
    }

    /**
     * 将所有日志文件打包为 zip，附带设备信息，用于分享
     * @return zip 文件，失败返回 null
     */
    @Synchronized
    fun createLogZip(context: Context): File? {
        return try {
            val logsDir = getLogDirectory()
            if (logsDir == null || !logsDir.exists()) {
                log("AppLogger", "日志目录不存在，无法打包")
                return null
            }

            val logFiles = logsDir.listFiles { f -> f.isFile && f.name.endsWith(".log") }
            if (logFiles.isNullOrEmpty()) {
                log("AppLogger", "没有日志文件可打包")
                return null
            }

            // 清理之前的旧 zip
            context.cacheDir.listFiles { f -> f.name.startsWith(ZIP_PREFIX) && f.name.endsWith(ZIP_SUFFIX) }
                ?.forEach { it.delete() }

            val timestamp = SimpleDateFormat("yyyy-MM-dd_HHmmss", Locale.getDefault()).format(Date())
            val zipFile = File(context.cacheDir, "${ZIP_PREFIX}${timestamp}${ZIP_SUFFIX}")
            var truncatedFiles = 0

            ZipOutputStream(FileOutputStream(zipFile)).use { zos ->
                // 写入日志文件
                for (file in logFiles.sortedByDescending { it.lastModified() }) {
                    val snapshotSize = file.length().coerceAtLeast(0L)
                    val bytesToWrite = minOf(snapshotSize, MAX_LOG_BYTES_PER_FILE)
                    val startOffset = snapshotSize - bytesToWrite
                    if (snapshotSize > MAX_LOG_BYTES_PER_FILE) {
                        truncatedFiles += 1
                    }

                    zos.putNextEntry(ZipEntry(file.name))
                    copyFileSnapshotToZip(file, startOffset, bytesToWrite, zos)
                    zos.closeEntry()
                }

                // 写入设备信息
                zos.putNextEntry(ZipEntry("device_info.txt"))
                val info = buildString {
                    appendLine("=== 设备信息 ===")
                    appendLine("设备型号: ${Build.MANUFACTURER} ${Build.MODEL}")
                    appendLine("Android 版本: ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})")
                    appendLine("App 版本: ${getAppVersion(context)}")
                    appendLine("导出时间: ${dateFormat.format(Date())}")
                    appendLine("日志文件数: ${logFiles.size}")
                    appendLine("单文件打包上限: ${MAX_LOG_BYTES_PER_FILE / (1024 * 1024)}MB（超出取尾部）")
                    appendLine("被截断文件数: $truncatedFiles")
                }
                zos.write(info.toByteArray(Charsets.UTF_8))
                zos.closeEntry()
            }

            log("AppLogger", "日志打包完成: ${zipFile.absolutePath} (${zipFile.length() / 1024}KB)")
            zipFile
        } catch (e: Exception) {
            Log.e("AppLogger", "日志打包失败", e)
            null
        }
    }

    private fun copyFileSnapshotToZip(
        file: File,
        startOffset: Long,
        byteCount: Long,
        zos: ZipOutputStream
    ) {
        if (byteCount <= 0L) return

        RandomAccessFile(file, "r").use { raf ->
            if (startOffset > 0L) {
                raf.seek(startOffset)
            }

            val buffer = ByteArray(ZIP_BUFFER_SIZE)
            var remaining = byteCount
            while (remaining > 0L) {
                val toRead = minOf(buffer.size.toLong(), remaining).toInt()
                val read = raf.read(buffer, 0, toRead)
                if (read <= 0) break
                zos.write(buffer, 0, read)
                remaining -= read
            }
        }
    }

    private fun getAppVersion(context: Context): String {
        return try {
            val pInfo = context.packageManager.getPackageInfo(context.packageName, 0)
            "${pInfo.versionName} (${pInfo.versionCode})"
        } catch (_: Exception) {
            "unknown"
        }
    }
}
