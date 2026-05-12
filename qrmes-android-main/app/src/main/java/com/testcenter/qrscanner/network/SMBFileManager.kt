package com.testcenter.qrscanner.network

import android.content.Context
import com.hierynomus.msdtyp.AccessMask
import com.hierynomus.msfscc.FileAttributes
import com.hierynomus.msfscc.fileinformation.FileIdBothDirectoryInformation
import com.hierynomus.mssmb2.SMB2CreateDisposition
import com.hierynomus.mssmb2.SMB2CreateOptions
import com.hierynomus.mssmb2.SMB2ShareAccess
import com.hierynomus.smbj.SMBClient
import com.hierynomus.smbj.auth.AuthenticationContext
import com.hierynomus.smbj.connection.Connection
import com.hierynomus.smbj.session.Session
import com.hierynomus.smbj.share.DiskShare
import com.hierynomus.msdtyp.FileTime
import com.testcenter.qrscanner.data.ProjectConfig
import com.testcenter.qrscanner.data.TestRecord
import com.testcenter.qrscanner.utils.PreferencesManager
import com.testcenter.qrscanner.utils.AppLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.EnumSet
import java.util.concurrent.ConcurrentHashMap

class SMBFileManager(
    private val context: Context,
    private val username: String? = null,
    private val password: String? = null
) : FileManager {
    
    private val serverAddress = "172.16.30.10"
    private val shareName = "mes"
    private val targetPath = "QRMES"
    private val testersFileName = "testers.json"
    private val activeTestsFileName = "active_tests.json"
    private val apkDirectory = "$targetPath\\APK"
    private val apkFileRegex = "(?i)^(.+)\\s+v([0-9.]+)(?:_(\\d+))?\\.apk$".toRegex()
    
    private val preferencesManager = PreferencesManager(context)
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
    private val fileNameFormat = SimpleDateFormat("yyyyMMdd", Locale.getDefault())
    private val photoDirectoryCache = ConcurrentHashMap<String, String>()
    
    // 获取实际的登录凭据
    private fun getCredentials(): Triple<String, String, String> {
        val actualUsername = username ?: preferencesManager.getUsername() ?: ""
        val actualPassword = password ?: preferencesManager.getPassword() ?: ""
        val actualDomain = preferencesManager.getDomain() ?: ""
        return Triple(actualUsername, actualPassword, actualDomain)
    }
    
    private suspend fun <T> withSMBConnection(operation: suspend (DiskShare) -> T): T {
        return withContext(Dispatchers.IO) {
            val (user, pass, domain) = getCredentials()
            val client = SMBClient()
            var connection: Connection? = null
            var session: Session? = null
            var share: DiskShare? = null
            
            try {
                AppLogger.logSMB("CONNECTION", "Connecting to SMB server: $serverAddress")
                connection = client.connect(serverAddress)
                
                val authContext = AuthenticationContext(user, pass.toCharArray(), domain)
                session = connection.authenticate(authContext)
                AppLogger.logSMB("CONNECTION", "SMB authentication successful")
                
                share = session.connectShare(shareName) as DiskShare
                AppLogger.logSMB("CONNECTION", "Connected to share: $shareName")
                
                operation(share)
            } catch (e: Exception) {
                AppLogger.logSMB("CONNECTION", "SMB operation failed: ${e.message}", e)
                throw e
            } finally {
                try {
                    share?.close()
                    session?.close()
                    connection?.close()
                    client.close()
                } catch (e: Exception) {
                    AppLogger.logSMB("CONNECTION", "Error closing SMB connection: ${e.message}")
                }
            }
        }
    }

    private fun buildPhotoCacheKey(directoryInfo: FileManager.PhotoDirectoryInfo): String {
        return listOf(
            sanitizeFolderName(directoryInfo.projectName, directoryInfo.projectCode),
            sanitizeFolderName(directoryInfo.productType, directoryInfo.modelNumber),
            sanitize(directoryInfo.productSerial)
        ).joinToString("|")
    }

    override suspend fun listApkFiles(): List<FileManager.ApkFileInfo> = withContext(Dispatchers.IO) {
        try {
            withSMBConnection { share ->
                ensureDirectoryExists(share, apkDirectory)
                val entries = try {
                    share.list(apkDirectory)
                } catch (e: Exception) {
                    AppLogger.logSMB("APK_LIST", "Failed to list APK directory $apkDirectory: ${e.message}", e)
                    return@withSMBConnection emptyList<FileManager.ApkFileInfo>()
                }

                entries
                    .filterIsInstance<FileIdBothDirectoryInformation>()
                    .filter { (it.fileAttributes and FileAttributes.FILE_ATTRIBUTE_DIRECTORY.value) == 0L }
                    .filter { it.fileName.endsWith(".apk", ignoreCase = true) }
                    .map { toApkFileInfo(it) }
                    .sortedByDescending { it.lastModified }
            }
        } catch (e: Exception) {
            AppLogger.logSMB("APK_LIST", "Error retrieving APK list: ${e.message}", e)
            emptyList()
        }
    }

    override suspend fun downloadApk(apkFileName: String): ByteArray? = withContext(Dispatchers.IO) {
        try {
            withSMBConnection { share ->
                val filePath = "$apkDirectory\\$apkFileName"
                AppLogger.logSMB("APK_DOWNLOAD", "Downloading APK from $filePath")
                if (!share.fileExists(filePath)) {
                    AppLogger.logSMB("APK_DOWNLOAD", "APK file not found: $filePath")
                    return@withSMBConnection null
                }

                val file = share.openFile(
                    filePath,
                    EnumSet.of(AccessMask.GENERIC_READ),
                    EnumSet.of(FileAttributes.FILE_ATTRIBUTE_NORMAL),
                    SMB2ShareAccess.ALL,
                    SMB2CreateDisposition.FILE_OPEN,
                    EnumSet.noneOf(SMB2CreateOptions::class.java)
                )

                file.use { f ->
                    f.inputStream.use { it.readBytes() }
                }
            }
        } catch (e: Exception) {
            AppLogger.logSMB("APK_DOWNLOAD", "Error downloading APK $apkFileName: ${e.message}", e)
            null
        }
    }

    private fun FileTime?.toSafeEpochMillis(): Long {
        if (this == null) return 0L
        return try {
            this.toEpochMillis()
        } catch (e: Exception) {
            AppLogger.logSMB("APK_LIST", "Failed to convert FileTime: ${e.message}", e)
            0L
        }
    }

    private fun toApkFileInfo(info: FileIdBothDirectoryInformation): FileManager.ApkFileInfo {
        val name = info.fileName
        val match = apkFileRegex.find(name)
        val versionName = match?.groupValues?.getOrNull(2)
        val buildNumber = match?.groupValues?.getOrNull(3)
        val size = info.endOfFile
        val modified = info.lastWriteTime.toSafeEpochMillis()

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
    
    private fun ensureDirectoryExists(share: DiskShare, path: String) {
        try {
            val pathParts = path.split("/", "\\").filter { it.isNotEmpty() }
            var currentPath = ""
            
            for (part in pathParts) {
                currentPath = if (currentPath.isEmpty()) part else "$currentPath\\$part"
                
                AppLogger.logSMB("CREATE_DIR", "Checking directory: $currentPath")
                
                if (!share.folderExists(currentPath)) {
                    try {
                        share.mkdir(currentPath)
                        AppLogger.logSMB("CREATE_DIR", "Successfully created directory: $currentPath")
                    } catch (e: Exception) {
                        AppLogger.logSMB("CREATE_DIR", "Failed to create directory $currentPath: ${e.message}")
                        // Continue - directory might already exist or we might not have permissions
                    }
                } else {
                    AppLogger.logSMB("CREATE_DIR", "Directory already exists: $currentPath")
                }
            }
        } catch (e: Exception) {
            AppLogger.logSMB("CREATE_DIR", "Failed to ensure directory exists for path: $path", e)
            throw e
        }
    }
    
    override suspend fun testConnection(): Boolean {
        return try {
            withSMBConnection { share ->
                AppLogger.logSMB("TEST_CONNECTION", "Testing SMB connection")
                
                // Try to list the target directory
                val normalizedPath = targetPath.replace("/", "\\")
                val exists = try {
                    share.folderExists(normalizedPath)
                } catch (e: Exception) {
                    AppLogger.logSMB("TEST_CONNECTION", "Directory check failed: ${e.message}")
                    false
                }
                
                if (exists) {
                    AppLogger.logSMB("TEST_CONNECTION", "Target directory exists: $normalizedPath")
                    true
                } else {
                    // Try to create the directory
                    try {
                        ensureDirectoryExists(share, normalizedPath)
                        AppLogger.logSMB("TEST_CONNECTION", "Successfully created target directory")
                        true
                    } catch (e: Exception) {
                        AppLogger.logSMB("TEST_CONNECTION", "Failed to create target directory: ${e.message}")
                        false
                    }
                }
            }
        } catch (e: Exception) {
            AppLogger.logSMB("TEST_CONNECTION", "SMB connection test failed: ${e.message}", e)
            false
        }
    }
    
    override suspend fun syncTestRecords(records: List<TestRecord>): Boolean {
        return try {
            withSMBConnection { share ->
                AppLogger.logSMB("SYNC_RECORDS", "Starting sync - records=${records.size}")

                val normalizedPath = targetPath.replace("/", "\\")
                ensureDirectoryExists(share, normalizedPath)

                val currentDate = Date()
                val formattedDate = fileNameFormat.format(currentDate)
                val fileName = "test_records_${formattedDate}.csv"
                val fullPath = "$normalizedPath\\$fileName"
                AppLogger.logSMB("SYNC_RECORDS", "Generated CSV filename: $fileName (date: $currentDate, formatted: $formattedDate)")

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
                    AppLogger.logSMB("SYNC_RECORDS", "rowsOnly was blank after split; rebuilt from records directly (count=${records.size})")
                }

                // 读取已存在内容
                val existing: String? = if (share.fileExists(fullPath)) {
                    val readFile = share.openFile(
                        fullPath,
                        EnumSet.of(AccessMask.GENERIC_READ),
                        null,
                        SMB2ShareAccess.ALL,
                        SMB2CreateDisposition.FILE_OPEN,
                        null
                    )
                    readFile.use {
                        val buffer = ByteArrayOutputStream()
                        val data = ByteArray(8192)
                        var offset = 0L
                        while (true) {
                            val bytesRead = it.read(data, offset, 0, data.size)
                            if (bytesRead <= 0) break
                            buffer.write(data, 0, bytesRead)
                            offset += bytesRead
                        }
                        buffer.toString(Charsets.UTF_8.name())
                    }
                } else null

                AppLogger.logSMB("SYNC_RECORDS", "existing length=${existing?.length ?: 0}")

                // 并发安全：读-合并-写，写后校验，冲突则合并并重试
                val maxRetries = 3
                var expectedUnion: LinkedHashSet<String>? = null
                for (attempt in 1..maxRetries) {

                    // 每次重试都使用最新的远端内容
                    val currentExisting: String? = if (share.fileExists(fullPath)) {
                        val rf = share.openFile(
                            fullPath,
                            EnumSet.of(AccessMask.GENERIC_READ),
                            null,
                            SMB2ShareAccess.ALL,
                            SMB2CreateDisposition.FILE_OPEN,
                            null
                        )
                        rf.use {
                            val buffer = ByteArrayOutputStream()
                            val data = ByteArray(8192)
                            var offset = 0L
                            while (true) {
                                val bytesRead = it.read(data, offset, 0, data.size)
                                if (bytesRead <= 0) break
                                buffer.write(data, 0, bytesRead)
                                offset += bytesRead
                            }
                            buffer.toString(Charsets.UTF_8.name())
                        }
                    } else null

                    // 解析现有与新增行（去 BOM、去表头、统一换行、去空行）
                    var ex = currentExisting ?: ""
                    if (ex.startsWith("\uFEFF")) ex = ex.removePrefix("\uFEFF")
                    val existingLines = ex.replace("\r\n", "\n")
                        .lineSequence().drop(1).map { it.trimEnd() }.filter { it.isNotBlank() }.toList()
                    val newLines = rowsOnly.replace("\r\n", "\n")
                        .lineSequence().map { it.trimEnd() }.filter { it.isNotBlank() }.toList()

                    val expectedSet = LinkedHashSet<String>()
                    if (expectedUnion != null) expectedSet.addAll(expectedUnion) else expectedSet.addAll(existingLines)
                    expectedSet.addAll(newLines)

                    // 组装合并内容（单一表头 + CRLF，末尾保留 CRLF）
                    val body = if (expectedSet.isEmpty()) "$header\r\n" else "$header\r\n" + expectedSet.joinToString("\r\n") + "\r\n"
                    val finalOut = if (body.startsWith("\uFEFF")) body else "\uFEFF$body"

                    // 覆盖写入合并结果
                    val wf = share.openFile(
                        fullPath,
                        EnumSet.of(AccessMask.GENERIC_WRITE),
                        null,
                        SMB2ShareAccess.ALL,
                        SMB2CreateDisposition.FILE_OVERWRITE_IF,
                        null
                    )
                    wf.use {
                        val bytes = finalOut.toByteArray(Charsets.UTF_8)
                        it.write(bytes, 0L, 0, bytes.size)
                        AppLogger.logFileOperation("WRITE", fullPath, true, "Attempt ${attempt}: wrote ${bytes.size} bytes")
                    }

                    // 写后再读，校验是否包含期望集合（若不满足，说明发生并发覆盖，合并后重试）
                    val fresh = if (share.fileExists(fullPath)) {
                        val rf2 = share.openFile(
                            fullPath,
                            EnumSet.of(AccessMask.GENERIC_READ),
                            null,
                            SMB2ShareAccess.ALL,
                            SMB2CreateDisposition.FILE_OPEN,
                            null
                        )
                        rf2.use {
                            val buffer = ByteArrayOutputStream()
                            val data = ByteArray(8192)
                            var offset = 0L
                            while (true) {
                                val bytesRead = it.read(data, offset, 0, data.size)
                                if (bytesRead <= 0) break
                                buffer.write(data, 0, bytesRead)
                                offset += bytesRead
                            }
                            buffer.toString(Charsets.UTF_8.name())
                        }
                    } else ""

                    var fx = fresh
                    if (fx.startsWith("\uFEFF")) fx = fx.removePrefix("\uFEFF")
                    val freshSet = LinkedHashSet<String>()
                    fx.replace("\r\n", "\n").lineSequence().drop(1)
                        .map { it.trimEnd() }.filter { it.isNotBlank() }.forEach { freshSet.add(it) }

                    val ok = expectedSet.all { freshSet.contains(it) }
                    if (ok) {
                        AppLogger.logSMB("SYNC_RECORDS", "Upload completed successfully (attempt=${attempt})")
                        return@withSMBConnection true
                    }

                    // 合并并重试（期望集合 ∪ 新鲜集合）；最后一次失败则跳出循环
                    expectedUnion = LinkedHashSet<String>().apply {
                        addAll(expectedSet)
                        addAll(freshSet)
                    }
                    if (attempt < maxRetries) {
                        AppLogger.logSMB("SYNC_RECORDS", "Concurrency detected, retrying with union merge... attempt ${attempt}/${maxRetries}")
                        delay(200L * attempt)
                        continue
                    }
                }
                AppLogger.logSMB("SYNC_RECORDS", "Concurrency conflict not resolved after ${maxRetries} attempts")
                return@withSMBConnection false
            }
        } catch (e: Exception) {
            AppLogger.logSMB("SYNC_RECORDS", "Failed to sync records: ${e.message}", e)
            false
        }
    }
    
    override suspend fun saveToLocalStorage(records: List<TestRecord>): String? {
        return withContext(Dispatchers.IO) {
            try {
                val csvContent = generateCSVContent(records)
                val fileName = "test_records_${fileNameFormat.format(Date())}.csv"
                val file = context.getExternalFilesDir(null)?.let { 
                    java.io.File(it, fileName)
                }
                
                // 写入本地同样添加 UTF-8 BOM 与 CRLF，确保在本机 Excel 打开正常
                val normalized = csvContent.replace("\n", "\r\n")
                val bom = "\uFEFF" // UTF-8 BOM 字符
                file?.writeText(bom + normalized, Charsets.UTF_8)
                file?.absolutePath
            } catch (e: Exception) {
                e.printStackTrace()
                null
            }
        }
    }
    
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
    
    override suspend fun fetchTesterList(): List<String> {
        return try {
            withSMBConnection { share ->
                AppLogger.logSMB("FETCH_TESTERS", "Starting fetch testers list")
                
                val normalizedPath = targetPath.replace("/", "\\")
                ensureDirectoryExists(share, normalizedPath)
                
                val testersPath = "$normalizedPath\\$testersFileName"
                AppLogger.logSMB("FETCH_TESTERS", "Checking testers file at: $testersPath")
                
                if (share.fileExists(testersPath)) {
                    val file = share.openFile(
                        testersPath,
                        EnumSet.of(AccessMask.GENERIC_READ),
                        null,
                        SMB2ShareAccess.ALL,
                        SMB2CreateDisposition.FILE_OPEN,
                        null
                    )
                    
                    file.use {
                        val buffer = ByteArrayOutputStream()
                        val data = ByteArray(8192)
                        var offset = 0L
                        while (true) {
                            val bytesRead = it.read(data, offset, 0, data.size)
                            if (bytesRead <= 0) break
                            buffer.write(data, 0, bytesRead)
                            offset += bytesRead
                        }
                        
                        val json = buffer.toString(Charsets.UTF_8.name())
                        AppLogger.logFileOperation("READ", testersPath, true, "Successfully read testers file")
                        val testers = parseTesterJson(json)
                        AppLogger.logSMB("FETCH_TESTERS", "Successfully fetched ${testers.size} testers")
                        testers
                    }
                } else {
                    AppLogger.logSMB("FETCH_TESTERS", "Testers file does not exist")
                    emptyList()
                }
            }
        } catch (e: Exception) {
            AppLogger.logSMB("FETCH_TESTERS", "Failed to fetch testers: ${e.message}", e)
            emptyList()
        }
    }
    
    override suspend fun saveTesterList(testers: List<String>): Boolean {
        return try {
            withSMBConnection { share ->
                AppLogger.logSMB("SAVE_TESTERS", "Starting save testers list with ${testers.size} testers")
                
                val normalizedPath = targetPath.replace("/", "\\")
                ensureDirectoryExists(share, normalizedPath)
                
                val testersPath = "$normalizedPath\\$testersFileName"
                val json = toTesterJson(testers)
                AppLogger.logSMB("SAVE_TESTERS", "Saving testers to: $testersPath")
                
                val file = share.openFile(
                    testersPath,
                    EnumSet.of(AccessMask.GENERIC_WRITE),
                    null,
                    SMB2ShareAccess.ALL,
                    SMB2CreateDisposition.FILE_OVERWRITE_IF,
                    null
                )
                
                file.use {
                    val bytes = json.toByteArray(Charsets.UTF_8)
                    it.write(bytes, 0L, 0, bytes.size)
                    AppLogger.logFileOperation("WRITE", testersPath, true, "Successfully saved testers file")
                }
                
                AppLogger.logSMB("SAVE_TESTERS", "Successfully saved testers list")
                true
            }
        } catch (e: Exception) {
            AppLogger.logSMB("SAVE_TESTERS", "Failed to save testers: ${e.message}", e)
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
    
    override suspend fun fetchActiveTests(): List<FileManager.ActiveTest> {
        val startTime = System.currentTimeMillis()
        return try {
            withSMBConnection { share ->
                AppLogger.logSMB("FETCH_ACTIVE_TESTS", "Starting fetch active tests - server: $serverAddress, share: $shareName, targetPath: $targetPath")
                
                val normalizedPath = targetPath.replace("/", "\\")
                ensureDirectoryExists(share, normalizedPath)
                AppLogger.logSMB("FETCH_ACTIVE_TESTS", "Directory check/creation completed for: $normalizedPath")
                
                val activeTestsPath = "$normalizedPath\\$activeTestsFileName"
                AppLogger.logSMB("FETCH_ACTIVE_TESTS", "Checking active tests file at: $activeTestsPath")
                
                if (share.fileExists(activeTestsPath)) {
                    AppLogger.logSMB("FETCH_ACTIVE_TESTS", "Active tests file exists, opening for read")
                    val file = share.openFile(
                        activeTestsPath,
                        EnumSet.of(AccessMask.GENERIC_READ),
                        null,
                        SMB2ShareAccess.ALL,
                        SMB2CreateDisposition.FILE_OPEN,
                        null
                    )
                    
                    file.use {
                        val readStartTime = System.currentTimeMillis()
                        val buffer = ByteArrayOutputStream()
                        val data = ByteArray(8192)
                        var offset = 0L
                        var totalBytesRead = 0
                        while (true) {
                            val bytesRead = it.read(data, offset, 0, data.size)
                            if (bytesRead <= 0) break
                            buffer.write(data, 0, bytesRead)
                            offset += bytesRead
                            totalBytesRead += bytesRead
                        }
                        val readTime = System.currentTimeMillis() - readStartTime
                        
                        val json = buffer.toString(Charsets.UTF_8.name())
                        AppLogger.logFileOperation("READ", activeTestsPath, true, "Successfully read active tests file in ${readTime}ms, size: ${totalBytesRead} bytes, json length: ${json.length} chars")
                        
                        val tests = parseActiveTestsJson(json)
                        val totalTime = System.currentTimeMillis() - startTime
                        AppLogger.logSMB("FETCH_ACTIVE_TESTS", "Successfully fetched ${tests.size} active tests in ${totalTime}ms")
                        
                        if (tests.isNotEmpty()) {
                            AppLogger.logSMB("FETCH_ACTIVE_TESTS", "Active tests found: ${tests.map { "SN='${it.serial}', tester='${it.tester}', start='${it.startTime}'" }}")
                        } else {
                            AppLogger.logSMB("FETCH_ACTIVE_TESTS", "No active tests found in file")
                        }
                        
                        tests
                    }
                } else {
                    val totalTime = System.currentTimeMillis() - startTime
                    AppLogger.logSMB("FETCH_ACTIVE_TESTS", "Active tests file does not exist at $activeTestsPath after ${totalTime}ms")
                    emptyList()
                }
            }
        } catch (e: Exception) {
            val totalTime = System.currentTimeMillis() - startTime
            AppLogger.logSMB("FETCH_ACTIVE_TESTS", "Failed to fetch active tests after ${totalTime}ms: ${e.message}", e)
            emptyList()
        }
    }
    
    override suspend fun upsertActiveTest(serial: String, tester: String, startTime: Date): Boolean {
        return try {
            AppLogger.logSMB("UPSERT_ACTIVE_TEST", "Starting upsert for serial: $serial, tester: $tester")
            val current = fetchActiveTests().toMutableList()
            val fmt = dateFormat.format(startTime)
            val idx = current.indexOfFirst { it.serial == serial }
            if (idx >= 0) {
                current[idx] = FileManager.ActiveTest(serial, tester, fmt)
                AppLogger.logSMB("UPSERT_ACTIVE_TEST", "Updated existing test for serial: $serial")
            } else {
                current.add(FileManager.ActiveTest(serial, tester, fmt))
                AppLogger.logSMB("UPSERT_ACTIVE_TEST", "Added new test for serial: $serial")
            }
            saveActiveTests(current)
        } catch (e: Exception) {
            AppLogger.logSMB("UPSERT_ACTIVE_TEST", "Failed to upsert active test: ${e.message}", e)
            false
        }
    }
    
    override suspend fun removeActiveTest(serial: String): Boolean {
        return try {
            AppLogger.logSMB("REMOVE_ACTIVE_TEST", "Starting remove for serial: $serial")
            val current = fetchActiveTests().filterNot { it.serial == serial }
            AppLogger.logSMB("REMOVE_ACTIVE_TEST", "Removed test for serial: $serial")
            saveActiveTests(current)
        } catch (e: Exception) {
            AppLogger.logSMB("REMOVE_ACTIVE_TEST", "Failed to remove active test: ${e.message}", e)
            false
        }
    }
    
    private suspend fun saveActiveTests(list: List<FileManager.ActiveTest>): Boolean {
        return try {
            withSMBConnection { share ->
                AppLogger.logSMB("SAVE_ACTIVE_TESTS", "Starting save active tests with ${list.size} tests")
                
                val normalizedPath = targetPath.replace("/", "\\")
                ensureDirectoryExists(share, normalizedPath)
                
                val activeTestsPath = "$normalizedPath\\$activeTestsFileName"
                val json = toActiveTestsJson(list)
                AppLogger.logSMB("SAVE_ACTIVE_TESTS", "Saving active tests to: $activeTestsPath")
                
                val file = share.openFile(
                    activeTestsPath,
                    EnumSet.of(AccessMask.GENERIC_WRITE),
                    null,
                    SMB2ShareAccess.ALL,
                    SMB2CreateDisposition.FILE_OVERWRITE_IF,
                    null
                )
                
                file.use {
                    val bytes = json.toByteArray(Charsets.UTF_8)
                    it.write(bytes, 0L, 0, bytes.size)
                    AppLogger.logFileOperation("WRITE", activeTestsPath, true, "Successfully saved active tests file")
                }
                
                AppLogger.logSMB("SAVE_ACTIVE_TESTS", "Successfully saved active tests")
                true
            }
        } catch (e: Exception) {
            AppLogger.logSMB("SAVE_ACTIVE_TESTS", "Failed to save active tests: ${e.message}", e)
            false
        }
    }
    
    private fun parseActiveTestsJson(json: String): List<FileManager.ActiveTest> {
        return try {
            val trimmed = json.trim()
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
                AppLogger.log("SMBFileManager", "Querying product record for: $productSerial")
                withSMBConnection { share ->
                    // Get project list from projects.json first
                    val projectList = try {
                        val projectsPath = "$targetPath/projects.json"
                        if (share.fileExists(projectsPath)) {
                            val projectsContent = readFromSMBFile(share, projectsPath)
                            parseProjectsJson(projectsContent)
                        } else {
                            // 如果 projects.json 不存在，返回空列表
                            AppLogger.logSMB("GET_PROJECTS", "projects.json not found, returning empty list")
                            emptyList()
                        }
                    } catch (e: Exception) {
                        AppLogger.logSMB("GET_PROJECTS", "Error reading projects.json: ${e.message}")
                        // 返回空列表
                        emptyList()
                    }
                    
                    val searchPath = "$targetPath/record"
                    AppLogger.log("SMBFileManager", "Searching for product record in ${projectList.size} project files")
                    
                    for (projectName in projectList) {
                        // Clean project name for filename
                        val cleanProjectName = projectName.replace(" ", "_").replace("\\\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
                        
                        // 尝试新格式文件名：项目名称_产品类型.csv
                        val possibleFileNames = mutableListOf<String>()
                        
                        // 从当前项目配置获取所有可能的产品类型
                        try {
                            val configPath = "$targetPath/configs/${cleanProjectName}_config.json"
                            if (share.fileExists(configPath)) {
                                val configContent = readFromSMBFile(share, configPath)
                                // 简单解析产品类型
                                val productTypeRegex = "\"typeName\":\\s*\"([^\"]+)\"".toRegex()
                                val productTypes = productTypeRegex.findAll(configContent).map { it.groupValues[1] }.toList()
                                
                                for (productType in productTypes) {
                                    val cleanProductType = productType.replace(" ", "_").replace("/", "_").replace("\\\\", "_")
                                        .replace(":", "_").replace("*", "_").replace("?", "_")
                                        .replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
                                    possibleFileNames.add("${cleanProjectName}_${cleanProductType}.csv")
                                }
                                AppLogger.log("SMBFileManager", "Found ${productTypes.size} product types for project $projectName")
                            }
                        } catch (e: Exception) {
                            AppLogger.log("SMBFileManager", "Failed to read project config for $projectName: ${e.message}")
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
                        
                        AppLogger.log("SMBFileManager", "Trying ${possibleFileNames.size} possible files for project $projectName")
                        
                        // 尝试所有可能的文件名
                        for (fileName in possibleFileNames) {
                            val filePath = "$searchPath/$fileName"
                            
                            try {
                                if (share.fileExists(filePath)) {
                                    AppLogger.log("SMBFileManager", "Checking file: $filePath")
                                    val content = readFromSMBFile(share, filePath)
                                    val record = parseProductRecordFromCSV(content, productSerial)
                                    if (record != null) {
                                        AppLogger.log("SMBFileManager", "✓ Found product record in file: $fileName")
                                        return@withSMBConnection record
                                    }
                                }
                            } catch (e: Exception) {
                                AppLogger.log("SMBFileManager", "Error checking file $fileName: ${e.message}")
                            }
                        }
                    }
                    
                    AppLogger.log("SMBFileManager", "Product record not found in any project file")
                    null
                }
            } catch (e: Exception) {
                AppLogger.log("SMBFileManager", "Error querying product record: ${e.message}", e)
                null
            }
        }
    }
    
    private fun appendToSMBFile(share: DiskShare, filePath: String, content: String) {
        try {
            // Read existing content
            val existingContent = readFromSMBFile(share, filePath)
            // Write combined content
            val combinedContent = existingContent + content
            writeToSMBFile(share, filePath, combinedContent)
        } catch (e: Exception) {
            AppLogger.log("SMBFileManager", "Error appending to SMB file: ${e.message}", e)
            throw e
        }
    }
    
    private fun writeToSMBFile(share: DiskShare, filePath: String, content: String) {
        try {
            val file = share.openFile(
                filePath,
                setOf(AccessMask.GENERIC_WRITE),
                setOf(FileAttributes.FILE_ATTRIBUTE_NORMAL),
                SMB2ShareAccess.ALL,
                SMB2CreateDisposition.FILE_OVERWRITE_IF,
                setOf(SMB2CreateOptions.FILE_NON_DIRECTORY_FILE)
            )
            
            file.use { f ->
                f.outputStream.use { outputStream ->
                    outputStream.write(content.toByteArray(Charsets.UTF_8))
                    outputStream.flush()
                }
            }
            AppLogger.log("SMBFileManager", "Successfully wrote to SMB file: $filePath")
        } catch (e: Exception) {
            AppLogger.log("SMBFileManager", "Error writing to SMB file: ${e.message}", e)
            throw e
        }
    }
    
    private fun writeToSMBFileWithBOM(share: DiskShare, filePath: String, content: String) {
        try {
            val file = share.openFile(
                filePath,
                setOf(AccessMask.GENERIC_WRITE),
                setOf(FileAttributes.FILE_ATTRIBUTE_NORMAL),
                SMB2ShareAccess.ALL,
                SMB2CreateDisposition.FILE_OVERWRITE_IF,
                setOf(SMB2CreateOptions.FILE_NON_DIRECTORY_FILE)
            )
            
            file.use { f ->
                f.outputStream.use { outputStream ->
                    // Write UTF-8 BOM for proper Chinese character display
                    val utf8Bom = byteArrayOf(0xEF.toByte(), 0xBB.toByte(), 0xBF.toByte())
                    outputStream.write(utf8Bom)
                    outputStream.write(content.toByteArray(Charsets.UTF_8))
                    outputStream.flush()
                }
            }
            AppLogger.log("SMBFileManager", "Successfully wrote to SMB file with UTF-8 BOM: $filePath")
        } catch (e: Exception) {
            AppLogger.log("SMBFileManager", "Error writing to SMB file with BOM: ${e.message}", e)
            throw e
        }
    }
    
    private fun readFromSMBFile(share: DiskShare, filePath: String): String {
        return try {
            val file = share.openFile(
                filePath,
                setOf(AccessMask.GENERIC_READ),
                setOf(FileAttributes.FILE_ATTRIBUTE_NORMAL),
                SMB2ShareAccess.ALL,
                SMB2CreateDisposition.FILE_OPEN,
                null
            )
            
            file.use { f ->
                f.inputStream.use { inputStream ->
                    inputStream.readBytes().toString(Charsets.UTF_8)
                }
            }
        } catch (e: Exception) {
            AppLogger.log("SMBFileManager", "Error reading from SMB file: ${e.message}", e)
            ""
        }
    }
    
    private fun parseProductRecordFromCSV(csvContent: String, targetSerial: String): FileManager.ProductRecord? {
        val lines = csvContent.split("\n")
        if (lines.size < 2) return null // At least header and one data row needed
        
        // 解析表头，获取组件列名
        val headerLine = lines[0].trim()
        val headers = headerLine.split(",").map { it.trim() }
        
        AppLogger.log("SMBFileManager", "CSV Headers: $headers")
        
        // Skip header, find matching product serial
        for (i in 1 until lines.size) {
            val line = lines[i].trim()
            if (line.isEmpty()) continue
            
            val columns = line.split(",").map { it.trim() }
            
            // 检查第一列是否匹配产品序列号
            if (columns.isNotEmpty() && columns[0] == targetSerial) {
                AppLogger.log("SMBFileManager", "Found matching record: $line")
                
                // 基础字段（前4列通常是：产品序列号、项目名称、操作员、扫描时间）
                val productSerial = columns.getOrNull(0) ?: ""
                val projectName = columns.getOrNull(1) ?: ""
                val operator = columns.getOrNull(2) ?: ""
                val scanTime = columns.getOrNull(3) ?: ""
                
                // 动态解析组件数据（从第5列开始）
                val components = mutableMapOf<String, String>()
                
                // 从第4列开始是组件数据（索引4开始）
                for (j in 4 until minOf(headers.size, columns.size)) {
                    val componentName = headers.getOrNull(j) ?: continue
                    val componentValue = columns.getOrNull(j) ?: ""
                    
                    if (componentName.isNotEmpty() && componentValue.isNotEmpty()) {
                        components[componentName] = componentValue
                        AppLogger.log("SMBFileManager", "  Component: $componentName = $componentValue")
                    }
                }
                
                AppLogger.log("SMBFileManager", "Loaded ${components.size} components from CSV")
                
                // 兼容旧格式（固定组件名）
                val controlBoard = columns.getOrNull(4) ?: ""
                val drivingCapacitor = columns.getOrNull(5) ?: ""
                val pumpCapacitor = columns.getOrNull(6) ?: ""
                val drivingPower = columns.getOrNull(7) ?: ""
                val pumpPower = columns.getOrNull(8) ?: ""
                
                return FileManager.ProductRecord(
                    productSerial = productSerial,
                    projectName = projectName,
                    operator = operator,
                    scanTime = scanTime,
                    controlBoard = controlBoard,
                    drivingCapacitor = drivingCapacitor,
                    pumpCapacitor = pumpCapacitor,
                    drivingPower = drivingPower,
                    pumpPower = pumpPower,
                    components = components  // 新增：动态组件数据
                )
            }
        }
        
        return null
    }
    
    override suspend fun fetchProjectList(): List<String> {
        return withContext(Dispatchers.IO) {
            try {
                AppLogger.log("SMBFileManager", "Fetching project list from SMB server")
                withSMBConnection { share ->
                    val filePath = "$targetPath/projects.json"
                    
                    if (share.fileExists(filePath)) {
                        val content = readFromSMBFile(share, filePath)
                        AppLogger.log("SMBFileManager", "Found projects file, content: $content")
                        parseProjectsJson(content)
                    } else {
                        AppLogger.logSMB("GET_PROJECTS", "No projects file found, returning empty list")
                        // 返回空列表
                        emptyList()
                    }
                }
            } catch (e: Exception) {
                AppLogger.log("SMBFileManager", "Error fetching project list: ${e.message}", e)
                emptyList()
            }
        }
    }
    
    override suspend fun saveProjectList(projects: List<String>): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                AppLogger.log("SMBFileManager", "Saving project list to SMB server: ${projects.size} projects")
                withSMBConnection { share ->
                    val filePath = "$targetPath/projects.json"
                    val projectsJson = generateProjectsJson(projects)
                    writeToSMBFileWithBOM(share, filePath, projectsJson)
                    AppLogger.log("SMBFileManager", "Successfully saved project list to $filePath")
                }
                true
            } catch (e: Exception) {
                AppLogger.log("SMBFileManager", "Error saving project list: ${e.message}", e)
                false
            }
        }
    }
    
    private fun parseProjectsJson(jsonContent: String): List<String> {
        return try {
            val trimmed = jsonContent.trim()
            AppLogger.log("SMBFileManager", "Parsing projects JSON: $trimmed")

            val key = "\"projects\""
            val start = trimmed.indexOf(key)
            if (start >= 0) {
                val arrStart = trimmed.indexOf('[', start)
                val arrEnd = trimmed.lastIndexOf(']')
                if (arrStart > 0 && arrEnd > arrStart) {
                    val content = trimmed.substring(arrStart + 1, arrEnd)
                    if (content.isBlank()) return emptyList()

                    val projects = content.split(",")
                        .map { it.trim().removeSurrounding("\"") }
                        .filter { it.isNotEmpty() }

                    AppLogger.log("SMBFileManager", "Parsed ${projects.size} projects: $projects")
                    projects
                } else {
                    AppLogger.log("SMBFileManager", "Invalid projects array structure")
                    emptyList()
                }
            } else {
                AppLogger.log("SMBFileManager", "No projects key found in JSON")
                emptyList()
            }
        } catch (e: Exception) {
            AppLogger.log("SMBFileManager", "Error parsing projects JSON: ${e.message}", e)
            emptyList()
        }
    }

    private fun generateProjectsJson(projects: List<String>): String {
        val projectsArray = projects.joinToString(",") { "\"$it\"" }
        return "{\"projects\":[${projectsArray}]}"
    }

    private fun updateExistingRecord(existingContent: String, newDataLine: String, productSerial: String): String {
        val lines = existingContent.split("\n").toMutableList()
        var recordFound = false

        AppLogger.log("SMBFileManager", "[UPDATE_DEBUG] ===== Start updateExistingRecord =====")
        AppLogger.log("SMBFileManager", "[UPDATE_DEBUG] Target product serial: '$productSerial'")
        AppLogger.log("SMBFileManager", "[UPDATE_DEBUG] Total lines in file: ${lines.size}")
        AppLogger.log("SMBFileManager", "[UPDATE_DEBUG] New data line: $newDataLine")

        for (i in 1 until lines.size) {
            val line = lines[i].trim()
            if (line.isEmpty()) continue

            val columns = line.split(",")
            val existingSerial = columns.getOrNull(0)?.trim() ?: ""

            if (columns.isNotEmpty() && existingSerial == productSerial) {
                AppLogger.log("SMBFileManager", "[UPDATE_DEBUG] ✓ MATCH FOUND at line $i")
                val newColumns = newDataLine.split(",")
                val mergedColumns = mutableListOf<String>()

                for (j in 0 until maxOf(columns.size, newColumns.size)) {
                    val existingValue = columns.getOrNull(j)?.trim() ?: ""
                    val newValue = newColumns.getOrNull(j)?.trim() ?: ""
                    val finalValue = if (newValue.isNotEmpty()) newValue else existingValue
                    mergedColumns.add(finalValue)

                    if (j < 5 || existingValue != finalValue) {
                        AppLogger.log(
                            "SMBFileManager",
                            "[UPDATE_DEBUG] Column $j: existing='$existingValue', new='$newValue', final='$finalValue'"
                        )
                    }
                }

                lines[i] = mergedColumns.joinToString(",")
                recordFound = true
                AppLogger.log("SMBFileManager", "[UPDATE_DEBUG] ✓ Record updated successfully")
                break
            }
        }

        if (!recordFound) {
            AppLogger.log("SMBFileManager", "[UPDATE_DEBUG] ✗ No existing record found, appending")
            lines.add(newDataLine)
        }

        val result = lines.joinToString("\n")
        AppLogger.log("SMBFileManager", "[UPDATE_DEBUG] Final line count: ${lines.size}")
        AppLogger.log("SMBFileManager", "[UPDATE_DEBUG] ===== End updateExistingRecord =====")
        return result
    }

    override suspend fun fetchProjectConfig(projectName: String): ProjectConfig? {
        return withContext(Dispatchers.IO) {
            try {
                AppLogger.logSMB("FETCH_PROJECT_CONFIG", "Fetching project config for: $projectName")
                
                withSMBConnection { share ->
                    // 不清理项目名称 - 直接使用原始名称
                    val fileName = "$projectName.json"
                    
                    // 规范化路径为 Windows 格式
                    val normalizedPath = targetPath.replace("/", "\\")
                    val filePath = "$normalizedPath\\projects\\$fileName"
                    
                    AppLogger.logSMB("FETCH_PROJECT_CONFIG", "Looking for config file: $filePath")
                    
                    if (share.fileExists(filePath)) {
                        val content = readFromSMBFile(share, filePath)
                        AppLogger.logSMB("FETCH_PROJECT_CONFIG", "Found config file, content length: ${content.length}")
                        
                        // ===== 详细日志：原始 JSON 内容 =====
                        AppLogger.logSMB("FETCH_PROJECT_CONFIG", "[JSON_DEBUG] Raw JSON content:")
                        AppLogger.logSMB("FETCH_PROJECT_CONFIG", "[JSON_DEBUG] $content")
                        // ===== 结束详细日志 =====
                        
                        if (content.isNotEmpty()) {
                            val config = ProjectConfig.fromJson(content)
                            AppLogger.logSMB("FETCH_PROJECT_CONFIG", "Successfully parsed config: projectName=${config.projectName}, version=${config.version}, productTypes=${config.productTypes.size}")
                            
                            // ===== 详细日志：解析后的配置 =====
                            config.productTypes.forEachIndexed { index, productType ->
                                AppLogger.logSMB("FETCH_PROJECT_CONFIG", "[PARSE_DEBUG] ProductType[$index]: name='${productType.typeName}', materials=${productType.materials.size}")
                                productType.materials.forEachIndexed { mIndex, material ->
                                    AppLogger.logSMB("FETCH_PROJECT_CONFIG", "[PARSE_DEBUG]   Material[$mIndex]: name='${material.name}', partNumber='${material.partNumber}'")
                                }
                            }
                            // ===== 结束详细日志 =====
                            
                            return@withSMBConnection config
                        }
                    } else {
                        AppLogger.logSMB("FETCH_PROJECT_CONFIG", "Config file not found: $filePath")
                    }
                    
                    null
                }
            } catch (e: Exception) {
                AppLogger.logSMB("FETCH_PROJECT_CONFIG", "Error fetching project config: ${e.message}", e)
                null
            }
        }
    }
    
    override suspend fun saveProjectConfig(config: ProjectConfig): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                AppLogger.logSMB("SAVE_PROJECT_CONFIG", "Saving project config for: ${config.projectName}")
                
                withSMBConnection { share ->
                    // 不清理项目名称 - 直接使用原始名称
                    val fileName = "${config.projectName}.json"
                    
                    // 规范化路径为 Windows 格式
                    val normalizedPath = targetPath.replace("/", "\\")
                    val projectsDir = "$normalizedPath\\projects"
                    val filePath = "$projectsDir\\$fileName"
                    
                    val configJson = config.toJson()
                    AppLogger.logSMB("SAVE_PROJECT_CONFIG", "Generated config JSON, length: ${configJson.length}")
                    
                    // 确保 projects 目录存在
                    try {
                        if (!share.folderExists(projectsDir)) {
                            AppLogger.logSMB("SAVE_PROJECT_CONFIG", "Creating projects directory: $projectsDir")
                            share.mkdir(projectsDir)
                        }
                    } catch (e: Exception) {
                        AppLogger.logSMB("SAVE_PROJECT_CONFIG", "Warning: Could not create/verify projects directory: ${e.message}")
                    }
                    
                    // 写入配置文件
                    writeToSMBFile(share, filePath, configJson)
                    AppLogger.logSMB("SAVE_PROJECT_CONFIG", "Successfully saved config to: $filePath")
                    true
                }
            } catch (e: Exception) {
                AppLogger.logSMB("SAVE_PROJECT_CONFIG", "Error saving project config: ${e.message}", e)
                false
            }
        }
    }
    
    /**
     * Upload photo to NAS server
     * Photos are saved to: QRMES/picture/{projectName}_{projectCode}/{productType}_{modelNumber}/{productSerial}/{fileName}
     */
    override suspend fun uploadPhoto(directoryInfo: FileManager.PhotoDirectoryInfo, fileName: String, photoBytes: ByteArray): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                withSMBConnection { share ->
                    AppLogger.logSMB("UPLOAD_PHOTO", "Uploading photo: $fileName for product: ${directoryInfo.productSerial}")
                    
                    val normalizedPath = targetPath.replace("/", "\\")
                    val pictureDir = "$normalizedPath\\picture"
                    
                    // 构建完整的层级路径: picture/{projectName}_{projectCode}/{productType}_{modelNumber}/{productSerial}
                    val projectFolder = sanitizeFolderName(directoryInfo.projectName, directoryInfo.projectCode)
                    val productTypeFolder = sanitizeFolderName(directoryInfo.productType, directoryInfo.modelNumber)
                    val serialFolder = sanitize(directoryInfo.productSerial)
                    
                    val projectDir = "$pictureDir\\$projectFolder"
                    val productTypeDir = "$projectDir\\$productTypeFolder"
                    val productDir = "$productTypeDir\\$serialFolder"
                    val filePath = "$productDir\\$fileName"
                    
                    AppLogger.logSMB("UPLOAD_PHOTO", "Full path: $filePath")
                    
                    // 确保完整的目录层级存在
                    ensureDirectoryExists(share, pictureDir)
                    ensureDirectoryExists(share, projectDir)
                    ensureDirectoryExists(share, productTypeDir)
                    ensureDirectoryExists(share, productDir)
                    
                    // 写入照片文件
                    val file = share.openFile(
                        filePath,
                        EnumSet.of(AccessMask.GENERIC_WRITE),
                        EnumSet.of(FileAttributes.FILE_ATTRIBUTE_NORMAL),
                        SMB2ShareAccess.ALL,
                        SMB2CreateDisposition.FILE_OVERWRITE_IF,
                        EnumSet.noneOf(SMB2CreateOptions::class.java)
                    )
                    
                    file.use {
                        val outputStream = it.outputStream
                        outputStream.write(photoBytes)
                        outputStream.flush()
                    }
                    
                    AppLogger.logSMB("UPLOAD_PHOTO", "Successfully uploaded photo: $filePath (${photoBytes.size} bytes)")
                    true
                }
            } catch (e: Exception) {
                AppLogger.logSMB("UPLOAD_PHOTO", "Error uploading photo: ${e.message}", e)
                false
            }
        }
    }
    
    /**
     * List photos for a product from NAS server
     * 兼容策略：优先新路径，其次旧路径、缓存路径、同项目同级目录，最后递归搜索
     */
    override suspend fun listPhotos(directoryInfo: FileManager.PhotoDirectoryInfo): List<FileManager.PhotoInfo> {
        return withContext(Dispatchers.IO) {
            try {
                withSMBConnection { share ->
                    AppLogger.logSMB("LIST_PHOTOS", "Listing photos for product: ${directoryInfo.productSerial}")

                    val allPhotos = findPhotosWithCompat(share, directoryInfo)

                    AppLogger.logSMB("LIST_PHOTOS", "Found ${allPhotos.size} photos total")
                    allPhotos
                }
            } catch (e: Exception) {
                AppLogger.logSMB("LIST_PHOTOS", "Error listing photos: ${e.message}", e)
                emptyList()
            }
        }
    }

    private fun findPhotosWithCompat(
        share: DiskShare,
        directoryInfo: FileManager.PhotoDirectoryInfo
    ): List<FileManager.PhotoInfo> {
        val normalizedPath = targetPath.replace("/", "\\")
        val pictureDir = "$normalizedPath\\picture"
        val serialFolder = sanitize(directoryInfo.productSerial)
        val projectFolder = sanitizeFolderName(directoryInfo.projectName, directoryInfo.projectCode)
        val productTypeFolder = sanitizeFolderName(directoryInfo.productType, directoryInfo.modelNumber)
        val projectDir = "$pictureDir\\$projectFolder"
        val newPathDir = "$projectDir\\$productTypeFolder\\$serialFolder"
        val oldPathDir = "$pictureDir\\$serialFolder"
        val cacheKey = buildPhotoCacheKey(directoryInfo)
        val cachedPathDir = photoDirectoryCache[cacheKey]

        AppLogger.logSMB("LIST_PHOTOS", "Trying new path: $newPathDir")
        listPhotosIfExists(share, newPathDir)?.takeIf { it.isNotEmpty() }?.let { photos ->
            AppLogger.logSMB("LIST_PHOTOS", "Found ${photos.size} photos in new path")
            photoDirectoryCache[cacheKey] = newPathDir
            return photos
        }

        AppLogger.logSMB("LIST_PHOTOS", "Trying old path: $oldPathDir")
        listPhotosIfExists(share, oldPathDir)?.takeIf { it.isNotEmpty() }?.let { photos ->
            AppLogger.logSMB("LIST_PHOTOS", "Found ${photos.size} photos in old path")
            photoDirectoryCache[cacheKey] = oldPathDir
            return photos
        }

        cachedPathDir?.takeIf { it != newPathDir && it != oldPathDir }?.let { cachedDir ->
            AppLogger.logSMB("LIST_PHOTOS", "Trying cached path: $cachedDir")
            listPhotosIfExists(share, cachedDir)?.takeIf { it.isNotEmpty() }?.let { photos ->
                AppLogger.logSMB("LIST_PHOTOS", "Found ${photos.size} photos in cached path")
                photoDirectoryCache[cacheKey] = cachedDir
                return photos
            }
        }

        findPhotosInSiblingFolders(share, projectDir, serialFolder)?.let { found ->
            AppLogger.logSMB("LIST_PHOTOS", "Found ${found.first.size} photos in legacy path: ${found.second}")
            photoDirectoryCache[cacheKey] = found.second
            return found.first
        }

        AppLogger.logSMB("LIST_PHOTOS", "Searching recursively in picture directory")
        val recursive = searchPhotosRecursively(share, pictureDir, serialFolder)
        if (recursive.isNotEmpty()) {
            recursive.firstOrNull()?.filePath
                ?.substringBeforeLast("\\")
                ?.takeIf { it.isNotBlank() }
                ?.let { photoDirectoryCache[cacheKey] = it }
        }
        return recursive
    }

    private fun listPhotosIfExists(share: DiskShare, directory: String): List<FileManager.PhotoInfo>? {
        if (!share.folderExists(directory)) return null
        return listPhotosInDirectory(share, directory)
    }

    private fun findPhotosInSiblingFolders(
        share: DiskShare,
        projectDir: String,
        serialFolder: String
    ): Pair<List<FileManager.PhotoInfo>, String>? {
        if (!share.folderExists(projectDir)) return null

        AppLogger.logSMB("LIST_PHOTOS", "Searching sibling product type folders in: $projectDir")

        val entries = try {
            share.list(projectDir)
        } catch (e: Exception) {
            AppLogger.logSMB("LIST_PHOTOS", "Error listing sibling folders in $projectDir: ${e.message}")
            return null
        }

        for (entry in entries) {
            if (entry.fileName.startsWith(".") || entry.fileName == "." || entry.fileName == "..") {
                continue
            }
            if ((entry.fileAttributes and FileAttributes.FILE_ATTRIBUTE_DIRECTORY.value) == 0L) {
                continue
            }

            val candidateDir = "$projectDir\\${entry.fileName}\\$serialFolder"
            val photos = listPhotosIfExists(share, candidateDir) ?: continue
            if (photos.isNotEmpty()) {
                return photos to candidateDir
            }
        }

        return null
    }
    
    /**
     * 列出指定目录中的所有照片文件
     */
    private fun listPhotosInDirectory(share: DiskShare, directory: String): List<FileManager.PhotoInfo> {
        return try {
            val entries = share.list(directory)
            entries
                .filter { entry ->
                    !entry.fileName.startsWith(".") &&
                    entry.fileName != "." &&
                    entry.fileName != ".." &&
                    (entry.fileName.endsWith(".jpg", ignoreCase = true) ||
                     entry.fileName.endsWith(".jpeg", ignoreCase = true) ||
                     entry.fileName.endsWith(".png", ignoreCase = true))
                }
                .map { entry ->
                    FileManager.PhotoInfo(
                        fileName = entry.fileName,
                        filePath = "$directory\\${entry.fileName}",
                        fileSize = entry.endOfFile,
                        lastModified = entry.lastWriteTime.toEpochMillis()
                    )
                }
                .sortedByDescending { it.lastModified }
        } catch (e: Exception) {
            AppLogger.logSMB("LIST_PHOTOS", "Error listing directory $directory: ${e.message}")
            emptyList()
        }
    }
    
    /**
     * 递归搜索包含指定序列号的照片
     * 最多搜索3层深度，避免性能问题
     */
    private fun searchPhotosRecursively(share: DiskShare, baseDir: String, serialFolder: String, depth: Int = 0): List<FileManager.PhotoInfo> {
        if (depth > 3) return emptyList()  // 限制搜索深度
        
        val allPhotos = mutableListOf<FileManager.PhotoInfo>()
        
        try {
            if (!share.folderExists(baseDir)) return emptyList()
            
            val entries = share.list(baseDir)
            
            for (entry in entries) {
                if (entry.fileName.startsWith(".") || entry.fileName == "." || entry.fileName == "..") {
                    continue
                }
                
                val fullPath = "$baseDir\\${entry.fileName}"
                
                // 如果是目录
                if ((entry.fileAttributes and com.hierynomus.msfscc.FileAttributes.FILE_ATTRIBUTE_DIRECTORY.value) != 0L) {
                    // 如果目录名匹配序列号，列出其中的照片
                    if (entry.fileName.equals(serialFolder, ignoreCase = true)) {
                        val photos = listPhotosInDirectory(share, fullPath)
                        allPhotos.addAll(photos)
                        AppLogger.logSMB("LIST_PHOTOS", "Found ${photos.size} photos in: $fullPath")
                    } else {
                        // 否则继续递归搜索
                        val photos = searchPhotosRecursively(share, fullPath, serialFolder, depth + 1)
                        allPhotos.addAll(photos)
                    }
                }
            }
        } catch (e: Exception) {
            AppLogger.logSMB("LIST_PHOTOS", "Error searching in $baseDir: ${e.message}")
        }
        
        return allPhotos.sortedByDescending { it.lastModified }
    }
    
    /**
     * Download photo from NAS server
     */
    override suspend fun downloadPhoto(directoryInfo: FileManager.PhotoDirectoryInfo, fileName: String): ByteArray? {
        return withContext(Dispatchers.IO) {
            // 重试机制：最多尝试3次
            var lastException: Exception? = null
            repeat(3) { attempt ->
                try {
                    val result = downloadPhotoInternal(directoryInfo, fileName)
                    if (result != null) {
                        return@withContext result
                    }
                    // 如果返回null但没有异常，说明文件不存在，不需要重试
                    if (attempt == 0) {
                        return@withContext null
                    }
                } catch (e: Exception) {
                    lastException = e
                    AppLogger.logSMB("DOWNLOAD_PHOTO", "Download attempt ${attempt + 1} failed: ${e.message}")
                    if (attempt < 2) {
                        delay(500L * (attempt + 1)) // 递增延迟：500ms, 1000ms
                    }
                }
            }
            
            AppLogger.logSMB("DOWNLOAD_PHOTO", "All download attempts failed", lastException)
            null
        }
    }
    
    private suspend fun downloadPhotoInternal(directoryInfo: FileManager.PhotoDirectoryInfo, fileName: String): ByteArray? {
        return withSMBConnection { share ->
            AppLogger.logSMB("DOWNLOAD_PHOTO", "Downloading photo: $fileName for product: ${directoryInfo.productSerial}")

            val foundPath = findPhotoFileWithCompat(share, directoryInfo, fileName)
            if (foundPath != null) {
                AppLogger.logSMB("DOWNLOAD_PHOTO", "Found file at: $foundPath")
                return@withSMBConnection downloadPhotoFile(share, foundPath)
            }

            AppLogger.logSMB("DOWNLOAD_PHOTO", "Photo file not found: $fileName")
            null
        }
    }

    private fun findPhotoFileWithCompat(
        share: DiskShare,
        directoryInfo: FileManager.PhotoDirectoryInfo,
        fileName: String
    ): String? {
        val normalizedPath = targetPath.replace("/", "\\")
        val pictureDir = "$normalizedPath\\picture"
        val serialFolder = sanitize(directoryInfo.productSerial)
        val projectFolder = sanitizeFolderName(directoryInfo.projectName, directoryInfo.projectCode)
        val productTypeFolder = sanitizeFolderName(directoryInfo.productType, directoryInfo.modelNumber)
        val projectDir = "$pictureDir\\$projectFolder"
        val newPathFile = "$projectDir\\$productTypeFolder\\$serialFolder\\$fileName"
        val oldPathFile = "$pictureDir\\$serialFolder\\$fileName"
        val cacheKey = buildPhotoCacheKey(directoryInfo)
        val cachedPathFile = photoDirectoryCache[cacheKey]?.let { "$it\\$fileName" }

        AppLogger.logSMB("DOWNLOAD_PHOTO", "Trying new path: $newPathFile")
        if (share.fileExists(newPathFile)) {
            photoDirectoryCache[cacheKey] = newPathFile.substringBeforeLast("\\")
            return newPathFile
        }

        AppLogger.logSMB("DOWNLOAD_PHOTO", "Trying old path: $oldPathFile")
        if (share.fileExists(oldPathFile)) {
            photoDirectoryCache[cacheKey] = oldPathFile.substringBeforeLast("\\")
            return oldPathFile
        }

        cachedPathFile?.takeIf { it != newPathFile && it != oldPathFile }?.let { cachedFile ->
            AppLogger.logSMB("DOWNLOAD_PHOTO", "Trying cached path: $cachedFile")
            if (share.fileExists(cachedFile)) {
                photoDirectoryCache[cacheKey] = cachedFile.substringBeforeLast("\\")
                return cachedFile
            }
        }

        findPhotoFileInSiblingFolders(share, projectDir, serialFolder, fileName)?.let { siblingFile ->
            photoDirectoryCache[cacheKey] = siblingFile.substringBeforeLast("\\")
            return siblingFile
        }

        AppLogger.logSMB("DOWNLOAD_PHOTO", "Searching recursively for file: $fileName")
        val foundPath = searchPhotoFileRecursively(share, pictureDir, serialFolder, fileName)
        if (foundPath != null) {
            photoDirectoryCache[cacheKey] = foundPath.substringBeforeLast("\\")
        }
        return foundPath
    }

    private fun findPhotoFileInSiblingFolders(
        share: DiskShare,
        projectDir: String,
        serialFolder: String,
        fileName: String
    ): String? {
        if (!share.folderExists(projectDir)) return null

        AppLogger.logSMB("DOWNLOAD_PHOTO", "Searching sibling product type folders in: $projectDir")

        val entries = try {
            share.list(projectDir)
        } catch (e: Exception) {
            AppLogger.logSMB("DOWNLOAD_PHOTO", "Error listing sibling folders in $projectDir: ${e.message}")
            return null
        }

        for (entry in entries) {
            if (entry.fileName.startsWith(".") || entry.fileName == "." || entry.fileName == "..") {
                continue
            }
            if ((entry.fileAttributes and FileAttributes.FILE_ATTRIBUTE_DIRECTORY.value) == 0L) {
                continue
            }

            val candidateFile = "$projectDir\\${entry.fileName}\\$serialFolder\\$fileName"
            if (share.fileExists(candidateFile)) {
                AppLogger.logSMB("DOWNLOAD_PHOTO", "Found file in legacy path: $candidateFile")
                return candidateFile
            }
        }

        return null
    }
    
    /**
     * 从SMB共享下载照片文件
     */
    private fun downloadPhotoFile(share: DiskShare, filePath: String): ByteArray? {
        return try {
            val file = share.openFile(
                filePath,
                EnumSet.of(AccessMask.GENERIC_READ),
                EnumSet.of(FileAttributes.FILE_ATTRIBUTE_NORMAL),
                SMB2ShareAccess.ALL,
                SMB2CreateDisposition.FILE_OPEN,
                EnumSet.noneOf(SMB2CreateOptions::class.java)
            )
            
            val photoBytes = file.use {
                val inputStream = it.inputStream
                val outputStream = ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                var bytesRead: Int
                
                while (inputStream.read(buffer).also { bytesRead = it } != -1) {
                    outputStream.write(buffer, 0, bytesRead)
                }
                
                outputStream.toByteArray()
            }
            
            AppLogger.logSMB("DOWNLOAD_PHOTO", "Successfully downloaded: $filePath (${photoBytes.size} bytes)")
            photoBytes
        } catch (e: Exception) {
            AppLogger.logSMB("DOWNLOAD_PHOTO", "Error reading file $filePath: ${e.message}", e)
            throw e
        }
    }
    
    /**
     * 递归搜索照片文件
     */
    private fun searchPhotoFileRecursively(
        share: DiskShare, 
        directory: String, 
        serialFolder: String, 
        fileName: String,
        depth: Int = 0
    ): String? {
        if (depth > 5) return null // 限制递归深度
        
        return try {
            val entries = share.list(directory)
            
            for (entry in entries) {
                if (entry.fileName == "." || entry.fileName == "..") continue
                
                val fullPath = "$directory\\${entry.fileName}"
                
                // 如果是目录
                if ((entry.fileAttributes and FileAttributes.FILE_ATTRIBUTE_DIRECTORY.value) != 0L) {
                    // 如果目录名匹配序列号
                    if (entry.fileName.equals(serialFolder, ignoreCase = true)) {
                        val targetFile = "$fullPath\\$fileName"
                        if (share.fileExists(targetFile)) {
                            return targetFile
                        }
                    }
                    // 继续递归搜索
                    val found = searchPhotoFileRecursively(share, fullPath, serialFolder, fileName, depth + 1)
                    if (found != null) return found
                }
            }
            null
        } catch (e: Exception) {
            AppLogger.logSMB("DOWNLOAD_PHOTO", "Error searching in $directory: ${e.message}")
            null
        }
    }
}
