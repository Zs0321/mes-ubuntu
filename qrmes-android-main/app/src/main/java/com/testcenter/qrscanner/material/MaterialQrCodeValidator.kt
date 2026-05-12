package com.testcenter.qrscanner.material

import com.testcenter.qrscanner.adapter.Component
import com.testcenter.qrscanner.data.MaterialInfo
import java.util.Locale

object MaterialQrCodeValidator {

    private const val DEFAULT_PCB_VERSION_LENGTH = 2

    data class ValidationResult(
        val isValid: Boolean,
        val message: String? = null,
        val detectedVersion: String? = null
    )

    fun validate(
        material: MaterialInfo,
        scannedCode: String,
        forceVersionCheck: Boolean = false
    ): ValidationResult {
        val normalizedCode = normalize(scannedCode)
        if (normalizedCode.isEmpty()) {
            return ValidationResult(false, "扫描内容为空")
        }

        return when (material.normalizedQrRuleType()) {
            MaterialInfo.QR_RULE_PCB -> validatePcbMaterial(material, normalizedCode, forceVersionCheck)
            else -> validateMotorMaterial(material, forceVersionCheck)
        }
    }

    fun validate(component: Component, scannedCode: String): ValidationResult {
        return validate(
            material = MaterialInfo(
                name = component.name,
                partNumber = component.partNumber,
                qrRuleType = component.qrRuleType,
                expectedVersion = component.expectedVersion
            ),
            scannedCode = scannedCode,
            forceVersionCheck = component.forceVersionCheck
        )
    }

    private fun validateMotorMaterial(
        material: MaterialInfo,
        forceVersionCheck: Boolean
    ): ValidationResult {
        val configuredVersion = material.normalizedExpectedVersion()
        if (configuredVersion.isNotEmpty()) {
            return ValidationResult(false, "物料 ${material.name} 使用电机二维码规则，暂不支持版本号检查")
        }
        if (!forceVersionCheck) {
            return ValidationResult(true)
        }
        return ValidationResult(false, "物料 ${material.name} 未配置版本号，已启用强制版本检查")
    }

    private fun validatePcbMaterial(
        material: MaterialInfo,
        scannedCode: String,
        forceVersionCheck: Boolean
    ): ValidationResult {
        val partNumber = normalize(material.partNumber)
        val materialCode = partNumber.substringBefore('.', missingDelimiterValue = partNumber)
        if (materialCode.isNotEmpty() && !matchesPcbMaterialCode(scannedCode, materialCode)) {
            return ValidationResult(false, "物料编码不匹配，应为 $materialCode")
        }

        val configuredVersion = material.normalizedExpectedVersion()
        if (configuredVersion.isEmpty() && !forceVersionCheck) {
            return ValidationResult(true)
        }
        if (configuredVersion.isEmpty()) {
            return ValidationResult(false, "物料 ${material.name} 未配置版本号，已启用强制版本检查")
        }

        val detectedVersion = parsePcbVersion(scannedCode, configuredVersion.length)
            ?: return ValidationResult(false, "未识别到二维码中的版本号")

        return if (detectedVersion.equals(configuredVersion, ignoreCase = true)) {
            ValidationResult(true, detectedVersion = detectedVersion)
        } else {
            ValidationResult(
                false,
                "版本不匹配，应为 $configuredVersion，实际为 $detectedVersion",
                detectedVersion = detectedVersion
            )
        }
    }

    private fun parsePcbVersion(scannedCode: String, configuredVersionLength: Int): String? {
        val separatorIndex = scannedCode.indexOfFirst { it == '.' || it == '-' || it == '_' }
        if (separatorIndex < 0 || separatorIndex == scannedCode.lastIndex) {
            return null
        }
        val suffix = scannedCode.substring(separatorIndex + 1)
        if (suffix.isBlank()) {
            return null
        }
        val versionLength = configuredVersionLength.takeIf { it > 0 } ?: DEFAULT_PCB_VERSION_LENGTH
        if (suffix.length < versionLength) {
            return null
        }
        return suffix.substring(0, versionLength)
    }

    private fun normalize(value: String): String {
        return value.trim().uppercase(Locale.ROOT)
    }

    private fun matchesPcbMaterialCode(scannedCode: String, materialCode: String): Boolean {
        if (!scannedCode.startsWith(materialCode, ignoreCase = true)) {
            return false
        }
        if (scannedCode.length == materialCode.length) {
            return true
        }
        val nextChar = scannedCode[materialCode.length]
        return nextChar == '.' || nextChar == '-' || nextChar == '_'
    }
}
