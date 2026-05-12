package com.testcenter.qrscanner.database

import android.content.Context
import com.testcenter.qrscanner.data.ProductRecord
import com.testcenter.qrscanner.utils.ProjectManager
import com.testcenter.qrscanner.utils.ProjectConfigManager
import com.testcenter.qrscanner.utils.PreferencesManager
import com.testcenter.qrscanner.utils.AppLogger

/**
 * 数据验证器
 * 在保存到数据库前验证数据的完整性和引用正确性
 */
class DataValidator(private val context: Context) {
    
    private val projectManager = ProjectManager(context)
    private val projectConfigManager = ProjectConfigManager(context)
    private val preferencesManager = PreferencesManager(context)
    
    companion object {
        private const val TAG = "DataValidator"
    }
    
    /**
     * 验证结果
     */
    data class ValidationResult(
        val isValid: Boolean,
        val errors: List<String> = emptyList(),
        val warnings: List<String> = emptyList()
    ) {
        fun hasErrors() = errors.isNotEmpty()
        fun hasWarnings() = warnings.isNotEmpty()
    }
    
    /**
     * 验证产品记录
     */
    fun validateProductRecord(record: ProductRecord): ValidationResult {
        val errors = mutableListOf<String>()
        val warnings = mutableListOf<String>()
        
        // 1. 验证必填字段
        if (record.productSerial.isBlank()) {
            errors.add("产品序列号不能为空")
        }
        
        if (record.productType.isBlank()) {
            errors.add("产品类型不能为空")
        }
        
        if (record.projectName.isBlank()) {
            errors.add("项目名称不能为空")
        }
        
        if (record.operator.isBlank()) {
            errors.add("操作员不能为空")
        }
        
        // 2. 验证项目是否存在
        val projects = projectManager.getProjectList()
        if (!projects.contains(record.projectName)) {
            errors.add("项目 '${record.projectName}' 不存在")
        }
        
        // 3. 验证产品类型是否存在
        if (record.projectName.isNotBlank()) {
            val projectConfig = projectConfigManager.loadProjectConfig(record.projectName)
            if (projectConfig == null) {
                errors.add("项目 '${record.projectName}' 的配置不存在")
            } else {
                val productTypes = projectConfig.productTypes.map { it.typeName }
                
                if (!productTypes.contains(record.productType)) {
                    errors.add("产品类型 '${record.productType}' 在项目 '${record.projectName}' 中不存在")
                } else {
                    // 4. 验证物料是否匹配配置
                    val productTypeConfig = projectConfig.getProductTypeConfig(record.productType)
                if (productTypeConfig != null) {
                    val configuredMaterials = productTypeConfig.materials.map { it.name }.toSet()
                    val recordMaterials = record.materials.keys
                    
                    // 检查是否有配置中没有的物料
                    val extraMaterials = recordMaterials - configuredMaterials
                    if (extraMaterials.isNotEmpty()) {
                        warnings.add("记录包含未配置的物料: ${extraMaterials.joinToString(", ")}")
                    }
                    
                    // 检查是否缺少必需的物料（可选检查）
                    val missingMaterials = configuredMaterials - recordMaterials.toSet()
                    if (missingMaterials.isNotEmpty()) {
                        warnings.add("记录缺少配置的物料: ${missingMaterials.joinToString(", ")}")
                    }
                }
                }
            }
        }
        
        // 5. 验证操作员是否存在
        val testers = preferencesManager.getTesterList()
        if (!testers.contains(record.operator)) {
            warnings.add("操作员 '${record.operator}' 不在人员列表中")
        }
        
        // 6. 验证时间戳
        if (record.scanTime <= 0) {
            errors.add("扫描时间无效")
        }
        
        val result = ValidationResult(
            isValid = errors.isEmpty(),
            errors = errors,
            warnings = warnings
        )
        
        if (result.hasErrors()) {
            AppLogger.log(TAG, "Validation failed for ${record.productSerial}: ${errors.joinToString("; ")}")
        }
        
        if (result.hasWarnings()) {
            AppLogger.log(TAG, "Validation warnings for ${record.productSerial}: ${warnings.joinToString("; ")}")
        }
        
        return result
    }
    
    /**
     * 验证并修复（尽可能）
     */
    fun validateAndFix(record: ProductRecord): Pair<ProductRecord, ValidationResult> {
        val result = validateProductRecord(record)
        
        if (result.isValid) {
            return Pair(record, result)
        }
        
        // 尝试修复一些问题
        var fixedRecord = record
        
        // 修复空白操作员（使用当前选中的）
        if (fixedRecord.operator.isBlank()) {
            val currentOperator = preferencesManager.getSelectedTester()
            if (currentOperator != null) {
                fixedRecord = fixedRecord.copy(operator = currentOperator)
            }
        }
        
        // 修复无效时间戳
        if (fixedRecord.scanTime <= 0) {
            fixedRecord = fixedRecord.copy(scanTime = System.currentTimeMillis())
        }
        
        // 重新验证
        val newResult = validateProductRecord(fixedRecord)
        return Pair(fixedRecord, newResult)
    }
}
