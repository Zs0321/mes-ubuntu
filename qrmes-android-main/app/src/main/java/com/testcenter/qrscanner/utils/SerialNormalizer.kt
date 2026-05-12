package com.testcenter.qrscanner.utils

/**
 * Normalize scanned/manual serial values before API lookup/save.
 * Removes ASCII control chars (e.g. CR/LF) and trims leading/trailing spaces.
 */
object SerialNormalizer {
    private val controlChars = Regex("[\\u0000-\\u001F\\u007F]")

    fun normalize(raw: String?): String {
        if (raw == null) return ""
        return raw.replace(controlChars, "").trim()
    }
}
