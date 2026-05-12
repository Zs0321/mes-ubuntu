package com.testcenter.qrscanner.quality

import android.content.Context
import com.bumptech.glide.load.model.GlideUrl
import com.bumptech.glide.load.model.LazyHeaders
import com.testcenter.qrscanner.utils.PreferencesManager
import okhttp3.Credentials
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

object QualityPhotoRequestFactory {

    fun buildModel(
        context: Context,
        photo: QualityPhotoDto,
        preferThumbnail: Boolean = false
    ): Any? {
        val rawUrl = if (preferThumbnail) {
            photo.thumbnailUrl.ifBlank { photo.url }
        } else {
            photo.url.ifBlank { photo.thumbnailUrl }
        }
        val absoluteUrl = resolveUrl(context, rawUrl)
        if (absoluteUrl.isBlank()) {
            return null
        }
        if (!isTrustedApiUrl(context, absoluteUrl)) {
            return null
        }

        val preferencesManager = PreferencesManager(context)
        val username = preferencesManager.getUsername()
        val password = preferencesManager.getPassword()
        if (!username.isNullOrBlank() && !password.isNullOrBlank()) {
            val headers = LazyHeaders.Builder()
                .addHeader("Authorization", Credentials.basic(username, password))
                .build()
            return GlideUrl(absoluteUrl, headers)
        }
        return absoluteUrl
    }

    fun resolveUrl(context: Context, rawUrl: String?): String {
        val candidate = rawUrl?.trim().orEmpty()
        if (candidate.isBlank()) {
            return ""
        }
        if (candidate.startsWith("http://") || candidate.startsWith("https://")) {
            return candidate
        }

        val baseUrl = PreferencesManager(context).getApiBaseUrl().trim()
        if (baseUrl.isBlank()) {
            return ""
        }

        return when {
            candidate.startsWith("/") -> baseUrl.trimEnd('/') + candidate
            else -> baseUrl.trimEnd('/') + "/" + candidate.trimStart('/')
        }
    }

    internal fun isSameOrigin(baseUrl: String, targetUrl: String): Boolean {
        val base = baseUrl.trim().toHttpUrlOrNull() ?: return false
        val target = targetUrl.trim().toHttpUrlOrNull() ?: return false
        return base.scheme.equals(target.scheme, ignoreCase = true) &&
            base.host.equals(target.host, ignoreCase = true) &&
            base.port == target.port
    }

    private fun isTrustedApiUrl(context: Context, absoluteUrl: String): Boolean {
        if (!absoluteUrl.startsWith("http://") && !absoluteUrl.startsWith("https://")) {
            return false
        }
        val baseUrl = PreferencesManager(context).getApiBaseUrl().trim()
        if (baseUrl.isBlank()) {
            return false
        }
        return isSameOrigin(baseUrl, absoluteUrl)
    }
}
