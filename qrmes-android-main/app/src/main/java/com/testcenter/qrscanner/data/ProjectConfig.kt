package com.testcenter.qrscanner.data

import com.google.gson.Gson
import com.google.gson.JsonDeserializationContext
import com.google.gson.JsonDeserializer
import com.google.gson.JsonElement
import com.google.gson.JsonParseException
import com.google.gson.JsonPrimitive
import com.google.gson.JsonSerializationContext
import com.google.gson.JsonSerializer
import com.google.gson.annotations.SerializedName
import com.google.gson.annotations.JsonAdapter
import java.lang.reflect.Type
import java.time.Instant
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * 物料信息
 */
data class MaterialInfo(
    @SerializedName("name")
    val name: String,           // 物料名称，如"控制板"
    
    @SerializedName("partNumber")
    val partNumber: String,     // 物料编号，如"U12020034.A0"

    @SerializedName("qrRuleType")
    val qrRuleType: String = QR_RULE_MOTOR,

    @SerializedName("expectedVersion")
    val expectedVersion: String = ""
) {
    fun normalizedQrRuleType(): String {
        return if (qrRuleType.equals(QR_RULE_PCB, ignoreCase = true)) {
            QR_RULE_PCB
        } else {
            QR_RULE_MOTOR
        }
    }

    fun normalizedExpectedVersion(): String {
        return expectedVersion.trim().uppercase()
    }

    companion object {
        const val QR_RULE_MOTOR = "motor"
        const val QR_RULE_PCB = "pcb"
    }
}

/**
 * 工序步骤信息
 */
data class ProcessStep(
    @SerializedName("id")
    val id: String,                     // 工序ID，如"process_001"
    
    @SerializedName("name")
    val name: String,                   // 工序名称，如"热套工序"
    
    @SerializedName("description")
    val description: String,            // 工序描述
    
    @SerializedName("order")
    val order: Int,                     // 工序顺序
    
    @SerializedName("productType")
    val productType: String = "",       // 关联的产品类型名称
    
    @SerializedName("required")
    val required: Boolean = true,       // 是否必需
    
    @SerializedName("photoRequired")
    val photoRequired: Boolean = true,  // 是否需要拍照
    
    @SerializedName("estimatedDuration")
    val estimatedDuration: Int = 0,      // 预计耗时（秒）

    @SerializedName("attachmentType")
    val attachmentType: String = "photo",  // 附件类型: "photo" / "pdf" / "both"

    @SerializedName(value = "responsibleDepartments", alternate = ["responsible_departments"])
    val responsibleDepartments: List<String> = emptyList()  // 责任部门（群组名）
)

/**
 * 产品类型配置
 */
data class ProductTypeConfig(
    @SerializedName("typeName")
    val typeName: String,                       // 产品类型名称，如"电机控制器"
    
    @SerializedName("modelNumber")
    val modelNumber: String = "",              // 产品型号，如"MCU-V3.2" (Schema 2.1新增)

    @SerializedName(value = "serialRules", alternate = ["serial_rules", "serialPrefixes", "serial_prefixes"])
    val serialRules: List<String> = emptyList(), // 可选：二维码前缀规则

    @SerializedName("forceVersionCheck")
    val forceVersionCheck: Boolean = false,
    
    @SerializedName("materials")
    val materials: MutableList<MaterialInfo>,   // 该产品类型包含的物料列表
    
    @SerializedName("processSteps")
    var processSteps: MutableList<ProcessStep>? = null // 该产品类型的工序步骤列表（可选字段，向后兼容）
) {
    /**
     * 安全获取工序步骤列表，如果为null则返回空列表
     */
    fun safeGetProcessSteps(): List<ProcessStep> {
        return processSteps ?: emptyList()
    }

    fun getDisplayName(): String {
        return if (modelNumber.isNotBlank()) {
            "$typeName ($modelNumber)"
        } else {
            typeName
        }
    }
}

/**
 * 项目配置
 */
data class ProjectConfig(
    @SerializedName("projectName")
    val projectName: String,                                // 项目名称
    
    @SerializedName("projectCode")
    val projectCode: String = "",                          // 项目号，如"LG-WLY-001" (Schema 2.1新增)
    
    @SerializedName("productTypes")
    val productTypes: MutableList<ProductTypeConfig>,       // 该项目支持的产品类型列表
    
    @SerializedName("processSteps")
    var processSteps: MutableList<ProcessStep>? = null, // 工序步骤列表（旧版本兼容，新版本应使用产品类型中的processSteps）
    
    @SerializedName("schemaVersion")
    val schemaVersion: String = "1.0",                      // 数据结构版本，用于版本识别和迁移
    
    @SerializedName("version")
    val version: Int = 1,                                   // 配置版本号
    
    @SerializedName("lastModified")
    @JsonAdapter(FlexibleLongAdapter::class)
    val lastModified: Long = System.currentTimeMillis()     // 最后修改时间戳
) {
    init {
        // 确保 processSteps 永远不会是 null（用于向后兼容）
        if (processSteps == null) {
            processSteps = mutableListOf()
        }
    }
    
    companion object {
        /**
         * 创建默认项目配置
         */
        fun createDefault(projectName: String): ProjectConfig {
            // 默认物料列表（电机控制器和电机通用）
            val defaultMaterials = mutableListOf(
                MaterialInfo("控制板", "U12020034.A0", qrRuleType = MaterialInfo.QR_RULE_PCB),
                MaterialInfo("左侧电容板", "W12020035.A0", qrRuleType = MaterialInfo.QR_RULE_PCB),
                MaterialInfo("右侧电容板", "W12020035.A0", qrRuleType = MaterialInfo.QR_RULE_PCB),
                MaterialInfo("左侧功率板", "U12020036.A0", qrRuleType = MaterialInfo.QR_RULE_PCB),
                MaterialInfo("右侧功率板", "U12020036.A0", qrRuleType = MaterialInfo.QR_RULE_PCB)
            )
            
            // 默认工序步骤（电机控制器）
            val motorControllerProcessSteps = mutableListOf(
                ProcessStep("process_001", "热套工序", "热套装配工序", 1, "电机控制器", true, true, 300),
                ProcessStep("process_002", "总装工序", "最终总装工序", 2, "电机控制器", true, true, 600)
            )
            
            // 默认工序步骤（电机）
            val motorProcessSteps = mutableListOf(
                ProcessStep("process_003", "热套工序", "热套装配工序", 1, "电机", true, true, 300),
                ProcessStep("process_004", "总装工序", "最终总装工序", 2, "电机", true, true, 600)
            )
            
            // 默认产品类型（新版本2.0结构）
            val productTypes = mutableListOf(
                ProductTypeConfig(
                    typeName = "电机控制器",
                    modelNumber = "MCU-V1.0",
                    materials = defaultMaterials.map { it.copy() }.toMutableList(),
                    processSteps = motorControllerProcessSteps
                ),
                ProductTypeConfig(
                    typeName = "电机",
                    modelNumber = "MOTOR-V1.0",
                    materials = defaultMaterials.map { it.copy() }.toMutableList(),
                    processSteps = motorProcessSteps
                )
            )
            
            return ProjectConfig(
                projectName = projectName,
                projectCode = "",  // Schema 2.1新增字段，默认为空
                productTypes = productTypes,
                processSteps = mutableListOf(), // 新版本不使用顶层processSteps
                schemaVersion = "2.1",  // 升级到Schema 2.1
                version = 1,
                lastModified = System.currentTimeMillis()
            )
        }
        
        /**
         * 从JSON字符串解析
         */
        fun fromJson(json: String): ProjectConfig {
            return Gson().fromJson(json, ProjectConfig::class.java)
        }
    }
    
    /**
     * 转换为JSON字符串
     */
    fun toJson(): String {
        return Gson().toJson(this)
    }
    
    /**
     * 获取指定产品类型的配置
     */
    fun getProductTypeConfig(typeName: String): ProductTypeConfig? {
        return productTypes.find { it.typeName == typeName }
    }
    
    /**
     * 创建新版本（版本号+1）
     */
    fun createNewVersion(): ProjectConfig {
        return this.copy(
            version = this.version + 1,
            lastModified = System.currentTimeMillis()
        )
    }
    
    /**
     * 检查是否比另一个配置更新
     */
    fun isNewerThan(other: ProjectConfig?): Boolean {
        if (other == null) return true
        if (this.version > other.version) return true
        if (this.version == other.version && this.lastModified > other.lastModified) return true
        return false
    }
}

class FlexibleLongAdapter : JsonDeserializer<Long>, JsonSerializer<Long> {
    override fun deserialize(json: JsonElement?, typeOfT: Type?, context: JsonDeserializationContext?): Long {
        if (json == null || json.isJsonNull) {
            return System.currentTimeMillis()
        }

        val primitive = json.asJsonPrimitive ?: return System.currentTimeMillis()
        return when {
            primitive.isNumber -> primitive.asLong
            primitive.isString -> parseFlexibleTimestamp(primitive.asString)
            else -> System.currentTimeMillis()
        }
    }

    override fun serialize(src: Long?, typeOfSrc: Type?, context: JsonSerializationContext?): JsonElement {
        return JsonPrimitive(src ?: System.currentTimeMillis())
    }

    private fun parseFlexibleTimestamp(raw: String): Long {
        val value = raw.trim()
        if (value.isEmpty()) {
            return System.currentTimeMillis()
        }

        value.toLongOrNull()?.let { return it }

        return try {
            Instant.parse(value).toEpochMilli()
        } catch (_: Exception) {
            try {
                OffsetDateTime.parse(value, DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant().toEpochMilli()
            } catch (_: Exception) {
                try {
                    LocalDateTime.parse(value, DateTimeFormatter.ISO_LOCAL_DATE_TIME)
                        .atZone(ZoneId.systemDefault())
                        .toInstant()
                        .toEpochMilli()
                } catch (e: Exception) {
                    throw JsonParseException("Unsupported timestamp format: $value", e)
                }
            }
        }
    }
}
