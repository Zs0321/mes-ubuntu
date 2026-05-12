package com.testcenter.qrscanner.utils

import java.util.Locale

/**
 * 解析工序照片文件名:
 * 1) {serial}_{process}_{yyyyMMdd_HHmmss}.jpg
 * 2) {serial}_{process}_{yyyyMMdd_HHmmss}_{seq}.jpg
 */
object ProcessPhotoFileNameParser {

    private val tailPattern = Regex("_(\\d{8}_\\d{6})(?:_\\d+)?(?:\\.[^.]+)?$", RegexOption.IGNORE_CASE)
    private val sanitizePattern = Regex("[^\\p{L}\\p{N}_-]")
    private val normalizePattern = Regex("[^\\p{L}\\p{N}]")

    fun extractProcessName(serial: String, fileName: String): String? {
        val serialPrefixes = buildSerialPrefixes(serial)
        val matchedPrefix = serialPrefixes.firstOrNull { fileName.startsWith(it) } ?: return null
        val rest = fileName.removePrefix(matchedPrefix)
        val match = tailPattern.find(rest) ?: return null
        if (match.range.first <= 0) return null
        val processName = rest.substring(0, match.range.first).trim('_', '-', ' ')
        return processName.takeIf { it.isNotEmpty() }
    }

    fun normalizeForMatch(value: String): String {
        return value
            .lowercase(Locale.ROOT)
            .replace(normalizePattern, "")
    }

    private fun buildSerialPrefixes(serial: String): List<String> {
        val raw = serial.trim()
        val sanitized = raw.replace(sanitizePattern, "_")
        return linkedSetOf("${raw}_", "${sanitized}_")
            .filter { it != "_" }
            .toList()
    }
}
