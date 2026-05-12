package com.testcenter.qrscanner.auth

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import com.testcenter.qrscanner.network.FileManagerFactory
import com.testcenter.qrscanner.sync.UserPermissions
import com.testcenter.qrscanner.utils.AppLogger
import com.testcenter.qrscanner.utils.PreferencesManager
import java.io.File

/**
 * 基于 SQLite 数据库的权限读取器
 * 
 * WebDAV 模式：下载 web_users.db 数据库文件到本地，直接查询细粒度权限
 * 
 * 优势：
 * - 直接查询 SQLite 数据库，无需 JSON 解析
 * - 与服务器端数据结构完全一致
 * - 支持细粒度权限查询（基于角色的权限映射）
 * - 离线可用
 */
class DatabasePermissionReader(
    private val context: Context,
    private val preferencesManager: PreferencesManager
) {
    companion object {
        private const val TAG = "DatabasePermissionReader"
        private const val DB_FILE_PATH = "web_users.db"  // 服务器端数据库文件
        private const val CACHE_DIR = "permissions_cache"
        private const val CACHE_DB_NAME = "web_users.db"
    }
    
    /**
     * 读取用户权限
     * 
     * 1. 尝试从服务器下载最新的数据库文件
     * 2. 如果下载失败，使用本地缓存
     * 3. 直接查询 SQLite 数据库获取细粒度权限
     */
    suspend fun readUserPermissions(username: String): UserPermissions? {
        return try {
            AppLogger.log(TAG, "Reading permissions for user: $username")
            
            // 1. 尝试从服务器下载数据库文件
            val dbFile = downloadDatabaseFile()
            
            if (dbFile != null && dbFile.exists()) {
                // 2. 查询数据库
                val permissions = queryUserPermissionsFromDb(dbFile, username)
                
                if (permissions != null) {
                    AppLogger.log(TAG, "Successfully read permissions from database for user: $username")
                    return permissions
                }
            }
            
            // 3. 如果服务器下载失败，尝试使用本地缓存
            AppLogger.log(TAG, "Server download failed, trying local cache")
            val cachedDb = getCachedDatabaseFile()
            if (cachedDb != null && cachedDb.exists()) {
                val permissions = queryUserPermissionsFromDb(cachedDb, username)
                if (permissions != null) {
                    AppLogger.log(TAG, "Successfully read permissions from cache for user: $username")
                    return permissions
                }
            }
            
            AppLogger.log(TAG, "Failed to read permissions for user: $username")
            null
        } catch (e: Exception) {
            AppLogger.log(TAG, "Error reading permissions for user: $username", e)
            null
        }
    }
    
    /**
     * 从服务器下载数据库文件
     */
    private suspend fun downloadDatabaseFile(): File? {
        return try {
            // TODO: Implement database file download when FileManager supports it
            AppLogger.log(TAG, "Database file download not yet implemented, using cached version if available")
            return null
            
            /* 
            val fileManager = FileManagerFactory.create(
                context,
                preferencesManager.getUsername(),
                preferencesManager.getPassword()
            )
            
            // 下载数据库文件
            val fileContent = fileManager.downloadFile(DB_FILE_PATH)
            
            if (fileContent != null) {
                // 保存到缓存目录
                val cacheDir = File(context.filesDir, CACHE_DIR)
                if (!cacheDir.exists()) {
                    cacheDir.mkdirs()
                }
                
                val cacheFile = File(cacheDir, CACHE_DB_NAME)
                cacheFile.writeBytes(fileContent)
                
                // 记录缓存时间
                preferencesManager.putString("permissions_db_cache_time", System.currentTimeMillis().toString())
                
                AppLogger.log(TAG, "Database file downloaded and cached successfully, size: ${fileContent.size} bytes")
                cacheFile
            } else {
                AppLogger.log(TAG, "Failed to download database file: file content is null")
                null
            }
            */
        } catch (e: Exception) {
            AppLogger.log(TAG, "Error downloading database file", e)
            null
        }
    }
    
    /**
     * 获取本地缓存的数据库文件
     */
    private fun getCachedDatabaseFile(): File? {
        return try {
            val cacheDir = File(context.filesDir, CACHE_DIR)
            val cacheFile = File(cacheDir, CACHE_DB_NAME)
            
            if (cacheFile.exists()) {
                AppLogger.log(TAG, "Found cached database file, size: ${cacheFile.length()} bytes")
                cacheFile
            } else {
                AppLogger.log(TAG, "No cached database file found")
                null
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "Error getting cached database file", e)
            null
        }
    }
    
    /**
     * 从 SQLite 数据库查询用户细粒度权限
     * 
     * 查询逻辑：
     * 1. 查询用户基本信息（role）
     * 2. 根据角色映射到具体权限（与服务器端 PermissionService 一致）
     */
    private fun queryUserPermissionsFromDb(dbFile: File, username: String): UserPermissions? {
        var db: SQLiteDatabase? = null
        return try {
            // 打开数据库（只读模式）
            db = SQLiteDatabase.openDatabase(
                dbFile.absolutePath,
                null,
                SQLiteDatabase.OPEN_READONLY
            )
            
            // 查询用户信息
            val cursor = db.rawQuery(
                "SELECT * FROM users WHERE synology_username = ? LIMIT 1",
                arrayOf(username)
            )
            
            if (cursor.moveToFirst()) {
                val roleIndex = cursor.getColumnIndex("role")
                val role = if (roleIndex >= 0) cursor.getString(roleIndex) else "user"
                
                cursor.close()
                
                // 根据角色映射到细粒度权限（与服务器端 PermissionService 一致）
                val isAdmin = role == "admin"
                
                val permissions = UserPermissions(
                    username = username,
                    role = role,
                    // 基于角色的权限映射
                    canModifyRecords = isAdmin,  // 管理员可以修改记录
                    canDeleteRecords = isAdmin,  // 管理员可以删除记录
                    canManageUsers = isAdmin,    // 管理员可以管理用户
                    canAccessAllProjects = isAdmin,  // 管理员可以访问所有项目
                    timestamp = System.currentTimeMillis().toString()
                )
                
                AppLogger.log(TAG, "Queried permissions from database: username=$username, role=$role, " +
                        "canModify=$isAdmin, canDelete=$isAdmin, canManageUsers=$isAdmin")
                
                permissions
            } else {
                cursor.close()
                AppLogger.log(TAG, "User $username not found in database")
                null
            }
        } catch (e: Exception) {
            AppLogger.log(TAG, "Error querying database", e)
            null
        } finally {
            db?.close()
        }
    }
    
    /**
     * 检查缓存是否过期
     */
    fun isCacheExpired(maxAgeMillis: Long = 5 * 60 * 1000): Boolean {
        return try {
            val cacheTimeStr = preferencesManager.getString("permissions_db_cache_time", "0")
            val cacheTime = cacheTimeStr.toLongOrNull() ?: 0L
            val currentTime = System.currentTimeMillis()
            
            (currentTime - cacheTime) > maxAgeMillis
        } catch (e: Exception) {
            true
        }
    }
    
    /**
     * 清除权限缓存
     */
    fun clearCache() {
        try {
            val cacheDir = File(context.filesDir, CACHE_DIR)
            val cacheFile = File(cacheDir, CACHE_DB_NAME)
            
            if (cacheFile.exists()) {
                cacheFile.delete()
                AppLogger.log(TAG, "Permissions database cache cleared")
            }
            
            preferencesManager.putString("permissions_db_cache_time", "0")
        } catch (e: Exception) {
            AppLogger.log(TAG, "Error clearing permissions cache", e)
        }
    }
}
