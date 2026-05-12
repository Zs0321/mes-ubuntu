package com.testcenter.qrscanner

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.inputmethod.EditorInfo
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanIntentResult
import com.testcenter.qrscanner.adapter.InspectionStepAdapter
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.databinding.ActivityInspectionReportBinding
import com.testcenter.qrscanner.qc.QcInspectionReportResponse
import com.testcenter.qrscanner.scanner.EnhancedQRScanner
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.SerialNormalizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class InspectionReportActivity : AppCompatActivity() {

    private lateinit var binding: ActivityInspectionReportBinding
    private lateinit var enhancedQRScanner: EnhancedQRScanner
    private lateinit var stepAdapter: InspectionStepAdapter
    private val apiService by lazy { ApiClient.getApiService(this) }

    private val barcodeLauncher = registerForActivityResult(ScanContract()) { result: ScanIntentResult ->
        if (result.contents != null) {
            val serial = SerialNormalizer.normalize(result.contents)
            binding.etSerialNumber.setText(serial)
            loadReport(serial)
        }
    }

    private val requestCameraLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startQRScanner()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        androidx.appcompat.app.AppCompatDelegate.setDefaultNightMode(
            androidx.appcompat.app.AppCompatDelegate.MODE_NIGHT_NO
        )

        binding = ActivityInspectionReportBinding.inflate(layoutInflater)
        setContentView(binding.root)

        enhancedQRScanner = EnhancedQRScanner(this)

        setupToolbar()
        setupUI()

        // 如果从外部传入了序列号，直接查询
        intent.getStringExtra(EXTRA_SERIAL_NUMBER)?.let { serial ->
            val normalized = SerialNormalizer.normalize(serial)
            if (normalized.isNotEmpty()) {
                binding.etSerialNumber.setText(normalized)
                loadReport(normalized)
            }
        }
    }

    private fun setupToolbar() {
        setSupportActionBar(binding.toolbar)
        supportActionBar?.apply {
            title = "电机检验报告"
            setDisplayHomeAsUpEnabled(true)
        }
        binding.toolbar.setNavigationOnClickListener { finish() }
    }

    private fun setupUI() {
        // 工序列表
        stepAdapter = InspectionStepAdapter()
        binding.recyclerViewSteps.apply {
            layoutManager = LinearLayoutManager(this@InspectionReportActivity)
            adapter = stepAdapter
        }

        // 扫码按钮
        binding.btnScan.setOnClickListener {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                == PackageManager.PERMISSION_GRANTED) {
                startQRScanner()
            } else {
                requestCameraLauncher.launch(Manifest.permission.CAMERA)
            }
        }

        // 查询按钮
        binding.btnSearch.setOnClickListener {
            val serial = SerialNormalizer.normalize(binding.etSerialNumber.text?.toString())
            if (serial.isNullOrEmpty()) {
                Toast.makeText(this, "请输入序列号", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            loadReport(serial)
        }

        // 键盘搜索键
        binding.etSerialNumber.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                val serial = SerialNormalizer.normalize(binding.etSerialNumber.text?.toString())
                if (!serial.isNullOrEmpty()) {
                    loadReport(serial)
                }
                true
            } else false
        }
    }

    private fun startQRScanner() {
        val options = enhancedQRScanner.createEnhancedScanOptions("扫描产品序列号")
        barcodeLauncher.launch(options)
    }

    private fun loadReport(serialNumber: String) {
        val normalizedSerial = SerialNormalizer.normalize(serialNumber)
        if (normalizedSerial.isEmpty()) {
            showError("请输入有效序列号")
            return
        }
        AppLogger.log(TAG, "加载检验报告: $normalizedSerial")

        // 隐藏键盘
        currentFocus?.let {
            val imm = getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
            imm.hideSoftInputFromWindow(it.windowToken, 0)
        }

        showLoading()

        lifecycleScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    apiService.getInspectionReport(normalizedSerial)
                }

                if (response.isSuccessful) {
                    val report = response.body()
                    if (report != null && report.success) {
                        showReport(report)
                    } else {
                        showError(report?.error ?: "未找到该序列号的检验报告")
                    }
                } else {
                    showError("请求失败 (${response.code()})")
                }
            } catch (e: Exception) {
                AppLogger.log(TAG, "加载报告异常: ${e.message}", e)
                showError("网络连接失败: ${e.message}")
            }
        }
    }

    private fun showLoading() {
        binding.loadingSection.visibility = View.VISIBLE
        binding.tvEmptyMessage.visibility = View.GONE
        binding.reportContent.visibility = View.GONE
    }

    private fun showError(message: String) {
        binding.loadingSection.visibility = View.GONE
        binding.reportContent.visibility = View.GONE
        binding.tvEmptyMessage.visibility = View.VISIBLE
        binding.tvEmptyMessage.text = message
    }

    private fun showReport(report: QcInspectionReportResponse) {
        binding.loadingSection.visibility = View.GONE
        binding.tvEmptyMessage.visibility = View.GONE
        binding.reportContent.visibility = View.VISIBLE

        // 序列号
        binding.tvReportSerial.text = report.serialNumber

        // 项目信息
        binding.tvReportProject.text = "项目：${report.projectName.ifEmpty { "未知" }}"
        binding.tvReportProductType.text = "产品类型：${report.productType.ifEmpty { "未知" }}"

        // 总体状态
        applyStatusStyle(binding.tvOverallStatus, report.overallStatus)

        // 统计数字：分别计算各状态
        val passCount = report.results.count { it.status == "pass" }
        val failCount = report.results.count { it.status == "fail" }
        val ngCount = report.results.count { it.status == "ng" }
        val missingCount = report.missingProcesses.size + report.results.count { it.status == null && !it.hasPhoto }
        val pendingCount = ngCount + missingCount

        binding.tvTotalProcesses.text = report.totalProcesses.toString()
        binding.tvPassedCount.text = passCount.toString()
        binding.tvFailedCount.text = failCount.toString()
        binding.tvMissingCount.text = pendingCount.toString()

        // 工序详情列表
        val stepItems = report.results.map { result ->
            InspectionStepAdapter.StepItem(
                processName = result.process,
                order = result.order,
                hasPhoto = result.hasPhoto,
                photoCount = result.photoCount,
                qcStatus = result.status,
                summary = result.summary,
                defects = result.defects.map { defect ->
                    val severityLabel = when (defect.severity) {
                        "critical" -> "[严重]"
                        "major" -> "[主要]"
                        else -> "[轻微]"
                    }
                    "$severityLabel ${defect.description}"
                }
            )
        }
        stepAdapter.updateData(stepItems)
    }

    private fun applyStatusStyle(textView: android.widget.TextView, status: String) {
        val bg = GradientDrawable().apply { cornerRadius = 12f }
        when (status) {
            "pass" -> {
                textView.text = "通过"
                textView.setTextColor(Color.WHITE)
                bg.setColor(Color.parseColor("#4CAF50"))
            }
            "fail" -> {
                textView.text = "未通过"
                textView.setTextColor(Color.WHITE)
                bg.setColor(Color.parseColor("#F44336"))
            }
            "ng" -> {
                textView.text = "待复核"
                textView.setTextColor(Color.WHITE)
                bg.setColor(Color.parseColor("#FF9800"))
            }
            else -> {
                textView.text = "未知"
                textView.setTextColor(Color.parseColor("#666666"))
                bg.setColor(Color.parseColor("#E0E0E0"))
            }
        }
        textView.background = bg
    }

    companion object {
        private const val TAG = "InspectionReport"
        const val EXTRA_SERIAL_NUMBER = "extra_serial_number"
    }
}
