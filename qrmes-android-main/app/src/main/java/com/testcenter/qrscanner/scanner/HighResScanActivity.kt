package com.testcenter.qrscanner.scanner

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.util.Size
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.*
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.ZoomSuggestionOptions
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import com.testcenter.qrscanner.R
import com.testcenter.qrscanner.utils.AppLogger
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * ML Kit + CameraX 高清扫描页
 *
 * 优化点：
 * 1. ML Kit 只扫 QR + DataMatrix（不扫其他格式，速度翻倍）
 * 2. 分辨率回退策略：优先 1920x1080，不支持则自动降级
 * 3. AtomicBoolean 跳帧：上一帧没处理完就丢弃新帧
 * 4. 定时触发对焦（每 2 秒），比连续对焦更稳定
 * 5. 初始放大 1.5x（2.0x 容易把码推出视野）
 * 6. 超时 60 秒
 * 7. 修复 imageProxy 双重 close bug
 */
class HighResScanActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "HighResScanActivity"
    }

    private val scanConfig = HighResScanConfig.default()
    private lateinit var previewView: PreviewView
    private var camera: Camera? = null
    private var cameraExecutor: ExecutorService? = null
    private var torchEnabled = false
    private var finished = false

    // 跳帧保护：上一帧还在处理时丢弃新帧
    private val isProcessing = AtomicBoolean(false)

    private val mainHandler by lazy { android.os.Handler(android.os.Looper.getMainLooper()) }

    private val timeoutTask = Runnable {
        if (!finished) {
            finished = true
            Toast.makeText(this, "扫描超时，请重试", Toast.LENGTH_SHORT).show()
            setResult(Activity.RESULT_CANCELED)
            finish()
        }
    }

    // 定时自动对焦
    private val autoFocusTask = object : Runnable {
        override fun run() {
            if (!finished) {
                triggerAutoFocus()
                mainHandler.postDelayed(this, scanConfig.autoFocusIntervalMs)
            }
        }
    }

    // ML Kit 扫描器：只扫 QR + DataMatrix
    private val scanner by lazy {
        val options = scanConfig.buildOptions(
            zoomCallback = object : ZoomSuggestionOptions.ZoomCallback {
                override fun setZoom(suggestedZoomRatio: Float): Boolean {
                    val activeCamera = camera ?: return false
                    val safeZoomRatio = suggestedZoomRatio.coerceIn(1f, resolveMaxZoomRatio())
                    activeCamera.cameraControl.setZoomRatio(safeZoomRatio)
                    return true
                }
            },
            maxSupportedZoomRatio = resolveMaxZoomRatio()
        )
        BarcodeScanning.getClient(options)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_high_res_scan)

        previewView = findViewById(R.id.previewView)
        val btnBack: Button = findViewById(R.id.btnBack)
        val btnTorch: Button = findViewById(R.id.btnTorch)
        val tvHint: TextView = findViewById(R.id.tvHint)
        tvHint.text = scanConfig.hintText

        btnBack.setOnClickListener {
            if (!finished) {
                finished = true
                setResult(Activity.RESULT_CANCELED)
            }
            cleanup()
            finish()
        }

        btnTorch.setOnClickListener {
            torchEnabled = !torchEnabled
            camera?.cameraControl?.enableTorch(torchEnabled)
            btnTorch.text = if (torchEnabled) "关闭手电" else "开启手电"
        }

        cameraExecutor = Executors.newSingleThreadExecutor()
        startCamera()
        setupGestures()

        // 超时 60 秒
        mainHandler.postDelayed(timeoutTask, scanConfig.timeoutMs)
        // 定时对焦
        mainHandler.postDelayed(autoFocusTask, scanConfig.autoFocusIntervalMs)
    }

    private fun triggerAutoFocus() {
        try {
            val factory = previewView.meteringPointFactory
            // 对焦屏幕中心
            val centerPoint = factory.createPoint(
                previewView.width / 2f,
                previewView.height / 2f
            )
            val action = FocusMeteringAction.Builder(centerPoint, FocusMeteringAction.FLAG_AF)
                .setAutoCancelDuration(1, TimeUnit.SECONDS)
                .build()
            camera?.cameraControl?.startFocusAndMetering(action)
        } catch (_: Exception) {}
    }

    private fun setupGestures() {
        val scaleGestureDetector = android.view.ScaleGestureDetector(this,
            object : android.view.ScaleGestureDetector.SimpleOnScaleGestureListener() {
                override fun onScale(detector: android.view.ScaleGestureDetector): Boolean {
                    val current = camera?.cameraInfo?.zoomState?.value?.zoomRatio ?: 1f
                    val delta = detector.scaleFactor
                    camera?.cameraControl?.setZoomRatio(
                        (current * delta).coerceIn(1f, resolveMaxZoomRatio())
                    )
                    return true
                }
            })

        previewView.setOnTouchListener { _, event ->
            scaleGestureDetector.onTouchEvent(event)
            if (event.action == android.view.MotionEvent.ACTION_UP) {
                val factory = previewView.meteringPointFactory
                val point = factory.createPoint(event.x, event.y)
                val action = FocusMeteringAction.Builder(point, FocusMeteringAction.FLAG_AF)
                    .setAutoCancelDuration(3, TimeUnit.SECONDS)
                    .build()
                camera?.cameraControl?.startFocusAndMetering(action)
            }
            true
        }
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener({
            try {
                val cameraProvider = cameraProviderFuture.get()

                // 分辨率策略：优先 1920x1080，不支持则自动选最接近的更高分辨率
                val selector = ResolutionSelector.Builder()
                    .setResolutionStrategy(
                        ResolutionStrategy(
                            Size(1920, 1080),
                            ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER
                        )
                    )
                    .build()

                val preview = Preview.Builder()
                    .setResolutionSelector(selector)
                    .build()
                    .also { it.setSurfaceProvider(previewView.surfaceProvider) }

                val analysis = ImageAnalysis.Builder()
                    .setResolutionSelector(selector)
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()

                analysis.setAnalyzer(cameraExecutor!!) { imageProxy ->
                    processFrame(imageProxy)
                }

                cameraProvider.unbindAll()
                camera = cameraProvider.bindToLifecycle(
                    this, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis
                )

                // 初始放大，帮助小码和密集码更快进入可识别区域
                camera?.cameraControl?.setZoomRatio(
                    scanConfig.initialZoomRatio.coerceIn(1f, resolveMaxZoomRatio())
                )

                AppLogger.log(TAG, "相机启动成功")
            } catch (e: Exception) {
                AppLogger.log(TAG, "相机启动失败: ${e.message}", e)
                Toast.makeText(this, "相机初始化失败，请返回重试", Toast.LENGTH_LONG).show()
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun processFrame(imageProxy: ImageProxy) {
        // 跳帧：上一帧还在处理中，直接丢弃
        if (!isProcessing.compareAndSet(false, true)) {
            imageProxy.close()
            return
        }

        val mediaImage = imageProxy.image
        if (mediaImage == null) {
            imageProxy.close()
            isProcessing.set(false)
            return
        }

        val image = InputImage.fromMediaImage(mediaImage, imageProxy.imageInfo.rotationDegrees)

        scanner.process(image)
            .addOnSuccessListener { barcodes ->
                val first = barcodes.firstOrNull { it.rawValue?.isNotBlank() == true }
                if (first != null && !finished) {
                    finished = true
                    val formatStr = when (first.format) {
                        Barcode.FORMAT_QR_CODE -> "QR_CODE"
                        Barcode.FORMAT_DATA_MATRIX -> "DATA_MATRIX"
                        else -> "UNKNOWN"
                    }
                    val data = ScanResultBridge.success(
                        rawValue = first.rawValue!!,
                        formatName = formatStr
                    ).toIntent()
                    setResult(Activity.RESULT_OK, data)
                    AppLogger.log(TAG, "识别成功: ${first.rawValue} ($formatStr)")
                    cleanup()
                    finish()
                }
            }
            .addOnCompleteListener {
                // 无论成功失败，都在 complete 回调中关闭 imageProxy 并释放锁
                imageProxy.close()
                isProcessing.set(false)
            }
    }

    private fun cleanup() {
        mainHandler.removeCallbacks(timeoutTask)
        mainHandler.removeCallbacks(autoFocusTask)
    }

    private fun resolveMaxZoomRatio(): Float {
        val hardwareMax = camera?.cameraInfo?.zoomState?.value?.maxZoomRatio ?: scanConfig.manualMaxZoomRatio
        return hardwareMax.coerceAtLeast(1f)
    }

    override fun onDestroy() {
        super.onDestroy()
        cleanup()
        cameraExecutor?.shutdown()
        scanner.close()
    }
}
