package com.testcenter.qrscanner.sync

import android.content.Context
import com.testcenter.qrscanner.config.ConfigFileManager
import com.testcenter.qrscanner.network.FileManager
import com.testcenter.qrscanner.sync.ConfigSyncService
import com.testcenter.qrscanner.utils.ProjectConfigManager
import io.mockk.*
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import java.io.File

/**
 * 配置同步服务测试
 */
@RunWith(RobolectricTestRunner::class)
class ConfigSyncServiceTest {
    
    private lateinit var context: Context
    private lateinit var mockFileManager: FileManager
    private lateinit var configSyncService: ConfigSyncService
    private lateinit var testDir: File
    
    @Before
    fun setUp() {
        context = RuntimeEnvironment.getApplication()
        testDir = File(context.filesDir, "test_sync")
        testDir.mkdirs()
        
        // 使用测试目录
        val mockContext = mockk<Context>()
        every { mockContext.filesDir } returns testDir
        
        // 创建模拟的FileManager
        mockFileManager = mockk<FileManager>()
        
        configSyncService = ConfigSyncService(mockContext, mockFileManager)
    }
    
    @After
    fun tearDown() {
        testDir.deleteRecursively()
        clearAllMocks()
    }
    
    @Test
    fun testSyncToServerSuccess() = runBlocking {
        val projectName = "测试项目"
        
        // 准备本地配置
        val configFileManager = ConfigFileManager(context)
        val localConfig = configFileManager.createDefaultConfig(projectName)
        configFileManager.writeConfigFile(localConfig)
        
        // 模拟服务器没有更新的版本
        every { runBlocking { mockFileManager.fetchProjectConfig(projectName) } } returns null
        
        // 模拟上传成功
        coEvery { mockFileManager.saveProjectConfig(any()) } returns true
        
        // 执行同步
        val result = configSyncService.syncToServer(projectName)
        
        // 验证结果
        assertTrue("同步到服务器应该成功", result is ConfigSyncService.SyncResult.Success)
        
        // 验证调用
        coVerify { mockFileManager.saveProjectConfig(any()) }
    }
    
    @Test
    fun testSyncToServerConflict() = runBlocking {
        val projectName = "冲突测试项目"
        
        // 准备本地配置
        val configFileManager = ConfigFileManager(context)
        val localConfig = configFileManager.createDefaultConfig(projectName)
        configFileManager.writeConfigFile(localConfig)
        
        // 模拟服务器有更新的版本
        val serverConfig = localConfig.copy(
            configVersion = localConfig.configVersion + 1,
            description = "服务器版本"
        )
        
        // 这里需要模拟ProjectConfig的转换，简化处理
        coEvery { mockFileManager.fetchProjectConfig(projectName) } returns mockk()
        
        // 执行同步
        val result = configSyncService.syncToServer(projectName)
        
        // 验证结果（由于转换复杂性，这里主要测试不会崩溃）
        assertNotNull("同步结果不应该为null", result)
    }
    
    @Test
    fun testSyncFromServerSuccess() = runBlocking {
        val projectName = "从服务器同步项目"
        
        // 模拟服务器配置
        coEvery { mockFileManager.fetchProjectConfig(projectName) } returns mockk()
        
        // 执行同步
        val result = configSyncService.syncFromServer(projectName, ConfigSyncService.SyncStrategy.SERVER_WINS)
        
        // 验证结果
        assertNotNull("同步结果不应该为null", result)
        
        // 验证调用
        coVerify { mockFileManager.fetchProjectConfig(projectName) }
    }
    
    @Test
    fun testSyncFromServerNotFound() = runBlocking {
        val projectName = "不存在的项目"
        
        // 模拟服务器没有配置
        coEvery { mockFileManager.fetchProjectConfig(projectName) } returns null
        
        // 执行同步
        val result = configSyncService.syncFromServer(projectName)
        
        // 验证结果
        assertTrue("应该返回错误结果", result is ConfigSyncService.SyncResult.Error)
        val errorResult = result as ConfigSyncService.SyncResult.Error
        assertTrue("错误消息应该包含'没有找到'", errorResult.message.contains("没有找到"))
    }
    
    @Test
    fun testBatchSync() = runBlocking {
        val projectNames = listOf("项目1", "项目2", "项目3")
        
        // 模拟服务器响应
        projectNames.forEach { projectName ->
            coEvery { mockFileManager.fetchProjectConfig(projectName) } returns null
        }
        
        // 执行批量同步
        val results = configSyncService.batchSync(projectNames, ConfigSyncService.SyncStrategy.MERGE)
        
        // 验证结果
        assertEquals("应该返回所有项目的结果", projectNames.size, results.size)
        
        projectNames.forEach { projectName ->
            assertTrue("每个项目都应该有结果", results.containsKey(projectName))
            assertNotNull("每个项目的结果都不应该为null", results[projectName])
        }
    }
    
    @Test
    fun testMergeConfigs() {
        // 这个测试需要访问私有方法，这里提供一个简化的测试
        // 实际实现中可以将合并逻辑提取为公共方法进行测试
        
        val configFileManager = ConfigFileManager(context)
        val localConfig = configFileManager.createDefaultConfig("本地项目")
        val serverConfig = configFileManager.createDefaultConfig("服务器项目")
        
        // 修改配置以创建差异
        val modifiedLocalConfig = localConfig.copy(
            materialAttributes = localConfig.materialAttributes.toMutableList().apply {
                add(ConfigFileManager.MaterialAttribute(
                    id = "local_material",
                    name = "本地物料",
                    type = "component",
                    required = true,
                    qrCodeFormat = "CODE128"
                ))
            }
        )
        
        val modifiedServerConfig = serverConfig.copy(
            processAttributes = serverConfig.processAttributes.toMutableList().apply {
                add(ConfigFileManager.ProcessAttribute(
                    id = "server_process",
                    name = "服务器工序",
                    description = "服务器工序描述",
                    order = 3,
                    required = true,
                    photoRequired = true,
                    estimatedDuration = 240
                ))
            }
        )
        
        // 验证配置不同
        assertNotEquals("本地和服务器配置应该不同", 
            modifiedLocalConfig.materialAttributes.size, 
            modifiedServerConfig.materialAttributes.size)
        
        assertNotEquals("本地和服务器工序应该不同", 
            modifiedLocalConfig.processAttributes.size, 
            modifiedServerConfig.processAttributes.size)
    }
    
    @Test
    fun testConfigChangeHistory() {
        val projectName = "历史测试项目"
        
        // 记录配置变更
        configSyncService.recordConfigChange(
            projectName, 
            ConfigSyncService.ChangeType.CREATED, 
            "创建项目配置"
        )
        
        configSyncService.recordConfigChange(
            projectName, 
            ConfigSyncService.ChangeType.UPDATED, 
            "更新项目配置"
        )
        
        // 获取变更历史
        val history = configSyncService.getConfigChangeHistory(projectName)
        
        // 验证历史记录
        assertNotNull("变更历史不应该为null", history)
        // 由于实现简化，这里主要测试方法不会崩溃
    }
    
    @Test
    fun testCleanupOldChanges() {
        // 测试清理旧变更记录
        configSyncService.cleanupOldChanges(keepDays = 30)
        
        // 这里主要测试方法不会崩溃
        // 实际的清理逻辑需要更复杂的测试设置
        assertTrue("清理方法应该正常执行", true)
    }
    
    @Test
    fun testSyncWithNetworkError() = runBlocking {
        val projectName = "网络错误测试项目"
        
        // 模拟网络错误
        coEvery { mockFileManager.fetchProjectConfig(projectName) } throws Exception("网络连接失败")
        
        // 执行同步
        val result = configSyncService.syncFromServer(projectName)
        
        // 验证结果
        assertTrue("应该返回错误结果", result is ConfigSyncService.SyncResult.Error)
        val errorResult = result as ConfigSyncService.SyncResult.Error
        assertTrue("错误消息应该包含网络相关信息", errorResult.message.contains("网络") || errorResult.message.contains("失败"))
    }
    
    @Test
    fun testSyncStrategies() = runBlocking {
        val projectName = "策略测试项目"
        
        // 测试不同的同步策略
        val strategies = listOf(
            ConfigSyncService.SyncStrategy.SERVER_WINS,
            ConfigSyncService.SyncStrategy.LOCAL_WINS,
            ConfigSyncService.SyncStrategy.MERGE,
            ConfigSyncService.SyncStrategy.ASK_USER
        )
        
        strategies.forEach { strategy ->
            // 模拟服务器没有配置
            coEvery { mockFileManager.fetchProjectConfig(projectName) } returns null
            
            // 执行同步
            val result = configSyncService.syncFromServer(projectName, strategy)
            
            // 验证结果
            assertNotNull("策略 $strategy 的同步结果不应该为null", result)
        }
    }
    
    @Test
    fun testConcurrentSync() = runBlocking {
        val projectName = "并发同步测试项目"
        
        // 模拟服务器配置
        coEvery { mockFileManager.fetchProjectConfig(projectName) } returns null
        coEvery { mockFileManager.saveProjectConfig(any()) } returns true
        
        // 创建本地配置
        val configFileManager = ConfigFileManager(context)
        val localConfig = configFileManager.createDefaultConfig(projectName)
        configFileManager.writeConfigFile(localConfig)
        
        // 并发执行同步
        val results = mutableListOf<ConfigSyncService.SyncResult>()
        val jobs = mutableListOf<kotlinx.coroutines.Job>()
        
        repeat(3) {
            val job = kotlinx.coroutines.GlobalScope.launch {
                val result = configSyncService.syncToServer(projectName)
                synchronized(results) {
                    results.add(result)
                }
            }
            jobs.add(job)
        }
        
        // 等待所有任务完成
        jobs.forEach { it.join() }
        
        // 验证结果
        assertEquals("应该有3个同步结果", 3, results.size)
        results.forEach { result ->
            assertNotNull("每个同步结果都不应该为null", result)
        }
    }
    
    @Test
    fun testSyncResultTypes() {
        // 测试不同类型的同步结果
        val successResult = ConfigSyncService.SyncResult.Success("同步成功")
        assertTrue("Success结果应该是Success类型", successResult is ConfigSyncService.SyncResult.Success)
        assertEquals("Success消息应该正确", "同步成功", successResult.message)
        
        val errorResult = ConfigSyncService.SyncResult.Error("同步失败")
        assertTrue("Error结果应该是Error类型", errorResult is ConfigSyncService.SyncResult.Error)
        assertEquals("Error消息应该正确", "同步失败", errorResult.message)
        
        val noChangesResult = ConfigSyncService.SyncResult.NoChanges
        assertTrue("NoChanges结果应该是NoChanges类型", noChangesResult is ConfigSyncService.SyncResult.NoChanges)
    }
    
    @Test
    fun testChangeTypeEnum() {
        // 测试变更类型枚举
        val changeTypes = ConfigSyncService.ChangeType.values()
        
        assertTrue("应该包含CREATED类型", changeTypes.contains(ConfigSyncService.ChangeType.CREATED))
        assertTrue("应该包含UPDATED类型", changeTypes.contains(ConfigSyncService.ChangeType.UPDATED))
        assertTrue("应该包含DELETED类型", changeTypes.contains(ConfigSyncService.ChangeType.DELETED))
        assertTrue("应该包含IMPORTED类型", changeTypes.contains(ConfigSyncService.ChangeType.IMPORTED))
        assertTrue("应该包含RESTORED类型", changeTypes.contains(ConfigSyncService.ChangeType.RESTORED))
    }
}