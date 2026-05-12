package com.testcenter.qrscanner.scanner

import android.content.Intent
import com.google.zxing.client.android.Intents

data class ScanResultBridge(
    val rawValue: String,
    val formatName: String
) {
    fun toExtras(): Map<String, String> {
        return mapOf(
            Intents.Scan.RESULT to rawValue,
            Intents.Scan.RESULT_FORMAT to formatName
        )
    }

    fun toIntent(): Intent {
        return Intent().apply {
            for ((key, value) in toExtras()) {
                putExtra(key, value)
            }
        }
    }

    companion object {
        fun success(rawValue: String, formatName: String): ScanResultBridge {
            return ScanResultBridge(
                rawValue = rawValue,
                formatName = formatName
            )
        }
    }
}
