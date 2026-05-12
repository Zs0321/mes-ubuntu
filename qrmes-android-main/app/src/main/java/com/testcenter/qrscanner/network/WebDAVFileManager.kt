package com.testcenter.qrscanner.network

import android.content.Context
import com.thegrizzlylabs.sardineandroid.Sardine
import com.thegrizzlylabs.sardineandroid.DavResource
import com.thegrizzlylabs.sardineandroid.impl.OkHttpSardine
import com.thegrizzlylabs.sardineandroid.impl.SardineException
import com.testcenter.qrscanner.data.ProjectConfig
import com.testcenter.qrscanner.data.TestRecord
import com.testcenter.qrscanner.utils.PreferencesManager
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*
import java.net.URLEncoder
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Credentials
import com.testcenter.qrscanner.BuildConfig
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

class WebDAVFileManager(
    private val context: Context,
    private val username: String? = null,
    private val password: String? = null
) : FileManager {
    
    private val targetPath = "/MES/QRMES"
    private val testersFileName = "testers.json"
    private val activeTestsFileName = "active_tests.json"
    private val apkDirectory = "$targetPath/APK"
    private val apkFileRegex = "(?i)^(.+)\\s+v([0-9.]+)(?:_(\\d+))?\\.apk$".toRegex()
    
    private val preferencesManager = PreferencesManager(context)
    
    // Get WebDAV base URL from preferences
    private fun getBaseUrl(): String {
        val url = preferencesManager.getWebDavUrl()
        AppLogger.logWebDAV("GET_BASE_URL", "Using WebDAV URL: $url")
        return url
    }
    
    // 获取实际的登录凭据
    private fun getCredentials(): Pair<String, String> {
        val actualUsername = username ?: preferencesManager.getUsername() ?: ""
        val actualPassword = password ?: preferencesManager.getPassword() ?: ""
        return Pair(actualUsername, actualPassword)
    }
    
    // 创建信任所有证书的TrustManager（仅 DEBUG 构建，用于自签名证书）
    private fun getUnsafeTrustManager(): X509TrustManager {
        return object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
            override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
        }
    }

    // Create configured Sardine client with Windows WebDAV compatible headers
    private fun createSardineClient(): Sardine {
        val (actualUsername, actualPassword) = getCredentials()
        val baseUrl = getBaseUrl()

        // 验证凭据
        if (actualUsername.isEmpty() || actualPassword.isEmpty()) {
            AppLogger.logWebDAV("CREATE_CLIENT", "⚠️ 警告: WebDAV凭据为空 - username: '${actualUsername}', password: ${if (actualPassword.isEmpty()) "空" else "已设置"}")
            throw IllegalStateException("WebDAV凭据未设置，请先登录")
        }

        AppLogger.logWebDAV("CREATE_CLIENT", "创建WebDAV客户端 - 用户: $actualUsername, 服务器: $baseUrl")

        val clientBuilder = okhttp3.OkHttpClient.Builder()
            .addInterceptor { chain ->
                val request = chain.request().newBuilder()
                    .addHeader("User-Agent", "Microsoft-WebDAV-MiniRedir/10.0.19041")
                    .addHeader("Translate", "f")
                    .addHeader("Cache-Control", "no-cache")
                    .addHeader("Pragma", "no-cache")
                    .addHeader("Accept", "*/*")
                    .addHeader("Connection", "Keep-Alive")
                    .build()
                chain.proceed(request)
            }

        // 仅在 DEBUG 构建中跳过 SSL 证书验证（自签名证书支持）
        if (BuildConfig.DEBUG) {
            val trustManager = getUnsafeTrustManager()
            val sslContext = SSLContext.getInstance("TLS").apply {
                init(null, arrayOf<TrustManager>(trustManager), java.security.SecureRandom())
            }
            clientBuilder.sslSocketFactory(sslContext.socketFactory, trustManager)
            clientBuilder.hostnameVerifier { _, _ -> true }
        }

        return OkHttpSardine(clientBuilder.build()).apply {
            setCredentials(actualUsername, actualPassword)
        }
    }
    
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
    private val fileNameFormat = SimpleDateFormat("yyyyMMdd", Locale.getDefault())
    // 简化根路径候选列表，移除不必要的探测
    private val rootCandidates = listOf("/")
    @Volatile private var resolvedRootPrefix: String? = null
    
    private fun normalizeBase(): String = getBaseUrl().removeSuffix("/")
    
    private fun buildUrl(path: String): String {
        val parts = path.split("/").filter { it.isNotEmpty() }
        val encoded = parts.joinToString("/") { URLEncoder.encode(it, "UTF-8").replace("+", "%20") }
        return if (encoded.isEmpty()) normalizeBase() else "${normalizeBase()}/$encoded"
    }
    
    private fun buildUrl(rootPrefix: String, path: String): String {
        val normalizedBase = normalizeBase()
        val cleanRoot = rootPrefix.trim().removePrefix("/").removeSuffix("/")
        val cleanPath = path.trim().removePrefix("/").removeSuffix("/")
        
        val fullPath = if (cleanRoot.isEmpty()) {
            cleanPath
        } else if (cleanPath.isEmpty()) {
            cleanRoot
        } else {
            "$cleanRoot/$cleanPath"
        }
        
        val parts = fullPath.split("/").filter { it.isNotEmpty() }
        val encoded = parts.joinToString("/") { URLEncoder.encode(it, "UTF-8").replace("+", "%20") }
        
        return if (encoded.isEmpty()) normalizedBase else "$normalizedBase/$encoded"
    }
    
    private fun ensureDirectoryExistsWithRoot(sardine: Sardine, rootPrefix: String, path: String) {
        try {
            val pathParts = path.split("/").filter { it.isNotEmpty() }
            val cleanRoot = rootPrefix.trim().removePrefix("/").removeSuffix("/")
            
            // Build path incrementally using our fixed buildUrl function
            var currentPathParts = if (cleanRoot.isNotEmpty()) listOf(cleanRoot) else emptyList()
            
            for (part in pathParts) {
                currentPathParts = currentPathParts + part
                val currentPath = buildUrl("", currentPathParts.joinToString("/"))
                
                AppLogger.logWebDAV("CREATE_DIR", "Checking directory: $currentPath")
                
                try {
                    // Try list first as it's more reliable than exists for some servers
                    try {
                        sardine.list(currentPath)
                        AppLogger.logWebDAV("CREATE_DIR", "Directory accessible via list: $currentPath")
                    } catch (listException: SardineException) {
                        if (listException.statusCode == 404) {
                            // Directory doesn't exist, try to create it
                            AppLogger.logWebDAV("CREATE_DIR", "Directory not found, creating: $currentPath")
                            try {
                                sardine.createDirectory(currentPath)
                                AppLogger.logWebDAV("CREATE_DIR", "Successfully created directory: $currentPath")
                            } catch (createException: SardineException) {
                                if (createException.statusCode == 405) {
                                    AppLogger.logWebDAV("CREATE_DIR", "405 Method Not Allowed for creation, directory may already exist: $currentPath")
                                } else if (createException.statusCode == 409) {
                                    // 409 Conflict - directory already exists, this is OK
                                    AppLogger.logWebDAV("CREATE_DIR", "409 Conflict - directory already exists: $currentPath")
                                } else {
                                    throw createException
                                }
                            }
                        } else if (listException.statusCode == 403) {
                            AppLogger.logWebDAV("CREATE_DIR", "403 Forbidden for list operation on $currentPath - assuming directory exists")
                            // Continue processing - assume directory exists but we can't verify it
                        } else {
                            throw listException
                        }
                    }
                } catch (e: SardineException) {
                    if (e.statusCode == 405) {
                        // Method not allowed - try to check if directory exists by listing parent
                        AppLogger.logWebDAV("CREATE_DIR", "405 Method Not Allowed for $currentPath, trying alternative check")
                        try {
                            sardine.list(currentPath)
                            AppLogger.logWebDAV("CREATE_DIR", "Directory accessible via list: $currentPath")
                        } catch (listException: Exception) {
                            AppLogger.logWebDAV("CREATE_DIR", "Directory not accessible: $currentPath", listException)
                            throw e // Re-throw original exception
                        }
                    } else if (e.statusCode == 403) {
                        AppLogger.logWebDAV("CREATE_DIR", "403 Forbidden for exists operation on $currentPath - assuming directory exists")
                        // Continue processing - assume directory exists but we can't verify it
                    } else {
                        throw e
                    }
                }
            }
        } catch (e: Exception) {
            AppLogger.logWebDAV("CREATE_DIR", "Failed to ensure directory exists for path: $path", e)
            throw e
        }
    }

    private fun resolveRootPrefix(sardine: Sardine): String {
        resolvedRootPrefix?.let { 
            AppLogger.logWebDAV("RESOLVE_ROOT", "Using cached root prefix: $it")
            return it 
        }
        
        AppLogger.logWebDAV("RESOLVE_ROOT", "Using fixed root prefix: /")
        resolvedRootPrefix = "/"
        return "/"
    }

    // --- Concurrency helpers (WebDAV) ---
    private fun buildDavOkHttpClient(): OkHttpClient {
        return OkHttpClient.Builder()
            .connectTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
            .readTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
            .writeTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val (u, p) = getCredentials()
                val auth = Credentials.basic(u, p)
                val request = chain.request().newBuilder()
                    .addHeader("User-Agent", "Microsoft-WebDAV-MiniRedir/10.0.19041")
                    .addHeader("Translate", "f")
                    .addHeader("Cache-Control", "no-cache")
                    .addHeader("Pragma", "no-cache")
                    .addHeader("Accept", "*/*")
                    .addHeader("Connection", "Keep-Alive")
                    .addHeader("Authorization", auth)
                    .build()
                chain.proceed(request)
            }
            .build()
    }

    private fun headETag(url: String): String? {
        return try {
            val client = buildDavOkHttpClient()
            val req = Request.Builder().url(url).head().build()
            client.newCall(req).execute().use { resp ->
                if (resp.isSuccessful) resp.header("ETag") else null
            }
        } catch (_: Exception) { null }
    }

    private fun conditionalPut(url: String, bytes: ByteArray, contentType: String, etag: String?): Int {
        val client = buildDavOkHttpClient()
        val body = bytes.toRequestBody(contentType.toMediaTypeOrNull())
        val builder = Request.Builder().url(url).put(body)
        if (etag == null) {
            builder.header("If-None-Match", "*")
        } else {
            builder.header("If-Match", etag)
        }
        return client.newCall(builder.build()).execute().use { it.code }
    }
    
    // 在某些服务器上，即便文件已存在也不会返回 ETag。为避免 If-None-Match "*" 导致 412，这里提供不带条件头的普通 PUT。
    private fun plainPut(url: String, bytes: ByteArray, contentType: String): Int {
        val client = buildDavOkHttpClient()
        val body = bytes.toRequestBody(contentType.toMediaTypeOrNull())
        val req = Request.Builder().url(url).put(body).build()
        return client.newCall(req).execute().use { it.code }
    }
    
    override suspend fun syncTestRecords(records: List<TestRecord>): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                AppLogger.logWebDAV("SYNC_RECORDS", "Starting sync - records=${records.size}")
                val sardine: Sardine = createSardineClient()
                
                // 解析可用根并确保目录
                val root = resolveRootPrefix(sardine)
                AppLogger.logWebDAV("SYNC_RECORDS", "Ensuring directory exists under root $root: $targetPath")
                ensureDirectoryExistsWithRoot(sardine, root, targetPath)
                
                val currentDate = Date()
                val formattedDate = fileNameFormat.format(currentDate)
                val fileName = "test_records_${formattedDate}.csv"
                val fullUrl = buildUrl(root, "$targetPath/$fileName")
                AppLogger.logWebDAV("SYNC_RECORDS", "Generated CSV filename: $fileName (date: $currentDate, formatted: $formattedDate)")
                // 生成仅数据行（不含表头），并统一 CRLF
                val generatedCsv = generateCSVContent(records).replace("\n", "\r\n")
                val header = "序列号,测试人员,开始时间,结束时间,测试时长(分钟),状态,创建时间"
                var rowsOnly = generatedCsv
                    .lineSequence()
                    .drop(1) // 去表头
                    .joinToString("\r\n")
                if (rowsOnly.isBlank() && records.isNotEmpty()) {
                    // 兜底：直接基于 records 生成数据行，避免因换行解析差异导致空写入
                    rowsOnly = records.joinToString("\r\n") { record ->
                        val endTimeStr = record.endTime?.let { dateFormat.format(it) } ?: ""
                        val durationStr = record.testDurationMinutes?.toString() ?: ""
                        val status = if (record.isCompleted) "已完成" else "测试中"
                        "${record.serialNumber},${record.tester},${dateFormat.format(record.startTime)},$endTimeStr,$durationStr,$status,${dateFormat.format(record.createdAt)}"
                    }
                    AppLogger.logWebDAV("SYNC_RECORDS", "rowsOnly was blank after split; rebuilt from records directly (count=${records.size})")
                }

                // 轻量并发控制：ETag 条件写 + 失败重试（考虑 423 Locked）
                val maxRetries = 6
                var attempt = 0
                while (true) {
                    attempt++
                    val etag = headETag(fullUrl) // null 表示文件不存在或服务器未返回
                    val existing: String? = try {
                        sardine.get(fullUrl).use { it.readBytes().toString(Charsets.UTF_8) }
                    } catch (e: SardineException) {
                        if (e.statusCode == 404) null else throw e
                    }

                    AppLogger.logWebDAV("SYNC_RECORDS", "existing length=${existing?.length ?: 0}, etagPresent=${etag != null}")

                    val mergedContent: String = if (existing.isNullOrEmpty()) {
                        val body = if (rowsOnly.isNotBlank()) "$header\r\n$rowsOnly\r\n" else "$header\r\n"
                        body
                    } else {
                        var ex = existing
                        if (ex.startsWith("\uFEFF")) ex = ex.removePrefix("\uFEFF")
                        val firstLine = ex.lineSequence().firstOrNull()?.trim()
                        val hasHeader = firstLine == header
                        var base = if (hasHeader) ex else "$header\r\n$ex"
                        if (!base.endsWith("\r\n")) base += "\r\n"
                        if (rowsOnly.isNotBlank()) base + rowsOnly + "\r\n" else base
                    }

                    val finalOut = if (mergedContent.startsWith("\uFEFF")) mergedContent else "\uFEFF$mergedContent"
                    val outBytes = finalOut.toByteArray(Charsets.UTF_8)
                    AppLogger.logWebDAV("SYNC_RECORDS", "Conditional upload attempt $attempt to: $fullUrl (bytes=${outBytes.size}) etag=$etag, rowsOnlyBlank=${rowsOnly.isBlank()}")

                    val code = try {
                        if (etag == null && existing != null) {
                            // 文件存在但无 ETag：使用普通 PUT 覆盖写入合并后的内容，避免 412
                            AppLogger.logWebDAV("SYNC_RECORDS", "ETag is null while file exists. Using plain PUT to avoid 412.")
                            plainPut(fullUrl, outBytes, "text/csv; charset=utf-8")
                        } else {
                            conditionalPut(fullUrl, outBytes, "text/csv; charset=utf-8", etag)
                        }
                    } catch (e: Exception) {
                        AppLogger.logWebDAV("SYNC_RECORDS", "Conditional PUT error: ${e.message}", e)
                        -1
                    }

                    if (code in 200..299) {
                        AppLogger.logFileOperation("WRITE", fullUrl, true, "Appended ${records.size} records (attempt=$attempt)")
                        // 写后校验：再次读取并打印长度与行数，便于定位空文件问题
                        try {
                            val post = sardine.get(fullUrl).use { it.readBytes().toString(Charsets.UTF_8) }
                            var pv = post
                            if (pv.startsWith("\uFEFF")) pv = pv.removePrefix("\uFEFF")
                            val lines = pv.replace("\r\n", "\n").lineSequence().toList()
                            AppLogger.logWebDAV(
                                "SYNC_RECORDS",
                                "Post-write verify: size=${post.length} chars, lines=${lines.size}, firstLine='${lines.firstOrNull()}'"
                            )
                        } catch (ve: Exception) {
                            AppLogger.logWebDAV("SYNC_RECORDS", "Post-write verify failed: ${ve.message}")
                        }
                        break
                    } else if (code == 412 || code == 409 || code == 423) {
                        // 412: 前置条件失败（If-Match/If-None-Match），409: 冲突，423: 文件被锁定（WebDAV Locked）
                        if (attempt >= maxRetries) throw RuntimeException("Conditional PUT failed after $maxRetries attempts (code=$code)")
                        val reason = if (code == 423) "Locked" else "Concurrency"
                        AppLogger.logWebDAV("SYNC_RECORDS", "$reason detected (code=$code), retrying... attempt $attempt/$maxRetries")
                        delay(350L * attempt)
                        continue
                    } else if (code == -1) {
                        if (attempt >= maxRetries) throw RuntimeException("Network error during conditional PUT after $maxRetries attempts")
                        delay(250L * attempt)
                        continue
                    } else {
                        throw RuntimeException("Unexpected response code: $code")
                    }
                }
                
                AppLogger.logWebDAV("SYNC_RECORDS", "Upload completed successfully")
                true
            } catch (e: Exception) {
                e.printStackTrace()
                AppLogger.logWebDAV("SYNC_RECORDS", "Failed to sync records: ${e.message}", e)
                false
            }
        }
    }

    override suspend fun listApkFiles(): List<FileManager.ApkFileInfo> = withContext(Dispatchers.IO) {
        try {
            val sardine = createSardineClient()
            val root = resolveRootPrefix(sardine)
            val apkUrl = buildUrl(root, apkDirectory)
            AppLogger.logWebDAV("APK_LIST", "Listing APK files from: $apkUrl")

            val resources = try {
                sardine.list(apkUrl)
            } catch (e: Exception) {
                AppLogger.logWebDAV("APK_LIST", "Error listing APK directory: ${e.message}", e)
                return@withContext emptyList<FileManager.ApkFileInfo>()
            }

            resources
                .filter { !it.isDirectory && it.name.endsWith(".apk", ignoreCase = true) }
                .map { toApkFileInfo(it) }
                .sortedByDescending { it.lastModified }
        } catch (e: Exception) {
            AppLogger.logWebDAV("APK_LIST", "Error retrieving APK list: ${e.message}", e)
            emptyList()
        }
    }

    override suspend fun downloadApk(apkFileName: String): ByteArray? = withContext(Dispatchers.IO) {
        try {
            val sardine = createSardineClient()
            val root = resolveRootPrefix(sardine)
            val apkPath = "$apkDirectory/$apkFileName"
            val apkUrl = buildUrl(root, apkPath)
            AppLogger.logWebDAV("APK_DOWNLOAD", "Downloading APK: $apkUrl")

            sardine.get(apkUrl).use { input ->
                input.readBytes()
            }
        } catch (e: Exception) {
            AppLogger.logWebDAV("APK_DOWNLOAD", "Error downloading APK $apkFileName: ${e.message}", e)
            null
        }
    }

    private fun toApkFileInfo(resource: DavResource): FileManager.ApkFileInfo {
        val name = resource.name
        val match = apkFileRegex.find(name)
        val versionName = match?.groupValues?.getOrNull(2)
        val buildNumber = match?.groupValues?.getOrNull(3)
        val size = resource.contentLength
        val modified = resource.modified?.time ?: System.currentTimeMillis()

        return FileManager.ApkFileInfo(
            fileName = name,
            versionName = versionName,
            buildNumber = buildNumber,
            sizeBytes = size,
            lastModified = modified
        )
    }

    private fun sanitize(value: String): String {
        return value.replace("[^\\p{L}\\p{N}_-]".toRegex(), "_")
    }

    private fun sanitizeFolderName(primary: String, secondary: String): String {
        val base = primary.ifEmpty { "未命名" }
        val secondaryPart = secondary.takeIf { it.isNotEmpty() }?.let { "_${it}" } ?: ""
        return sanitize(base + secondaryPart)
    }
    
    private fun ensureDirectoryExists(_sardine: Sardine, _path: String) { /* deprecated - keep for compatibility */ }
    
    private fun generateCSVContent(records: List<TestRecord>): String {
        val header = "序列号,测试人员,开始时间,结束时间,测试时长(分钟),状态,创建时间\n"
        val rows = records.joinToString("\n") { record ->
            val endTimeStr = record.endTime?.let { dateFormat.format(it) } ?: ""
            val durationStr = record.testDurationMinutes?.toString() ?: ""
            val status = if (record.isCompleted) "已完成" else "测试中"
            "${record.serialNumber},${record.tester},${dateFormat.format(record.startTime)},$endTimeStr,$durationStr,$status,${dateFormat.format(record.createdAt)}"
        }
        
        return header + rows
    }
    
    // 测试WebDAV连接 - 简化逻辑，对标SMB实现
    override suspend fun testConnection(): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val (actualUsername, actualPassword) = getCredentials()
                val baseUrl = getBaseUrl()
                
                // 先检查凭据
                if (actualUsername.isEmpty() || actualPassword.isEmpty()) {
                    AppLogger.log("WebDAVFileManager", "❌ 测试失败: 凭据为空 - username='$actualUsername', password=${if (actualPassword.isEmpty()) "空" else "已设置"}")
                    AppLogger.logWebDAV("TEST_CONNECTION", "❌ 测试失败: 凭据为空 - username='$actualUsername', password=${if (actualPassword.isEmpty()) "空" else "已设置"}")
                    return@withContext false
                }
                
                AppLogger.log("WebDAVFileManager", "开始测试WebDAV连接 - 服务器: $baseUrl, 用户: $actualUsername, 目标: $targetPath")
                AppLogger.logWebDAV("TEST_CONNECTION", "开始测试WebDAV连接...")
                AppLogger.logWebDAV("TEST_CONNECTION", "- 服务器: $baseUrl")
                AppLogger.logWebDAV("TEST_CONNECTION", "- 用户名: $actualUsername")
                AppLogger.logWebDAV("TEST_CONNECTION", "- 目标路径: $targetPath")
                
                val sardine: Sardine = try {
                    AppLogger.log("WebDAVFileManager", "正在创建Sardine客户端...")
                    createSardineClient()
                } catch (e: IllegalStateException) {
                    AppLogger.log("WebDAVFileManager", "❌ 创建客户端失败: ${e.message}")
                    AppLogger.logWebDAV("TEST_CONNECTION", "❌ 创建客户端失败: ${e.message}")
                    return@withContext false
                } catch (e: Exception) {
                    AppLogger.log("WebDAVFileManager", "❌ 创建客户端异常: ${e.javaClass.simpleName} - ${e.message}")
                    AppLogger.logWebDAV("TEST_CONNECTION", "❌ 创建客户端异常: ${e.javaClass.simpleName} - ${e.message}")
                    return@withContext false
                }
                
                // 使用固定根路径，不再探测
                val root = "/"
                val targetUrl = buildUrl(root, targetPath)
                
                AppLogger.log("WebDAVFileManager", "检查目标路径: $targetUrl")
                AppLogger.logWebDAV("TEST_CONNECTION", "检查目标路径: $targetUrl")
                
                // 检查目标路径是否存在 - 使用 list() 而不是 exists() 来避免 403 错误
                val targetExists = try {
                    // 尝试列出目录内容，这比 exists() 更可靠
                    sardine.list(targetUrl, 0)
                    AppLogger.logWebDAV("TEST_CONNECTION", "目标路径存在且可访问: $targetUrl")
                    true
                } catch (e: SardineException) {
                    when (e.statusCode) {
                        401 -> {
                            AppLogger.logWebDAV("TEST_CONNECTION", "❌ 认证失败(401): 用户名或密码错误")
                            return@withContext false
                        }
                        403 -> {
                            // 403 可能是 list() 方法被拒绝，尝试用其他方法验证
                            AppLogger.logWebDAV("TEST_CONNECTION", "⚠️ list()返回403，尝试使用exists()方法")
                            try {
                                val exists = sardine.exists(targetUrl)
                                AppLogger.logWebDAV("TEST_CONNECTION", "exists()方法${if (exists) "成功" else "失败"}: $targetUrl")
                                if (exists) {
                                    AppLogger.logWebDAV("TEST_CONNECTION", "✅ 目标路径存在（通过exists验证）")
                                    return@withContext true
                                }
                                false
                            } catch (e2: Exception) {
                                AppLogger.logWebDAV("TEST_CONNECTION", "exists()方法也失败: ${e2.message}")
                                // 如果两种方法都返回403，可能是权限问题，但也可能是服务器配置问题
                                // 尝试继续，让后续的创建目录操作来验证
                                false
                            }
                        }
                        404 -> {
                            AppLogger.logWebDAV("TEST_CONNECTION", "目标路径不存在(404): $targetUrl")
                            false
                        }
                        else -> {
                            AppLogger.logWebDAV("TEST_CONNECTION", "❌ HTTP错误(${e.statusCode}): ${e.message}")
                            false
                        }
                    }
                } catch (e: Exception) {
                    AppLogger.logWebDAV("TEST_CONNECTION", "❌ 检查路径异常: ${e.javaClass.simpleName} - ${e.message}")
                    if (e.message?.contains("Unable to resolve host") == true) {
                        AppLogger.logWebDAV("TEST_CONNECTION", "⚠️ 无法解析主机名，请检查网络连接和服务器地址")
                        return@withContext false
                    } else if (e.message?.contains("SSL") == true || e.message?.contains("certificate") == true) {
                        AppLogger.logWebDAV("TEST_CONNECTION", "⚠️ SSL证书错误，请检查服务器证书配置")
                        return@withContext false
                    }
                    false
                }
                
                if (targetExists) {
                    AppLogger.logWebDAV("TEST_CONNECTION", "✅ 连接测试成功: 目标目录已存在")
                    true
                } else {
                    // 尝试创建目录（对标SMB逻辑）
                    try {
                        AppLogger.logWebDAV("TEST_CONNECTION", "目标路径不存在，尝试创建: $targetPath")
                        ensureDirectoryExistsWithRoot(sardine, root, targetPath)
                        AppLogger.logWebDAV("TEST_CONNECTION", "✅ 连接测试成功: 目标目录已创建")
                        true
                    } catch (e: SardineException) {
                        AppLogger.logWebDAV("TEST_CONNECTION", "❌ 创建目录失败(${e.statusCode}): ${e.message}")
                        false
                    } catch (e: Exception) {
                        AppLogger.logWebDAV("TEST_CONNECTION", "❌ 创建目录异常: ${e.javaClass.simpleName} - ${e.message}")
                        false
                    }
                }
            } catch (e: Exception) {
                AppLogger.logWebDAV("TEST_CONNECTION", "❌ WebDAV连接测试失败: ${e.javaClass.simpleName} - ${e.message}", e)
                false
            }
        }
    }
    
    // 备用方法：保存到本地存储
    override suspend fun saveToLocalStorage(records: List<TestRecord>): String? {
        return withContext(Dispatchers.IO) {
            try {
                val csvContent = generateCSVContent(records)
                val fileName = "test_records_${fileNameFormat.format(Date())}.csv"
                val file = context.getExternalFilesDir(null)?.let { 
                    java.io.File(it, fileName)
                }
                
                // 本地保存同样加入 UTF-8 BOM 与 CRLF，确保本机 Excel 打开正常
                val normalized = csvContent.replace("\n", "\r\n")
                val bom = "\uFEFF"
                file?.writeText(bom + normalized, Charsets.UTF_8)
                file?.absolutePath
            } catch (e: Exception) {
                e.printStackTrace()
                null
            }
        }
    }

    // testers.json 同步
    override suspend fun fetchTesterList(): List<String> = withContext(Dispatchers.IO) {
        try {
            val (user, pass) = getCredentials()
            AppLogger.logWebDAV("FETCH_TESTERS", "Starting fetch testers list")
            val sardine: Sardine = createSardineClient()
            val root = resolveRootPrefix(sardine)
            
            // Try to ensure directory exists, but don't fail if 405
            try {
                ensureDirectoryExistsWithRoot(sardine, root, targetPath)
            } catch (e: SardineException) {
                if (e.statusCode == 405) {
                    AppLogger.logWebDAV("FETCH_TESTERS", "Directory creation not allowed (405), continuing with file operations")
                } else {
                    throw e
                }
            }
            
            val testersUrl = buildUrl(root, "$targetPath/$testersFileName")
            AppLogger.logWebDAV("FETCH_TESTERS", "Checking testers file at: $testersUrl")
            
            return@withContext try {
                if (sardine.exists(testersUrl)) {
                    val json = sardine.get(testersUrl).use { it.readBytes().toString(Charsets.UTF_8) }
                    AppLogger.logFileOperation("READ", testersUrl, true, "Successfully read testers file")
                    val testers = parseTesterJson(json)
                    AppLogger.logWebDAV("FETCH_TESTERS", "Successfully fetched ${testers.size} testers")
                    testers
                } else {
                    AppLogger.logWebDAV("FETCH_TESTERS", "Testers file does not exist")
                    emptyList()
                }
            } catch (e: SardineException) {
                if (e.statusCode == 404) {
                    AppLogger.logWebDAV("FETCH_TESTERS", "Testers file not found (404)")
                    emptyList()
                } else {
                    throw e
                }
            }
        } catch (e: Exception) {
            AppLogger.logWebDAV("FETCH_TESTERS", "Failed to fetch testers: ${e.message}", e)
            emptyList()
        }
    }

    override suspend fun saveTesterList(testers: List<String>): Boolean = withContext(Dispatchers.IO) {
        try {
            AppLogger.logWebDAV("SAVE_TESTERS", "Starting save testers list with ${testers.size} testers")
            val sardine: Sardine = createSardineClient()
            val root = resolveRootPrefix(sardine)
            
            // 确保目标目录存在
            try {
                ensureDirectoryExistsWithRoot(sardine, root, targetPath)
            } catch (e: Exception) {
                AppLogger.logWebDAV("SAVE_TESTERS", "Failed to ensure directory: ${e.message}")
            }
            
            val json = toTesterJson(testers)
            val testersPath = "$targetPath/$testersFileName"
            val fullUrl = buildUrl(root, testersPath)
            
            try {
                AppLogger.logWebDAV("SAVE_TESTERS", "Saving testers to: $fullUrl")
                sardine.put(fullUrl, json.toByteArray(Charsets.UTF_8), "application/json; charset=utf-8")
                AppLogger.logWebDAV("SAVE_TESTERS", "Successfully saved testers to: $fullUrl")
                return@withContext true
            } catch (e: Exception) {
                AppLogger.logWebDAV("SAVE_TESTERS", "Failed to save testers: ${e.message}")
                return@withContext false
            }
            
        } catch (e: Exception) {
            AppLogger.logWebDAV("SAVE_TESTERS", "Failed to save testers: ${e.message}", e)
            false
        }
    }

    override suspend fun fetchActiveTests(): List<FileManager.ActiveTest> = withContext(Dispatchers.IO) {
        val startTime = System.currentTimeMillis()
        try {
            val (user, _) = getCredentials()
            AppLogger.logWebDAV("FETCH_ACTIVE_TESTS", "Starting fetch active tests - user: $user, targetPath: $targetPath")
            val sardine: Sardine = createSardineClient()
            val root = resolveRootPrefix(sardine)
            AppLogger.logWebDAV("FETCH_ACTIVE_TESTS", "Resolved root prefix: '$root'")

            // Try to ensure directory exists, but don't fail if 405
            try {
                ensureDirectoryExistsWithRoot(sardine, root, targetPath)
                AppLogger.logWebDAV("FETCH_ACTIVE_TESTS", "Directory check/creation completed")
            } catch (e: SardineException) {
                if (e.statusCode == 405) {
                    AppLogger.logWebDAV("FETCH_ACTIVE_TESTS", "Directory creation not allowed (405), continuing with file operations")
                } else {
                    AppLogger.logWebDAV("FETCH_ACTIVE_TESTS", "Directory operation failed with status ${e.statusCode}: ${e.message}")
                    throw e
                }
            }

            val url = buildUrl(root, "$targetPath/$activeTestsFileName")
            AppLogger.logWebDAV("FETCH_ACTIVE_TESTS", "Fetching active tests from: $url")

            return@withContext try {
                // Some servers return false for exists(); read directly and handle 404
                val readStartTime = System.currentTimeMillis()
                val json = sardine.get(url).use { it.readBytes().toString(Charsets.UTF_8) }
                val readTime = System.currentTimeMillis() - readStartTime
                AppLogger.logFileOperation("READ", url, true, "Successfully read active tests file in ${readTime}ms, size: ${json.length} chars")
                
                val tests = parseActiveTestsJson(json)
                val totalTime = System.currentTimeMillis() - startTime
                AppLogger.logWebDAV("FETCH_ACTIVE_TESTS", "Successfully fetched ${tests.size} active tests in ${totalTime}ms")
                
                if (tests.isNotEmpty()) {
                    AppLogger.logWebDAV("FETCH_ACTIVE_TESTS", "Active tests found: ${tests.map { "SN='${it.serial}', tester='${it.tester}', start='${it.startTime}'" }}")
                } else {
                    AppLogger.logWebDAV("FETCH_ACTIVE_TESTS", "No active tests found in file")
                }
                
                tests
            } catch (e: SardineException) {
                val totalTime = System.currentTimeMillis() - startTime
                if (e.statusCode == 404) {
                    AppLogger.logWebDAV("FETCH_ACTIVE_TESTS", "Active tests file not found (404) at $url after ${totalTime}ms")
                    emptyList()
                } else if (e.statusCode == 403) {
                    AppLogger.logWebDAV("FETCH_ACTIVE_TESTS", "403 Forbidden when reading $url after ${totalTime}ms; treating as empty list")
                    emptyList()
                } else {
                    AppLogger.logWebDAV("FETCH_ACTIVE_TESTS", "HTTP ${e.statusCode} error when reading $url after ${totalTime}ms: ${e.message}")
                    throw e
                }
            }
        } catch (e: Exception) {
            val totalTime = System.currentTimeMillis() - startTime
            AppLogger.logWebDAV("FETCH_ACTIVE_TESTS", "Failed to fetch active tests after ${totalTime}ms: ${e.message}", e)
            emptyList()
        }
    }

    override suspend fun upsertActiveTest(serial: String, tester: String, startTime: Date): Boolean = withContext(Dispatchers.IO) {
        try {
            AppLogger.logWebDAV("UPSERT_ACTIVE_TEST", "Starting upsert for serial: $serial, tester: $tester")
            val current = fetchActiveTests().toMutableList()
            val fmt = dateFormat.format(startTime)
            val idx = current.indexOfFirst { it.serial == serial }
            if (idx >= 0) {
                current[idx] = FileManager.ActiveTest(serial, tester, fmt)
                AppLogger.logWebDAV("UPSERT_ACTIVE_TEST", "Updated existing test for serial: $serial")
            } else {
                current.add(FileManager.ActiveTest(serial, tester, fmt))
                AppLogger.logWebDAV("UPSERT_ACTIVE_TEST", "Added new test for serial: $serial")
            }
            saveActiveTests(current)
        } catch (e: Exception) {
            AppLogger.logWebDAV("UPSERT_ACTIVE_TEST", "Failed to upsert active test: $e", e)
            false
        }
    }

    override suspend fun removeActiveTest(serial: String): Boolean = withContext(Dispatchers.IO) {
        try {
            AppLogger.logWebDAV("REMOVE_ACTIVE_TEST", "Starting remove for serial: $serial")
            val current = fetchActiveTests().filterNot { it.serial == serial }
            AppLogger.logWebDAV("REMOVE_ACTIVE_TEST", "Removed test for serial: $serial")
            saveActiveTests(current)
        } catch (e: Exception) {
            AppLogger.logWebDAV("REMOVE_ACTIVE_TEST", "Failed to remove active test: $e", e)
            false
        }
    }

    private suspend fun saveActiveTests(list: List<FileManager.ActiveTest>): Boolean = withContext(Dispatchers.IO) {
        try {
            val (user, pass) = getCredentials()
            AppLogger.logWebDAV("SAVE_ACTIVE_TESTS", "Starting save active tests with ${list.size} tests")
            val sardine: Sardine = createSardineClient()
            val root = resolveRootPrefix(sardine)
            
            // Try to ensure directory exists, but don't fail if 405
            try {
                ensureDirectoryExistsWithRoot(sardine, root, targetPath)
            } catch (e: SardineException) {
                if (e.statusCode == 405) {
                    AppLogger.logWebDAV("SAVE_ACTIVE_TESTS", "Directory creation not allowed (405), continuing with file operations")
                } else {
                    throw e
                }
            }
            
            val url = buildUrl(root, "$targetPath/$activeTestsFileName")
            val json = toActiveTestsJson(list)
            AppLogger.logWebDAV("SAVE_ACTIVE_TESTS", "Saving active tests to: $url")
            // Retry on transient WebDAV errors and verify after write
            var success = false
            var attempt = 0
            val maxAttempts = 4
            attemptLoop@ while (attempt < maxAttempts) {
                attempt++
                try {
                    sardine.put(url, json.toByteArray(Charsets.UTF_8), "application/json; charset=utf-8")
                    AppLogger.logFileOperation("WRITE", url, true, "Successfully saved active tests file (attempt=$attempt)")
                    // Post-write verification (best-effort)
                    try {
                        val post = sardine.get(url).use { it.readBytes().toString(Charsets.UTF_8) }
                        val parsed = parseActiveTestsJson(post)
                        AppLogger.logWebDAV(
                            "SAVE_ACTIVE_TESTS",
                            "Post-write verify: size=${post.length} chars, parsedCount=${parsed.size}"
                        )
                    } catch (ve: Exception) {
                        AppLogger.logWebDAV("SAVE_ACTIVE_TESTS", "Post-write verify failed: ${ve.message}")
                    }
                    AppLogger.logWebDAV("SAVE_ACTIVE_TESTS", "Successfully saved active tests")
                    success = true
                    break@attemptLoop
                } catch (se: SardineException) {
                    if (se.statusCode == 409 || se.statusCode == 423) {
                        if (attempt >= maxAttempts) {
                            AppLogger.logWebDAV("SAVE_ACTIVE_TESTS", "Failed after $maxAttempts attempts: HTTP ${se.statusCode}", se)
                            success = false
                            break@attemptLoop
                        }
                        AppLogger.logWebDAV("SAVE_ACTIVE_TESTS", "Transient error ${se.statusCode}, retrying attempt $attempt/$maxAttempts")
                        delay(250L * attempt)
                        continue@attemptLoop
                    } else if (se.statusCode == 405) {
                        AppLogger.logWebDAV("SAVE_ACTIVE_TESTS", "405 on PUT; attempting read-back to confirm")
                        success = try {
                            sardine.get(url).close()
                            true
                        } catch (_: Exception) { false }
                        break@attemptLoop
                    } else {
                        AppLogger.logWebDAV("SAVE_ACTIVE_TESTS", "HTTP ${se.statusCode} saving active tests: ${se.message}", se)
                        success = false
                        break@attemptLoop
                    }
                } catch (e: Exception) {
                    if (attempt >= maxAttempts) {
                        AppLogger.logWebDAV("SAVE_ACTIVE_TESTS", "Failed after $maxAttempts attempts: ${e.message}", e)
                        success = false
                        break@attemptLoop
                    }
                    AppLogger.logWebDAV("SAVE_ACTIVE_TESTS", "Network error: ${e.message}, retrying attempt $attempt/$maxAttempts")
                    delay(250L * attempt)
                }
            }
            success
        } catch (e: Exception) {
            AppLogger.logWebDAV("SAVE_ACTIVE_TESTS", "Failed to save active tests: ${e.message}", e)
            false
        }
    }

    private fun parseTesterJson(json: String): List<String> {
        return try {
            val trimmed = json.trim()
            if (trimmed.startsWith("{")) {
                val key = "\"testers\""
                val start = trimmed.indexOf(key)
                if (start >= 0) {
                    val arrStart = trimmed.indexOf('[', start)
                    val arrEnd = trimmed.indexOf(']', arrStart)
                    if (arrStart > 0 && arrEnd > arrStart) {
                        val content = trimmed.substring(arrStart + 1, arrEnd)
                        content.split(',').mapNotNull {
                            it.trim().trim('"')
                        }.filter { it.isNotEmpty() }
                    } else emptyList()
                } else emptyList()
            } else if (trimmed.startsWith("[")) {
                trimmed.trim('[', ']').split(',').mapNotNull { it.trim().trim('"') }.filter { it.isNotEmpty() }
            } else emptyList()
        } catch (_: Exception) { emptyList() }
    }

    private fun toTesterJson(testers: List<String>): String {
        val quoted = testers.joinToString(",") { "\"$it\"" }
        return "{\"testers\":[${quoted}]}"
    }

    private fun parseActiveTestsJson(json: String): List<FileManager.ActiveTest> {
        return try {
            val trimmed = json.trim()
            // Expecting: {"active":[{"serial":"SN","tester":"T","startTime":"yyyy-MM-dd HH:mm:ss"}, ...]}
            val key = "\"active\""
            val start = trimmed.indexOf(key)
            if (start >= 0) {
                val arrStart = trimmed.indexOf('[', start)
                val arrEnd = trimmed.lastIndexOf(']')
                if (arrStart > 0 && arrEnd > arrStart) {
                    val content = trimmed.substring(arrStart + 1, arrEnd)
                    if (content.isBlank()) return emptyList()
                    content.split("},").mapNotNull { item ->
                        val obj = if (!item.trim().endsWith("}")) item + "}" else item
                        val s = extractJsonString(obj, "serial")
                        val t = extractJsonString(obj, "tester")
                        val st = extractJsonString(obj, "startTime")
                        if (s != null && t != null && st != null) FileManager.ActiveTest(s, t, st) else null
                    }
                } else emptyList()
            } else emptyList()
        } catch (_: Exception) { emptyList() }
    }

    private fun toActiveTestsJson(list: List<FileManager.ActiveTest>): String {
        val items = list.joinToString(",") { "{\"serial\":\"${it.serial}\",\"tester\":\"${it.tester}\",\"startTime\":\"${it.startTime}\"}" }
        return "{\"active\":[${items}]}"
    }

    private fun extractJsonString(obj: String, key: String): String? {
        return try {
            val k = "\"$key\""
            val i = obj.indexOf(k)
            if (i >= 0) {
                val c = obj.indexOf(':', i)
                val q1 = obj.indexOf('"', c + 1)
                val q2 = obj.indexOf('"', q1 + 1)
                if (q1 >= 0 && q2 > q1) obj.substring(q1 + 1, q2) else null
            } else null
        } catch (_: Exception) { null }
    }

    override suspend fun queryProductRecord(productSerial: String): FileManager.ProductRecord? {
        return withContext(Dispatchers.IO) {
            try {
                AppLogger.logWebDAV("QUERY_PRODUCT_RECORD", "Querying product record for: $productSerial")
                val sardine = createSardineClient()
                
                // 使用固定根路径，对标SMB实现
                val root = resolveRootPrefix(sardine)
                
                // 获取项目列表
                val projectList = try {
                    val projectsPath = "$targetPath/projects.json"
                    val projectsUrl = buildUrl(root, projectsPath)
                    
                    AppLogger.logWebDAV("QUERY_PRODUCT_RECORD", "Fetching projects from: $projectsUrl")
                    
                    if (sardine.exists(projectsUrl)) {
                        val content = String(sardine.get(projectsUrl).readBytes(), Charsets.UTF_8)
                        parseProjectsJson(content)
                    } else {
                        AppLogger.logWebDAV("QUERY_PRODUCT_RECORD", "projects.json not found, returning empty list")
                        emptyList()
                    }
                } catch (e: Exception) {
                    AppLogger.logWebDAV("QUERY_PRODUCT_RECORD", "Error reading projects.json: ${e.message}")
                    emptyList()
                }
                
                val searchPath = "$targetPath/record"
                AppLogger.logWebDAV("QUERY_PRODUCT_RECORD", "Searching for product record in ${projectList.size} project files")
                
                for (projectName in projectList) {
                    // 清理项目名作为文件名
                    val cleanProjectName = projectName.replace(" ", "_").replace("\\\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
                    
                    // 尝试新格式文件名：项目名称_产品类型.csv
                    val possibleFileNames = mutableListOf<String>()
                    
                    // 从当前项目配置获取所有可能的产品类型
                    try {
                        val configPath = "$targetPath/configs/${cleanProjectName}_config.json"
                        val configUrl = buildUrl(root, configPath)
                        
                        if (sardine.exists(configUrl)) {
                            val configContent = String(sardine.get(configUrl).readBytes(), Charsets.UTF_8)
                            // 简单解析产品类型
                            val productTypeRegex = "\"typeName\":\\s*\"([^\"]+)\"".toRegex()
                            val productTypes = productTypeRegex.findAll(configContent).map { it.groupValues[1] }.toList()
                            
                            for (productType in productTypes) {
                                val cleanProductType = productType.replace(" ", "_").replace("/", "_").replace("\\\\", "_")
                                    .replace(":", "_").replace("*", "_").replace("?", "_")
                                    .replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
                                possibleFileNames.add("${cleanProjectName}_${cleanProductType}.csv")
                            }
                            AppLogger.logWebDAV("QUERY_PRODUCT_RECORD", "Found ${productTypes.size} product types for project $projectName")
                        }
                    } catch (e: Exception) {
                        AppLogger.logWebDAV("QUERY_PRODUCT_RECORD", "Failed to read project config for $projectName: ${e.message}")
                    }
                    
                    // 如果没有找到配置，尝试常见的产品类型
                    if (possibleFileNames.isEmpty()) {
                        val commonProductTypes = listOf("电机", "电机控制器", "控制器", "驱动器")
                        for (productType in commonProductTypes) {
                            possibleFileNames.add("${cleanProjectName}_${productType}.csv")
                        }
                    }
                    
                    // 兼容旧格式：项目名称.csv
                    possibleFileNames.add("$cleanProjectName.csv")
                    
                    AppLogger.logWebDAV("QUERY_PRODUCT_RECORD", "Trying ${possibleFileNames.size} possible files for project $projectName")
                    
                    // 尝试所有可能的文件名
                    for (fileName in possibleFileNames) {
                        val filePath = "$searchPath/$fileName"
                        val fileUrl = buildUrl(root, filePath)
                        
                        try {
                            AppLogger.logWebDAV("QUERY_PRODUCT_RECORD", "Checking file: $fileUrl")
                            
                            if (sardine.exists(fileUrl)) {
                                val content = String(sardine.get(fileUrl).readBytes(), Charsets.UTF_8)
                                val record = parseProductRecordFromCSV(content, productSerial)
                                if (record != null) {
                                    AppLogger.logWebDAV("QUERY_PRODUCT_RECORD", "✓ Found product record in file: $fileName")
                                    return@withContext record
                                }
                            }
                        } catch (e: Exception) {
                            AppLogger.logWebDAV("QUERY_PRODUCT_RECORD", "Error checking file $fileName: ${e.message}")
                        }
                    }
                }
                
                AppLogger.logWebDAV("QUERY_PRODUCT_RECORD", "Product record not found in any project file")
                null
            } catch (e: Exception) {
                AppLogger.logWebDAV("QUERY_PRODUCT_RECORD", "Error querying product record: ${e.message}", e)
                null
            }
        }
    }
    
    private fun parseProductRecordFromCSV(csvContent: String, targetSerial: String): FileManager.ProductRecord? {
        AppLogger.log("WebDAVFileManager", "Parsing CSV for serial: $targetSerial")
        AppLogger.log("WebDAVFileManager", "CSV content: $csvContent")
        
        val lines = csvContent.split("\n")
        AppLogger.log("WebDAVFileManager", "CSV lines count: ${lines.size}")
        
        if (lines.size < 2) {
            AppLogger.log("WebDAVFileManager", "Not enough lines in CSV")
            return null
        }
        
        // Log header
        if (lines.isNotEmpty()) {
            AppLogger.log("WebDAVFileManager", "CSV header: ${lines[0]}")
        }
        
        // Skip header, find matching product serial
        for (i in 1 until lines.size) {
            val line = lines[i].trim()
            if (line.isEmpty()) continue
            
            AppLogger.log("WebDAVFileManager", "Processing line $i: $line")
            val columns = line.split(",")
            AppLogger.log("WebDAVFileManager", "Columns count: ${columns.size}, columns: $columns")
            
            if (columns.size >= 9 && columns[0].trim() == targetSerial) {
                val record = FileManager.ProductRecord(
                    productSerial = columns[0].trim(),
                    projectName = columns[1].trim(),
                    operator = columns[2].trim(),
                    scanTime = columns[3].trim(),
                    controlBoard = columns[4].trim(),
                    drivingCapacitor = columns[5].trim(),
                    pumpCapacitor = columns[6].trim(),
                    drivingPower = columns[7].trim(),
                    pumpPower = columns[8].trim()
                )
                AppLogger.log("WebDAVFileManager", "Found matching record: $record")
                return record
            } else {
                AppLogger.log("WebDAVFileManager", "Line doesn't match: serial=${columns.getOrNull(0)?.trim()}, target=$targetSerial")
            }
        }
        
        AppLogger.log("WebDAVFileManager", "No matching record found for serial: $targetSerial")
        return null
    }
    
    override suspend fun fetchProjectList(): List<String> {
        return withContext(Dispatchers.IO) {
            try {
                AppLogger.logWebDAV("FETCH_PROJECT_LIST", "Fetching project list from server")
                val sardine = createSardineClient()
                
                // 使用固定路径，对标SMB实现
                val root = resolveRootPrefix(sardine)
                val projectsPath = "$targetPath/projects.json"
                val projectsUrl = buildUrl(root, projectsPath)
                
                AppLogger.logWebDAV("FETCH_PROJECT_LIST", "Trying to fetch projects from: $projectsUrl")
                
                try {
                    if (sardine.exists(projectsUrl)) {
                        val content = String(sardine.get(projectsUrl).readBytes(), Charsets.UTF_8)
                        AppLogger.logWebDAV("FETCH_PROJECT_LIST", "Found projects file, content length: ${content.length}")
                        return@withContext parseProjectsJson(content)
                    } else {
                        AppLogger.logWebDAV("FETCH_PROJECT_LIST", "projects.json not found")
                    }
                } catch (e: Exception) {
                    AppLogger.logWebDAV("FETCH_PROJECT_LIST", "Failed to fetch projects: ${e.message}")
                }
                
                AppLogger.logWebDAV("FETCH_PROJECT_LIST", "No projects file found, returning empty list")
                emptyList()
            } catch (e: Exception) {
                AppLogger.logWebDAV("FETCH_PROJECT_LIST", "Error fetching project list: ${e.message}", e)
                emptyList()
            }
        }
    }
    
    override suspend fun saveProjectList(projects: List<String>): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                AppLogger.logWebDAV("SAVE_PROJECT_LIST", "Saving project list to server: ${projects.size} projects")
                val sardine = createSardineClient()
                
                // 使用固定路径，对标SMB实现
                val root = resolveRootPrefix(sardine)
                val projectsPath = "$targetPath/projects.json"
                val projectsUrl = buildUrl(root, projectsPath)
                
                val projectsJson = generateProjectsJson(projects)
                AppLogger.logWebDAV("SAVE_PROJECT_LIST", "Generated projects JSON, length: ${projectsJson.length}")
                AppLogger.logWebDAV("SAVE_PROJECT_LIST", "Trying to save projects to: $projectsUrl")
                
                try {
                    val jsonBytes = projectsJson.toByteArray(Charsets.UTF_8)
                    sardine.put(projectsUrl, jsonBytes)
                    AppLogger.logWebDAV("SAVE_PROJECT_LIST", "Successfully saved projects to: $projectsUrl")
                    return@withContext true
                } catch (e: Exception) {
                    AppLogger.logWebDAV("SAVE_PROJECT_LIST", "Failed to save projects: ${e.message}")
                    return@withContext false
                }
            } catch (e: Exception) {
                AppLogger.logWebDAV("SAVE_PROJECT_LIST", "Error saving project list: ${e.message}", e)
                false
            }
        }
    }
    
    private fun parseProjectsJson(jsonContent: String): List<String> {
        return try {
            val trimmed = jsonContent.trim()
            AppLogger.log("WebDAVFileManager", "Parsing projects JSON: $trimmed")
            
            // Simple JSON parsing for projects array
            val key = "\"projects\""
            val start = trimmed.indexOf(key)
            if (start >= 0) {
                val arrStart = trimmed.indexOf('[', start)
                val arrEnd = trimmed.lastIndexOf(']')
                if (arrStart > 0 && arrEnd > arrStart) {
                    val content = trimmed.substring(arrStart + 1, arrEnd)
                    if (content.isBlank()) return emptyList()
                    
                    // Parse project names from JSON array
                    val projects = mutableListOf<String>()
                    val items = content.split(",")
                    for (item in items) {
                        val cleaned = item.trim().removeSurrounding("\"")
                        if (cleaned.isNotEmpty()) {
                            projects.add(cleaned)
                        }
                    }
                    AppLogger.log("WebDAVFileManager", "Parsed ${projects.size} projects: $projects")
                    return projects
                } else {
                    AppLogger.log("WebDAVFileManager", "Invalid JSON array structure")
                    emptyList()
                }
            } else {
                AppLogger.log("WebDAVFileManager", "No projects key found in JSON")
                emptyList()
            }
        } catch (e: Exception) {
            AppLogger.log("WebDAVFileManager", "Error parsing projects JSON: ${e.message}", e)
            emptyList()
        }
    }
    
    private fun generateProjectsJson(projects: List<String>): String {
        val projectsArray = projects.joinToString(",") { "\"$it\"" }
        return "{\"projects\":[$projectsArray]}"
    }
    
    private fun updateExistingRecord(existingContent: String, newDataLine: String, productSerial: String): String {
        val lines = existingContent.split("\n").toMutableList()
        var recordFound = false
        
        AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] ===== Start updateExistingRecord =====")
        AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] Target product serial: '$productSerial'")
        AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] Total lines in file: ${lines.size}")
        AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] New data line: $newDataLine")
        
        // Find and update existing record
        for (i in 1 until lines.size) { // Skip header (index 0)
            val line = lines[i].trim()
            if (line.isEmpty()) {
                AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] Line $i is empty, skipping")
                continue
            }
            
            val columns = line.split(",")
            val existingSerial = columns.getOrNull(0)?.trim() ?: ""
            AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] Line $i: serial='$existingSerial', comparing with '$productSerial'")
            
            if (columns.isNotEmpty() && existingSerial == productSerial) {
                AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] ✓ MATCH FOUND at line $i!")
                AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] Existing line: $line")
                
                // Parse new data
                val newColumns = newDataLine.split(",")
                AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] New columns count: ${newColumns.size}, Existing columns count: ${columns.size}")
                
                // Merge data: keep existing non-empty values, update with new non-empty values
                val mergedColumns = mutableListOf<String>()
                
                for (j in 0 until maxOf(columns.size, newColumns.size)) {
                    val existingValue = columns.getOrNull(j)?.trim() ?: ""
                    val newValue = newColumns.getOrNull(j)?.trim() ?: ""
                    
                    // Use new value if it's not empty, otherwise keep existing value
                    val finalValue = if (newValue.isNotEmpty()) newValue else existingValue
                    mergedColumns.add(finalValue)
                    
                    if (j < 5 || existingValue != finalValue) {  // Log first 5 columns or changed values
                        AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] Column $j: existing='$existingValue', new='$newValue', final='$finalValue'")
                    }
                }
                
                lines[i] = mergedColumns.joinToString(",")
                recordFound = true
                AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] ✓ Record updated successfully")
                AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] Updated line: ${lines[i]}")
                break
            } else {
                AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] ✗ No match (serial mismatch or empty)")
            }
        }
        
        // If no existing record found, append new record
        if (!recordFound) {
            AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] ✗ No existing record found, appending new record")
            lines.add(newDataLine)
            AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] New line added at position ${lines.size - 1}")
        }
        
        val result = lines.joinToString("\n")
        AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] Final content has ${lines.size} lines")
        AppLogger.log("WebDAVFileManager", "[UPDATE_DEBUG] ===== End updateExistingRecord =====")
        return result
    }
    
    override suspend fun fetchProjectConfig(projectName: String): ProjectConfig? {
        return withContext(Dispatchers.IO) {
            try {
                AppLogger.logWebDAV("FETCH_PROJECT_CONFIG", "Fetching project config for: $projectName")
                val sardine = createSardineClient()
                
                // 不清理项目名称 - 直接使用原始名称
                val fileName = "$projectName.json"
                
                // 解析根路径并构建完整路径
                val root = resolveRootPrefix(sardine)
                AppLogger.logWebDAV("FETCH_PROJECT_CONFIG", "Resolved root: $root")
                
                val projectConfigPath = "$targetPath/projects/$fileName"
                val fullUrl = buildUrl(root, projectConfigPath)
                
                AppLogger.logWebDAV("FETCH_PROJECT_CONFIG", "Trying to fetch config from: $fullUrl")
                
                try {
                    if (sardine.exists(fullUrl)) {
                        val content = String(sardine.get(fullUrl).readBytes(), Charsets.UTF_8)
                        AppLogger.logWebDAV("FETCH_PROJECT_CONFIG", "Found config file, content length: ${content.length}")
                        
                        // ===== 详细日志：原始 JSON 内容 =====
                        AppLogger.logWebDAV("FETCH_PROJECT_CONFIG", "[JSON_DEBUG] Raw JSON content:")
                        AppLogger.logWebDAV("FETCH_PROJECT_CONFIG", "[JSON_DEBUG] $content")
                        // ===== 结束详细日志 =====
                        
                        val config = ProjectConfig.fromJson(content)
                        AppLogger.logWebDAV("FETCH_PROJECT_CONFIG", "Successfully parsed config: projectName=${config.projectName}, version=${config.version}, productTypes=${config.productTypes.size}")
                        
                        // ===== 详细日志：解析后的配置 =====
                        config.productTypes.forEachIndexed { index, productType ->
                            AppLogger.logWebDAV("FETCH_PROJECT_CONFIG", "[PARSE_DEBUG] ProductType[$index]: name='${productType.typeName}', materials=${productType.materials.size}")
                            productType.materials.forEachIndexed { mIndex, material ->
                                AppLogger.logWebDAV("FETCH_PROJECT_CONFIG", "[PARSE_DEBUG]   Material[$mIndex]: name='${material.name}', partNumber='${material.partNumber}'")
                            }
                        }
                        // ===== 结束详细日志 =====
                        
                        return@withContext config
                    } else {
                        AppLogger.logWebDAV("FETCH_PROJECT_CONFIG", "Config file does not exist: $fullUrl")
                    }
                } catch (e: Exception) {
                    AppLogger.logWebDAV("FETCH_PROJECT_CONFIG", "Failed to fetch from $fullUrl: ${e.message}", e)
                }
                
                AppLogger.logWebDAV("FETCH_PROJECT_CONFIG", "No config file found for $projectName")
                null
            } catch (e: Exception) {
                AppLogger.logWebDAV("FETCH_PROJECT_CONFIG", "Error fetching project config: ${e.message}", e)
                null
            }
        }
    }
    
    override suspend fun saveProjectConfig(config: ProjectConfig): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                AppLogger.logWebDAV("SAVE_PROJECT_CONFIG", "Saving project config for: ${config.projectName}")
                val sardine = createSardineClient()
                
                // 不清理项目名称 - 直接使用原始名称
                val fileName = "${config.projectName}.json"
                
                // 解析根路径并构建完整路径
                val root = resolveRootPrefix(sardine)
                AppLogger.logWebDAV("SAVE_PROJECT_CONFIG", "Resolved root: $root")
                
                // 确保 projects 目录存在
                val projectsDir = "$targetPath/projects"
                try {
                    ensureDirectoryExistsWithRoot(sardine, root, projectsDir)
                    AppLogger.logWebDAV("SAVE_PROJECT_CONFIG", "Projects directory ensured: $projectsDir")
                } catch (e: Exception) {
                    AppLogger.logWebDAV("SAVE_PROJECT_CONFIG", "Failed to create projects directory: ${e.message}", e)
                }
                
                val projectConfigPath = "$projectsDir/$fileName"
                val fullUrl = buildUrl(root, projectConfigPath)
                
                val configJson = config.toJson()
                AppLogger.logWebDAV("SAVE_PROJECT_CONFIG", "Generated config JSON, length: ${configJson.length}")
                AppLogger.logWebDAV("SAVE_PROJECT_CONFIG", "Trying to save config to: $fullUrl")
                
                try {
                    val jsonBytes = configJson.toByteArray(Charsets.UTF_8)
                    sardine.put(fullUrl, jsonBytes)
                    AppLogger.logWebDAV("SAVE_PROJECT_CONFIG", "Successfully saved config to: $fullUrl")
                    return@withContext true
                } catch (e: Exception) {
                    AppLogger.logWebDAV("SAVE_PROJECT_CONFIG", "Failed to save to $fullUrl: ${e.message}", e)
                    return@withContext false
                }
            } catch (e: Exception) {
                AppLogger.logWebDAV("SAVE_PROJECT_CONFIG", "Error saving project config: ${e.message}", e)
                false
            }
        }
    }
    
    /**
     * Upload photo to WebDAV server
     * Photos are saved to: /mes/QRMES/picture/{projectFolder}/{productTypeFolder}/{productSerial}/{fileName}
     */
    override suspend fun uploadPhoto(directoryInfo: FileManager.PhotoDirectoryInfo, fileName: String, photoBytes: ByteArray): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val sardine = createSardineClient()
                AppLogger.logWebDAV("UPLOAD_PHOTO", "Uploading photo: $fileName for product: ${directoryInfo.productSerial}")
                
                // 解析根路径
                val root = resolveRootPrefix(sardine)
                AppLogger.logWebDAV("UPLOAD_PHOTO", "Resolved root: $root")
                
                // 构建完整的层级路径: picture/{projectName}_{projectCode}/{productType}_{modelNumber}/{productSerial}
                val pictureDir = "$targetPath/picture"
                val projectFolder = sanitizeFolderName(directoryInfo.projectName, directoryInfo.projectCode)
                val productTypeFolder = sanitizeFolderName(directoryInfo.productType, directoryInfo.modelNumber)
                val serialFolder = sanitize(directoryInfo.productSerial)
                
                val projectDir = "$pictureDir/$projectFolder"
                val productTypeDir = "$projectDir/$productTypeFolder"
                val productDir = "$productTypeDir/$serialFolder"
                
                AppLogger.logWebDAV("UPLOAD_PHOTO", "Full path: $productDir")
                
                // 确保完整的目录层级存在
                try {
                    ensureDirectoryExistsWithRoot(sardine, root, pictureDir)
                    ensureDirectoryExistsWithRoot(sardine, root, projectDir)
                    ensureDirectoryExistsWithRoot(sardine, root, productTypeDir)
                    ensureDirectoryExistsWithRoot(sardine, root, productDir)
                    AppLogger.logWebDAV("UPLOAD_PHOTO", "Directory hierarchy ensured")
                } catch (e: Exception) {
                    AppLogger.logWebDAV("UPLOAD_PHOTO", "Warning: Could not create directory hierarchy: ${e.message}")
                }
                
                // 上传照片文件
                val photoPath = "$productDir/$fileName"
                val fullUrl = buildUrl(root, photoPath)
                
                AppLogger.logWebDAV("UPLOAD_PHOTO", "Uploading to: $fullUrl")
                
                try {
                    sardine.put(fullUrl, photoBytes)
                    AppLogger.logWebDAV("UPLOAD_PHOTO", "Successfully uploaded photo: $fullUrl (${photoBytes.size} bytes)")
                    return@withContext true
                } catch (e: Exception) {
                    AppLogger.logWebDAV("UPLOAD_PHOTO", "Failed to upload to $fullUrl: ${e.message}", e)
                    return@withContext false
                }
            } catch (e: Exception) {
                AppLogger.logWebDAV("UPLOAD_PHOTO", "Error uploading photo: ${e.message}", e)
                false
            }
        }
    }
    
    /**
     * List photos for a product from WebDAV server
     * 兼容策略：先尝试新路径（完整层级），如果找不到则尝试旧路径
     */
    override suspend fun listPhotos(directoryInfo: FileManager.PhotoDirectoryInfo): List<FileManager.PhotoInfo> {
        return withContext(Dispatchers.IO) {
            try {
                val webdav = createSardineClient()
                AppLogger.logWebDAV("LIST_PHOTOS", "Listing photos for product: ${directoryInfo.productSerial}")
                
                val root = resolveRootPrefix(webdav)
                val pictureDir = "$targetPath/picture"
                val serialFolder = sanitize(directoryInfo.productSerial)
                
                // 策略1: 尝试新路径（完整层级）
                val projectFolder = sanitizeFolderName(directoryInfo.projectName, directoryInfo.projectCode)
                val productTypeFolder = sanitizeFolderName(directoryInfo.productType, directoryInfo.modelNumber)
                val newPathDir = "$pictureDir/$projectFolder/$productTypeFolder/$serialFolder"
                val newPathUrl = buildUrl(root, newPathDir)
                
                AppLogger.logWebDAV("LIST_PHOTOS", "Trying new path: $newPathUrl")
                
                try {
                    val resources = webdav.list(newPathUrl)
                    val photos = resources
                        .filter { !it.isDirectory && !it.name.startsWith(".") &&
                            (it.name.endsWith(".jpg", ignoreCase = true) ||
                             it.name.endsWith(".jpeg", ignoreCase = true) ||
                             it.name.endsWith(".png", ignoreCase = true))
                        }
                        .map { FileManager.PhotoInfo(
                            fileName = it.name,
                            filePath = "$newPathDir/${it.name}",
                            fileSize = it.contentLength,
                            lastModified = it.modified?.time ?: System.currentTimeMillis()
                        )}
                        .sortedByDescending { it.lastModified }
                    
                    if (photos.isNotEmpty()) {
                        AppLogger.logWebDAV("LIST_PHOTOS", "Found ${photos.size} photos in new path")
                        return@withContext photos
                    }
                } catch (e: Exception) {
                    AppLogger.logWebDAV("LIST_PHOTOS", "New path not accessible: ${e.message}")
                }
                
                // 策略2: 搜索旧路径（只有序列号）
                val oldPathDir = "$pictureDir/$serialFolder"
                val oldPathUrl = buildUrl(root, oldPathDir)
                
                AppLogger.logWebDAV("LIST_PHOTOS", "Trying old path: $oldPathUrl")
                
                try {
                    val resources = webdav.list(oldPathUrl)
                    val photos = resources
                        .filter { !it.isDirectory && !it.name.startsWith(".") &&
                            (it.name.endsWith(".jpg", ignoreCase = true) ||
                             it.name.endsWith(".jpeg", ignoreCase = true) ||
                             it.name.endsWith(".png", ignoreCase = true))
                        }
                        .map { FileManager.PhotoInfo(
                            fileName = it.name,
                            filePath = "$oldPathDir/${it.name}",
                            fileSize = it.contentLength,
                            lastModified = it.modified?.time ?: System.currentTimeMillis()
                        )}
                        .sortedByDescending { it.lastModified }
                    
                    if (photos.isNotEmpty()) {
                        AppLogger.logWebDAV("LIST_PHOTOS", "Found ${photos.size} photos in old path")
                        return@withContext photos
                    }
                } catch (e: Exception) {
                    AppLogger.logWebDAV("LIST_PHOTOS", "Old path not accessible: ${e.message}")
                }
                
                AppLogger.logWebDAV("LIST_PHOTOS", "No photos found")
                emptyList()
            } catch (e: Exception) {
                AppLogger.logWebDAV("LIST_PHOTOS", "Error listing photos: ${e.message}", e)
                emptyList()
            }
        }
    }
    
    /**
     * Download photo from WebDAV server
     */
    override suspend fun downloadPhoto(directoryInfo: FileManager.PhotoDirectoryInfo, fileName: String): ByteArray? {
        return withContext(Dispatchers.IO) {
            try {
                val sardine = createSardineClient()
                AppLogger.logWebDAV("DOWNLOAD_PHOTO", "Downloading photo: $fileName for product: ${directoryInfo.productSerial}")
                
                // 解析根路径
                val root = resolveRootPrefix(sardine)
                
                // 构建完整的层级路径
                val pictureDir = "$targetPath/picture"
                val projectFolder = sanitizeFolderName(directoryInfo.projectName, directoryInfo.projectCode)
                val productTypeFolder = sanitizeFolderName(directoryInfo.productType, directoryInfo.modelNumber)
                val serialFolder = sanitize(directoryInfo.productSerial)
                
                val productDir = "$pictureDir/$projectFolder/$productTypeFolder/$serialFolder"
                val photoPath = "$productDir/$fileName"
                val fullUrl = buildUrl(root, photoPath)
                
                AppLogger.logWebDAV("DOWNLOAD_PHOTO", "Photo path: $fullUrl")
                
                // 检查文件是否存在
                try {
                    if (!sardine.exists(fullUrl)) {
                        AppLogger.logWebDAV("DOWNLOAD_PHOTO", "Photo file does not exist: $fullUrl")
                        return@withContext null
                    }
                } catch (e: Exception) {
                    AppLogger.logWebDAV("DOWNLOAD_PHOTO", "Error checking file existence: ${e.message}")
                    return@withContext null
                }
                
                // 下载文件内容
                val photoBytes = sardine.get(fullUrl).use { inputStream ->
                    inputStream.readBytes()
                }
                
                AppLogger.logWebDAV("DOWNLOAD_PHOTO", "Successfully downloaded photo: $fullUrl (${photoBytes.size} bytes)")
                photoBytes
            } catch (e: Exception) {
                AppLogger.logWebDAV("DOWNLOAD_PHOTO", "Error downloading photo: ${e.message}", e)
                null
            }
        }
    }
}
