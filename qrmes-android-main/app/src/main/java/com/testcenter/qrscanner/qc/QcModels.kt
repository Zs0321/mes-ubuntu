package com.testcenter.qrscanner.qc

import com.google.gson.annotations.SerializedName

/**
 * QC 分析请求
 * 提交照片到后端进行千问 Vision 识别
 */
data class QcAnalyzeRequest(
    @SerializedName("product_serial")
    val productSerial: String,
    @SerializedName("process_name")
    val processName: String,
    @SerializedName("process_index")
    val processIndex: Int,
    @SerializedName("project_name")
    val projectName: String,
    @SerializedName("product_type")
    val productType: String,
    @SerializedName("photo_base64")
    val photoBase64: List<String>
)

/**
 * QC 分析响应
 * 三级判定：pass / fail / ng
 */
data class QcAnalyzeResponse(
    val success: Boolean,
    val status: String,           // "pass" / "fail" / "ng"
    val confidence: Float = 0f,
    val summary: String = "",
    val findings: List<QcFinding> = emptyList(),
    val checklist: Map<String, Boolean> = emptyMap(),
    val error: String? = null
)

/**
 * QC 人工确认请求
 */
data class QcManualConfirmRequest(
    @SerializedName("product_serial")
    val productSerial: String,
    @SerializedName("project_name")
    val projectName: String,
    @SerializedName("process_name")
    val processName: String,
    @SerializedName("human_status")
    val humanStatus: String,
    @SerializedName("human_summary")
    val humanSummary: String? = null
)

/**
 * QC 人工确认响应
 */
data class QcManualConfirmResponse(
    val success: Boolean,
    val message: String? = null,
    val error: String? = null
)

/**
 * QC 缺陷发现
 */
data class QcFinding(
    val type: String,             // missing_material, misalignment, contamination, damage, incomplete, measurement_error
    val severity: String,         // critical, major, minor
    val description: String,
    val location: String = "",
    val confidence: Float = 0f
)

/**
 * 前面工序检查响应
 */
data class QcPreviousCheckResponse(
    val success: Boolean,
    @SerializedName("current_process_index")
    val currentProcessIndex: Int = 0,
    @SerializedName("previous_steps")
    val previousSteps: List<QcStepStatus> = emptyList(),
    @SerializedName("all_passed")
    val allPassed: Boolean = false,
    @SerializedName("missing_photos")
    val missingPhotos: List<String> = emptyList(),
    @SerializedName("failed_steps")
    val failedSteps: List<String> = emptyList(),
    @SerializedName("ng_steps")
    val ngSteps: List<String> = emptyList(),
    val error: String? = null
)

/**
 * 单个工序的 QC 状态
 */
data class QcStepStatus(
    @SerializedName("process_name")
    val processName: String,
    val order: Int,
    @SerializedName("has_photo")
    val hasPhoto: Boolean = false,
    @SerializedName("photo_count")
    val photoCount: Int = 0,
    @SerializedName("qc_status")
    val qcStatus: String? = null   // "pass" / "fail" / "ng" / null(未检)
)

/**
 * QC 策略配置响应
 */
data class QcPolicyResponse(
    val success: Boolean,
    val data: QcPolicy? = null,
    val error: String? = null
)

/**
 * QC 策略配置
 */
data class QcPolicy(
    @SerializedName("qc_enabled")
    val qcEnabled: Boolean = false,
    @SerializedName("enforcement_mode")
    val enforcementMode: String = "warn",   // "warn" = 警告允许继续, "block" = 强制阻断
    @SerializedName("check_previous_photos")
    val checkPreviousPhotos: Boolean = true,
    @SerializedName("realtime_qc_enabled")
    val realtimeQcEnabled: Boolean = true,
    @SerializedName("vision_model")
    val visionModel: String = "qwen3-vl-flash",
    @SerializedName("confidence_threshold")
    val confidenceThreshold: Float = 0.8f
) {
    companion object {
        /** 默认策略：QC 关闭 */
        val DEFAULT = QcPolicy()
    }
}

/**
 * 电机检验报告响应（整机）
 */
data class QcInspectionReportResponse(
    val success: Boolean,
    @SerializedName("serial_number")
    val serialNumber: String = "",
    @SerializedName("overall_status")
    val overallStatus: String = "",       // "pass" / "fail" / "ng"
    @SerializedName("project_name")
    val projectName: String = "",
    @SerializedName("product_type")
    val productType: String = "",
    @SerializedName("total_processes")
    val totalProcesses: Int = 0,
    @SerializedName("inspected_processes")
    val inspectedProcesses: Int = 0,
    @SerializedName("missing_processes")
    val missingProcesses: List<String> = emptyList(),
    val results: List<QcProcessResult> = emptyList(),
    val error: String? = null
)

/**
 * 单个工序的检验结果
 */
data class QcProcessResult(
    val process: String = "",
    val order: Int = 0,
    val status: String? = null,           // "pass" / "fail" / "ng" / null
    @SerializedName("effective_status")
    val effectiveStatus: String? = null,
    val confidence: Float = 0f,
    val summary: String = "",
    @SerializedName("effective_summary")
    val effectiveSummary: String = "",
    @SerializedName("ai_status")
    val aiStatus: String? = null,
    @SerializedName("ai_summary")
    val aiSummary: String = "",
    @SerializedName("ai_defects")
    val aiDefects: List<QcDefectInfo> = emptyList(),
    @SerializedName("human_status")
    val humanStatus: String? = null,
    @SerializedName("human_summary")
    val humanSummary: String = "",
    @SerializedName("human_defects")
    val humanDefects: List<QcDefectInfo> = emptyList(),
    @SerializedName("has_photo")
    val hasPhoto: Boolean = false,
    @SerializedName("photo_count")
    val photoCount: Int = 0,
    @SerializedName("defect_count")
    val defectCount: Int = 0,
    val defects: List<QcDefectInfo> = emptyList()
)

/**
 * 缺陷信息
 */
data class QcDefectInfo(
    val type: String = "",
    val severity: String = "",
    val description: String = "",
    val location: String = "",
    val confidence: Float = 0f
)
