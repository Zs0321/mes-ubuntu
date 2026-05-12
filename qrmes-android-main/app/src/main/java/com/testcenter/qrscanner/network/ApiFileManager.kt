package com.testcenter.qrscanner.network

import android.content.Context
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.data.ProjectConfig
import com.testcenter.qrscanner.data.TestRecord
import com.testcenter.qrscanner.repository.ActiveTestRepository
import com.testcenter.qrscanner.repository.ApkUpdateRepository
import com.testcenter.qrscanner.repository.PhotoRepository
import com.testcenter.qrscanner.repository.ProductRecordRepository
import com.testcenter.qrscanner.repository.ProjectRepository
import com.testcenter.qrscanner.repository.TesterRepository
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.PreferencesManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Credentials
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

class ApiFileManager(
    private val context: Context,
    private val username: String? = null,
    private val password: String? = null
) : FileManager {

    companion object {
        private const val TAG = "ApiFileManager"
    }

    private val preferencesManager = PreferencesManager(context)
    private val testerRepository = TesterRepository(context)
    private val activeTestRepository = ActiveTestRepository(context)
    private val productRecordRepository = ProductRecordRepository(context)
    private val projectRepository = ProjectRepository(context)
    private val photoRepository = PhotoRepository(context)
    private val apkUpdateRepository = ApkUpdateRepository(context)

    override suspend fun testConnection(): Boolean = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.getApiService(context).getProjects()
            if (response.isSuccessful) {
                return@withContext true
            }

            AppLogger.log(TAG, "API testConnection failed: HTTP ${response.code()} ${response.message()}")
            false
        } catch (e: Exception) {
            AppLogger.log(TAG, "API testConnection exception: ${e.message}", e)
            false
        }
    }

    override suspend fun syncTestRecords(records: List<TestRecord>): Boolean {
        AppLogger.log(TAG, "syncTestRecords is not supported in API-only mode; records=${records.size}")
        return false
    }

    override suspend fun saveToLocalStorage(records: List<TestRecord>): String? = withContext(Dispatchers.IO) {
        try {
            if (records.isEmpty()) {
                return@withContext null
            }

            val backupDir = File(context.getExternalFilesDir(null) ?: context.filesDir, "sync-backup")
            if (!backupDir.exists()) {
                backupDir.mkdirs()
            }
            val backupFile = File(
                backupDir,
                "test_records_${SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())}.csv"
            )
            val formatter = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
            val content = buildString {
                appendLine("serial,start_time,end_time,duration_minutes,status,created_at,tester")
                records.forEach { record ->
                    append(record.serialNumber)
                    append(',')
                    append(formatter.format(record.startTime))
                    append(',')
                    append(record.endTime?.let(formatter::format) ?: "")
                    append(',')
                    append(record.testDurationMinutes?.toString() ?: "")
                    append(',')
                    append(if (record.isCompleted) "completed" else "running")
                    append(',')
                    append(formatter.format(record.createdAt))
                    append(',')
                    append(record.tester)
                    appendLine()
                }
            }
            backupFile.writeText(content, Charsets.UTF_8)
            backupFile.absolutePath
        } catch (e: Exception) {
            AppLogger.log(TAG, "saveToLocalStorage failed: ${e.message}", e)
            null
        }
    }

    override suspend fun fetchTesterList(): List<String> {
        return testerRepository.fetchTesterList().getOrElse {
            AppLogger.log(TAG, "fetchTesterList failed: ${it.message}", it)
            emptyList()
        }
    }

    override suspend fun saveTesterList(testers: List<String>): Boolean {
        return testerRepository.saveTesterList(testers).getOrElse {
            AppLogger.log(TAG, "saveTesterList failed: ${it.message}", it)
            false
        }
    }

    override suspend fun fetchActiveTests(): List<FileManager.ActiveTest> {
        return activeTestRepository.fetchActiveTests().getOrElse {
            AppLogger.log(TAG, "fetchActiveTests failed: ${it.message}", it)
            emptyList()
        }.map {
            FileManager.ActiveTest(
                serial = it.serial,
                tester = it.tester,
                startTime = it.startTime
            )
        }
    }

    override suspend fun upsertActiveTest(serial: String, tester: String, startTime: Date): Boolean {
        return activeTestRepository.startTest(serial, tester).getOrElse {
            AppLogger.log(TAG, "upsertActiveTest failed: ${it.message}", it)
            false
        }
    }

    override suspend fun removeActiveTest(serial: String): Boolean {
        return activeTestRepository.endTest(serial).getOrElse {
            AppLogger.log(TAG, "removeActiveTest failed: ${it.message}", it)
            false
        }
    }

    override suspend fun queryProductRecord(productSerial: String): FileManager.ProductRecord? {
        return productRecordRepository.queryProductRecord(productSerial).getOrElse {
            AppLogger.log(TAG, "queryProductRecord failed: ${it.message}", it)
            null
        }
    }

    override suspend fun fetchProjectList(): List<String> {
        return projectRepository.fetchProjectList().getOrElse {
            AppLogger.log(TAG, "fetchProjectList failed: ${it.message}", it)
            emptyList()
        }
    }

    override suspend fun saveProjectList(projects: List<String>): Boolean {
        return projectRepository.saveProjectList(projects).getOrElse {
            AppLogger.log(TAG, "saveProjectList failed: ${it.message}", it)
            false
        }
    }

    override suspend fun fetchProjectConfig(projectName: String): ProjectConfig? {
        return projectRepository.fetchProjectConfig(projectName).getOrElse {
            AppLogger.log(TAG, "fetchProjectConfig failed: ${it.message}", it)
            null
        }
    }

    override suspend fun saveProjectConfig(config: ProjectConfig): Boolean {
        return projectRepository.saveProjectConfig(config).getOrElse {
            AppLogger.log(TAG, "saveProjectConfig failed: ${it.message}", it)
            false
        }
    }

    override suspend fun uploadPhoto(
        directoryInfo: FileManager.PhotoDirectoryInfo,
        fileName: String,
        photoBytes: ByteArray
    ): Boolean {
        return photoRepository.uploadPhoto(
            photoBytes = photoBytes,
            fileName = fileName,
            productSerial = directoryInfo.productSerial,
            projectName = directoryInfo.projectName,
            productType = directoryInfo.productType,
            projectCode = directoryInfo.projectCode,
            modelNumber = directoryInfo.modelNumber
        ).getOrElse {
            AppLogger.log(TAG, "uploadPhoto failed: ${it.message}", it)
            null
        } != null
    }

    override suspend fun listPhotos(directoryInfo: FileManager.PhotoDirectoryInfo): List<FileManager.PhotoInfo> {
        return photoRepository.listPhotos(
            projectName = directoryInfo.projectName,
            productType = directoryInfo.productType,
            productSerial = directoryInfo.productSerial
        ).getOrElse {
            AppLogger.log(TAG, "listPhotos failed: ${it.message}", it)
            emptyList()
        }.map { photo ->
            FileManager.PhotoInfo(
                fileName = photo.fileName,
                filePath = photo.fullUrl ?: photo.thumbnailUrl ?: photo.filePath ?: "",
                fileSize = 0L,
                lastModified = 0L
            )
        }
    }

    override suspend fun downloadPhoto(
        directoryInfo: FileManager.PhotoDirectoryInfo,
        fileName: String
    ): ByteArray? = withContext(Dispatchers.IO) {
        try {
            val photos = photoRepository.listPhotos(
                projectName = directoryInfo.projectName,
                productType = directoryInfo.productType,
                productSerial = directoryInfo.productSerial
            ).getOrElse {
                AppLogger.log(TAG, "downloadPhoto listPhotos failed: ${it.message}", it)
                emptyList()
            }

            val target = photos.firstOrNull { it.fileName == fileName }
            val rawUrl = target?.fullUrl ?: target?.thumbnailUrl ?: target?.filePath
            if (rawUrl.isNullOrBlank()) {
                AppLogger.log(TAG, "downloadPhoto target URL missing for $fileName")
                return@withContext null
            }

            val apiBaseUrl = preferencesManager.getApiBaseUrl().trimEnd('/')
            val requestUrl = if (rawUrl.startsWith("http://") || rawUrl.startsWith("https://")) {
                rawUrl
            } else {
                "$apiBaseUrl/${rawUrl.trimStart('/')}"
            }

            val requestBuilder = Request.Builder().url(requestUrl).get()
            resolveCredentials()?.let { requestBuilder.header("Authorization", it) }

            val client = OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(60, TimeUnit.SECONDS)
                .build()

            client.newCall(requestBuilder.build()).execute().use { response ->
                if (!response.isSuccessful) {
                    AppLogger.log(TAG, "downloadPhoto failed: HTTP ${response.code} $requestUrl")
                    return@withContext null
                }
                response.body?.bytes()
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "downloadPhoto failed: ${e.message}", e)
            null
        }
    }

    override suspend fun listApkFiles(): List<FileManager.ApkFileInfo> {
        return apkUpdateRepository.listApkFiles().getOrElse {
            AppLogger.log(TAG, "listApkFiles failed: ${it.message}", it)
            emptyList()
        }.map {
            FileManager.ApkFileInfo(
                fileName = it.fileName,
                versionName = it.versionName,
                buildNumber = it.versionCode.toString(),
                sizeBytes = it.fileSize,
                lastModified = it.lastModified
            )
        }
    }

    override suspend fun downloadApk(apkFileName: String): ByteArray? = withContext(Dispatchers.IO) {
        try {
            apkUpdateRepository.downloadApk(apkFileName).getOrElse {
                AppLogger.log(TAG, "downloadApk failed: ${it.message}", it)
                null
            }?.readBytes()
        } catch (e: Exception) {
            AppLogger.log(TAG, "downloadApk failed: ${e.message}", e)
            null
        }
    }

    private fun resolveCredentials(): String? {
        val resolvedUsername = username ?: preferencesManager.getUsername()
        val resolvedPassword = password ?: preferencesManager.getPassword()
        if (resolvedUsername.isNullOrBlank() || resolvedPassword.isNullOrBlank()) {
            return null
        }
        return Credentials.basic(resolvedUsername, resolvedPassword)
    }
}
