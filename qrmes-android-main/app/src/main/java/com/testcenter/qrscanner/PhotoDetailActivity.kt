package com.testcenter.qrscanner

import android.content.Intent
import android.graphics.BitmapFactory
import android.os.Bundle
import android.view.MenuItem
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import com.testcenter.qrscanner.databinding.ActivityPhotoDetailBinding
import com.testcenter.qrscanner.network.FileManager
import com.testcenter.qrscanner.network.FileManagerFactory
import com.testcenter.qrscanner.photo.PhotoCacheManager
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.PreferencesManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/**
 * 照片大图查看Activity
 * 支持缩放、拖动、分享
 */
class PhotoDetailActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPhotoDetailBinding
    private lateinit var preferencesManager: PreferencesManager
    private lateinit var photoCacheManager: PhotoCacheManager
    
    private var productSerial: String = ""
    private var projectName: String = ""
    private var projectCode: String = ""
    private var productType: String = ""
    private var modelNumber: String = ""
    private var fileName: String = ""
    
    companion object {
        const val EXTRA_PRODUCT_SERIAL = "extra_product_serial"
        const val EXTRA_PROJECT_NAME = "extra_project_name"
        const val EXTRA_PROJECT_CODE = "extra_project_code"
        const val EXTRA_PRODUCT_TYPE = "extra_product_type"
        const val EXTRA_MODEL_NUMBER = "extra_model_number"
        const val EXTRA_FILE_NAME = "extra_file_name"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPhotoDetailBinding.inflate(layoutInflater)
        setContentView(binding.root)
        
        preferencesManager = PreferencesManager(this)
        photoCacheManager = PhotoCacheManager(this)
        
        // 获取传入的参数
        productSerial = intent.getStringExtra(EXTRA_PRODUCT_SERIAL) ?: ""
        projectName = intent.getStringExtra(EXTRA_PROJECT_NAME) ?: ""
        projectCode = intent.getStringExtra(EXTRA_PROJECT_CODE) ?: ""
        productType = intent.getStringExtra(EXTRA_PRODUCT_TYPE) ?: ""
        modelNumber = intent.getStringExtra(EXTRA_MODEL_NUMBER) ?: ""
        fileName = intent.getStringExtra(EXTRA_FILE_NAME) ?: ""
        
        if (productSerial.isEmpty() || fileName.isEmpty()) {
            Toast.makeText(this, "参数错误", Toast.LENGTH_SHORT).show()
            finish()
            return
        }
        
        setupToolbar()
        setupUI()
        loadPhoto()
    }
    
    private fun setupToolbar() {
        setSupportActionBar(binding.toolbar)
        supportActionBar?.apply {
            title = fileName
            setDisplayHomeAsUpEnabled(true)
        }
    }
    
    private fun setupUI() {
        // 分享按钮
        binding.btnShare.setOnClickListener {
            sharePhoto()
        }
        
        // 下载按钮
        binding.btnDownload.setOnClickListener {
            downloadPhoto()
        }
    }
    
    private fun loadPhoto() {
        binding.progressBar.visibility = View.VISIBLE
        binding.photoView.visibility = View.GONE
        binding.tvError.visibility = View.GONE
        
        lifecycleScope.launch {
            try {
                // 先检查缓存
                val cachedFile = photoCacheManager.getCachedPhoto(productSerial, fileName)
                if (cachedFile != null && cachedFile.exists()) {
                    AppLogger.log("PhotoDetailActivity", "从缓存加载照片: $fileName")
                    displayPhoto(cachedFile)
                    return@launch
                }
                
                // 从NAS下载
                val username = preferencesManager.getUsername() ?: ""
                val password = preferencesManager.getPassword() ?: ""
                val fileManager = FileManagerFactory.create(this@PhotoDetailActivity, username, password)
                
                val directoryInfo = FileManager.PhotoDirectoryInfo(
                    projectName = projectName,
                    projectCode = projectCode,
                    productType = productType,
                    modelNumber = modelNumber,
                    productSerial = productSerial
                )
                
                val photoBytes = withContext(Dispatchers.IO) {
                    fileManager.downloadPhoto(directoryInfo, fileName)
                }
                
                if (photoBytes != null) {
                    // 保存到缓存
                    val cachedFile = photoCacheManager.cachePhoto(productSerial, fileName, photoBytes)
                    if (cachedFile != null) {
                        displayPhoto(cachedFile)
                    } else {
                        // 缓存失败，直接显示
                        displayPhotoFromBytes(photoBytes)
                    }
                } else {
                    showError("下载照片失败")
                }
            } catch (e: Exception) {
                AppLogger.log("PhotoDetailActivity", "加载照片失败: ${e.message}", e)
                showError("加载失败: ${e.message}")
            }
        }
    }
    
    private fun displayPhoto(file: File) {
        binding.progressBar.visibility = View.GONE
        binding.photoView.visibility = View.VISIBLE
        binding.photoView.setImageURI(android.net.Uri.fromFile(file))
    }
    
    private fun displayPhotoFromBytes(photoBytes: ByteArray) {
        binding.progressBar.visibility = View.GONE
        binding.photoView.visibility = View.VISIBLE
        // 先获取图片尺寸，按需降采样避免 OOM
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(photoBytes, 0, photoBytes.size, options)
        val maxDimension = 2048
        var sampleSize = 1
        while (options.outWidth / sampleSize > maxDimension || options.outHeight / sampleSize > maxDimension) {
            sampleSize *= 2
        }
        val decodeOptions = BitmapFactory.Options().apply { inSampleSize = sampleSize }
        val bitmap = BitmapFactory.decodeByteArray(photoBytes, 0, photoBytes.size, decodeOptions)
        binding.photoView.setImageBitmap(bitmap)
    }
    
    private fun showError(message: String) {
        binding.progressBar.visibility = View.GONE
        binding.photoView.visibility = View.GONE
        binding.tvError.visibility = View.VISIBLE
        binding.tvError.text = message
    }
    
    private fun sharePhoto() {
        lifecycleScope.launch {
            try {
                val cachedFile = photoCacheManager.getCachedPhoto(productSerial, fileName)
                if (cachedFile == null || !cachedFile.exists()) {
                    Toast.makeText(this@PhotoDetailActivity, "照片未缓存，请稍候", Toast.LENGTH_SHORT).show()
                    return@launch
                }
                
                val uri = FileProvider.getUriForFile(
                    this@PhotoDetailActivity,
                    "${packageName}.fileprovider",
                    cachedFile
                )
                
                val shareIntent = Intent(Intent.ACTION_SEND).apply {
                    type = "image/*"
                    putExtra(Intent.EXTRA_STREAM, uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                
                startActivity(Intent.createChooser(shareIntent, "分享照片"))
            } catch (e: Exception) {
                AppLogger.log("PhotoDetailActivity", "分享照片失败: ${e.message}", e)
                Toast.makeText(this@PhotoDetailActivity, "分享失败: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }
    
    private fun downloadPhoto() {
        lifecycleScope.launch {
            try {
                val cachedFile = photoCacheManager.getCachedPhoto(productSerial, fileName)
                if (cachedFile != null && cachedFile.exists()) {
                    // 复制到公共目录
                    val success = photoCacheManager.saveToPublicDirectory(cachedFile, fileName)
                    if (success) {
                        Toast.makeText(this@PhotoDetailActivity, "照片已保存到相册", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(this@PhotoDetailActivity, "保存失败", Toast.LENGTH_SHORT).show()
                    }
                } else {
                    Toast.makeText(this@PhotoDetailActivity, "照片未缓存", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                AppLogger.log("PhotoDetailActivity", "下载照片失败: ${e.message}", e)
                Toast.makeText(this@PhotoDetailActivity, "下载失败: ${e.message}", Toast.LENGTH_SHORT).show()
            }
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
}
