package com.testcenter.qrscanner

import android.content.Intent
import android.os.Bundle
import android.view.MenuItem
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.GridLayoutManager
import com.testcenter.qrscanner.adapter.PhotoRecordAdapter
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.databinding.ActivityPhotoRecordsBinding
import com.testcenter.qrscanner.network.FileManagerFactory
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.PreferencesManager
import com.testcenter.qrscanner.utils.ProcessPhotoFileNameParser
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull

/**
 * 照片记录查看Activity
 * 显示指定产品的所有已上传照片
 */
class PhotoRecordsActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPhotoRecordsBinding
    private lateinit var preferencesManager: PreferencesManager
    private lateinit var photoAdapter: PhotoRecordAdapter
    
    private var productSerial: String = ""
    private var projectName: String = ""
    private var projectCode: String = ""
    private var productType: String = ""
    private var modelNumber: String = ""
    private var processStepName: String = ""
    
    companion object {
        const val EXTRA_PRODUCT_SERIAL = "extra_product_serial"
        const val EXTRA_PROJECT_NAME = "extra_project_name"
        const val EXTRA_PROJECT_CODE = "extra_project_code"
        const val EXTRA_PRODUCT_TYPE = "extra_product_type"
        const val EXTRA_MODEL_NUMBER = "extra_model_number"
        const val EXTRA_PROCESS_STEP_NAME = "extra_process_step_name"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPhotoRecordsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        
        preferencesManager = PreferencesManager(this)
        
        // 获取传入的参数
        productSerial = intent.getStringExtra(EXTRA_PRODUCT_SERIAL) ?: ""
        projectName = intent.getStringExtra(EXTRA_PROJECT_NAME) ?: ""
        projectCode = intent.getStringExtra(EXTRA_PROJECT_CODE) ?: ""
        productType = intent.getStringExtra(EXTRA_PRODUCT_TYPE) ?: ""
        modelNumber = intent.getStringExtra(EXTRA_MODEL_NUMBER) ?: ""
        processStepName = intent.getStringExtra(EXTRA_PROCESS_STEP_NAME) ?: ""
        
        if (productSerial.isEmpty()) {
            Toast.makeText(this, "产品序列号为空", Toast.LENGTH_SHORT).show()
            finish()
            return
        }
        
        setupToolbar()
        setupUI()
        loadPhotoRecords()
    }
    
    private fun setupToolbar() {
        setSupportActionBar(binding.toolbar)
        supportActionBar?.apply {
            title = "照片记录"
            setDisplayHomeAsUpEnabled(true)
        }
    }
    
    private fun setupUI() {
        binding.tvProductSerial.text = productSerial
        binding.tvProjectInfo.text = buildString {
            append(projectName)
            if (projectCode.isNotEmpty()) {
                append(" ($projectCode)")
            }
        }
        binding.tvProductTypeInfo.text = buildString {
            append(productType)
            if (modelNumber.isNotEmpty()) {
                append(" ($modelNumber)")
            }
        }
        
        // 构建目录信息
        val directoryInfo = com.testcenter.qrscanner.network.FileManager.PhotoDirectoryInfo(
            projectName = projectName,
            projectCode = projectCode,
            productType = productType,
            modelNumber = modelNumber,
            productSerial = productSerial
        )
        
        // 设置照片网格布局
        photoAdapter = PhotoRecordAdapter(
            photos = emptyList(),
            directoryInfo = directoryInfo,
            onPhotoClick = { photo ->
                // 点击照片，显示大图
                showPhotoDetail(photo)
            }
        )
        binding.recyclerViewPhotos.apply {
            layoutManager = GridLayoutManager(this@PhotoRecordsActivity, 2)
            adapter = photoAdapter
        }
        
        // 刷新按钮
        binding.btnRefresh.setOnClickListener {
            loadPhotoRecords()
        }
    }
    
    private fun showPhotoDetail(photo: PhotoRecord) {
        val intent = Intent(this, PhotoDetailActivity::class.java).apply {
            putExtra(PhotoDetailActivity.EXTRA_PRODUCT_SERIAL, productSerial)
            putExtra(PhotoDetailActivity.EXTRA_PROJECT_NAME, projectName)
            putExtra(PhotoDetailActivity.EXTRA_PROJECT_CODE, projectCode)
            putExtra(PhotoDetailActivity.EXTRA_PRODUCT_TYPE, productType)
            putExtra(PhotoDetailActivity.EXTRA_MODEL_NUMBER, modelNumber)
            putExtra(PhotoDetailActivity.EXTRA_FILE_NAME, photo.fileName)
        }
        startActivity(intent)
    }
    
    private fun loadPhotoRecords() {
        binding.progressBar.visibility = View.VISIBLE
        binding.tvEmptyMessage.visibility = View.GONE
        binding.recyclerViewPhotos.visibility = View.GONE
        
        lifecycleScope.launch {
            try {
                val username = preferencesManager.getUsername() ?: ""
                val password = preferencesManager.getPassword() ?: ""
                val fileManager = FileManagerFactory.create(this@PhotoRecordsActivity, username, password)
                
                // 优先 NAS，超时后自动回退 API，避免界面长时间转圈
                val nasPhotos = withContext(Dispatchers.IO) {
                    withTimeoutOrNull(12_000L) { listPhotosFromNAS(fileManager) }
                }
                if (nasPhotos == null) {
                    AppLogger.log("PhotoRecordsActivity", "NAS 查询超时，回退 API 列表")
                }
                val apiPhotos = withContext(Dispatchers.IO) { listPhotosViaApi() }
                val photos = mergePhotoRecords(nasPhotos ?: emptyList(), apiPhotos)

                AppLogger.log(
                    "PhotoRecordsActivity",
                    "照片列表合并完成: nas=${nasPhotos?.size ?: 0}, api=${apiPhotos.size}, merged=${photos.size}"
                )

                if (photos.isEmpty()) {
                    binding.tvEmptyMessage.visibility = View.VISIBLE
                    binding.recyclerViewPhotos.visibility = View.GONE
                    binding.tvPhotoCount.text = buildPhotoCountText(0)
                } else {
                    binding.tvEmptyMessage.visibility = View.GONE
                    binding.recyclerViewPhotos.visibility = View.VISIBLE
                    binding.tvPhotoCount.text = buildPhotoCountText(photos.size)
                    photoAdapter.updateData(photos)
                }
            } catch (e: Exception) {
                AppLogger.log("PhotoRecordsActivity", "加载照片记录失败: ${e.message}", e)
                binding.tvEmptyMessage.visibility = View.VISIBLE
                binding.tvEmptyMessage.text = "加载失败: ${e.message}"
                Toast.makeText(this@PhotoRecordsActivity, "加载失败: ${e.message}", Toast.LENGTH_LONG).show()
            } finally {
                binding.progressBar.visibility = View.GONE
            }
        }
    }

    private suspend fun listPhotosViaApi(): List<PhotoRecord> {
        return withContext(Dispatchers.IO) {
            try {
                val response = ApiClient.getApiService(this@PhotoRecordsActivity).listPhotos(
                    projectName = projectName.ifBlank { null },
                    productType = productType.ifBlank { null },
                    productSerial = productSerial.ifBlank { null },
                    processStep = processStepName.ifBlank { null }
                )
                if (!response.isSuccessful) {
                    AppLogger.log("PhotoRecordsActivity", "API 查询照片失败: HTTP ${response.code()}")
                    return@withContext emptyList()
                }
                val body = response.body()
                if (body?.success != true) {
                    AppLogger.log("PhotoRecordsActivity", "API 查询照片返回失败响应")
                    return@withContext emptyList()
                }
                (body.photos ?: emptyList())
                    .filter { it.productSerial.isNullOrBlank() || it.productSerial == productSerial }
                    .filter { photo ->
                        if (processStepName.isBlank()) return@filter true
                        val parsed = photo.processStep
                            ?: ProcessPhotoFileNameParser.extractProcessName(productSerial, photo.fileName)
                            ?: ""
                        ProcessPhotoFileNameParser.normalizeForMatch(parsed) ==
                            ProcessPhotoFileNameParser.normalizeForMatch(processStepName)
                    }
                    .map {
                        PhotoRecord(
                            fileName = it.fileName,
                            filePath = it.filePath ?: "",
                            fileSize = 0L,
                            uploadTime = 0L,
                            thumbnailUrl = it.thumbnailUrl
                        )
                    }
            } catch (e: Exception) {
                AppLogger.log("PhotoRecordsActivity", "API 查询照片异常: ${e.message}", e)
                emptyList()
            }
        }
    }
    
    private suspend fun listPhotosFromNAS(fileManager: com.testcenter.qrscanner.network.FileManager): List<PhotoRecord> {
        return withContext(Dispatchers.IO) {
            try {
                // 构建目录信息
                val directoryInfo = com.testcenter.qrscanner.network.FileManager.PhotoDirectoryInfo(
                    projectName = projectName,
                    projectCode = projectCode,
                    productType = productType,
                    modelNumber = modelNumber,
                    productSerial = productSerial
                )
                
                AppLogger.log("PhotoRecordsActivity", "查询照片列表: 项目=$projectName, 产品=$productSerial")
                
                // 从NAS获取照片列表
                val photoInfoList = fileManager.listPhotos(directoryInfo)
                
                // 转换为PhotoRecord
                val photoRecords = photoInfoList.map { photoInfo ->
                    PhotoRecord(
                        fileName = photoInfo.fileName,
                        filePath = photoInfo.filePath,
                        fileSize = photoInfo.fileSize,
                        uploadTime = photoInfo.lastModified
                    )
                }
                    .filter { photo ->
                        if (processStepName.isBlank()) return@filter true
                        val parsed = ProcessPhotoFileNameParser.extractProcessName(productSerial, photo.fileName) ?: ""
                        ProcessPhotoFileNameParser.normalizeForMatch(parsed) ==
                            ProcessPhotoFileNameParser.normalizeForMatch(processStepName)
                    }
                
                AppLogger.log("PhotoRecordsActivity", "成功获取 ${photoRecords.size} 张照片")
                photoRecords
            } catch (e: Exception) {
                AppLogger.log("PhotoRecordsActivity", "获取照片列表失败: ${e.message}", e)
                emptyList()
            }
        }
    }
    
    private fun sanitize(value: String): String {
        return value.replace("[^\\p{L}\\p{N}_-]".toRegex(), "_")
    }

    private fun mergePhotoRecords(
        nasPhotos: List<PhotoRecord>,
        apiPhotos: List<PhotoRecord>
    ): List<PhotoRecord> {
        val merged = LinkedHashMap<String, PhotoRecord>()

        fun putPhoto(photo: PhotoRecord) {
            val key = buildPhotoIdentity(photo.fileName, photo.filePath)
            val existing = merged[key]
            merged[key] = when {
                existing == null -> photo
                existing.filePath.isBlank() && photo.filePath.isNotBlank() -> photo
                existing.fileSize <= 0 && photo.fileSize > 0 -> photo
                existing.uploadTime <= 0 && photo.uploadTime > 0 -> photo
                else -> existing
            }
        }

        nasPhotos.forEach(::putPhoto)
        apiPhotos.forEach(::putPhoto)

        return merged.values.sortedWith(
            compareByDescending<PhotoRecord> { it.uploadTime }
                .thenByDescending { it.fileName }
        )
    }

    private fun buildPhotoIdentity(fileName: String, filePath: String?): String {
        return (fileName.ifBlank { filePath ?: "" }).trim().lowercase()
    }
    
    private fun sanitizeFolderName(primary: String, secondary: String): String {
        val base = primary.ifEmpty { "未命名" }
        val secondaryPart = secondary.takeIf { it.isNotEmpty() }?.let { "_${it}" } ?: ""
        return sanitize(base + secondaryPart)
    }

    private fun buildPhotoCountText(count: Int): String {
        return if (processStepName.isBlank()) {
            "共 $count 张照片"
        } else {
            "工序“$processStepName”共 $count 张照片"
        }
    }
    
    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            android.R.id.home -> {
                finish()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }
    
    data class PhotoRecord(
        val fileName: String,
        val filePath: String,
        val fileSize: Long,
        val uploadTime: Long,
        val thumbnailUrl: String? = null
    )
}
