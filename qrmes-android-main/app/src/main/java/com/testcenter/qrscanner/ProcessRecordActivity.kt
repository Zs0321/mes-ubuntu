package com.testcenter.qrscanner

import android.Manifest
import android.app.AlertDialog
import android.app.Dialog
import android.app.ProgressDialog
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.os.Environment
import android.view.MenuItem
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.bumptech.glide.Glide
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanIntentResult
import com.testcenter.qrscanner.adapter.ProcessStepAdapter
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.data.ProcessStep
import com.testcenter.qrscanner.data.ProjectConfig
import com.testcenter.qrscanner.databinding.ActivityProcessRecordBinding
import com.testcenter.qrscanner.scanner.EnhancedQRScanner
import com.testcenter.qrscanner.telemetry.ApkTelemetryManager
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.FileUtils
import com.testcenter.qrscanner.utils.PreferencesManager
import com.testcenter.qrscanner.utils.ProcessPhotoFileNameParser
import com.testcenter.qrscanner.utils.ProjectConfigManager
import com.testcenter.qrscanner.utils.ProjectManager
import com.testcenter.qrscanner.utils.SerialNormalizer
import com.testcenter.qrscanner.network.FileManagerFactory
import com.testcenter.qrscanner.qc.QcService
import com.testcenter.qrscanner.repository.PhotoRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.io.FileOutputStream
import com.testcenter.qrscanner.qc.QcPolicy
import com.testcenter.qrscanner.qc.QcPreviousCheckResponse
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class ProcessRecordActivity : AppCompatActivity() {

    private lateinit var binding: ActivityProcessRecordBinding
    private lateinit var preferencesManager: PreferencesManager
    private lateinit var projectManager: ProjectManager
    private lateinit var projectConfigManager: ProjectConfigManager
    private lateinit var enhancedQRScanner: EnhancedQRScanner
    private lateinit var processStepAdapter: ProcessStepAdapter
    private lateinit var localUserManager: com.testcenter.qrscanner.auth.LocalUserManager
    private lateinit var authenticationService: com.testcenter.qrscanner.auth.AuthenticationService
    private lateinit var permissionUIController: com.testcenter.qrscanner.ui.PermissionUIController
    
    private var currentProjectConfig: ProjectConfig? = null
    private var currentProductSerial: String? = null
    private var currentProductType: String? = null
    private var currentUserGroupNames: Set<String> = emptySet()
    private var currentUserGroupsLoaded: Boolean = false
    // 绑定当前工序状态缓存对应的序列号，防止跨序列号串状态
    private var qcStatusBoundSerial: String? = null
    private var productTypes = arrayOf<String>()
    private val processStepsList = mutableListOf<ProcessStep>()
    private val capturedPhotos = mutableMapOf<String, String>() // processStepId -> photoPath
    private val photoRepository by lazy { PhotoRepository(this) }
    private lateinit var qcService: QcService
    private var qcPolicy: QcPolicy = QcPolicy.DEFAULT
    private var currentProcessStep: ProcessStep? = null
    private var progressDialog: ProgressDialog? = null
    private var refreshQcStatusJob: Job? = null
    private var deferredRefreshJob: Job? = null
    private var refreshQcStatusKey: String? = null
    private var refreshQcStatusStartedAt: Long = 0L
    private var lastPhotoCaptureResultAt: Long = 0L
    private var qcPreCheckJob: Job? = null
    private var qcPreCheckKey: String? = null
    private var pendingRefreshKey: String? = null
    private var pendingRefreshReason: String? = null
    private var pendingRefreshForce: Boolean = false
    private var suppressSpinnerProcessReloadOnce: Boolean = false
    private val scanOnlyAutoMatchMode = true

    private companion object {
        const val REFRESH_QC_STATUS_COOLDOWN_MS = 1500L
        const val SKIP_ON_RESUME_AFTER_CAPTURE_MS = 2000L
    }

    // 拍照结果接收器
    private val photoCaptureResultLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            val data = result.data ?: return@registerForActivityResult
            val stepName = data.getStringExtra(PhotoCaptureActivity.RESULT_EXTRA_PROCESS_STEP_NAME) ?: return@registerForActivityResult
            val photoCount = data.getIntExtra(PhotoCaptureActivity.RESULT_EXTRA_PHOTO_COUNT, 0)
            val qcStatus = data.getStringExtra(PhotoCaptureActivity.RESULT_EXTRA_QC_STATUS)
            val qcSummary = data.getStringExtra(PhotoCaptureActivity.RESULT_EXTRA_QC_SUMMARY)
            val findingsJson = data.getStringExtra(PhotoCaptureActivity.RESULT_EXTRA_QC_FINDINGS)

            // 解析 findings
            val findings = parseFindingsJson(findingsJson)

            // 找到对应工序并立即更新状态
            val matchingStep = processStepsList.find { it.name == stepName }
            if (matchingStep != null && photoCount > 0) {
                processStepAdapter.updateQcStatus(
                    processStepId = matchingStep.id,
                    hasPhoto = true,
                    photoCount = photoCount,
                    qcStatus = qcStatus,
                    qcSummary = qcSummary,
                    findings = findings,
                    aiStatus = qcStatus,
                    aiSummary = qcSummary,
                    aiFindings = findings
                )
                AppLogger.log("ProcessRecordActivity", "[拍照结果] 工序: $stepName, 照片: ${photoCount}张, QC: $qcStatus, 问题: ${findings.size}个, 结论: ${qcSummary?.take(50)}")
            }
            lastPhotoCaptureResultAt = System.currentTimeMillis()
            refreshQcStatus(reason = "photo_capture_result", force = true)
        }
    }

    // PDF 文件选择器
    private val pdfPickerLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            result.data?.data?.let { uri ->
                currentProcessStep?.let { step ->
                    handlePdfSelected(uri, step)
                }
            }
        }
    }

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
                AppLogger.log("ProcessRecordActivity", "Product serial normalized: rawLen=${rawSerial.length}, normalizedLen=${scannedSerial.length}")
            }
            handleProductScanned(scannedSerial)
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
        
        AppLogger.log("ProcessRecordActivity", "onCreate")

        // Initialize dependencies
        preferencesManager = PreferencesManager(this)
        projectManager = ProjectManager(this)
        projectConfigManager = ProjectConfigManager(this)
        enhancedQRScanner = EnhancedQRScanner(this)
        localUserManager = com.testcenter.qrscanner.auth.LocalUserManager(this)
        qcService = QcService(this)

        // Check login status
        if (!preferencesManager.isLoggedIn()) {
            AppLogger.log("ProcessRecordActivity", "Not logged in. Redirecting to LoginActivity")
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
            return
        }

        binding = ActivityProcessRecordBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // 初始化权限服务（initialize 内部已调用 loadCachedPermissionsForCurrentUser）
        authenticationService = com.testcenter.qrscanner.auth.AuthenticationService(this)
        authenticationService.initialize()
        permissionUIController = com.testcenter.qrscanner.ui.PermissionUIController(authenticationService)

        // 获取当前用户信息用于日志
        val currentUser = localUserManager.getCurrentUser()
        if (currentUser != null) {
            AppLogger.log("ProcessRecordActivity", "[权限] 当前用户: ${currentUser.synologyUsername}, 角色: ${currentUser.role.name}")
        } else {
            AppLogger.log("ProcessRecordActivity", "[权限] 警告：未找到当前用户，将使用 PreferencesManager 中的用户名")
        }

        // 检查工序记录权限
        if (!checkProcessRecordPermission(authenticationService)) {
            AppLogger.log("ProcessRecordActivity", "[权限] 权限检查失败，Activity 将关闭")
            return
        }
        AppLogger.log("ProcessRecordActivity", "[权限] 权限检查通过")

        setupToolbar()
        setupUI()
        loadProjectConfiguration()
    }

    private fun setupToolbar() {
        setSupportActionBar(binding.toolbar)
        supportActionBar?.apply {
            title = "工序记录"
            setDisplayHomeAsUpEnabled(true)
        }
    }

    private fun setupUI() {
        // Setup project info (operator name removed from UI - using login user automatically)
        val currentUser = localUserManager.getCurrentUser()
        val operatorName = getCurrentOperatorName()
        
        AppLogger.log("ProcessRecordActivity", "Current operator: $operatorName (User ID: ${currentUser?.id}, Source: ${if (currentUser != null) "LocalUserManager" else "PreferencesManager"})")
        
        val processProject = projectManager.getSelectedProcessProject()
        val initialProject = processProject ?: projectManager.getSelectedProject()
        if (processProject == null && initialProject != null) {
            projectManager.setSelectedProcessProject(initialProject)
        }
        updateProjectNameDisplay(initialProject)

        // Setup product type spinner
        setupProductTypeSpinner()

        // Setup scan button
        binding.btnScanProduct.setOnClickListener {
            checkCameraPermissionAndScanProduct()
        }

        binding.btnManualInput.visibility = View.GONE

        // Setup RecyclerView for process steps
        processStepAdapter = ProcessStepAdapter(
            processStepsList,
            onCameraClick = { processStep ->
                openCameraForProcessStep(processStep)
            },
            onStepClick = { processStep, statusInfo ->
                showStepDetailDialog(processStep, statusInfo)
            }
        )
        binding.recyclerViewProcessSteps.layoutManager = LinearLayoutManager(this)
        binding.recyclerViewProcessSteps.adapter = processStepAdapter

        // Project selection is handled by menu
        // binding.projectInfoLayout.setOnClickListener {
        //     showProcessProjectSelectionDialog()
        // }

        // 项目信息初始显示
        updateProjectNameDisplay(initialProject)
        
        // 项目选择点击事件
        applyScanOnlyAutoMatchMode()
        
        // 查看照片记录按钮
        binding.btnViewPhotos.setOnClickListener {
            val productSerial = currentProductSerial
            if (productSerial.isNullOrEmpty()) {
                Toast.makeText(this, "请先扫描产品二维码", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            
            val projectName = projectManager.getSelectedProcessProject() ?: currentProjectConfig?.projectName ?: ""
            val projectCode = currentProjectConfig?.projectCode ?: ""
            val productTypeName = currentProductType ?: ""
            val modelNumber = currentProjectConfig?.getProductTypeConfig(productTypeName)?.modelNumber ?: ""
            
            val intent = Intent(this, PhotoRecordsActivity::class.java).apply {
                putExtra(PhotoRecordsActivity.EXTRA_PRODUCT_SERIAL, productSerial)
                putExtra(PhotoRecordsActivity.EXTRA_PROJECT_NAME, projectName)
                putExtra(PhotoRecordsActivity.EXTRA_PROJECT_CODE, projectCode)
                putExtra(PhotoRecordsActivity.EXTRA_PRODUCT_TYPE, productTypeName)
                putExtra(PhotoRecordsActivity.EXTRA_MODEL_NUMBER, modelNumber)
            }
            startActivity(intent)
        }
        
        // 应用权限控制
        applyPermissionControls(permissionUIController, binding)
        binding.btnManualInput.visibility = View.GONE
    }

    /**
     * 更新项目显示信息（项目号和项目名称分开显示）
     */
    private fun updateProjectNameDisplay(projectName: String?) {
        if (projectName == null) {
            binding.tvProjectCode.text = "未选择"
            binding.tvProjectName.text = "未选择项目"
            return
        }

        val projectCode = when {
            currentProjectConfig?.projectName == projectName -> currentProjectConfig?.projectCode
            else -> projectConfigManager.loadProjectConfig(projectName)?.projectCode
        }

        binding.tvProjectCode.text = projectCode?.takeIf { it.isNotEmpty() } ?: projectName
        binding.tvProjectName.text = projectName
    }
    
    /**
     * 更新产品类型显示信息
     */
    private fun updateProductTypeDisplay(productTypeName: String?) {
        if (productTypeName != null) {
            val productTypeConfig = currentProjectConfig?.getProductTypeConfig(productTypeName)
            binding.tvProductTypeName.text = productTypeConfig?.getDisplayName() ?: productTypeName
        } else {
            binding.tvProductTypeName.text = "未选择"
        }
    }

    private fun setupProductTypeSpinner() {
        val displayNames = currentProjectConfig?.productTypes?.map { productType ->
            productType.getDisplayName()
        }?.toTypedArray() ?: productTypes

        val adapter = ArrayAdapter(
            this,
            R.layout.spinner_compact_selected_item,
            displayNames
        )
        adapter.setDropDownViewResource(R.layout.spinner_compact_dropdown_item)
        binding.spinnerProductType.adapter = adapter

        binding.spinnerProductType.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (productTypes.isNotEmpty()) {
                    currentProductType = productTypes[position]
                    AppLogger.log("ProcessRecordActivity", "Product type selected: $currentProductType")
                    
                    // 更新产品类型显示
                    updateProductTypeDisplay(currentProductType)
                    
                    // If product is already scanned, reload process steps for new product type
                    if (suppressSpinnerProcessReloadOnce) {
                        suppressSpinnerProcessReloadOnce = false
                    } else if (currentProductSerial != null) {
                        loadProcessStepsForProduct(currentProductSerial!!)
                    }
                }
            }

            override fun onNothingSelected(parent: AdapterView<*>?) {
                currentProductType = null
                updateProductTypeDisplay(null)
            }
        }

        binding.spinnerProductType.isEnabled = !scanOnlyAutoMatchMode
        binding.spinnerProductType.isClickable = !scanOnlyAutoMatchMode
        binding.spinnerProductType.isFocusable = !scanOnlyAutoMatchMode
        binding.spinnerProductType.alpha = if (scanOnlyAutoMatchMode) 0.7f else 1f
    }

    private fun applyScanOnlyAutoMatchMode() {
        if (!scanOnlyAutoMatchMode) {
            binding.tvProjectCode.setOnClickListener {
                AppLogger.log("ProcessRecordActivity", "[项目选择] 点击项目号，准备显示项目选择对话框")
                showProcessProjectSelectionDialog()
            }
            binding.tvProjectName.setOnClickListener {
                AppLogger.log("ProcessRecordActivity", "[项目选择] 点击项目名称，准备显示项目选择对话框")
                showProcessProjectSelectionDialog()
            }
            binding.spinnerProductType.isEnabled = true
            binding.spinnerProductType.isClickable = true
            binding.spinnerProductType.isFocusable = true
            binding.spinnerProductType.alpha = 1f
            return
        }

        AppLogger.log("ProcessRecordActivity", "Scan-only auto-match mode enabled")
        binding.tvProjectCode.setOnClickListener(null)
        binding.tvProjectName.setOnClickListener(null)
        binding.tvProjectCode.isClickable = false
        binding.tvProjectCode.isFocusable = false
        binding.tvProjectName.isClickable = false
        binding.tvProjectName.isFocusable = false
        binding.tvProjectCode.alpha = 0.7f
        binding.tvProjectName.alpha = 0.7f
        binding.spinnerProductType.isEnabled = false
        binding.spinnerProductType.isClickable = false
        binding.spinnerProductType.isFocusable = false
        binding.spinnerProductType.alpha = 0.7f
    }

    private fun normalizeGroupName(raw: String?): String {
        return raw?.trim()?.lowercase() ?: ""
    }

    private suspend fun loadCurrentUserGroups() {
        try {
            val response = withContext(Dispatchers.IO) {
                ApiClient.getApiService(this@ProcessRecordActivity).getCurrentUserGroups()
            }
            if (!response.isSuccessful) {
                currentUserGroupNames = emptySet()
                currentUserGroupsLoaded = false
                AppLogger.log("ProcessRecordActivity", "获取用户群组失败: HTTP ${response.code()}")
                return
            }

            val body = response.body()
            if (body?.success != true) {
                currentUserGroupNames = emptySet()
                currentUserGroupsLoaded = false
                AppLogger.log("ProcessRecordActivity", "获取用户群组失败: ${body?.error ?: "unknown"}")
                return
            }
            if (body.data?.userFound == false) {
                currentUserGroupNames = emptySet()
                currentUserGroupsLoaded = false
                AppLogger.log("ProcessRecordActivity", "当前用户未映射群组，跳过工序责任过滤")
                return
            }

            val names = mutableSetOf<String>()
            body.data?.groupNames?.forEach { name ->
                val normalized = normalizeGroupName(name)
                if (normalized.isNotEmpty()) names.add(normalized)
            }
            body.data?.groups?.forEach { group ->
                val normalizedName = normalizeGroupName(group.name)
                if (normalizedName.isNotEmpty()) names.add(normalizedName)
                val normalizedDisplay = normalizeGroupName(group.displayName)
                if (normalizedDisplay.isNotEmpty()) names.add(normalizedDisplay)
            }

            currentUserGroupNames = names
            currentUserGroupsLoaded = true
            AppLogger.log("ProcessRecordActivity", "当前用户群组加载完成: ${currentUserGroupNames.size} 项")
        } catch (e: Exception) {
            currentUserGroupNames = emptySet()
            currentUserGroupsLoaded = false
            AppLogger.log("ProcessRecordActivity", "获取用户群组异常: ${e.message}", e)
        }
    }

    private fun filterProcessStepsByResponsibility(processSteps: List<ProcessStep>): List<ProcessStep> {
        if (processSteps.isEmpty()) return processSteps

        return processSteps.filter { step ->
            // 配置历史数据可能出现 responsibleDepartments = null（尽管模型声明为非空）
            // 这里做运行时兜底，避免扫码后加载工序时触发 NPE。
            val responsible = (step.responsibleDepartments as? List<*>)
                .orEmpty()
                .filterIsInstance<String>()
                .map { normalizeGroupName(it) }
                .filter { it.isNotEmpty() }
                .toSet()

            if (responsible.isEmpty()) {
                true
            } else if (!currentUserGroupsLoaded) {
                true
            } else {
                responsible.any { currentUserGroupNames.contains(it) }
            }
        }
    }

    private fun loadProjectConfiguration(
        preferredProductType: String? = null,
        onLoaded: ((Boolean) -> Unit)? = null
    ) {
        val selectedProject = projectManager.getSelectedProcessProject() ?: projectManager.getSelectedProject()
        if (selectedProject == null) {
            Toast.makeText(this, "请先选择项目", Toast.LENGTH_SHORT).show()
            onLoaded?.invoke(false)
            return
        }

        AppLogger.log("ProcessRecordActivity", "Loading configuration for project: $selectedProject")
        
        lifecycleScope.launch {
            try {
                // Load project configuration
                val fileManager = FileManagerFactory.create(
                    this@ProcessRecordActivity,
                    preferencesManager.getUsername(),
                    preferencesManager.getPassword()
                )
                
                currentProjectConfig = projectConfigManager.loadProjectConfigWithSync(selectedProject, fileManager)
                
                AppLogger.log("ProcessRecordActivity", "Project configuration loaded successfully")
                AppLogger.log("ProcessRecordActivity", "Schema version: ${currentProjectConfig?.schemaVersion}")
                AppLogger.log("ProcessRecordActivity", "Product types: ${currentProjectConfig?.productTypes?.size ?: 0}")

                loadCurrentUserGroups()
                
                // Load product types from configuration
                productTypes = currentProjectConfig?.productTypes?.map { it.typeName }?.toTypedArray() ?: emptyArray()
                
                // Log product types and their process steps
                currentProjectConfig?.productTypes?.forEach { productType ->
                    val steps = productType.safeGetProcessSteps()
                    AppLogger.log("ProcessRecordActivity", "Product type: ${productType.typeName}, Process steps: ${steps.size}")
                    steps.forEach { step ->
                        AppLogger.log("ProcessRecordActivity", "  - ${step.name} (order: ${step.order})")
                    }
                }
                
                // Setup product type spinner with loaded types
                setupProductTypeSpinner()

                // Set default product type if available
                if (productTypes.isNotEmpty()) {
                    val normalizedPreferredProductType = preferredProductType?.trim().orEmpty()
                    currentProductType = if (
                        normalizedPreferredProductType.isNotEmpty() &&
                        productTypes.contains(normalizedPreferredProductType)
                    ) {
                        normalizedPreferredProductType
                    } else {
                        productTypes[0]
                    }
                    AppLogger.log("ProcessRecordActivity", "Default product type set to: $currentProductType")
                    val targetIndex = productTypes.indexOf(currentProductType).takeIf { it >= 0 } ?: 0
                    suppressSpinnerProcessReloadOnce = true
                    binding.spinnerProductType.setSelection(targetIndex, false)
                    // 更新产品类型显示
                    updateProductTypeDisplay(currentProductType)
                }
                
                // 更新项目展示信息（包含项目号）
                updateProjectNameDisplay(selectedProject)

                // 加载 QC 策略配置
                try {
                    qcPolicy = qcService.getQcPolicy(selectedProject)
                    AppLogger.log("ProcessRecordActivity", "QC 策略: enabled=${qcPolicy.qcEnabled}, mode=${qcPolicy.enforcementMode}")
                } catch (e: Exception) {
                    AppLogger.log("ProcessRecordActivity", "QC 策略加载失败，使用默认: ${e.message}")
                    qcPolicy = QcPolicy.DEFAULT
                }

                // Don't load process steps here - they will be loaded when product is scanned
                processStepsList.clear()
                processStepAdapter.notifyDataSetChanged()
                onLoaded?.invoke(true)

            } catch (e: Exception) {
                AppLogger.log("ProcessRecordActivity", "Error loading project configuration: ${e.message}", e)
                Toast.makeText(this@ProcessRecordActivity, "配置加载失败: ${e.message}", Toast.LENGTH_SHORT).show()
                onLoaded?.invoke(false)
            }
        }
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
                AppLogger.log("ProcessRecordActivity", "Requesting camera permission for Product Scan")
                requestPermissionLauncher.launch(Manifest.permission.CAMERA)
            }
        }
    }

    private fun startProductQRScanner() {
        AppLogger.log("ProcessRecordActivity", "Launching Enhanced Product QR Scanner")
        val options = enhancedQRScanner.createEnhancedScanOptions("扫描产品二维码")
        productBarcodeLauncher.launch(options)
    }

    private fun showManualInputDialog() {
        val builder = android.app.AlertDialog.Builder(this)
        builder.setTitle("手动输入产品序列号")
        
        // Create input field
        val input = android.widget.EditText(this)
        input.inputType = android.text.InputType.TYPE_CLASS_TEXT
        input.hint = "请输入产品序列号"
        
        // Add padding to input
        val padding = (16 * resources.displayMetrics.density).toInt()
        input.setPadding(padding, padding, padding, padding)
        
        builder.setView(input)
        
        builder.setPositiveButton("确定") { dialog, _ ->
            val serialNumber = SerialNormalizer.normalize(input.text?.toString())
            if (serialNumber.isNotEmpty()) {
                handleProductScanned(serialNumber)
                AppLogger.log("ProcessRecordActivity", "Manual input product serial: $serialNumber")
            } else {
                Toast.makeText(this, "序列号不能为空", Toast.LENGTH_SHORT).show()
            }
            dialog.dismiss()
        }
        
        builder.setNegativeButton("取消") { dialog, _ ->
            dialog.cancel()
        }
        
        val dialog = builder.create()
        dialog.show()
        
        // Auto focus on input field
        input.requestFocus()
        val imm = getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
        imm.showSoftInput(input, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT)
    }

    private fun handleProductScanned(serialNumber: String) {
        val normalizedSerial = SerialNormalizer.normalize(serialNumber)
        if (normalizedSerial.isEmpty()) {
            Toast.makeText(this, "序列号无效，请重试", Toast.LENGTH_SHORT).show()
            return
        }
        val previousSerial = currentProductSerial
        currentProductSerial = normalizedSerial
        binding.tvProductSerial.text = normalizedSerial
        binding.productInfoLayout.visibility = View.VISIBLE
        
        AppLogger.log("ProcessRecordActivity", "Product QR Scanned: $normalizedSerial")
        Toast.makeText(this, "产品扫描成功: $normalizedSerial", Toast.LENGTH_SHORT).show()
        
        // Clear previous photos when scanning new product
        capturedPhotos.clear()
        if (!previousSerial.isNullOrBlank() && previousSerial != normalizedSerial) {
            processStepAdapter.clearQcStatus()
            qcStatusBoundSerial = normalizedSerial
            AppLogger.log("ProcessRecordActivity", "[刷新] 切换序列号，清空旧QC状态: $previousSerial -> $normalizedSerial")
        }

        autoMatchProjectAndProductTypeForSerial(normalizedSerial) { matched ->
            if (!matched) {
                AppLogger.log("ProcessRecordActivity", "Skip loading process steps because serial rule auto-match did not resolve a valid project/product type")
                return@autoMatchProjectAndProductTypeForSerial
            }
            // Load and display process steps for this product
            val hasAvailableProcessSteps = loadProcessStepsForProduct(normalizedSerial)

            // 如果没有需要拍照的工序，则回退到物料记录拍照
            if (!hasAvailableProcessSteps) {
                AppLogger.log("ProcessRecordActivity", "Skip material photo fallback because process steps are unavailable")
                return@autoMatchProjectAndProductTypeForSerial
            }
            val hasPhotoRequiredStep = processStepsList.any { it.photoRequired }
            if (!hasPhotoRequiredStep) {
                val projectName = projectManager.getSelectedProcessProject() ?: currentProjectConfig?.projectName ?: ""
                val projectCode = currentProjectConfig?.projectCode ?: ""
                val productTypeName = currentProductType ?: currentProjectConfig?.productTypes?.firstOrNull()?.typeName
                val modelNumber = productTypeName?.let { currentProjectConfig?.getProductTypeConfig(it)?.modelNumber } ?: ""
                val operator = getCurrentOperatorName()

                AppLogger.log("ProcessRecordActivity", "No photo-required steps, redirecting to PhotoCaptureActivity")
                launchMaterialPhotoCapture(projectName, projectCode, productTypeName, modelNumber, operator)
            }
        }
    }

    private fun openCameraForProcessStep(processStep: ProcessStep) {
        val productSerial = currentProductSerial
        if (productSerial == null) {
            Toast.makeText(this, "请先扫描产品二维码", Toast.LENGTH_SHORT).show()
            return
        }

        val projectName = projectManager.getSelectedProcessProject() ?: currentProjectConfig?.projectName ?: ""
        val projectCode = currentProjectConfig?.projectCode ?: ""
        val productTypeName = currentProductType ?: processStep.productType
        val modelNumber = currentProjectConfig?.getProductTypeConfig(productTypeName)?.modelNumber ?: ""
        val operator = getCurrentOperatorName()

        if (!processStep.photoRequired) {
            AppLogger.log("ProcessRecordActivity", "Process step ${processStep.name} does not require photo, redirecting")
            launchMaterialPhotoCapture(projectName, projectCode, productTypeName, modelNumber, operator)
            return
        }

        // 根据 attachmentType 路由（先检查前面工序是否有照片）
        when (processStep.attachmentType) {
            "pdf" -> {
                AppLogger.log("ProcessRecordActivity", "工序 ${processStep.name} 类型为 PDF，打开文件选择器")
                checkMissingPhotosBeforeCapture(processStep) {
                    openPdfPicker(processStep)
                }
            }
            "both" -> {
                AppLogger.log("ProcessRecordActivity", "工序 ${processStep.name} 类型为 both，显示选择对话框")
                checkMissingPhotosBeforeCapture(processStep) {
                    showAttachmentTypeDialog(processStep, productSerial, projectName, projectCode, productTypeName, modelNumber, operator)
                }
            }
            else -> {
                // "photo" 或默认：走原有相机流程
                // 检查相机访问权限
                if (!checkCameraAccessPermission(permissionUIController)) {
                    return
                }
                checkMissingPhotosBeforeCapture(processStep) {
                    launchPhotoCaptureWithQcCheck(processStep, productSerial, projectName, projectCode, productTypeName, modelNumber, operator)
                }
            }
        }
    }

    /**
     * 带 QC 前置检查的拍（从原 openCameraForProcessStep 提取）
     */
    private fun launchPhotoCaptureWithQcCheck(
        processStep: ProcessStep,
        productSerial: String,
        projectName: String,
        projectCode: String,
        productTypeName: String?,
        modelNumber: String,
        operator: String
    ) {
        // QC 前置检查：检查前面工序的照片和 QC 状态
        if (qcPolicy.qcEnabled && qcPolicy.checkPreviousPhotos && processStep.order > 1) {
            val requestKey = listOf(productSerial, projectName, productTypeName.orEmpty(), processStep.order.toString()).joinToString("|")
            if (qcPreCheckJob?.isActive == true && qcPreCheckKey == requestKey) {
                AppLogger.log("ProcessRecordActivity", "[QC] 前置检查进行中，忽略重复请求: ${processStep.name}")
                Toast.makeText(this, "正在检查前面工序，请稍候", Toast.LENGTH_SHORT).show()
                return
            }
            AppLogger.log("ProcessRecordActivity", "[QC] 开始检查前面工序, 当前工序: ${processStep.name} (order=${processStep.order})")
            qcPreCheckKey = requestKey
            qcPreCheckJob = lifecycleScope.launch {
                try {
                    performQcPreCheck(processStep, productSerial, projectName, projectCode, productTypeName, modelNumber, operator)
                } finally {
                    if (qcPreCheckKey == requestKey) {
                        qcPreCheckKey = null
                    }
                    if (qcPreCheckJob == this) {
                        qcPreCheckJob = null
                    }
                }
            }
        } else {
            // QC 未启用或第一个工序，直接打开相机
            launchProcessPhotoCapture(productSerial, projectName, projectCode, productTypeName, modelNumber, operator, processStep.name, processStep.order)
        }
    }

    /**
     * 检查前面工序是否有照片（不依赖 QC 启用）
     */
    private fun checkMissingPhotosBeforeCapture(processStep: ProcessStep, onContinue: () -> Unit) {
        if (processStep.order <= 1) {
            onContinue()
            return
        }
        val missingSteps = processStepsList
            .filter { it.order < processStep.order && it.photoRequired }
            .filter { !processStepAdapter.hasPhotoForStep(it.id) }

        if (missingSteps.isEmpty()) {
            onContinue()
        } else {
            showMissingPhotoWarning(missingSteps, onContinue)
        }
    }

    /**
     * 显示前面工序未拍照的红色警告
     */
    private fun showMissingPhotoWarning(missingSteps: List<ProcessStep>, onContinue: () -> Unit) {
        val stepNames = missingSteps.joinToString("\n") { "  - 步骤${it.order}: ${it.name}" }
        val message = "以下工序尚未拍照：\n$stepNames\n\n是否跳过继续？"

        AlertDialog.Builder(this)
            .setTitle("前面工序未拍照")
            .setMessage(message)
            .setIcon(android.R.drawable.ic_dialog_alert)
            .setPositiveButton("继续拍照") { dialog, _ ->
                dialog.dismiss()
                onContinue()
            }
            .setNegativeButton("返回补拍") { dialog, _ ->
                dialog.dismiss()
            }
            .setCancelable(true)
            .show()
    }

    /**
     * 打开 PDF 文件选择器
     */
    private fun openPdfPicker(processStep: ProcessStep) {
        currentProcessStep = processStep
        val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
            type = "application/pdf"
            addCategory(Intent.CATEGORY_OPENABLE)
        }
        try {
            pdfPickerLauncher.launch(intent)
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, "未找到文件管理器，无法选择PDF", Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * 显示附件类型选择对话框（拍照 / PDF）
     */
    private fun showAttachmentTypeDialog(
        processStep: ProcessStep,
        productSerial: String,
        projectName: String,
        projectCode: String,
        productTypeName: String?,
        modelNumber: String,
        operator: String
    ) {
        AlertDialog.Builder(this)
            .setTitle("选择附件类型")
            .setItems(arrayOf("拍照", "选择PDF文件")) { _, which ->
                when (which) {
                    0 -> {
                        if (!checkCameraAccessPermission(permissionUIController)) return@setItems
                        launchPhotoCaptureWithQcCheck(processStep, productSerial, projectName, projectCode, productTypeName, modelNumber, operator)
                    }
                    1 -> openPdfPicker(processStep)
                }
            }
            .show()
    }

    /**
     * 处理选中的 PDF 文件
     */
    private fun handlePdfSelected(uri: Uri, processStep: ProcessStep) {
        lifecycleScope.launch {
            try {
                // 验证文件大小
                val fileSize = FileUtils.getFileSize(this@ProcessRecordActivity, uri)
                if (!FileUtils.validateFileSize(fileSize)) {
                    Toast.makeText(this@ProcessRecordActivity, "PDF文件大小不能超过20MB", Toast.LENGTH_LONG).show()
                    return@launch
                }

                val fileName = FileUtils.getFileName(this@ProcessRecordActivity, uri)
                AppLogger.log("ProcessRecordActivity", "PDF 已选择: $fileName (${fileSize / 1024}KB), 工序: ${processStep.name}")

                // 显示上传进度
                showUploadProgress("正在上传PDF...")

                // 上传 PDF（Task 3 实现）
                uploadPdf(uri, processStep)

            } catch (e: Exception) {
                AppLogger.log("ProcessRecordActivity", "PDF 处理失败: ${e.message}", e)
                Toast.makeText(this@ProcessRecordActivity, "处理PDF失败: ${e.message}", Toast.LENGTH_LONG).show()
            } finally {
                hideUploadProgress()
            }
        }
    }

    /**
     * 上传 PDF 文件到服务端
     */
    private suspend fun uploadPdf(uri: Uri, processStep: ProcessStep) {
        withContext(Dispatchers.IO) {
            try {
                val file = FileUtils.uriToFile(this@ProcessRecordActivity, uri)

                val requestFile = file.asRequestBody("application/pdf".toMediaTypeOrNull())
                val body = MultipartBody.Part.createFormData("file", file.name, requestFile)

                val projectName = (projectManager.getSelectedProcessProject()
                    ?: currentProjectConfig?.projectName ?: "")
                    .toRequestBody("text/plain".toMediaTypeOrNull())
                val productType = (currentProductType ?: "")
                    .toRequestBody("text/plain".toMediaTypeOrNull())
                val productSerial = (currentProductSerial ?: "")
                    .toRequestBody("text/plain".toMediaTypeOrNull())
                val processName = processStep.name
                    .toRequestBody("text/plain".toMediaTypeOrNull())

                val apiService = ApiClient.getApiService(this@ProcessRecordActivity)
                val response = apiService.uploadDocument(
                    file = body,
                    productSerial = productSerial,
                    projectName = projectName,
                    productType = productType,
                    processName = processName
                )

                // 清理临时文件
                file.delete()

                withContext(Dispatchers.Main) {
                    if (response.isSuccessful && response.body()?.success == true) {
                        AppLogger.log("ProcessRecordActivity", "PDF 上传成功: ${response.body()?.filename}")
                        Toast.makeText(this@ProcessRecordActivity, "PDF上传成功", Toast.LENGTH_SHORT).show()
                        // 本地立即更新 PDF 计数
                        processStepAdapter.incrementPdfCount(processStep.id)
                        // 刷新 QC 状态
                        refreshQcStatus(reason = "pdf_upload")
                    } else {
                        val errorMsg = response.body()?.error ?: response.message()
                        AppLogger.log("ProcessRecordActivity", "PDF 上传失败: $errorMsg")
                        ApkTelemetryManager.captureUploadFailure(
                            this@ProcessRecordActivity,
                            trigger = "process_pdf_upload",
                            feature = "pdf_upload",
                            summary = "PDF 上传失败: $errorMsg",
                            httpStatus = response.code(),
                            extras = mapOf(
                                "projectName" to (currentProjectConfig?.projectName ?: ""),
                                "productType" to (currentProductType ?: ""),
                                "productSerial" to (currentProductSerial ?: ""),
                                "processName" to processStep.name,
                                "uri" to uri.toString(),
                            ),
                        )
                        Toast.makeText(this@ProcessRecordActivity, "上传失败: $errorMsg", Toast.LENGTH_LONG).show()
                    }
                }
            } catch (e: Exception) {
                ApkTelemetryManager.captureUploadFailure(
                    this@ProcessRecordActivity,
                    trigger = "process_pdf_upload_exception",
                    feature = "pdf_upload",
                    summary = "PDF 上传异常",
                    throwable = e,
                    extras = mapOf(
                        "projectName" to (currentProjectConfig?.projectName ?: ""),
                        "productType" to (currentProductType ?: ""),
                        "productSerial" to (currentProductSerial ?: ""),
                        "processName" to processStep.name,
                        "uri" to uri.toString(),
                    ),
                )
                withContext(Dispatchers.Main) {
                    AppLogger.log("ProcessRecordActivity", "PDF 上传异常: ${e.message}", e)
                    Toast.makeText(this@ProcessRecordActivity, "上传失败: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun showUploadProgress(message: String) {
        @Suppress("DEPRECATION")
        progressDialog = ProgressDialog(this).apply {
            setMessage(message)
            setCancelable(false)
            show()
        }
    }

    private fun hideUploadProgress() {
        progressDialog?.dismiss()
        progressDialog = null
    }

    /**
     * 查看 PDF 文件（本地或远程）
     */
    fun viewPdf(pdfPath: String) {
        try {
            if (pdfPath.startsWith("http")) {
                downloadAndViewPdf(pdfPath)
                return
            }

            val file = File(pdfPath)
            if (!file.exists()) {
                Toast.makeText(this, "PDF文件不存在", Toast.LENGTH_SHORT).show()
                return
            }

            val uri = FileProvider.getUriForFile(this, "${packageName}.fileprovider", file)
            launchPdfViewer(uri)
        } catch (e: Exception) {
            AppLogger.log("ProcessRecordActivity", "打开PDF失败: ${e.message}", e)
            Toast.makeText(this, "打开PDF失败: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * 下载远程 PDF 并打开
     */
    private fun downloadAndViewPdf(url: String) {
        lifecycleScope.launch {
            try {
                showUploadProgress("正在下载PDF...")

                withContext(Dispatchers.IO) {
                    val apiService = ApiClient.getApiService(this@ProcessRecordActivity)
                    val filename = url.substringAfterLast("/")
                    val response = apiService.downloadDocument(filename)

                    if (!response.isSuccessful) {
                        throw Exception("下载失败: ${response.code()}")
                    }

                    val downloadDir = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
                        ?: throw Exception("无法访问下载目录")
                    val file = File(downloadDir, filename)

                    response.body()?.byteStream()?.use { input ->
                        FileOutputStream(file).use { output ->
                            input.copyTo(output)
                        }
                    }

                    withContext(Dispatchers.Main) {
                        hideUploadProgress()
                        val uri = FileProvider.getUriForFile(
                            this@ProcessRecordActivity,
                            "${packageName}.fileprovider",
                            file
                        )
                        launchPdfViewer(uri)
                    }
                }
            } catch (e: Exception) {
                hideUploadProgress()
                AppLogger.log("ProcessRecordActivity", "下载PDF失败: ${e.message}", e)
                Toast.makeText(this@ProcessRecordActivity, "下载PDF失败: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    /**
     * 启动外部 PDF 阅读器
     */
    private fun launchPdfViewer(uri: Uri) {
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/pdf")
            flags = Intent.FLAG_ACTIVITY_NO_HISTORY or Intent.FLAG_GRANT_READ_URI_PERMISSION
        }
        try {
            startActivity(intent)
        } catch (e: ActivityNotFoundException) {
            showInstallPdfReaderDialog()
        }
    }

    /**
     * 提示安装 PDF 阅读器
     */
    private fun showInstallPdfReaderDialog() {
        AlertDialog.Builder(this)
            .setTitle("需要PDF阅读器")
            .setMessage("您的设备上没有安装PDF阅读器，是否前往应用商店下载？")
            .setPositiveButton("前往下载") { _, _ ->
                try {
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("market://search?q=pdf reader")))
                } catch (e: Exception) {
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/search?q=pdf+reader")))
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }

    /**
     * 执行 QC 前置检查，根据策略弹出警告或阻断
     */
    private suspend fun performQcPreCheck(
        processStep: ProcessStep,
        productSerial: String,
        projectName: String,
        projectCode: String,
        productTypeName: String?,
        modelNumber: String,
        operator: String
    ) {
        val checkResult = qcService.checkPreviousSteps(
            productSerial = productSerial,
            processIndex = processStep.order,
            projectName = projectName,
            productType = productTypeName ?: ""
        )

        if (checkResult == null) {
            // 网络请求失败，根据策略决定是否放行
            AppLogger.log("ProcessRecordActivity", "[QC] 前置检查请求失败")
            if (qcPolicy.enforcementMode == "block") {
                showQcBlockDialog("QC 服务连接失败，无法验证前面工序状态。\n请检查网络后重试。")
            } else {
                showQcWarnDialog(
                    "QC 服务连接失败，无法验证前面工序状态。",
                    onContinue = {
                        launchProcessPhotoCapture(productSerial, projectName, projectCode, productTypeName, modelNumber, operator, processStep.name, processStep.order)
                    }
                )
            }
            return
        }

        if (checkResult.allPassed) {
            // 前面工序全部通过，直接打开相机
            AppLogger.log("ProcessRecordActivity", "[QC] 前面工序全部通过")
            launchProcessPhotoCapture(productSerial, projectName, projectCode, productTypeName, modelNumber, operator, processStep.name, processStep.order)
            return
        }

        // 构建问题描述
        val issues = buildQcIssueMessage(checkResult)
        AppLogger.log("ProcessRecordActivity", "[QC] 发现问题: $issues")

        if (qcPolicy.enforcementMode == "block") {
            showQcBlockDialog(issues)
        } else {
            showQcWarnDialog(issues) {
                launchProcessPhotoCapture(productSerial, projectName, projectCode, productTypeName, modelNumber, operator, processStep.name, processStep.order)
            }
        }
    }

    /**
     * 构建 QC 问题描述文本
     */
    private fun buildQcIssueMessage(result: QcPreviousCheckResponse): String {
        val sb = StringBuilder()
        if (result.missingPhotos.isNotEmpty()) {
            sb.append("以下工序尚未上传照片：\n")
            result.missingPhotos.forEach { sb.append("  - $it\n") }
        }
        if (result.failedSteps.isNotEmpty()) {
            sb.append("以下工序 QC 未通过：\n")
            result.failedSteps.forEach { sb.append("  - $it\n") }
        }
        if (result.ngSteps.isNotEmpty()) {
            sb.append("以下工序需人工复核：\n")
            result.ngSteps.forEach { sb.append("  - $it\n") }
        }
        return sb.toString().trimEnd()
    }

    /**
     * 显示 QC 警告对话框（允许继续）
     */
    private fun showQcWarnDialog(message: String, onContinue: () -> Unit) {
        AlertDialog.Builder(this)
            .setTitle("工序检查警告")
            .setMessage(message)
            .setIcon(android.R.drawable.ic_dialog_alert)
            .setPositiveButton("继续拍照") { dialog, _ ->
                dialog.dismiss()
                onContinue()
            }
            .setNegativeButton("返回补拍") { dialog, _ ->
                dialog.dismiss()
            }
            .setCancelable(false)
            .show()
    }

    /**
     * 显示 QC 阻断对话框（不允许继续）
     */
    private fun showQcBlockDialog(message: String) {
        AlertDialog.Builder(this)
            .setTitle("工序检查未通过")
            .setMessage("$message\n\n请先完成前面工序的拍照和质检。")
            .setIcon(android.R.drawable.ic_dialog_alert)
            .setPositiveButton("知道了") { dialog, _ ->
                dialog.dismiss()
            }
            .setCancelable(false)
            .show()
    }

    /**
     * 启动工序拍照（提取公共逻辑）
     */
    private fun launchProcessPhotoCapture(
        productSerial: String,
        projectName: String,
        projectCode: String,
        productTypeName: String?,
        modelNumber: String,
        operator: String,
        processStepName: String,
        processIndex: Int
    ) {
        val intent = Intent(this, PhotoCaptureActivity::class.java).apply {
            putExtra(PhotoCaptureActivity.EXTRA_PRODUCT_SERIAL, productSerial)
            putExtra(PhotoCaptureActivity.EXTRA_PROJECT_NAME, projectName)
            putExtra(PhotoCaptureActivity.EXTRA_PROJECT_CODE, projectCode)
            putExtra(PhotoCaptureActivity.EXTRA_PRODUCT_TYPE, productTypeName)
            putExtra(PhotoCaptureActivity.EXTRA_MODEL_NUMBER, modelNumber)
            putExtra(PhotoCaptureActivity.EXTRA_OPERATOR_NAME, operator)
            putExtra(PhotoCaptureActivity.EXTRA_PROCESS_STEP_NAME, processStepName)
            putExtra(PhotoCaptureActivity.EXTRA_PROCESS_INDEX, processIndex)
            putExtra(PhotoCaptureActivity.EXTRA_CAPTURE_MODE, PhotoCaptureActivity.CaptureMode.PROCESS)
        }
        photoCaptureResultLauncher.launch(intent)
    }

    private fun launchMaterialPhotoCapture(
        projectName: String,
        projectCode: String,
        productType: String?,
        modelNumber: String,
        operator: String
    ) {
        val productSerial = currentProductSerial ?: return
        val intent = Intent(this, PhotoCaptureActivity::class.java).apply {
            putExtra(PhotoCaptureActivity.EXTRA_PRODUCT_SERIAL, productSerial)
            putExtra(PhotoCaptureActivity.EXTRA_PROJECT_NAME, projectName)
            putExtra(PhotoCaptureActivity.EXTRA_PROJECT_CODE, projectCode)
            putExtra(PhotoCaptureActivity.EXTRA_PRODUCT_TYPE, productType ?: "")
            putExtra(PhotoCaptureActivity.EXTRA_MODEL_NUMBER, modelNumber)
            putExtra(PhotoCaptureActivity.EXTRA_OPERATOR_NAME, operator)
            putExtra(PhotoCaptureActivity.EXTRA_CAPTURE_MODE, PhotoCaptureActivity.CaptureMode.MATERIAL)
        }
        startActivity(intent)
    }

    /**
     * 解析 QC findings JSON
     */
    private fun parseFindingsJson(json: String?): List<ProcessStepAdapter.FindingInfo> {
        if (json.isNullOrBlank()) return emptyList()
        return try {
            val type = object : com.google.gson.reflect.TypeToken<List<com.testcenter.qrscanner.qc.QcFinding>>() {}.type
            val qcFindings: List<com.testcenter.qrscanner.qc.QcFinding> = com.google.gson.Gson().fromJson(json, type)
            qcFindings.map { ProcessStepAdapter.FindingInfo(it.severity, it.description, it.location) }
        } catch (e: Exception) {
            AppLogger.log("ProcessRecordActivity", "解析 findings JSON 失败: ${e.message}")
            emptyList()
        }
    }

    /**
     * 点击工序卡片 → 显示 QC 详情对话框
     */
    private fun showStepDetailDialog(processStep: ProcessStep, statusInfo: ProcessStepAdapter.QcStatusInfo?) {
        val root = ScrollView(this)
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val p = (16 * resources.displayMetrics.density).toInt()
            setPadding(p, p, p, p)
        }
        root.addView(content)

        val tvUploadInfo = TextView(this).apply {
            textSize = 16f
            text = buildAttachmentSummary(statusInfo)
        }
        content.addView(tvUploadInfo)

        val tvQcResult = TextView(this).apply {
            textSize = 15f
            setPadding(0, 16, 0, 0)
            text = buildQcResultText(statusInfo)
        }
        content.addView(tvQcResult)

        val tvFindings = TextView(this).apply {
            textSize = 14f
            setPadding(0, 12, 0, 0)
            text = buildFindingsText(statusInfo)
        }
        content.addView(tvFindings)

        val tvPreviewTitle = TextView(this).apply {
            textSize = 15f
            setPadding(0, 16, 0, 8)
            text = "工序照片预览（加载中...）"
        }
        content.addView(tvPreviewTitle)

        val previewScroll = HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
        }
        val previewContainer = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        previewScroll.addView(previewContainer)
        content.addView(previewScroll)

        val actionRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, 18, 0, 0)
        }
        val btnRunQc = Button(this).apply {
            text = "QC检查"
        }
        actionRow.addView(btnRunQc)

        val btnViewPhotos = Button(this).apply {
            text = "查看照片"
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            lp.marginStart = (8 * resources.displayMetrics.density).toInt()
            layoutParams = lp
            isEnabled = statusInfo?.hasPhoto == true
        }
        actionRow.addView(btnViewPhotos)

        val btnViewDocs = Button(this).apply {
            text = "查看文档"
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            lp.marginStart = (8 * resources.displayMetrics.density).toInt()
            layoutParams = lp
            val isPdfStep = processStep.attachmentType == "pdf" || processStep.attachmentType == "both"
            visibility = if (isPdfStep || (statusInfo?.pdfCount ?: 0) > 0) View.VISIBLE else View.GONE
        }
        actionRow.addView(btnViewDocs)
        content.addView(actionRow)

        val tvHumanTitle = TextView(this).apply {
            textSize = 15f
            setPadding(0, 18, 0, 8)
            text = "人工确认/修复"
        }
        content.addView(tvHumanTitle)

        val statusSpinner = Spinner(this)
        val statusOptions = listOf("未确认", "人工通过", "人工不通过")
        statusSpinner.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_item,
            statusOptions
        ).apply {
            setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }
        statusSpinner.setSelection(
            when (statusInfo?.qcStatus) {
                "pass" -> 1
                "fail", "ng" -> 2
                else -> 0
            }
        )
        content.addView(statusSpinner)

        val etHumanNote = EditText(this).apply {
            hint = "人工结论备注（可选）"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            minLines = 2
            maxLines = 4
            setPadding(0, 10, 0, 0)
        }
        content.addView(etHumanNote)

        val btnSubmitHuman = Button(this).apply {
            text = "提交人工确认"
            setPadding(0, 16, 0, 0)
        }
        content.addView(btnSubmitHuman)

        val dialog = AlertDialog.Builder(this)
            .setTitle("${processStep.name}（步骤${processStep.order}）")
            .setView(root)
            .setPositiveButton("关闭", null)
            .show()

        btnViewPhotos.setOnClickListener {
            viewProcessPhotos(processStep)
        }
        btnViewDocs.setOnClickListener {
            viewProcessDocuments(processStep)
        }
        btnRunQc.setOnClickListener {
            runQcCheckForStep(processStep) { newStatus ->
                val latest = processStepAdapter.getQcStatusForStep(processStep.id) ?: newStatus
                tvUploadInfo.text = buildAttachmentSummary(latest)
                tvQcResult.text = buildQcResultText(latest)
                tvFindings.text = buildFindingsText(latest)
                if (latest.hasPhoto) {
                    btnViewPhotos.isEnabled = true
                }
                loadStepPhotoPreviewInto(processStep, tvPreviewTitle, previewContainer)
                statusSpinner.setSelection(
                    when (latest.qcStatus) {
                        "pass" -> 1
                        "fail", "ng" -> 2
                        else -> statusSpinner.selectedItemPosition
                    }
                )
            }
        }
        btnSubmitHuman.setOnClickListener {
            val humanStatus = when (statusSpinner.selectedItemPosition) {
                1 -> "pass"
                2 -> "fail"
                else -> ""
            }
            if (humanStatus.isEmpty()) {
                Toast.makeText(this, "请先选择人工结论", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            btnSubmitHuman.isEnabled = false
            submitManualQcConfirmation(
                processStep = processStep,
                humanStatus = humanStatus,
                humanSummary = etHumanNote.text.toString().trim()
            ) { ok, message ->
                btnSubmitHuman.isEnabled = true
                Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
                if (ok) {
                    val existing = processStepAdapter.getQcStatusForStep(processStep.id)
                    val base = existing ?: statusInfo ?: ProcessStepAdapter.QcStatusInfo()
                    val finalHumanSummary = etHumanNote.text.toString().trim()
                        .ifBlank { if (humanStatus == "pass") "人工确认通过" else "人工确认不通过" }
                    val aiFindings = if (base.aiFindings.isNotEmpty()) base.aiFindings else base.findings
                    val humanFindings = if (humanStatus == "pass") {
                        emptyList()
                    } else {
                        if (base.humanFindings.isNotEmpty()) base.humanFindings
                        else if (aiFindings.isNotEmpty()) aiFindings
                        else listOf(ProcessStepAdapter.FindingInfo("major", finalHumanSummary))
                    }
                    val merged = ProcessStepAdapter.QcStatusInfo(
                        hasPhoto = base.hasPhoto,
                        photoCount = base.photoCount,
                        qcStatus = humanStatus,
                        qcSummary = finalHumanSummary,
                        findings = humanFindings,
                        pdfCount = base.pdfCount,
                        aiStatus = base.aiStatus ?: base.qcStatus,
                        aiSummary = base.aiSummary ?: base.qcSummary,
                        aiFindings = aiFindings,
                        humanStatus = humanStatus,
                        humanSummary = finalHumanSummary,
                        humanFindings = humanFindings
                    )
                    processStepAdapter.updateQcStatusFull(
                        processStep.id,
                        merged.hasPhoto,
                        merged.photoCount,
                        merged.qcStatus,
                        merged.qcSummary,
                        merged.findings,
                        merged.pdfCount,
                        merged.aiStatus,
                        merged.aiSummary,
                        merged.aiFindings,
                        merged.humanStatus,
                        merged.humanSummary,
                        merged.humanFindings
                    )
                    tvUploadInfo.text = buildAttachmentSummary(merged)
                    tvQcResult.text = buildQcResultText(merged)
                    tvFindings.text = buildFindingsText(merged)
                }
            }
        }
        dialog.setOnDismissListener {
            refreshQcStatus(reason = "step_detail_dismiss")
        }

        loadStepPhotoPreviewInto(processStep, tvPreviewTitle, previewContainer)
    }

    private fun buildAttachmentSummary(statusInfo: ProcessStepAdapter.QcStatusInfo?): String {
        val parts = mutableListOf<String>()
        if (statusInfo?.hasPhoto == true) {
            parts.add("${statusInfo.photoCount} 张照片")
        }
        if ((statusInfo?.pdfCount ?: 0) > 0) {
            parts.add("${statusInfo?.pdfCount ?: 0} 个文档")
        }
        return if (parts.isEmpty()) "暂无上传记录" else "已上传：${parts.joinToString("，")}"
    }

    private fun buildQcResultText(statusInfo: ProcessStepAdapter.QcStatusInfo?): String {
        val effectiveStatus = statusInfo?.qcStatus
        val qcLabel = when (effectiveStatus) {
            "pass" -> "QC结果：通过"
            "fail" -> "QC结果：未通过"
            "ng" -> "QC结果：待复核"
            "skipped" -> "QC结果：未启用"
            else -> if (statusInfo?.hasPhoto == true) "QC结果：待检测" else "QC结果：未检测"
        }
        val lines = mutableListOf(qcLabel)
        val effectiveSummary = statusInfo?.qcSummary?.takeIf { it.isNotBlank() }
        if (!effectiveSummary.isNullOrBlank()) {
            lines.add("当前结论：$effectiveSummary")
        }
        val aiStatus = statusInfo?.aiStatus
        val aiSummary = statusInfo?.aiSummary?.takeIf { it.isNotBlank() }
        if (!aiStatus.isNullOrBlank() || !aiSummary.isNullOrBlank()) {
            val aiLabel = when (aiStatus) {
                "pass" -> "通过"
                "fail" -> "未通过"
                "ng" -> "待复核"
                else -> "未提供"
            }
            lines.add("AI结论：$aiLabel${if (!aiSummary.isNullOrBlank()) " - $aiSummary" else ""}")
        }
        val humanStatus = statusInfo?.humanStatus
        val humanSummary = statusInfo?.humanSummary?.takeIf { it.isNotBlank() }
        if (!humanStatus.isNullOrBlank() || !humanSummary.isNullOrBlank()) {
            val humanLabel = when (humanStatus) {
                "pass" -> "通过"
                "fail" -> "不通过"
                "ng" -> "待复核"
                else -> "未提供"
            }
            lines.add("人工结论：$humanLabel${if (!humanSummary.isNullOrBlank()) " - $humanSummary" else ""}")
        }
        return lines.joinToString("\n")
    }

    private fun buildFindingsText(statusInfo: ProcessStepAdapter.QcStatusInfo?): String {
        fun formatFindings(title: String, findings: List<ProcessStepAdapter.FindingInfo>): String {
            if (findings.isEmpty()) return "$title：无"
            val lines = findings.mapIndexed { i, finding ->
                val severityLabel = when (finding.severity) {
                    "critical" -> "[严重]"
                    "major" -> "[主要]"
                    else -> "[轻微]"
                }
                val location = if (finding.location.isBlank()) "" else "（${finding.location}）"
                "${i + 1}. $severityLabel ${finding.description}$location"
            }
            return "$title：\n${lines.joinToString("\n")}"
        }

        val aiFindings = statusInfo?.aiFindings ?: emptyList()
        val humanFindings = statusInfo?.humanFindings ?: emptyList()
        val effectiveFindings = statusInfo?.findings ?: emptyList()
        val blocks = mutableListOf<String>()
        blocks.add(formatFindings("当前问题明细", effectiveFindings))
        if (aiFindings.isNotEmpty() || humanFindings.isNotEmpty()) {
            blocks.add(formatFindings("AI问题明细", aiFindings))
            blocks.add(formatFindings("人工问题明细", humanFindings))
        }
        return blocks.joinToString("\n\n")
    }

    private fun mapDefectsToFindings(defects: List<com.testcenter.qrscanner.qc.QcDefectInfo>): List<ProcessStepAdapter.FindingInfo> {
        return defects.map { defect ->
            ProcessStepAdapter.FindingInfo(
                severity = defect.severity.ifBlank { "major" },
                description = defect.description.ifBlank { "未提供问题描述" },
                location = defect.location
            )
        }
    }

    private fun runQcCheckForStep(
        processStep: ProcessStep,
        onDone: (ProcessStepAdapter.QcStatusInfo) -> Unit
    ) {
        val serial = currentProductSerial
        val projectName = projectManager.getSelectedProcessProject() ?: currentProjectConfig?.projectName
        val productType = currentProductType
        if (serial.isNullOrBlank() || projectName.isNullOrBlank() || productType.isNullOrBlank()) {
            Toast.makeText(this, "缺少产品/项目信息，无法执行QC检查", Toast.LENGTH_SHORT).show()
            return
        }

        showUploadProgress("正在执行QC检查...")
        lifecycleScope.launch {
            try {
                val photoBytes = withContext(Dispatchers.IO) {
                    loadStepPhotoBytesForQc(processStep)
                }
                if (photoBytes.isEmpty()) {
                    Toast.makeText(this@ProcessRecordActivity, "该工序暂无可分析照片", Toast.LENGTH_SHORT).show()
                    return@launch
                }
                val analyzeResult = qcService.analyzePhotos(
                    photoBytesList = photoBytes,
                    productSerial = serial,
                    processName = processStep.name,
                    processIndex = processStep.order,
                    projectName = projectName,
                    productType = productType
                )
                val findings = analyzeResult.findings.map {
                    ProcessStepAdapter.FindingInfo(
                        severity = it.severity,
                        description = it.description,
                        location = it.location
                    )
                }
                val existing = processStepAdapter.getQcStatusForStep(processStep.id)
                val merged = ProcessStepAdapter.QcStatusInfo(
                    hasPhoto = true,
                    photoCount = maxOf(existing?.photoCount ?: 0, photoBytes.size),
                    qcStatus = analyzeResult.status,
                    qcSummary = analyzeResult.summary,
                    findings = findings,
                    pdfCount = existing?.pdfCount ?: 0,
                    aiStatus = analyzeResult.status,
                    aiSummary = analyzeResult.summary,
                    aiFindings = findings,
                    humanStatus = existing?.humanStatus,
                    humanSummary = existing?.humanSummary,
                    humanFindings = existing?.humanFindings ?: emptyList()
                )
                processStepAdapter.updateQcStatusFull(
                    processStep.id,
                    merged.hasPhoto,
                    merged.photoCount,
                    merged.qcStatus,
                    merged.qcSummary,
                    merged.findings,
                    merged.pdfCount,
                    merged.aiStatus,
                    merged.aiSummary,
                    merged.aiFindings,
                    merged.humanStatus,
                    merged.humanSummary,
                    merged.humanFindings
                )
                onDone(merged)
                Toast.makeText(
                    this@ProcessRecordActivity,
                    "QC检查完成：${if (analyzeResult.status == "pass") "通过" else "需复核"}",
                    Toast.LENGTH_SHORT
                ).show()
            } catch (e: Exception) {
                AppLogger.log("ProcessRecordActivity", "执行QC检查失败: ${e.message}", e)
                Toast.makeText(this@ProcessRecordActivity, "QC检查失败: ${e.message}", Toast.LENGTH_SHORT).show()
            } finally {
                hideUploadProgress()
            }
        }
    }

    private fun getLocalRuleMatchCandidateProjects(): List<String> {
        return buildList {
            addAll(projectConfigManager.getCachedProjectNames())
            projectManager.getSelectedProcessProject()?.let { add(it) }
            projectManager.getSelectedProject()?.let { add(it) }
            currentProjectConfig?.projectName?.let { add(it) }
        }
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .distinct()
    }
    private suspend fun resolveSerialRuleMatchesFromServer(
        serialNumber: String
    ): List<ProjectConfigManager.SerialRuleMatch> {
        return try {
            val response = withContext(Dispatchers.IO) {
                ApiClient.getApiService(this@ProcessRecordActivity).resolveSerialRule(serialNumber)
            }
            if (!response.isSuccessful) {
                AppLogger.log(
                    "ProcessRecordActivity",
                    "[规则匹配] 服务端前缀规则解析失败: HTTP ${response.code()}"
                )
                return emptyList()
            }

            val body = response.body()
            if (body?.success != true) {
                AppLogger.log(
                    "ProcessRecordActivity",
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
            AppLogger.log("ProcessRecordActivity", "[规则匹配] 服务端前缀规则解析异常: ${e.message}", e)
            emptyList()
        }
    }

    private fun handleSerialRuleMatches(
        serialNumber: String,
        ruleMatches: List<ProjectConfigManager.SerialRuleMatch>,
        onDone: (Boolean) -> Unit
    ) {
        if (ruleMatches.isNotEmpty()) {
            AppLogger.log(
                "ProcessRecordActivity",
                "[规则匹配] 命中: serial=$serialNumber, matches=${ruleMatches.joinToString { "${it.projectName}/${it.productType}:${it.prefix}" }}"
            )
        }

        when {
            ruleMatches.size == 1 -> {
                val ruleMatch = ruleMatches.first()
                applyResolvedProjectAndProductType(ruleMatch.projectName, ruleMatch.productType) {
                    onDone(it)
                }
            }
            ruleMatches.size > 1 -> {
                handleRuleMatchFailure("扫码命中多个二维码前缀规则，请检查项目配置")
                onDone(false)
            }
            else -> {
                handleRuleMatchFailure("未匹配到项目规则，请检查二维码规则配置")
                onDone(false)
            }
        }
    }

    private fun handleRuleMatchFailure(message: String) {
        AppLogger.log("ProcessRecordActivity", "[规则匹配] $message")
        currentProjectConfig = null
        currentProductType = null
        updateProjectNameDisplay(null)
        updateProductTypeDisplay(null)
        processStepsList.clear()
        processStepAdapter.notifyDataSetChanged()
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }

    private fun applyResolvedProjectAndProductType(
        targetProject: String,
        targetProductType: String,
        onDone: (Boolean) -> Unit
    ) {
        val normalizedProject = targetProject.trim()
        val normalizedProductType = targetProductType.trim()
        if (normalizedProject.isEmpty() || normalizedProductType.isEmpty()) {
            onDone(false)
            return
        }

        val currentProject = projectManager.getSelectedProcessProject() ?: projectManager.getSelectedProject()
        val shouldReloadProject =
            currentProjectConfig?.projectName != normalizedProject || currentProject != normalizedProject

        if (shouldReloadProject) {
            AppLogger.log(
                "ProcessRecordActivity",
                "自动匹配切换项目: ${currentProject ?: "<none>"} -> $normalizedProject, 产品类型: $normalizedProductType"
            )
            projectManager.setSelectedProcessProject(normalizedProject)
            projectManager.setSelectedProject(normalizedProject)
            updateProjectNameDisplay(normalizedProject)
            loadProjectConfiguration(preferredProductType = normalizedProductType) { loaded ->
                if (!loaded) {
                    onDone(false)
                    return@loadProjectConfiguration
                }
                onDone(currentProductType == normalizedProductType)
            }
            return
        }

        val typeIndex = productTypes.indexOf(normalizedProductType)
        if (typeIndex < 0) {
            loadProjectConfiguration(preferredProductType = normalizedProductType) { loaded ->
                onDone(loaded && currentProductType == normalizedProductType)
            }
            return
        }

        currentProductType = normalizedProductType
        suppressSpinnerProcessReloadOnce = true
        binding.spinnerProductType.setSelection(typeIndex, false)
        updateProductTypeDisplay(normalizedProductType)
        onDone(true)
    }

    private fun autoMatchProjectAndProductTypeForSerial(
        serialNumber: String,
        onDone: (Boolean) -> Unit
    ) {
        lifecycleScope.launch {
            val serverRuleMatches = resolveSerialRuleMatchesFromServer(serialNumber)
            if (serverRuleMatches.isNotEmpty()) {
                handleSerialRuleMatches(serialNumber, serverRuleMatches, onDone)
                return@launch
            }

            val localRuleMatches = projectConfigManager.resolveSerialRuleMatches(
                serialNumber = serialNumber,
                projectNames = getLocalRuleMatchCandidateProjects()
            )
            handleSerialRuleMatches(serialNumber, localRuleMatches, onDone)
        }
    }

    private data class StepPhotoPreview(
        val fileName: String,
        val bytes: ByteArray
    )

    private fun loadStepPhotoPreviewInto(
        processStep: ProcessStep,
        titleView: TextView,
        container: LinearLayout
    ) {
        titleView.text = "工序照片预览（加载中...）"
        container.removeAllViews()
        lifecycleScope.launch {
            try {
                val previews = withContext(Dispatchers.IO) {
                    loadStepPhotoPreviews(processStep, maxCount = 6)
                }
                if (previews.isEmpty()) {
                    titleView.text = "工序照片预览（0）"
                    val emptyText = TextView(this@ProcessRecordActivity).apply {
                        text = "当前工序暂无照片"
                        setTextColor(android.graphics.Color.parseColor("#777777"))
                    }
                    container.addView(emptyText)
                    return@launch
                }

                titleView.text = "工序照片预览（${previews.size}）"
                previews.forEach { preview ->
                    val card = LinearLayout(this@ProcessRecordActivity).apply {
                        orientation = LinearLayout.VERTICAL
                        val pad = (6 * resources.displayMetrics.density).toInt()
                        setPadding(pad, pad, pad, pad)
                        val lp = LinearLayout.LayoutParams(
                            (140 * resources.displayMetrics.density).toInt(),
                            LinearLayout.LayoutParams.WRAP_CONTENT
                        )
                        lp.marginEnd = (8 * resources.displayMetrics.density).toInt()
                        layoutParams = lp
                        background = android.graphics.drawable.GradientDrawable().apply {
                            cornerRadius = 12f
                            setColor(android.graphics.Color.parseColor("#F7F9FC"))
                            setStroke(1, android.graphics.Color.parseColor("#D7DEEA"))
                        }
                    }

                    val image = ImageView(this@ProcessRecordActivity).apply {
                        scaleType = ImageView.ScaleType.CENTER_CROP
                        layoutParams = LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT,
                            (96 * resources.displayMetrics.density).toInt()
                        )
                        setOnClickListener {
                            showStepPhotoFullPreview(preview)
                        }
                    }
                    Glide.with(this@ProcessRecordActivity)
                        .load(preview.bytes)
                        .into(image)

                    val nameText = TextView(this@ProcessRecordActivity).apply {
                        textSize = 11f
                        setTextColor(android.graphics.Color.parseColor("#4D5B73"))
                        setPadding(0, (6 * resources.displayMetrics.density).toInt(), 0, 0)
                        text = preview.fileName.take(24)
                    }

                    card.addView(image)
                    card.addView(nameText)
                    container.addView(card)
                }
            } catch (e: Exception) {
                AppLogger.log("ProcessRecordActivity", "加载工序预览失败: ${e.message}", e)
                titleView.text = "工序照片预览（加载失败）"
                val errorText = TextView(this@ProcessRecordActivity).apply {
                    text = "加载失败: ${e.message}"
                    setTextColor(android.graphics.Color.parseColor("#C62828"))
                }
                container.addView(errorText)
            }
        }
    }

    private suspend fun loadStepPhotoPreviews(
        processStep: ProcessStep,
        maxCount: Int
    ): List<StepPhotoPreview> {
        val serial = currentProductSerial ?: return emptyList()
        val projectName = projectManager.getSelectedProcessProject() ?: currentProjectConfig?.projectName ?: return emptyList()
        val productTypeName = currentProductType ?: return emptyList()
        val projectCode = currentProjectConfig?.projectCode ?: ""
        val modelNumber = currentProjectConfig?.getProductTypeConfig(productTypeName)?.modelNumber ?: ""
        val username = preferencesManager.getUsername() ?: ""
        val password = preferencesManager.getPassword() ?: ""
        val fileManager = FileManagerFactory.create(this, username, password)
        val directoryInfo = com.testcenter.qrscanner.network.FileManager.PhotoDirectoryInfo(
            projectName = projectName,
            projectCode = projectCode,
            productType = productTypeName,
            modelNumber = modelNumber,
            productSerial = serial
        )
        val normalizedStep = ProcessPhotoFileNameParser.normalizeForMatch(processStep.name)
        val targetPhotos = fileManager.listPhotos(directoryInfo)
            .asSequence()
            .filter { photo ->
                val parsed = ProcessPhotoFileNameParser.extractProcessName(serial, photo.fileName) ?: return@filter false
                ProcessPhotoFileNameParser.normalizeForMatch(parsed) == normalizedStep
            }
            .sortedByDescending { it.lastModified }
            .take(maxCount)
            .toList()
        if (targetPhotos.isEmpty()) {
            return emptyList()
        }
        return targetPhotos.mapNotNull { photo ->
            val bytes = fileManager.downloadPhoto(directoryInfo, photo.fileName)
            if (bytes == null || bytes.isEmpty()) {
                null
            } else {
                StepPhotoPreview(photo.fileName, bytes)
            }
        }
    }

    private fun showStepPhotoFullPreview(preview: StepPhotoPreview) {
        val dialog = Dialog(this, android.R.style.Theme_Black_NoTitleBar_Fullscreen)
        val root = FrameLayout(this).apply {
            setBackgroundColor(android.graphics.Color.BLACK)
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        }

        val image = ImageView(this).apply {
            adjustViewBounds = true
            scaleType = ImageView.ScaleType.FIT_CENTER
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
            setOnClickListener { dialog.dismiss() }
        }
        Glide.with(this)
            .load(preview.bytes)
            .fitCenter()
            .into(image)

        val closeHint = TextView(this).apply {
            text = "点击图片关闭"
            setTextColor(android.graphics.Color.WHITE)
            textSize = 13f
            setPadding(
                (16 * resources.displayMetrics.density).toInt(),
                (16 * resources.displayMetrics.density).toInt(),
                (16 * resources.displayMetrics.density).toInt(),
                (24 * resources.displayMetrics.density).toInt()
            )
            background = android.graphics.drawable.GradientDrawable().apply {
                setColor(android.graphics.Color.parseColor("#66000000"))
            }
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                gravity = android.view.Gravity.BOTTOM or android.view.Gravity.CENTER_HORIZONTAL
                bottomMargin = (24 * resources.displayMetrics.density).toInt()
            }
        }

        root.addView(image)
        root.addView(closeHint)
        dialog.setContentView(root)
        dialog.show()
    }

    private suspend fun loadStepPhotoBytesForQc(processStep: ProcessStep): List<ByteArray> {
        val serial = currentProductSerial ?: return emptyList()
        val projectName = projectManager.getSelectedProcessProject() ?: currentProjectConfig?.projectName ?: return emptyList()
        val productTypeName = currentProductType ?: return emptyList()
        val projectCode = currentProjectConfig?.projectCode ?: ""
        val modelNumber = currentProjectConfig?.getProductTypeConfig(productTypeName)?.modelNumber ?: ""
        val username = preferencesManager.getUsername() ?: ""
        val password = preferencesManager.getPassword() ?: ""
        val fileManager = FileManagerFactory.create(this, username, password)
        val directoryInfo = com.testcenter.qrscanner.network.FileManager.PhotoDirectoryInfo(
            projectName = projectName,
            projectCode = projectCode,
            productType = productTypeName,
            modelNumber = modelNumber,
            productSerial = serial
        )
        val normalizedStep = ProcessPhotoFileNameParser.normalizeForMatch(processStep.name)
        val targetPhotos = fileManager.listPhotos(directoryInfo)
            .asSequence()
            .filter { photo ->
                val parsed = ProcessPhotoFileNameParser.extractProcessName(serial, photo.fileName) ?: return@filter false
                ProcessPhotoFileNameParser.normalizeForMatch(parsed) == normalizedStep
            }
            .sortedByDescending { it.lastModified }
            .take(6)
            .toList()
        if (targetPhotos.isEmpty()) {
            return emptyList()
        }
        val photoBytes = mutableListOf<ByteArray>()
        for (photo in targetPhotos) {
            val bytes = fileManager.downloadPhoto(directoryInfo, photo.fileName)
            if (bytes != null && bytes.isNotEmpty()) {
                photoBytes.add(bytes)
            }
        }
        return photoBytes
    }

    private fun submitManualQcConfirmation(
        processStep: ProcessStep,
        humanStatus: String,
        humanSummary: String,
        onDone: (Boolean, String) -> Unit
    ) {
        val serial = currentProductSerial
        val projectName = projectManager.getSelectedProcessProject() ?: currentProjectConfig?.projectName
        if (serial.isNullOrBlank() || projectName.isNullOrBlank()) {
            onDone(false, "缺少项目或序列号信息")
            return
        }
        lifecycleScope.launch {
            val result = qcService.submitManualConfirmation(
                productSerial = serial,
                projectName = projectName,
                processName = processStep.name,
                humanStatus = humanStatus,
                humanSummary = humanSummary
            )
            onDone(result.success, result.message)
        }
    }

    /**
     * 查看工序照片 — 跳转到照片记录页面
     */
    private fun viewProcessPhotos(processStep: ProcessStep) {
        val serial = currentProductSerial ?: return
        val projectName = projectManager.getSelectedProcessProject() ?: currentProjectConfig?.projectName ?: return
        val productType = currentProductType ?: ""
        val projectCode = currentProjectConfig?.projectCode ?: ""
        val modelNumber = currentProjectConfig?.getProductTypeConfig(productType)?.modelNumber ?: ""
        AppLogger.log("ProcessRecordActivity", "查看工序照片: step=${processStep.name}, serial=$serial")

        val intent = Intent(this, PhotoRecordsActivity::class.java).apply {
            putExtra(PhotoRecordsActivity.EXTRA_PRODUCT_SERIAL, serial)
            putExtra(PhotoRecordsActivity.EXTRA_PROJECT_NAME, projectName)
            putExtra(PhotoRecordsActivity.EXTRA_PROJECT_CODE, projectCode)
            putExtra(PhotoRecordsActivity.EXTRA_PRODUCT_TYPE, productType)
            putExtra(PhotoRecordsActivity.EXTRA_MODEL_NUMBER, modelNumber)
            putExtra(PhotoRecordsActivity.EXTRA_PROCESS_STEP_NAME, processStep.name)
        }
        startActivity(intent)
    }

    /**
     * 查看工序文档 — 打开文档列表
     */
    private fun viewProcessDocuments(processStep: ProcessStep) {
        val serial = currentProductSerial ?: return
        val projectName = projectManager.getSelectedProcessProject() ?: currentProjectConfig?.projectName ?: return
        val productType = currentProductType ?: ""

        lifecycleScope.launch {
            try {
                val apiService = ApiClient.getApiService(this@ProcessRecordActivity)
                val response = apiService.listDocuments(
                    projectName = projectName,
                    productType = productType,
                    productSerial = serial,
                    processName = processStep.name
                )
                if (response.isSuccessful) {
                    val docs = response.body()?.documents ?: emptyList()

                    if (docs.isEmpty()) {
                        Toast.makeText(this@ProcessRecordActivity, "未找到该工序的文档", Toast.LENGTH_SHORT).show()
                        return@launch
                    }

                    // 如果只有一个 PDF，直接打开
                    if (docs.size == 1) {
                        openPdfDocument(docs[0].path ?: docs[0].filename)
                        return@launch
                    }

                    // 多个 PDF，弹出选择列表
                    val names = docs.map { it.filename }.toTypedArray()
                    val paths = docs.map { it.path ?: it.filename }
                    AlertDialog.Builder(this@ProcessRecordActivity)
                        .setTitle("选择文档（${docs.size}个）")
                        .setItems(names) { _, which ->
                            openPdfDocument(paths[which])
                        }
                        .setNegativeButton("取消", null)
                        .show()
                } else {
                    Toast.makeText(this@ProcessRecordActivity, "获取文档列表失败", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                AppLogger.log("ProcessRecordActivity", "获取文档列表异常: ${e.message}")
                Toast.makeText(this@ProcessRecordActivity, "获取文档列表失败: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    /**
     * 下载并打开 PDF 文档
     */
    private fun openPdfDocument(filename: String) {
        lifecycleScope.launch {
            try {
                showUploadProgress("正在下载文档...")
                val apiService = ApiClient.getApiService(this@ProcessRecordActivity)
                val response = apiService.downloadDocument(filename)
                if (response.isSuccessful) {
                    val body = response.body() ?: run {
                        hideUploadProgress()
                        Toast.makeText(this@ProcessRecordActivity, "下载失败：空响应", Toast.LENGTH_SHORT).show()
                        return@launch
                    }
                    // 保存到临时文件
                    val tempFile = java.io.File(cacheDir, filename)
                    tempFile.outputStream().use { out ->
                        body.byteStream().use { input -> input.copyTo(out) }
                    }
                    hideUploadProgress()

                    // 用系统 PDF 查看器打开
                    val uri = FileProvider.getUriForFile(this@ProcessRecordActivity,
                        "${packageName}.fileprovider", tempFile)
                    val intent = Intent(Intent.ACTION_VIEW).apply {
                        setDataAndType(uri, "application/pdf")
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }
                    try {
                        startActivity(intent)
                    } catch (e: ActivityNotFoundException) {
                        Toast.makeText(this@ProcessRecordActivity, "未安装 PDF 查看器", Toast.LENGTH_SHORT).show()
                    }
                } else {
                    hideUploadProgress()
                    Toast.makeText(this@ProcessRecordActivity, "下载失败: ${response.message()}", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                hideUploadProgress()
                AppLogger.log("ProcessRecordActivity", "下载文档异常: ${e.message}")
                Toast.makeText(this@ProcessRecordActivity, "下载失败: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        projectManager.refreshProjectListCacheInBackground(force = true)

        // Log operator name (operator UI removed - using login user automatically)
        val currentUser = localUserManager.getCurrentUser()
        val operatorName = getCurrentOperatorName()
        AppLogger.log("ProcessRecordActivity", "onResume - Operator: $operatorName (User ID: ${currentUser?.id}, Source: ${if (currentUser != null) "LocalUserManager" else "PreferencesManager"})")

        if (System.currentTimeMillis() - lastPhotoCaptureResultAt < SKIP_ON_RESUME_AFTER_CAPTURE_MS) {
            AppLogger.log("ProcessRecordActivity", "[刷新] 跳过 onResume 立即刷新，避免拍照返回后重复请求")
            return
        }

        // 从拍照返回后，刷新工序 QC 状态
        refreshQcStatus(reason = "onResume")
    }

    private fun queueRefreshAfterCurrent(refreshKey: String, reason: String, force: Boolean) {
        pendingRefreshKey = refreshKey
        pendingRefreshReason = reason
        pendingRefreshForce = pendingRefreshForce || force
    }

    private fun scheduleDeferredRefresh(refreshKey: String, delayMs: Long) {
        if (delayMs <= 0L) {
            val reason = pendingRefreshReason ?: "deferred_refresh"
            pendingRefreshKey = null
            pendingRefreshReason = null
            pendingRefreshForce = false
            refreshQcStatus(reason = reason, force = true)
            return
        }

        if (deferredRefreshJob?.isActive == true && pendingRefreshKey == refreshKey) {
            return
        }

        deferredRefreshJob?.cancel()
        deferredRefreshJob = lifecycleScope.launch {
            delay(delayMs)
            if (pendingRefreshKey != refreshKey || refreshQcStatusJob?.isActive == true) {
                return@launch
            }
            val reason = pendingRefreshReason ?: "deferred_refresh"
            pendingRefreshKey = null
            pendingRefreshReason = null
            pendingRefreshForce = false
            refreshQcStatus(reason = reason, force = true)
        }
    }

    /**
     * 刷新所有工序的状态（照片 + 文档 + 历史 QC 报告）
     */
    private fun refreshQcStatus(reason: String = "manual", force: Boolean = false) {
        val serial = currentProductSerial ?: return
        val projectName = projectManager.getSelectedProcessProject() ?: currentProjectConfig?.projectName ?: return
        val productTypeName = currentProductType ?: return

        if (processStepsList.isEmpty()) {
            return
        }

        val refreshKey = listOf(serial, projectName, productTypeName).joinToString("|")
        val now = System.currentTimeMillis()
        if (!force) {
            if (refreshQcStatusJob?.isActive == true && refreshQcStatusKey == refreshKey) {
                AppLogger.log("ProcessRecordActivity", "[刷新] 跳过重复刷新: reason=$reason serial=$serial productType=$productTypeName")
                queueRefreshAfterCurrent(refreshKey, reason, force)
                return
            }
            if (refreshQcStatusKey == refreshKey && now - refreshQcStatusStartedAt < REFRESH_QC_STATUS_COOLDOWN_MS) {
                AppLogger.log("ProcessRecordActivity", "[刷新] 命中短冷却，跳过: reason=$reason serial=$serial productType=$productTypeName")
                queueRefreshAfterCurrent(refreshKey, reason, force)
                scheduleDeferredRefresh(
                    refreshKey = refreshKey,
                    delayMs = REFRESH_QC_STATUS_COOLDOWN_MS - (now - refreshQcStatusStartedAt)
                )
                return
            }
        }

        if (qcStatusBoundSerial != serial) {
            processStepAdapter.clearQcStatus()
            qcStatusBoundSerial = serial
            AppLogger.log("ProcessRecordActivity", "[刷新] 绑定新序列号，清空缓存状态: $serial")
        }

        val projectCode = currentProjectConfig?.projectCode ?: ""
        val modelNumber = currentProjectConfig?.getProductTypeConfig(productTypeName)?.modelNumber ?: ""

        AppLogger.log("ProcessRecordActivity", "[刷新] 开始远端刷新: reason=$reason serial=$serial productType=$productTypeName")
        refreshQcStatusKey = refreshKey
        refreshQcStatusStartedAt = now
        if (pendingRefreshKey == refreshKey) {
            pendingRefreshKey = null
            pendingRefreshReason = null
            pendingRefreshForce = false
        }
        refreshQcStatusJob = lifecycleScope.launch {
            // 并行：NAS 查照片 + API 查照片记录 + 后端查文档 + 后端查历史 QC 报告
            val nasPhotoJob = async(Dispatchers.IO) {
                try {
                    val username = preferencesManager.getUsername() ?: ""
                    val password = preferencesManager.getPassword() ?: ""
                    val fileManager = com.testcenter.qrscanner.network.FileManagerFactory.create(
                        this@ProcessRecordActivity, username, password
                    )
                    val dirInfo = com.testcenter.qrscanner.network.FileManager.PhotoDirectoryInfo(
                        projectName = projectName,
                        projectCode = projectCode,
                        productType = productTypeName,
                        modelNumber = modelNumber,
                        productSerial = serial
                    )
                    fileManager.listPhotos(dirInfo)
                } catch (e: Exception) {
                    AppLogger.log("ProcessRectivity", "[PHOTO] WebDAV 查询照片失败: ${e.message}")
                    emptyList()
                }
            }

            val apiPhotoJob = async(Dispatchers.IO) {
                photoRepository.listPhotos(
                    projectName = projectName,
                    productType = productTypeName,
                    productSerial = serial
                ).getOrElse { e ->
                    AppLogger.log("ProcessRecordActivity", "[PHOTO] API 查询照片失败: ${e.message}")
                    emptyList()
                }
            }

            val docJob = async(Dispatchers.IO) {
                try {
                    val apiService = ApiClient.getApiService(this@ProcessRecordActivity)
                    val resp = apiService.listDocuments(projectName, productTypeName, serial)
                    if (resp.isSuccessful) resp.body()?.documents ?: emptyList() else emptyList()
                } catch (e: Exception) {
                    AppLogger.log("ProcessRecordActivity", "[DOC] 获取文档列表失败: ${e.message}")
                    emptyList()
                }
            }

            val reportJob = async(Dispatchers.IO) {
                try {
                    val apiService = ApiClient.getApiService(this@ProcessRecordActivity)
                    val response = apiService.getInspectionReport(
                        serial = serial,
                        projectName = projectName,
                        productType = productTypeName
                    )
                    if (response.isSuccessful && response.body()?.success == true) {
                        response.body()?.results ?: emptyList()
                    } else {
                        emptyList()
                    }
                } catch (e: Exception) {
                    AppLogger.log("ProcessRecordActivity", "[QC] 获取历史报告失败: ${e.message}")
                    emptyList()
                }
            }

            val nasPhotos = nasPhotoJob.await()
            val apiPhotos = apiPhotoJob.await()
            val docs = docJob.await()
            val reportResults = reportJob.await()
            val mergedPhotoFiles = mergePhotoFileNames(nasPhotos, apiPhotos)

            AppLogger.log(
                "ProcessRecordActivity",
                "[刷新] 照片源: nas=${nasPhotos.size}, api=${apiPhotos.size}, merged=${mergedPhotoFiles.size}"
            )

            // 先建立“规范化工序名 -> 配置工序名”映射，兼容标点/下划线差异
            val stepNameByNormalized = processStepsList.associateBy(
                keySelector = { ProcessPhotoFileNameParser.normalizeForMatch(it.name) },
                valueTransform = { it.name }
            )

            // 按工序名统计照片数量（兼容两种文件名）
            val photoCountByProcess = mutableMapOf<String, Int>()
            for (fileName in mergedPhotoFiles) {
                val parsed = ProcessPhotoFileNameParser.extractProcessName(serial, fileName) ?: continue
                val normalized = ProcessPhotoFileNameParser.normalizeForMatch(parsed)
                val canonicalName = stepNameByNormalized[normalized]
                if (canonicalName != null) {
                    photoCountByProcess[canonicalName] = (photoCountByProcess[canonicalName] ?: 0) + 1
                } else {
                    // 兜底：无法映射到配置工序时仍保留统计，便于日志排查
                    AppLogger.log("ProcessRecordActivity", "[刷新] 照片工序未命中配置: parsed=$parsed, file=$fileName")
                    photoCountByProcess[parsed] = (photoCountByProcess[parsed] ?: 0) + 1
                }
            }

            // 按工序名统计文档数量
            val docCountByProcess = docs.groupBy { doc -> doc.processName ?: "" }
                .mapValues { entry -> entry.value.size }

            // 按工序名建立历史 QC 报告索引
            val reportByProcess = reportResults.associateBy {
                ProcessPhotoFileNameParser.normalizeForMatch(it.process)
            }

            AppLogger.log(
                "ProcessRecordActivity",
                "[刷新] 照片: ${mergedPhotoFiles.size}张 (${photoCountByProcess.size}个工序), 文档: ${docs.size}个, 报告工序: ${reportResults.size}个"
            )

            // 更新每个工序的状态（无论是否拍照，均刷新一遍，避免旧状态残留）
            for (step in processStepsList) {
                val normalizedStepName = ProcessPhotoFileNameParser.normalizeForMatch(step.name)
                val reportResult = reportByProcess[normalizedStepName]
                val pCount = photoCountByProcess[step.name] ?: 0
                val dCount = docCountByProcess[step.name] ?: 0
                val existing = processStepAdapter.getQcStatusForStep(step.id)
                // 仅使用当前序列号当次刷新得到的数据，避免历史缓存串到新序列号
                val mergedPhotoCount = maxOf(
                    pCount,
                    reportResult?.photoCount ?: 0
                )
                val mergedHasPhoto = mergedPhotoCount > 0 || reportResult?.hasPhoto == true
                val reportAiFindings = reportResult?.aiDefects?.let { mapDefectsToFindings(it) } ?: emptyList()
                val reportHumanFindings = reportResult?.humanDefects?.let { mapDefectsToFindings(it) } ?: emptyList()
                val reportEffectiveFindings = reportResult?.defects?.let { mapDefectsToFindings(it) } ?: emptyList()
                val canReuseExistingQc = mergedHasPhoto

                val mergedAiStatus = reportResult?.aiStatus ?: existing?.aiStatus
                val mergedAiSummary = reportResult?.aiSummary?.takeIf { it.isNotBlank() } ?: existing?.aiSummary
                val mergedAiFindings = if (reportAiFindings.isNotEmpty()) reportAiFindings else existing?.aiFindings ?: emptyList()

                val mergedHumanStatus = reportResult?.humanStatus ?: existing?.humanStatus
                val mergedHumanSummary = reportResult?.humanSummary?.takeIf { it.isNotBlank() } ?: existing?.humanSummary
                val mergedHumanFindings = if (reportHumanFindings.isNotEmpty()) reportHumanFindings else existing?.humanFindings ?: emptyList()

                val mergedQcStatus = reportResult?.effectiveStatus
                    ?: reportResult?.status
                    ?: if (canReuseExistingQc) existing?.qcStatus else null
                val mergedQcSummary = (reportResult?.effectiveSummary?.takeIf { it.isNotBlank() }
                    ?: reportResult?.summary?.takeIf { it.isNotBlank() }
                    ?: if (canReuseExistingQc) existing?.qcSummary else null)
                val mergedFindings = if (reportEffectiveFindings.isNotEmpty()) {
                    reportEffectiveFindings
                } else {
                    if (canReuseExistingQc) existing?.findings ?: emptyList() else emptyList()
                }

                processStepAdapter.updateQcStatusFull(
                    step.id,
                    hasPhoto = mergedHasPhoto,
                    photoCount = mergedPhotoCount,
                    qcStatus = mergedQcStatus,
                    qcSummary = mergedQcSummary,
                    findings = mergedFindings,
                    pdfCount = dCount,
                    aiStatus = mergedAiStatus,
                    aiSummary = mergedAiSummary,
                    aiFindings = mergedAiFindings,
                    humanStatus = mergedHumanStatus,
                    humanSummary = mergedHumanSummary,
                    humanFindings = mergedHumanFindings
                )
            }
        }.also { job ->
            job.invokeOnCompletion {
                if (refreshQcStatusJob == job) {
                    refreshQcStatusJob = null
                }
                if (pendingRefreshKey == refreshKey) {
                    val pendingReason = pendingRefreshReason ?: "queued_refresh"
                    pendingRefreshKey = null
                    pendingRefreshReason = null
                    pendingRefreshForce = false
                    lifecycleScope.launch {
                        refreshQcStatus(reason = pendingReason, force = true)
                    }
                }
            }
        }
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
            preferencesManager.getUsername() ?: "未知"
        }
    }

    private fun loadProcessStepsForProduct(productSerial: String): Boolean {
        AppLogger.log("ProcessRecordActivity", "Loading process steps for product: $productSerial")

        // Check if product type is selected
        if (currentProductType == null) {
            AppLogger.log("ProcessRecordActivity", "No product type selected")
            Toast.makeText(this, "请先选择产品类型", Toast.LENGTH_SHORT).show()
            return false
        }
        
        AppLogger.log("ProcessRecordActivity", "Current product type: $currentProductType")
        AppLogger.log("ProcessRecordActivity", "Schema version: ${currentProjectConfig?.schemaVersion}")
        
        // Always use 2.0 structure: get process steps from product type
        val productTypeConfig = currentProjectConfig?.getProductTypeConfig(currentProductType!!)
        if (productTypeConfig == null) {
            AppLogger.log("ProcessRecordActivity", "Product type not found: $currentProductType")
            Toast.makeText(this, "产品类型配置未找到: $currentProductType", Toast.LENGTH_SHORT).show()
            return false
        }
        
        AppLogger.log("ProcessRecordActivity", "Loading process steps from product type: ${productTypeConfig.typeName}")
        val processSteps = productTypeConfig.safeGetProcessSteps()
        val visibleProcessSteps = filterProcessStepsByResponsibility(processSteps)
        AppLogger.log(
            "ProcessRecordActivity",
            "Found ${processSteps.size} process steps, visible ${visibleProcessSteps.size} for product type: $currentProductType"
        )

        if (processSteps.isEmpty()) {
            AppLogger.log("ProcessRecordActivity", "No process steps configured for product type: $currentProductType")
            Toast.makeText(this, "当前产品类型未配置工序步骤", Toast.LENGTH_SHORT).show()
            return false
        }

        if (visibleProcessSteps.isEmpty()) {
            AppLogger.log("ProcessRecordActivity", "No visible process steps for current user groups")
            Toast.makeText(this, "当前账号暂无负责工序，请联系管理员配置责任部门", Toast.LENGTH_SHORT).show()
            processStepsList.clear()
            processStepAdapter.notifyDataSetChanged()
            return false
        }
        
        // Update the process steps list and notify adapter
        processStepsList.clear()
        processStepsList.addAll(visibleProcessSteps.sortedBy { it.order })
        processStepAdapter.notifyDataSetChanged()
        
        AppLogger.log("ProcessRecordActivity", "Loaded ${processStepsList.size} process steps for product $productSerial (type: $currentProductType)")
        
        // Show process steps section
        if (processStepsList.isNotEmpty()) {
            Toast.makeText(this, "已加载 ${processStepsList.size} 个工序步骤", Toast.LENGTH_SHORT).show()
            // 加载完工序后立即刷新照片/QC 状态
            refreshQcStatus(reason = "load_process_steps")
        }
        return true
    }

    private fun mergePhotoFileNames(
        nasPhotos: List<com.testcenter.qrscanner.network.FileManager.PhotoInfo>,
        apiPhotos: List<com.testcenter.qrscanner.api.PhotoInfo>
    ): List<String> {
        val merged = LinkedHashMap<String, String>()

        fun putFileName(fileName: String?, filePath: String?) {
            val normalizedName = fileName?.trim().orEmpty()
            if (normalizedName.isBlank()) return
            val key = buildPhotoIdentity(normalizedName, filePath)
            merged.putIfAbsent(key, normalizedName)
        }

        nasPhotos.forEach { putFileName(it.fileName, it.filePath) }
        apiPhotos.forEach { putFileName(it.fileName, it.filePath) }

        return merged.values.toList()
    }

    private fun buildPhotoIdentity(fileName: String, filePath: String?): String {
        return (fileName.ifBlank { filePath ?: "" }).trim().lowercase()
    }

    private fun showProcessProjectSelectionDialog() {
        AppLogger.log("ProcessRecordActivity", "[项目选择] 开始显示项目选择对话框")
        
        val projects = projectManager.getProjectList()
        AppLogger.log("ProcessRecordActivity", "[项目选择] 获取到 ${projects.size} 个项目")
        
        if (projects.isEmpty()) {
            AppLogger.log("ProcessRecordActivity", "[项目选择] 没有可用项目，显示提示")
            Toast.makeText(this, "没有可用的项目，请先同步或添加项目", Toast.LENGTH_SHORT).show()
            return
        }

        val currentSelection = projectManager.getSelectedProcessProject()
        val selectedIndex = currentSelection?.let { projects.indexOf(it) }?.takeIf { it >= 0 } ?: -1
        AppLogger.log("ProcessRecordActivity", "[项目选择] 当前选中项目: $currentSelection, 索引: $selectedIndex")
        
        projects.forEachIndexed { index, project ->
            AppLogger.log("ProcessRecordActivity", "[项目选择] 项目[$index]: $project")
        }

        AlertDialog.Builder(this)
            .setTitle("选择工序项目")
            .setSingleChoiceItems(projects.toTypedArray(), selectedIndex) { dialog, which ->
                val newProject = projects[which]
                AppLogger.log("ProcessRecordActivity", "[项目选择] 用户选择了项目: $newProject (索引: $which)")
                
                projectManager.setSelectedProcessProject(newProject)
                updateProjectNameDisplay(newProject)
                qcService.clearCache()
                currentProductSerial = null
                binding.tvProductSerial.text = "未扫描"
                binding.productInfoLayout.visibility = View.GONE
                processStepsList.clear()
                processStepAdapter.notifyDataSetChanged()
                loadProjectConfiguration()
                
                AppLogger.log("ProcessRecordActivity", "[项目选择] 项目切换完成，对话框关闭")
                dialog.dismiss()
            }
            .setNegativeButton("取消") { dialog, _ ->
                AppLogger.log("ProcessRecordActivity", "[项目选择] 用户取消选择")
                dialog.dismiss()
            }
            .show()
        
        AppLogger.log("ProcessRecordActivity", "[项目选择] 对话框已显示")
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
