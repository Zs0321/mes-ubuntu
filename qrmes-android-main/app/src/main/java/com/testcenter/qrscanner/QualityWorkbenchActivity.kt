package com.testcenter.qrscanner

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanIntentResult
import com.testcenter.qrscanner.adapter.QualityProcessStepAdapter
import com.testcenter.qrscanner.api.ApiClient
import com.testcenter.qrscanner.databinding.ActivityQualityWorkbenchBinding
import com.testcenter.qrscanner.quality.QualityCheckDto
import com.testcenter.qrscanner.quality.QualityProcessResultDto
import com.testcenter.qrscanner.quality.QualityReportStatusDto
import com.testcenter.qrscanner.quality.QualityShipmentStatsResponse
import com.testcenter.qrscanner.quality.QualityWorkbenchResponse
import com.testcenter.qrscanner.scanner.EnhancedQRScanner
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.SerialNormalizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class QualityWorkbenchActivity : AppCompatActivity() {

    private enum class WorkbenchPage {
        SERIAL,
        STATS
    }

    private lateinit var binding: ActivityQualityWorkbenchBinding
    private lateinit var enhancedQrScanner: EnhancedQRScanner
    private lateinit var processAdapter: QualityProcessStepAdapter
    private val apiService by lazy { ApiClient.getApiService(this) }
    private var currentSerialNumber: String = ""
    private var activeRequestId: Int = 0
    private var latestRequestedSerial: String = ""
    private var currentPage: WorkbenchPage = WorkbenchPage.SERIAL

    private val barcodeLauncher = registerForActivityResult(ScanContract()) { result: ScanIntentResult ->
        val serial = SerialNormalizer.normalize(result.contents)
        if (serial.isEmpty()) {
            Toast.makeText(this, "未识别到有效序列号", Toast.LENGTH_SHORT).show()
            return@registerForActivityResult
        }
        binding.etSerialNumber.setText(serial)
        showSerialPage()
        submitSerialQuery()
    }

    private val requestCameraLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            startQrScanner()
        } else {
            Toast.makeText(this, "需要相机权限才能扫码", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityQualityWorkbenchBinding.inflate(layoutInflater)
        setContentView(binding.root)

        enhancedQrScanner = EnhancedQRScanner(this)

        setupToolbar()
        setupUi()
        setupProcessList()
        loadShipmentStats()
        prefillSerialNumber()?.let { serial ->
            loadQualityWorkbench(serial)
        }
    }

    private fun setupToolbar() {
        setSupportActionBar(binding.toolbar)
        supportActionBar?.apply {
            title = SCREEN_TITLE
            setDisplayHomeAsUpEnabled(true)
        }
        binding.toolbar.setNavigationOnClickListener {
            onBackPressedDispatcher.onBackPressed()
        }
    }

    private fun setupUi() {
        showEmptyState()
        binding.btnScan.isEnabled = true
        binding.btnSearch.isEnabled = true
        setupPageSwitcher()

        binding.btnScan.setOnClickListener {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                == PackageManager.PERMISSION_GRANTED
            ) {
                startQrScanner()
            } else {
                requestCameraLauncher.launch(Manifest.permission.CAMERA)
            }
        }

        binding.btnSearch.setOnClickListener {
            showSerialPage()
            submitSerialQuery()
        }

        binding.etSerialNumber.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                showSerialPage()
                submitSerialQuery()
                true
            } else {
                false
            }
        }
    }

    private fun setupPageSwitcher() {
        binding.btnSerialPage.setOnClickListener { showSerialPage() }
        binding.btnStatsPage.setOnClickListener { showStatsPage() }
        showSerialPage()
    }

    private fun showSerialPage() {
        currentPage = WorkbenchPage.SERIAL
        binding.serialPageContainer.visibility = View.VISIBLE
        binding.statsPageContainer.visibility = View.GONE
        binding.btnSerialPage.backgroundTintList = ContextCompat.getColorStateList(this, R.color.md_primary)
        binding.btnSerialPage.setTextColor(ContextCompat.getColor(this, R.color.md_onSecondary))
        binding.btnStatsPage.backgroundTintList = ContextCompat.getColorStateList(this, R.color.md_surface)
        binding.btnStatsPage.setTextColor(ContextCompat.getColor(this, R.color.md_primary))
    }

    private fun showStatsPage() {
        currentPage = WorkbenchPage.STATS
        binding.serialPageContainer.visibility = View.GONE
        binding.statsPageContainer.visibility = View.VISIBLE
        binding.btnStatsPage.backgroundTintList = ContextCompat.getColorStateList(this, R.color.md_primary)
        binding.btnStatsPage.setTextColor(ContextCompat.getColor(this, R.color.md_onSecondary))
        binding.btnSerialPage.backgroundTintList = ContextCompat.getColorStateList(this, R.color.md_surface)
        binding.btnSerialPage.setTextColor(ContextCompat.getColor(this, R.color.md_primary))
    }

    private fun setupProcessList() {
        processAdapter = QualityProcessStepAdapter { item ->
            if (item.process.isBlank()) {
                return@QualityProcessStepAdapter
            }
            openProcessDetail(item)
        }
        binding.recyclerViewProcessSteps.apply {
            layoutManager = LinearLayoutManager(this@QualityWorkbenchActivity)
            adapter = processAdapter
            isNestedScrollingEnabled = false
        }
    }

    private fun prefillSerialNumber(): String? {
        val normalized = SerialNormalizer.normalize(intent.getStringExtra(EXTRA_SERIAL_NUMBER))
        if (normalized.isNotEmpty()) {
            showSerialPage()
            binding.etSerialNumber.setText(normalized)
            return normalized
        }
        return null
    }

    private fun submitSerialQuery() {
        val serial = SerialNormalizer.normalize(binding.etSerialNumber.text?.toString())
        if (serial.isEmpty()) {
            showEmptyState("请输入有效序列号")
            Toast.makeText(this, "请输入序列号", Toast.LENGTH_SHORT).show()
            return
        }
        hideKeyboard()
        loadQualityWorkbench(serial)
    }

    private fun startQrScanner() {
        val options = enhancedQrScanner.createEnhancedScanOptions("扫描产品序列号")
        barcodeLauncher.launch(options)
    }

    private fun hideKeyboard() {
        val imm = getSystemService(INPUT_METHOD_SERVICE) as? InputMethodManager ?: return
        currentFocus?.windowToken?.let { windowToken ->
            imm.hideSoftInputFromWindow(windowToken, 0)
        }
    }

    private fun loadQualityWorkbench(serial: String) {
        val requestId = ++activeRequestId
        latestRequestedSerial = serial
        currentSerialNumber = ""
        showLoadingState()
        AppLogger.log(TAG, "加载质量工作台: $serial, requestId=$requestId")

        lifecycleScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    apiService.getQualityWorkbench(serial)
                }
                if (shouldIgnoreResponse(requestId, serial)) {
                    AppLogger.log(TAG, "忽略过期质量工作台响应: serial=$serial requestId=$requestId")
                    return@launch
                }

                if (!response.isSuccessful) {
                    showErrorState("请求失败 (${response.code()})")
                    return@launch
                }

                val payload = response.body()
                if (payload == null) {
                    showErrorState("返回数据为空")
                    return@launch
                }

                if (!payload.success) {
                    showErrorState(payload.error ?: "未找到该序列号的质量工作台数据")
                    return@launch
                }

                renderPayload(payload)
            } catch (e: Exception) {
                if (shouldIgnoreResponse(requestId, serial)) {
                    AppLogger.log(TAG, "忽略过期质量工作台异常: serial=$serial requestId=$requestId")
                    return@launch
                }
                AppLogger.log(TAG, "加载质量工作台失败: ${e.message}", e)
                showErrorState("网络连接失败: ${e.message}")
            }
        }
    }

    private fun loadShipmentStats() {
        lifecycleScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    apiService.getQualityWorkbenchShipmentStats()
                }
                if (!response.isSuccessful) {
                    binding.shipmentStatsSection.visibility = View.GONE
                    return@launch
                }

                val payload = response.body()
                if (payload == null || !payload.success) {
                    binding.shipmentStatsSection.visibility = View.GONE
                    return@launch
                }

                renderShipmentStats(payload)
            } catch (e: Exception) {
                AppLogger.log(TAG, "加载出厂统计失败: ${e.message}", e)
                binding.shipmentStatsSection.visibility = View.GONE
            }
        }
    }

    private fun shouldIgnoreResponse(requestId: Int, serial: String): Boolean {
        return requestId != activeRequestId || serial != latestRequestedSerial
    }

    private fun openProcessDetail(step: QualityProcessResultDto) {
        val serial = currentSerialNumber
        if (serial.isEmpty() || step.process.isBlank()) {
            Toast.makeText(this, "缺少工序详情参数", Toast.LENGTH_SHORT).show()
            return
        }
        QualityProcessDetailDialogFragment
            .newInstance(serial, step.process)
            .show(supportFragmentManager, "quality_process_detail")
    }

    private fun renderPayload(payload: QualityWorkbenchResponse) {
        showSerialPage()
        binding.loadingSection.visibility = View.GONE
        binding.tvEmptyMessage.visibility = View.GONE
        binding.workbenchContent.visibility = View.VISIBLE
        binding.workbenchContent.scrollTo(0, 0)

        val conclusion = payload.qualityConclusion
        val baseRecord = payload.baseRecord
        val materialStatus = payload.materialStatus
        val processStatus = payload.processStatus
        val triggeredChecks = conclusion.triggeredRules.ifEmpty {
            payload.checks.filter { !it.passed && !it.severity.isNullOrBlank() }
        }

        currentSerialNumber = SerialNormalizer.normalize(payload.serialNumber)
        binding.tvSummarySerial.text = currentSerialNumber.ifBlank { "-" }
        binding.tvSummaryProject.text = buildInlineMeta("项目", payload.projectName)
        binding.tvSummaryProductType.text = buildInlineMeta("产品类型", payload.productType)
        binding.tvConclusionSummary.text = conclusion.summary.ifBlank { "—" }
        binding.tvShipmentStatus.text = if (conclusion.shipmentReady) "满足出货" else "暂不满足出货"
        binding.tvShipmentEvidence.text = buildShipmentTrackingText(payload)

        applyBadgeStyle(
            binding.tvConclusionLabel,
            conclusion.label.ifBlank { mapStatusLabel(conclusion.level) },
            conclusion.level
        )

        binding.tvBaseRecordMeta.text = buildMetaText(
            "记录状态" to if (baseRecord.exists) "已记录" else "未记录",
            "最近扫描时间" to baseRecord.latestScanTimeFormatted.ifBlank { "-" },
            "操作员" to baseRecord.operator.ifBlank { "-" },
            "当前状态" to baseRecord.status.ifBlank { "-" }
        )

        binding.tvMaterialMeta.text = buildMetaText(
            "必需物料数" to materialStatus.requiredTotal.toString(),
            "已记录物料数" to materialStatus.recordedCount.toString(),
            "缺失物料数" to materialStatus.missingCount.toString(),
            "是否完整" to if (materialStatus.complete) "是" else "否"
        )
        binding.tvMissingMaterials.text = buildListText(
            title = "缺失物料",
            items = materialStatus.missingMaterials,
            emptyText = "当前没有缺失物料。"
        )

        binding.tvProcessMeta.text = buildMetaText(
            "总工序数" to processStatus.totalProcesses.toString(),
            "要求拍照工序" to processStatus.requiredPhotoProcesses.toString(),
            "缺失照片工序" to processStatus.missingPhotoCount.toString(),
            "已完成检查工序" to processStatus.inspectedProcesses.toString()
        )
        binding.tvMissingProcesses.text = buildListText(
            title = "缺少照片工序",
            items = processStatus.missingPhotoProcesses,
            emptyText = "当前没有缺少照片的工序。"
        )
        processAdapter.updateData(processStatus.results)
        binding.tvProcessEmpty.visibility = if (processStatus.results.isEmpty()) View.VISIBLE else View.GONE

        renderReport(binding.tvHilStatus, binding.tvHilMeta, payload.testReports.hil, "HIL")
        renderReport(binding.tvBemfStatus, binding.tvBemfMeta, payload.testReports.bemf, "反电势")
        binding.tvTriggeredChecks.text = buildChecksText(triggeredChecks)
    }

    private fun renderShipmentStats(payload: QualityShipmentStatsResponse) {
        binding.shipmentStatsSection.visibility = View.VISIBLE
        binding.tvShipmentStatsDate.text = "今日出厂统计"
        binding.tvShipmentStatsCount.text = payload.todayCount.toString()
        binding.tvShipmentStatsTrend.text = payload.trend
            .takeLast(7)
            .joinToString("  ") { item ->
                val label = if (item.date.length >= 5) item.date.substring(5) else item.date
                "$label ${item.count}"
            }
            .ifBlank { "暂无近 7 天统计" }
        binding.tvShipmentStatsModels.text = payload.modelBreakdown
            .take(4)
            .joinToString("\n") { item ->
                val projectName = item.projectName.ifBlank { "-" }
                val productType = item.productType.ifBlank { "-" }
                val modelName = if (projectName == productType || productType == "-") {
                    projectName
                } else {
                    "$projectName / $productType"
                }
                "$modelName  ${item.count}台"
            }
            .ifBlank { "暂无当日产品型号统计" }
        binding.tvShipmentStatsRecent.text = payload.recentShipments
            .take(3)
            .joinToString("\n") { item ->
                val modelName = listOf(
                    item.projectName.takeIf { it.isNotBlank() },
                    item.productType.takeIf { it.isNotBlank() }
                ).joinToString(" / ")
                "${item.serialNumber.ifBlank { "-" }}\n$modelName  ${item.latestPhotoTimeFormatted.ifBlank { "-" }}"
            }
            .ifBlank { "今天还没有出厂检测拍照记录" }
    }

    private fun renderReport(
        titleView: TextView,
        metaView: TextView,
        report: QualityReportStatusDto,
        moduleName: String
    ) {
        val label = when {
            report.required != true -> "不要求"
            report.present -> "已关联"
            else -> "未关联"
        }
        val level = when {
            report.required != true -> "ignore"
            report.present -> "pass"
            else -> report.severity
        }
        applyBadgeStyle(titleView, "$moduleName：$label", level)

        val latest = report.latest
        val latestFile = latest?.fileName?.takeIf { it.isNotBlank() }
            ?: latest?.filePath?.takeIf { it.isNotBlank() }
            ?: "无"
        val latestResult = latest?.testResult?.takeIf { it.isNotBlank() } ?: "无"
        val latestTime = latest?.testTime?.takeIf { it.isNotBlank() } ?: "无"

        metaView.text = buildMetaText(
            "是否必需" to when {
                report.required != true -> "否"
                report.severity == "review" -> "评审项"
                else -> "阻断项"
            },
            "关联数量" to report.count.toString(),
            "最新文件" to latestFile,
            "测试结果" to latestResult,
            "测试时间" to latestTime
        )
    }

    private fun showEmptyState(message: CharSequence = DEFAULT_EMPTY_MESSAGE) {
        binding.loadingSection.visibility = View.GONE
        binding.tvEmptyMessage.visibility = View.VISIBLE
        binding.workbenchContent.visibility = View.GONE
        binding.tvEmptyMessage.text = message
    }

    private fun showLoadingState() {
        binding.loadingSection.visibility = View.VISIBLE
        binding.tvEmptyMessage.visibility = View.GONE
        binding.workbenchContent.visibility = View.GONE
    }

    private fun showErrorState(message: CharSequence) {
        showEmptyState(message)
    }

    private fun applyBadgeStyle(textView: TextView, label: String, level: String?) {
        textView.text = label
        val background = GradientDrawable().apply { cornerRadius = 16f }
        when (level) {
            "pass" -> {
                background.setColor(Color.parseColor("#E6F4EA"))
                textView.setTextColor(Color.parseColor("#1B5E20"))
            }
            "review", "ng" -> {
                background.setColor(Color.parseColor("#FFF4E5"))
                textView.setTextColor(Color.parseColor("#B45309"))
            }
            "block", "fail" -> {
                background.setColor(Color.parseColor("#FDECEC"))
                textView.setTextColor(Color.parseColor("#B91C1C"))
            }
            "ignore" -> {
                background.setColor(Color.parseColor("#EEF2FF"))
                textView.setTextColor(Color.parseColor("#475569"))
            }
            else -> {
                background.setColor(Color.parseColor("#F1F5F9"))
                textView.setTextColor(Color.parseColor("#475569"))
            }
        }
        textView.background = background
    }

    private fun buildInlineMeta(key: String, value: String): String {
        return "$key：${value.ifBlank { "-" }}"
    }

    private fun buildMetaText(vararg items: Pair<String, String>): String {
        return items.joinToString("\n") { (key, value) -> "$key：${value.ifBlank { "-" }}" }
    }

    private fun buildListText(title: String, items: List<String>, emptyText: String): String {
        val filteredItems = items.filter { it.isNotBlank() }
        if (filteredItems.isEmpty()) {
            return "$title：$emptyText"
        }
        return buildString {
            append(title)
            append("：\n")
            filteredItems.forEach { item ->
                append("• ")
                append(item)
                append('\n')
            }
        }.trimEnd()
    }

    private fun buildChecksText(checks: List<QualityCheckDto>): String {
        if (checks.isEmpty()) {
            return "当前没有命中阻断/评审规则。"
        }
        return buildString {
            checks.forEachIndexed { index, check ->
                append(index + 1)
                append(". ")
                append(check.summary.ifBlank { check.key.ifBlank { "未命名规则" } })
                if (!check.severity.isNullOrBlank()) {
                    append(" [")
                    append(check.severity)
                    append(']')
                }
                append('\n')
                check.details.filter { it.isNotBlank() }.forEach { detail ->
                    append("   - ")
                    append(detail)
                    append('\n')
                }
            }
        }.trimEnd()
    }

    private fun buildShipmentTrackingText(payload: QualityWorkbenchResponse): String {
        val tracking = payload.shipmentTracking
        if (!tracking.hasShipmentPhoto) {
            return "当前序列号暂无出厂检测/发运拍照记录"
        }
        val processStep = tracking.latestProcessStep.ifBlank { "出厂拍照" }
        val photoTime = tracking.latestPhotoTimeFormatted.ifBlank { "-" }
        return "已记录 $processStep，时间：$photoTime，照片数：${tracking.photoCount}"
    }

    private fun mapStatusLabel(level: String?): String {
        return when (level) {
            "pass" -> "可出货"
            "review", "ng" -> "待质量评审"
            "block", "fail" -> "不可出货"
            else -> "待补充"
        }
    }

    companion object {
        const val EXTRA_SERIAL_NUMBER = "extra_serial_number"
        private const val SCREEN_TITLE = "质量工作台"
        private const val DEFAULT_EMPTY_MESSAGE = "请输入序列号查询质量工作台"
        private const val TAG = "QualityWorkbench"
    }
}
