package com.testcenter.qrscanner

import android.app.Application
import com.testcenter.qrscanner.telemetry.ApkTelemetryManager
import com.testcenter.qrscanner.utils.AppLogger

class MesApp : Application() {
    override fun onCreate() {
        super.onCreate()
        AppLogger.init(this)
        ApkTelemetryManager.install(this)
    }
}
