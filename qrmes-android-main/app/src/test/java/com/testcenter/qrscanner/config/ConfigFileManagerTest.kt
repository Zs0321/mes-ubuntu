package com.testcenter.qrscanner.config

import android.content.Context
import com.testcenter.qrscanner.config.ConfigFileManager
import io.mockk.every
import io.mockk.mockk
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import java.io.File
import java.io.IOException

/**
 * 配置文件管理器测试
 */
@RunWith(RobolectricTestRunner::class)
class ConfigFileManagerTest {
    
    private lateinit var context: Context
    private lateinit var configFileManager: ConfigFileManager
    private lateinit var testDir: File
    
    @Before
    fun setUp() {
        context = RuntimeEnvironment.getApplication()
        testDir = File(context.filesDir, "test_config")
        testDir.mkdirs()
        
        // 使用测试目录
        val mockContext = mockk<Context>()
        every { mockContext.filesDir } returns testDir
        
        configFileManager = ConfigFileManager(mockContext)
    }
    
    @After
    fun tearDown() {
        // 清理测试目录
        testDir.deleteRecursively()
    }
    
    @Test
    fun testCreateDefaultConfig() {
        val projectName = "测试项目"
        val config = configFileManager.createDefaultConfig(projectName)
        
        // 验证基本结构
        assertEquals(projectName, config.projectName)
        assertEquals("1.0", config.version)
        assertEquals(1, config.configVersion)
        assertEquals("mobile_app", config.createdBy)
        
        // 验证默认物料属性
        assertEquals(1, config.materialAttributes.size)
        val material = config.materialAttributes[0]
        assertEquals("material_001", material.id)
        assertEquals("主要物料", material.name)
        assertEquals("component", material.type)
        assertTrue(material.required)
        
        // 验证默认工序属性
        assertEquals(2, config.processAttributes.size)
        
        val process1 = config.processAttributes[0]
        assertEquals("process_001", process1.id)
        assertEquals("热套工序", process1.name)
        assertEquals(1, process1.order)
        assertTrue(process1.required)
        assertTrue(process1.photoRequired)
        
        val process2 = config.processAttributes[1]
        assertEquals("process_002", process2.id)
        assertEquals("总装工序", process2.name)
        assertEquals(2, process2.order)
        assertTrue(process2.required)
        assertTrue(process2.photoRequired)
        
        // 验证元数据
        assertEquals("v1.0", config.metadata.configFormat)
        assertTrue(config.metadata.supportedFeatures.contains("materialAttributes"))
        assertTrue(config.metadata.supportedFeatures.contains("processAttributes"))
        assertTrue(config.metadata.supportedFeatures.contains("versionControl"))
    }
    
    @Test
    fun testWriteAndReadConfigFile() {
        val projectName = "测试项目"
        val config = configFileManager.createDefaultConfig(projectName)
        
        // 写入配置文件
        val writeSuccess = configFileManager.writeConfigFile(config)
        assertTrue("配置文件写入应该成功", writeSuccess)
        
        // 读取配置文件
        val readConfig = configFileManager.readConfigFile(projectName)
        assertNotNull("应该能够读取配置文件", readConfig)
        
        // 验证读取的配置
        assertEquals(projectName, readConfig!!.projectName)
        assertEquals("1.0", readConfig.version)
        assertEquals(2, readConfig.configVersion) // 写入时版本号会递增
        assertEquals(config.materialAttributes.size, readConfig.materialAttributes.size)
        assertEquals(config.processAttributes.size, readConfig.processAttributes.size)
    }
    
    @Test
    fun testReadNonExistentConfigFile() {
        val nonExistentProject = "不存在的项目"
        val config = configFileManager.readConfigFile(nonExistentProject)
        assertNull("不存在的配置文件应该返回null", config)
    }
    
    @Test
    fun testConfigValidation() {
        // 测试有效配置
        val validConfig = configFileManager.createDefaultConfig("有效项目")
        val writeSuccess = configFileManager.writeConfigFile(validConfig)
        assertTrue("有效配置应该写入成功", writeSuccess)
        
        // 测试无效配置 - 空项目名称
        val invalidConfig = validConfig.copy(projectName = "")
        val writeFailure = configFileManager.writeConfigFile(invalidConfig)
        assertFalse("无效配置应该写入失败", writeFailure)
    }
    
    @Test
    fun testVersionIncrement() {
        val projectName = "版本测试项目"
        val config = configFileManager.createDefaultConfig(projectName)
        val initialVersion = config.configVersion
        
        // 第一次写入
        configFileManager.writeConfigFile(config)
        val firstRead = configFileManager.readConfigFile(projectName)
        assertEquals(initialVersion + 1, firstRead!!.configVersion)
        
        // 第二次写入
        configFileManager.writeConfigFile(firstRead)
        val secondRead = configFileManager.readConfigFile(projectName)
        assertEquals(initialVersion + 2, secondRead!!.configVersion)
    }
    
    @Test
    fun testBackupCreation() {
        val projectName = "备份测试项目"
        val config = configFileManager.createDefaultConfig(projectName)
        
        // 第一次写入（不会创建备份，因为文件不存在）
        configFileManager.writeConfigFile(config)
        
        // 修改配置
        val modifiedConfig = config.copy(
            description = "修改后的描述",
            materialAttributes = config.materialAttributes.toMutableList().apply {
                add(ConfigFileManager.MaterialAttribute(
                    id = "material_002",
                    name = "新增物料",
                    type = "component",
                    required = false,
                    qrCodeFormat = "QR_CODE",
                    description = "新增的物料"
                ))
            }
        )
        
        // 第二次写入（应该创建备份）
        val writeSuccess = configFileManager.writeConfigFile(modifiedConfig)
        assertTrue("修改后的配置应该写入成功", writeSuccess)
        
        // 验证备份文件存在
        val backupsDir = File(testDir, "config/backups")
        assertTrue("备份目录应该存在", backupsDir.exists())
        
        val backupFiles = backupsDir.listFiles { _, name ->
            name.startsWith("${projectName}_") && name.endsWith(".json")
        }
        assertTrue("应该存在备份文件", backupFiles?.isNotEmpty() == true)
    }
    
    @Test
    fun testVersionHistory() {
        val projectName = "版本历史测试项目"
        val config = configFileManager.createDefaultConfig(projectName)
        
        // 写入多个版本
        repeat(3) { i ->
            val versionConfig = config.copy(
                description = "版本 ${i + 1} 的描述"
            )
            configFileManager.writeConfigFile(versionConfig)
        }
        
        // 获取版本历史
        val versionHistory = configFileManager.getVersionHistory(projectName)
        assertTrue("应该有版本历史记录", versionHistory.isNotEmpty())
        
        // 验证版本按降序排列
        for (i in 0 until versionHistory.size - 1) {
            assertTrue(
                "版本应该按降序排列",
                versionHistory[i].version >= versionHistory[i + 1].version
            )
        }
    }
    
    @Test
    fun testRestoreVersion() {
        val projectName = "版本恢复测试项目"
        val config = configFileManager.createDefaultConfig(projectName)
        
        // 写入初始版本
        configFileManager.writeConfigFile(config)
        val version1 = configFileManager.readConfigFile(projectName)!!
        
        // 修改并写入第二个版本
        val modifiedConfig = config.copy(description = "修改后的版本")
        configFileManager.writeConfigFile(modifiedConfig)
        val version2 = configFileManager.readConfigFile(projectName)!!
        
        // 恢复到第一个版本
        val restoreSuccess = configFileManager.restoreVersion(projectName, version1.configVersion)
        assertTrue("版本恢复应该成功", restoreSuccess)
        
        // 验证恢复结果
        val restoredConfig = configFileManager.readConfigFile(projectName)!!
        assertEquals("恢复后的描述应该是原始描述", config.description, restoredConfig.description)
        assertTrue("恢复后的版本号应该大于原版本", restoredConfig.configVersion > version2.configVersion)
    }
    
    @Test
    fun testExportConfig() {
        val projectName = "导出测试项目"
        val config = configFileManager.createDefaultConfig(projectName)
        configFileManager.writeConfigFile(config)
        
        val exportFile = File(testDir, "export_test.json")
        val exportSuccess = configFileManager.exportConfig(projectName, exportFile)
        
        assertTrue("配置导出应该成功", exportSuccess)
        assertTrue("导出文件应该存在", exportFile.exists())
        assertTrue("导出文件应该有内容", exportFile.length() > 0)
        
        // 验证导出文件格式（简单检查）
        val exportContent = exportFile.readText()
        assertTrue("导出内容应该包含exportedAt", exportContent.contains("exportedAt"))
        assertTrue("导出内容应该包含config", exportContent.contains("config"))
        assertTrue("导出内容应该包含项目名称", exportContent.contains(projectName))
    }
    
    @Test
    fun testImportConfig() {
        val originalProject = "原始项目"
        val targetProject = "目标项目"
        
        // 创建原始配置
        val originalConfig = configFileManager.createDefaultConfig(originalProject)
        configFileManager.writeConfigFile(originalConfig)
        
        // 导出原始配置
        val exportFile = File(testDir, "import_test.json")
        configFileManager.exportConfig(originalProject, exportFile)
        
        // 导入到新项目
        val importSuccess = configFileManager.importConfig(exportFile, targetProject)
        assertTrue("配置导入应该成功", importSuccess)
        
        // 验证导入结果
        val importedConfig = configFileManager.readConfigFile(targetProject)
        assertNotNull("导入的配置应该存在", importedConfig)
        assertEquals("导入后的项目名称应该是目标项目名称", targetProject, importedConfig!!.projectName)
        assertEquals("导入后的物料数量应该一致", originalConfig.materialAttributes.size, importedConfig.materialAttributes.size)
        assertEquals("导入后的工序数量应该一致", originalConfig.processAttributes.size, importedConfig.processAttributes.size)
    }
    
    @Test
    fun testImportNonExistentFile() {
        val nonExistentFile = File(testDir, "non_existent.json")
        val importSuccess = configFileManager.importConfig(nonExistentFile, "测试项目")
        assertFalse("导入不存在的文件应该失败", importSuccess)
    }
    
    @Test
    fun testConfigFileNaming() {
        // 测试特殊字符的文件名处理
        val projectsWithSpecialChars = listOf(
            "项目/名称",
            "项目\\名称",
            "项目:名称",
            "项目*名称",
            "项目?名称",
            "项目\"名称",
            "项目<名称>",
            "项目|名称"
        )
        
        projectsWithSpecialChars.forEach { projectName ->
            val config = configFileManager.createDefaultConfig(projectName)
            val writeSuccess = configFileManager.writeConfigFile(config)
            assertTrue("包含特殊字符的项目名称应该能够写入: $projectName", writeSuccess)
            
            val readConfig = configFileManager.readConfigFile(projectName)
            assertNotNull("包含特殊字符的项目名称应该能够读取: $projectName", readConfig)
            assertEquals("读取的项目名称应该一致", projectName, readConfig!!.projectName)
        }
    }
    
    @Test
    fun testConcurrentAccess() {
        val projectName = "并发测试项目"
        val config = configFileManager.createDefaultConfig(projectName)
        
        // 模拟并发写入
        val threads = mutableListOf<Thread>()
        val results = mutableListOf<Boolean>()
        
        repeat(5) { i ->
            val thread = Thread {
                val threadConfig = config.copy(description = "线程 $i 的配置")
                val success = configFileManager.writeConfigFile(threadConfig)
                synchronized(results) {
                    results.add(success)
                }
            }
            threads.add(thread)
        }
        
        // 启动所有线程
        threads.forEach { it.start() }
        
        // 等待所有线程完成
        threads.forEach { it.join() }
        
        // 验证结果
        assertTrue("至少有一个线程应该写入成功", results.any { it })
        
        // 验证最终配置存在
        val finalConfig = configFileManager.readConfigFile(projectName)
        assertNotNull("最终配置应该存在", finalConfig)
    }
    
    @Test
    fun testLargeConfigFile() {
        val projectName = "大配置文件测试项目"
        val config = configFileManager.createDefaultConfig(projectName)
        
        // 添加大量物料和工序
        val largeMaterialList = mutableListOf<ConfigFileManager.MaterialAttribute>()
        repeat(100) { i ->
            largeMaterialList.add(
                ConfigFileManager.MaterialAttribute(
                    id = "material_$i",
                    name = "物料 $i",
                    type = "component",
                    required = i % 2 == 0,
                    qrCodeFormat = if (i % 2 == 0) "CODE128" else "QR_CODE",
                    description = "这是第 $i 个物料的详细描述"
                )
            )
        }
        
        val largeProcessList = mutableListOf<ConfigFileManager.ProcessAttribute>()
        repeat(50) { i ->
            largeProcessList.add(
                ConfigFileManager.ProcessAttribute(
                    id = "process_$i",
                    name = "工序 $i",
                    description = "这是第 $i 个工序的详细描述，包含了很多详细信息",
                    order = i + 1,
                    required = i % 3 != 0,
                    photoRequired = i % 2 == 0,
                    estimatedDuration = (i + 1) * 60
                )
            )
        }
        
        val largeConfig = config.copy(
            materialAttributes = largeMaterialList,
            processAttributes = largeProcessList
        )
        
        // 写入大配置文件
        val writeSuccess = configFileManager.writeConfigFile(largeConfig)
        assertTrue("大配置文件应该写入成功", writeSuccess)
        
        // 读取大配置文件
        val readConfig = configFileManager.readConfigFile(projectName)
        assertNotNull("大配置文件应该读取成功", readConfig)
        assertEquals("物料数量应该一致", largeMaterialList.size, readConfig!!.materialAttributes.size)
        assertEquals("工序数量应该一致", largeProcessList.size, readConfig.processAttributes.size)
    }
}