package com.testcenter.qrscanner.telemetry

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.worker.ApkLogUploadWorker
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.util.UUID
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import javax.net.ssl.SSLException

object ApkTelemetryManager {
    private const val TAG = "ApkTelemetryManager"
    private const val PREFS_NAME = "apk_telemetry"
    private const val KEY_PENDING_EVENTS = "pending_events"
    private const val UNIQUE_UPLOAD_WORK = "apk-log-upload"
    private const val UNIQUE_PERIODIC_UPLOAD_WORK = "apk-log-upload-periodic"

    private val installed = AtomicBoolean(false)

    data class PendingEvent(
        val id: String,
        val eventType: String,
        val severity: String,
        val feature: String,
        val reasonCode: String,
        val httpStatus: Int?,
        val trigger: String,
        val summary: String,
        val extraJson: String,
        val createdAt: Long,
    )

    fun install(context: Context) {
        val appContext = context.applicationContext
        if (!installed.compareAndSet(false, true)) {
            scheduleUpload(appContext)
            return
        }

        schedulePeriodicUpload(appContext)
        scheduleUpload(appContext)

        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            try {
                captureException(
                    appContext,
                    trigger = "uncaught_exception",
                    throwable = throwable,
                    feature = "app_runtime",
                    extras = mapOf(
                        "thread" to thread.name,
                        "fatal" to true,
                    ),
                    fatal = true,
                    scheduleUpload = false,
                )
                scheduleUpload(appContext)
            } catch (handlerError: Exception) {
                AppLogger.log(TAG, "记录全局异常失败: ${handlerError.message}", handlerError)
            }
            defaultHandler?.uncaughtException(thread, throwable)
        }
    }

    fun captureException(
        context: Context,
        trigger: String,
        throwable: Throwable,
        feature: String = "app_runtime",
        extras: Map<String, Any?> = emptyMap(),
        fatal: Boolean = false,
        scheduleUpload: Boolean = true,
    ) {
        val classification = classifyThrowable(throwable)
        val payload = linkedMapOf<String, Any?>(
            "message" to (throwable.message ?: throwable.javaClass.simpleName),
            "exceptionClass" to throwable.javaClass.name,
            "stackTrace" to android.util.Log.getStackTraceString(throwable),
        )
        payload.putAll(extras)
        enqueueEvent(
            context = context,
            eventType = "exception",
            severity = if (fatal) "fatal" else "error",
            feature = feature,
            reasonCode = classification,
            httpStatus = null,
            trigger = trigger,
            summary = throwable.message ?: throwable.javaClass.simpleName,
            extras = payload,
            shouldSchedule = scheduleUpload,
        )
    }

    fun captureUploadFailure(
        context: Context,
        trigger: String,
        feature: String,
        summary: String,
        throwable: Throwable? = null,
        httpStatus: Int? = null,
        reasonCode: String? = null,
        extras: Map<String, Any?> = emptyMap(),
    ) {
        val payload = linkedMapOf<String, Any?>()
        payload.putAll(extras)
        if (throwable != null) {
            payload["exceptionClass"] = throwable.javaClass.name
            payload["stackTrace"] = android.util.Log.getStackTraceString(throwable)
            payload["message"] = throwable.message ?: throwable.javaClass.simpleName
        }
        enqueueEvent(
            context = context,
            eventType = "upload_failure",
            severity = "error",
            feature = feature,
            reasonCode = reasonCode ?: classifyUploadFailure(throwable, httpStatus),
            httpStatus = httpStatus,
            trigger = trigger,
            summary = summary,
            extras = payload,
            shouldSchedule = true,
        )
    }

    fun getPendingEvents(context: Context): List<PendingEvent> {
        val prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val raw = prefs.getString(KEY_PENDING_EVENTS, "[]") ?: "[]"
        return try {
            val array = JSONArray(raw)
            buildList {
                for (index in 0 until array.length()) {
                    val item = array.optJSONObject(index) ?: continue
                    add(
                        PendingEvent(
                            id = item.optString("id"),
                            eventType = item.optString("eventType"),
                            severity = item.optString("severity"),
                            feature = item.optString("feature"),
                            reasonCode = item.optString("reasonCode"),
                            httpStatus = if (item.has("httpStatus") && !item.isNull("httpStatus")) item.optInt("httpStatus") else null,
                            trigger = item.optString("trigger"),
                            summary = item.optString("summary"),
                            extraJson = item.optJSONObject("extras")?.toString() ?: "{}",
                            createdAt = item.optLong("createdAt"),
                        )
                    )
                }
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "读取待上传事件失败: ${e.message}", e)
            emptyList()
        }
    }

    fun removePendingEvent(context: Context, eventId: String) {
        mutateQueue(context) { array ->
            val updated = JSONArray()
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                if (item.optString("id") != eventId) {
                    updated.put(item)
                }
            }
            updated
        }
    }

    fun scheduleUpload(context: Context) {
        val request = OneTimeWorkRequestBuilder<ApkLogUploadWorker>()
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build()
            )
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 10, TimeUnit.MINUTES)
            .build()

        WorkManager.getInstance(context.applicationContext).enqueueUniqueWork(
            UNIQUE_UPLOAD_WORK,
            ExistingWorkPolicy.KEEP,
            request,
        )
    }

    private fun schedulePeriodicUpload(context: Context) {
        val request = PeriodicWorkRequestBuilder<ApkLogUploadWorker>(6, TimeUnit.HOURS)
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build()
            )
            .setBackoffCriteria(BackoffPolicy.LINEAR, 15, TimeUnit.MINUTES)
            .build()

        WorkManager.getInstance(context.applicationContext).enqueueUniquePeriodicWork(
            UNIQUE_PERIODIC_UPLOAD_WORK,
            ExistingPeriodicWorkPolicy.KEEP,
            request,
        )
    }

    private fun enqueueEvent(
        context: Context,
        eventType: String,
        severity: String,
        feature: String,
        reasonCode: String,
        httpStatus: Int?,
        trigger: String,
        summary: String,
        extras: Map<String, Any?>,
        shouldSchedule: Boolean,
    ) {
        val normalizedSummary = summary.trim().ifBlank { eventType }
        val event = JSONObject().apply {
            put("id", UUID.randomUUID().toString())
            put("eventType", eventType)
            put("severity", severity)
            put("feature", feature)
            put("reasonCode", reasonCode)
            put("httpStatus", httpStatus)
            put("trigger", trigger)
            put("summary", normalizedSummary.take(500))
            put("createdAt", System.currentTimeMillis())
            put("extras", JSONObject(extras))
        }

        mutateQueue(context) { array ->
            array.put(event)
            trimQueue(array, maxSize = 20)
        }
        AppLogger.log(TAG, "记录待上传事件: $eventType/$trigger")

        if (shouldSchedule) {
            scheduleUpload(context.applicationContext)
        }
    }

    private fun classifyUploadFailure(throwable: Throwable?, httpStatus: Int?): String {
        if (httpStatus != null) {
            return when (httpStatus) {
                400 -> "http_bad_request"
                401 -> "http_unauthorized"
                403 -> "http_forbidden"
                404 -> "http_not_found"
                408 -> "http_timeout"
                413 -> "http_payload_too_large"
                429 -> "http_rate_limited"
                in 500..599 -> "http_server_error"
                else -> "http_upload_failed"
            }
        }
        return throwable?.let { classifyThrowable(it) } ?: "upload_failed"
    }

    private fun classifyThrowable(throwable: Throwable): String {
        return when (throwable) {
            is UnknownHostException -> "network_dns_failure"
            is SocketTimeoutException -> "network_timeout"
            is SSLException -> "network_ssl_error"
            is SecurityException -> "permission_denied"
            is IOException -> "network_io_error"
            else -> "unknown_exception"
        }
    }

    private fun mutateQueue(context: Context, transform: (JSONArray) -> JSONArray) {
        val prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val current = prefs.getString(KEY_PENDING_EVENTS, "[]") ?: "[]"
        val input = try {
            JSONArray(current)
        } catch (_: Exception) {
            JSONArray()
        }
        val output = transform(input)
        prefs.edit().putString(KEY_PENDING_EVENTS, output.toString()).commit()
    }

    private fun trimQueue(source: JSONArray, maxSize: Int): JSONArray {
        if (source.length() <= maxSize) {
            return source
        }
        val trimmed = JSONArray()
        val start = source.length() - maxSize
        for (index in start until source.length()) {
            trimmed.put(source.get(index))
        }
        return trimmed
    }
}
