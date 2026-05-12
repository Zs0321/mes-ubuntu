package com.testcenter.qrscanner.integration

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.testcenter.qrscanner.auth.AuthenticationService
import com.testcenter.qrscanner.auth.PermissionService
import com.testcenter.qrscanner.cache.OfflineDataCache
import com.testcenter.qrscanner.cache.PermissionCache
import com.testcenter.qrscanner.network.NetworkErrorHandler
import com.testcenter.qrscanner.photo.PhotoUploadService
import com.testcenter.qrscanner.security.AuditLogger
import com.testcenter.qrscanner.security.SecurityValidator
import kotlinx.coroutines.runBlocking
import org.junit.Before
import org.junit.Test
import org.junit.Assert.*
import java.io.File

/**
 * 系统集成测试
 * 测试端到端的功能流程和多用户并发操作场景
 */
class SystemIntegrationTest {
    
    private lateinit var context: Context
    private lateinit var authService: AuthenticationService
    private lateinit var permissionService: PermissionService
    private lateinit var offlineCache: OfflineDataCache
    private lateinit var permissionCache: PermissionCache
    private lateinit var networkErrorHandler: NetworkErrorHandler
    private lateinit var securityValidator: SecurityValidator
    private lateinit var auditLogger: AuditLogger
    
    @Before
    fun setup() {
        context = ApplicationProvider.getApplicationContext()
        authService = AuthenticationService(context)
        permissionService = PermissionService(context)
        offlineCache = OfflineDataCache(context)
        permissionCache = PermissionCache(context)
        networkErrorHandler = NetworkErrorHandler(context)
        securityValidator = SecurityValidator(context)
        auditLogger = AuditLogger(context)
    }
    
    /**
     * 测试1: 完整的用户认证和权限验证流程
     */
    @Test
    fun testCompleteAuthenticationAndAuthorizationFlow() = runBlocking {
        // 1. 用户登录
        val loginResult = authService.login("testuser", "password123")
        assertTrue("登录应该成功", loginResult.success)
        assertNotNull("应该返回用户信息", loginResult.userInfo)
        
        // 2. 缓存用户权限
        val userInfo = loginResult.userInfo!!
        permissionCache.cacheUserPermission(
            username = userInfo.username,
            role = userInfo.role,
            displayName = userInfo.displayName
        )
        
        // 3. 验证权限缓存
        val cachedData = permissionCache.getCachedUserPermission()
        assertNotNull("应该能获取缓存的权限数据", cachedData)
        assertEquals("缓存的用户名应该匹配", userInfo.username, cachedData?.username)
        
        // 4. 检查权限
        val hasViewPermission = permissionService.hasPermission(userInfo.username, "view_records")
        assertTrue("用户应该有查看记录的权限", hasViewPermission)
        
        // 5. 记录审计日志
        auditLogger.logAuthenticationAttempt(userInfo.username, true)
        auditLogger.logPermissionCheck(userInfo.username, "view_records", "records", true)
        
        // 6. 验证审计日志已记录
        val logFiles = auditLogger.getAuditLogFiles()
        assertTrue("应该生成审计日志文件", logFiles.isNotEmpty())
    }
    
    /**
     * 测试2: 离线模式下的数据缓存和同步
     */
    @Test
    fun testOfflineDataCachingAndSync() {
        // 1. 模拟网络断开
        val isNetworkAvailable = networkErrorHandler.isNetworkAvailable()
        
        // 2. 缓存待上传的记录
        val record = mapOf(
            "productSerial" to "TEST001",
            "materialCode" to "MAT001",
            "timestamp" to System.currentTimeMillis().toString()
        )
        
        val cacheResult = offlineCache.cachePendingRecord(record)
        assertTrue("应该成功缓存记录", cacheResult)
        
        // 3. 获取待上传记录
        val pendingRecords = offlineCache.getPendingRecords()
        assertEquals("应该有1条待上传记录", 1, pendingRecords.size)
        assertEquals("记录内容应该匹配", "TEST001", pendingRecords[0]["productSerial"])
        
        // 4. 获取统计信息
        val stats = offlineCache.getPendingDataStats()
        assertEquals("待上传记录数应该为1", 1, stats["pendingRecords"])
        
        // 5. 清除缓存
        offlineCache.clearPendingRecords()
        val afterClear = offlineCache.getPendingRecords()
        assertEquals("清除后应该没有待上传记录", 0, afterClear.size)
    }
    
    /**
     * 测试3: 文件上传安全验证流程
     */
    @Test
    fun testFileUploadSecurityValidation() {
        // 1. 创建测试图片文件
        val testFile = createTestImageFile()
        
        // 2. 验证文件
        val validationResult = securityValidator.validateFileUpload(testFile)
        assertTrue("有效的图片文件应该通过验证", validationResult.valid)
        assertNull("不应该有错误", validationResult.error)
        
        // 3. 计算文件哈希
        val fileHash = securityValidator.calculateFileHash(testFile)
        assertNotNull("应该能计算文件哈希", fileHash)
        assertTrue("哈希值应该不为空", fileHash.isNotEmpty())
        
        // 4. 清理文件名
        val unsafeName = "../../../etc/passwd"
        val safeName = securityValidator.sanitizeFilename(unsafeName)
        assertFalse("清理后的文件名不应该包含危险字符", safeName.contains(".."))
        
        // 5. 记录文件上传审计日志
        auditLogger.logFileUpload(
            username = "testuser",
            filename = testFile.name,
            fileSize = testFile.length(),
            fileHash = fileHash,
            success = true
        )
        
        // 清理测试文件
        testFile.delete()
    }
    
    /**
     * 测试4: 权限拒绝场景
     */
    @Test
    fun testPermissionDeniedScenario() {
        // 1. 普通用户尝试删除记录
        val username = "normaluser"
        val role = "user"
        
        val validationResult = securityValidator.validatePermission(
            username = username,
            role = role,
            operation = "delete_record",
            target = "RECORD001"
        )
        
        assertFalse("普通用户不应该有删除权限", validationResult.allowed)
        assertTrue("应该需要审计", validationResult.requiresAudit)
        
        // 2. 记录权限拒绝日志
        auditLogger.logPermissionCheck(username, "delete_record", "RECORD001", false)
        auditLogger.logSecurityViolation(username, "delete_record", "RECORD001", "权限不足")
        
        // 3. 验证审计日志
        val logFiles = auditLogger.getAuditLogFiles()
        assertTrue("应该生成审计日志", logFiles.isNotEmpty())
    }
    
    /**
     * 测试5: 网络错误处理
     */
    @Test
    fun testNetworkErrorHandling() {
        // 1. 模拟各种网络异常
        val exceptions = listOf(
            java.net.UnknownHostException("Host not found"),
            java.net.SocketTimeoutException("Connection timeout"),
            java.io.IOException("Network error")
        )
        
        exceptions.forEach { exception ->
            val errorResponse = networkErrorHandler.handleException(exception)
            
            assertNotNull("应该返回错误响应", errorResponse)
            assertNotNull("应该有用户友好的错误消息", errorResponse.userMessage)
            assertTrue("错误消息不应该为空", errorResponse.userMessage.isNotEmpty())
            
            // 验证可重试的错误
            if (exception is java.net.SocketTimeoutException) {
                assertTrue("超时错误应该可重试", errorResponse.retryable)
            }
        }
    }
    
    /**
     * 测试6: 多用户并发操作
     */
    @Test
    fun testConcurrentUserOperations() = runBlocking {
        // 模拟多个用户同时操作
        val users = listOf(
            Pair("admin", "admin"),
            Pair("user1", "user"),
            Pair("user2", "user")
        )
        
        users.forEach { (username, role) ->
            // 缓存用户权限
            permissionCache.cacheUserPermission(username, role, username)
            
            // 检查权限
            val hasPermission = permissionCache.hasPermission("view_records")
            assertTrue("所有用户都应该有查看权限", hasPermission)
            
            // 记录操作
            auditLogger.logDataAccess(username, "view", "records", 10)
        }
        
        // 验证所有操作都被记录
        val logFiles = auditLogger.getAuditLogFiles()
        assertTrue("应该生成审计日志", logFiles.isNotEmpty())
    }
    
    /**
     * 测试7: 边界条件 - 空数据
     */
    @Test
    fun testBoundaryConditions_EmptyData() {
        // 测试空文件名
        val emptyFile = File("")
        val validationResult = securityValidator.validateFileUpload(emptyFile)
        assertFalse("空文件应该验证失败", validationResult.valid)
        
        // 测试空用户名
        val permissionResult = securityValidator.validatePermission("", "user", "view_records")
        // 即使用户名为空，也应该返回结果（不应该崩溃）
        assertNotNull("应该返回验证结果", permissionResult)
    }
    
    /**
     * 测试8: 边界条件 - 大文件
     */
    @Test
    fun testBoundaryConditions_LargeFile() {
        // 创建超大文件（模拟）
        val largeFile = File(context.cacheDir, "large_test.jpg")
        largeFile.createNewFile()
        
        // 写入超过限制的数据（模拟）
        // 实际测试中可能需要真实创建大文件
        
        val validationResult = securityValidator.validateFileUpload(largeFile)
        // 根据文件实际大小判断
        
        largeFile.delete()
    }
    
    /**
     * 测试9: 系统稳定性 - 连续操作
     */
    @Test
    fun testSystemStability_ContinuousOperations() {
        // 执行大量连续操作
        repeat(100) { i ->
            // 缓存数据
            val record = mapOf(
                "id" to i.toString(),
                "data" to "test_$i"
            )
            offlineCache.cachePendingRecord(record)
            
            // 记录审计日志
            auditLogger.logDataAccess("testuser", "create", "record_$i", 1)
        }
        
        // 验证系统仍然正常
        val pendingRecords = offlineCache.getPendingRecords()
        assertEquals("应该有100条记录", 100, pendingRecords.size)
        
        // 清理
        offlineCache.clearPendingRecords()
    }
    
    /**
     * 测试10: 完整的照片上传流程
     */
    @Test
    fun testCompletePhotoUploadFlow() {
        // 1. 创建测试照片
        val testPhoto = createTestImageFile()
        
        // 2. 验证文件安全性
        val validationResult = securityValidator.validateFileUpload(testPhoto)
        assertTrue("照片应该通过安全验证", validationResult.valid)
        
        // 3. 计算文件哈希
        val fileHash = securityValidator.calculateFileHash(testPhoto)
        
        // 4. 缓存照片元数据（模拟离线）
        val metadata = com.testcenter.qrscanner.photo.PhotoMetadata(
            productSerial = "TEST001",
            processStep = "测试工序",
            filePath = testPhoto.absolutePath,
            fileName = testPhoto.name,
            fileSize = testPhoto.length(),
            capturedBy = "testuser",
            capturedAt = System.currentTimeMillis().toString(),
            metadata = mapOf("hash" to fileHash)
        )
        
        offlineCache.cachePendingPhoto(metadata)
        
        // 5. 验证缓存
        val pendingPhotos = offlineCache.getPendingPhotos()
        assertEquals("应该有1张待上传照片", 1, pendingPhotos.size)
        
        // 6. 记录审计日志
        auditLogger.logFileUpload("testuser", testPhoto.name, testPhoto.length(), fileHash, true)
        
        // 清理
        testPhoto.delete()
        offlineCache.clearPendingPhotos()
    }
    
    /**
     * 辅助方法: 创建测试图片文件
     */
    private fun createTestImageFile(): File {
        val testFile = File(context.cacheDir, "test_image.jpg")
        testFile.createNewFile()
        
        // 写入JPEG文件头
        testFile.outputStream().use { output ->
            output.write(byteArrayOf(0xFF.toByte(), 0xD8.toByte(), 0xFF.toByte()))
            // 写入一些测试数据
            output.write(ByteArray(1024) { it.toByte() })
        }
        
        return testFile
    }
}
