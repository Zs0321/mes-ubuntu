package com.testcenter.qrscanner.utils

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import org.json.JSONArray

class PreferencesManager(context: Context) {

    private val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()

    private val sharedPreferences: SharedPreferences = EncryptedSharedPreferences.create(
        context,
        "user_credentials",
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )

    companion object {
        private const val PREF_NAME = "QRTestScannerPrefs"
        private const val KEY_USERNAME = "username"
        private const val KEY_PASSWORD = "password"
        private const val KEY_IS_LOGGED_IN = "is_logged_in"
        private const val KEY_SELECTED_TESTER = "selected_tester"
        private const val KEY_SELECTED_PROJECT_PROCESS = "selected_project_process"
        private const val KEY_TESTERS_JSON = "testers_json"
        private const val KEY_SELECTED_PROJECT = "selected_project"
        private const val KEY_BACKEND = "backend_type" // value: "api"
        private const val KEY_DOMAIN = "domain"
        private const val KEY_REMEMBER_CREDENTIALS = "remember_credentials"
        private const val KEY_STORAGE_MODE = "storage_mode"
        private const val KEY_NETWORK_BASE_PATH = "network_base_path"
        private const val KEY_SYNOLOGY_URL = "synology_url"
        private const val KEY_WEBDAV_URL = "webdav_url"
        private const val KEY_ENABLE_SYNOLOGY_AUTH = "enable_synology_auth"
        private const val KEY_LAST_AUTH_METHOD = "last_auth_method"
        private const val KEY_API_BASE_URL = "api_base_url"

        private val DEFAULT_TESTERS = listOf("胡涛", "朱志强", "张三", "李四")
        private const val DEFAULT_SYNOLOGY_URL = "https://172.16.30.10:5001"
        private const val DEFAULT_WEBDAV_URL = "https://panovation.i234.me:5006"
        // 只使用内网 API，不使用外网反向代理
        private const val DEFAULT_API_URL = "http://172.16.30.10:8891"
        private const val EXTERNAL_API_URL = "http://221.226.60.30:8891"
    }

    /**
     * 数据存储模式（仅保留 API 模式）
     */
    enum class StorageMode {
        API_ONLY            // 仅API模式（默认）- 实时读写服务器数据库
    }

    fun saveCredentials(username: String, password: String, domain: String = "", rememberCredentials: Boolean = true) {
        with(sharedPreferences.edit()) {
            putString(KEY_USERNAME, username)
            // Always store password securely for background sync/auth.
            // The remember flag only controls whether we autofill the login UI, not storage.
            putString(KEY_PASSWORD, password)
            putString(KEY_DOMAIN, domain)
            putBoolean(KEY_IS_LOGGED_IN, true)
            putBoolean(KEY_REMEMBER_CREDENTIALS, rememberCredentials)
            apply()
        }
    }

    fun getUsername(): String? = sharedPreferences.getString(KEY_USERNAME, null)

    fun getPassword(): String? = sharedPreferences.getString(KEY_PASSWORD, null)

    fun getDomain(): String? = sharedPreferences.getString(KEY_DOMAIN, "")

    fun isLoggedIn(): Boolean = sharedPreferences.getBoolean(KEY_IS_LOGGED_IN, false)

    fun shouldRememberCredentials(): Boolean = sharedPreferences.getBoolean(KEY_REMEMBER_CREDENTIALS, true)

    fun logout() {
        with(sharedPreferences.edit()) {
            putBoolean(KEY_IS_LOGGED_IN, false)
            if (!shouldRememberCredentials()) {
                remove(KEY_PASSWORD)
            }
            apply()
        }
    }

    fun clearAllCredentials() {
        with(sharedPreferences.edit()) {
            clear()
            apply()
        }
    }

    // Tester list management
    fun getTesterList(): List<String> {
        val json = sharedPreferences.getString(KEY_TESTERS_JSON, null)
        if (json.isNullOrEmpty()) return DEFAULT_TESTERS
        return try {
            val arr = JSONArray(json)
            (0 until arr.length()).map { arr.getString(it) }
        } catch (_: Exception) {
            DEFAULT_TESTERS
        }
    }

    fun saveTesterList(testers: List<String>) {
        val arr = JSONArray()
        testers.forEach { arr.put(it) }
        with(sharedPreferences.edit()) {
            putString(KEY_TESTERS_JSON, arr.toString())
            apply()
        }
        // ensure selected tester still valid
        val selected = getSelectedTester()
        if (selected.isNullOrEmpty() || !testers.contains(selected)) {
            setSelectedTester(testers.firstOrNull() ?: "")
        }
    }

    fun getSelectedTester(): String? = sharedPreferences.getString(KEY_SELECTED_TESTER, getTesterList().firstOrNull())

    fun setSelectedTester(name: String) {
        with(sharedPreferences.edit()) {
            putString(KEY_SELECTED_TESTER, name)
            apply()
        }
    }

    // Backend selection
    fun getBackend(): String = "api"

    fun setBackend(value: String) {
        with(sharedPreferences.edit()) {
            putString(KEY_BACKEND, "api")
            apply()
        }
    }

    // Project management
    fun getSelectedProject(): String? = sharedPreferences.getString(KEY_SELECTED_PROJECT, null)

    fun setSelectedProject(projectName: String) {
        with(sharedPreferences.edit()) {
            putString(KEY_SELECTED_PROJECT, projectName)
            apply()
        }
    }

    fun getSelectedProcessProject(): String? = sharedPreferences.getString(KEY_SELECTED_PROJECT_PROCESS, null)

    fun setSelectedProcessProject(projectName: String) {
        with(sharedPreferences.edit()) {
            putString(KEY_SELECTED_PROJECT_PROCESS, projectName)
            apply()
        }
    }

    fun clearSelectedProcessProject() {
        with(sharedPreferences.edit()) {
            remove(KEY_SELECTED_PROJECT_PROCESS)
            apply()
        }
    }

    // Storage mode management
    fun getStorageMode(): StorageMode {
        val modeName = sharedPreferences.getString(KEY_STORAGE_MODE, StorageMode.API_ONLY.name)
        return try {
            StorageMode.valueOf(modeName ?: StorageMode.API_ONLY.name)
        } catch (e: Exception) {
            StorageMode.API_ONLY
        }
    }

    fun setStorageMode(mode: StorageMode) {
        with(sharedPreferences.edit()) {
            putString(KEY_STORAGE_MODE, mode.name)
            apply()
        }
    }

    // Network path management
    fun getNetworkBasePath(): String? = sharedPreferences.getString(KEY_NETWORK_BASE_PATH, null)

    fun setNetworkBasePath(path: String) {
        with(sharedPreferences.edit()) {
            putString(KEY_NETWORK_BASE_PATH, path)
            apply()
        }
    }

    // Generic getter/setter for counters
    fun getInt(key: String, defaultValue: Int = 0): Int {
        return sharedPreferences.getInt(key, defaultValue)
    }

    fun putInt(key: String, value: Int) {
        with(sharedPreferences.edit()) {
            putInt(key, value)
            apply()
        }
    }

    // Generic getter/setter for strings
    fun getString(key: String, defaultValue: String): String {
        return sharedPreferences.getString(key, defaultValue) ?: defaultValue
    }

    fun putString(key: String, value: String) {
        with(sharedPreferences.edit()) {
            putString(key, value)
            apply()
        }
    }

    // Synology configuration management
    fun getSynologyUrl(): String {
        return sharedPreferences.getString(KEY_SYNOLOGY_URL, DEFAULT_SYNOLOGY_URL) ?: DEFAULT_SYNOLOGY_URL
    }

    fun setSynologyUrl(url: String) {
        with(sharedPreferences.edit()) {
            putString(KEY_SYNOLOGY_URL, url)
            apply()
        }
    }

    fun isSynologyAuthEnabled(): Boolean {
        return sharedPreferences.getBoolean(KEY_ENABLE_SYNOLOGY_AUTH, false)
    }

    fun setSynologyAuthEnabled(enabled: Boolean) {
        with(sharedPreferences.edit()) {
            putBoolean(KEY_ENABLE_SYNOLOGY_AUTH, enabled)
            apply()
        }
    }

    // WebDAV configuration management
    fun getWebDavUrl(): String {
        return sharedPreferences.getString(KEY_WEBDAV_URL, DEFAULT_WEBDAV_URL) ?: DEFAULT_WEBDAV_URL
    }

    fun setWebDavUrl(url: String) {
        with(sharedPreferences.edit()) {
            putString(KEY_WEBDAV_URL, url)
            apply()
        }
    }

    // Authentication method tracking
    fun getLastAuthMethod(): String? {
        return sharedPreferences.getString(KEY_LAST_AUTH_METHOD, null)
    }

    fun setLastAuthMethod(method: String) {
        with(sharedPreferences.edit()) {
            putString(KEY_LAST_AUTH_METHOD, method)
            apply()
        }
    }

    // API Base URL management
    /**
     * 获取 API 基础 URL
     *
     * 固定使用内网 API: http://172.16.30.10:8891
     *
     * @return API 基础 URL（不含尾部斜杠）
     */
    // Default internal API stays on 172.16.30.10.
    fun getDefaultApiBaseUrl(): String = DEFAULT_API_URL

    fun getInternalApiBaseUrl(): String = DEFAULT_API_URL

    fun getExternalApiBaseUrl(): String = EXTERNAL_API_URL

    fun getApiBaseUrl(): String {
        val customUrl = sharedPreferences.getString(KEY_API_BASE_URL, null)?.trimEnd('/')
        if (!customUrl.isNullOrBlank()) {
            return customUrl
        }
        return DEFAULT_API_URL
    }

    fun isExternalApiUrl(url: String?): Boolean {
        if (url.isNullOrBlank()) {
            return false
        }
        return url.trimEnd('/') == EXTERNAL_API_URL
    }

    /**
     * ????? API ?? URL
     *
     * @param url ??? API URL??????????
     */
    fun setApiBaseUrl(url: String) {
        val normalized = url.trimEnd('/')
        with(sharedPreferences.edit()) {
            if (normalized.isBlank()) {
                remove(KEY_API_BASE_URL)
            } else {
                putString(KEY_API_BASE_URL, normalized)
            }
            apply()
        }
    }

    /**
     * 清除自定义 API URL，恢复自动判断
     */
    fun clearApiBaseUrl() {
        with(sharedPreferences.edit()) {
            remove(KEY_API_BASE_URL)
            apply()
        }
    }

    /**
     * 检查是否使用自定义 API URL
     */
    fun hasCustomApiUrl(): Boolean {
        return !sharedPreferences.getString(KEY_API_BASE_URL, null).isNullOrBlank()
    }

    /**
     * 缓存用户权限信息
     *
     * @param role 用户角色
     * @param permissionsJson 权限 JSON 字符串
     * @param timestamp 缓存时间戳
     */
    fun cacheUserPermissions(role: String, permissionsJson: String, timestamp: Long) {
        with(sharedPreferences.edit()) {
            putString("cached_user_role", role)
            putString("cached_permissions_json", permissionsJson)
            putLong("cached_permissions_timestamp", timestamp)
            apply()
        }
    }

    /**
     * 获取缓存的用户角色
     */
    fun getCachedUserRole(): String? {
        return sharedPreferences.getString("cached_user_role", null)
    }

    /**
     * 获取缓存的权限 JSON
     */
    fun getCachedPermissionsJson(): String? {
        return sharedPreferences.getString("cached_permissions_json", null)
    }

    /**
     * 获取权限缓存时间戳
     */
    fun getCachedPermissionsTimestamp(): Long {
        return sharedPreferences.getLong("cached_permissions_timestamp", 0L)
    }

    /**
     * 清除权限缓存
     */
    fun clearPermissionsCache() {
        with(sharedPreferences.edit()) {
            remove("cached_user_role")
            remove("cached_permissions_json")
            remove("cached_permissions_timestamp")
            apply()
        }
    }
}
