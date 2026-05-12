package com.testcenter.qrscanner

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.RectF
import android.net.Uri
import android.os.Bundle
import android.util.AttributeSet
import android.view.Surface
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.exifinterface.media.ExifInterface
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.testcenter.qrscanner.adapter.PhotoThumbnailAdapter
import com.testcenter.qrscanner.databinding.ActivityPhotoCaptureBinding
import com.testcenter.qrscanner.network.FileManager
import com.testcenter.qrscanner.network.FileManagerFactory
import com.testcenter.qrscanner.repository.PhotoRepository
import com.testcenter.qrscanner.qc.QcService
import com.testcenter.qrscanner.qc.QcAnalyzeResponse
import com.testcenter.qrscanner.telemetry.ApkTelemetryManager
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.PreferencesManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.NonCancellable
import java.io.ByteArrayInputStream
import java.io.File
import java.text.SimpleDateFormat
import java.util.*
import kotlin.math.min

class PhotoCaptureActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPhotoCaptureBinding
    private lateinit var preferencesManager: PreferencesManager
    private lateinit var photoAdapter: PhotoThumbnailAdapter
    
    // 使用 REST API Repository 替代 SMB FileManager
    private val photoRepository by lazy { PhotoRepository(this) }
    private val qcService by lazy { QcService(this) }
    
    private var imageCapture: ImageCapture? = null
    private var productSerial: String = ""
    private var projectName: String = ""
    private var projectCode: String = ""
    private var productType: String = ""
    private var modelNumber: String = ""
    private var operatorName: String = ""
    private var processStepName: String? = null
    private var processIndex: Int = 0
    private var captureMode: CaptureMode = CaptureMode.MATERIAL

    // 上传成功的照片数量和 QC 结果（用于回传）
    private var uploadedCount = 0
    private var lastQcStatus: String? = null
    private var lastQcSummary: String? = null
    private var lastQcFindingsJson: String? = null

    private val photoItems = mutableListOf<PhotoItem>()
    private var photoCounter = 1  // 照片序号计数器，从1开始
    
    private val dateFormatFull = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
    private val dateFormatFile = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault())
    
    // 相机权限请求
    private val requestCameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            startCamera()
        } else {
            Toast.makeText(this, "需要相机权限才能拍照", Toast.LENGTH_LONG).show()
        }
    }
    
    // 选择多张照片
    private val selectPhotosLauncher = registerForActivityResult(
        ActivityResultContracts.GetMultipleContents()
    ) { uris: List<Uri> ->
        if (uris.isNotEmpty()) {
            lifecycleScope.launch {
                val newItems = uris.map { uri ->
                    async(Dispatchers.IO) { processPhotoUri(uri, PhotoSource.GALLERY) }
                }.awaitAll().filterNotNull()
                photoItems.addAll(newItems)
                updateAdapterData()
                AppLogger.log("PhotoCapture", "Selected ${uris.size} photos, total: ${photoItems.size}")
                Toast.makeText(this@PhotoCaptureActivity, "已选择 ${newItems.size} 张照片", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPhotoCaptureBinding.inflate(layoutInflater)
        setContentView(binding.root)
        binding.previewView.scaleType = androidx.camera.view.PreviewView.ScaleType.FIT_CENTER
        
        preferencesManager = PreferencesManager(this)
        
        // 读取上下文信息
        productSerial = intent.getStringExtra(EXTRA_PRODUCT_SERIAL) ?: ""
        projectName = intent.getStringExtra(EXTRA_PROJECT_NAME) ?: ""
        projectCode = intent.getStringExtra(EXTRA_PROJECT_CODE) ?: ""
        productType = intent.getStringExtra(EXTRA_PRODUCT_TYPE) ?: ""
        modelNumber = intent.getStringExtra(EXTRA_MODEL_NUMBER) ?: ""
        operatorName = intent.getStringExtra(EXTRA_OPERATOR_NAME)
            ?.takeIf { it.isNotBlank() }
            ?: preferencesManager.getUsername()
            ?: "未知"
        processStepName = intent.getStringExtra(EXTRA_PROCESS_STEP_NAME)
        processIndex = intent.getIntExtra(EXTRA_PROCESS_INDEX, 0)
        captureMode = intent.getSerializableExtra(EXTRA_CAPTURE_MODE) as? CaptureMode ?: CaptureMode.MATERIAL
        
        if (productSerial.isEmpty()) {
            Toast.makeText(this, "产品序列号为空", Toast.LENGTH_SHORT).show()
            finish()
            return
        }
        if (!ensureValidCaptureContext(finishOnFailure = true)) {
            return
        }
        
        binding.tvProductSerial.text = productSerial
        binding.tvProjectInfo.text = buildString {
            append("项目：")
            append(projectName.ifEmpty { "未设置" })
            if (projectCode.isNotEmpty()) {
                append(" (" + projectCode + ")")
            }
        }
        binding.tvProductTypeInfo.text = buildString {
            append("产品：")
            append(productType.ifEmpty { "未设置" })
            if (modelNumber.isNotEmpty()) {
                append(" (" + modelNumber + ")")
            }
        }
        binding.tvOperatorInfo.text = "操作人：$operatorName"
        binding.tvProcessInfo.apply {
            visibility = if (captureMode == CaptureMode.PROCESS && !processStepName.isNullOrEmpty()) View.VISIBLE else View.GONE
            text = "工序：${processStepName ?: "未设置"}"
        }
        
        // 设置工具栏
        binding.toolbar.setNavigationOnClickListener {
            if (!binding.btnUpload.isEnabled) {
                Toast.makeText(this, "照片上传中，请等待完成", Toast.LENGTH_SHORT).show()
                return@setNavigationOnClickListener
            }
            finish()
        }
        
        // 设置照片列表
        setupPhotoList()
        
        // 请求相机权限并启动相机
        if (checkCameraPermission()) {
            startCamera()
        } else {
            requestCameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
        
        // 拍照按钮
        binding.btnCapture.setOnClickListener {
            takePhoto()
        }
        
        // 选择照片按钮
        binding.btnSelectPhotos.setOnClickListener {
            selectPhotosLauncher.launch("image/*")
        }
        
        binding.btnUpload.setOnClickListener {
            uploadPhotos()
        }
    }
    
    private fun setupPhotoList() {
        photoAdapter = PhotoThumbnailAdapter(mutableListOf()) { position ->
            // 上传中禁止删除，避免并发上传时临时文件被提前清理导致部分失败
            if (!binding.btnUpload.isEnabled) {
                Toast.makeText(this@PhotoCaptureActivity, "照片上传中，暂不可删除", Toast.LENGTH_SHORT).show()
                return@PhotoThumbnailAdapter
            }
            // 删除照片
            if (position in photoItems.indices) {
                val removed = photoItems.removeAt(position)
                removed.deleteTempFiles()
                AppLogger.log("PhotoCapture", "Removed photo at position $position")
                updateAdapterData()
            }
        }
        binding.recyclerViewPhotos.apply {
            layoutManager = LinearLayoutManager(this@PhotoCaptureActivity, LinearLayoutManager.HORIZONTAL, false)
            adapter = photoAdapter
        }
    }
    
    private fun checkCameraPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED
    }
    
    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        
        cameraProviderFuture.addListener({
            val cameraProvider: ProcessCameraProvider = cameraProviderFuture.get()
            val targetRotation = binding.previewView.display?.rotation ?: Surface.ROTATION_0
            
            // 预览
            val preview = Preview.Builder()
                .setTargetRotation(targetRotation)
                .build()
                .also {
                    it.setSurfaceProvider(binding.previewView.surfaceProvider)
                }
            
            // 拍照
            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
                .setTargetRotation(targetRotation)
                .build()
            
            // 选择后置摄像头
            val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA
            
            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(
                    this, cameraSelector, preview, imageCapture
                )
            } catch (exc: Exception) {
                AppLogger.log("PhotoCapture", "Camera binding failed", exc)
                Toast.makeText(this, "相机启动失败", Toast.LENGTH_SHORT).show()
            }
            
        }, ContextCompat.getMainExecutor(this))
    }
    
    private fun takePhoto() {
        if (!ensureValidCaptureContext()) {
            return
        }
        val imageCapture = imageCapture ?: return
        val latestRotation = binding.previewView.display?.rotation ?: Surface.ROTATION_0
        imageCapture.targetRotation = latestRotation
        
        val timestamp = System.currentTimeMillis()
        val rawFile = File(externalCacheDir, "RAW_${timestamp}.jpg")
        val outputOptions = ImageCapture.OutputFileOptions.Builder(rawFile).build()
        
        imageCapture.takePicture(
            outputOptions,
            ContextCompat.getMainExecutor(this),
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    lifecycleScope.launch {
                        val item = processPhotoUri(Uri.fromFile(rawFile), PhotoSource.CAMERA)
                        if (item != null) {
                            photoItems.add(item)
                            updateAdapterData()
                            Toast.makeText(this@PhotoCaptureActivity, "拍照成功", Toast.LENGTH_SHORT).show()
                        } else {
                            rawFile.delete()
                            Toast.makeText(this@PhotoCaptureActivity, "处理照片失败", Toast.LENGTH_SHORT).show()
                        }
                    }
                }
                
                override fun onError(exc: ImageCaptureException) {
                    AppLogger.log("PhotoCapture", "Photo capture failed", exc)
                    Toast.makeText(this@PhotoCaptureActivity, "拍照失败: ${exc.message}", Toast.LENGTH_SHORT).show()
                }
            }
        )
    }

    private fun uploadPhotos() {
        if (!ensureValidCaptureContext()) {
            return
        }
        if (photoItems.isEmpty()) {
            Toast.makeText(this, "请先选择或拍摄照片", Toast.LENGTH_SHORT).show()
            return
        }

        binding.btnUpload.isEnabled = false
        binding.btnUpload.text = "上传中..."

        val uploadBatch = photoItems.toList()
        val totalCount = uploadBatch.size

        lifecycleScope.launch {
            try {
                val username = preferencesManager.getUsername() ?: ""
                val password = preferencesManager.getPassword() ?: ""

                var successCount = 0
                var failCount = 0
                val uploadedPhotoBytes = mutableListOf<ByteArray>()

                // 并行上传所有照片（最多 3 个并发）
                val semaphore = kotlinx.coroutines.sync.Semaphore(3)
                val uploadCount = java.util.concurrent.atomic.AtomicInteger(0)
                val results = uploadBatch.map { item ->
                    async(Dispatchers.IO) {
                        semaphore.acquire()
                        val result: Pair<Boolean, ByteArray?>
                        try {
                            val fileManager = FileManagerFactory.create(this@PhotoCaptureActivity, username, password)
                            var attempt = 0
                            var lastResult: Pair<Boolean, ByteArray?> = false to null
                            while (attempt < 3) {
                                attempt++
                                try {
                                    lastResult = uploadSinglePhoto(fileManager, item)
                                } catch (e: Exception) {
                                    if (e is kotlinx.coroutines.CancellationException) {
                                        throw e
                                    }
                                    AppLogger.log("PhotoCapture", "Single photo upload failed on attempt $attempt", e)
                                    lastResult = false to null
                                }
                                if (lastResult.first) {
                                    break
                                }
                                if (attempt < 3) {
                                    kotlinx.coroutines.delay(500L * attempt)
                                }
                            }
                            result = lastResult
                        } finally {
                            semaphore.release()
                        }
                        val count = uploadCount.incrementAndGet()
                        withContext(Dispatchers.Main) {
                            binding.btnUpload.text = "上传中 $count/$totalCount"
                        }
                        result
                    }
                }.awaitAll()

                for ((success, bytes) in results) {
                    if (success) {
                        successCount++
                        if (bytes != null) uploadedPhotoBytes.add(bytes)
                    } else {
                        failCount++
                    }
                }

                withContext(Dispatchers.Main) {
                    if (successCount > 0 && failCount == 0) {
                        uploadedCount = successCount
                        // 全部上传成功，进行 QC 分析
                        if (captureMode == CaptureMode.PROCESS && !processStepName.isNullOrEmpty()) {
                            performQcAnalysis(uploadedPhotoBytes)
                        } else {
                            binding.btnUpload.isEnabled = true
                            binding.btnUpload.text = "上传照片"
                            Toast.makeText(this@PhotoCaptureActivity, "成功上传 $successCount 张照片", Toast.LENGTH_LONG).show()
                            finishWithResult()
                        }
                    } else {
                        binding.btnUpload.isEnabled = true
                        binding.btnUpload.text = "上传照片"
                        ApkTelemetryManager.captureUploadFailure(
                            this@PhotoCaptureActivity,
                            trigger = "photo_capture_batch_upload",
                            feature = "photo_upload",
                            summary = "照片上传存在失败记录",
                            reasonCode = if (successCount > 0) "partial_failure" else "all_failed",
                            extras = mapOf(
                                "productSerial" to productSerial,
                                "projectName" to projectName,
                                "productType" to productType,
                                "processStep" to processStepName,
                                "successCount" to successCount,
                                "failCount" to failCount,
                                "totalCount" to totalCount,
                            ),
                        )
                        if (successCount > 0) {
                            Toast.makeText(this@PhotoCaptureActivity, "成功上传 $successCount 张，失败 $failCount 张", Toast.LENGTH_LONG).show()
                        } else {
                            Toast.makeText(this@PhotoCaptureActivity, "上传失败", Toast.LENGTH_LONG).show()
                        }
                    }
                }
            } catch (e: kotlinx.coroutines.CancellationException) {
                AppLogger.log("PhotoCapture", "Upload cancelled", e)
                withContext(NonCancellable + Dispatchers.Main) {
                    binding.btnUpload.isEnabled = true
                    binding.btnUpload.text = "上传照片"
                }
                return@launch
            } catch (e: Exception) {
                val isJobCancellation = generateSequence<Throwable>(e) { it.cause }
                    .any {
                        it is kotlinx.coroutines.CancellationException ||
                            it.javaClass.name == "kotlinx.coroutines.JobCancellationException" ||
                            it.javaClass.simpleName == "JobCancellationException" ||
                            it.message?.contains("Job was cancelled", ignoreCase = true) == true
                    }
                if (e is kotlinx.coroutines.CancellationException || isJobCancellation) {
                    AppLogger.log("PhotoCapture", "Upload cancelled", e)
                    withContext(NonCancellable + Dispatchers.Main) {
                        binding.btnUpload.isEnabled = true
                        binding.btnUpload.text = "上传照片"
                    }
                    return@launch
                }
                AppLogger.log("PhotoCapture", "Upload failed", e)
                ApkTelemetryManager.captureUploadFailure(
                    this@PhotoCaptureActivity,
                    trigger = "photo_capture_batch_upload_exception",
                    feature = "photo_upload",
                    summary = "照片批量上传异常",
                    throwable = e,
                    extras = mapOf(
                        "productSerial" to productSerial,
                        "projectName" to projectName,
                        "productType" to productType,
                        "processStep" to processStepName,
                        "totalCount" to totalCount,
                    ),
                )
                withContext(Dispatchers.Main) {
                    binding.btnUpload.isEnabled = true
                    binding.btnUpload.text = "上传照片"
                    Toast.makeText(this@PhotoCaptureActivity, buildUploadFailureMessage(e), Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    /**
     * 上传成功后进行 QC 分析
     */
    private fun performQcAnalysis(photoBytesList: List<ByteArray>) {
        binding.btnUpload.text = "QC 识别中..."
        binding.btnUpload.isEnabled = false

        lifecycleScope.launch {
            try {
                val qcPolicy = qcService.getQcPolicy(projectName)
                if (!qcPolicy.qcEnabled || !qcPolicy.realtimeQcEnabled) {
                    // QC 未启用，直接完成
                    AppLogger.log("PhotoCapture", "[QC] 实时 QC 未启用，跳过分析")
                    // 即使策略关闭，也回传明确状态，避免上层收到 null
                    lastQcStatus = "skipped"
                    lastQcSummary = "项目未启用实时QC"
                    binding.btnUpload.isEnabled = true
                    binding.btnUpload.text = "上传照片"
                    Toast.makeText(this@PhotoCaptureActivity, "上传成功", Toast.LENGTH_SHORT).show()
                    finishWithResult()
                    return@launch
                }

                val result = qcService.analyzePhotos(
                    photoBytesList = photoBytesList,
                    productSerial = productSerial,
                    processName = processStepName ?: "",
                    processIndex = processIndex,
                    projectName = projectName,
                    productType = productType
                )

                // 记录 QC 结果用于回传
                lastQcStatus = result.status
                lastQcSummary = result.summary
                if (result.findings.isNotEmpty()) {
                    lastQcFindingsJson = com.google.gson.Gson().toJson(result.findings)
                }

                withContext(Dispatchers.Main) {
                    binding.btnUpload.isEnabled = true
                    binding.btnUpload.text = "上传照片"
                    showQcResultDialog(result)
                }
            } catch (e: Exception) {
                AppLogger.log("PhotoCapture", "[QC] 分析异常: ${e.message}", e)
                withContext(Dispatchers.Main) {
                    binding.btnUpload.isEnabled = true
                    binding.btnUpload.text = "上传照片"
                    android.app.AlertDialog.Builder(this@PhotoCaptureActivity)
                        .setTitle("QC 分析失败")
                        .setMessage("照片已上传成功，但 QC 分析失败：${e.message}")
                        .setPositiveButton("返回") { dialog, _ ->
                            dialog.dismiss()
                            finishWithResult()
                        }
                        .setCancelable(false)
                        .show()
                }
            }
        }
    }

    /**
     * 显示 QC 分析结果对话框
     */
    private fun showQcResultDialog(result: QcAnalyzeResponse) {
        val (title, icon) = when (result.status) {
            "pass" -> "QC 通过" to android.R.drawable.ic_dialog_info
            "fail" -> "QC 未通过" to android.R.drawable.ic_dialog_alert
            else -> "需人工复核" to android.R.drawable.ic_dialog_alert
        }

        val message = buildString {
            append(result.summary)
            if (result.findings.isNotEmpty()) {
                append("\n\n发现问题：")
                result.findings.forEach { finding ->
                    val severityLabel = when (finding.severity) {
                        "critical" -> "[严重]"
                        "major" -> "[主要]"
                        else -> "[轻微]"
                    }
                    append("\n$severityLabel ${finding.description}")
                }
            }
            if (result.confidence > 0) {
                append("\n\n置信度：${(result.confidence * 100).toInt()}%")
            }
        }

        val builder = android.app.AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage(message)
            .setIcon(icon)
            .setCancelable(false)

        when (result.status) {
            "pass" -> {
                builder.setPositiveButton("确定") { dialog, _ ->
                    dialog.dismiss()
                    finishWithResult()
                }
            }
            "fail" -> {
                builder.setPositiveButton("重新拍照") { dialog, _ ->
                    dialog.dismiss()
                    // 清空已拍照片，重新拍
                    photoItems.forEach { it.deleteTempFiles() }
                    photoItems.clear()
                    updateAdapterData()
                }
                builder.setNegativeButton("忽略并返回") { dialog, _ ->
                    dialog.dismiss()
                    finishWithResult()
                }
            }
            else -> { // ng
                builder.setPositiveButton("接受并返回") { dialog, _ ->
                    dialog.dismiss()
                    finishWithResult()
                }
                builder.setNegativeButton("重新拍照") { dialog, _ ->
                    dialog.dismiss()
                    photoItems.forEach { it.deleteTempFiles() }
                    photoItems.clear()
                    updateAdapterData()
                }
            }
        }

        builder.show()
    }

    /**
     * 上传单张照片，返回 (是否成功, 照片字节)。
     * 上传成功后临时文件会被删除，所以必须在此处保留 bytes 返回给调用方用于 QC 分析。
     */
    private suspend fun uploadSinglePhoto(
        fileManager: FileManager,
        item: PhotoItem
    ): Pair<Boolean, ByteArray?> {
        return withContext(Dispatchers.IO) {
            try {
                val photoBytes = item.readBytes()
                if (photoBytes.isEmpty()) {
                    AppLogger.log("PhotoCapture", "Photo bytes empty for ${item.fileName}")
                    return@withContext Pair(false, null)
                }

                // 优先使用 REST API
                val apiResult = photoRepository.uploadPhoto(
                    photoBytes = photoBytes,
                    fileName = item.fileName,
                    productSerial = productSerial,
                    projectName = projectName,
                    productType = productType,
                    processName = processStepName,
                    operator = operatorName,
                    projectCode = projectCode,
                    modelNumber = modelNumber
                )

                apiResult.fold(
                    onSuccess = { filename ->
                        AppLogger.log("PhotoCapture", "Successfully uploaded photo via REST API: $filename")
                        item.deleteTempFiles()
                        return@withContext Pair(true, photoBytes)
                    },
                    onFailure = { e ->
                        AppLogger.log("PhotoCapture", "REST API upload failed, trying FileManager: ${e.message}")
                    }
                )

                // 降级到 FileManager (SMB)
                val directoryInfo = FileManager.PhotoDirectoryInfo(
                    projectName = projectName,
                    projectCode = projectCode,
                    productType = productType,
                    modelNumber = modelNumber,
                    productSerial = productSerial
                )

                val result = fileManager.uploadPhoto(directoryInfo, item.fileName, photoBytes)
                if (result) {
                    AppLogger.log("PhotoCapture", "Successfully uploaded photo via FileManager: ${item.fileName}")
                    val metadataResult = photoRepository.recordPhotoMetadata(
                        productSerial = productSerial,
                        processName = processStepName,
                        fileName = item.fileName,
                        fileSize = photoBytes.size.toLong(),
                        operator = operatorName
                    )
                    metadataResult.onSuccess {
                        AppLogger.log("PhotoCapture", "Backfilled photo metadata after FileManager upload: ${item.fileName}")
                    }.onFailure { metadataError ->
                        AppLogger.log("PhotoCapture", "Failed to backfill metadata after FileManager upload: ${metadataError.message}")
                    }
                    item.deleteTempFiles()
                } else {
                    AppLogger.log("PhotoCapture", "Failed to upload photo: ${item.fileName}")
                }
                Pair(result, if (result) photoBytes else null)
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                AppLogger.log("PhotoCapture", "Error uploading photo", e)
                Pair(false, null)
            }
        }
    }



    private fun buildUploadFailureMessage(error: Throwable?): String {
        return when (error) {
            is java.net.SocketTimeoutException -> "上传失败：网络超时，请稍后重试"
            is java.net.UnknownHostException -> "上传失败：无法连接服务器，请检查网络"
            is java.io.IOException -> "上传失败：网络异常，请确认 MES 服务可用"
            else -> {
                val raw = error?.message?.trim().orEmpty()
                if (raw.isNotEmpty()) "上传失败：$raw" else "上传失败，请稍后重试"
            }
        }
    }

    /**
     * 带结果回传的 finish
     */
    private fun finishWithResult() {
        val data = Intent().apply {
            putExtra(RESULT_EXTRA_PHOTO_COUNT, uploadedCount)
            putExtra(RESULT_EXTRA_PROCESS_STEP_NAME, processStepName)
            lastQcStatus?.let { putExtra(RESULT_EXTRA_QC_STATUS, it) }
            lastQcSummary?.let { putExtra(RESULT_EXTRA_QC_SUMMARY, it) }
            lastQcFindingsJson?.let { putExtra(RESULT_EXTRA_QC_FINDINGS, it) }
        }
        setResult(RESULT_OK, data)
        finish()
    }

    companion object {
        const val EXTRA_PRODUCT_SERIAL = "extra_product_serial"
        const val EXTRA_PROJECT_NAME = "extra_project_name"
        const val EXTRA_PROJECT_CODE = "extra_project_code"
        const val EXTRA_PRODUCT_TYPE = "extra_product_type"
        const val EXTRA_MODEL_NUMBER = "extra_model_number"
        const val EXTRA_OPERATOR_NAME = "extra_operator_name"
        const val EXTRA_PROCESS_STEP_NAME = "extra_process_step_name"
        const val EXTRA_PROCESS_INDEX = "extra_process_index"
        const val EXTRA_CAPTURE_MODE = "extra_capture_mode"

        // 结果回传
        const val RESULT_EXTRA_PHOTO_COUNT = "result_photo_count"
        const val RESULT_EXTRA_QC_STATUS = "result_qc_status"
        const val RESULT_EXTRA_QC_SUMMARY = "result_qc_summary"
        const val RESULT_EXTRA_QC_FINDINGS = "result_qc_findings"
        const val RESULT_EXTRA_PROCESS_STEP_NAME = "result_process_step_name"
    }

    enum class CaptureMode {
        MATERIAL,
        PROCESS
    }

    private enum class PhotoSource {
        CAMERA,
        GALLERY
    }

    private class PhotoItem(
        val originalFile: File?,
        val processedFile: File,
        val previewUri: Uri,
        val fileName: String
    ) {
        /** 按需从文件读取字节，避免常驻内存 */
        fun readBytes(): ByteArray = processedFile.readBytes()

        fun deleteTempFiles() {
            originalFile?.delete()
            processedFile.delete()
        }
    }

    private suspend fun processPhotoUri(uri: Uri, source: PhotoSource): PhotoItem? {
        return withContext(Dispatchers.IO) {
            var rawBitmap: Bitmap? = null
            var processedBitmap: Bitmap? = null
            try {
                val captureDate = Date()
                // 一次性读取字节，避免打开两次 InputStream
                val rawBytes = contentResolver.openInputStream(uri)?.use { it.readBytes() }
                    ?: return@withContext null

                // 先读取尺寸，按需降采样避免 OOM
                val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(rawBytes, 0, rawBytes.size, options)
                val maxDimension = 2048
                var sampleSize = 1
                while (options.outWidth / sampleSize > maxDimension || options.outHeight / sampleSize > maxDimension) {
                    sampleSize *= 2
                }
                val decodeOptions = BitmapFactory.Options().apply { inSampleSize = sampleSize }
                rawBitmap = BitmapFactory.decodeByteArray(rawBytes, 0, rawBytes.size, decodeOptions)
                    ?: return@withContext null
                rawBitmap = rotateBitmapIfRequired(rawBitmap, uri, rawBytes)

                processedBitmap = addFooterOverlay(rawBitmap, captureDate)
                // 直接压缩写入文件，避免 ByteArrayOutputStream 中转
                val processedFile = File(externalCacheDir, "PROCESSED_${System.currentTimeMillis()}.jpg")
                processedFile.outputStream().use { fos ->
                    processedBitmap.compress(Bitmap.CompressFormat.JPEG, 90, fos)
                    fos.flush()
                }

                rawBitmap.recycle()
                processedBitmap.recycle()

                val fileName = generateFileName(captureDate)
                val previewUri = Uri.fromFile(processedFile)
                val originalFile = if (source == PhotoSource.CAMERA) File(uri.path!!) else null
                PhotoItem(originalFile, processedFile, previewUri, fileName)
            } catch (e: Exception) {
                rawBitmap?.recycle()
                processedBitmap?.recycle()
                AppLogger.log("PhotoCapture", "Failed to process photo uri: $uri", e)
                null
            }
        }
    }

    private fun addFooterOverlay(original: Bitmap, captureDate: Date): Bitmap {
        val footerHeight = (original.height * 0.22f).toInt().coerceAtLeast(220)
        val resultBitmap = Bitmap.createBitmap(
            original.width,
            original.height + footerHeight,
            Bitmap.Config.RGB_565  // 照片不需要透明通道，节省 50% 内存
        )
        val canvas = Canvas(resultBitmap)
        canvas.drawBitmap(original, 0f, 0f, null)

        val footerPaint = Paint().apply {
            color = Color.parseColor("#CC000000")
        }
        canvas.drawRect(
            0f,
            original.height.toFloat(),
            original.width.toFloat(),
            (original.height + footerHeight).toFloat(),
            footerPaint
        )

        val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
        }

        val lines = buildList {
            add("项目：${projectName.ifEmpty { "未设置" }}")
            add("项目号：${projectCode.ifEmpty { "未设置" }}")
            add("产品类型：${productType.ifEmpty { "未设置" }}")
            add("产品型号：${modelNumber.ifEmpty { "未设置" }}")
            add("产品序列号：$productSerial")
            add("工序：${processStepName ?: if (captureMode == CaptureMode.MATERIAL) "物料记录" else "未设置"}")
            add("操作人：$operatorName")
            add("日期：${dateFormatFull.format(captureDate)}")
        }

        val columns = 2
        val horizontalMargin = original.width * 0.05f
        val contentWidth = original.width.toFloat() - horizontalMargin * 2f
        val columnWidth = contentWidth / columns

        var textSize = (footerHeight / 3.2f).toFloat().coerceIn(40f, 72f)
        textPaint.textSize = textSize

        if (lines.isNotEmpty()) {
            var maxLineWidth = lines.maxOf { line -> textPaint.measureText(line) }
            while (maxLineWidth > columnWidth && textSize > 28f) {
                textSize -= 2f
                textPaint.textSize = textSize
                maxLineWidth = lines.maxOf { line -> textPaint.measureText(line) }
            }
        }

        val rowsPerColumn = Math.ceil(lines.size / columns.toDouble()).toInt()
        var lineSpacing = textPaint.textSize * 1.25f
        var totalTextHeight = rowsPerColumn * lineSpacing

        while (totalTextHeight > footerHeight * 0.9f && textSize > 28f) {
            textSize -= 2f
            textPaint.textSize = textSize
            lineSpacing = textPaint.textSize * 1.3f
            totalTextHeight = rowsPerColumn * lineSpacing
        }

        val baseY = original.height + (footerHeight - totalTextHeight) / 2f + textPaint.textSize

        for (columnIndex in 0 until columns) {
            val startIndex = columnIndex * rowsPerColumn
            if (startIndex >= lines.size) break
            val endIndex = Math.min(startIndex + rowsPerColumn, lines.size)

            val startX = horizontalMargin + columnIndex * columnWidth
            var currentY = baseY

            for (i in startIndex until endIndex) {
                canvas.drawText(lines[i], startX, currentY, textPaint)
                currentY += lineSpacing
            }
        }

        return resultBitmap
    }

    private fun rotateBitmapIfRequired(bitmap: Bitmap, uri: Uri, rawBytes: ByteArray): Bitmap {
        val rotation = readRotationDegrees(uri, rawBytes)
        if (rotation == 0f) {
            return bitmap
        }

        return try {
            val matrix = Matrix().apply { postRotate(rotation) }
            val rotated = Bitmap.createBitmap(
                bitmap,
                0,
                0,
                bitmap.width,
                bitmap.height,
                matrix,
                true
            )
            if (rotated != bitmap) {
                bitmap.recycle()
            }
            rotated
        } catch (e: Exception) {
            AppLogger.log("PhotoCapture", "旋转照片失败: ${e.message}", e)
            bitmap
        }
    }

    private fun readRotationDegrees(uri: Uri, rawBytes: ByteArray): Float {
        val orientation = try {
            contentResolver.openInputStream(uri)?.use { input ->
                ExifInterface(input).getAttributeInt(
                    ExifInterface.TAG_ORIENTATION,
                    ExifInterface.ORIENTATION_NORMAL
                )
            } ?: ExifInterface.ORIENTATION_NORMAL
        } catch (e: Exception) {
            try {
                ByteArrayInputStream(rawBytes).use { input ->
                    ExifInterface(input).getAttributeInt(
                        ExifInterface.TAG_ORIENTATION,
                        ExifInterface.ORIENTATION_NORMAL
                    )
                }
            } catch (_: Exception) {
                ExifInterface.ORIENTATION_NORMAL
            }
        }

        return when (orientation) {
            ExifInterface.ORIENTATION_ROTATE_90 -> 90f
            ExifInterface.ORIENTATION_ROTATE_180 -> 180f
            ExifInterface.ORIENTATION_ROTATE_270 -> 270f
            else -> 0f
        }
    }

    private fun generateFileName(captureDate: Date): String {
        val safeStep = sanitizeFileName(processStepName ?: "")
        val datePart = dateFormatFile.format(captureDate)
        val sequenceNumber = String.format("%03d", photoCounter)  // 三位数序号，例如：001, 002, 003
        photoCounter++  // 递增计数器

        if (captureMode == CaptureMode.PROCESS && safeStep.isEmpty()) {
            throw IllegalStateException("Process capture requires processStepName")
        }
        
        return if (captureMode == CaptureMode.PROCESS) {
            "${sanitizeFileName(productSerial)}_${if (safeStep.isNotEmpty()) safeStep + "_" else ""}${datePart}_$sequenceNumber.jpg"
        } else {
            "${sanitizeFileName(productSerial)}_${datePart}_$sequenceNumber.jpg"
        }
    }

    private fun sanitizeFileName(input: String): String {
        if (input.isEmpty()) return ""
        return input.replace("[^\\p{L}\\p{N}_-]".toRegex(), "_")
    }

    private fun ensureValidCaptureContext(finishOnFailure: Boolean = false): Boolean {
        if (captureMode != CaptureMode.PROCESS || !processStepName.isNullOrBlank()) {
            return true
        }

        AppLogger.log(
            "PhotoCapture",
            "Blocked process capture without process step name for product: $productSerial"
        )
        Toast.makeText(this, "工序拍照缺少工序信息，请返回工序页重新进入", Toast.LENGTH_LONG).show()
        if (finishOnFailure) {
            finish()
        }
        return false
    }

    private fun updateAdapterData() {
        photoAdapter.updateData(photoItems.map { it.previewUri })
    }
}

/**
 * Camera preview overlay that draws a guide frame for operators.
 * Keep this class in a tracked file to avoid missing class issues during clean builds.
 */
class CameraGuideOverlayView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private val maskPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#66000000")
        style = Paint.Style.FILL
    }

    private val framePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#33B5E5")
        style = Paint.Style.STROKE
        strokeWidth = context.resources.displayMetrics.density * 2f
    }

    private val cornerPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#00E676")
        style = Paint.Style.STROKE
        strokeWidth = context.resources.displayMetrics.density * 4f
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (width <= 0 || height <= 0) return

        val isPortrait = height >= width
        val targetRatio = if (isPortrait) 3f / 4f else 4f / 3f
        val maxWidth = width * 0.9f
        val maxHeight = height * 0.8f

        var frameWidth = maxWidth
        var frameHeight = frameWidth / targetRatio
        if (frameHeight > maxHeight) {
            frameHeight = maxHeight
            frameWidth = frameHeight * targetRatio
        }

        val left = (width - frameWidth) / 2f
        val top = (height - frameHeight) / 2f
        val right = left + frameWidth
        val bottom = top + frameHeight
        val frame = RectF(left, top, right, bottom)

        canvas.drawRect(0f, 0f, width.toFloat(), top, maskPaint)
        canvas.drawRect(0f, bottom, width.toFloat(), height.toFloat(), maskPaint)
        canvas.drawRect(0f, top, left, bottom, maskPaint)
        canvas.drawRect(right, top, width.toFloat(), bottom, maskPaint)

        canvas.drawRoundRect(frame, 12f, 12f, framePaint)

        val corner = min(frameWidth, frameHeight) * 0.08f
        drawCorner(canvas, left, top, corner, true, true)
        drawCorner(canvas, right, top, corner, false, true)
        drawCorner(canvas, left, bottom, corner, true, false)
        drawCorner(canvas, right, bottom, corner, false, false)
    }

    private fun drawCorner(
        canvas: Canvas,
        x: Float,
        y: Float,
        len: Float,
        left: Boolean,
        top: Boolean
    ) {
        val hx = if (left) x + len else x - len
        val vy = if (top) y + len else y - len
        canvas.drawLine(x, y, hx, y, cornerPaint)
        canvas.drawLine(x, y, x, vy, cornerPaint)
    }
}
