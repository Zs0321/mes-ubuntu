package com.testcenter.qrscanner

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.core.view.setPadding
import androidx.core.widget.doAfterTextChanged
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanIntentResult
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.api.MaterialInboundRecordRequest
import com.testcenter.qrscanner.api.MaterialInboundResolveResponse
import com.testcenter.qrscanner.databinding.ActivityMaterialInboundBinding
import com.testcenter.qrscanner.scanner.EnhancedQRScanner
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File

class MaterialInboundActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMaterialInboundBinding
    private lateinit var enhancedQRScanner: EnhancedQRScanner
    private val apiService by lazy { ApiClient.getApiService(this) }

    private var currentResolveResponse: MaterialInboundResolveResponse? = null
    private var currentMaterialSerial: String? = null
    private var pendingCameraAction: CameraAction = CameraAction.SCAN
    private var pendingPhotoType: PhotoType? = null
    private var pendingPhotoFile: File? = null
    private val capturedPhotos = mutableListOf<CapturedPhoto>()

    private enum class CameraAction {
        SCAN,
        CAPTURE,
    }

    private enum class PhotoType(val requestValue: String, val label: String) {
        DELIVERY("delivery", "\u9001\u8d27\u5355\u7167\u7247"),
        MATERIAL("material", "\u7269\u6599\u7167\u7247"),
    }

    private data class CapturedPhoto(
        val type: PhotoType,
        val file: File,
        val uri: Uri,
    )

    private val barcodeLauncher = registerForActivityResult(ScanContract()) { result: ScanIntentResult ->
        val serial = result.contents?.trim().orEmpty()
        if (serial.isEmpty()) {
            Toast.makeText(this, "\u672a\u8bc6\u522b\u5230\u7269\u6599\u4e8c\u7ef4\u7801", Toast.LENGTH_SHORT).show()
            return@registerForActivityResult
        }
        binding.tvScanResult.text = serial
        resolveMaterial(serial)
    }

    private val requestCameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (!granted) {
            Toast.makeText(this, "\u9700\u8981\u76f8\u673a\u6743\u9650\u624d\u80fd\u626b\u7801\u548c\u62cd\u7167", Toast.LENGTH_SHORT).show()
            return@registerForActivityResult
        }
        proceedWithCameraAction()
    }

    private val takePictureLauncher = registerForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        val photoType = pendingPhotoType
        val photoFile = pendingPhotoFile
        pendingPhotoType = null
        pendingPhotoFile = null
        if (!success || photoType == null || photoFile == null || !photoFile.exists()) {
            photoFile?.delete()
            Toast.makeText(this, "\u62cd\u7167\u53d6\u6d88\u6216\u5931\u8d25", Toast.LENGTH_SHORT).show()
            return@registerForActivityResult
        }
        capturedPhotos.add(CapturedPhoto(photoType, photoFile, Uri.fromFile(photoFile)))
        updatePhotoSummary()
        Toast.makeText(this, "\u5df2\u6dfb\u52a0${photoType.label}", Toast.LENGTH_SHORT).show()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        androidx.appcompat.app.AppCompatDelegate.setDefaultNightMode(
            androidx.appcompat.app.AppCompatDelegate.MODE_NIGHT_NO
        )
        binding = ActivityMaterialInboundBinding.inflate(layoutInflater)
        setContentView(binding.root)
        enhancedQRScanner = EnhancedQRScanner(this)
        setupToolbar()
        setupActions()
        renderIdleState(clearScanText = true)
    }

    private fun setupToolbar() {
        setSupportActionBar(binding.toolbar)
        supportActionBar?.apply {
            title = "\u7269\u6599\u5165\u5e93"
            setDisplayHomeAsUpEnabled(true)
        }
        binding.toolbar.setNavigationOnClickListener { finish() }
    }

    private fun setupActions() {
        binding.etInboundQuantity.doAfterTextChanged {
            binding.tilInboundQuantity.error = null
            updatePhotoSummary()
        }
        binding.btnScanMaterial.setOnClickListener {
            pendingCameraAction = CameraAction.SCAN
            ensureCameraPermissionOrProceed()
        }
        binding.btnRescanMaterial.setOnClickListener {
            renderIdleState(clearScanText = true)
        }
        binding.btnCapturePhoto.setOnClickListener {
            if (!hasResolvedMaterial()) {
                Toast.makeText(this, "\u8bf7\u5148\u626b\u7801\u8bc6\u522b\u7269\u6599", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            showPhotoTypePicker()
        }
        binding.btnClearPhotos.setOnClickListener {
            clearCapturedPhotos(deleteFiles = true)
            updatePhotoSummary()
        }
        binding.btnUploadPhotos.setOnClickListener {
            uploadPhotos()
        }
    }

    private fun renderIdleState(clearScanText: Boolean) {
        currentResolveResponse = null
        currentMaterialSerial = null
        binding.progressBar.visibility = View.GONE
        binding.cardMaterialInfo.visibility = View.GONE
        binding.cardPhotoSection.visibility = View.GONE
        binding.tvResolveStatus.text = "\u8bf7\u5148\u626b\u7801\u8bc6\u522b\u7269\u6599\u4e8c\u7ef4\u7801"
        binding.tvMaterialCode.text = "-"
        binding.tvMaterialName.text = "-"
        binding.etInboundQuantity.setText("")
        binding.tilInboundQuantity.error = null
        if (clearScanText) {
            binding.tvScanResult.text = "\u7b49\u5f85\u626b\u7801"
        }
        clearCapturedPhotos(deleteFiles = true)
        updatePhotoSummary()
    }

    private fun hasResolvedMaterial(): Boolean {
        return !displayMaterialCode().isNullOrBlank() && !displayMaterialName().isNullOrBlank()
    }

    private fun enteredQuantity(): String? {
        val value = binding.etInboundQuantity.text?.toString()?.trim().orEmpty()
        return value.takeIf { it.isNotEmpty() }
    }

    private fun hasValidQuantity(): Boolean {
        return !enteredQuantity().isNullOrBlank()
    }

    private fun ensureCameraPermissionOrProceed() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            proceedWithCameraAction()
        } else {
            requestCameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun proceedWithCameraAction() {
        when (pendingCameraAction) {
            CameraAction.SCAN -> startScanner()
            CameraAction.CAPTURE -> startTakePicture()
        }
    }

    private fun startScanner() {
        barcodeLauncher.launch(enhancedQRScanner.createEnhancedScanOptions("\u7269\u6599\u5165\u5e93\u626b\u7801"))
    }

    private fun showPhotoTypePicker() {
        val labels = arrayOf(PhotoType.DELIVERY.label, PhotoType.MATERIAL.label)
        MaterialAlertDialogBuilder(this)
            .setTitle("\u9009\u62e9\u7167\u7247\u7c7b\u578b")
            .setItems(labels) { _, which ->
                pendingPhotoType = if (which == 0) PhotoType.DELIVERY else PhotoType.MATERIAL
                pendingCameraAction = CameraAction.CAPTURE
                ensureCameraPermissionOrProceed()
            }
            .setNegativeButton("\u53d6\u6d88", null)
            .show()
    }

    private fun startTakePicture() {
        val photoType = pendingPhotoType ?: return
        val captureDir = File(externalCacheDir ?: cacheDir, "material_inbound_capture").apply { mkdirs() }
        val file = File(captureDir, "${photoType.requestValue}_${System.currentTimeMillis()}.jpg")
        val uri = FileProvider.getUriForFile(this, "${packageName}.fileprovider", file)
        pendingPhotoFile = file
        takePictureLauncher.launch(uri)
    }

    private fun resolveMaterial(serial: String) {
        currentMaterialSerial = serial
        binding.progressBar.visibility = View.VISIBLE
        binding.tvResolveStatus.text = "\u6b63\u5728\u5339\u914d\u7269\u6599\uff0c\u8bf7\u7a0d\u5019..."
        binding.cardMaterialInfo.visibility = View.GONE
        binding.cardPhotoSection.visibility = View.GONE
        clearCapturedPhotos(deleteFiles = true)
        updatePhotoSummary()

        lifecycleScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    apiService.resolveMaterialInbound(serial)
                }
                binding.progressBar.visibility = View.GONE
                if (!response.isSuccessful) {
                    showResolveError("\u7269\u6599\u5339\u914d\u5931\u8d25 (${response.code()})")
                    return@launch
                }
                val body = response.body()
                if (body == null || !body.success) {
                    showResolveError(body?.error ?: "\u7269\u6599\u5339\u914d\u5931\u8d25")
                    return@launch
                }
                currentResolveResponse = body
                val materialCode = displayMaterialCode()
                val materialName = displayMaterialName()
                if (materialCode.isNullOrBlank() || materialName.isNullOrBlank()) {
                    showResolveError("\u672a\u5339\u914d\u5230\u7269\u6599\u7f16\u7801\u6216\u7269\u6599\u540d\u79f0")
                    return@launch
                }
                binding.cardMaterialInfo.visibility = View.VISIBLE
                binding.cardPhotoSection.visibility = View.VISIBLE
                binding.tvMaterialCode.text = materialCode
                binding.tvMaterialName.text = materialName
                binding.tvResolveStatus.text = "\u5df2\u5339\u914d\u5230\u7269\u6599\uff0c\u8bf7\u4e0a\u4f20\u9001\u8d27\u5355\u548c\u7269\u6599\u7167\u7247"
                binding.tvPhotoTip.text = "\u8bf7\u4e0a\u4f20\u9001\u8d27\u5355\u548c\u7269\u6599\u7167\u7247"
                updatePhotoSummary()
            } catch (error: Exception) {
                binding.progressBar.visibility = View.GONE
                AppLogger.log(TAG, "Resolve material inbound failed: ${error.message}", error)
                showResolveError("\u7269\u6599\u5339\u914d\u5931\u8d25\uff1a${error.message}")
            }
        }
    }

    private fun displayMaterialCode(): String? {
        val response = currentResolveResponse ?: return null
        return response.materialCode?.takeIf { it.isNotBlank() }
            ?: response.results?.firstOrNull()?.materialCode?.takeIf { it.isNotBlank() }
    }

    private fun displayMaterialName(): String? {
        val response = currentResolveResponse ?: return null
        return response.materialName?.takeIf { it.isNotBlank() }
            ?: response.results?.firstOrNull()?.materialName?.takeIf { it.isNotBlank() }
    }

    private fun updatePhotoSummary() {
        val deliveryCount = capturedPhotos.count { it.type == PhotoType.DELIVERY }
        val materialCount = capturedPhotos.count { it.type == PhotoType.MATERIAL }
        val totalCount = capturedPhotos.size
        binding.tvPhotoSummary.text = if (totalCount == 0) {
            "\u5c1a\u672a\u62cd\u7167"
        } else {
            "\u5df2\u62cd\u7167 ${totalCount} \u5f20\uff0c\u9001\u8d27\u5355 ${deliveryCount} \u5f20\uff0c\u7269\u6599\u7167\u7247 ${materialCount} \u5f20"
        }
        binding.btnClearPhotos.isEnabled = totalCount > 0
        binding.btnUploadPhotos.isEnabled = deliveryCount > 0 && materialCount > 0 && hasResolvedMaterial() && hasValidQuantity()
        renderCapturedPhotos()
    }

    private fun renderCapturedPhotos() {
        binding.photosContainer.removeAllViews()
        if (capturedPhotos.isEmpty()) {
            binding.photosContainer.addView(TextView(this).apply {
                text = "\u8fd8\u6ca1\u6709\u62cd\u6444\u4efb\u4f55\u7167\u7247"
                textSize = 13f
                setTextColor(ContextCompat.getColor(this@MaterialInboundActivity, R.color.md_onSurfaceVariant))
            })
            return
        }
        capturedPhotos.forEachIndexed { index, item ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                if (index > 0) {
                    setPadding(0, dpInt(8f), 0, 0)
                }
            }
            val labelView = TextView(this).apply {
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                text = "${index + 1}. ${item.type.label} - ${item.file.name}"
                textSize = 13f
                setTextColor(ContextCompat.getColor(this@MaterialInboundActivity, R.color.md_onSurface))
            }
            val deleteView = TextView(this).apply {
                text = "\u5220\u9664"
                textSize = 13f
                setTextColor(ContextCompat.getColor(this@MaterialInboundActivity, R.color.md_error))
                setPadding(dpInt(12f), dpInt(4f), 0, dpInt(4f))
                setOnClickListener {
                    item.file.delete()
                    capturedPhotos.remove(item)
                    updatePhotoSummary()
                    Toast.makeText(this@MaterialInboundActivity, "\u5df2\u5220\u9664${item.type.label}", Toast.LENGTH_SHORT).show()
                }
            }
            row.addView(labelView)
            row.addView(deleteView)
            binding.photosContainer.addView(row)
        }
    }

    private fun uploadPhotos() {
        val materialSerial = currentMaterialSerial?.takeIf { it.isNotBlank() }
        val materialCode = displayMaterialCode()
        val materialName = displayMaterialName()
        val quantity = enteredQuantity()
        val deliveryCount = capturedPhotos.count { it.type == PhotoType.DELIVERY }
        val materialCount = capturedPhotos.count { it.type == PhotoType.MATERIAL }
        if (materialSerial.isNullOrBlank() || materialCode.isNullOrBlank() || materialName.isNullOrBlank()) {
            Toast.makeText(this, "\u8bf7\u5148\u5b8c\u6210\u7269\u6599\u8bc6\u522b", Toast.LENGTH_SHORT).show()
            return
        }
        if (quantity.isNullOrBlank()) {
            binding.tilInboundQuantity.error = "\u8bf7\u586b\u5199\u6570\u91cf"
            binding.etInboundQuantity.requestFocus()
            Toast.makeText(this, "\u8bf7\u586b\u5199\u6570\u91cf", Toast.LENGTH_SHORT).show()
            return
        }
        if (deliveryCount <= 0) {
            Toast.makeText(this, "\u8bf7\u81f3\u5c11\u62cd\u6444\u4e00\u5f20\u9001\u8d27\u5355\u7167\u7247", Toast.LENGTH_SHORT).show()
            return
        }
        if (materialCount <= 0) {
            Toast.makeText(this, "\u8bf7\u81f3\u5c11\u62cd\u6444\u4e00\u5f20\u7269\u6599\u7167\u7247", Toast.LENGTH_SHORT).show()
            return
        }

        binding.progressBar.visibility = View.VISIBLE
        binding.btnCapturePhoto.isEnabled = false
        binding.btnClearPhotos.isEnabled = false
        binding.btnUploadPhotos.isEnabled = false
        binding.tvResolveStatus.text = "\u6b63\u5728\u4e0a\u4f20\u7167\u7247\uff0c\u8bf7\u7a0d\u5019..."

        val pendingItems = capturedPhotos.toList()
        lifecycleScope.launch {
            val remainingItems = mutableListOf<CapturedPhoto>()
            var successCount = 0
            var failCount = 0
            var recordSaved = false
            var recordSaveError: String? = null

            for (item in pendingItems) {
                try {
                    val response = withContext(Dispatchers.IO) {
                        val photoBody = item.file.asRequestBody("image/jpeg".toMediaType())
                        apiService.uploadMaterialInboundPhoto(
                            photo = MultipartBody.Part.createFormData("photo", item.file.name, photoBody),
                            materialSerial = materialSerial.toPlainText(),
                            materialCode = materialCode.toPlainText(),
                            materialName = materialName.toPlainText(),
                            quantity = quantity.toPlainText(),
                            photoType = item.type.requestValue.toPlainText(),
                        )
                    }
                    val body = response.body()
                    if (response.isSuccessful && body != null && body.success) {
                        successCount += 1
                        item.file.delete()
                    } else {
                        failCount += 1
                        remainingItems.add(item)
                    }
                } catch (error: Exception) {
                    failCount += 1
                    remainingItems.add(item)
                    AppLogger.log(TAG, "Upload material inbound photo failed: ${error.message}", error)
                }
            }

            if (successCount > 0) {
                try {
                    recordSaved = saveInboundRecord(materialCode, materialName, quantity)
                } catch (error: Exception) {
                    recordSaveError = error.message
                    AppLogger.log(TAG, "Save inbound quantity record failed: ${error.message}", error)
                }
            }

            binding.progressBar.visibility = View.GONE
            capturedPhotos.clear()
            capturedPhotos.addAll(remainingItems)
            updatePhotoSummary()
            binding.btnCapturePhoto.isEnabled = hasResolvedMaterial()
            if (successCount > 0 && failCount == 0) {
                binding.tvResolveStatus.text = if (recordSaved) {
                    "\u7167\u7247\u548c\u6570\u91cf\u8bb0\u5f55\u5df2\u4e0a\u4f20\u5b8c\u6210"
                } else {
                    "\u7167\u7247\u5df2\u4e0a\u4f20\uff0c\u4f46\u6570\u91cf\u8bb0\u5f55\u4fdd\u5b58\u5931\u8d25"
                }
                Toast.makeText(this@MaterialInboundActivity, "\u6210\u529f\u4e0a\u4f20 ${successCount} \u5f20\u7167\u7247", Toast.LENGTH_SHORT).show()
            } else if (successCount > 0) {
                binding.tvResolveStatus.text = if (recordSaved) {
                    "\u5df2\u4e0a\u4f20 ${successCount} \u5f20\uff0c\u5931\u8d25 ${failCount} \u5f20\uff0c\u6570\u91cf\u8bb0\u5f55\u5df2\u4fdd\u5b58"
                } else {
                    "\u5df2\u4e0a\u4f20 ${successCount} \u5f20\uff0c\u5931\u8d25 ${failCount} \u5f20\uff0c\u6570\u91cf\u8bb0\u5f55\u4fdd\u5b58\u5931\u8d25"
                }
                Toast.makeText(this@MaterialInboundActivity, "\u90e8\u5206\u7167\u7247\u4e0a\u4f20\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5\u5269\u4f59\u7167\u7247", Toast.LENGTH_SHORT).show()
            } else {
                binding.tvResolveStatus.text = "\u7167\u7247\u4e0a\u4f20\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u7f51\u7edc\u540e\u91cd\u8bd5"
                Toast.makeText(this@MaterialInboundActivity, "\u7167\u7247\u4e0a\u4f20\u5931\u8d25", Toast.LENGTH_SHORT).show()
            }
            if (!recordSaveError.isNullOrBlank()) {
                Toast.makeText(this@MaterialInboundActivity, recordSaveError, Toast.LENGTH_SHORT).show()
            }
        }
    }

    private suspend fun saveInboundRecord(materialCode: String, materialName: String, quantity: String): Boolean {
        val response = withContext(Dispatchers.IO) {
            apiService.recordMaterialInbound(
                MaterialInboundRecordRequest(
                    materialCode = materialCode,
                    materialName = materialName,
                    quantity = quantity,
                )
            )
        }
        val body = response.body()
        if (response.isSuccessful && body != null && body.success) {
            return true
        }
        throw IllegalStateException(body?.error ?: body?.message ?: "\u6570\u91cf\u8bb0\u5f55\u4fdd\u5b58\u5931\u8d25")
    }

    private fun clearCapturedPhotos(deleteFiles: Boolean) {
        if (deleteFiles) {
            capturedPhotos.forEach { it.file.delete() }
        }
        capturedPhotos.clear()
        pendingPhotoFile?.delete()
        pendingPhotoFile = null
        pendingPhotoType = null
    }

    private fun showResolveError(message: String) {
        binding.tvResolveStatus.text = message
        binding.cardMaterialInfo.visibility = View.GONE
        binding.cardPhotoSection.visibility = View.GONE
    }

    private fun String.toPlainText() = this.toRequestBody("text/plain".toMediaType())

    private fun dp(value: Float): Float = value * resources.displayMetrics.density

    private fun dpInt(value: Float): Int = dp(value).toInt()

    companion object {
        private const val TAG = "MaterialInboundActivity"
    }
}
