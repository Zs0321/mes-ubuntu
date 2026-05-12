package com.testcenter.qrscanner.network

import com.testcenter.qrscanner.data.ProjectConfig
import com.testcenter.qrscanner.data.TestRecord
import java.util.Date

/**
 * Common interface for file operations (WebDAV, SMB, etc.)
 */
interface FileManager {
    
    /**
     * Test connection to the file server
     */
    suspend fun testConnection(): Boolean
    
    /**
     * Sync test records to server
     */
    suspend fun syncTestRecords(records: List<TestRecord>): Boolean
    
    /**
     * Save records to local storage as backup
     */
    suspend fun saveToLocalStorage(records: List<TestRecord>): String?
    
    /**
     * Fetch tester list from server
     */
    suspend fun fetchTesterList(): List<String>
    
    /**
     * Save tester list to server
     */
    suspend fun saveTesterList(testers: List<String>): Boolean
    
    /**
     * Fetch active tests from server
     */
    suspend fun fetchActiveTests(): List<ActiveTest>
    
    /**
     * Add or update an active test
     */
    suspend fun upsertActiveTest(serial: String, tester: String, startTime: Date): Boolean
    
    /**
     * Remove an active test
     */
    suspend fun removeActiveTest(serial: String): Boolean
    
    /**
     * Query product record by serial number
     */
    suspend fun queryProductRecord(productSerial: String): ProductRecord?
    
    /**
     * Fetch project list from server
     */
    suspend fun fetchProjectList(): List<String>
    
    /**
     * Save project list to server
     */
    suspend fun saveProjectList(projects: List<String>): Boolean
    
    /**
     * Fetch project configuration from server
     * @param projectName The name of the project
     * @return ProjectConfig object or null if not found
     */
    suspend fun fetchProjectConfig(projectName: String): ProjectConfig?
    
    /**
     * Save project configuration to server
     * @param config The project configuration to save
     * @return True if successful, false otherwise
     */
    suspend fun saveProjectConfig(config: ProjectConfig): Boolean
    
    /**
     * Upload photo to server
     * @param directoryInfo Folder hierarchy information (project/product/serial)
     * @param fileName The file name (already sanitized)
     * @param photoBytes The photo data in bytes
     * @return True if successful, false otherwise
     */
    suspend fun uploadPhoto(directoryInfo: PhotoDirectoryInfo, fileName: String, photoBytes: ByteArray): Boolean
    
    /**
     * List photos for a product
     * @param directoryInfo Folder hierarchy information (project/product/serial)
     * @return List of photo information
     */
    suspend fun listPhotos(directoryInfo: PhotoDirectoryInfo): List<PhotoInfo>
    
    /**
     * Download photo from server
     * @param directoryInfo Folder hierarchy information (project/product/serial)
     * @param fileName The photo file name
     * @return Photo bytes or null if failed
     */
    suspend fun downloadPhoto(directoryInfo: PhotoDirectoryInfo, fileName: String): ByteArray?
    
    /**
     * 列出NAS中可用的APK文件
     */
    suspend fun listApkFiles(): List<ApkFileInfo>

    /**
     * 下载指定APK文件
     * @param apkFileName APK文件名（位于APK目录下）
     * @return APK文件的二进制内容，失败时返回null
     */
    suspend fun downloadApk(apkFileName: String): ByteArray?
    
    /**
     * Data class for active test information
     */
    data class ActiveTest(val serial: String, val tester: String, val startTime: String)
    
    /**
     * Directory info for photo storage
     */
    data class PhotoDirectoryInfo(
        val projectName: String,
        val projectCode: String,
        val productType: String,
        val modelNumber: String,
        val productSerial: String
    )
    
    /**
     * APK文件信息
     */
    data class ApkFileInfo(
        val fileName: String,
        val versionName: String?,
        val buildNumber: String?,
        val sizeBytes: Long,
        val lastModified: Long
    )
    
    /**
     * 照片文件信息
     */
    data class PhotoInfo(
        val fileName: String,
        val filePath: String,
        val fileSize: Long,
        val lastModified: Long
    )
    
    /**
     * Data class for product record
     */
    data class ProductRecord(
        val productSerial: String,
        val productType: String = "",  // 新增：产品类型，用于初始化物料列表
        val projectName: String,
        val operator: String,
        val scanTime: String,
        val controlBoard: String = "",
        val drivingCapacitor: String = "",
        val pumpCapacitor: String = "",
        val drivingPower: String = "",
        val pumpPower: String = "",
        // 新增：动态组件数据（组件名 -> 序列号）
        val components: Map<String, String> = emptyMap()
    )
}
