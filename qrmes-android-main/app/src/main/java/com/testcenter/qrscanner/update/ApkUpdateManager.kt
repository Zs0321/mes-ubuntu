package com.testcenter.qrscanner.update

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import androidx.core.content.FileProvider
import com.testcenter.qrscanner.BuildConfig
import com.testcenter.qrscanner.network.FileManager
import com.testcenter.qrscanner.repository.ApkUpdateRepository
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.text.DecimalFormat
import java.util.Locale

/**
 * 应用升级管理器
 *
 * 负责：
 * - 从 NAS 获取 APK 列表并比较版本
 * - 下载指定 APK 到本地
 * - 触发安装流程（基于 FileProvider ）
 */
class ApkUpdateManager(private val context: Context) {

    companion object {
        private const val TAG = "ApkUpdateManager"
        private const val APK_FOLDER_NAME = "QRTestScanner"
        private const val DOWNLOAD_SUB_DIR = "QRTestScanner"
        private val SIZE_FORMAT = DecimalFormat("#,##0.00")

        fun formatVersionLabel(versionName: String, buildNumber: Int?): String {
            val normalizedVersion = versionName.ifBlank { "0.0" }
            return "v$normalizedVersion"
        }

        fun formatWatermarkLabel(versionName: String, buildNumber: Int?): String {
            val normalizedVersion = versionName.ifBlank { "0.0" }
            return "v$normalizedVersion"
        }
    }
    
    // 使用 REST API Repository 替代 SMB FileManager
    private val apkRepository = ApkUpdateRepository(context)

    /**
     * 升级检查结果
     */
    sealed class UpdateResult {
        object NoUpdate : UpdateResult()
        data class NewVersion(val info: UpdateInfo) : UpdateResult()
        data class Error(val message: String, val throwable: Throwable? = null) : UpdateResult()
    }

    /**
     * 可用更新信息
     */
    data class UpdateInfo(
        val fileName: String,
        val versionName: String,
        val buildNumber: Int?,
        val sizeBytes: Long,
        val lastModified: Long,
        val releaseNotes: String? = null,
        val releaseNotesFile: String? = null
    ) {
        fun formattedSize(): String {
            val sizeMb = sizeBytes / (1024.0 * 1024.0)
            return "${SIZE_FORMAT.format(sizeMb)} MB"
        }

        fun formattedVersionLabel(): String {
            return formatVersionLabel(versionName, buildNumber)
        }
    }

    /**
     * 检查是否存在新版本 (使用 REST API)
     */
    suspend fun checkForUpdatesViaApi(): UpdateResult = withContext(Dispatchers.IO) {
        try {
            AppLogger.log(TAG, "[版本更新] 开始通过 REST API 检查更新")
            AppLogger.log(TAG, "[版本更新] 当前版本: ${BuildConfig.VERSION_NAME}.${BuildConfig.VERSION_CODE}")
            
            val result = apkRepository.checkUpdate(
                currentVersionCode = BuildConfig.VERSION_CODE,
                currentVersionName = BuildConfig.VERSION_NAME
            )
            
            result.fold(
                onSuccess = { checkResult ->
                    if (checkResult.hasUpdate && checkResult.latestVersion != null) {
                        val latest = checkResult.latestVersion
                        val info = UpdateInfo(
                            fileName = latest.fileName,
                            versionName = latest.versionName,
                            buildNumber = latest.versionCode,
                            sizeBytes = latest.fileSize,
                            lastModified = latest.lastModified,
                            releaseNotes = latest.releaseNotes,
                            releaseNotesFile = latest.releaseNotesFile
                        )
                        AppLogger.log(TAG, "[版本更新] ✓ 找到最新版本: ${info.fileName} (${info.formattedVersionLabel()})")
                        UpdateResult.NewVersion(info)
                    } else {
                        AppLogger.log(TAG, "[版本更新] ✓ 当前已是最新版本")
                        UpdateResult.NoUpdate
                    }
                },
                onFailure = { e ->
                    AppLogger.log(TAG, "[版本更新] ✗ REST API 检查失败: ${e.message}")
                    UpdateResult.Error("检查更新失败: ${e.message}", e)
                }
            )
        } catch (e: Exception) {
            AppLogger.log(TAG, "[版本更新] ✗ 检查更新失败: ${e.message}", e)
            UpdateResult.Error("检查更新失败: ${e.message}", e)
        }
    }
    
    /**
     * 检查是否存在新版本 (兼容旧的 FileManager 接口)
     * @deprecated 请使用 checkForUpdatesViaApi()
     */
    suspend fun checkForUpdates(fileManager: FileManager): UpdateResult = withContext(Dispatchers.IO) {
        // 优先使用 REST API
        val apiResult = checkForUpdatesViaApi()
        if (apiResult !is UpdateResult.Error) {
            return@withContext apiResult
        }
        
        // 降级到 FileManager (SMB)
        AppLogger.log(TAG, "[版本更新] REST API 失败，降级到 FileManager")
        try {
            AppLogger.log(TAG, "[版本更新] 开始检查更新")
            AppLogger.log(TAG, "[版本更新] 当前版本: ${BuildConfig.VERSION_NAME}.${BuildConfig.VERSION_CODE}")
            
            val remoteApks = fileManager.listApkFiles()
            AppLogger.log(TAG, "[版本更新] 从服务器获取到 ${remoteApks.size} 个 APK 文件")
            
            if (remoteApks.isEmpty()) {
                AppLogger.log(TAG, "[版本更新] 服务器上没有找到 APK 文件")
                return@withContext UpdateResult.NoUpdate
            }

            val candidates = remoteApks.map { apk ->
                val info = UpdateInfo(
                    fileName = apk.fileName,
                    versionName = apk.versionName ?: "",
                    buildNumber = apk.buildNumber?.toIntOrNull(),
                    sizeBytes = apk.sizeBytes,
                    lastModified = apk.lastModified
                )
                AppLogger.log(TAG, "[版本更新] 发现 APK: ${info.fileName}, 版本: ${info.versionName}, Build: ${info.buildNumber}, 大小: ${info.formattedSize()}")
                info
            }

            AppLogger.log(TAG, "[版本更新] 开始筛选比当前版本更新的 APK")
            val newerVersions = candidates.filter { 
                val isNewer = isNewerVersion(it.versionName, it.buildNumber)
                AppLogger.log(TAG, "[版本更新] ${it.fileName} 是否更新: $isNewer")
                isNewer
            }
            
            AppLogger.log(TAG, "[版本更新] 找到 ${newerVersions.size} 个更新的版本")

            val best = newerVersions
                .sortedWith(compareBy<UpdateInfo> { it.versionName }
                    .thenBy { it.buildNumber ?: 0 })
                .lastOrNull()

            if (best != null) {
                AppLogger.log(TAG, "[版本更新] ✓ 找到最新版本: ${best.fileName} (${best.formattedVersionLabel()})")
                UpdateResult.NewVersion(best)
            } else {
                AppLogger.log(TAG, "[版本更新] ✓ 当前已是最新版本")
                UpdateResult.NoUpdate
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "[版本更新] ✗ 检查更新失败: ${e.message}", e)
            UpdateResult.Error("检查更新失败: ${e.message}", e)
        }
    }

    /**
     * 下载指定版本并返回保存的文件 (使用 REST API)
     */
    suspend fun downloadUpdateViaApi(info: UpdateInfo): File = withContext(Dispatchers.IO) {
        val result = apkRepository.downloadApk(info.fileName)
        result.fold(
            onSuccess = { file ->
                AppLogger.log(TAG, "APK downloaded via REST API to: ${file.absolutePath}")
                file
            },
            onFailure = { e ->
                throw IllegalStateException("下载APK失败: ${info.fileName}, ${e.message}")
            }
        )
    }
    
    /**
     * 下载指定版本并返回保存的文件 (兼容旧的 FileManager 接口)
     * @deprecated 请使用 downloadUpdateViaApi()
     */
    suspend fun downloadUpdate(fileManager: FileManager, info: UpdateInfo): File = withContext(Dispatchers.IO) {
        // 优先使用 REST API
        try {
            return@withContext downloadUpdateViaApi(info)
        } catch (e: Exception) {
            AppLogger.log(TAG, "[下载] REST API 失败，降级到 FileManager: ${e.message}")
        }
        
        // 降级到 FileManager (SMB)
        val bytes = fileManager.downloadApk(info.fileName)
            ?: throw IllegalStateException("下载APK失败: ${info.fileName}")

        val downloadsDir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            ?: context.filesDir
        val targetDir = File(downloadsDir, DOWNLOAD_SUB_DIR)
        if (!targetDir.exists()) {
            targetDir.mkdirs()
        }

        val targetFile = File(targetDir, info.fileName)
        FileOutputStream(targetFile).use { it.write(bytes) }
        AppLogger.log(TAG, "APK downloaded to: ${targetFile.absolutePath}")
        targetFile
    }

    /**
     * 触发安装APK
     */
    fun installApk(activity: Activity, apkFile: File) {
        val authority = "${BuildConfig.APPLICATION_ID}.fileprovider"
        val apkUri: Uri = FileProvider.getUriForFile(activity, authority, apkFile)

        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(apkUri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }

        activity.startActivity(intent)
    }

    /**
     * 是否已具备未知来源安装权限
     */
    fun hasInstallPermission(context: Context): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.packageManager.canRequestPackageInstalls()
        } else {
            true
        }
    }

    /**
     * 构造未知来源安装权限的跳转 Intent
     */
    fun buildInstallPermissionIntent(context: Context): Intent {
        return Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES).apply {
            data = Uri.parse("package:${context.packageName}")
        }
    }

    /**
     * 当前版本显示名称，例如：Panovation MesApp V1.1.010
     */
    fun currentReleaseDisplayName(): String {
        return "Panovation MesApp ${formatVersionLabel(BuildConfig.VERSION_NAME, BuildConfig.VERSION_CODE)}"
    }

    private fun isNewerVersion(remoteVersion: String, remoteBuild: Int?): Boolean {
        val remoteComponents = parseVersionComponents(remoteVersion)
        val localComponents = parseVersionComponents(BuildConfig.VERSION_NAME)

        AppLogger.log(TAG, "[版本比较] 远程版本: $remoteVersion (组件: $remoteComponents, Build: $remoteBuild)")
        AppLogger.log(TAG, "[版本比较] 本地版本: ${BuildConfig.VERSION_NAME} (组件: $localComponents, Build: ${BuildConfig.VERSION_CODE})")

        val cmp = compareVersionLists(remoteComponents, localComponents)
        AppLogger.log(TAG, "[版本比较] 版本号比较结果: $cmp (>0表示远程更新, <0表示本地更新, =0表示相同)")
        
        return if (cmp > 0) {
            AppLogger.log(TAG, "[版本比较] 结果: 远程版本更新")
            true
        } else if (cmp < 0) {
            AppLogger.log(TAG, "[版本比较] 结果: 本地版本更新")
            false
        } else {
            val remoteBuildNumber = remoteBuild ?: 0
            val isNewer = remoteBuildNumber > BuildConfig.VERSION_CODE
            AppLogger.log(TAG, "[版本比较] 版本号相同，比较 Build 号: 远程=$remoteBuildNumber, 本地=${BuildConfig.VERSION_CODE}, 结果=$isNewer")
            isNewer
        }
    }

    private fun parseVersionComponents(version: String): List<Int> {
        return version.split('.', '-', '_')
            .mapNotNull {
                it.trim().takeIf { part -> part.isNotEmpty() }?.toIntOrNull()
            }
            .ifEmpty { listOf(0) }
    }

    private fun compareVersionLists(remote: List<Int>, local: List<Int>): Int {
        val max = maxOf(remote.size, local.size)
        for (i in 0 until max) {
            val r = remote.getOrElse(i) { 0 }
            val l = local.getOrElse(i) { 0 }
            if (r != l) {
                return r.compareTo(l)
            }
        }
        return 0
    }
}
