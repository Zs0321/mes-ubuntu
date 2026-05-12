package com.testcenter.qrscanner.photo

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayInputStream
import java.io.File

/**
 * PhotoStorageManager 单元测试
 */
@RunWith(AndroidJUnit4::class)
class PhotoStorageManagerTest {
    
    private lateinit var context: Context
    private lateinit var photoStorageManager: PhotoStorageManager
    private lateinit var testDir: File
    
    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        photoStorageManager = PhotoStorageManager(context)
        
        // 创建测试目录
        testDir = File(context.filesDir, "test_photos")
        if (testDir.exists()) {
            testDir.deleteRecursively()
        }
        testDir.mkdirs()
    }
    
    @After
    fun tearDown() {
        // 清理测试文件
        if (testDir.exists()) {
            testDir.deleteRecursively()
        }
    }
    
    @Test
    fun testGeneratePhotoFileName() {
        val productSerial = "TEST001"
        val processStepName = "热套工序"
        
        val fileName = photoStorageManager.generatePhotoFileName(productSerial, processStepName)
        
        // 验证文件名格式
        assertTrue("文件名应包含产品序列号", fileName.contains("TEST001"))
        assertTrue("文件名应包含工序名称", fileName.contains("热套工序"))
        assertTrue("文件名应以.jpg结尾", fileName.endsWith(".jpg"))
        assertTrue("文件名应包含时间戳", fileName.matches(Regex(".*_\\d{8}_\\d{6}\\.jpg")))
    }
    
    @Test
    fun testGeneratePhotoFileNameWithSpecialCharacters() {
        val productSerial = "TEST/001*"
        val processStepName = "热套<工序>"
        
        val fileName = photoStorageManager.generatePhotoFileName(productSerial, processStepName)
        
        // 验证特殊字符被替换
        assertFalse("文件名不应包含特殊字符", fileName.contains("/"))
        assertFalse("文件名不应包含特殊字符", fileName.contains("*"))
        assertFalse("文件名不应包含特殊字符", fileName.contains("<"))
        assertFalse("文件名不应包含特殊字符", fileName.contains(">"))
    }
    
    @Test
    fun testCreatePhotoDirectory() {
        val productSerial = "TEST001"
        
        val photoDir = photoStorageManager.createPhotoDirectory(productSerial)
        
        // 验证目录创建
        assertTrue("照片目录应该存在", photoDir.exists())
        assertTrue("应该是目录", photoDir.isDirectory)
        
        // 验证目录结构包含年月
        val path = photoDir.absolutePath
        assertTrue("目录路径应包含年份", path.matches(Regex(".*\\d{4}.*")))
        assertTrue("目录路径应包含月份", path.matches(Regex(".*\\d{2}.*")))
        assertTrue("目录路径应包含产品序列号", path.contains("TEST001"))
    }
    
    @Test
    fun testSavePhotoToTemp() {
        val testData = "test photo data".toByteArray()
        val inputStream = ByteArrayInputStream(testData)
        val fileName = "test_photo.jpg"
        
        val savedFile = photoStorageManager.savePhotoToTemp(inputStream, fileName)
        
        // 验证文件保存
        assertNotNull("应该返回保存的文件", savedFile)
        assertTrue("文件应该存在", savedFile!!.exists())
        assertEquals("文件名应该正确", fileName, savedFile.name)
        
        // 验证文件内容
        val savedData = savedFile.readBytes()
        assertArrayEquals("文件内容应该正确", testData, savedData)
    }
    
    @Test
    fun testMovePhotoFromTemp() {
        // 先创建临时文件
        val testData = "test photo data".toByteArray()
        val inputStream = ByteArrayInputStream(testData)
        val tempFile = photoStorageManager.savePhotoToTemp(inputStream, "temp_photo.jpg")
        assertNotNull("临时文件应该创建成功", tempFile)
        
        val productSerial = "TEST001"
        val processStepName = "热套工序"
        
        val finalFile = photoStorageManager.movePhotoFromTemp(tempFile!!, productSerial, processStepName)
        
        // 验证文件移动
        assertNotNull("应该返回最终文件", finalFile)
        assertTrue("最终文件应该存在", finalFile!!.exists())
        assertFalse("临时文件应该被删除", tempFile.exists())
        
        // 验证文件内容
        val finalData = finalFile.readBytes()
        assertArrayEquals("文件内容应该正确", testData, finalData)
        
        // 验证文件名格式
        assertTrue("文件名应包含产品序列号", finalFile.name.contains("TEST001"))
        assertTrue("文件名应包含工序名称", finalFile.name.contains("热套工序"))
    }
    
    @Test
    fun testSavePhotoToFinal() {
        val testData = "test photo data".toByteArray()
        val inputStream = ByteArrayInputStream(testData)
        val productSerial = "TEST001"
        val processStepName = "热套工序"
        
        val savedFile = photoStorageManager.savePhotoToFinal(inputStream, productSerial, processStepName)
        
        // 验证文件保存
        assertNotNull("应该返回保存的文件", savedFile)
        assertTrue("文件应该存在", savedFile!!.exists())
        
        // 验证文件内容
        val savedData = savedFile.readBytes()
        assertArrayEquals("文件内容应该正确", testData, savedData)
        
        // 验证文件位置
        val path = savedFile.absolutePath
        assertTrue("文件应该在正确的目录结构中", path.contains("TEST001"))
    }
    
    @Test
    fun testGetProductPhotos() {
        val productSerial = "TEST001"
        
        // 创建多个测试照片
        for (i in 1..3) {
            val testData = "test photo data $i".toByteArray()
            val inputStream = ByteArrayInputStream(testData)
            photoStorageManager.savePhotoToFinal(inputStream, productSerial, "工序$i")
        }
        
        // 为另一个产品创建照片
        val testData = "other product photo".toByteArray()
        val inputStream = ByteArrayInputStream(testData)
        photoStorageManager.savePhotoToFinal(inputStream, "TEST002", "工序1")
        
        val productPhotos = photoStorageManager.getProductPhotos(productSerial)
        
        // 验证结果
        assertEquals("应该返回3张照片", 3, productPhotos.size)
        productPhotos.forEach { photo ->
            assertTrue("照片文件应该存在", photo.exists())
            assertTrue("照片文件名应该包含产品序列号", photo.name.contains(productSerial))
        }
    }
    
    @Test
    fun testCleanupTempFiles() {
        // 创建一些临时文件
        val tempDir = photoStorageManager.getTempDirectory()
        
        // 创建新文件（不应被清理）
        val newFile = File(tempDir, "new_file.jpg")
        newFile.writeText("new file")
        
        // 创建旧文件（应被清理）
        val oldFile = File(tempDir, "old_file.jpg")
        oldFile.writeText("old file")
        // 设置文件为25小时前
        oldFile.setLastModified(System.currentTimeMillis() - 25 * 60 * 60 * 1000)
        
        val cleanedCount = photoStorageManager.cleanupTempFiles(24)
        
        // 验证清理结果
        assertEquals("应该清理1个文件", 1, cleanedCount)
        assertTrue("新文件应该保留", newFile.exists())
        assertFalse("旧文件应该被删除", oldFile.exists())
    }
    
    @Test
    fun testGetPhotoInfo() {
        val testData = "test photo data".toByteArray()
        val inputStream = ByteArrayInputStream(testData)
        val savedFile = photoStorageManager.savePhotoToFinal(inputStream, "TEST001", "热套工序")
        assertNotNull("文件应该保存成功", savedFile)
        
        val photoInfo = photoStorageManager.getPhotoInfo(savedFile!!)
        
        // 验证照片信息
        assertNotNull("应该返回照片信息", photoInfo)
        assertEquals("文件名应该正确", savedFile.name, photoInfo!!.fileName)
        assertEquals("文件路径应该正确", savedFile.absolutePath, photoInfo.filePath)
        assertEquals("文件大小应该正确", testData.size.toLong(), photoInfo.fileSize)
        assertTrue("最后修改时间应该合理", photoInfo.lastModified > 0)
    }
    
    @Test
    fun testGetPhotoInfoForNonExistentFile() {
        val nonExistentFile = File("/non/existent/path/photo.jpg")
        
        val photoInfo = photoStorageManager.getPhotoInfo(nonExistentFile)
        
        // 验证不存在文件的处理
        assertNull("不存在的文件应该返回null", photoInfo)
    }
}