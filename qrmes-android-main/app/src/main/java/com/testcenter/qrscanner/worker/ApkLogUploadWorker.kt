package com.testcenter.qrscanner.worker

import android.content.Context
import android.os.Build
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.testcenter.qrscanner.BuildConfig
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.telemetry.ApkTelemetryManager
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody

class ApkLogUploadWorker(
    appContext: Context,
    workerParams: WorkerParameters,
) : CoroutineWorker(appContext, workerParams) {

    companion object {
        private const val TAG = "ApkLogUploadWorker"
    }

    override suspend fun doWork(): Result {
        val pending = ApkTelemetryManager.getPendingEvents(applicationContext)
        if (pending.isEmpty()) {
            return Result.success()
        }

        val event = pending.first()
        return try {
            val zipFile = AppLogger.createLogZip(applicationContext)
            if (zipFile == null || !zipFile.exists()) {
                AppLogger.log(TAG, "没有可上传的日志包，等待下次重试")
                Result.retry()
            } else {
                val response = withContext(Dispatchers.IO) {
                    val api = ApiClient.getApiService(applicationContext)
                    val zipBody = zipFile.asRequestBody("application/zip".toMediaType())
                    val filePart = MultipartBody.Part.createFormData("file", zipFile.name, zipBody)
                    api.uploadApkLogs(
                        file = filePart,
                        appVersionName = BuildConfig.VERSION_NAME.toRequestBody("text/plain".toMediaType()),
                        appVersionCode = BuildConfig.VERSION_CODE.toString().toRequestBody("text/plain".toMediaType()),
                        deviceModel = Build.MODEL.orEmpty().toRequestBody("text/plain".toMediaType()),
                        manufacturer = Build.MANUFACTURER.orEmpty().toRequestBody("text/plain".toMediaType()),
                        androidVersion = Build.VERSION.RELEASE.orEmpty().toRequestBody("text/plain".toMediaType()),
                        source = "apk_auto".toRequestBody("text/plain".toMediaType()),
                        eventType = event.eventType.toRequestBody("text/plain".toMediaType()),
                        severity = event.severity.toRequestBody("text/plain".toMediaType()),
                        feature = event.feature.toRequestBody("text/plain".toMediaType()),
                        reasonCode = event.reasonCode.toRequestBody("text/plain".toMediaType()),
                        httpStatus = (event.httpStatus?.toString() ?: "").toRequestBody("text/plain".toMediaType()),
                        trigger = event.trigger.toRequestBody("text/plain".toMediaType()),
                        summary = event.summary.toRequestBody("text/plain".toMediaType()),
                        extraJson = event.extraJson.toRequestBody("application/json".toMediaType()),
                    )
                }

                if (response.isSuccessful && response.body()?.success == true) {
                    ApkTelemetryManager.removePendingEvent(applicationContext, event.id)
                    AppLogger.log(TAG, "自动上传 APK 日志成功: ${event.eventType}/${event.trigger}")
                    if (ApkTelemetryManager.getPendingEvents(applicationContext).isNotEmpty()) {
                        ApkTelemetryManager.scheduleUpload(applicationContext)
                    }
                    Result.success()
                } else {
                    val code = response.code()
                    val body = try {
                        response.errorBody()?.string()
                    } catch (_: Exception) {
                        null
                    }
                    AppLogger.log(TAG, "自动上传 APK 日志失败: code=$code, body=$body")
                    if (code in listOf(400, 404)) {
                        ApkTelemetryManager.removePendingEvent(applicationContext, event.id)
                        Result.success()
                    } else {
                        Result.retry()
                    }
                }
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "自动上传 APK 日志异常: ${e.message}", e)
            Result.retry()
        }
    }
}
