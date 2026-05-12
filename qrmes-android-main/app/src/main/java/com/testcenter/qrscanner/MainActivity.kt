package com.testcenter.qrscanner

import android.Manifest
import android.content.DialogInterface
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import android.widget.AdapterView
import android.view.View
import android.view.ViewGroup
import android.view.LayoutInflater
import android.view.ViewParent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import androidx.recyclerview.widget.LinearLayoutManager
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.tabs.TabLayout
import androidx.recyclerview.widget.RecyclerView
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanIntentResult
import com.journeyapps.barcodescanner.ScanOptions
import com.testcenter.qrscanner.scanner.EnhancedQRScanner
import com.testcenter.qrscanner.adapter.Component
import com.testcenter.qrscanner.adapter.ComponentAdapter
import com.testcenter.qrscanner.databinding.ActivityMainBinding
import com.testcenter.qrscanner.utils.PreferencesManager
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.ProjectManager
import com.testcenter.qrscanner.utils.ProjectConfigManager
import com.testcenter.qrscanner.utils.SerialNormalizer
import com.testcenter.qrscanner.data.ProjectConfig
import com.testcenter.qrscanner.data.MaterialInfo
import com.testcenter.qrscanner.database.UnifiedDataManager
import com.testcenter.qrscanner.data.ProductRecord
import com.testcenter.qrscanner.repository.TestRepository
import com.testcenter.qrscanner.data.TestDatabase
import com.testcenter.qrscanner.network.FileManager
import com.testcenter.qrscanner.network.FileManagerFactory
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.material.MaterialQrCodeValidator
import com.testcenter.qrscanner.repository.ProductRecordRepository
import com.testcenter.qrscanner.update.ApkUpdateManager
import com.testcenter.qrscanner.worker.ConfigSyncScheduler
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var preferencesManager: PreferencesManager
    private lateinit var projectManager: ProjectManager
    private lateinit var projectConfigManager: ProjectConfigManager
    private lateinit var unifiedDataManager: UnifiedDataManager
    private lateinit var testRepository: TestRepository
    private lateinit var enhancedQRScanner: EnhancedQRScanner
    private lateinit var localUserManager: com.testcenter.qrscanner.auth.LocalUserManager
    private lateinit var permissionService: com.testcenter.qrscanner.auth.PermissionService

    private val apkUpdateManager by lazy { ApkUpdateManager(this) }
    
    // 使用 REST API Repository 替代 SMB FileManager
    private val productRecordRepository by lazy { ProductRecordRepository(this) }

    private var currentProjectConfig: ProjectConfig? = null

    private lateinit var productInfoLayout: View
    private lateinit var syncProgressLayout: View
    private lateinit var syncProgressText: TextView
    private lateinit var tvProductSerial: TextView
    // tvOperatorName removed - using login user automatically
    private lateinit var tvProjectCode: TextView
    private lateinit var tvProjectName: TextView
    private lateinit var tvProductTypeName: TextView
    private lateinit var spinnerProductType: Spinner
    private lateinit var recyclerViewComponents: RecyclerView
    private lateinit var componentAdapter: ComponentAdapter
    private lateinit var btnPhotoCapture: com.google.android.material.button.MaterialButton
    private var currentScanningComponent: Component? = null
    private var currentProductSerial: String? = null
    private var currentProductType: String = "电机控制器"
    private var suppressProductTypeSwitchCheck: Boolean = false
    private var pendingBindingUpdateSerial: String? = null
    private val scannedComponents = mutableMapOf<String, String>() // componentName -> serialNumber
    private val scanOnlyAutoMatchMode = true
    private val projectListRefreshInterval = 60 * 1000L

    // 前台定期检查配置更新
    private val configCheckHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private val configCheckInterval = 1 * 60 * 1000L // 1分钟检查一次（可调整：1/3/5分钟）
    private val configCheckRunnable = object : Runnable {
        override fun run() {
            refreshProjectListCacheInBackground()
            val selectedProject = projectManager.getSelectedProject()
            if (selectedProject != null) {
                AppLogger.log("MainActivity", "Periodic config check (foreground)")
                checkAndSyncConfigIfNeeded(selectedProject)
            }
            configCheckHandler.postDelayed(this, configCheckInterval)
        }
    }
    
    private var productTypes = arrayOf<String>()  // 动态加载
    private var componentsList = mutableListOf<Component>()  // 动态加载

    private val productBarcodeLauncher = registerForActivityResult(ScanContract()) { result: ScanIntentResult ->
        if (result.contents == null) {
            Toast.makeText(this, "产品二维码扫描已取消", Toast.LENGTH_SHORT).show()
        } else {
            val rawSerial = result.contents
            val scannedSerial = SerialNormalizer.normalize(rawSerial)
            if (scannedSerial.isEmpty()) {
                Toast.makeText(this, "扫描内容无效，请重试", Toast.LENGTH_SHORT).show()
                return@registerForActivityResult
            }
            if (rawSerial != scannedSerial) {
                AppLogger.log("MainActivity", "Product serial normalized: rawLen=${rawSerial.length}, normalizedLen=${scannedSerial.length}")
            }
            currentProductSerial = scannedSerial
            tvProductSerial.text = scannedSerial
            productInfoLayout.visibility = View.VISIBLE
            btnPhotoCapture.visibility = View.VISIBLE  // 显示相机图标
            AppLogger.log("MainActivity", "Product QR Scanned: $scannedSerial")
            
            // Query existing record from network first
            queryExistingProductRecord(scannedSerial)
        }
    }

    // 检查是否所有组件都已扫描，若已完成则保存完整记录
    private fun checkAllComponentsScanned() {
        if (scannedComponents.size == componentsList.size) {
            AppLogger.log("MainActivity", "All components scanned: ${scannedComponents.size}/${componentsList.size}")
            Toast.makeText(this, "所有零部件已扫描，正在保存记录...", Toast.LENGTH_SHORT).show()
            saveCompleteProductRecord()
        } else {
            AppLogger.log(
                "MainActivity",
                "Scanned components: ${scannedComponents.size}/${componentsList.size}"
            )
        }
    }
    
    // 检查网络连接状态
    private fun isNetworkAvailable(): Boolean {
        val connectivityManager = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = connectivityManager.activeNetwork
        val capabilities = connectivityManager.getNetworkCapabilities(network)
        return capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
    }

    private val componentBarcodeLauncher = registerForActivityResult(ScanContract()) { result: ScanIntentResult ->
        if (result.contents == null) {
            Toast.makeText(this, "零部件二维码扫描已取消", Toast.LENGTH_SHORT).show()
        } else {
            currentScanningComponent?.let { component ->
                val rawSerial = result.contents
                val serialNumber = SerialNormalizer.normalize(rawSerial)
                if (serialNumber.isEmpty()) {
                    Toast.makeText(this, "扫描内容无效，请重试", Toast.LENGTH_SHORT).show()
                    return@let
                }
                if (rawSerial != serialNumber) {
                    AppLogger.log("MainActivity", "Component serial normalized: rawLen=${rawSerial.length}, normalizedLen=${serialNumber.length}")
                }
                AppLogger.log("MainActivity", "Component scanned: ${component.name} = $serialNumber")
                handleComponentInput(component, serialNumber)
            }
        }
    }

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            Toast.makeText(this, "相机权限已获取", Toast.LENGTH_SHORT).show()
        } else {
            Toast.makeText(this, "需要相机权限才能扫描二维码", Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // 强制使用白天模式
        androidx.appcompat.app.AppCompatDelegate.setDefaultNightMode(
            androidx.appcompat.app.AppCompatDelegate.MODE_NIGHT_NO
        )
        
        AppLogger.init(applicationContext)
        AppLogger.log("MainActivity", "onCreate - start new version")

        preferencesManager = PreferencesManager(this)
        projectManager = ProjectManager(this)
        projectConfigManager = ProjectConfigManager(this)
        unifiedDataManager = UnifiedDataManager.getInstance(this)
        enhancedQRScanner = EnhancedQRScanner(this)
        
        // Initialize LocalUserManager for login check
        localUserManager = com.testcenter.qrscanner.auth.LocalUserManager(this)
        
        // Initialize database and repository
        val database = TestDatabase.getDatabase(this)
        testRepository = TestRepository(database.testRecordDao())

        // 使用 LocalUserManager 检查登录状态（与 LoginActivity 保持一致）
        val isLoggedInByLocalUser = localUserManager.isLoggedIn()
        val isLoggedInByPrefs = preferencesManager.isLoggedIn()
        AppLogger.log("MainActivity", "isLoggedIn: LocalUserManager=$isLoggedInByLocalUser, PreferencesManager=$isLoggedInByPrefs")
        
        // 两者都需要为 true 才认为已登录，或者只要 LocalUserManager 认为已登录就行
        if (!isLoggedInByLocalUser) {
            AppLogger.log("MainActivity", "Not logged in (LocalUserManager). Redirecting to LoginActivity")
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
            return
        }

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        AppLogger.log("MainActivity", "contentView set for new layout")
        binding.tvVersionWatermarkMain.text = ApkUpdateManager.formatWatermarkLabel(
            BuildConfig.VERSION_NAME,
            BuildConfig.VERSION_CODE
        )

        setSupportActionBar(binding.toolbar)
        supportActionBar?.title = "物料记录系统"
        // Inflate the menu into the toolbar for items to be shown as actions
        binding.toolbar.inflateMenu(R.menu.menu_main)
        
        // Setup tab navigation
        setupTabNavigation() 

        productInfoLayout = binding.productInfoLayout
        syncProgressLayout = binding.syncProgressLayout
        syncProgressText = binding.syncProgressText
        tvProductSerial = binding.tvProductSerial
        recyclerViewComponents = binding.recyclerViewComponents
        // tvOperatorName removed - using login user automatically
        tvProjectCode = binding.tvProjectCode // Initialize the project code TextView
        tvProjectName = binding.tvProjectName // Initialize the project name TextView
        tvProductTypeName = binding.tvProductTypeName // Initialize the product type name TextView
        spinnerProductType = binding.spinnerProductType // Initialize the product type spinner
        btnPhotoCapture = binding.btnPhotoCapture // Initialize the photo capture button
        
        // 启动后台定时同步（30分钟一次，作为兜底机制）
        ConfigSyncScheduler.schedulePeriodicSync(this, intervalHours = 0, intervalMinutes = 30)

        binding.btnScanProduct.setOnClickListener {
            checkCameraPermissionAndScanProduct()
        }

        if (scanOnlyAutoMatchMode) {
            binding.btnManualInputProduct.visibility = View.GONE
        } else {
            binding.btnManualInputProduct.setOnClickListener {
                showManualInputDialog("产品序列号") { inputSerial ->
                    handleProductInput(inputSerial)
                }
            }
        }

        binding.btnQualityWorkbench.setOnClickListener {
            openQualityWorkbench()
        }

        // 相机按钮点击事件
        btnPhotoCapture.setOnClickListener {
            currentProductSerial?.let { serial ->
                val intent = Intent(this, PhotoCaptureActivity::class.java).apply {
                    putExtra(PhotoCaptureActivity.EXTRA_PRODUCT_SERIAL, serial)
                    putExtra(PhotoCaptureActivity.EXTRA_PROJECT_NAME, projectManager.getSelectedProject() ?: "")
                    putExtra(PhotoCaptureActivity.EXTRA_PRODUCT_TYPE, currentProductType)
                    putExtra(PhotoCaptureActivity.EXTRA_OPERATOR_NAME, getCurrentOperatorName())
                    putExtra(PhotoCaptureActivity.EXTRA_PROCESS_STEP_NAME, "产品拍照")
                    putExtra(PhotoCaptureActivity.EXTRA_CAPTURE_MODE, PhotoCaptureActivity.CaptureMode.MATERIAL)
                }
                startActivity(intent)
            } ?: run {
                Toast.makeText(this, "请先扫描产品二维码", Toast.LENGTH_SHORT).show()
            }
        }

        // Initialize LocalUserManager
        localUserManager = com.testcenter.qrscanner.auth.LocalUserManager(this)
        permissionService = com.testcenter.qrscanner.auth.PermissionService(localUserManager)

        setupRecyclerView()
        setupOptionsMenu() // Configure menu item clicks

        // Auto-load projects from server on startup
        loadInitialData()

        // Set initial project name and load configuration
        val selectedProject = projectManager.getSelectedProject()
        updateProjectDisplay(selectedProject)
        applyScanOnlyAutoMatchMode()
        
        // Load project configuration if project is selected
        if (selectedProject != null) {
            loadProjectConfiguration(selectedProject)
        }
        
        AppLogger.log("MainActivity", "onCreate completed")
    }
    
    private fun setupTabNavigation() {
        binding.tabLayout.addOnTabSelectedListener(object : TabLayout.OnTabSelectedListener {
            override fun onTabSelected(tab: TabLayout.Tab?) {
                when (tab?.position) {
                    0 -> {
                        // 物料记录选项卡 - 当前页面，无需操作
                        AppLogger.log("MainActivity", "Material record tab selected")
                    }
                    1 -> {
                        // 工序记录选项卡 - 跳转到工序记录页面
                        AppLogger.log("MainActivity", "Process record tab selected")
                        val intent = Intent(this@MainActivity, ProcessRecordActivity::class.java)
                        startActivity(intent)
                        // 重置选项卡到物料记录，因为我们跳转到了新页面
                        binding.tabLayout.getTabAt(0)?.select()
                    }
                    2 -> {
                        AppLogger.log("MainActivity", "Material inbound tab selected")
                        val intent = Intent(this@MainActivity, MaterialInboundActivity::class.java)
                        startActivity(intent)
                        binding.tabLayout.getTabAt(0)?.select()
                    }
                }
            }
            
            override fun onTabUnselected(tab: TabLayout.Tab?) {}
            override fun onTabReselected(tab: TabLayout.Tab?) {}
        })
        
        // 默认选中物料记录选项卡
        binding.tabLayout.getTabAt(0)?.select()
    }
    
    override fun onResume() {
        super.onResume()
        AppLogger.log("MainActivity", "onResume - checking for config updates")
        refreshProjectListCacheInBackground(force = true)
        
        // 应用恢复时检查配置更新
        val selectedProject = projectManager.getSelectedProject()
        if (selectedProject != null) {
            checkAndSyncConfigIfNeeded(selectedProject)
        }
        
        // 启动前台定期检查（5分钟一次）
        configCheckHandler.postDelayed(configCheckRunnable, configCheckInterval)
    }
    
    override fun onPause() {
        super.onPause()
        // 应用进入后台时停止定期检查，节省资源
        configCheckHandler.removeCallbacks(configCheckRunnable)
        AppLogger.log("MainActivity", "onPause - stopped periodic config check")
    }
    
    /**
     * 更新项目显示信息
     */
    private fun updateProjectDisplay(projectName: String?) {
        if (projectName != null) {
            // 从配置中获取项目号
            val projectCode = currentProjectConfig?.projectCode?.takeIf { it.isNotEmpty() } ?: projectName
            tvProjectCode.text = projectCode
            tvProjectName.text = projectName
        } else {
            tvProjectCode.text = "未选择"
            tvProjectName.text = "未选择项目"
        }
    }
    
    /**
     * 更新产品类型显示信息
     */
    private fun updateProductTypeDisplay(productTypeName: String?) {
        if (productTypeName != null) {
            val productTypeConfig = currentProjectConfig?.getProductTypeConfig(productTypeName)
            tvProductTypeName.text = productTypeConfig?.getDisplayName() ?: productTypeName
        } else {
            tvProductTypeName.text = "未选择"
        }
    }
    
    /**
     * 检查并同步配置（如果需要）
     * 静默检查，只在有更新时才提示
     */
    private fun checkAndSyncConfigIfNeeded(projectName: String) {
        lifecycleScope.launch {
            try {
                val fileManager = getFileManager()
                val result = projectConfigManager.syncConfigFromServer(projectName, fileManager, forceSync = false)
                
                when (result) {
                    is ProjectConfigManager.SyncResult.Success -> {
                        AppLogger.log("MainActivity", "Config updated in background (v${result.config.version})")
                        if (!currentProductSerial.isNullOrBlank() || scannedComponents.isNotEmpty()) {
                            AppLogger.log(
                                "MainActivity",
                                "Active record in progress, skip auto product-type reset after background sync"
                            )
                            return@launch
                        }

                        // 静默更新，重新加载配置但不显示 Toast
                        currentProjectConfig = result.config
                        updateProjectDisplay(projectName)
                        val previousProductType = currentProductType.trim()
                        productTypes = currentProjectConfig?.productTypes?.map { it.typeName }?.toTypedArray() ?: emptyArray()
                        if (productTypes.isNotEmpty()) {
                            currentProductType = if (
                                previousProductType.isNotEmpty() &&
                                productTypes.contains(previousProductType)
                            ) {
                                previousProductType
                            } else {
                                productTypes[0]
                            }
                            loadMaterialsForProductType(currentProductType)
                            updateProductTypeDisplay(currentProductType)
                        }
                        setupProductTypeSpinner()
                        setupRecyclerView()
                    }
                    is ProjectConfigManager.SyncResult.AlreadyLatest -> {
                        // 已是最新，无需操作
                    }
                    is ProjectConfigManager.SyncResult.Conflict -> {
                        // 有冲突，显示解决对话框
                        showConflictResolutionDialog(projectName, result)
                    }
                    else -> {
                        // 其他情况（NotFound, Error）不做处理
                    }
                }
            } catch (e: Exception) {
                AppLogger.log("MainActivity", "Background config check failed: ${e.message}")
            }
        }
    }

    private fun refreshProjectListCacheInBackground(force: Boolean = false) {
        projectManager.refreshProjectListCacheInBackground(
            force = force,
            maxCacheAgeMs = projectListRefreshInterval
        )
    }

    // This method ensures overflow menu items are also populated, 
    // but setOnMenuItemClickListener on toolbar handles all clicks.
    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.menu_main, menu)
        applyAdminMenuVisibility(menu)
        AppLogger.log("MainActivity", "onCreateOptionsMenu - menu_main.xml inflated for overflow menu")
        return true
    }

    override fun onPrepareOptionsMenu(menu: Menu): Boolean {
        applyAdminMenuVisibility(menu)
        applyAdminMenuVisibility(binding.toolbar.menu)
        return super.onPrepareOptionsMenu(menu)
    }

    private fun applyAdminMenuVisibility(menu: Menu?) {
        if (menu == null) return
        if (!::permissionService.isInitialized) return
        val isAdmin = permissionService.isCurrentUserAdmin()
        val adminOnlyItems = intArrayOf(
            R.id.action_manage_projects,
            R.id.action_project_config
        )
        for (itemId in adminOnlyItems) {
            menu.findItem(itemId)?.isVisible = isAdmin
        }
    }

    private fun ensureAdminOrWarn(): Boolean {
        if (!::permissionService.isInitialized) {
            Toast.makeText(this, "权限服务尚未初始化，请稍后重试", Toast.LENGTH_SHORT).show()
            return false
        }
        if (permissionService.isCurrentUserAdmin()) return true
        Toast.makeText(this, "该功能仅管理员可用", Toast.LENGTH_SHORT).show()
        return false
    }

    private fun setupOptionsMenu() {
        applyAdminMenuVisibility(binding.toolbar.menu)
        binding.toolbar.setOnMenuItemClickListener { item: MenuItem ->
            AppLogger.log("MainActivity", "Toolbar menu item clicked: ${item.title}")

            val adminOnlyItemIds = setOf(
                R.id.action_manage_projects,
                R.id.action_project_config
            )
            if (item.itemId in adminOnlyItemIds && !ensureAdminOrWarn()) {
                return@setOnMenuItemClickListener true
            }

            when (item.itemId) {
                R.id.action_logout -> {
                    showLogoutDialog()
                    true
                }
                R.id.action_manage_people -> {
                    showCurrentUserInfo()
                    true
                }
                // Handle other items from menu_main.xml if they were added to toolbar via inflateMenu
                 R.id.action_manual_input -> {
                    Toast.makeText(this, "手动输入功能待实现", Toast.LENGTH_SHORT).show()
                    true
                }
                R.id.action_filter_by_tester -> {
                    Toast.makeText(this, "按人员查询功能待实现", Toast.LENGTH_SHORT).show()
                    true
                }
                R.id.action_clear_filter -> {
                    Toast.makeText(this, "清除筛选功能待实现", Toast.LENGTH_SHORT).show()
                    true
                }
                R.id.action_manage_projects -> {
                    showProjectManagementDialog()
                    true
                }
                R.id.action_project_config -> {
                    showProjectConfigManagementDialog()
                    true
                }
                R.id.action_network_settings -> {
                    showNetworkSettingsDialog()
                    true
                }
                R.id.action_sync_config -> {
                    syncProjectConfiguration()
                    true
                }
                R.id.action_check_update -> {
                    checkForAppUpdates()
                    true
                }
                R.id.action_share_logs -> {
                    showLogActionsDialog()
                    true
                }
                R.id.action_inspection_report -> {
                    startActivity(Intent(this, InspectionReportActivity::class.java))
                    true
                }
                R.id.action_quality_workbench -> {
                    openQualityWorkbench()
                    true
                }
                R.id.action_batch_sync_configs -> {
                    batchSyncAllProjectConfigurations()
                    true
                }
                else -> false
            }
        }
    }

    private fun openQualityWorkbench() {
        startActivity(Intent(this, QualityWorkbenchActivity::class.java).apply {
            currentProductSerial?.let { putExtra(QualityWorkbenchActivity.EXTRA_SERIAL_NUMBER, it) }
        })
    }

    private suspend fun buildLogZipFile() = withContext(Dispatchers.IO) {
        withTimeout(20_000L) {
            AppLogger.createLogZip(this@MainActivity)
        }
    }

    private fun showLogActionsDialog() {
        MaterialAlertDialogBuilder(this)
            .setTitle("日志操作")
            .setItems(arrayOf("上传到服务器", "系统分享", "清除当前日志")) { _, which ->
                when (which) {
                    0 -> uploadLogsToServer()
                    1 -> shareLogs()
                    2 -> clearCurrentLogs()
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun clearCurrentLogs() {
        MaterialAlertDialogBuilder(this)
            .setTitle("清除当前日志")
            .setMessage("这会清空当前手机上的日志文件和临时日志压缩包，但不会删除已经上传到服务器的日志。确定继续吗？")
            .setPositiveButton("清除") { _, _ ->
                lifecycleScope.launch {
                    try {
                        val clearedCount = withContext(Dispatchers.IO) {
                            AppLogger.clearCurrentLogs(this@MainActivity)
                        }
                        Toast.makeText(
                            this@MainActivity,
                            "已清除当前日志（$clearedCount 个文件）",
                            Toast.LENGTH_SHORT
                        ).show()
                    } catch (e: Exception) {
                        AppLogger.log("MainActivity", "清除当前日志失败: ${e.message}", e)
                        Toast.makeText(
                            this@MainActivity,
                            "清除当前日志失败: ${e.message}",
                            Toast.LENGTH_LONG
                        ).show()
                    }
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun shareLogs() {
        lifecycleScope.launch {
            try {
                Toast.makeText(this@MainActivity, "正在打包日志...", Toast.LENGTH_SHORT).show()
                val zipFile = buildLogZipFile()
                if (zipFile == null) {
                    Toast.makeText(this@MainActivity, "没有可分享的日志文件", Toast.LENGTH_SHORT).show()
                    return@launch
                }
                val uri = androidx.core.content.FileProvider.getUriForFile(
                    this@MainActivity,
                    "${packageName}.fileprovider",
                    zipFile
                )
                val shareIntent = Intent(Intent.ACTION_SEND).apply {
                    type = "application/zip"
                    putExtra(Intent.EXTRA_STREAM, uri)
                    putExtra(Intent.EXTRA_SUBJECT, "QRTestScanner 日志")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                startActivity(Intent.createChooser(shareIntent, "分享日志"))
            } catch (e: TimeoutCancellationException) {
                AppLogger.log("MainActivity", "日志打包超时", e)
                Toast.makeText(this@MainActivity, "日志打包超时，请稍后重试", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                AppLogger.log("MainActivity", "日志分享失败: ${e.message}", e)
                Toast.makeText(this@MainActivity, "日志分享失败: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun uploadLogsToServer() {
        lifecycleScope.launch {
            try {
                Toast.makeText(this@MainActivity, "正在打包并上传日志...", Toast.LENGTH_SHORT).show()
                val zipFile = buildLogZipFile()
                if (zipFile == null) {
                    Toast.makeText(this@MainActivity, "没有可上传的日志文件", Toast.LENGTH_SHORT).show()
                    return@launch
                }

                val api = ApiClient.getApiService(this@MainActivity)
                val response = withContext(Dispatchers.IO) {
                    val zipBody = zipFile.asRequestBody("application/zip".toMediaType())
                    val filePart = MultipartBody.Part.createFormData("file", zipFile.name, zipBody)
                    api.uploadApkLogs(
                        file = filePart,
                        appVersionName = BuildConfig.VERSION_NAME.toRequestBody("text/plain".toMediaType()),
                        appVersionCode = BuildConfig.VERSION_CODE.toString().toRequestBody("text/plain".toMediaType()),
                        deviceModel = Build.MODEL.orEmpty().toRequestBody("text/plain".toMediaType()),
                        manufacturer = Build.MANUFACTURER.orEmpty().toRequestBody("text/plain".toMediaType()),
                        androidVersion = Build.VERSION.RELEASE.orEmpty().toRequestBody("text/plain".toMediaType()),
                    )
                }

                if (response.isSuccessful && response.body()?.success == true) {
                    val body = response.body()
                    val uploadedName = body?.record?.originalFilename ?: zipFile.name
                    AppLogger.log("MainActivity", "日志上传成功: $uploadedName")
                    Toast.makeText(
                        this@MainActivity,
                        body?.message ?: "日志上传成功",
                        Toast.LENGTH_LONG
                    ).show()
                } else {
                    val message = try {
                        response.errorBody()?.string()
                    } catch (_: Exception) {
                        null
                    }
                    AppLogger.log("MainActivity", "日志上传失败: code=${response.code()}, body=$message")
                    Toast.makeText(
                        this@MainActivity,
                        "日志上传失败: ${response.code()}",
                        Toast.LENGTH_LONG
                    ).show()
                }
            } catch (e: TimeoutCancellationException) {
                AppLogger.log("MainActivity", "日志上传打包超时", e)
                Toast.makeText(this@MainActivity, "日志打包超时，请稍后重试", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                AppLogger.log("MainActivity", "日志上传失败: ${e.message}", e)
                Toast.makeText(this@MainActivity, "日志上传失败: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun checkForAppUpdates() {
        if (!isNetworkAvailable()) {
            Toast.makeText(this, "网络不可用，无法检查更新", Toast.LENGTH_SHORT).show()
            return
        }

        val username = preferencesManager.getUsername()
        val password = preferencesManager.getPassword()
        if (username.isNullOrBlank() || password.isNullOrBlank()) {
            Toast.makeText(this, "未配置网络账户，无法检查更新", Toast.LENGTH_SHORT).show()
            return
        }

        val checkingDialog = MaterialAlertDialogBuilder(this)
            .setTitle("检查更新")
            .setMessage("正在检查，请稍候...")
            .setCancelable(false)
            .create()

        checkingDialog.show()

        lifecycleScope.launch {
            try {
                val fileManager = withContext(Dispatchers.IO) {
                    FileManagerFactory.create(this@MainActivity, username, password)
                }
                val result = apkUpdateManager.checkForUpdates(fileManager)
                checkingDialog.dismiss()
                when (result) {
                    is ApkUpdateManager.UpdateResult.NoUpdate -> {
                        MaterialAlertDialogBuilder(this@MainActivity)
                            .setTitle("已是最新版本")
                            .setMessage(apkUpdateManager.currentReleaseDisplayName())
                            .setPositiveButton("确定", null)
                            .show()
                    }
                    is ApkUpdateManager.UpdateResult.NewVersion -> {
                        showUpdateAvailableDialog(result.info, fileManager)
                    }
                    is ApkUpdateManager.UpdateResult.Error -> {
                        MaterialAlertDialogBuilder(this@MainActivity)
                            .setTitle("检查更新失败")
                            .setMessage(result.message)
                            .setPositiveButton("确定", null)
                            .show()
                    }
                }
            } catch (e: Exception) {
                checkingDialog.dismiss()
                MaterialAlertDialogBuilder(this@MainActivity)
                    .setTitle("检查更新失败")
                    .setMessage(e.message ?: "未知错误")
                    .setPositiveButton("确定", null)
                    .show()
            }
        }
    }

    private fun showUpdateAvailableDialog(info: ApkUpdateManager.UpdateInfo, fileManager: FileManager) {
        val message = buildString {
            appendLine("发现新版本：${info.formattedVersionLabel()}")
            appendLine("文件：${info.fileName}")
            appendLine("大小：${info.formattedSize()}")
            info.releaseNotes?.trim()?.takeIf { it.isNotEmpty() }?.let { notes ->
                appendLine()
                appendLine("更新说明：")
                appendLine(notes)
            }
        }

        MaterialAlertDialogBuilder(this)
            .setTitle("发现新版本")
            .setMessage(message.trim())
            .setPositiveButton("下载并安装") { _, _ ->
                downloadAndInstallUpdate(info, fileManager)
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun downloadAndInstallUpdate(info: ApkUpdateManager.UpdateInfo, fileManager: FileManager) {
        val downloadingDialog = MaterialAlertDialogBuilder(this)
            .setTitle("下载更新")
            .setMessage("正在下载 ${info.formattedVersionLabel()}...")
            .setCancelable(false)
            .create()

        downloadingDialog.show()

        lifecycleScope.launch {
            try {
                val apkFile = apkUpdateManager.downloadUpdate(fileManager, info)
                downloadingDialog.dismiss()

                if (apkUpdateManager.hasInstallPermission(this@MainActivity)) {
                    apkUpdateManager.installApk(this@MainActivity, apkFile)
                } else {
                    MaterialAlertDialogBuilder(this@MainActivity)
                        .setTitle("需要安装权限")
                        .setMessage("请允许安装未知来源应用以完成更新。")
                        .setPositiveButton("前往设置") { _, _ ->
                            startActivity(apkUpdateManager.buildInstallPermissionIntent(this@MainActivity))
                        }
                        .setNegativeButton("取消", null)
                        .show()
                }
            } catch (e: Exception) {
                downloadingDialog.dismiss()
                MaterialAlertDialogBuilder(this@MainActivity)
                    .setTitle("下载失败")
                    .setMessage(e.message ?: "未知错误")
                    .setPositiveButton("确定", null)
                    .show()
            }
        }
    }

    private fun setupRecyclerView() {
        componentAdapter = ComponentAdapter(
            componentsList,
            onScanClick = { component ->
                currentScanningComponent = component
                checkCameraPermissionAndScanComponent()
            },
            onManualInputClick = { component ->
                showManualInputDialog("${component.name}序列号") { inputSerial ->
                    handleComponentInput(component, inputSerial)
                }
            }
        )
        recyclerViewComponents.layoutManager = LinearLayoutManager(this)
        recyclerViewComponents.adapter = componentAdapter
        recyclerViewComponents.isNestedScrollingEnabled = false
        AppLogger.log("MainActivity", "RecyclerView for components setup")
    }

    private fun checkCameraPermissionAndScanProduct() {
        when {
            ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.CAMERA
            ) == PackageManager.PERMISSION_GRANTED -> {
                startProductQRScanner()
            }
            else -> {
                AppLogger.log("MainActivity", "Requesting camera permission for Product Scan")
                requestPermissionLauncher.launch(Manifest.permission.CAMERA)
            }
        }
    }

    private fun checkCameraPermissionAndScanComponent() {
        when {
            ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.CAMERA
            ) == PackageManager.PERMISSION_GRANTED -> {
                startComponentQRScanner()
            }
            else -> {
                AppLogger.log("MainActivity", "Requesting camera permission for Component Scan")
                requestPermissionLauncher.launch(Manifest.permission.CAMERA)
            }
        }
    }

    private fun startProductQRScanner() {
        AppLogger.log("MainActivity", "Launching Enhanced Product QR Scanner")
        val options = enhancedQRScanner.createEnhancedScanOptions("扫描产品二维码")
        productBarcodeLauncher.launch(options)
    }

    private fun startComponentQRScanner() {
        currentScanningComponent?.let {
            AppLogger.log("MainActivity", "Launching Enhanced Component QR Scanner for ${it.name}")
            val options = enhancedQRScanner.createEnhancedScanOptions("扫描 ${it.name} 二维码")
            componentBarcodeLauncher.launch(options)
        } ?: AppLogger.log("MainActivity", "Error: currentScanningComponent is null before component scan")
    }

    private fun showLogoutDialog() {
        AlertDialog.Builder(this)
            .setTitle("退出登录")
            .setMessage("确定要退出登录吗？")
            .setPositiveButton("确定") { _, _ ->
                AppLogger.log("MainActivity", "User confirmed logout")
                val currentUsername = localUserManager.getCurrentUser()?.synologyUsername
                preferencesManager.logout()
                localUserManager.clearSession()
                if (!currentUsername.isNullOrBlank()) {
                    localUserManager.clearUserPermissions(currentUsername)
                } else {
                    localUserManager.clearAllPermissions()
                }
                AppLogger.log("MainActivity", "Logout completed, local session cleared, redirecting to LoginActivity")
                val intent = Intent(this, LoginActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                }
                startActivity(intent)
                finish()
            }
            .setNegativeButton("取消", null)
            .show()
    }
    
    private fun showCurrentUserInfo() {
        val username = preferencesManager.getUsername() ?: "未知"
        val currentUser = localUserManager.getCurrentUser()
        
        val message = buildString {
            append("用户名：$username\n\n")
            
            if (currentUser != null) {
                append("显示名：${currentUser.displayName}\n")
                append("角色：${getRoleDisplayName(currentUser.role)}\n\n")
                
                append("移动端权限：\n")
                val mobilePermissions = mutableListOf<String>()
                if (permissionService.hasPermission(com.testcenter.qrscanner.auth.PermissionService.Permission.MOBILE_MATERIAL_RECORD)) {
                    mobilePermissions.add("✓ 物料记录")
                }
                if (permissionService.hasPermission(com.testcenter.qrscanner.auth.PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL)) {
                    mobilePermissions.add("✓ 修改物料")
                }
                if (permissionService.hasPermission(com.testcenter.qrscanner.auth.PermissionService.Permission.MOBILE_PROCESS_RECORD)) {
                    mobilePermissions.add("✓ 工序记录")
                }
                if (permissionService.hasPermission(com.testcenter.qrscanner.auth.PermissionService.Permission.MOBILE_CAMERA_ACCESS)) {
                    mobilePermissions.add("✓ 相机访问")
                }
                
                if (mobilePermissions.isEmpty()) {
                    append("  无移动端权限\n")
                } else {
                    mobilePermissions.forEach { append("  $it\n") }
                }
                
                append("\nWeb后台权限：\n")
                val webPermissions = mutableListOf<String>()
                if (permissionService.hasPermission(com.testcenter.qrscanner.auth.PermissionService.Permission.WEB_VIEW_RECORDS)) {
                    webPermissions.add("✓ 查看记录")
                }
                if (permissionService.hasPermission(com.testcenter.qrscanner.auth.PermissionService.Permission.WEB_MODIFY_RECORDS)) {
                    webPermissions.add("✓ 修改记录")
                }
                if (permissionService.hasPermission(com.testcenter.qrscanner.auth.PermissionService.Permission.WEB_DELETE_RECORDS)) {
                    webPermissions.add("✓ 删除记录")
                }
                if (permissionService.hasPermission(com.testcenter.qrscanner.auth.PermissionService.Permission.WEB_MANAGE_PROJECTS)) {
                    webPermissions.add("✓ 项目管理")
                }
                if (permissionService.hasPermission(com.testcenter.qrscanner.auth.PermissionService.Permission.WEB_MANAGE_USERS)) {
                    webPermissions.add("✓ 用户管理")
                }
                
                if (webPermissions.isEmpty()) {
                    append("  无Web后台权限")
                } else {
                    webPermissions.forEach { append("  $it\n") }
                }
            } else {
                append("角色：未知\n")
                append("权限：无法获取权限信息")
            }
        }
        
        MaterialAlertDialogBuilder(this)
            .setTitle("👤 当前账户信息")
            .setMessage(message)
            .setPositiveButton("确定", null)
            .show()
    }
    
    private fun getRoleDisplayName(role: com.testcenter.qrscanner.auth.LocalUserManager.UserRole): String {
        return when (role) {
            com.testcenter.qrscanner.auth.LocalUserManager.UserRole.ADMIN -> "管理员"
            com.testcenter.qrscanner.auth.LocalUserManager.UserRole.USER -> "普通用户"
        }
    }

    // showPersonnelManageDialog removed - operator uses login user automatically

    private fun startTestRecord(serialNumber: String) {
        val currentOperator = getCurrentOperatorName()
        
        lifecycleScope.launch {
            try {
                // Save to local database
                val testRecord = testRepository.startTest(serialNumber, currentOperator)
                AppLogger.log("MainActivity", "Test record created locally: ID=${testRecord.id}, Serial=$serialNumber, Operator=$currentOperator")
                
                // Save to network
                saveTestRecordToNetwork(testRecord)
                
            } catch (e: Exception) {
                AppLogger.log("MainActivity", "Failed to start test record for $serialNumber", e)
                Toast.makeText(this@MainActivity, "保存测试记录失败: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private suspend fun saveTestRecordToNetwork(testRecord: com.testcenter.qrscanner.data.TestRecord) {
        try {
            val username = preferencesManager.getUsername() ?: return
            val password = preferencesManager.getPassword() ?: return
            
            val fileManager = FileManagerFactory.create(this, username, password)
            
            // Create active test entry on server
            val success = fileManager.upsertActiveTest(
                testRecord.serialNumber,
                testRecord.tester,
                testRecord.startTime
            )
            
            if (success) {
                // Mark as synced in local database
                testRepository.markAsSynced(testRecord.id)
                AppLogger.log("MainActivity", "Test record synced to network: ${testRecord.serialNumber}")
                Toast.makeText(this, "测试记录已保存到网络", Toast.LENGTH_SHORT).show()
            } else {
                AppLogger.log("MainActivity", "Failed to sync test record to network: ${testRecord.serialNumber}")
                Toast.makeText(this, "网络保存失败，数据已保存到本地", Toast.LENGTH_SHORT).show()
            }
            
        } catch (e: Exception) {
            AppLogger.log("MainActivity", "Network save error for ${testRecord.serialNumber}", e)
            Toast.makeText(this, "网络保存异常: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun saveComponentData(componentName: String, serialNumber: String) {
        val productSerial = currentProductSerial ?: "未知产品"
        val productType = currentProductType
        val projectName = projectManager.getSelectedProject() ?: "未知项目"
        val currentOperator = getCurrentOperatorName()
        
        lifecycleScope.launch {
            try {
                AppLogger.log("MainActivity", "保存零部件数据: 产品=$productSerial, 零部件=$componentName, 序列号=$serialNumber")
                
                // 使用 REST API 直接保存（不再使用 CSV 格式）
                val apiResult = productRecordRepository.saveProductRecord(
                    productSerial = productSerial,
                    productType = productType,
                    projectName = projectName,
                    operator = currentOperator,
                    materials = scannedComponents,
                    allowBindingUpdate = shouldForceBindingUpdate(productSerial)
                )
                
                withContext(Dispatchers.Main) {
                    apiResult.fold(
                        onSuccess = {
                            AppLogger.log("MainActivity", "✓ 零部件数据已保存: $componentName")
                            clearPendingBindingUpdate(productSerial)
                            Toast.makeText(this@MainActivity, "✓ 零部件 $componentName 已保存", Toast.LENGTH_SHORT).show()
                        },
                        onFailure = { e ->
                            AppLogger.log("MainActivity", "REST API 保存失败: ${e.message}")
                            Toast.makeText(this@MainActivity, "⚠ 零部件保存失败: ${e.message}", Toast.LENGTH_SHORT).show()
                        }
                    )
                }
                
            } catch (e: Exception) {
                AppLogger.log("MainActivity", "Failed to save component data", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, "零部件数据保存失败: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun saveCompleteProductRecord() {
        val productSerial = currentProductSerial ?: return
        val productType = currentProductType
        val projectName = projectManager.getSelectedProject() ?: "未知项目"
        val currentOperator = getCurrentOperatorName()
        
        // 检查网络状态
        if (!isNetworkAvailable()) {
            Toast.makeText(this@MainActivity, "⚠ 网络不可用，请稍后重试", Toast.LENGTH_LONG).show()
            return
        }
        
        // 显示上传状态
        Toast.makeText(this@MainActivity, "正在保存完整产品记录...", Toast.LENGTH_SHORT).show()
        
        lifecycleScope.launch {
            try {
                // 使用 REST API 直接保存（不再使用 CSV 格式）
                val apiResult = productRecordRepository.saveProductRecord(
                    productSerial = productSerial,
                    productType = productType,
                    projectName = projectName,
                    operator = currentOperator,
                    materials = scannedComponents,
                    allowBindingUpdate = shouldForceBindingUpdate(productSerial)
                )
                
                withContext(Dispatchers.Main) {
                    apiResult.fold(
                        onSuccess = {
                            AppLogger.log("MainActivity", "✓ 完整产品记录已保存: $productSerial")
                            clearPendingBindingUpdate(productSerial)
                            Toast.makeText(this@MainActivity, "✓ 完整产品记录已保存", Toast.LENGTH_LONG).show()
                        },
                        onFailure = { e ->
                            AppLogger.log("MainActivity", "保存失败: ${e.message}")
                            Toast.makeText(this@MainActivity, "⚠ 保存失败: ${e.message}", Toast.LENGTH_LONG).show()
                        }
                    )
                }
                
            } catch (e: Exception) {
                AppLogger.log("MainActivity", "Failed to save complete product record", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, "❌ 保存失败: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    /**
     * 加载项目配置（优先从服务器同步）
     */
    private fun loadProjectConfiguration(projectName: String, onLoaded: (() -> Unit)? = null) {
        AppLogger.log("MainActivity", "Loading configuration for project: $projectName")
        
        // 显示进度指示器
        showSyncProgress("正在同步项目配置...")
        
        lifecycleScope.launch {
            try {
                // 获取 FileManager 实例
                val fileManager = getFileManager()
                
                // 优先从服务器加载配置
                currentProjectConfig = projectConfigManager.loadProjectConfigWithSync(projectName, fileManager)
                
                // ===== 详细日志：配置内容 =====
                AppLogger.log("MainActivity", "[CONFIG_DEBUG] Loaded config for project: ${currentProjectConfig?.projectName}")
                AppLogger.log("MainActivity", "[CONFIG_DEBUG] Config version: ${currentProjectConfig?.version}")
                AppLogger.log("MainActivity", "[CONFIG_DEBUG] Number of product types: ${currentProjectConfig?.productTypes?.size}")
                
                currentProjectConfig?.productTypes?.forEachIndexed { index, productType ->
                    AppLogger.log("MainActivity", "[CONFIG_DEBUG] ProductType[$index]: name='${productType.typeName}', materials=${productType.materials.size}")
                    productType.materials.forEachIndexed { mIndex, material ->
                        AppLogger.log("MainActivity", "[CONFIG_DEBUG]   Material[$mIndex]: name='${material.name}', partNumber='${material.partNumber}'")
                    }
                }
                // ===== 结束详细日志 =====
                
                // 更新产品类型列表
                val previousProductType = currentProductType.trim()
                productTypes = currentProjectConfig?.productTypes?.map { it.typeName }?.toTypedArray() ?: emptyArray()
                AppLogger.log("MainActivity", "[CONFIG_DEBUG] ProductTypes array: ${productTypes.joinToString(", ")}")
                
                // 更新项目显示
                updateProjectDisplay(projectName)
                
                // 如果有产品类型，设置第一个为默认
                if (productTypes.isNotEmpty()) {
                    currentProductType = if (
                        previousProductType.isNotEmpty() &&
                        productTypes.contains(previousProductType)
                    ) {
                        previousProductType
                    } else {
                        productTypes[0]
                    }
                    AppLogger.log("MainActivity", "[CONFIG_DEBUG] Setting default product type: $currentProductType")
                    // 加载该产品类型的物料列表
                    loadMaterialsForProductType(currentProductType)
                    // 更新产品类型显示
                    updateProductTypeDisplay(currentProductType)
                } else {
                    // 没有产品类型，清空物料列表
                    componentsList.clear()
                    updateProductTypeDisplay(null)
                }
                
                // 更新UI
                setupProductTypeSpinner()
                setupRecyclerView()
                
                AppLogger.log("MainActivity", "Loaded ${productTypes.size} product types, ${componentsList.size} materials")
                
                // 隐藏进度指示器
                hideSyncProgress()
                Toast.makeText(this@MainActivity, "✓ 配置加载成功", Toast.LENGTH_SHORT).show()
                onLoaded?.invoke()
            } catch (e: Exception) {
                AppLogger.log("MainActivity", "Error loading project configuration: ${e.message}", e)
                
                // 失败时使用本地配置
                currentProjectConfig = projectConfigManager.loadProjectConfig(projectName)
                val previousProductType = currentProductType.trim()
                productTypes = currentProjectConfig?.productTypes?.map { it.typeName }?.toTypedArray() ?: emptyArray()
                
                // 更新项目显示
                updateProjectDisplay(projectName)
                
                if (productTypes.isNotEmpty()) {
                    currentProductType = if (
                        previousProductType.isNotEmpty() &&
                        productTypes.contains(previousProductType)
                    ) {
                        previousProductType
                    } else {
                        productTypes[0]
                    }
                    loadMaterialsForProductType(currentProductType)
                    // 更新产品类型显示
                    updateProductTypeDisplay(currentProductType)
                } else {
                    componentsList.clear()
                    updateProductTypeDisplay(null)
                }
                
                setupProductTypeSpinner()
                setupRecyclerView()
                
                // 隐藏进度指示器
                hideSyncProgress()
                Toast.makeText(this@MainActivity, "⚠ 配置加载失败，使用本地缓存", Toast.LENGTH_SHORT).show()
                onLoaded?.invoke()
            }
        }
    }
    
    /**
     * 手动同步项目配置
     */
    private fun syncProjectConfiguration(forceSync: Boolean = true) {
        val projectName = projectManager.getSelectedProject()
        if (projectName == null) {
            Toast.makeText(this, "请先选择项目", Toast.LENGTH_SHORT).show()
            return
        }
        
        AppLogger.log("MainActivity", "Manual sync configuration for project: $projectName (force=$forceSync)")
        showSyncProgress("正在同步配置...")
        
        lifecycleScope.launch {
            try {
                val fileManager = getFileManager()
                val result = projectConfigManager.syncConfigFromServer(projectName, fileManager, forceSync)
                
                hideSyncProgress()
                
                when (result) {
                    is ProjectConfigManager.SyncResult.Success -> {
                        Toast.makeText(this@MainActivity, "✓ 配置同步成功 (v${result.config.version})", Toast.LENGTH_SHORT).show()
                        // 重新加载配置
                        loadProjectConfiguration(projectName)
                    }
                    is ProjectConfigManager.SyncResult.AlreadyLatest -> {
                        Toast.makeText(this@MainActivity, "✓ 已是最新版本 (v${result.config.version})", Toast.LENGTH_SHORT).show()
                    }
                    is ProjectConfigManager.SyncResult.Conflict -> {
                        // 检测到冲突，显示解决对话框
                        showConflictResolutionDialog(projectName, result)
                    }
                    is ProjectConfigManager.SyncResult.NotFound -> {
                        Toast.makeText(this@MainActivity, "✗ 服务器无配置文件", Toast.LENGTH_SHORT).show()
                    }
                    is ProjectConfigManager.SyncResult.Error -> {
                        Toast.makeText(this@MainActivity, "✗ 同步失败: ${result.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                hideSyncProgress()
                AppLogger.log("MainActivity", "Error syncing configuration: ${e.message}", e)
                Toast.makeText(this@MainActivity, "✗ 配置同步失败: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }
    
    /**
     * 显示同步进度指示器
     */
    private fun showSyncProgress(message: String) {
        if (android.os.Looper.myLooper() == android.os.Looper.getMainLooper()) {
            syncProgressText.text = message
            syncProgressLayout.visibility = View.VISIBLE
        } else {
            runOnUiThread {
                syncProgressText.text = message
                syncProgressLayout.visibility = View.VISIBLE
            }
        }
    }
    
    /**
     * 隐藏同步进度指示器
     */
    private fun hideSyncProgress() {
        if (android.os.Looper.myLooper() == android.os.Looper.getMainLooper()) {
            syncProgressLayout.visibility = View.GONE
        } else {
            runOnUiThread {
                syncProgressLayout.visibility = View.GONE
            }
        }
    }
    
    /**
     * 批量同步所有项目配置
     */
    private fun batchSyncAllProjectConfigurations() {
        AppLogger.log("MainActivity", "Starting batch sync for all projects")
        
        lifecycleScope.launch {
            try {
                // 获取所有项目
                val projects = projectManager.getProjectList()
                if (projects.isEmpty()) {
                    Toast.makeText(this@MainActivity, "没有可同步的项目", Toast.LENGTH_SHORT).show()
                    return@launch
                }
                
                val fileManager = getFileManager()
                
                showSyncProgress("准备批量同步 ${projects.size} 个项目...")
                
                // 执行批量同步
                val batchResult = projectConfigManager.batchSyncConfigs(
                    projectNames = projects,
                    fileManager = fileManager,
                    forceSync = false,
                    onProgress = { current: Int, total: Int, projectName: String, result: ProjectConfigManager.SyncResult ->
                        val statusIcon = when (result) {
                            is ProjectConfigManager.SyncResult.Success -> "✓"
                            is ProjectConfigManager.SyncResult.AlreadyLatest -> "="
                            is ProjectConfigManager.SyncResult.NotFound -> "?"
                            is ProjectConfigManager.SyncResult.Error -> "✗"
                            is ProjectConfigManager.SyncResult.Conflict -> "!"
                        }
                        showSyncProgress("[$current/$total] $statusIcon $projectName")
                    }
                )
                
                hideSyncProgress()
                
                // 显示结果
                val summary = batchResult.getSummary()
                AppLogger.log("MainActivity", "Batch sync completed: $summary")
                
                MaterialAlertDialogBuilder(this@MainActivity)
                    .setTitle("批量同步完成")
                    .setMessage(summary as CharSequence)
                    .setPositiveButton("确定") { dialog: DialogInterface, _: Int ->
                        dialog.dismiss()
                    }
                    .show()
                
            } catch (e: Exception) {
                hideSyncProgress()
                AppLogger.log("MainActivity", "Batch sync error: ${e.message}", e)
                Toast.makeText(this@MainActivity, "批量同步失败: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }
    
    /**
     * 显示冲突解决对话框
     */
    private fun showConflictResolutionDialog(projectName: String, conflict: ProjectConfigManager.SyncResult.Conflict) {
        val options = arrayOf(
            "使用服务器版本 (v${conflict.serverConfig.version})",
            "使用本地版本 (v${conflict.localConfig.version})",
            "智能合并"
        )
        
        AlertDialog.Builder(this)
            .setTitle("配置冲突")
            .setMessage("项目 \"$projectName\" 的配置在本地和服务器上都有修改，请选择如何处理：")
            .setItems(options) { _, which ->
                val strategy = when (which) {
                    0 -> ProjectConfigManager.ConflictResolutionStrategy.USE_SERVER
                    1 -> ProjectConfigManager.ConflictResolutionStrategy.USE_LOCAL
                    2 -> ProjectConfigManager.ConflictResolutionStrategy.MERGE
                    else -> ProjectConfigManager.ConflictResolutionStrategy.USE_SERVER
                }
                
                resolveConfigConflict(projectName, strategy)
            }
            .setNegativeButton("取消", null)
            .show()
    }
    
    /**
     * 解决配置冲突
     */
    private fun resolveConfigConflict(projectName: String, strategy: ProjectConfigManager.ConflictResolutionStrategy) {
        showSyncProgress("正在解决冲突...")
        
        lifecycleScope.launch {
            try {
                val fileManager = getFileManager()
                val resolvedConfig = projectConfigManager.resolveConflict(projectName, strategy, fileManager)
                
                hideSyncProgress()
                
                if (resolvedConfig != null) {
                    Toast.makeText(this@MainActivity, "✓ 冲突已解决 (v${resolvedConfig.version})", Toast.LENGTH_SHORT).show()
                    // 重新加载配置
                    loadProjectConfiguration(projectName)
                } else {
                    Toast.makeText(this@MainActivity, "✗ 冲突解决失败", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                hideSyncProgress()
                AppLogger.log("MainActivity", "Error resolving conflict: ${e.message}", e)
                Toast.makeText(this@MainActivity, "✗ 冲突解决失败: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }
    
    /**
     * 获取 FileManager 实例
     */
    private fun getFileManager(): FileManager {
        return FileManagerFactory.create(
            this,
            preferencesManager.getUsername(),
            preferencesManager.getPassword()
        )
    }
    
    /**
     * 加载指定产品类型的物料列表
     */
    private fun loadMaterialsForProductType(productTypeName: String) {
        AppLogger.log("MainActivity", "Loading materials for product type: $productTypeName")
        
        val productTypeConfig = currentProjectConfig?.getProductTypeConfig(productTypeName)
        
        // ===== 详细日志：产品类型配置 =====
        AppLogger.log("MainActivity", "[MATERIAL_DEBUG] Looking for product type: '$productTypeName'")
        AppLogger.log("MainActivity", "[MATERIAL_DEBUG] ProductTypeConfig found: ${productTypeConfig != null}")
        
        if (productTypeConfig != null) {
            AppLogger.log("MainActivity", "[MATERIAL_DEBUG] ProductTypeConfig.typeName: '${productTypeConfig.typeName}'")
            AppLogger.log("MainActivity", "[MATERIAL_DEBUG] ProductTypeConfig.materials count: ${productTypeConfig.materials.size}")
            AppLogger.log("MainActivity", "[MATERIAL_DEBUG] ProductTypeConfig.forceVersionCheck: ${productTypeConfig.forceVersionCheck}")
            productTypeConfig.materials.forEachIndexed { index, material ->
                AppLogger.log(
                    "MainActivity",
                    "[MATERIAL_DEBUG]   Material[$index]: name='${material.name}', partNumber='${material.partNumber}', qrRuleType='${material.qrRuleType}', expectedVersion='${material.expectedVersion}'"
                )
            }
        } else {
            AppLogger.log("MainActivity", "[MATERIAL_DEBUG] ERROR: ProductTypeConfig is NULL for '$productTypeName'")
            AppLogger.log("MainActivity", "[MATERIAL_DEBUG] Available product types in config:")
            currentProjectConfig?.productTypes?.forEach { pt ->
                AppLogger.log("MainActivity", "[MATERIAL_DEBUG]   - '${pt.typeName}'")
            }
        }
        // ===== 结束详细日志 =====
        
        componentsList.clear()
        productTypeConfig?.materials?.forEach { material ->
            componentsList.add(
                Component(
                    name = material.name,
                    partNumber = material.partNumber,
                    serial = "待扫描",
                    qrRuleType = material.normalizedQrRuleType(),
                    expectedVersion = material.normalizedExpectedVersion(),
                    forceVersionCheck = productTypeConfig.forceVersionCheck
                )
            )
        }
        
        // ===== 详细日志：最终物料列表 =====
        AppLogger.log("MainActivity", "[MATERIAL_DEBUG] Final componentsList size: ${componentsList.size}")
        componentsList.forEachIndexed { index, component ->
            AppLogger.log("MainActivity", "[MATERIAL_DEBUG]   Component[$index]: name='${component.name}', partNumber='${component.partNumber}'")
        }
        // ===== 结束详细日志 =====
        
        // 通知适配器数据变化
        if (::componentAdapter.isInitialized) {
            componentAdapter.notifyDataSetChanged()
        }
        
        AppLogger.log("MainActivity", "Loaded ${componentsList.size} materials")
    }
    
    private fun setupProductTypeSpinner() {
        if (productTypes.isEmpty()) {
            AppLogger.log("MainActivity", "No product types available")
            return
        }

        val displayNames = currentProjectConfig?.productTypes
            ?.map { it.getDisplayName() }
            ?.toTypedArray()
            ?: productTypes

        val adapter = ArrayAdapter(this, R.layout.spinner_compact_selected_item, displayNames)
        adapter.setDropDownViewResource(R.layout.spinner_compact_dropdown_item)
        spinnerProductType.adapter = adapter
        
        // Set default selection
        val currentIndex = productTypes.indexOf(currentProductType).takeIf { it >= 0 } ?: 0
        spinnerProductType.setSelection(currentIndex)
        
        spinnerProductType.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val newProductType = productTypes[position]
                
                // 检测产品类型切换
                if (
                    !suppressProductTypeSwitchCheck &&
                    currentProductType.isNotEmpty() &&
                    currentProductType != newProductType &&
                    !currentProductSerial.isNullOrEmpty()
                ) {
                    // 产品类型切换，需要保存当前记录并清空
                    showProductTypeSwitchConfirmation(newProductType)
                    return
                }
                
                currentProductType = newProductType
                AppLogger.log("MainActivity", "Product type selected: $currentProductType")
                AppLogger.log("MainActivity", "[SPINNER_DEBUG] Selected position: $position, typeName: '$currentProductType'")
                Toast.makeText(this@MainActivity, "已选择产品: $currentProductType", Toast.LENGTH_SHORT).show()
                
                // 更新产品类型显示
                updateProductTypeDisplay(currentProductType)
                
                // 加载该产品类型的物料列表
                loadMaterialsForProductType(currentProductType)
                
                // 清空已扫描的组件数据
                scannedComponents.clear()
            }
            
            override fun onNothingSelected(parent: AdapterView<*>?) {
                // Do nothing
            }
        }

        spinnerProductType.isEnabled = !scanOnlyAutoMatchMode
        spinnerProductType.isClickable = !scanOnlyAutoMatchMode
        spinnerProductType.isFocusable = !scanOnlyAutoMatchMode
        spinnerProductType.alpha = if (scanOnlyAutoMatchMode) 0.7f else 1f
    }

    private fun applyScanOnlyAutoMatchMode() {
        if (!scanOnlyAutoMatchMode) {
            tvProjectCode.setOnClickListener {
                showProjectSelectionDialog()
            }
            tvProjectName.setOnClickListener {
                showProjectSelectionDialog()
            }
            spinnerProductType.isEnabled = true
            spinnerProductType.isClickable = true
            spinnerProductType.isFocusable = true
            spinnerProductType.alpha = 1f
            return
        }

        AppLogger.log("MainActivity", "Scan-only auto-match mode enabled")
        tvProjectCode.setOnClickListener(null)
        tvProjectName.setOnClickListener(null)
        tvProjectCode.isClickable = false
        tvProjectCode.isFocusable = false
        tvProjectName.isClickable = false
        tvProjectName.isFocusable = false
        tvProjectCode.alpha = 0.7f
        tvProjectName.alpha = 0.7f
        spinnerProductType.isEnabled = false
        spinnerProductType.isClickable = false
        spinnerProductType.isFocusable = false
        spinnerProductType.alpha = 0.7f
    }
    
    private fun showManualInputDialog(title: String, onInput: (String) -> Unit) {
        val editText = EditText(this)
        editText.hint = "请输入$title"
        
        AlertDialog.Builder(this)
            .setTitle("手动输入$title")
            .setView(editText)
            .setPositiveButton("确定") { _, _ ->
                val input = editText.text.toString().trim()
                if (input.isNotEmpty()) {
                    onInput(input)
                } else {
                    Toast.makeText(this, "输入不能为空", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun handleProductInput(serialNumber: String) {
        // Check if product is being switched
        if (!currentProductSerial.isNullOrEmpty() && currentProductSerial != serialNumber) {
            // Product is being switched, require confirmation
            showProductSwitchConfirmation(serialNumber)
            return
        }
        
        // Same product or first scan
        currentProductSerial = serialNumber
        tvProductSerial.text = serialNumber
        productInfoLayout.visibility = View.VISIBLE
        btnPhotoCapture.visibility = View.VISIBLE  // 显示相机图标
        AppLogger.log("MainActivity", "Product input: $serialNumber")
        
        // Query existing record from network first
        queryExistingProductRecord(serialNumber)
    }
    
    private fun showProductSwitchConfirmation(newSerialNumber: String) {
        AlertDialog.Builder(this)
            .setTitle("产品切换检测")
            .setMessage("检测到产品切换：\n\n当前产品: $currentProductSerial\n新产品: $newSerialNumber\n\n请重新扫描新产品的二维码以确认切换")
            .setPositiveButton("确认切换") { _, _ ->
                // User confirmed, switch to new product
                AppLogger.log("MainActivity", "Product switch confirmed: $currentProductSerial -> $newSerialNumber")
                currentProductSerial = newSerialNumber
                tvProductSerial.text = newSerialNumber
                productInfoLayout.visibility = View.VISIBLE
                btnPhotoCapture.visibility = View.VISIBLE  // 显示相机图标
                queryExistingProductRecord(newSerialNumber)
            }
            .setNegativeButton("取消", null)
            .setCancelable(false)
            .show()
    }
    
    private fun showProductTypeSwitchConfirmation(newProductType: String) {
        AlertDialog.Builder(this)
            .setTitle("产品类型切换检测")
            .setMessage("检测到产品类型切换：\n\n当前产品: $currentProductSerial\n当前类型: $currentProductType\n新类型: $newProductType\n\n是否保存当前记录并切换到新类型？")
            .setPositiveButton("保存并切换") { _, _ ->
                lifecycleScope.launch {
                    try {
                        // 保存当前产品记录
                        if (!currentProductSerial.isNullOrEmpty() && scannedComponents.isNotEmpty()) {
                            AppLogger.log("MainActivity", "Saving current product record before type switch: $currentProductSerial")
                            saveCompleteProductRecord()
                            Toast.makeText(this@MainActivity, "已保存产品 $currentProductSerial 的记录", Toast.LENGTH_SHORT).show()
                        }
                        
                        // 切换产品类型
                        currentProductType = newProductType
                        AppLogger.log("MainActivity", "Product type switched to: $newProductType")
                        
                        // 清空当前产品信息
                        currentProductSerial = ""
                        tvProductSerial.text = "待扫描"
                        productInfoLayout.visibility = View.GONE
                        scannedComponents.clear()
                        
                        // 加载新产品类型的物料
                        loadMaterialsForProductType(newProductType)
                        
                        // 更新Spinner选择
                        val availableProductTypes = currentProjectConfig?.productTypes?.map { it.typeName } ?: emptyList()
                        val newIndex = availableProductTypes.indexOf(newProductType)
                        if (newIndex >= 0) {
                            spinnerProductType.setSelection(newIndex)
                        }
                        
                        Toast.makeText(this@MainActivity, "已切换到产品类型: $newProductType\n请扫描新产品的二维码", Toast.LENGTH_LONG).show()
                    } catch (e: Exception) {
                        AppLogger.log("MainActivity", "Error switching product type", e)
                        Toast.makeText(this@MainActivity, "切换失败: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            .setNegativeButton("取消") { _, _ ->
                // 恢复原来的产品类型选择
                val availableProductTypes = currentProjectConfig?.productTypes?.map { it.typeName } ?: emptyList()
                val currentIndex = availableProductTypes.indexOf(currentProductType)
                if (currentIndex >= 0) {
                    spinnerProductType.setSelection(currentIndex)
                }
            }
            .setCancelable(false)
            .show()
    }

    private fun handleComponentInput(component: Component, serialNumber: String) {
        val validationResult = MaterialQrCodeValidator.validate(component, serialNumber)
        if (!validationResult.isValid) {
            val errorMessage = validationResult.message ?: "二维码校验失败"
            AppLogger.log(
                "MainActivity",
                "[物料校验] 拒绝写入: component=${component.name}, serial=$serialNumber, rule=${component.qrRuleType}, expectedVersion=${component.expectedVersion}, force=${component.forceVersionCheck}, reason=$errorMessage"
            )
            Toast.makeText(this, "⚠ ${component.name}: $errorMessage", Toast.LENGTH_LONG).show()
            return
        }

        if (!validationResult.detectedVersion.isNullOrBlank()) {
            AppLogger.log(
                "MainActivity",
                "[物料校验] 版本校验通过: component=${component.name}, detectedVersion=${validationResult.detectedVersion}"
            )
        }

        // 关键修复：检查的是"这个组件"是否已有值，而不是"产品记录"是否存在
        // 如果组件原本为空，则是"新增"操作，不需要修改权限
        // 如果组件原本有值，则是"修改"操作，需要修改权限
        
        val existingValue = component.serial
        val isModification = !existingValue.isNullOrBlank() && existingValue != "待扫描"
        
        AppLogger.log("MainActivity", "[权限检查] 组件: ${component.name}, 现有值: '$existingValue', 是否修改: $isModification")
        
        if (isModification) {
            // 修改已有值，需要检查修改权限
            lifecycleScope.launch {
                try {
                    val authService = com.testcenter.qrscanner.auth.AuthenticationService(this@MainActivity)
                    authService.initialize()
                    val hasPermission = authService.hasPermission(
                        com.testcenter.qrscanner.auth.PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL
                    )
                    
                    AppLogger.log("MainActivity", "[权限检查] 修改权限: $hasPermission")
                    
                    if (!hasPermission) {
                        withContext(Dispatchers.Main) {
                            AppLogger.log("MainActivity", "[权限拒绝] 用户没有修改已存在物料的权限")
                            Toast.makeText(
                                this@MainActivity,
                                "⚠️ 该组件已有值 (${existingValue})，您没有修改权限",
                                Toast.LENGTH_LONG
                            ).show()
                        }
                        return@launch
                    }
                    
                    AppLogger.log("MainActivity", "[权限通过] 允许修改已存在的物料")
                    withContext(Dispatchers.Main) {
                        proceedWithComponentInput(component, serialNumber)
                    }
                } catch (e: Exception) {
                    AppLogger.log("MainActivity", "[权限检查] 检查失败: ${e.message}", e)
                    withContext(Dispatchers.Main) {
                        // 网络错误时允许操作（降级策略）
                        AppLogger.log("MainActivity", "[权限检查] 网络错误，使用降级策略允许操作")
                        proceedWithComponentInput(component, serialNumber)
                    }
                }
            }
        } else {
            // 新增值，不需要修改权限，直接处理
            AppLogger.log("MainActivity", "[权限检查] 组件为空，是新增操作，无需检查修改权限")
            proceedWithComponentInput(component, serialNumber)
        }
    }
    
    private fun proceedWithComponentInput(component: Component, serialNumber: String) {
        component.serial = serialNumber
        scannedComponents[component.name] = serialNumber
        componentAdapter.notifyItemChanged(componentsList.indexOf(component))
        AppLogger.log("MainActivity", "Component ${component.name} manually input: $serialNumber")
        
        // Save individual component update to network immediately
        // (manual input path used to call two save APIs and caused duplicate writes)
        saveComponentUpdateToNetwork(component.name, serialNumber)
        
        // Check if all components are scanned and save complete record
        if (scannedComponents.size == componentsList.size) {
            saveCompleteProductRecord()
        }
    }

    private fun getRuleMatchCandidateProjects(): List<String> {
        return buildList {
            addAll(projectManager.getProjectList())
            addAll(projectConfigManager.getCachedProjectNames())
            projectManager.getSelectedProject()?.let { add(it) }
            currentProjectConfig?.projectName?.let { add(it) }
        }
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .distinct()
    }

    private fun handleRuleMatchFailure(serialNumber: String, message: String) {
        AppLogger.log("MainActivity", "[规则匹配] $message, serial=$serialNumber")
        scannedComponents.clear()
        componentsList.clear()
        componentAdapter.notifyDataSetChanged()
        currentProjectConfig = null
        currentProductType = ""
        updateProjectDisplay(null)
        updateProductTypeDisplay(null)
        btnPhotoCapture.visibility = View.GONE
        Toast.makeText(this@MainActivity, message, Toast.LENGTH_SHORT).show()
    }

    private suspend fun resolveSerialRuleMatchesFromServer(
        serialNumber: String
    ): List<ProjectConfigManager.SerialRuleMatch> {
        return try {
            val response = withContext(Dispatchers.IO) {
                ApiClient.getApiService(this@MainActivity).resolveSerialRule(serialNumber)
            }
            if (!response.isSuccessful) {
                AppLogger.log(
                    "MainActivity",
                    "[规则匹配] 服务端前缀规则解析失败: HTTP ${response.code()}"
                )
                return emptyList()
            }

            val body = response.body()
            if (body?.success != true) {
                AppLogger.log(
                    "MainActivity",
                    "[规则匹配] 服务端前缀规则解析失败: ${body?.error ?: "unknown"}"
                )
                return emptyList()
            }

            body.data?.matches
                ?.mapNotNull { match ->
                    val projectName = match.projectName?.trim().orEmpty()
                    val productType = match.productType?.trim().orEmpty()
                    val prefix = match.prefix?.trim().orEmpty()
                    if (projectName.isEmpty() || productType.isEmpty() || prefix.isEmpty()) {
                        null
                    } else {
                        ProjectConfigManager.SerialRuleMatch(
                            projectName = projectName,
                            productType = productType,
                            prefix = prefix,
                            length = match.length ?: prefix.length
                        )
                    }
                }
                ?: emptyList()
        } catch (e: Exception) {
            AppLogger.log("MainActivity", "[规则匹配] 服务端前缀规则解析异常: ${e.message}", e)
            emptyList()
        }
    }

    private fun queryExistingProductRecord(serialNumber: String) {
        lifecycleScope.launch {
            try {
                val normalizedSerial = SerialNormalizer.normalize(serialNumber)
                if (normalizedSerial.isEmpty()) {
                    Toast.makeText(this@MainActivity, "序列号无效，请重试", Toast.LENGTH_SHORT).show()
                    return@launch
                }

                AppLogger.log("MainActivity", "查询产品记录: $normalizedSerial")

                val candidateProjects = getRuleMatchCandidateProjects()
                val recordDeferred = async {
                    productRecordRepository.queryProductRecord(normalizedSerial)
                }

                var ruleMatches = resolveSerialRuleMatchesFromServer(normalizedSerial)
                if (ruleMatches.isEmpty()) {
                    ruleMatches = projectConfigManager.resolveSerialRuleMatches(
                        serialNumber = normalizedSerial,
                        projectNames = candidateProjects
                    )
                }

                if (ruleMatches.isEmpty()) {
                    val fileManager = withContext(Dispatchers.IO) { getFileManager() }
                    ruleMatches = projectConfigManager.resolveSerialRuleMatchesWithSync(
                        serialNumber = normalizedSerial,
                        projectNames = candidateProjects,
                        fileManager = fileManager
                    )
                }

                if (ruleMatches.isNotEmpty()) {
                    AppLogger.log(
                        "MainActivity",
                        "规则命中: serial=$normalizedSerial, matches=${ruleMatches.joinToString { "${it.projectName}/${it.productType}:${it.prefix}" }}"
                    )
                }
                val recordResult = recordDeferred.await()

                val existingRecord = recordResult.getOrElse { e ->
                    AppLogger.log("MainActivity", "查询记录失败: ${e.message}", e)
                    null
                }

                if (ruleMatches.size == 1) {
                    val ruleMatch = ruleMatches.first()
                    val ruleCandidate = listOf(
                        com.testcenter.qrscanner.api.SerialRecommendationCandidate(
                            projectName = ruleMatch.projectName,
                            productType = ruleMatch.productType,
                            confidence = 1.0,
                            source = "serial_rule:${ruleMatch.prefix}"
                        )
                    )
                    applySelectionAndContinue(
                        serialNumber = normalizedSerial,
                        targetProject = ruleMatch.projectName,
                        targetProductType = ruleMatch.productType,
                        existingRecord = existingRecord,
                        learningSource = "serial_rule_only",
                        conflict = false,
                        candidates = ruleCandidate
                    )
                    return@launch
                }

                if (ruleMatches.size > 1) {
                    handleRuleMatchFailure(normalizedSerial, "扫码命中多个规则，请检查项目配置")
                    return@launch
                }

                handleRuleMatchFailure(normalizedSerial, "未匹配到项目规则，请检查二维码规则配置")
            } catch (e: Exception) {
                AppLogger.log("MainActivity", "查询异常: $serialNumber", e)
                handleRuleMatchFailure(serialNumber, "规则匹配异常，请稍后重试")
            }
        }
    }

    private fun handleSerialRecommendationAndLoad(
        serialNumber: String,
        existingRecord: FileManager.ProductRecord?,
        recommendation: ProductRecordRepository.SerialRecommendation?
    ) {
        if (recommendation == null) {
            finalizeRecordLoading(serialNumber, existingRecord)
            return
        }

        val hasConflict =
            recommendation.candidates.size > 1 ||
                (
                    recommendation.shouldConfirm &&
                        recommendation.reason != "low_confidence" &&
                        recommendation.autoApply != true
                )

        if (hasConflict) {
            showSerialConflictConfirmationDialog(serialNumber, existingRecord, recommendation)
            return
        }

        applySelectionAndContinue(
            serialNumber = serialNumber,
            targetProject = recommendation.recommendedProjectName,
            targetProductType = recommendation.recommendedProductType,
            existingRecord = existingRecord,
            learningSource = if (recommendation.autoApply) "auto_recommend" else "history_recommend",
            conflict = false,
            candidates = recommendation.candidates
        )
    }

    private fun showSerialConflictConfirmationDialog(
        serialNumber: String,
        existingRecord: FileManager.ProductRecord?,
        recommendation: ProductRecordRepository.SerialRecommendation
    ) {
        val currentProject = projectManager.getSelectedProject().orEmpty()
        val currentType = currentProductType

        val candidates = recommendation.candidates.toMutableList()
        if (candidates.none {
                it.projectName == recommendation.recommendedProjectName &&
                    it.productType == recommendation.recommendedProductType
            }) {
            candidates.add(
                com.testcenter.qrscanner.api.SerialRecommendationCandidate(
                    projectName = recommendation.recommendedProjectName,
                    productType = recommendation.recommendedProductType,
                    confidence = recommendation.confidence,
                    source = "recommended"
                )
            )
        }

        val optionItems = mutableListOf<String>()
        candidates.forEachIndexed { index, candidate ->
            val sourceTag = if (candidate.isMainRecord == true) "主记录" else "学习候选"
            optionItems.add(
                "${index + 1}. ${candidate.projectName} / ${candidate.productType}\n" +
                    "   来源: $sourceTag"
            )
        }
        optionItems.add("保持当前选择: $currentProject / $currentType")

        var selectedIndex = optionItems.lastIndex
        MaterialAlertDialogBuilder(this)
            .setTitle("序列号候选冲突，请确认")
            .setMessage(
                "序列号: $serialNumber\n" +
                    "系统推荐存在候选冲突，最终选择由您确认。"
            )
            .setSingleChoiceItems(optionItems.toTypedArray(), selectedIndex) { _, which ->
                selectedIndex = which
            }
            .setPositiveButton("确认并继续") { _, _ ->
                if (selectedIndex >= candidates.size) {
                    applySelectionAndContinue(
                        serialNumber = serialNumber,
                        targetProject = currentProject,
                        targetProductType = currentType,
                        existingRecord = existingRecord,
                        learningSource = "manual_keep_current",
                        conflict = true,
                        candidates = candidates
                    )
                } else {
                    val selectedCandidate = candidates[selectedIndex]
                    applySelectionAndContinue(
                        serialNumber = serialNumber,
                        targetProject = selectedCandidate.projectName,
                        targetProductType = selectedCandidate.productType,
                        existingRecord = existingRecord,
                        learningSource = "manual_confirm",
                        conflict = true,
                        candidates = candidates
                    )
                }
            }
            .setNeutralButton("修复绑定") { _, _ ->
                if (selectedIndex >= candidates.size) {
                    applySelectionAndContinue(
                        serialNumber = serialNumber,
                        targetProject = currentProject,
                        targetProductType = currentType,
                        existingRecord = existingRecord,
                        learningSource = "manual_repair",
                        conflict = true,
                        candidates = candidates,
                        forceRepairBinding = true
                    )
                } else {
                    val selectedCandidate = candidates[selectedIndex]
                    applySelectionAndContinue(
                        serialNumber = serialNumber,
                        targetProject = selectedCandidate.projectName,
                        targetProductType = selectedCandidate.productType,
                        existingRecord = existingRecord,
                        learningSource = "manual_repair",
                        conflict = true,
                        candidates = candidates,
                        forceRepairBinding = true
                    )
                }
            }
            .setNegativeButton("取消") { _, _ ->
                finalizeRecordLoading(serialNumber, existingRecord)
            }
            .setCancelable(false)
            .show()
    }

    private fun applySelectionAndContinue(
        serialNumber: String,
        targetProject: String,
        targetProductType: String,
        existingRecord: FileManager.ProductRecord?,
        learningSource: String,
        conflict: Boolean,
        candidates: List<com.testcenter.qrscanner.api.SerialRecommendationCandidate>,
        forceRepairBinding: Boolean = false
    ) {
        applySelection(targetProject, targetProductType) { applied ->
            if (!applied) {
                AppLogger.log("MainActivity", "推荐项目/产品类型无法应用，已保留当前选择")
                finalizeRecordLoading(serialNumber, existingRecord)
                return@applySelection
            }

            markPendingBindingUpdateIfNeeded(
                serialNumber = serialNumber,
                existingRecord = existingRecord,
                targetProject = targetProject,
                targetProductType = targetProductType
            )
            finalizeRecordLoading(
                serialNumber = serialNumber,
                existingRecord = existingRecord,
                preserveCurrentProductType = true
            )

            if (forceRepairBinding) {
                lifecycleScope.launch {
                    val operator = getCurrentOperatorName()
                    productRecordRepository.repairSerialBinding(
                        productSerial = serialNumber,
                        projectName = targetProject,
                        productType = targetProductType,
                        operator = operator,
                        source = "manual_repair"
                    ).fold(
                        onSuccess = {
                            clearPendingBindingUpdate(serialNumber)
                            Toast.makeText(
                                this@MainActivity,
                                "绑定已修复: $targetProject / $targetProductType",
                                Toast.LENGTH_SHORT
                            ).show()
                        },
                        onFailure = { e ->
                            AppLogger.log("MainActivity", "手动修复绑定失败: ${e.message}", e)
                            Toast.makeText(
                                this@MainActivity,
                                "绑定修复失败: ${e.message}",
                                Toast.LENGTH_SHORT
                            ).show()
                        }
                    )
                }
            } else if (learningSource != "serial_rule_only") {
                lifecycleScope.launch {
                    val operator = getCurrentOperatorName()
                    productRecordRepository.confirmSerialLearning(
                        productSerial = serialNumber,
                        projectName = targetProject,
                        productType = targetProductType,
                        operator = operator,
                        source = learningSource,
                        conflict = conflict,
                        candidates = candidates
                    ).onFailure { e ->
                        AppLogger.log("MainActivity", "学习写回失败: ${e.message}", e)
                    }
                }
            }
        }
    }

    private fun applySelection(
        targetProject: String,
        targetProductType: String,
        onDone: (Boolean) -> Unit
    ) {
        if (targetProject.isBlank() || targetProductType.isBlank()) {
            onDone(false)
            return
        }

        val currentProject = projectManager.getSelectedProject()
        if (currentProject != targetProject) {
            val previousProject = currentProject
            suppressProductTypeSwitchCheck = true
            projectManager.setSelectedProject(targetProject)
            updateProjectDisplay(targetProject)
            loadProjectConfiguration(targetProject) {
                val applied = applyProductTypeWithoutSwitchPrompt(targetProductType)
                if (!applied && !previousProject.isNullOrBlank() && previousProject != targetProject) {
                    AppLogger.log(
                        "MainActivity",
                        "推荐产品类型应用失败，回滚项目: $targetProject -> $previousProject"
                    )
                    projectManager.setSelectedProject(previousProject)
                    updateProjectDisplay(previousProject)
                    loadProjectConfiguration(previousProject) {
                        binding.root.post {
                            suppressProductTypeSwitchCheck = false
                            onDone(false)
                        }
                    }
                    return@loadProjectConfiguration
                }

                binding.root.post {
                    suppressProductTypeSwitchCheck = false
                    onDone(applied)
                }
            }
            return
        }

        suppressProductTypeSwitchCheck = true
        val applied = applyProductTypeWithoutSwitchPrompt(targetProductType)
        binding.root.post {
            suppressProductTypeSwitchCheck = false
            onDone(applied)
        }
    }

    private fun applyProductTypeWithoutSwitchPrompt(productType: String): Boolean {
        val index = productTypes.indexOf(productType)
        if (index < 0) {
            AppLogger.log("MainActivity", "推荐产品类型不在当前配置中: $productType")
            return false
        }
        currentProductType = productType
        spinnerProductType.setSelection(index)
        updateProductTypeDisplay(productType)
        loadMaterialsForProductType(productType)
        scannedComponents.clear()
        if (::componentAdapter.isInitialized) {
            componentAdapter.notifyDataSetChanged()
        }
        return true
    }

    private fun markPendingBindingUpdateIfNeeded(
        serialNumber: String,
        existingRecord: FileManager.ProductRecord?,
        targetProject: String,
        targetProductType: String
    ) {
        if (existingRecord == null) {
            return
        }
        val existingProject = existingRecord.projectName.trim()
        val existingType = existingRecord.productType.trim()
        val targetProjectTrimmed = targetProject.trim()
        val targetTypeTrimmed = targetProductType.trim()
        val projectChanged = existingProject.isNotBlank() && existingProject != targetProjectTrimmed
        val typeChanged = existingType.isNotBlank() && existingType != targetTypeTrimmed
        if (projectChanged || typeChanged) {
            pendingBindingUpdateSerial = serialNumber
            AppLogger.log(
                "MainActivity",
                "绑定变更已标记: serial=$serialNumber project=$existingProject->$targetProjectTrimmed type=$existingType->$targetTypeTrimmed"
            )
        }
    }

    private fun shouldForceBindingUpdate(productSerial: String): Boolean {
        return pendingBindingUpdateSerial == productSerial
    }

    private fun clearPendingBindingUpdate(productSerial: String) {
        if (pendingBindingUpdateSerial == productSerial) {
            pendingBindingUpdateSerial = null
        }
    }

    private fun finalizeRecordLoading(
        serialNumber: String,
        existingRecord: FileManager.ProductRecord?,
        preserveCurrentProductType: Boolean = false
    ) {
        if (existingRecord != null) {
            AppLogger.log("MainActivity", "✓ 找到已有记录: $serialNumber")
            loadExistingRecord(
                record = existingRecord,
                allowFallbackToRecordType = !preserveCurrentProductType
            )
            Toast.makeText(this@MainActivity, "✓ 找到已有记录", Toast.LENGTH_LONG).show()
        } else {
            AppLogger.log("MainActivity", "记录不存在: $serialNumber, 开始新记录")
            startFreshRecord(serialNumber)
            Toast.makeText(this@MainActivity, "新产品序列号，开始新记录", Toast.LENGTH_SHORT).show()
        }
    }

    private fun loadExistingRecord(
        record: FileManager.ProductRecord,
        allowFallbackToRecordType: Boolean = true
    ) {
        AppLogger.log("MainActivity", "Loading existing record: $record")
        
        // 先按当前选择加载；若无法映射任何组件且历史产品类型可用，则回退到历史类型。
        loadMaterialsForProductType(currentProductType)
        val dynamicRecordComponents = record.components
            .filterKeys { key ->
                key != "扫描时间" && key != "操作员" && !key.contains("标记")
            }
            .filterValues { value ->
                value.isNotEmpty() && value != "null"
            }
        var matchedComponentCount = dynamicRecordComponents.keys.count { componentName ->
            componentsList.any { it.name == componentName }
        }

        val recordProductType = record.productType.trim()
        if (
            allowFallbackToRecordType &&
            matchedComponentCount == 0 &&
            recordProductType.isNotEmpty() &&
            recordProductType != currentProductType &&
            productTypes.contains(recordProductType)
        ) {
            AppLogger.log(
                "MainActivity",
                "[记录加载] 当前产品类型无法映射历史组件，回退到历史产品类型: $currentProductType -> $recordProductType"
            )
            suppressProductTypeSwitchCheck = true
            val switched = applyProductTypeWithoutSwitchPrompt(recordProductType)
            suppressProductTypeSwitchCheck = false
            if (switched) {
                matchedComponentCount = dynamicRecordComponents.keys.count { componentName ->
                    componentsList.any { it.name == componentName }
                }
            }
        }
        AppLogger.log(
            "MainActivity",
            "[记录加载] 最终产品类型: $currentProductType, 历史产品类型: ${record.productType}, 可映射组件: $matchedComponentCount/${dynamicRecordComponents.size}"
        )
        
        // Load existing component data
        scannedComponents.clear()
        
        // 优先使用动态组件数据（新格式）
        if (record.components.isNotEmpty()) {
            AppLogger.log("MainActivity", "Loading components from dynamic data (${record.components.size} components)")
            
            for ((componentName, serialNumber) in record.components) {
                // 跳过非物料字段
                if (componentName == "扫描时间" || componentName == "操作员" || componentName.contains("标记")) {
                    AppLogger.log("MainActivity", "Skipping non-material field: $componentName")
                    continue
                }
                
                if (serialNumber.isNotEmpty() && serialNumber != "null") {
                    scannedComponents[componentName] = serialNumber
                    
                    // 只更新当前配置中存在的组件
                    val component = componentsList.find { it.name == componentName }
                    if (component != null) {
                        component.serial = serialNumber
                        AppLogger.log("MainActivity", "Loaded component: $componentName = $serialNumber")
                    } else {
                        AppLogger.log("MainActivity", "Component $componentName not in current config, skipping UI update")
                    }
                }
            }
        } else {
            // 降级到旧格式（固定组件名）
            AppLogger.log("MainActivity", "Loading components from legacy format")
            
            if (record.controlBoard.isNotEmpty()) {
                scannedComponents["控制板"] = record.controlBoard
                updateComponentInList("控制板", record.controlBoard)
                AppLogger.log("MainActivity", "Loaded 控制板: ${record.controlBoard}")
            }
            if (record.drivingCapacitor.isNotEmpty()) {
                scannedComponents["左侧电容板"] = record.drivingCapacitor
                updateComponentInList("左侧电容板", record.drivingCapacitor)
                AppLogger.log("MainActivity", "Loaded 左侧电容板: ${record.drivingCapacitor}")
            }
            if (record.pumpCapacitor.isNotEmpty()) {
                scannedComponents["右侧电容板"] = record.pumpCapacitor
                updateComponentInList("右侧电容板", record.pumpCapacitor)
                AppLogger.log("MainActivity", "Loaded 右侧电容板: ${record.pumpCapacitor}")
            }
            if (record.drivingPower.isNotEmpty()) {
                scannedComponents["左侧功率板"] = record.drivingPower
                updateComponentInList("左侧功率板", record.drivingPower)
                AppLogger.log("MainActivity", "Loaded 左侧功率板: ${record.drivingPower}")
            }
            if (record.pumpPower.isNotEmpty()) {
                scannedComponents["右侧功率板"] = record.pumpPower
                updateComponentInList("右侧功率板", record.pumpPower)
                AppLogger.log("MainActivity", "Loaded 右侧功率板: ${record.pumpPower}")
            }
        }
        
        // Refresh the adapter to show loaded data
        componentAdapter.notifyDataSetChanged()
        
        AppLogger.log("MainActivity", "Loaded existing record: ${scannedComponents.size} components")
    }

    private fun updateComponentInList(componentName: String, serialNumber: String) {
        val component = componentsList.find { it.name == componentName }
        component?.serial = serialNumber
    }

    private fun startFreshRecord(serialNumber: String) {
        // Clear previous component scans for new product
        scannedComponents.clear()
        
        // Reset all components to "待扫描"
        componentsList.forEach { component ->
            component.serial = "待扫描"
        }
        
        // Refresh the adapter
        componentAdapter.notifyDataSetChanged()
        
        // Start test record and save to network
        startTestRecord(serialNumber)
    }

    private fun saveComponentUpdateToNetwork(componentName: String, serialNumber: String) {
        val productSerial = currentProductSerial ?: return
        val productType = currentProductType
        val projectName = projectManager.getSelectedProject() ?: "未知项目"
        val currentOperator = getCurrentOperatorName()
        
        // 检查网络状态
        if (!isNetworkAvailable()) {
            Toast.makeText(this@MainActivity, "⚠ 网络不可用，请稍后重试", Toast.LENGTH_SHORT).show()
            return
        }
        
        // 显示上传状态
        runOnUiThread {
            Toast.makeText(this@MainActivity, "正在上传 $componentName 数据...", Toast.LENGTH_SHORT).show()
        }
        
        lifecycleScope.launch {
            try {
                // 使用 REST API 直接保存（不再使用 CSV 格式）
                val apiResult = productRecordRepository.saveProductRecord(
                    productSerial = productSerial,
                    productType = productType,
                    projectName = projectName,
                    operator = currentOperator,
                    materials = scannedComponents,
                    allowBindingUpdate = shouldForceBindingUpdate(productSerial)
                )
                
                withContext(Dispatchers.Main) {
                    apiResult.fold(
                        onSuccess = {
                            AppLogger.log("MainActivity", "✓ $componentName 已上传: $serialNumber")
                            clearPendingBindingUpdate(productSerial)
                            Toast.makeText(this@MainActivity, "✓ $componentName 数据已上传", Toast.LENGTH_SHORT).show()
                        },
                        onFailure = { e ->
                            AppLogger.log("MainActivity", "上传失败: ${e.message}")
                            Toast.makeText(this@MainActivity, "⚠ $componentName 上传失败: ${e.message}", Toast.LENGTH_SHORT).show()
                        }
                    )
                }
                
            } catch (e: Exception) {
                AppLogger.log("MainActivity", "Error updating component $componentName in network", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, "❌ $componentName 上传异常: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun showProjectSelectionDialog() {
        val projects = projectManager.getProjectList()
        if (projects.isEmpty()) {
            Toast.makeText(this, "没有可用的项目，请先添加项目", Toast.LENGTH_SHORT).show()
            showProjectManagementDialog()
            return
        }

        val projectsArray = projects.toTypedArray()
        val currentProject = projectManager.getSelectedProject()
        val selectedProjectIndex = if (currentProject != null) {
            projects.indexOf(currentProject).takeIf { it >= 0 } ?: 0
        } else {
            0
        }

        AlertDialog.Builder(this)
            .setTitle("选择项目")
            .setSingleChoiceItems(projectsArray, selectedProjectIndex) { dialog: DialogInterface, which: Int ->
                val newSelectedProject = projectsArray[which]
                projectManager.setSelectedProject(newSelectedProject)
                AppLogger.log("MainActivity", "Project selected: $newSelectedProject")
                Toast.makeText(this, "已选择项目: $newSelectedProject", Toast.LENGTH_SHORT).show()
                // Update UI immediately
                tvProjectName.text = newSelectedProject
                
                // 重新加载项目配置
                loadProjectConfiguration(newSelectedProject)
                
                // 清空当前产品数据
                currentProductSerial = null
                productInfoLayout.visibility = View.GONE
                scannedComponents.clear()
                
                dialog.dismiss()
            }
            .setNegativeButton("取消", null)
            .setNeutralButton("管理项目") { dialog, _ ->
                AppLogger.log("MainActivity", "Manage projects button clicked.")
                dialog.dismiss()
                showProjectManagementDialog()
            }
            .show()
    }

    private fun showProjectManagementDialog() {
        AlertDialog.Builder(this)
            .setTitle("项目管理")
            .setItems(arrayOf("添加项目", "删除项目", "清除缓存并刷新")) { _, which ->
                when (which) {
                    0 -> showAddProjectDialog()
                    1 -> showDeleteProjectDialog()
                    2 -> clearCacheAndRefresh()
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }
    
    private fun clearCacheAndRefresh() {
        AlertDialog.Builder(this)
            .setTitle("清除缓存并刷新")
            .setMessage("这将清除本地缓存的项目列表，并从服务器重新加载。确定继续吗？")
            .setPositiveButton("确定") { _, _ ->
                lifecycleScope.launch {
                    try {
                        // 清除本地缓存
                        projectManager.clearLocalCache()
                        Toast.makeText(this@MainActivity, "正在从服务器刷新...", Toast.LENGTH_SHORT).show()
                        
                        // 从网络刷新
                        val projects = projectManager.forceRefreshFromNetwork()
                        
                        // 更新 UI
                        runOnUiThread {
                            if (projects.isEmpty()) {
                                Toast.makeText(this@MainActivity, "服务器上没有项目，或刷新失败", Toast.LENGTH_LONG).show()
                            } else {
                                Toast.makeText(this@MainActivity, "成功刷新 ${projects.size} 个项目", Toast.LENGTH_SHORT).show()
                            }
                            // UI 会在下次访问项目列表时自动更新
                        }
                    } catch (e: Exception) {
                        runOnUiThread {
                            Toast.makeText(this@MainActivity, "刷新失败: ${e.message}", Toast.LENGTH_LONG).show()
                        }
                        AppLogger.log("MainActivity", "Error refreshing projects", e)
                    }
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun showAddProjectDialog() {
        val editText = EditText(this)
        editText.hint = "请输入项目名称"
        
        AlertDialog.Builder(this)
            .setTitle("添加项目")
            .setView(editText)
            .setPositiveButton("添加") { _, _ ->
                val newProject = editText.text.toString().trim()
                if (newProject.isNotEmpty()) {
                    if (projectManager.addProject(newProject)) {
                        AppLogger.log("MainActivity", "Added new project: $newProject")
                        Toast.makeText(this, "已添加项目: $newProject", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(this, "项目已存在", Toast.LENGTH_SHORT).show()
                    }
                } else {
                    Toast.makeText(this, "项目名称不能为空", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun showDeleteProjectDialog() {
        val projects = projectManager.getProjectList()
        if (projects.isEmpty()) {
            Toast.makeText(this, "没有可删除的项目", Toast.LENGTH_SHORT).show()
            return
        }
        
        val projectsArray = projects.toTypedArray()
        
        AlertDialog.Builder(this)
            .setTitle("删除项目")
            .setItems(projectsArray) { _, which ->
                val projectToDelete = projectsArray[which]
                
                AlertDialog.Builder(this)
                    .setTitle("确认删除")
                    .setMessage("确定要删除项目 \"$projectToDelete\" 吗？")
                    .setPositiveButton("删除") { _, _ ->
                        if (projectManager.removeProject(projectToDelete)) {
                            AppLogger.log("MainActivity", "Deleted project: $projectToDelete")
                            Toast.makeText(this, "已删除项目: $projectToDelete", Toast.LENGTH_SHORT).show()
                            
                            // Update selected project if deleted
                            if (projectManager.getSelectedProject() == projectToDelete) {
                                val remainingProjects = projectManager.getProjectList()
                                val newSelected = remainingProjects.firstOrNull() ?: "未选择项目"
                                if (remainingProjects.isNotEmpty()) {
                                    projectManager.setSelectedProject(newSelected)
                                }
                                tvProjectName.text = newSelected
                            }
                        } else {
                            Toast.makeText(this, "删除失败", Toast.LENGTH_SHORT).show()
                        }
                    }
                    .setNegativeButton("取消", null)
                    .show()
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun showNetworkSettingsDialog() {
        lifecycleScope.launch {
            val refreshed = refreshExternalLoginPermissionCache()
            if (!refreshed) {
                AppLogger.log("MainActivity", "Failed to refresh external login permission, falling back to cached permissions")
            }
            showNetworkSettingsDialogInternal()
        }
    }

    private suspend fun refreshExternalLoginPermissionCache(): Boolean = withContext(Dispatchers.IO) {
        try {
            val username = preferencesManager.getUsername()?.trim().orEmpty()
            val password = preferencesManager.getPassword()?.trim().orEmpty()
            val apiBaseUrl = preferencesManager.getApiBaseUrl().trim()

            if (username.isBlank() || password.isBlank() || apiBaseUrl.isBlank()) {
                AppLogger.log(
                    "MainActivity",
                    "Skip external login permission refresh: username/password/apiBaseUrl is blank"
                )
                return@withContext false
            }

            val apiClient = com.testcenter.qrscanner.network.PermissionApiClient(
                apiBaseUrl,
                username,
                password
            )
            val userPermissions = apiClient.fetchUserPermissions(username) ?: return@withContext false
            val permissions = apiClient.convertToPermissionSet(userPermissions)

            permissionService.setApiLoadedPermissions(username, permissions)
            AppLogger.log(
                "MainActivity",
                "External login permission refreshed: ${permissions.contains(com.testcenter.qrscanner.auth.PermissionService.Permission.WEB_EXTERNAL_LOGIN)}"
            )
            return@withContext true
        } catch (e: Exception) {
            AppLogger.log("MainActivity", "Error refreshing external login permission", e)
            return@withContext false
        }
    }

    private fun showNetworkSettingsDialogInternal() {
        val currentUrl = preferencesManager.getApiBaseUrl()
        val internalUrl = preferencesManager.getInternalApiBaseUrl()
        val externalUrl = preferencesManager.getExternalApiBaseUrl()
        val testUrl = preferencesManager.getDefaultApiBaseUrl()
        val canUseExternalLogin = permissionService.hasPermission(
            com.testcenter.qrscanner.auth.PermissionService.Permission.WEB_EXTERNAL_LOGIN
        )
        val externalOptionLabel = if (canUseExternalLogin) {
            "外网 ($externalUrl)"
        } else {
            "外网 ($externalUrl，未授权)"
        }

        val options = arrayOf(
            "内网 ($internalUrl)",
            "外网 ($externalUrl)",
            "测试服务器 ($testUrl)",
            "自定义"
        )
        options[1] = externalOptionLabel
        val selectedIndex = when (currentUrl) {
            internalUrl -> 0
            externalUrl -> 1
            testUrl -> 2
            else -> 3
        }

        AlertDialog.Builder(this)
            .setTitle("服务器地址 (当前: $currentUrl)")
            .setSingleChoiceItems(options, selectedIndex) { dialog, which ->
                when (which) {
                    0 -> {
                        preferencesManager.setApiBaseUrl(internalUrl)
                        ApiClient.resetInstance()
                        AppLogger.log("MainActivity", "切换到内网: $internalUrl")
                        Toast.makeText(this, "已切换到内网", Toast.LENGTH_SHORT).show()
                        dialog.dismiss()
                    }
                    1 -> {
                        if (!canUseExternalLogin) {
                            AppLogger.log("MainActivity", "Current user is not allowed to switch to external login")
                            Toast.makeText(this, "当前账号未配置外网登录权限", Toast.LENGTH_SHORT).show()
                            return@setSingleChoiceItems
                        }
                        preferencesManager.setApiBaseUrl(externalUrl)
                        ApiClient.resetInstance()
                        AppLogger.log("MainActivity", "切换到外网: $externalUrl")
                        Toast.makeText(this, "已切换到外网", Toast.LENGTH_SHORT).show()
                        dialog.dismiss()
                    }
                    2 -> {
                        preferencesManager.setApiBaseUrl(testUrl)
                        ApiClient.resetInstance()
                        AppLogger.log("MainActivity", "切换到测试服务器: $testUrl")
                        Toast.makeText(this, "已切换到测试服务器", Toast.LENGTH_SHORT).show()
                        dialog.dismiss()
                    }
                    3 -> {
                        dialog.dismiss()
                        showCustomUrlDialog()
                    }
                }
            }
            .setNeutralButton("测试连接") { _, _ ->
                testApiConnection()
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun showCustomUrlDialog() {
        val editText = android.widget.EditText(this).apply {
            hint = "http://IP:端口"
            setText(preferencesManager.getApiBaseUrl())
            setPadding(60, 40, 60, 20)
        }
        AlertDialog.Builder(this)
            .setTitle("自定义服务器地址")
            .setView(editText)
            .setPositiveButton("确定") { _, _ ->
                val url = editText.text.toString().trim().trimEnd('/')
                if (url.startsWith("http://") || url.startsWith("https://")) {
                    preferencesManager.setApiBaseUrl(url)
                    ApiClient.resetInstance()
                    AppLogger.log("MainActivity", "自定义服务器地址: $url")
                    Toast.makeText(this, "已设置: $url", Toast.LENGTH_SHORT).show()
                } else {
                    Toast.makeText(this, "地址必须以 http:// 或 https:// 开头", Toast.LENGTH_LONG).show()
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun testApiConnection() {
        lifecycleScope.launch {
            val url = preferencesManager.getApiBaseUrl()
            Toast.makeText(this@MainActivity, "正在测试 $url ...", Toast.LENGTH_SHORT).show()
            try {
                val result = withContext(Dispatchers.IO) {
                    val conn = java.net.URL("$url/api/apk/list").openConnection() as java.net.HttpURLConnection
                    conn.connectTimeout = 5000
                    conn.readTimeout = 5000
                    conn.requestMethod = "GET"
                    try {
                        conn.responseCode
                    } finally {
                        conn.disconnect()
                    }
                }
                if (result == 200) {
                    Toast.makeText(this@MainActivity, "✓ 连接成功", Toast.LENGTH_LONG).show()
                } else {
                    Toast.makeText(this@MainActivity, "连接异常: HTTP $result", Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                Toast.makeText(this@MainActivity, "连接失败: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun testNetworkConnection() {
        lifecycleScope.launch {
            try {
                val username = preferencesManager.getUsername() ?: return@launch
                val password = preferencesManager.getPassword() ?: return@launch
                
                Toast.makeText(this@MainActivity, "正在测试网络连接...", Toast.LENGTH_SHORT).show()
                
                val fileManager = FileManagerFactory.create(this@MainActivity, username, password)
                val success = fileManager.testConnection()
                
                val currentBackend = preferencesManager.getBackend()
                val protocolName = if (currentBackend == "smb") "SMB" else "WebDAV"
                
                if (success) {
                    Toast.makeText(this@MainActivity, "$protocolName 连接测试成功！", Toast.LENGTH_LONG).show()
                    AppLogger.log("MainActivity", "$protocolName connection test successful")
                } else {
                    Toast.makeText(this@MainActivity, "$protocolName 连接测试失败，请检查网络设置", Toast.LENGTH_LONG).show()
                    AppLogger.log("MainActivity", "$protocolName connection test failed")
                }
                
            } catch (e: Exception) {
                Toast.makeText(this@MainActivity, "连接测试出错: ${e.message}", Toast.LENGTH_LONG).show()
                AppLogger.log("MainActivity", "Connection test error", e)
            }
        }
    }

    private fun loadInitialData() {
        AppLogger.log("MainActivity", "Starting to load initial data (projects)")
        
        lifecycleScope.launch {
            try {
                val username = preferencesManager.getUsername() ?: return@launch
                val password = preferencesManager.getPassword() ?: return@launch
                
                val fileManager = FileManagerFactory.create(this@MainActivity, username, password)
                
                // Load projects in background
                launch(Dispatchers.IO) {
                    try {
                        AppLogger.log("MainActivity", "Loading projects from server...")
                        val projects = projectManager.forceRefreshFromNetwork()
                        if (projects.isNotEmpty()) {
                            // 只保存到本地缓存，不回传网络（避免普通用户权限问题）
                            AppLogger.log("MainActivity", "Successfully loaded ${projects.size} projects")

                            val selectedProject = projectManager.getSelectedProject()?.takeIf { projects.contains(it) }
                            preloadSelectedProjectConfig(
                                selectedProject = selectedProject,
                                fileManager = fileManager
                            )
                            
                            // Update UI on main thread
                            runOnUiThread {
                                tvProjectName.text = selectedProject ?: "未选择项目"
                            }
                        } else {
                            AppLogger.log("MainActivity", "No projects found on server")
                        }
                    } catch (e: Exception) {
                        AppLogger.log("MainActivity", "Failed to load projects: ${e.message}", e)
                    }
                }
                
            } catch (e: Exception) {
                AppLogger.log("MainActivity", "Failed to initialize file manager for data loading", e)
            }
        }
    }

    private suspend fun preloadSelectedProjectConfig(
        selectedProject: String?,
        fileManager: FileManager
    ) {
        selectedProject?.let { projectName ->
            try {
                when (val result = projectConfigManager.syncConfigFromServer(projectName, fileManager, forceSync = false)) {
                    is ProjectConfigManager.SyncResult.Success ->
                        AppLogger.log("MainActivity", "Preloaded selected project config: $projectName (v${result.config.version})")
                    is ProjectConfigManager.SyncResult.AlreadyLatest ->
                        AppLogger.log("MainActivity", "Selected project config already local: $projectName (v${result.config.version})")
                    is ProjectConfigManager.SyncResult.NotFound ->
                        AppLogger.log("MainActivity", "Selected project config not found on server: $projectName")
                    is ProjectConfigManager.SyncResult.Error ->
                        AppLogger.log("MainActivity", "Failed to preload selected project config: $projectName, error=${result.message}")
                    is ProjectConfigManager.SyncResult.Conflict ->
                        AppLogger.log("MainActivity", "Selected project config conflict detected: $projectName")
                }
            } catch (e: Exception) {
                AppLogger.log("MainActivity", "Exception preloading selected project config: $projectName", e)
            }
        }
    }
    
    /**
     * 显示项目配置管理对话框
     */
    private fun showProjectConfigManagementDialog() {
        val currentProject = projectManager.getSelectedProject()
        if (currentProject == null) {
            Toast.makeText(this, "请先选择一个项目", Toast.LENGTH_SHORT).show()
            return
        }
        
        val options = arrayOf("管理产品类型", "管理物料清单")
        
        AlertDialog.Builder(this)
            .setTitle("项目配置管理 - $currentProject")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> showProductTypeManagementDialog(currentProject)
                    1 -> showMaterialManagementDialog(currentProject)
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }
    
    /**
     * 显示产品类型管理对话框
     */
    private fun showProductTypeManagementDialog(projectName: String) {
        val options = arrayOf("添加产品类型", "删除产品类型", "查看所有产品类型")
        
        AlertDialog.Builder(this)
            .setTitle("产品类型管理")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> showAddProductTypeDialog(projectName)
                    1 -> showDeleteProductTypeDialog(projectName)
                    2 -> showAllProductTypesDialog(projectName)
                }
            }
            .setNegativeButton("返回", null)
            .show()
    }
    
    /**
     * 显示添加产品类型对话框
     */
    private fun showAddProductTypeDialog(projectName: String) {
        val editText = EditText(this)
        editText.hint = "请输入产品类型名称"
        
        AlertDialog.Builder(this)
            .setTitle("添加产品类型")
            .setView(editText)
            .setPositiveButton("添加") { _, _ ->
                val typeName = editText.text.toString().trim()
                if (typeName.isNotEmpty()) {
                    if (projectConfigManager.addProductType(projectName, typeName)) {
                        Toast.makeText(this, "已添加产品类型: $typeName", Toast.LENGTH_SHORT).show()
                        // 重新加载配置
                        loadProjectConfiguration(projectName)
                    } else {
                        Toast.makeText(this, "产品类型已存在", Toast.LENGTH_SHORT).show()
                    }
                } else {
                    Toast.makeText(this, "产品类型名称不能为空", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }
    
    /**
     * 显示删除产品类型对话框
     */
    private fun showDeleteProductTypeDialog(projectName: String) {
        val productTypes = projectConfigManager.getProductTypeNames(projectName)
        
        if (productTypes.isEmpty()) {
            Toast.makeText(this, "没有可删除的产品类型", Toast.LENGTH_SHORT).show()
            return
        }
        
        val typesArray = productTypes.toTypedArray()
        
        AlertDialog.Builder(this)
            .setTitle("删除产品类型")
            .setItems(typesArray) { _, which ->
                val typeToDelete = typesArray[which]
                
                AlertDialog.Builder(this)
                    .setTitle("确认删除")
                    .setMessage("确定要删除产品类型 \"$typeToDelete\" 吗？\n该类型下的所有物料配置也将被删除。")
                    .setPositiveButton("删除") { _, _ ->
                        if (projectConfigManager.removeProductType(projectName, typeToDelete)) {
                            Toast.makeText(this, "已删除产品类型: $typeToDelete", Toast.LENGTH_SHORT).show()
                            // 重新加载配置
                            loadProjectConfiguration(projectName)
                        } else {
                            Toast.makeText(this, "删除失败", Toast.LENGTH_SHORT).show()
                        }
                    }
                    .setNegativeButton("取消", null)
                    .show()
            }
            .setNegativeButton("取消", null)
            .show()
    }
    
    /**
     * 显示所有产品类型
     */
    private fun showAllProductTypesDialog(projectName: String) {
        val productTypes = projectConfigManager.getProductTypeNames(projectName)
        
        if (productTypes.isEmpty()) {
            Toast.makeText(this, "暂无产品类型", Toast.LENGTH_SHORT).show()
            return
        }
        
        val message = "当前产品类型：\n\n" + productTypes.joinToString("\n") { "• $it" }
        
        AlertDialog.Builder(this)
            .setTitle("所有产品类型")
            .setMessage(message)
            .setPositiveButton("确定", null)
            .show()
    }
    
    /**
     * 显示物料管理对话框
     */
    private fun showMaterialManagementDialog(projectName: String) {
        val productTypes = projectConfigManager.getProductTypeNames(projectName)
        
        if (productTypes.isEmpty()) {
            Toast.makeText(this, "请先添加产品类型", Toast.LENGTH_SHORT).show()
            return
        }
        
        val typesArray = productTypes.toTypedArray()
        
        AlertDialog.Builder(this)
            .setTitle("选择产品类型")
            .setItems(typesArray) { _, which ->
                val selectedType = typesArray[which]
                showMaterialOperationsDialog(projectName, selectedType)
            }
            .setNegativeButton("取消", null)
            .show()
    }
    
    /**
     * 显示物料操作对话框
     */
    private fun showMaterialOperationsDialog(projectName: String, productTypeName: String) {
        val options = arrayOf("添加物料", "删除物料", "编辑物料", "查看所有物料")
        
        AlertDialog.Builder(this)
            .setTitle("物料管理 - $productTypeName")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> showAddMaterialDialog(projectName, productTypeName)
                    1 -> showDeleteMaterialDialog(projectName, productTypeName)
                    2 -> showEditMaterialDialog(projectName, productTypeName)
                    3 -> showAllMaterialsDialog(projectName, productTypeName)
                }
            }
            .setNegativeButton("返回", null)
            .show()
    }
    
    /**
     * 显示添加物料对话框
     */
    private fun showAddMaterialDialog(projectName: String, productTypeName: String) {
        val layout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(50, 20, 50, 20)
        }
        
        val nameInput = EditText(this).apply {
            hint = "物料名称（如：控制板）"
        }
        
        val partNumberInput = EditText(this).apply {
            hint = "物料编号（如：U12020034.A0）"
        }
        
        layout.addView(nameInput)
        layout.addView(partNumberInput)
        
        AlertDialog.Builder(this)
            .setTitle("添加物料")
            .setView(layout)
            .setPositiveButton("添加") { _, _ ->
                val name = nameInput.text.toString().trim()
                val partNumber = partNumberInput.text.toString().trim()
                
                if (name.isEmpty() || partNumber.isEmpty()) {
                    Toast.makeText(this, "物料名称和编号都不能为空", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                
                val material = MaterialInfo(name, partNumber)
                if (projectConfigManager.addMaterial(projectName, productTypeName, material)) {
                    Toast.makeText(this, "已添加物料: $name", Toast.LENGTH_SHORT).show()
                    // 如果是当前项目和产品类型，重新加载
                    if (projectName == projectManager.getSelectedProject() && productTypeName == currentProductType) {
                        loadMaterialsForProductType(productTypeName)
                    }
                } else {
                    Toast.makeText(this, "物料已存在", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }
    
    /**
     * 显示删除物料对话框
     */
    private fun showDeleteMaterialDialog(projectName: String, productTypeName: String) {
        val materials = projectConfigManager.getMaterials(projectName, productTypeName)
        
        if (materials.isEmpty()) {
            Toast.makeText(this, "没有可删除的物料", Toast.LENGTH_SHORT).show()
            return
        }
        
        val materialNames = materials.map { "${it.name} (${it.partNumber})" }.toTypedArray()
        
        AlertDialog.Builder(this)
            .setTitle("删除物料")
            .setItems(materialNames) { _, which ->
                val materialToDelete = materials[which]
                
                AlertDialog.Builder(this)
                    .setTitle("确认删除")
                    .setMessage("确定要删除物料 \"${materialToDelete.name}\" 吗？")
                    .setPositiveButton("删除") { _, _ ->
                        if (projectConfigManager.removeMaterial(projectName, productTypeName, materialToDelete.name)) {
                            Toast.makeText(this, "已删除物料: ${materialToDelete.name}", Toast.LENGTH_SHORT).show()
                            // 如果是当前项目和产品类型，重新加载
                            if (projectName == projectManager.getSelectedProject() && productTypeName == currentProductType) {
                                loadMaterialsForProductType(productTypeName)
                            }
                        } else {
                            Toast.makeText(this, "删除失败", Toast.LENGTH_SHORT).show()
                        }
                    }
                    .setNegativeButton("取消", null)
                    .show()
            }
            .setNegativeButton("取消", null)
            .show()
    }
    
    /**
     * 显示编辑物料对话框
     */
    private fun showEditMaterialDialog(projectName: String, productTypeName: String) {
        val materials = projectConfigManager.getMaterials(projectName, productTypeName)
        
        if (materials.isEmpty()) {
            Toast.makeText(this, "没有可编辑的物料", Toast.LENGTH_SHORT).show()
            return
        }
        
        val materialNames = materials.map { "${it.name} (${it.partNumber})" }.toTypedArray()
        
        AlertDialog.Builder(this)
            .setTitle("选择要编辑的物料")
            .setItems(materialNames) { _, which ->
                val materialToEdit = materials[which]
                showEditMaterialDetailsDialog(projectName, productTypeName, materialToEdit)
            }
            .setNegativeButton("取消", null)
            .show()
    }
    
    /**
     * 显示编辑物料详情对话框
     */
    private fun showEditMaterialDetailsDialog(projectName: String, productTypeName: String, material: MaterialInfo) {
        val layout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(50, 20, 50, 20)
        }
        
        val nameInput = EditText(this).apply {
            hint = "物料名称"
            setText(material.name)
        }
        
        val partNumberInput = EditText(this).apply {
            hint = "物料编号"
            setText(material.partNumber)
        }
        
        layout.addView(nameInput)
        layout.addView(partNumberInput)
        
        AlertDialog.Builder(this)
            .setTitle("编辑物料")
            .setView(layout)
            .setPositiveButton("保存") { _, _ ->
                val newName = nameInput.text.toString().trim()
                val newPartNumber = partNumberInput.text.toString().trim()
                
                if (newName.isEmpty() || newPartNumber.isEmpty()) {
                    Toast.makeText(this, "物料名称和编号都不能为空", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                
                val newMaterial = MaterialInfo(newName, newPartNumber)
                if (projectConfigManager.updateMaterial(projectName, productTypeName, material.name, newMaterial)) {
                    Toast.makeText(this, "已更新物料信息", Toast.LENGTH_SHORT).show()
                    // 如果是当前项目和产品类型，重新加载
                    if (projectName == projectManager.getSelectedProject() && productTypeName == currentProductType) {
                        loadMaterialsForProductType(productTypeName)
                    }
                } else {
                    Toast.makeText(this, "更新失败", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }
    
    /**
     * 显示所有物料
     */
    private fun showAllMaterialsDialog(projectName: String, productTypeName: String) {
        val materials = projectConfigManager.getMaterials(projectName, productTypeName)
        
        if (materials.isEmpty()) {
            Toast.makeText(this, "暂无物料", Toast.LENGTH_SHORT).show()
            return
        }
        
        val message = "当前物料清单：\n\n" + materials.joinToString("\n") { 
            "• ${it.name}\n  编号：${it.partNumber}" 
        }
        
        AlertDialog.Builder(this)
            .setTitle("所有物料")
            .setMessage(message)
            .setPositiveButton("确定", null)
            .show()
    }
    
    
    
    
    
    
    
    
    
    /**
     * 获取当前操作员名称（使用登录用户）
     */
    private fun getCurrentOperatorName(): String {
        val currentUser = localUserManager.getCurrentUser()
        return if (currentUser != null) {
            currentUser.displayName.ifBlank {
                currentUser.synologyUsername.ifBlank {
                    preferencesManager.getUsername().orEmpty().ifBlank { "未知" }
                }
            }
        } else {
            // Fallback to username from PreferencesManager for WebDAV/SMB login
            preferencesManager.getUsername() ?: "未登录"
        }
    }
}
