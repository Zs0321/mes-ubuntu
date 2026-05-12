package com.testcenter.qrscanner.quality

import com.google.gson.JsonElement
import com.google.gson.annotations.SerializedName

data class QualityWorkbenchResponse @JvmOverloads constructor(
    val success: Boolean = false,
    @SerializedName(value = "serialNumber", alternate = ["serial_number"])
    val serialNumber: String = "",
    @SerializedName(value = "projectName", alternate = ["project_name"])
    val projectName: String = "",
    @SerializedName(value = "productType", alternate = ["product_type"])
    val productType: String = "",
    val qualityWorkbench: QualityWorkbenchConfigDto = QualityWorkbenchConfigDto(),
    val qualityConclusion: QualityConclusionDto = QualityConclusionDto(),
    val baseRecord: QualityBaseRecordDto = QualityBaseRecordDto(),
    val materialStatus: QualityMaterialStatusDto = QualityMaterialStatusDto(),
    val processStatus: QualityProcessStatusDto = QualityProcessStatusDto(),
    val testReports: QualityTestReportsDto = QualityTestReportsDto(),
    val checks: List<QualityCheckDto> = emptyList(),
    val shipmentTracking: QualityShipmentTrackingDto = QualityShipmentTrackingDto(),
    val associations: Map<String, JsonElement> = emptyMap(),
    val error: String? = null
)

data class QualityShipmentTrackingDto @JvmOverloads constructor(
    @SerializedName(value = "hasShipmentPhoto", alternate = ["has_shipment_photo"])
    val hasShipmentPhoto: Boolean = false,
    @SerializedName(value = "photoCount", alternate = ["photo_count"])
    val photoCount: Int = 0,
    @SerializedName(value = "latestProcessStep", alternate = ["latest_process_step"])
    val latestProcessStep: String = "",
    @SerializedName(value = "latestPhotoTime", alternate = ["latest_photo_time"])
    val latestPhotoTime: Long? = null,
    @SerializedName(value = "latestPhotoTimeFormatted", alternate = ["latest_photo_time_formatted"])
    val latestPhotoTimeFormatted: String = "",
    @SerializedName(value = "countedDate", alternate = ["counted_date"])
    val countedDate: String = ""
)

data class QualityShipmentStatsResponse @JvmOverloads constructor(
    val success: Boolean = false,
    @SerializedName(value = "selectedDate", alternate = ["selected_date"])
    val selectedDate: String = "",
    @SerializedName(value = "todayDate", alternate = ["today_date"])
    val todayDate: String = "",
    @SerializedName(value = "selectedDateCount", alternate = ["selected_date_count"])
    val selectedDateCount: Int = 0,
    @SerializedName(value = "todayCount", alternate = ["today_count"])
    val todayCount: Int = 0,
    @SerializedName(value = "recentShipments", alternate = ["recent_shipments"])
    val recentShipments: List<QualityShipmentRecordDto> = emptyList(),
    @SerializedName(value = "modelBreakdown", alternate = ["model_breakdown"])
    val modelBreakdown: List<QualityShipmentModelStatDto> = emptyList(),
    val trend: List<QualityShipmentTrendPointDto> = emptyList(),
    @SerializedName(value = "matchedPatterns", alternate = ["matched_patterns"])
    val matchedPatterns: List<String> = emptyList(),
    val error: String? = null
)

data class QualityShipmentModelStatDto @JvmOverloads constructor(
    @SerializedName(value = "projectName", alternate = ["project_name"])
    val projectName: String = "",
    @SerializedName(value = "productType", alternate = ["product_type"])
    val productType: String = "",
    val count: Int = 0
)

data class QualityShipmentRecordDto @JvmOverloads constructor(
    @SerializedName(value = "serialNumber", alternate = ["serial_number"])
    val serialNumber: String = "",
    @SerializedName(value = "projectName", alternate = ["project_name"])
    val projectName: String = "",
    @SerializedName(value = "productType", alternate = ["product_type"])
    val productType: String = "",
    @SerializedName(value = "processStep", alternate = ["process_step"])
    val processStep: String = "",
    @SerializedName(value = "photoCount", alternate = ["photo_count"])
    val photoCount: Int = 0,
    @SerializedName(value = "latestPhotoTime", alternate = ["latest_photo_time"])
    val latestPhotoTime: Long? = null,
    @SerializedName(value = "latestPhotoTimeFormatted", alternate = ["latest_photo_time_formatted"])
    val latestPhotoTimeFormatted: String = ""
)

data class QualityShipmentTrendPointDto @JvmOverloads constructor(
    val date: String = "",
    val count: Int = 0
)

data class QualityWorkbenchConfigDto @JvmOverloads constructor(
    val enabled: Boolean? = null,
    val defaultRules: Map<String, String> = emptyMap()
)

data class QualityConclusionDto @JvmOverloads constructor(
    val level: String? = null,
    val label: String = "",
    val shipmentReady: Boolean = false,
    val summary: String = "",
    val triggeredRules: List<QualityCheckDto> = emptyList()
)

data class QualityCheckDto @JvmOverloads constructor(
    val key: String = "",
    val severity: String? = null,
    val passed: Boolean = false,
    val summary: String = "",
    val details: List<String> = emptyList()
)

data class QualityBaseRecordDto @JvmOverloads constructor(
    val exists: Boolean = false,
    val latestScanTime: JsonElement? = null,
    val latestScanTimeFormatted: String = "",
    val operator: String = "",
    val status: String = "missing"
)

data class QualityMaterialStatusDto @JvmOverloads constructor(
    val requiredTotal: Int = 0,
    val recordedCount: Int = 0,
    val missingCount: Int = 0,
    val missingMaterials: List<String> = emptyList(),
    val complete: Boolean = false,
    val hasRequirements: Boolean = false
)

data class QualityProcessStatusDto @JvmOverloads constructor(
    val totalProcesses: Int = 0,
    val requiredPhotoProcesses: Int = 0,
    val requiredPhotoProcessNames: List<String> = emptyList(),
    val missingPhotoProcesses: List<String> = emptyList(),
    val missingPhotoCount: Int = 0,
    val overallStatus: String? = null,
    val inspectedProcesses: Int = 0,
    val nonPassProcesses: List<QualityNonPassProcessDto> = emptyList(),
    val results: List<QualityProcessResultDto> = emptyList()
)

data class QualityNonPassProcessDto @JvmOverloads constructor(
    val process: String = "",
    val status: String? = null,
    val summary: String = ""
)

data class QualityProcessResultDto @JvmOverloads constructor(
    val process: String = "",
    val order: Int = 0,
    val status: String? = null,
    @SerializedName(value = "effective_status", alternate = ["effectiveStatus"])
    val effectiveStatus: String? = null,
    val confidence: Float = 0f,
    val summary: String = "",
    @SerializedName(value = "effective_summary", alternate = ["effectiveSummary"])
    val effectiveSummary: String = "",
    @SerializedName(value = "has_photo", alternate = ["hasPhoto"])
    val hasPhoto: Boolean = false,
    @SerializedName(value = "photo_required", alternate = ["photoRequired"])
    val photoRequired: Boolean? = null,
    @SerializedName(value = "photo_count", alternate = ["photoCount"])
    val photoCount: Int = 0,
    @SerializedName(value = "defect_count", alternate = ["defectCount"])
    val defectCount: Int = 0,
    val defects: List<QualityDefectDto> = emptyList(),
    @SerializedName(value = "ai_status", alternate = ["aiStatus"])
    val aiStatus: String? = null,
    @SerializedName(value = "ai_summary", alternate = ["aiSummary"])
    val aiSummary: String = "",
    @SerializedName(value = "ai_defect_count", alternate = ["aiDefectCount"])
    val aiDefectCount: Int = 0,
    @SerializedName(value = "ai_defects", alternate = ["aiDefects"])
    val aiDefects: List<QualityDefectDto> = emptyList(),
    @SerializedName(value = "human_status", alternate = ["humanStatus"])
    val humanStatus: String? = null,
    @SerializedName(value = "human_summary", alternate = ["humanSummary"])
    val humanSummary: String = "",
    @SerializedName(value = "human_defect_count", alternate = ["humanDefectCount"])
    val humanDefectCount: Int = 0,
    @SerializedName(value = "human_defects", alternate = ["humanDefects"])
    val humanDefects: List<QualityDefectDto> = emptyList(),
    @SerializedName(value = "latest_inspection_time", alternate = ["latestInspectionTime"])
    val latestInspectionTime: String? = null,
    @SerializedName(value = "latest_inspection_time_formatted", alternate = ["latestInspectionTimeFormatted"])
    val latestInspectionTimeFormatted: String = "",
    val detailAvailable: Boolean = false
)

data class QualityTestReportsDto @JvmOverloads constructor(
    @SerializedName("HIL")
    val hil: QualityReportStatusDto = QualityReportStatusDto(),
    @SerializedName("BEMF")
    val bemf: QualityReportStatusDto = QualityReportStatusDto()
)

data class QualityReportStatusDto @JvmOverloads constructor(
    val present: Boolean = false,
    val count: Int = 0,
    val latest: QualityLinkedReportDto? = null,
    val severity: String? = null,
    val required: Boolean? = null
)

data class QualityLinkedReportDto @JvmOverloads constructor(
    val id: Long? = null,
    @SerializedName(value = "serial_number", alternate = ["serialNumber"])
    val serialNumber: String = "",
    @SerializedName(value = "project_name", alternate = ["projectName"])
    val projectName: String = "",
    @SerializedName(value = "test_module", alternate = ["testModule"])
    val testModule: String = "",
    @SerializedName(value = "test_result", alternate = ["testResult"])
    val testResult: String = "",
    @SerializedName(value = "test_time", alternate = ["testTime"])
    val testTime: String? = null,
    @SerializedName(value = "file_path", alternate = ["filePath"])
    val filePath: String = "",
    @SerializedName(value = "file_name", alternate = ["fileName"])
    val fileName: String = "",
    @SerializedName(value = "report_type", alternate = ["reportType"])
    val reportType: String = "",
    val description: String = "",
    @SerializedName(value = "created_at", alternate = ["createdAt"])
    val createdAt: String? = null,
    @SerializedName(value = "updated_at", alternate = ["updatedAt"])
    val updatedAt: String? = null
)

data class QualityProcessDetailResponse @JvmOverloads constructor(
    val success: Boolean = false,
    @SerializedName(value = "serialNumber", alternate = ["serial_number"])
    val serialNumber: String = "",
    @SerializedName(value = "projectName", alternate = ["project_name"])
    val projectName: String = "",
    @SerializedName(value = "productType", alternate = ["product_type"])
    val productType: String = "",
    val processDetail: QualityProcessDetailDto = QualityProcessDetailDto(),
    val error: String? = null
)

data class QualityProcessDetailDto @JvmOverloads constructor(
    val process: String = "",
    val order: Int = 0,
    @SerializedName(value = "canDeletePhotos", alternate = ["can_delete_photos"])
    val canDeletePhotos: Boolean = false,
    @SerializedName(value = "photoRequired", alternate = ["photo_required"])
    val photoRequired: Boolean? = null,
    @SerializedName(value = "hasPhoto", alternate = ["has_photo"])
    val hasPhoto: Boolean = false,
    @SerializedName(value = "photoCount", alternate = ["photo_count"])
    val photoCount: Int = 0,
    val status: String? = null,
    @SerializedName(value = "aiStatus", alternate = ["ai_status"])
    val aiStatus: String? = null,
    @SerializedName(value = "aiSummary", alternate = ["ai_summary"])
    val aiSummary: String = "",
    @SerializedName(value = "humanStatus", alternate = ["human_status"])
    val humanStatus: String? = null,
    @SerializedName(value = "humanSummary", alternate = ["human_summary"])
    val humanSummary: String = "",
    @SerializedName(value = "effectiveSummary", alternate = ["effective_summary"])
    val effectiveSummary: String = "",
    @SerializedName(value = "defectCount", alternate = ["defect_count"])
    val defectCount: Int = 0,
    val defects: List<QualityDefectDto> = emptyList(),
    val photos: List<QualityPhotoDto> = emptyList(),
    @SerializedName(value = "latestInspectionTime", alternate = ["latest_inspection_time_formatted", "latest_inspection_time"])
    val latestInspectionTime: String = ""
)

data class QualityPhotoDto @JvmOverloads constructor(
    val name: String = "",
    val url: String = "",
    @SerializedName(value = "thumbnailUrl", alternate = ["thumbnail_url"])
    val thumbnailUrl: String = "",
    @SerializedName(value = "relativePath", alternate = ["relative_path", "path"])
    val relativePath: String = ""
)

data class QualityDefectDto @JvmOverloads constructor(
    val type: String = "",
    val severity: String = "",
    val description: String = "",
    val location: String = "",
    val confidence: Float = 0f
)
