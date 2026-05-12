package com.testcenter.qrscanner.network

import android.content.Context
import com.testcenter.qrscanner.utils.PreferencesManager

object FileManagerFactory {
    fun create(
        context: Context,
        username: String? = null,
        password: String? = null,
        backendOverride: String? = null
    ): FileManager {
        val pm = PreferencesManager(context)
        val backend = (backendOverride ?: pm.getBackend()).lowercase()
        com.testcenter.qrscanner.utils.AppLogger.log(
            "FileManagerFactory",
            "Creating ApiFileManager for backend hint: $backend (override: $backendOverride, saved: ${pm.getBackend()})"
        )
        return ApiFileManager(context, username, password)
    }
}
