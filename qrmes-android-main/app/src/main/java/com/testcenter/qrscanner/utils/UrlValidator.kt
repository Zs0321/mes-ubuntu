package com.testcenter.qrscanner.utils

import java.net.URL

/**
 * Utility object for validating Synology server URLs.
 * Ensures URLs follow the correct format for DSM API endpoints.
 */
object UrlValidator {

    /**
     * Validates a Synology server URL.
     * 
     * @param url The URL string to validate
     * @return ValidationResult containing validation status and error message if invalid
     */
    fun validateSynologyUrl(url: String): ValidationResult {
        // Check if URL is blank
        if (url.isBlank()) {
            return ValidationResult(false, "URL不能为空")
        }

        // Check if URL starts with http:// or https://
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            return ValidationResult(false, "URL必须以http://或https://开头")
        }

        // Parse and validate URL structure
        try {
            val uri = URL(url)
            
            // Check if host is present
            if (uri.host.isNullOrBlank()) {
                return ValidationResult(false, "无效的主机地址")
            }
            
            // Check if port is specified
            if (uri.port == -1) {
                return ValidationResult(false, "请指定端口号 (例如: :5001)")
            }
            
        } catch (e: Exception) {
            return ValidationResult(false, "URL格式错误: ${e.message}")
        }

        // All validations passed
        return ValidationResult(true, "")
    }

    /**
     * Validates a WebDAV server URL.
     * 
     * @param url The URL string to validate
     * @return ValidationResult containing validation status and error message if invalid
     */
    fun validateWebDavUrl(url: String): ValidationResult {
        // Check if URL is blank
        if (url.isBlank()) {
            return ValidationResult(false, "WebDAV地址不能为空")
        }

        // Check if URL starts with http:// or https://
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            return ValidationResult(false, "WebDAV地址必须以http://或https://开头")
        }

        // Parse and validate URL structure
        try {
            val uri = java.net.URI(url)
            
            // Check if host is present
            if (uri.host.isNullOrBlank()) {
                return ValidationResult(false, "WebDAV地址格式无效")
            }
            
        } catch (e: Exception) {
            return ValidationResult(false, "WebDAV地址格式无效: ${e.message}")
        }

        // All validations passed
        return ValidationResult(true, "")
    }

    /**
     * Data class representing the result of URL validation.
     * 
     * @property isValid True if the URL is valid, false otherwise
     * @property errorMessage Error message describing why validation failed (empty if valid)
     */
    data class ValidationResult(
        val isValid: Boolean,
        val errorMessage: String
    )
}
