package com.testcenter.qrscanner.photo

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * LocalPhotoMetadataManager 单元测试
 */
@RunWith(AndroidJUnit4::class)
class LocalPhotoMetadataManagerTest {
    
    private lateinit var context: Context
    private lateinit var metadataManager: LocalPhotoMetadataManager
    
    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        metadataManager = LocalPhotoMetadataManager(context)
        
        // 清理之前的测试数据
        val prefs = context.getSharedPreferences("photo_metadata", Context.MODE_PRIVATE)
        prefs.edit().clear().apply()
    }
    
    @After
    fun tearDown() {
        // 清理测试数据
        val prefs = context.getSharedPreferences("photo_metadata", Context.MODE_PRIVATE)
        prefs.edit().clear().apply()
    }
    
    @Test
    fun testSavePhotoMetadata() {
        val metadata = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "热套工序",
            filePath = "/test/path/photo.jpg",
            fileName = "TEST001_热套工序_20241018_143022.jpg",
            fileSize = 1024000,
            capturedBy = "testuser"
        )
        
        val result = metadataManager.savePhotoMetadata(metadata)
        
        assertTrue("保存应该成功", result)
        
        // 验证数据是否保存
        val savedPhotos = metadataManager.getProductPhotos("TEST001")
        assertEquals("应该有1张照片", 1, savedPhotos.size)
        
        val savedMetadata = savedPhotos[0]
        assertEquals("产品序列号应该正确", "TEST001", savedMetadata.productSerial)
        assertEquals("工序步骤应该正确", "热套工序", savedMetadata.processStep)
        assertEquals("文件路径应该正确", "/test/path/photo.jpg", savedMetadata.filePath)
        assertEquals("文件名应该正确", "TEST001_热套工序_20241018_143022.jpg", savedMetadata.fileName)
        assertEquals("文件大小应该正确", 1024000, savedMetadata.fileSize)
        assertEquals("拍摄用户应该正确", "testuser", savedMetadata.capturedBy)
    }
    
    @Test
    fun testUpdateExistingPhotoMetadata() {
        val originalMetadata = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "热套工序",
            filePath = "/test/path/photo.jpg",
            fileName = "test_photo.jpg",
            fileSize = 1024000,
            capturedBy = "testuser"
        )
        
        // 保存原始数据
        metadataManager.savePhotoMetadata(originalMetadata)
        
        // 更新数据
        val updatedMetadata = originalMetadata.copy(
            fileSize = 2048000,
            uploadedAt = System.currentTimeMillis()
        )
        
        val result = metadataManager.savePhotoMetadata(updatedMetadata)
        
        assertTrue("更新应该成功", result)
        
        // 验证更新结果
        val savedPhotos = metadataManager.getProductPhotos("TEST001")
        assertEquals("应该只有1张照片", 1, savedPhotos.size)
        
        val savedMetadata = savedPhotos[0]
        assertEquals("文件大小应该更新", 2048000, savedMetadata.fileSize)
        assertNotNull("上传时间应该设置", savedMetadata.uploadedAt)
    }
    
    @Test
    fun testGetProductPhotos() {
        // 为TEST001创建照片
        val metadata1 = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "热套工序",
            filePath = "/test/path/photo1.jpg",
            fileName = "photo1.jpg",
            fileSize = 1024000,
            capturedBy = "testuser"
        )
        
        val metadata2 = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "总装工序",
            filePath = "/test/path/photo2.jpg",
            fileName = "photo2.jpg",
            fileSize = 2048000,
            capturedBy = "testuser"
        )
        
        // 为TEST002创建照片
        val metadata3 = PhotoMetadata.create(
            productSerial = "TEST002",
            processStep = "热套工序",
            filePath = "/test/path/photo3.jpg",
            fileName = "photo3.jpg",
            fileSize = 1536000,
            capturedBy = "testuser"
        )
        
        metadataManager.savePhotoMetadata(metadata1)
        metadataManager.savePhotoMetadata(metadata2)
        metadataManager.savePhotoMetadata(metadata3)
        
        val test001Photos = metadataManager.getProductPhotos("TEST001")
        val test002Photos = metadataManager.getProductPhotos("TEST002")
        
        assertEquals("TEST001应该有2张照片", 2, test001Photos.size)
        assertEquals("TEST002应该有1张照片", 1, test002Photos.size)
        
        // 验证照片属于正确的产品
        test001Photos.forEach { photo ->
            assertEquals("照片应该属于TEST001", "TEST001", photo.productSerial)
        }
        
        test002Photos.forEach { photo ->
            assertEquals("照片应该属于TEST002", "TEST002", photo.productSerial)
        }
    }
    
    @Test
    fun testGetProcessPhotos() {
        val metadata1 = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "热套工序",
            filePath = "/test/path/photo1.jpg",
            fileName = "photo1.jpg",
            fileSize = 1024000,
            capturedBy = "testuser"
        )
        
        val metadata2 = PhotoMetadata.create(
            productSerial = "TEST002",
            processStep = "热套工序",
            filePath = "/test/path/photo2.jpg",
            fileName = "photo2.jpg",
            fileSize = 2048000,
            capturedBy = "testuser"
        )
        
        val metadata3 = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "总装工序",
            filePath = "/test/path/photo3.jpg",
            fileName = "photo3.jpg",
            fileSize = 1536000,
            capturedBy = "testuser"
        )
        
        metadataManager.savePhotoMetadata(metadata1)
        metadataManager.savePhotoMetadata(metadata2)
        metadataManager.savePhotoMetadata(metadata3)
        
        val heatSetPhotos = metadataManager.getProcessPhotos("热套工序")
        val assemblyPhotos = metadataManager.getProcessPhotos("总装工序")
        
        assertEquals("热套工序应该有2张照片", 2, heatSetPhotos.size)
        assertEquals("总装工序应该有1张照片", 1, assemblyPhotos.size)
        
        // 验证照片属于正确的工序
        heatSetPhotos.forEach { photo ->
            assertEquals("照片应该属于热套工序", "热套工序", photo.processStep)
        }
        
        assemblyPhotos.forEach { photo ->
            assertEquals("照片应该属于总装工序", "总装工序", photo.processStep)
        }
    }
    
    @Test
    fun testGetPhotoByPath() {
        val metadata = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "热套工序",
            filePath = "/test/path/photo.jpg",
            fileName = "photo.jpg",
            fileSize = 1024000,
            capturedBy = "testuser"
        )
        
        metadataManager.savePhotoMetadata(metadata)
        
        val foundPhoto = metadataManager.getPhotoByPath("/test/path/photo.jpg")
        val notFoundPhoto = metadataManager.getPhotoByPath("/test/path/nonexistent.jpg")
        
        assertNotNull("应该找到照片", foundPhoto)
        assertNull("不应该找到不存在的照片", notFoundPhoto)
        
        assertEquals("找到的照片应该正确", "TEST001", foundPhoto!!.productSerial)
    }
    
    @Test
    fun testGetPendingUploadPhotos() {
        val uploadedMetadata = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "热套工序",
            filePath = "/test/path/uploaded.jpg",
            fileName = "uploaded.jpg",
            fileSize = 1024000,
            capturedBy = "testuser"
        ).copy(uploadedAt = System.currentTimeMillis())
        
        val pendingMetadata = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "总装工序",
            filePath = "/test/path/pending.jpg",
            fileName = "pending.jpg",
            fileSize = 2048000,
            capturedBy = "testuser"
        )
        
        metadataManager.savePhotoMetadata(uploadedMetadata)
        metadataManager.savePhotoMetadata(pendingMetadata)
        
        val pendingPhotos = metadataManager.getPendingUploadPhotos()
        
        assertEquals("应该有1张待上传照片", 1, pendingPhotos.size)
        assertEquals("待上传照片应该正确", "pending.jpg", pendingPhotos[0].fileName)
    }
    
    @Test
    fun testUpdateUploadStatus() {
        val metadata = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "热套工序",
            filePath = "/test/path/photo.jpg",
            fileName = "photo.jpg",
            fileSize = 1024000,
            capturedBy = "testuser"
        )
        
        metadataManager.savePhotoMetadata(metadata)
        
        // 更新为已上传
        val result = metadataManager.updateUploadStatus("/test/path/photo.jpg", true)
        
        assertTrue("更新应该成功", result)
        
        val updatedPhoto = metadataManager.getPhotoByPath("/test/path/photo.jpg")
        assertNotNull("照片应该存在", updatedPhoto)
        assertTrue("照片应该标记为已上传", updatedPhoto!!.isUploaded())
        
        // 更新为未上传
        val result2 = metadataManager.updateUploadStatus("/test/path/photo.jpg", false)
        
        assertTrue("更新应该成功", result2)
        
        val updatedPhoto2 = metadataManager.getPhotoByPath("/test/path/photo.jpg")
        assertNotNull("照片应该存在", updatedPhoto2)
        assertFalse("照片应该标记为未上传", updatedPhoto2!!.isUploaded())
    }
    
    @Test
    fun testDeletePhotoMetadata() {
        val metadata = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "热套工序",
            filePath = "/test/path/photo.jpg",
            fileName = "photo.jpg",
            fileSize = 1024000,
            capturedBy = "testuser"
        )
        
        metadataManager.savePhotoMetadata(metadata)
        
        // 验证照片存在
        assertNotNull("照片应该存在", metadataManager.getPhotoByPath("/test/path/photo.jpg"))
        
        val result = metadataManager.deletePhotoMetadata("/test/path/photo.jpg")
        
        assertTrue("删除应该成功", result)
        assertNull("照片应该被删除", metadataManager.getPhotoByPath("/test/path/photo.jpg"))
    }
    
    @Test
    fun testGetPhotoStatistics() {
        // 创建测试数据
        val metadata1 = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "热套工序",
            filePath = "/test/path/photo1.jpg",
            fileName = "photo1.jpg",
            fileSize = 1024000,
            capturedBy = "testuser"
        ).copy(uploadedAt = System.currentTimeMillis())
        
        val metadata2 = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "总装工序",
            filePath = "/test/path/photo2.jpg",
            fileName = "photo2.jpg",
            fileSize = 2048000,
            capturedBy = "testuser"
        )
        
        val metadata3 = PhotoMetadata.create(
            productSerial = "TEST002",
            processStep = "热套工序",
            filePath = "/test/path/photo3.jpg",
            fileName = "photo3.jpg",
            fileSize = 1536000,
            capturedBy = "testuser"
        )
        
        metadataManager.savePhotoMetadata(metadata1)
        metadataManager.savePhotoMetadata(metadata2)
        metadataManager.savePhotoMetadata(metadata3)
        
        val statistics = metadataManager.getPhotoStatistics()
        
        assertEquals("总照片数应该正确", 3, statistics.totalPhotos)
        assertEquals("已上传照片数应该正确", 1, statistics.uploadedPhotos)
        assertEquals("待上传照片数应该正确", 2, statistics.pendingPhotos)
        assertEquals("总文件大小应该正确", 4608000L, statistics.totalSize)
        
        // 验证按工序统计
        assertEquals("热套工序应该有2张照片", 2, statistics.byProcess["热套工序"])
        assertEquals("总装工序应该有1张照片", 1, statistics.byProcess["总装工序"])
        
        // 验证按产品统计
        assertEquals("TEST001应该有2张照片", 2, statistics.byProduct["TEST001"])
        assertEquals("TEST002应该有1张照片", 1, statistics.byProduct["TEST002"])
    }
    
    @Test
    fun testUploadQueue() {
        val metadata1 = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "热套工序",
            filePath = "/test/path/photo1.jpg",
            fileName = "photo1.jpg",
            fileSize = 1024000,
            capturedBy = "testuser"
        )
        
        val metadata2 = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "总装工序",
            filePath = "/test/path/photo2.jpg",
            fileName = "photo2.jpg",
            fileSize = 2048000,
            capturedBy = "testuser"
        )
        
        // 添加到上传队列
        metadataManager.addToUploadQueue(metadata1)
        metadataManager.addToUploadQueue(metadata2)
        
        val uploadQueue = metadataManager.getUploadQueue()
        assertEquals("上传队列应该有2张照片", 2, uploadQueue.size)
        
        // 从队列中移除
        metadataManager.removeFromUploadQueue("/test/path/photo1.jpg")
        
        val updatedQueue = metadataManager.getUploadQueue()
        assertEquals("上传队列应该有1张照片", 1, updatedQueue.size)
        assertEquals("剩余照片应该正确", "photo2.jpg", updatedQueue[0].fileName)
        
        // 清空队列
        metadataManager.clearUploadQueue()
        
        val emptyQueue = metadataManager.getUploadQueue()
        assertEquals("上传队列应该为空", 0, emptyQueue.size)
    }
    
    @Test
    fun testExportAndImportMetadata() {
        val metadata1 = PhotoMetadata.create(
            productSerial = "TEST001",
            processStep = "热套工序",
            filePath = "/test/path/photo1.jpg",
            fileName = "photo1.jpg",
            fileSize = 1024000,
            capturedBy = "testuser"
        )
        
        val metadata2 = PhotoMetadata.create(
            productSerial = "TEST002",
            processStep = "总装工序",
            filePath = "/test/path/photo2.jpg",
            fileName = "photo2.jpg",
            fileSize = 2048000,
            capturedBy = "testuser"
        )
        
        metadataManager.savePhotoMetadata(metadata1)
        metadataManager.savePhotoMetadata(metadata2)
        
        // 导出数据
        val exportedJson = metadataManager.exportMetadata()
        assertNotNull("导出的JSON不应该为空", exportedJson)
        assertTrue("导出的JSON应该包含数据", exportedJson.isNotEmpty())
        
        // 清空数据
        val prefs = context.getSharedPreferences("photo_metadata", Context.MODE_PRIVATE)
        prefs.edit().clear().apply()
        
        // 验证数据已清空
        assertEquals("数据应该被清空", 0, metadataManager.getPhotoStatistics().totalPhotos)
        
        // 导入数据
        val importResult = metadataManager.importMetadata(exportedJson)
        assertTrue("导入应该成功", importResult)
        
        // 验证导入结果
        val statistics = metadataManager.getPhotoStatistics()
        assertEquals("应该恢复2张照片", 2, statistics.totalPhotos)
        
        val test001Photos = metadataManager.getProductPhotos("TEST001")
        val test002Photos = metadataManager.getProductPhotos("TEST002")
        assertEquals("TEST001应该有1张照片", 1, test001Photos.size)
        assertEquals("TEST002应该有1张照片", 1, test002Photos.size)
    }
}