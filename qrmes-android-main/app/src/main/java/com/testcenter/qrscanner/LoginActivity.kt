package com.testcenter.qrscanner

import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.util.Log
import com.testcenter.qrscanner.BuildConfig
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import com.google.android.material.snackbar.Snackbar
import com.testcenter.qrscanner.auth.AuthenticationService
import com.testcenter.qrscanner.auth.LocalUserManager
import com.testcenter.qrscanner.databinding.ActivityLoginBinding
import com.testcenter.qrscanner.network.FileManagerFactory
import com.testcenter.qrscanner.update.ApkUpdateManager
import com.testcenter.qrscanner.utils.PreferencesManager
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.UrlValidator
import com.testcenter.qrscanner.utils.ErrorMessages
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Authentication method enum.
 */
enum class AuthMethod {
    API,
    SYNOLOGY,
    WEBDAV,
    SMB
}

/**
 * Authentication result sealed class.
 */
sealed class AuthenticationResult {
    data class Success(
        val user: com.testcenter.qrscanner.auth.LocalUserManager.LocalUser?,
        val method: AuthMethod
    ) : AuthenticationResult()

    data class PasswordChangeRequired(
        val username: String,
        val currentPassword: String,
        val message: String
    ) : AuthenticationResult()

    data class Failure(
        val error: String,
        val failedMethod: AuthMethod?,
        val canRetry: Boolean
    ) : AuthenticationResult()
}

class LoginActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLoginBinding
    private var preferencesManager: PreferencesManager? = null // Made nullable
    private var preferencesManagerInitialized = false
    private lateinit var authenticationService: AuthenticationService
    private var isSynologyUrlValid = true // Track URL validation state

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 强制使用白天模式
        androidx.appcompat.app.AppCompatDelegate.setDefaultNightMode(
            androidx.appcompat.app.AppCompatDelegate.MODE_NIGHT_NO
        )

        if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "onCreate - START")

        try {
            AppLogger.init(applicationContext)
            AppLogger.log("LoginActivity", "onCreate - AppLogger initialized.")
            if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "onCreate - AppLogger initialized.")
        } catch (e: Exception) {
            if (BuildConfig.DEBUG) Log.e("LoginActivityDebug", "AppLogger.init failed", e)
        }

        val originalHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            AppLogger.log("Uncaught", "Thread=${t.name} crashed: ${e.message}", e)
            if (BuildConfig.DEBUG) Log.e("LoginActivityDebug", "Uncaught exception in thread ${t.name}", e)
            originalHandler?.uncaughtException(t, e)
        }

        AppLogger.log("LoginActivity", "onCreate - Inflating layout.")
        if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "onCreate - Inflating layout.")
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)
        binding.tvVersionWatermark.text = ApkUpdateManager.formatWatermarkLabel(
            BuildConfig.VERSION_NAME,
            BuildConfig.VERSION_CODE
        )
        AppLogger.log("LoginActivity", "onCreate - Layout inflated and contentView set.")
        if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "onCreate - Layout inflated and contentView set.")

        // Initialize AuthenticationService
        AppLogger.log("LoginActivity", "onCreate - Initializing AuthenticationService.")
        if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "onCreate - Initializing AuthenticationService.")
        try {
            authenticationService = AuthenticationService(this)
            AppLogger.log("LoginActivity", "onCreate - AuthenticationService initialized successfully.")
            if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "onCreate - AuthenticationService initialized successfully.")
        } catch (e: Exception) {
            AppLogger.log("LoginActivity", "onCreate - AuthenticationService initialization FAILED: ${e.message}", e)
            if (BuildConfig.DEBUG) Log.e("LoginActivityDebug", "onCreate - AuthenticationService initialization FAILED", e)
            binding.tvStatus.text = "认证服务初始化失败，应用可能无法正常工作。"
            binding.tvStatus.visibility = View.VISIBLE
            binding.btnLogin.isEnabled = false
        }

        // Initialize PreferencesManager AFTER setContentView and with heavy logging
        AppLogger.log("LoginActivity", "onCreate - Attempting to initialize PreferencesManager (post-setContentView).")
        if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "onCreate - Attempting to initialize PreferencesManager (post-setContentView).")
        try {
            preferencesManager = PreferencesManager(this)
            preferencesManagerInitialized = true
            AppLogger.log("LoginActivity", "onCreate - PreferencesManager initialized successfully (post-setContentView).")
            if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "onCreate - PreferencesManager initialized successfully (post-setContentView).")
        } catch (e: Exception) {
            AppLogger.log("LoginActivity", "onCreate - PreferencesManager initialization FAILED (post-setContentView): ${e.message}", e)
            if (BuildConfig.DEBUG) Log.e("LoginActivityDebug", "onCreate - PreferencesManager initialization FAILED (post-setContentView)", e)
            binding.tvStatus.text = "关键存储组件初始化失败，应用可能无法正常工作。请检查应用日志。"
            binding.tvStatus.visibility = View.VISIBLE
            binding.btnLogin.isEnabled = false
            // Do not return here, let the UI show up at least.
        }

        // Check authentication status
        AppLogger.log("LoginActivity", "onCreate - Checking authentication status.")
        if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "onCreate - Checking authentication status.")
        if (::authenticationService.isInitialized && authenticationService.isLoggedIn()) {
            AppLogger.log("LoginActivity", "onCreate - User already logged in, navigating to main.")
            if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "onCreate - User already logged in, navigating to main.")
            navigateToMain()
            return
        }

        if (!preferencesManagerInitialized) {
            AppLogger.log("LoginActivity", "onCreate - PreferencesManager not initialized. UI might be limited.")
            if (BuildConfig.DEBUG) Log.w("LoginActivityDebug", "onCreate - PreferencesManager not initialized. UI might be limited.")
            // Show an error on screen but don't block UI interaction if possible
            if (binding.tvStatus.visibility == View.GONE) { // Only update if not already set by specific failure
                binding.tvStatus.text = "警告：用户配置无法加载。"
                binding.tvStatus.visibility = View.VISIBLE
            }
        }

        AppLogger.log("LoginActivity", "onCreate - Setting up UI and loading saved credentials.")
        if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "onCreate - Setting up UI and loading saved credentials.")
        setupUI()
        // loadSavedCredentials needs preferencesManager, so check for initialization
        if (preferencesManagerInitialized) {
            loadSavedCredentials()
        } else {
            AppLogger.log("LoginActivity", "onCreate - Skipping loadSavedCredentials as PreferencesManager is not initialized.")
            if (BuildConfig.DEBUG) Log.w("LoginActivityDebug", "onCreate - Skipping loadSavedCredentials as PreferencesManager is not initialized.")
        }
        AppLogger.log("LoginActivity", "onCreate - FINISHED")
        if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "onCreate - FINISHED")
    }

    private fun setupUI() {
        binding.cbEnableSynologyAuth.visibility = View.GONE
        binding.tilSynologyUrl.visibility = View.GONE
        binding.tvSynologyHelp.visibility = View.GONE
        binding.rgBackend.visibility = View.GONE
        binding.tilWebDavUrl.visibility = View.GONE
        binding.tvWebDavHelp.visibility = View.GONE
        binding.cbUseExternalLogin.setOnCheckedChangeListener { _, isChecked ->
            val targetApiBaseUrl = resolveApiBaseUrlForLogin()
            AppLogger.log(
                "LoginActivity",
                "External login checkbox changed: $isChecked, targetApiBaseUrl=${targetApiBaseUrl ?: "N/A"}"
            )
        }

        // Set up Synology auth checkbox listener
        binding.cbEnableSynologyAuth.setOnCheckedChangeListener { _, isChecked ->
            AppLogger.log("LoginActivity", "Synology auth checkbox changed: $isChecked")
            updateSynologyFieldsVisibility(isChecked)
            updateLoginButtonState()
        }

        // Set up backend radio button listeners
        binding.rbWebdav.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) {
                AppLogger.log("LoginActivity", "WebDAV backend selected")
                updateWebDavFieldsVisibility(true)
            }
        }

        binding.rbSmb.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) {
                AppLogger.log("LoginActivity", "SMB backend selected")
                updateWebDavFieldsVisibility(false)
            }
        }

        // Set up URL validation TextWatcher for Synology
        binding.etSynologyUrl.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {
                // Not needed
            }

            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                // Not needed
            }

            override fun afterTextChanged(s: Editable?) {
                val url = s?.toString() ?: ""
                validateSynologyUrl(url)
            }
        })

        // Set up URL validation TextWatcher for WebDAV
        binding.etWebDavUrl.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {
                // Not needed
            }

            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                // Not needed
            }

            override fun afterTextChanged(s: Editable?) {
                val url = s?.toString() ?: ""
                validateWebDavUrl(url)
            }
        })

        binding.btnLogin.setOnClickListener {
            AppLogger.log("LoginActivity", "Login button clicked")
            if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "Login button clicked")
            if (!preferencesManagerInitialized) {
                AppLogger.log("LoginActivity", "Login button clicked - PreferencesManager not initialized, login aborted.")
                if (BuildConfig.DEBUG) Log.e("LoginActivityDebug", "Login button clicked - PreferencesManager not initialized, login aborted.")
                showStatus("错误：用户配置未加载，无法登录。", false)
                return@setOnClickListener
            }
            performLogin()
        }
    }

    private fun updateSynologyFieldsVisibility(isEnabled: Boolean) {
        binding.tilSynologyUrl.visibility = if (isEnabled) View.VISIBLE else View.GONE
        binding.tvSynologyHelp.visibility = if (isEnabled) View.VISIBLE else View.GONE
        AppLogger.log("LoginActivity", "Synology fields visibility updated: ${if (isEnabled) "VISIBLE" else "GONE"}")

        // Validate URL when fields become visible
        if (isEnabled) {
            val url = binding.etSynologyUrl.text?.toString() ?: ""
            validateSynologyUrl(url)
        } else {
            // Clear any validation errors when disabled
            binding.tilSynologyUrl.error = null
            isSynologyUrlValid = true
        }
    }

    private fun updateWebDavFieldsVisibility(isWebDavSelected: Boolean) {
        binding.tilWebDavUrl.visibility = if (isWebDavSelected) View.VISIBLE else View.GONE
        binding.tvWebDavHelp.visibility = if (isWebDavSelected) View.VISIBLE else View.GONE
        AppLogger.log("LoginActivity", "WebDAV fields visibility updated: ${if (isWebDavSelected) "VISIBLE" else "GONE"}")

        // Validate URL when fields become visible
        if (isWebDavSelected) {
            val url = binding.etWebDavUrl.text?.toString() ?: ""
            validateWebDavUrl(url)
        } else {
            // Clear any validation errors when disabled
            binding.tilWebDavUrl.error = null
        }
    }

    /**
     * Validates the Synology URL and updates UI accordingly.
     *
     * @param url The URL to validate
     */
    private fun validateSynologyUrl(url: String) {
        val validationResult = UrlValidator.validateSynologyUrl(url)
        isSynologyUrlValid = validationResult.isValid

        if (validationResult.isValid) {
            // Clear error when URL is valid
            binding.tilSynologyUrl.error = null
            AppLogger.log("LoginActivity", "Synology URL validation passed: $url")
        } else {
            // Display validation error
            binding.tilSynologyUrl.error = validationResult.errorMessage
            AppLogger.log("LoginActivity", "Synology URL validation failed: ${validationResult.errorMessage}")
        }

        // Update login button state based on validation
        updateLoginButtonState()
    }

    /**
     * Validates the WebDAV URL and updates UI accordingly.
     *
     * @param url The URL to validate
     */
    private fun validateWebDavUrl(url: String) {
        val validationResult = UrlValidator.validateWebDavUrl(url)

        if (validationResult.isValid) {
            // Clear error when URL is valid
            binding.tilWebDavUrl.error = null
            AppLogger.log("LoginActivity", "WebDAV URL validation passed: $url")
        } else {
            // Display validation error
            binding.tilWebDavUrl.error = validationResult.errorMessage
            AppLogger.log("LoginActivity", "WebDAV URL validation failed: ${validationResult.errorMessage}")
        }
    }

    /**
     * Updates the login button enabled state based on URL validation.
     * Disables login button when Synology auth is enabled and URL is invalid.
     */
    private fun updateLoginButtonState() {
        val synologyAuthEnabled = binding.cbEnableSynologyAuth.isChecked
        val shouldDisable = synologyAuthEnabled && !isSynologyUrlValid

        // Only disable if not already in loading state
        if (binding.progressBar.visibility != View.VISIBLE) {
            binding.btnLogin.isEnabled = !shouldDisable

            if (shouldDisable) {
                AppLogger.log("LoginActivity", "Login button disabled due to invalid Synology URL")
            }
        }
    }

    private fun resolveApiBaseUrlForLogin(): String? {
        if (!preferencesManagerInitialized) {
            return null
        }
        return if (binding.cbUseExternalLogin.isChecked) {
            preferencesManager!!.getExternalApiBaseUrl()
        } else {
            preferencesManager!!.getInternalApiBaseUrl()
        }
    }

    private fun applyApiBaseUrlForLogin(): String? {
        val apiBaseUrl = resolveApiBaseUrlForLogin() ?: return null
        preferencesManager!!.setApiBaseUrl(apiBaseUrl)
        AppLogger.log("LoginActivity", "Applied API base URL for login: $apiBaseUrl")
        return apiBaseUrl
    }

    private fun loadSavedCredentials() {
        AppLogger.log("LoginActivity", "loadSavedCredentials - Start")
        if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "loadSavedCredentials - Start")
        // preferencesManager is checked for null via preferencesManagerInitialized before calling this
        preferencesManager!!.getUsername()?.let {
            binding.etUsername.setText(it)
            AppLogger.log("LoginActivity", "loadSavedCredentials - Username loaded: $it")
        }

        if (preferencesManager!!.shouldRememberCredentials()) {
            preferencesManager!!.getPassword()?.let {
                binding.etPassword.setText(it)
                AppLogger.log("LoginActivity", "loadSavedCredentials - Password loaded (remembered).")
            }
        }

        binding.cbRememberCredentials.isChecked = preferencesManager!!.shouldRememberCredentials()
        AppLogger.log("LoginActivity", "loadSavedCredentials - Remember credentials checkbox set to: ${binding.cbRememberCredentials.isChecked}")
        val savedApiUrl = preferencesManager!!.getApiBaseUrl()
        binding.cbUseExternalLogin.isChecked = preferencesManager!!.isExternalApiUrl(savedApiUrl)
        AppLogger.log(
            "LoginActivity",
            "loadSavedCredentials - External login checkbox set to: ${binding.cbUseExternalLogin.isChecked}, savedApiUrl=$savedApiUrl"
        )

        preferencesManager!!.setBackend("api")
        AppLogger.log("LoginActivity", "loadSavedCredentials - Backend fixed to API")

        AppLogger.log("LoginActivity", "loadSavedCredentials - End")
        if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "loadSavedCredentials - End")
    }

    private fun performLogin() {
        val username = binding.etUsername.text.toString().trim()
        val password = binding.etPassword.text.toString()
        val rememberCredentials = binding.cbRememberCredentials.isChecked

        AppLogger.log("LoginActivity", "performLogin - usernameLen=${username.length}, pwdEmpty=${password.isEmpty()}, remember=$rememberCredentials")

        if (username.isEmpty()) {
            binding.etUsername.error = "请输入用户名"
            AppLogger.log("LoginActivity", "performLogin - empty username")
            return
        }

        if (password.isEmpty()) {
            binding.etPassword.error = "请输入密码"
            AppLogger.log("LoginActivity", "performLogin - empty password")
            return
        }

        showLoading(true)

        lifecycleScope.launch {
            try {
                // API-only login flow
                val synologyAuthEnabled = false
                val synologyUrl: String? = null
                val selectedBackend = "api"
                val webDavUrl: String? = null

                // Log login start with configuration
                AppLogger.log(
                    "LoginActivity",
                    "performLogin - Login started at ${System.currentTimeMillis()}"
                )
                AppLogger.log(
                    "LoginActivity",
                    "performLogin - Configuration: Synology auth enabled=$synologyAuthEnabled, " +
                    "Synology URL=${if (synologyUrl != null) maskUrl(synologyUrl) else "null"}, " +
                    "backend=$selectedBackend, " +
                    "WebDAV URL=${if (webDavUrl != null) maskUrl(webDavUrl) else "null"}"
                )

                // Validate Synology URL if Synology auth is enabled
                if (synologyAuthEnabled) {
                    if (synologyUrl.isNullOrBlank()) {
                        AppLogger.log("LoginActivity", "performLogin - Synology auth enabled but URL is empty")
                        showStatus("请输入群晖DSM服务器地址", false)
                        showLoading(false)
                        return@launch
                    }

                    val validationResult = UrlValidator.validateSynologyUrl(synologyUrl)
                    if (!validationResult.isValid) {
                        AppLogger.log("LoginActivity", "performLogin - Synology URL validation failed: ${validationResult.errorMessage}")
                        showStatus("群晖URL格式错误：${validationResult.errorMessage}", false)
                        showLoading(false)
                        return@launch
                    }
                }

                // Validate WebDAV URL if WebDAV backend is selected
                if (selectedBackend == "webdav" && !webDavUrl.isNullOrBlank()) {
                    val validationResult = UrlValidator.validateWebDavUrl(webDavUrl)
                    if (!validationResult.isValid) {
                        AppLogger.log("LoginActivity", "performLogin - WebDAV URL validation failed: ${validationResult.errorMessage}")
                        showStatus("WebDAV地址格式错误：${validationResult.errorMessage}", false)
                        showLoading(false)
                        return@launch
                    }
                }

                val apiBaseUrl = if (preferencesManagerInitialized) applyApiBaseUrlForLogin() else null
                AppLogger.log("LoginActivity", "performLogin - Using API base URL: ${apiBaseUrl ?: "N/A"}")

                // Use the new authentication flow controller
                val result = performAuthenticationFlow(
                    username = username,
                    password = password,
                    synologyUrl = synologyUrl,
                    enableSynologyAuth = synologyAuthEnabled,
                    backend = selectedBackend
                )

                when (result) {
                    is AuthenticationResult.Success -> {
                        handleSuccessfulLogin(
                            username = username,
                            password = password,
                            rememberCredentials = rememberCredentials,
                            synologyAuthEnabled = synologyAuthEnabled,
                            synologyUrl = synologyUrl,
                            selectedBackend = selectedBackend,
                            webDavUrl = webDavUrl,
                            result = result
                        )
                    }
                    is AuthenticationResult.PasswordChangeRequired -> {
                        AppLogger.log("LoginActivity", "performLogin - Password change required for ${result.username}")
                        showStatus(result.message, false)
                        showLoading(false)
                        showForceChangePasswordDialog(
                            username = result.username,
                            currentPassword = result.currentPassword,
                            rememberCredentials = rememberCredentials
                        )
                    }
                    is AuthenticationResult.Failure -> {
                        // Log final authentication result
                        AppLogger.log(
                            "LoginActivity",
                            "performLogin - Final authentication result: FAILURE at ${System.currentTimeMillis()}, " +
                            "failedMethod=${result.failedMethod?.name ?: "N/A"}, " +
                            "error=${result.error}, " +
                            "canRetry=${result.canRetry}"
                        )
                        val userFriendlyMessage = ErrorMessages.getLocalizedMessage(result.error, this@LoginActivity)
                        showStatus(userFriendlyMessage, false)
                    }
                }
            } catch (e: Exception) {
                AppLogger.log("LoginActivity", "performLogin - Login failed with exception", e)
                val userFriendlyMessage = ErrorMessages.getLocalizedMessage(e.message ?: "未知错误", this@LoginActivity)
                showStatus(userFriendlyMessage, false)
            } finally {
                showLoading(false)
            }
        }
    }

    /**
     * Authentication flow controller that orchestrates the authentication process.
     *
     * Step 1: Attempt Synology authentication if enabled and URL provided
     * Step 2: Automatic fallback to traditional authentication on Synology failure
     *
     * @param username User's username
     * @param password User's password
     * @param synologyUrl Optional Synology DSM server URL
     * @param enableSynologyAuth Whether Synology authentication is enabled
     * @param backend Backend type for traditional auth ("webdav" or "smb")
     * @return AuthenticationResult indicating success or failure
     */
    private suspend fun performAuthenticationFlow(
        username: String,
        password: String,
        synologyUrl: String?,
        enableSynologyAuth: Boolean,
        backend: String
    ): AuthenticationResult {
        AppLogger.log(
            "LoginActivity",
            "performAuthenticationFlow - API-only authentication, apiBaseUrl=${preferencesManager?.getApiBaseUrl() ?: "N/A"}"
        )
        return attemptApiAuth(username, password)
    }

    /**
     * Attempt API authentication.
     */
    private suspend fun attemptApiAuth(
        username: String,
        password: String
    ): AuthenticationResult {
        return try {
            val response = com.testcenter.qrscanner.api.ApiClient
                .getApiService(this@LoginActivity)
                .mobileLogin(com.testcenter.qrscanner.api.MobileLoginRequest(username, password))

            val body = response.body()
            if (response.isSuccessful && body?.requirePasswordChange == true) {
                val message = body.message ?: "首次登录请先修改密码"
                AppLogger.log("LoginActivity", "attemptApiAuth - Password change required, user=$username")
                AuthenticationResult.PasswordChangeRequired(
                    username = username,
                    currentPassword = password,
                    message = message
                )
            } else if (response.isSuccessful && body?.success == true && body.user != null) {
                val roleValue = (body.user.role ?: body.role ?: "user").lowercase()
                val localUser = LocalUserManager.LocalUser(
                    id = body.user.id ?: java.util.UUID.randomUUID().toString(),
                    synologyUsername = body.user.synologyUsername ?: body.user.username ?: username,
                    displayName = body.user.displayName ?: body.user.username ?: username,
                    role = if (roleValue == "admin") LocalUserManager.UserRole.ADMIN else LocalUserManager.UserRole.USER,
                    createdAt = System.currentTimeMillis(),
                    updatedAt = System.currentTimeMillis(),
                    lastLoginAt = System.currentTimeMillis(),
                    email = body.user.email
                )
                AppLogger.log("LoginActivity", "attemptApiAuth - Success, user=${localUser.synologyUsername}, role=${localUser.role.name}")
                AuthenticationResult.Success(
                    user = localUser,
                    method = AuthMethod.API
                )
            } else {
                val errorMessage = body?.message ?: body?.error ?: when (response.code()) {
                    401 -> "用户名或密码错误"
                    403 -> "用户未在用户管理中启用"
                    404 -> "登录接口不可用"
                    in 500..599 -> "服务器处理登录请求失败"
                    else -> "登录接口异常（HTTP ${response.code()} ${response.message()}）"
                }
                AppLogger.log("LoginActivity", "attemptApiAuth - Failed, error=$errorMessage")
                AuthenticationResult.Failure(
                    error = errorMessage,
                    failedMethod = AuthMethod.API,
                    canRetry = false
                )
            }
        } catch (e: Exception) {
            AppLogger.log("LoginActivity", "attemptApiAuth - Exception: ${e.message}", e)
            AuthenticationResult.Failure(
                error = e.message ?: "无法连接登录接口，请检查网络和服务器地址",
                failedMethod = AuthMethod.API,
                canRetry = false
            )
        }
    }

    private fun handleSuccessfulLogin(
        username: String,
        password: String,
        rememberCredentials: Boolean,
        synologyAuthEnabled: Boolean,
        synologyUrl: String?,
        selectedBackend: String,
        webDavUrl: String?,
        result: AuthenticationResult.Success
    ) {
        AppLogger.log(
            "LoginActivity",
            "performLogin - Final authentication result: SUCCESS at ${System.currentTimeMillis()}, " +
                "method=${result.method.name}, " +
                "user=${result.user?.synologyUsername ?: "N/A"}, " +
                "role=${result.user?.role?.name ?: "N/A"}"
        )

        if (preferencesManagerInitialized) {
            preferencesManager!!.setBackend(selectedBackend)
            preferencesManager!!.saveCredentials(username, password, "", rememberCredentials)
            preferencesManager!!.setSynologyAuthEnabled(synologyAuthEnabled)
            if (synologyUrl != null) {
                preferencesManager!!.setSynologyUrl(synologyUrl)
            }
            if (webDavUrl != null) {
                preferencesManager!!.setWebDavUrl(webDavUrl)
            }
            preferencesManager!!.setLastAuthMethod(result.method.name)
        }

        val methodName = ErrorMessages.getAuthMethodName(result.method.name)
        val user = result.user
        val roleText = if (user?.role?.name == "ADMIN") "管理员" else "普通用户"
        showStatus("登录成功！认证方式：$methodName，用户角色：$roleText", true)

        if (result.method == AuthMethod.API ||
            result.method == AuthMethod.SMB ||
            result.method == AuthMethod.WEBDAV) {
            saveDefaultUserIfNeeded(username, result.user)
            AppLogger.log("LoginActivity", "API login success, fetching permissions...")
            fetchAndApplyUserPermissions(username, result.user)
        }

        binding.root.postDelayed({
            navigateToMain()
        }, 1000)
    }

    private fun showForceChangePasswordDialog(
        username: String,
        currentPassword: String,
        rememberCredentials: Boolean
    ) {
        val padding = (20 * resources.displayMetrics.density).toInt()
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding / 2, padding, 0)
        }
        val newPasswordInput = EditText(this).apply {
            hint = "新密码"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        val confirmPasswordInput = EditText(this).apply {
            hint = "确认新密码"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        container.addView(newPasswordInput)
        container.addView(confirmPasswordInput)

        AlertDialog.Builder(this)
            .setTitle("首次登录请修改密码")
            .setMessage("默认密码为 Ab123###，修改后才能继续登录。")
            .setView(container)
            .setCancelable(false)
            .setNegativeButton("取消") { _, _ -> showStatus("已取消登录", false) }
            .setPositiveButton("保存", null)
            .create()
            .also { dialog ->
                dialog.setOnShowListener {
                    dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                        val newPassword = newPasswordInput.text?.toString()?.trim().orEmpty()
                        val confirmPassword = confirmPasswordInput.text?.toString()?.trim().orEmpty()
                        if (newPassword.length < 4) {
                            showStatus("新密码长度至少 4 位", false)
                            return@setOnClickListener
                        }
                        if (newPassword != confirmPassword) {
                            showStatus("两次输入的新密码不一致", false)
                            return@setOnClickListener
                        }
                        if (newPassword == currentPassword) {
                            showStatus("新密码不能与默认密码相同", false)
                            return@setOnClickListener
                        }
                        dialog.dismiss()
                        performForcedPasswordChange(username, currentPassword, newPassword, rememberCredentials)
                    }
                }
                dialog.show()
            }
    }

    private fun performForcedPasswordChange(
        username: String,
        currentPassword: String,
        newPassword: String,
        rememberCredentials: Boolean
    ) {
        showLoading(true)
        lifecycleScope.launch {
            try {
                val api = com.testcenter.qrscanner.api.ApiClient.getApiService(this@LoginActivity)
                val changeResponse = api.mobileChangePassword(
                    com.testcenter.qrscanner.api.MobileChangePasswordRequest(
                        username = username,
                        currentPassword = currentPassword,
                        newPassword = newPassword
                    )
                )
                val changeBody = changeResponse.body()
                if (!changeResponse.isSuccessful || changeBody?.success != true) {
                    showStatus(changeBody?.message ?: changeBody?.error ?: "修改密码失败", false)
                    return@launch
                }

                when (val retryResult = attemptApiAuth(username, newPassword)) {
                    is AuthenticationResult.Success -> {
                        handleSuccessfulLogin(
                            username = username,
                            password = newPassword,
                            rememberCredentials = rememberCredentials,
                            synologyAuthEnabled = false,
                            synologyUrl = null,
                            selectedBackend = "api",
                            webDavUrl = null,
                            result = retryResult
                        )
                    }
                    is AuthenticationResult.Failure -> showStatus(retryResult.error, false)
                    is AuthenticationResult.PasswordChangeRequired -> showStatus(retryResult.message, false)
                }
            } catch (e: Exception) {
                AppLogger.log("LoginActivity", "performForcedPasswordChange - Exception: ${e.message}", e)
                showStatus(e.message ?: "修改密码失败", false)
            } finally {
                showLoading(false)
            }
        }
    }


    /**
     * Attempt Synology authentication.
     *
     * @param username User's username
     * @param password User's password
     * @param synologyUrl Synology DSM server URL
     * @return AuthenticationResult
     */
    private suspend fun attemptSynologyAuth(
        username: String,
        password: String,
        synologyUrl: String
    ): AuthenticationResult {
        return try {
            if (!::authenticationService.isInitialized) {
                AppLogger.log("LoginActivity", "attemptSynologyAuth - AuthenticationService not initialized")
                return AuthenticationResult.Failure(
                    error = "认证服务未初始化",
                    failedMethod = AuthMethod.SYNOLOGY,
                    canRetry = true
                )
            }

            authenticationService.initialize(synologyUrl)
            val loginResult = authenticationService.login(username, password, synologyUrl)

            if (loginResult.success && loginResult.user != null) {
                AppLogger.log(
                    "LoginActivity",
                    "attemptSynologyAuth - Success, user: ${loginResult.user.synologyUsername}, role: ${loginResult.user.role}"
                )
                AuthenticationResult.Success(
                    user = loginResult.user,
                    method = AuthMethod.SYNOLOGY
                )
            } else {
                val canRetry = loginResult.shouldFallback
                AppLogger.log(
                    "LoginActivity",
                    "attemptSynologyAuth - Failed, error: ${loginResult.error}, canRetry: $canRetry"
                )
                AuthenticationResult.Failure(
                    error = loginResult.error ?: "群晖认证失败",
                    failedMethod = AuthMethod.SYNOLOGY,
                    canRetry = canRetry
                )
            }
        } catch (e: Exception) {
            AppLogger.log("LoginActivity", "attemptSynologyAuth - Exception: ${e.message}", e)

            // Determine if we should retry based on error type
            val canRetry = when {
                // Network errors - should retry with fallback
                e.message?.contains("timeout", ignoreCase = true) == true -> true
                e.message?.contains("UnknownHost", ignoreCase = true) == true -> true
                e.message?.contains("Connection refused", ignoreCase = true) == true -> true
                e.message?.contains("Network is unreachable", ignoreCase = true) == true -> true
                e.message?.contains("No route to host", ignoreCase = true) == true -> true

                // SSL errors - should retry with fallback
                e.message?.contains("SSL", ignoreCase = true) == true -> true
                e.message?.contains("certificate", ignoreCase = true) == true -> true
                e.message?.contains("PKIX", ignoreCase = true) == true -> true

                // Authentication errors - should NOT retry
                e.message?.contains("401", ignoreCase = true) == true -> false
                e.message?.contains("用户名或密码错误", ignoreCase = true) == true -> false

                // Default to retry for unknown errors
                else -> true
            }

            AppLogger.log(
                "LoginActivity",
                "attemptSynologyAuth - Error categorized as ${if (canRetry) "network/server issue (will fallback)" else "authentication issue (no fallback)"}"
            )

            AuthenticationResult.Failure(
                error = e.message ?: "群晖认证异常",
                failedMethod = AuthMethod.SYNOLOGY,
                canRetry = canRetry
            )
        }
    }

    /**
     * Attempt traditional authentication (WebDAV or SMB).
     *
     * @param username User's username
     * @param password User's password
     * @param backend Backend type ("webdav" or "smb")
     * @return AuthenticationResult
     */
    private suspend fun attemptTraditionalAuth(
        username: String,
        password: String,
        backend: String
    ): AuthenticationResult {
        return try {
            val webDavUrl = if (backend == "webdav") getWebDavUrl() else null
            AppLogger.log("LoginActivity", "attemptTraditionalAuth - Testing connection via backend=$backend, URL=${webDavUrl?.let { maskUrl(it) } ?: "default"}")

            val fm = FileManagerFactory.create(this@LoginActivity, username, password, backend)
            val connectionSuccess = fm.testConnection()

            AppLogger.log(
                "LoginActivity",
                "attemptTraditionalAuth - Connection result via $backend = $connectionSuccess at ${System.currentTimeMillis()}"
            )

            if (connectionSuccess) {
                val method = if (backend == "smb") AuthMethod.SMB else AuthMethod.WEBDAV
                AuthenticationResult.Success(
                    user = null, // Traditional auth doesn't provide user object
                    method = method
                )
            } else {
                val errorMsg = if (backend == "webdav" && webDavUrl != null) {
                    "无法连接到WebDAV服务器: ${maskUrl(webDavUrl)}"
                } else {
                    "无法连接到网络共享文件夹"
                }
                AuthenticationResult.Failure(
                    error = errorMsg,
                    failedMethod = if (backend == "smb") AuthMethod.SMB else AuthMethod.WEBDAV,
                    canRetry = false
                )
            }
        } catch (e: Exception) {
            AppLogger.log("LoginActivity", "attemptTraditionalAuth - Exception: ${e.message}", e)

            // Categorize error for better user feedback
            val errorMsg = when {
                e.message?.contains("timeout", ignoreCase = true) == true -> {
                    val url = if (backend == "webdav") getWebDavUrl() else null
                    if (url != null) "连接超时: ${maskUrl(url)}" else "连接超时"
                }
                e.message?.contains("UnknownHost", ignoreCase = true) == true -> {
                    val url = if (backend == "webdav") getWebDavUrl() else null
                    if (url != null) "无法解析服务器地址: ${maskUrl(url)}" else "无法解析服务器地址"
                }
                e.message?.contains("SSL", ignoreCase = true) == true ||
                e.message?.contains("certificate", ignoreCase = true) == true -> {
                    "SSL证书错误，请检查服务器配置"
                }
                e.message?.contains("401") == true -> {
                    "认证失败：用户名或密码错误"
                }
                else -> "传统认证异常: ${e.message}"
            }

            AuthenticationResult.Failure(
                error = errorMsg,
                failedMethod = if (backend == "smb") AuthMethod.SMB else AuthMethod.WEBDAV,
                canRetry = false
            )
        }
    }

    /**
     * Get the Synology URL from preferences or UI.
     * Returns null if Synology auth is disabled.
     *
     * @return Synology URL or null
     */
    private fun getSynologyUrl(): String? {
        // Check if Synology auth is enabled
        val synologyAuthEnabled = binding.cbEnableSynologyAuth.isChecked
        if (!synologyAuthEnabled) {
            AppLogger.log("LoginActivity", "getSynologyUrl - Synology auth disabled, returning null")
            return null
        }

        // Try to get URL from UI first
        val urlFromUI = binding.etSynologyUrl.text?.toString()?.trim()
        if (!urlFromUI.isNullOrBlank()) {
            AppLogger.log("LoginActivity", "getSynologyUrl - Returning URL from UI: ${maskUrl(urlFromUI)}")
            return urlFromUI
        }

        // Fallback to PreferencesManager if available
        if (preferencesManagerInitialized) {
            val urlFromPrefs = preferencesManager!!.getSynologyUrl()
            if (!urlFromPrefs.isNullOrBlank()) {
                AppLogger.log("LoginActivity", "getSynologyUrl - Returning URL from preferences: ${maskUrl(urlFromPrefs)}")
                return urlFromPrefs
            }
        }

        // Return default URL if nothing is configured
        val defaultUrl = AuthenticationService.DEFAULT_SYNOLOGY_DSM_URL
        AppLogger.log("LoginActivity", "getSynologyUrl - Returning default URL: ${maskUrl(defaultUrl)}")
        return defaultUrl
    }

    /**
     * Get the WebDAV URL from preferences or UI.
     *
     * @return WebDAV URL or null
     */
    private fun getWebDavUrl(): String? {
        // Try to get URL from UI first
        val urlFromUI = binding.etWebDavUrl.text?.toString()?.trim()
        if (!urlFromUI.isNullOrBlank()) {
            AppLogger.log("LoginActivity", "getWebDavUrl - Returning URL from UI: ${maskUrl(urlFromUI)}")
            return urlFromUI
        }

        // Fallback to PreferencesManager if available
        if (preferencesManagerInitialized) {
            val urlFromPrefs = preferencesManager!!.getWebDavUrl()
            if (!urlFromPrefs.isNullOrBlank()) {
                AppLogger.log("LoginActivity", "getWebDavUrl - Returning URL from preferences: ${maskUrl(urlFromPrefs)}")
                return urlFromPrefs
            }
        }

        // Return null if nothing is configured (will use default in WebDAVFileManager)
        AppLogger.log("LoginActivity", "getWebDavUrl - No URL configured, will use default")
        return null
    }

    /**
     * Mask sensitive parts of URL for logging.
     *
     * @param url URL to mask
     * @return Masked URL
     */
    private fun maskUrl(url: String): String {
        return try {
            val parts = url.split("://")
            if (parts.size == 2) {
                val protocol = parts[0]
                val rest = parts[1].split(":")
                if (rest.size >= 2) {
                    "$protocol://***:${rest[1]}"
                } else {
                    "$protocol://***"
                }
            } else {
                "***"
            }
        } catch (e: Exception) {
            "***"
        }
    }



    private fun showLoading(show: Boolean) {
        AppLogger.log("LoginActivity", "showLoading=$show")
        binding.progressBar.visibility = if (show) View.VISIBLE else View.GONE
        binding.btnLogin.isEnabled = !show
        binding.btnLogin.text = if (show) "正在验证..." else "登录"
    }

    private fun showStatus(message: String, isSuccess: Boolean) {
        AppLogger.log("LoginActivity", "showStatus isSuccess=$isSuccess, msg=$message")
        binding.tvStatus.apply {
            text = message
            setTextColor(getColor(if (isSuccess) android.R.color.holo_green_dark else android.R.color.holo_red_dark))
            visibility = View.VISIBLE
        }
        Snackbar.make(binding.root, message, Snackbar.LENGTH_LONG).show()
    }

    /**
     * 从后台 API 查询并应用用户权限
     * 用于 SMB/WebDAV 登录后获取详细权限
     */
    private fun fetchAndApplyUserPermissions(username: String, user: LocalUserManager.LocalUser?) {
        lifecycleScope.launch {
            try {
                // 从 PreferencesManager 获取 API 地址
                val apiBaseUrl = preferencesManager?.getApiBaseUrl() ?: return@launch

                AppLogger.log("LoginActivity", "[权限查询] 查询权限: $apiBaseUrl")

                // 创建权限 API 客户端（带认证凭证）
                val apiClient = com.testcenter.qrscanner.network.PermissionApiClient(
                    apiBaseUrl,
                    preferencesManager?.getUsername(),
                    preferencesManager?.getPassword()
                )

                // 查询用户权限
                val userPermissions = apiClient.fetchUserPermissions(username)

                if (userPermissions != null) {
                    // 转换为 Permission 集合
                    val permissions = apiClient.convertToPermissionSet(userPermissions)

                    // 应用到 PermissionService
                    val permissionService = authenticationService.getPermissionService()
                    permissionService.setApiLoadedPermissions(username, permissions)

                    // 创建并保存 LocalUser 对象（如果不存在）
                    if (user == null) {
                        val localUserManager = authenticationService.getLocalUserManager()
                        val existingUser = localUserManager.getCurrentUser()

                        if (existingUser == null || existingUser.synologyUsername != username) {
                            // 根据API返回的角色创建用户
                            val userRole = if (userPermissions.role == "admin") {
                                LocalUserManager.UserRole.ADMIN
                            } else {
                                LocalUserManager.UserRole.USER
                            }

                            val currentTime = System.currentTimeMillis()
                            val newUser = LocalUserManager.LocalUser(
                                id = java.util.UUID.randomUUID().toString(),
                                synologyUsername = username,
                                displayName = username,
                                role = userRole,
                                createdAt = currentTime,
                                updatedAt = currentTime,
                                lastLoginAt = currentTime,
                                email = null
                            )

                            // 保存用户信息到 LocalUserManager
                            localUserManager.saveCurrentUser(newUser)
                            AppLogger.log("LoginActivity", "[用户管理] ✓ 为SMB/WebDAV登录创建并保存LocalUser: username=$username, role=$userRole")
                        }
                    }

                    AppLogger.log("LoginActivity", "[权限查询] ✓ 成功加载并应用用户权限: " +
                            "role=${userPermissions.role}, permissions=${permissions.size}项")

                    // 更新显示的角色信息
                    withContext(Dispatchers.Main) {
                        val roleText = if (userPermissions.role == "admin") "管理员" else "普通用户"
                        val currentStatus = binding.tvStatus.text.toString()
                        if (currentStatus.contains("用户角色：")) {
                            binding.tvStatus.text = currentStatus.replace(
                                Regex("用户角色：[^，]*"),
                                "用户角色：$roleText（已加载详细权限）"
                            )
                        }
                    }
                } else {
                    AppLogger.log("LoginActivity", "[权限查询] ✗ 权限查询失败，将使用默认角色权限")
                    // 权限查询失败时也要保存用户信息，否则会话无法建立
                    saveDefaultUserIfNeeded(username, user)
                }
            } catch (e: Exception) {
                AppLogger.log("LoginActivity", "[权限查询] ✗ 权限查询异常，将使用默认角色权限", e)
                // 异常时也要保存用户信息
                saveDefaultUserIfNeeded(username, user)
            }
        }
    }

    /**
     * 保存默认用户信息（当权限查询失败时使用）
     */
    private fun saveDefaultUserIfNeeded(username: String, existingUser: LocalUserManager.LocalUser?) {
        try {
            if (existingUser != null) {
                // 已有用户，更新登录时间
                val localUserManager = authenticationService.getLocalUserManager()
                localUserManager.saveCurrentUser(existingUser.copy(lastLoginAt = System.currentTimeMillis()))
                AppLogger.log("LoginActivity", "[用户管理] ✓ 更新现有用户登录时间: ${existingUser.synologyUsername}")
                return
            }

            val localUserManager = authenticationService.getLocalUserManager()
            val currentUser = localUserManager.getCurrentUser()

            if (currentUser == null || currentUser.synologyUsername != username) {
                val currentTime = System.currentTimeMillis()
                val newUser = LocalUserManager.LocalUser(
                    id = java.util.UUID.randomUUID().toString(),
                    synologyUsername = username,
                    displayName = username,
                    role = LocalUserManager.UserRole.USER, // 默认普通用户
                    createdAt = currentTime,
                    updatedAt = currentTime,
                    lastLoginAt = currentTime,
                    email = null
                )

                localUserManager.saveCurrentUser(newUser)
                AppLogger.log("LoginActivity", "[用户管理] ✓ 为SMB/WebDAV登录创建默认LocalUser: username=$username")
            }
        } catch (e: Exception) {
            AppLogger.log("LoginActivity", "[用户管理] ✗ 保存默认用户失败: ${e.message}", e)
        }
    }

    private fun navigateToMain() {
        AppLogger.log("LoginActivity", "navigateToMain - Attempting to start MainActivity")
        if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "navigateToMain - Attempting to start MainActivity")
        try {
            startActivity(Intent(this, MainActivity::class.java))
            finish()
            AppLogger.log("LoginActivity", "navigateToMain - MainActivity started and LoginActivity finished.")
            if (BuildConfig.DEBUG) Log.d("LoginActivityDebug", "navigateToMain - MainActivity started and LoginActivity finished.")
        } catch (e: Exception) {
            AppLogger.log("LoginActivity", "navigateToMain - Failed to start MainActivity", e)
            if (BuildConfig.DEBUG) Log.e("LoginActivityDebug", "navigateToMain - Failed to start MainActivity", e)
            binding.tvStatus.text = "无法启动主界面: ${e.message}"
            binding.tvStatus.visibility = View.VISIBLE
        }
    }
}
