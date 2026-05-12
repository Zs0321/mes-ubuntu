package com.testcenter.qrscanner.scanner

import android.content.Context
import com.journeyapps.barcodescanner.ScanOptions
import com.testcenter.qrscanner.utils.AppLogger

/**
 * 扫描选项配置
 *
 * 优化点：
 * 1. 移除 ZXing 不识别的无效 extra（SCAN_WIDTH/HEIGHT/CROP_PERCENT）
 * 2. 超时从 30s → 60s
 * 3. 锁定竖屏（避免旋转重建 Activity 丢失扫描状态）
 */
class EnhancedQRScanner(private val context: Context) {

    companion object {
        private const val TAG = "EnhancedQRScanner"
    }

    fun createEnhancedScanOptions(prompt: String): ScanOptions {
        AppLogger.log(TAG, "Creating scan options for: $prompt")

        return ScanOptions().apply {
            setCaptureActivity(EnhancedCaptureActivity::class.java)
            setDesiredBarcodeFormats(ScanOptions.QR_CODE, ScanOptions.DATA_MATRIX)
            setPrompt(prompt)
            setCameraId(0)
            setBeepEnabled(true)
            setBarcodeImageEnabled(false) // 不保存扫描图片，减少内存开销
            setOrientationLocked(true)    // 锁定竖屏，避免旋转重建
            setTimeout(60000)             // 60 秒超时
        }
    }
}
