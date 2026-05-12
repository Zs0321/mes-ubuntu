package com.testcenter.qrscanner.scanner

import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.ZoomSuggestionOptions
import com.google.mlkit.vision.barcode.common.Barcode

data class HighResScanConfig(
    val allowedFormats: IntArray,
    val enablePotentialBarcodes: Boolean,
    val enableAutoZoom: Boolean,
    val hintText: String,
    val timeoutMs: Long,
    val autoFocusIntervalMs: Long,
    val initialZoomRatio: Float,
    val manualMaxZoomRatio: Float
) {
    fun buildOptions(
        zoomCallback: ZoomSuggestionOptions.ZoomCallback,
        maxSupportedZoomRatio: Float
    ): BarcodeScannerOptions {
        val firstFormat = allowedFormats.first()
        val remainingFormats = allowedFormats.copyOfRange(1, allowedFormats.size)
        val builder = BarcodeScannerOptions.Builder()
            .setBarcodeFormats(firstFormat, *remainingFormats)

        if (enablePotentialBarcodes) {
            builder.enableAllPotentialBarcodes()
        }

        if (enableAutoZoom) {
            builder.setZoomSuggestionOptions(
                ZoomSuggestionOptions.Builder(zoomCallback)
                    .setMaxSupportedZoomRatio(maxSupportedZoomRatio)
                    .build()
            )
        }

        return builder.build()
    }

    companion object {
        fun default(): HighResScanConfig {
            return HighResScanConfig(
                allowedFormats = intArrayOf(
                    Barcode.FORMAT_QR_CODE,
                    Barcode.FORMAT_DATA_MATRIX
                ),
                enablePotentialBarcodes = true,
                enableAutoZoom = true,
                hintText = "对准中心框 · Data Matrix 请放在中心 · 双指缩放 · 点击对焦",
                timeoutMs = 60_000L,
                autoFocusIntervalMs = 2000L,
                initialZoomRatio = 1.5f,
                manualMaxZoomRatio = 10f
            )
        }
    }
}
