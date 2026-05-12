package com.testcenter.qrscanner

import android.app.Activity
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Build
import android.provider.MediaStore
import android.util.Log
import android.widget.Button
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.testcenter.qrscanner.adapter.ImagePreviewAdapter
import com.testcenter.qrscanner.databinding.ActivityCameraBinding
import com.testcenter.qrscanner.network.FileManager
import com.testcenter.qrscanner.network.FileManagerFactory
import com.testcenter.qrscanner.repository.PhotoRepository
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.PreferencesManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Locale

class CameraActivity : AppCompatActivity() {

    private lateinit var binding: ActivityCameraBinding
    private var imageCapture: ImageCapture? = null
    private lateinit var outputDirectory: File
    private var cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA
    private var productSerial: String? = null
    private lateinit var imagePreviewAdapter: ImagePreviewAdapter
    private val imageUris = mutableListOf<Uri>()
    private lateinit var fileManager: FileManager
    private lateinit var preferencesManager: PreferencesManager
    
    // 使用 REST API Repository 替代 SMB FileManager
    private val photoRepository by lazy { PhotoRepository(this) }

    private val selectImagesLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            result.data?.clipData?.let { clipData ->
                for (i in 0 until clipData.itemCount) {
                    val imageUri = clipData.getItemAt(i).uri
                    imageUris.add(imageUri)
                }
                imagePreviewAdapter.notifyDataSetChanged()
            } ?: result.data?.data?.let { uri ->
                imageUris.add(uri)
                imagePreviewAdapter.notifyDataSetChanged()
            }
        }
    }

    companion object {
        private const val TAG = "CameraActivity"
        private const val REQUEST_CODE_PERMISSIONS = 10
        private val REQUIRED_PERMISSIONS = arrayOf(android.Manifest.permission.CAMERA)
        private const val REQUEST_CODE_IMAGE = 101
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityCameraBinding.inflate(layoutInflater)
        setContentView(binding.root)

        productSerial = intent.getStringExtra("product_serial")

        preferencesManager = PreferencesManager(this)
        fileManager = FileManagerFactory.create(
            this,
            preferencesManager.getUsername(),
            preferencesManager.getPassword()
        )

        imagePreviewAdapter = ImagePreviewAdapter(imageUris)
        binding.rvImagePreviews.adapter = imagePreviewAdapter
        binding.rvImagePreviews.layoutManager = LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false)
        if (allPermissionsGranted()) {
            startCamera()
        } else {
            ActivityCompat.requestPermissions(
                this, REQUIRED_PERMISSIONS, REQUEST_CODE_PERMISSIONS)
        }


        binding.btnSwitchCamera.setOnClickListener {
            cameraSelector = if (cameraSelector == CameraSelector.DEFAULT_BACK_CAMERA) {
                CameraSelector.DEFAULT_FRONT_CAMERA
            } else {
                CameraSelector.DEFAULT_BACK_CAMERA
            }
            startCamera()
        }

        binding.btnCapture.setOnClickListener {
            takePhoto()
        }

        binding.btnSelectFromGallery.setOnClickListener {
            openGalleryForImageSelection()
        }

        binding.btnConfirmUpload.setOnClickListener {
            uploadImages()
        }
    }

    private fun uploadImages() {
        if (imageUris.isEmpty()) {
            Toast.makeText(this, "No images to upload", Toast.LENGTH_SHORT).show()
            return
        }

        lifecycleScope.launch {
            // 并行上传，最多 3 个并发
            val semaphore = kotlinx.coroutines.sync.Semaphore(3)
            val results = imageUris.map { uri ->
                async(Dispatchers.IO) {
                    semaphore.acquire()
                    try {
                        val photoBytes = readBytesFromUri(uri) ?: return@async false
                        val remoteFileName = "${productSerial}_${System.currentTimeMillis()}.jpg"

                        val apiResult = photoRepository.uploadPhoto(
                            photoBytes = photoBytes,
                            fileName = remoteFileName,
                            productSerial = productSerial ?: "unknown",
                            projectName = "",
                            productType = "",
                            processName = "产品拍照"
                        )

                        var uploaded = false
                        apiResult.fold(
                            onSuccess = {
                                AppLogger.log("CameraActivity", "Photo uploaded via REST API: $remoteFileName")
                                uploaded = true
                            },
                            onFailure = { e ->
                                AppLogger.log("CameraActivity", "REST API failed, trying FileManager: ${e.message}")
                                val directoryInfo = FileManager.PhotoDirectoryInfo(
                                    projectName = "",
                                    projectCode = "",
                                    productType = "",
                                    modelNumber = "",
                                    productSerial = productSerial ?: "unknown"
                                )
                                uploaded = fileManager.uploadPhoto(directoryInfo, remoteFileName, photoBytes)
                            }
                        )
                        uploaded
                    } finally {
                        semaphore.release()
                    }
                }
            }.awaitAll()

            val successCount = results.count { it }
            val failCount = results.count { !it }

            if (failCount == 0) {
                Toast.makeText(this@CameraActivity, "All images uploaded successfully", Toast.LENGTH_SHORT).show()
                imageUris.clear()
                imagePreviewAdapter.notifyDataSetChanged()
            } else {
                Toast.makeText(this@CameraActivity, "成功 $successCount 张，失败 $failCount 张", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private suspend fun readBytesFromUri(uri: Uri): ByteArray? = withContext(Dispatchers.IO) {
        try {
            contentResolver.openInputStream(uri)?.use { it.readBytes() }
        } catch (e: Exception) {
            AppLogger.log("CameraActivity", "Failed to read URI: $uri, error: ${e.message}")
            null
        }
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)

        cameraProviderFuture.addListener({
            val cameraProvider: ProcessCameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder()
                .build()
                .also {
                    it.setSurfaceProvider(binding.cameraPreview.surfaceProvider)
                }

            imageCapture = ImageCapture.Builder().build()

            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(
                    this, cameraSelector, preview, imageCapture
                )
            } catch (exc: Exception) {
                AppLogger.log("CameraActivity", "Use case binding failed", exc)
            }

        }, ContextCompat.getMainExecutor(this))
    }

    private fun takePhoto() {
        val imageCapture = imageCapture ?: return

        val name = productSerial ?: "default_product"
        val contentValues = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, "${name}_${System.currentTimeMillis()}")
            put(MediaStore.MediaColumns.MIME_TYPE, "image/jpeg")
            if (Build.VERSION.SDK_INT > Build.VERSION_CODES.P) {
                put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/CameraX-Image")
            }
        }

        val outputOptions = ImageCapture.OutputFileOptions
            .Builder(contentResolver,
                MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                contentValues)
            .build()

        imageCapture.takePicture(
            outputOptions,
            ContextCompat.getMainExecutor(this),
            object : ImageCapture.OnImageSavedCallback {
                override fun onError(exc: ImageCaptureException) {
                    Log.e(TAG, "Photo capture failed: ${exc.message}", exc)
                }

                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    val msg = "Photo capture succeeded: ${output.savedUri}"
                    Toast.makeText(baseContext, msg, Toast.LENGTH_SHORT).show()
                    Log.d(TAG, msg)
                    output.savedUri?.let { 
                        imageUris.add(it)
                        imagePreviewAdapter.notifyDataSetChanged()
                    }
                }
            }
        )
    }

    private fun openGalleryForImageSelection() {
        val intent = Intent(Intent.ACTION_PICK, MediaStore.Images.Media.EXTERNAL_CONTENT_URI)
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
        selectImagesLauncher.launch(intent)
    }

    private fun allPermissionsGranted() = REQUIRED_PERMISSIONS.all {
        ContextCompat.checkSelfPermission(
            baseContext, it) == PackageManager.PERMISSION_GRANTED
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_CODE_PERMISSIONS) {
            if (allPermissionsGranted()) {
                startCamera()
            } else {
                Toast.makeText(this, "Permissions not granted by the user.", Toast.LENGTH_SHORT).show()
                finish()
            }
        }
    }

    private fun getOutputDirectory(): File {
        val mediaDir = externalMediaDirs.firstOrNull()?.let {
            File(it, resources.getString(R.string.app_name)).apply { mkdirs() }
        }
        return if (mediaDir != null && mediaDir.exists())
            mediaDir else filesDir
    }

    private fun createFileName(): String {
        val timeStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(System.currentTimeMillis())
        return if (productSerial != null) {
            "${productSerial}_${timeStamp}.jpg"
        } else {
            "IMG_${timeStamp}.jpg"
        }
    }
}
