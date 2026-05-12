package com.testcenter.qrscanner.api

import com.google.gson.annotations.SerializedName
import com.testcenter.qrscanner.qc.*
import com.testcenter.qrscanner.quality.QualityProcessDetailResponse
import com.testcenter.qrscanner.quality.QualityShipmentStatsResponse
import com.testcenter.qrscanner.quality.QualityWorkbenchResponse
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.*

/**
 * REST API 接口定义
 * 替代 SMB 文件操作，提供统一的 HTTP API 调用
 */
interface ApiService {

    @POST("api/mobile-auth/login")
    suspend fun mobileLogin(@Body request: MobileLoginRequest): Response<MobileLoginResponse>

    @POST("api/mobile-auth/change-password")
    suspend fun mobileChangePassword(
        @Body request: MobileChangePasswordRequest
    ): Response<MobileChangePasswordResponse>

    // ==================== 测试人员 API ====================

    @GET("api/testers")
    suspend fun getTesters(): Response<TestersResponse>

    @POST("api/testers")
    suspend fun saveTesters(@Body request: SaveTestersRequest): Response<ApiResponse>

    @POST("api/testers/{name}")
    suspend fun addTester(@Path("name") name: String): Response<ApiResponse>

    @DELETE("api/testers/{name}")
    suspend fun removeTester(@Path("name") name: String): Response<ApiResponse>

    // ==================== 活动测试 API ====================

    @GET("api/active-tests")
    suspend fun getActiveTests(): Response<ActiveTestsResponse>

    @GET("api/active-tests/{serial}")
    suspend fun getActiveTest(@Path("serial") serial: String): Response<ActiveTestResponse>

    @POST("api/active-tests")
    suspend fun upsertActiveTest(@Body request: ActiveTestRequest): Response<ApiResponse>

    @DELETE("api/active-tests/{serial}")
    suspend fun removeActiveTest(@Path("serial") serial: String): Response<ApiResponse>

    // ==================== APK 更新 API ====================

    @GET("api/apk/list")
    suspend fun listApks(): Response<ApkListResponse>

    @GET("api/apk/latest")
    suspend fun getLatestApk(@Query("appName") appName: String? = null): Response<LatestApkResponse>

    @GET("api/apk/check-update")
    suspend fun checkUpdate(
        @Query("versionCode") versionCode: Int,
        @Query("versionName") versionName: String,
        @Query("appName") appName: String? = null
    ): Response<CheckUpdateResponse>

    @GET("api/apk/download/{filename}")
    @Streaming
    suspend fun downloadApk(@Path("filename") filename: String): Response<ResponseBody>

    @Multipart
    @POST("api/apk-logs/upload")
    suspend fun uploadApkLogs(
        @Part file: MultipartBody.Part,
        @Part("appVersionName") appVersionName: RequestBody,
        @Part("appVersionCode") appVersionCode: RequestBody,
        @Part("deviceModel") deviceModel: RequestBody,
        @Part("manufacturer") manufacturer: RequestBody,
        @Part("androidVersion") androidVersion: RequestBody,
        @Part("source") source: RequestBody? = null,
        @Part("eventType") eventType: RequestBody? = null,
        @Part("severity") severity: RequestBody? = null,
        @Part("feature") feature: RequestBody? = null,
        @Part("reasonCode") reasonCode: RequestBody? = null,
        @Part("httpStatus") httpStatus: RequestBody? = null,
        @Part("trigger") trigger: RequestBody? = null,
        @Part("summary") summary: RequestBody? = null,
        @Part("extraJson") extraJson: RequestBody? = null
    ): Response<ApkLogUploadResponse>

    // ==================== 项目管理 API ====================

    @GET("api/projects")
    suspend fun getProjects(): Response<ProjectsResponse>

    @POST("api/projects")
    suspend fun saveProjects(@Body request: SaveProjectsRequest): Response<ApiResponse>

    // ==================== 项目配置 API ====================

    @GET("api/process-config/projects/{projectName}/config")
    suspend fun getProjectConfig(@Path("projectName") projectName: String): Response<ProjectConfigResponse>

    @GET("api/process-config/resolve-serial-rule")
    suspend fun resolveSerialRule(
        @Query("serial") serial: String
    ): Response<SerialRuleResolutionResponse>

    @POST("api/process-config/projects/{projectName}/config")
    suspend fun saveProjectConfig(
        @Path("projectName") projectName: String,
        @Body config: ProjectConfigRequest
    ): Response<ApiResponse>

    @GET("api/process-config/me/groups")
    suspend fun getCurrentUserGroups(): Response<CurrentUserGroupsResponse>

    // ==================== 产品记录 API (H2) ====================

    @GET("api/h2/query/{serial}")
    suspend fun queryProductRecord(@Path("serial") serial: String): Response<ProductRecordResponse>

    @POST("api/h2/save")
    suspend fun saveProductRecord(@Body request: SaveProductRecordRequest): Response<ApiResponse>

    @GET("api/h2/recommend/{serial}")
    suspend fun getSerialRecommendation(
        @Path("serial") serial: String,
        @Query("current_project") currentProject: String? = null,
        @Query("current_product_type") currentProductType: String? = null
    ): Response<SerialRecommendationResponse>

    @POST("api/h2/learning/confirm")
    suspend fun confirmSerialLearning(
        @Body request: SerialLearningConfirmRequest
    ): Response<ApiResponse>

    @POST("api/h2/binding/repair")
    suspend fun repairSerialBinding(
        @Body request: SerialBindingRepairRequest
    ): Response<ApiResponse>

    // ==================== 质量工作台 API ====================

    @GET("api/quality-workbench/{serial}")
    suspend fun getQualityWorkbench(
        @Path("serial") serial: String
    ): Response<QualityWorkbenchResponse>

    @GET("api/quality-workbench/shipment-stats")
    suspend fun getQualityWorkbenchShipmentStats(
        @Query("date") date: String? = null,
        @Query("trendDays") trendDays: Int = 7,
        @Query("limit") limit: Int = 20
    ): Response<QualityShipmentStatsResponse>

    @GET("api/quality-workbench/{serial}/processes/{processName}")
    suspend fun getQualityWorkbenchProcessDetail(
        @Path("serial") serial: String,
        @Path("processName") processName: String
    ): Response<QualityProcessDetailResponse>

    @HTTP(method = "DELETE", path = "api/quality-workbench/photo", hasBody = true)
    suspend fun deleteQualityWorkbenchPhoto(
        @Body request: QualityPhotoDeleteRequest
    ): Response<ApiResponse>

    // ==================== 照片 API ====================

    @Multipart
    @POST("api/photos/upload")
    suspend fun uploadPhoto(
        @Part photo: MultipartBody.Part,
        @Part("productSerial") productSerial: RequestBody,
        @Part("projectName") projectName: RequestBody,
        @Part("productType") productType: RequestBody,
        @Part("processStep") processStep: RequestBody?,
        @Part("projectCode") projectCode: RequestBody?,
        @Part("modelNumber") modelNumber: RequestBody?,
        @Part("skipQcEnqueue") skipQcEnqueue: RequestBody?
    ): Response<PhotoUploadResponse>

    @POST("api/photos/metadata")
    suspend fun savePhotoMetadata(@Body metadata: PhotoMetadataRequest): Response<ApiResponse>

    @GET("api/photos/list")
    suspend fun listPhotos(
        @Query("projectName") projectName: String?,
        @Query("productType") productType: String?,
        @Query("productSerial") productSerial: String?,
        @Query("processStep") processStep: String? = null
    ): Response<PhotoListResponse>

    // ==================== QC 质检 API ====================

    @POST("api/qc/analyze")
    suspend fun qcAnalyze(@Body request: QcAnalyzeRequest): Response<QcAnalyzeResponse>

    @POST("api/qc/confirm")
    suspend fun qcConfirm(@Body request: QcManualConfirmRequest): Response<QcManualConfirmResponse>

    @GET("api/qc/check-previous/{serial}")
    suspend fun qcCheckPrevious(
        @Path("serial") serial: String,
        @Query("processIndex") processIndex: Int,
        @Query("projectName") projectName: String,
        @Query("productType") productType: String
    ): Response<QcPreviousCheckResponse>

    @GET("api/qc/config/{projectName}")
    suspend fun getQcPolicy(@Path("projectName") projectName: String): Response<QcPolicyResponse>

    @GET("api/qc/report/{serial}")
    suspend fun getInspectionReport(
        @Path("serial") serial: String,
        @Query("projectName") projectName: String? = null,
        @Query("productType") productType: String? = null
    ): Response<QcInspectionReportResponse>

    // ==================== 文档/PDF API ====================

    @Multipart
    @POST("api/documents/upload")
    suspend fun uploadDocument(
        @Part file: MultipartBody.Part,
        @Part("productSerial") productSerial: RequestBody,
        @Part("projectName") projectName: RequestBody,
        @Part("productType") productType: RequestBody,
        @Part("processName") processName: RequestBody
    ): Response<DocumentUploadResponse>

    @GET("api/documents/download/{filename}")
    @Streaming
    suspend fun downloadDocument(@Path("filename") filename: String): Response<ResponseBody>

    @GET("api/documents/list")
    suspend fun listDocuments(
        @Query("projectName") projectName: String,
        @Query("productType") productType: String,
        @Query("productSerial") productSerial: String,
        @Query("processName") processName: String? = null
    ): Response<DocumentListResponse>

    // ==================== ???? API ====================

    @GET("api/material-inbound/resolve")
    suspend fun resolveMaterialInbound(
        @Query("serial") serial: String
    ): Response<MaterialInboundResolveResponse>

    @POST("api/material-inbound/confirm")
    suspend fun confirmMaterialInbound(
        @Body request: MaterialInboundConfirmRequest
    ): Response<MaterialInboundConfirmResponse>

    @Multipart
    @POST("api/material-inbound/photo")
    suspend fun uploadMaterialInboundPhoto(
        @Part photo: MultipartBody.Part,
        @Part("materialSerial") materialSerial: RequestBody,
        @Part("materialCode") materialCode: RequestBody,
        @Part("materialName") materialName: RequestBody,
        @Part("quantity") quantity: RequestBody,
        @Part("photoType") photoType: RequestBody
    ): Response<MaterialInboundPhotoUploadResponse>

    @POST("api/material-inbound/record")
    suspend fun recordMaterialInbound(
        @Body request: MaterialInboundRecordRequest
    ): Response<MaterialInboundRecordResponse>
}

// ==================== 请求/响应数据类 ====================

// 通用响应
data class ApiResponse(
    val success: Boolean,
    val message: String? = null,
    val error: String? = null
)

data class QualityPhotoDeleteRequest(
    val path: String
)

data class MobileLoginRequest(
    val username: String,
    val password: String
)

data class MobileChangePasswordRequest(
    val username: String,
    @SerializedName("current_password")
    val currentPassword: String,
    @SerializedName("new_password")
    val newPassword: String
)

data class MobileLoginResponse(
    val success: Boolean,
    @SerializedName("require_password_change")
    val requirePasswordChange: Boolean = false,
    val message: String? = null,
    val user: MobileAuthUser? = null,
    val permissions: List<String>? = null,
    val role: String? = null,
    @SerializedName("api_base_url")
    val apiBaseUrl: String? = null,
    val error: String? = null
)

data class MobileChangePasswordResponse(
    val success: Boolean,
    val message: String? = null,
    val user: MobileAuthUser? = null,
    val error: String? = null
)

data class MobileAuthUser(
    val id: String? = null,
    val username: String? = null,
    @SerializedName("synology_username")
    val synologyUsername: String? = null,
    @SerializedName("display_name")
    val displayName: String? = null,
    val role: String? = null,
    val email: String? = null
)

// 测试人员
data class TestersResponse(
    val success: Boolean,
    val testers: List<String>,
    val count: Int
)

data class SaveTestersRequest(
    val testers: List<String>
)

// 活动测试
data class ActiveTestsResponse(
    val success: Boolean,
    val tests: List<ActiveTest>,
    val count: Int
)

data class ActiveTestResponse(
    val success: Boolean,
    val test: ActiveTest?,
    val exists: Boolean
)

data class ActiveTest(
    val serial: String,
    val tester: String,
    val startTime: String
)

data class ActiveTestRequest(
    val serial: String,
    val tester: String,
    val startTime: String? = null
)

// APK 更新
data class ApkListResponse(
    val success: Boolean,
    val apks: List<ApkInfo>,
    val count: Int
)

data class LatestApkResponse(
    val success: Boolean,
    val apk: ApkInfo?,
    val hasUpdate: Boolean
)

data class CheckUpdateResponse(
    val success: Boolean,
    val hasUpdate: Boolean,
    val currentVersion: VersionInfo?,
    val latestVersion: ApkInfo?,
    val message: String?
)

data class ApkInfo(
    val appName: String,
    val versionName: String,
    val versionCode: Int,
    val fileName: String,
    val fileSize: Long,
    val lastModified: Long,
    val releaseNotes: String? = null,
    val releaseNotesFile: String? = null
)

data class VersionInfo(
    val versionCode: Int,
    val versionName: String
)

// 项目
data class ProjectsResponse(
    val success: Boolean,
    val projects: List<String>? = null,
    val data: List<String>? = null  // 兼容不同的响应格式
) {
    fun getProjectList(): List<String> = projects ?: data ?: emptyList()
}

data class SaveProjectsRequest(
    val projects: List<String>
)

// 项目配置
data class ProjectConfigResponse(
    val success: Boolean,
    @SerializedName("data")  // 服务端返回 "data" 字段，而非 "config"
    val config: ProjectConfig?,
    val error: String? = null
)

data class ProjectConfig(
    val projectName: String? = null,
    val projectCode: String? = null,
    val productTypes: List<ProductTypeConfig>? = null,
    @SerializedName("processSteps")  // 服务端返回 processSteps
    val processes: List<ProcessConfig>? = null,
    @SerializedName("configVersion")  // 服务端返回 configVersion
    val version: Int? = null,
    val lastModified: Long? = null,  // 服务端返回 Long 类型
    val description: String? = null,
    val createdAt: String? = null,
    val createdBy: String? = null
)

data class ProductTypeConfig(
    @SerializedName("typeName")  // 服务端可能返回 typeName
    val name: String? = null,
    val modelNumber: String? = null,
    @SerializedName(value = "serialRules", alternate = ["serial_rules", "serialPrefixes", "serial_prefixes"])
    val serialRules: List<String>? = null,
    val forceVersionCheck: Boolean? = null,
    val description: String? = null,
    val materials: List<MaterialConfig>? = null,
    val processSteps: List<ProcessConfig>? = null
)

data class MaterialConfig(
    val name: String,
    val partNumber: String? = null,
    val qrRuleType: String? = null,
    val expectedVersion: String? = null
)

data class ProcessConfig(
    val name: String,
    val order: Int? = null,
    @SerializedName("photoRequired")  // 服务端返回 photoRequired
    val requirePhoto: Boolean? = null,
    val photoCount: Int? = null,
    val description: String? = null,
    val id: String? = null,
    val estimatedDuration: Int? = null,
    val productType: String? = null,
    val required: Boolean? = null,
    val attachmentType: String? = null,  // "photo" / "pdf" / "both"
    @SerializedName(value = "responsibleDepartments", alternate = ["responsible_departments"])
    val responsibleDepartments: List<String>? = null
)

data class CurrentUserGroupsResponse(
    val success: Boolean,
    @SerializedName("data")
    val data: CurrentUserGroupsData? = null,
    val error: String? = null
)

data class SerialRuleResolutionResponse(
    val success: Boolean,
    @SerializedName("data")
    val data: SerialRuleResolutionData? = null,
    val error: String? = null
)

data class SerialRuleResolutionData(
    val serial: String? = null,
    val matches: List<SerialRuleResolutionMatch>? = null
)

data class SerialRuleResolutionMatch(
    val projectName: String? = null,
    val productType: String? = null,
    val prefix: String? = null,
    val length: Int? = null
)

data class CurrentUserGroupsData(
    val username: String? = null,
    @SerializedName("user_found")
    val userFound: Boolean? = null,
    @SerializedName("group_names")
    val groupNames: List<String>? = null,
    val groups: List<GroupInfo>? = null
)

data class GroupInfo(
    val id: String? = null,
    val name: String? = null,
    @SerializedName("display_name")
    val displayName: String? = null
)

data class ProjectConfigRequest(
    val projectName: String,
    val projectCode: String?,
    val productTypes: List<ProductTypeConfig>?,
    val processes: List<ProcessConfig>?,
    val version: Int?
)

// 产品记录
data class ProductRecordResponse(
    val success: Boolean,
    val record: ProductRecordData?,
    val exists: Boolean?
)

data class ProductRecordData(
    @SerializedName("product_serial")
    val productSerial: String,
    @SerializedName("product_type")
    val productType: String?,
    @SerializedName("project_name")
    val projectName: String?,
    val operator: String?,
    @SerializedName("scan_time")
    val scanTime: String?,
    // H2 API 返回 materials 作为 JSON 字符串
    val materials: String?,
    val components: List<ComponentData>?
)

data class ComponentData(
    val name: String,
    val serial: String?,
    val scanTime: String?
)

data class SaveProductRecordRequest(
    @SerializedName("product_serial")
    val productSerial: String,
    @SerializedName("product_type")
    val productType: String,
    @SerializedName("project_name")
    val projectName: String,
    val operator: String,
    @SerializedName("scan_time")
    val scanTime: String,
    val components: List<ComponentData>?,
    @SerializedName("allow_binding_update")
    val allowBindingUpdate: Boolean = false,
    // 将 components 转换为 materials 格式供服务端使用
    val materials: Map<String, String>? = null
)

data class SerialRecommendationResponse(
    val success: Boolean,
    val recommendation: SerialRecommendationData?,
    val message: String? = null
)

data class ApkLogUploadResponse(
    val success: Boolean,
    val message: String? = null,
    val record: ApkLogRecord? = null
)

data class ApkLogRecord(
    @SerializedName("stored_name")
    val storedName: String? = null,
    @SerializedName("original_filename")
    val originalFilename: String? = null,
    val username: String? = null,
    @SerializedName("uploaded_at")
    val uploadedAt: String? = null,
    @SerializedName("size_bytes")
    val sizeBytes: Long? = null,
    @SerializedName("app_version_name")
    val appVersionName: String? = null,
    @SerializedName("app_version_code")
    val appVersionCode: Int? = null,
    @SerializedName("device_model")
    val deviceModel: String? = null,
    val manufacturer: String? = null,
    @SerializedName("android_version")
    val androidVersion: String? = null
)

data class SerialRecommendationData(
    @SerializedName("product_serial")
    val productSerial: String,
    @SerializedName("recommended_project_name")
    val recommendedProjectName: String?,
    @SerializedName("recommended_product_type")
    val recommendedProductType: String?,
    val confidence: Double?,
    @SerializedName("should_confirm")
    val shouldConfirm: Boolean?,
    @SerializedName("auto_apply")
    val autoApply: Boolean?,
    val reason: String?,
    val candidates: List<SerialRecommendationCandidate>? = null
)

data class SerialRecommendationCandidate(
    @SerializedName("project_name")
    val projectName: String,
    @SerializedName("product_type")
    val productType: String,
    val confidence: Double? = null,
    val score: Double? = null,
    @SerializedName("evidence_count")
    val evidenceCount: Int? = null,
    @SerializedName("manual_confirm_count")
    val manualConfirmCount: Int? = null,
    @SerializedName("is_main_record")
    val isMainRecord: Boolean? = null,
    val source: String? = null
)

data class SerialLearningConfirmRequest(
    @SerializedName("product_serial")
    val productSerial: String,
    @SerializedName("project_name")
    val projectName: String,
    @SerializedName("product_type")
    val productType: String,
    val operator: String? = null,
    val source: String? = "manual_confirm",
    val conflict: Boolean? = null,
    val candidates: List<SerialRecommendationCandidate>? = null
)

data class SerialBindingRepairRequest(
    @SerializedName("product_serial")
    val productSerial: String,
    @SerializedName("project_name")
    val projectName: String,
    @SerializedName("product_type")
    val productType: String,
    val operator: String? = null,
    val source: String? = "manual_repair"
)

// 照片
data class PhotoUploadResponse(
    val success: Boolean,
    val filename: String?,
    val filePath: String?,
    val fileSize: Long?,
    val message: String?,
    val error: String?
)

data class MaterialInboundProcessStep(
    val name: String? = null,
    val description: String? = null,
    val order: Int? = null,
    val required: Boolean? = null,
)

data class MaterialInboundCandidate(
    val materialSerial: String? = null,
    val materialCode: String? = null,
    val materialName: String? = null,
    val projectName: String? = null,
    val projectCode: String? = null,
    val productType: String? = null,
    val matchedRule: String? = null,
    val processSteps: List<MaterialInboundProcessStep>? = null,
)

data class MaterialInboundResolveResponse(
    val success: Boolean,
    val materialSerial: String? = null,
    val materialCode: String? = null,
    val materialName: String? = null,
    val projectName: String? = null,
    val projectCode: String? = null,
    val productType: String? = null,
    val matched: Boolean = false,
    val matchSource: String? = null,
    val photoFolder: String? = null,
    val templateFolder: String? = null,
    val reportFolder: String? = null,
    val resultCount: Int? = null,
    val results: List<MaterialInboundCandidate>? = null,
    val error: String? = null
)

data class MaterialInboundConfirmRequest(
    val initialSerial: String,
    val confirmSerial: String,
    val materialCode: String,
    val materialName: String,
    val projectName: String,
    val productType: String,
)

data class MaterialInboundConfirmResponse(
    val success: Boolean,
    val message: String? = null,
    val error: String? = null,
    val materialSerial: String? = null,
    val materialCode: String? = null,
    val materialName: String? = null,
    val projectName: String? = null,
    val productType: String? = null,
    val processSteps: List<MaterialInboundProcessStep>? = null,
    val databaseFolder: String? = null,
    val databaseName: String? = null,
    val databasePath: String? = null,
)

data class MaterialInboundPhotoUploadResponse(
    val success: Boolean,
    val message: String? = null,
    val error: String? = null,
    val filename: String? = null,
    val filePath: String? = null,
    val folder: String? = null,
    val photoType: String? = null,
    val fileSize: Long? = null
)

data class MaterialInboundRecordRequest(
    val materialCode: String,
    val materialName: String,
    val quantity: String,
)

data class MaterialInboundRecordResponse(
    val success: Boolean,
    val message: String? = null,
    val error: String? = null,
    val recordId: Int? = null,
    val databaseFolder: String? = null,
    val databaseName: String? = null,
    val databasePath: String? = null,
    val recordDate: String? = null,
    val createdAt: String? = null,
)

data class PhotoMetadataRequest(
    val productSerial: String,
    val processStep: String?,
    val filePath: String?,
    val fileName: String,
    val fileSize: Long?,
    val capturedBy: String?,
    val metadata: Map<String, String>? = null
)

data class PhotoListResponse(
    val success: Boolean,
    val photos: List<PhotoInfo>?,
    val count: Int?
)

data class PhotoInfo(
    val fileName: String,
    val filePath: String?,
    val productSerial: String?,
    val processStep: String? = null,
    val captureTime: String?,
    val thumbnailUrl: String?,
    val fullUrl: String?
)

// 文档上传
data class DocumentUploadResponse(
    val success: Boolean,
    val filename: String?,
    val path: String?,
    val message: String?,
    val error: String?
)

// 文档列表
data class DocumentListResponse(
    val documents: List<DocumentInfo>
)

data class DocumentInfo(
    val filename: String,
    val path: String?,
    val size: Long = 0,
    val modified: String? = null,
    val processName: String? = null,
    val projectName: String? = null,
    val productType: String? = null,
    val productSerial: String? = null
)
