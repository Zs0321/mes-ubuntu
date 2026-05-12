package com.testcenter.qrscanner.scanner

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import com.google.zxing.client.android.Intents
import com.google.zxing.BarcodeFormat
import com.google.zxing.DecodeHintType
import com.journeyapps.barcodescanner.CameraPreview
import com.journeyapps.barcodescanner.CaptureActivity
import com.journeyapps.barcodescanner.DecoratedBarcodeView
import com.journeyapps.barcodescanner.DefaultDecoderFactory
import com.journeyapps.barcodescanner.camera.CameraSettings
import com.testcenter.qrscanner.R
import com.testcenter.qrscanner.utils.AppLogger

/**
 * ZXing 增强扫描页（快速模式）
 *
 * 优化点：
 * 1. 去掉 ALSO_INVERTED（每帧解码时间减半，反色码交给 ML Kit 高清模式处理）
 * 2. 加 PURE_BARCODE 提示（工业码背景干净，跳过定位图案搜索，更快）
 * 3. 关闭连续对焦（改为普通自动对焦，避免对焦抽搐）
 * 4. 关闭自动手电（避免频繁闪烁干扰）
 */
class EnhancedCaptureActivity : CaptureActivity() {
    companion object {
        private const val TAG = "EnhancedCaptureActivity"
    }

    private val REQ_HIGH_RES = 3011
    private val escalationPolicy = ScanEscalationPolicy()
    private val mainHandler = Handler(Looper.getMainLooper())
    private lateinit var barcodeScannerView: DecoratedBarcodeView
    private var highResRequested = false
    private var autoFallbackEnabled = true
    private val autoHighResTask = Runnable {
        val action = escalationPolicy.decide(
            elapsedMs = escalationPolicy.autoFallbackDelayMs,
            hasRequestedHighRes = highResRequested,
            isPreviewReady = barcodeScannerView.barcodeView.isPreviewActive,
            autoFallbackEnabled = autoFallbackEnabled
        )
        if (action == ScanEscalationAction.AUTO_HIGH_RES) {
            launchHighResScan()
        }
    }
    private val previewStateListener = object : CameraPreview.StateListener {
        override fun previewSized() = Unit

        override fun previewStarted() {
            scheduleAutoHighRes()
        }

        override fun previewStopped() {
            cancelAutoHighRes()
        }

        override fun cameraError(error: Exception) {
            cancelAutoHighRes()
        }

        override fun cameraClosed() {
            cancelAutoHighRes()
        }
    }

    override fun initializeContent(): DecoratedBarcodeView {
        setContentView(R.layout.activity_strong_capture)
        return findViewById(R.id.zxing_barcode_scanner)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        barcodeScannerView = findViewById(R.id.zxing_barcode_scanner)
        barcodeScannerView.barcodeView.addStateListener(previewStateListener)

        // QR + Data Matrix
        val formats = listOf(BarcodeFormat.QR_CODE, BarcodeFormat.DATA_MATRIX)
        val hints = mutableMapOf<DecodeHintType, Any>(
            DecodeHintType.CHARACTER_SET to "UTF-8"
        )
        barcodeScannerView.barcodeView.decoderFactory = DefaultDecoderFactory(formats, hints, "UTF-8", 0)

        // 相机参数：优先保证快扫，难码再走高清识别兜底
        val cs: CameraSettings = barcodeScannerView.barcodeView.cameraSettings
        cs.isAutoFocusEnabled = true
        cs.isContinuousFocusEnabled = true
        cs.isAutoTorchEnabled = false

        barcodeScannerView.setStatusText("对准二维码快速扫描 · 识别困难时可点高清识别")

        // 高清识别按钮（ML Kit + CameraX）
        findViewById<Button>(R.id.btnHighRes)?.setOnClickListener {
            launchHighResScan()
        }

        // 取消按钮
        findViewById<Button>(R.id.btnCancel)?.setOnClickListener {
            setResult(Activity.RESULT_CANCELED)
            finish()
        }
    }

    override fun onResume() {
        super.onResume()
    }

    override fun onPause() {
        cancelAutoHighRes()
        super.onPause()
    }

    override fun onDestroy() {
        cancelAutoHighRes()
        super.onDestroy()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == REQ_HIGH_RES) {
            val propagatedContents = data?.getStringExtra(Intents.Scan.RESULT)
            val propagatedFormat = data?.getStringExtra(Intents.Scan.RESULT_FORMAT)
            AppLogger.log(
                TAG,
                "High-res finished: resultCode=$resultCode, hasData=${data != null}, " +
                    "hasContents=${!propagatedContents.isNullOrBlank()}, format=${propagatedFormat ?: "-"}"
            )
            val returnAction = escalationPolicy.onHighResFinished(
                succeeded = resultCode == Activity.RESULT_OK && !propagatedContents.isNullOrBlank()
            )
            if (returnAction == HighResReturnAction.PROPAGATE_RESULT && data != null) {
                setResult(Activity.RESULT_OK, data)
                finish()
                return
            }

            highResRequested = false
            autoFallbackEnabled = false
            barcodeScannerView.setStatusText("已返回快速扫描 · 如仍无法识别可手动点“高清识别”")
            return
        }
        super.onActivityResult(requestCode, resultCode, data)
    }

    private fun scheduleAutoHighRes() {
        if (highResRequested || isFinishing || !autoFallbackEnabled) {
            return
        }
        if (!barcodeScannerView.barcodeView.isPreviewActive) {
            return
        }
        cancelAutoHighRes()
        mainHandler.postDelayed(autoHighResTask, escalationPolicy.autoFallbackDelayMs)
    }

    private fun cancelAutoHighRes() {
        mainHandler.removeCallbacks(autoHighResTask)
    }

    private fun launchHighResScan() {
        if (highResRequested || isFinishing) {
            return
        }
        highResRequested = true
        cancelAutoHighRes()
        startActivityForResult(Intent(this, HighResScanActivity::class.java), REQ_HIGH_RES)
    }
}
