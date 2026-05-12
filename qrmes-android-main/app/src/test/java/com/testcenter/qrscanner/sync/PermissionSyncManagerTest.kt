package com.testcenter.qrscanner.sync

import com.testcenter.qrscanner.utils.PreferencesManager
import io.mockk.*
import kotlinx.coroutines.runBlocking
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/**
 * PermissionSyncManager 单元测试
 */
class PermissionSyncManagerTest {
    
    private lateinit var preferencesManager: PreferencesManager
    private lateinit var permissionSyncManager: PermissionSyncManager
    
    @Before
    fun setup() {
        preferencesManager = mockk(relaxed = true)
        permissionSyncManager = PermissionSyncManager(preferencesManager)
    }
    
    @After
    fun tearDown() {
        unmockkAll()
    }
    
    @Test
    fun `syncPermissions should return failure when username is null`() = runBlocking {
        // Given
        every { preferencesManager.getUsername() } returns null
        
        // When
        val result = permissionSyncManager.syncPermissions()
        
        // Then
        assertTrue(result is PermissionSyncResult.Failure)
        assertEquals("未找到用户名", (result as PermissionSyncResult.Failure).errorMessage)
    }
    
    @Test
    fun `syncPermissions should return failure when username is blank`() = runBlocking {
        // Given
        every { preferencesManager.getUsername() } returns ""
        
        // When
        val result = permissionSyncManager.syncPermissions()
        
        // Then
        assertTrue(result is PermissionSyncResult.Failure)
        assertEquals("未找到用户名", (result as PermissionSyncResult.Failure).errorMessage)
    }
    
    @Test
    fun `syncPermissions should return failure when mesapp URL is null`() = runBlocking {
        // Given
        every { preferencesManager.getUsername() } returns "testuser"
        every { preferencesManager.getMesappUrl() } returns null
        
        // When
        val result = permissionSyncManager.syncPermissions()
        
        // Then
        assertTrue(result is PermissionSyncResult.Failure)
        assertEquals("未配置服务器地址", (result as PermissionSyncResult.Failure).errorMessage)
    }
    
    @Test
    fun `syncPermissions should return failure when mesapp URL is blank`() = runBlocking {
        // Given
        every { preferencesManager.getUsername() } returns "testuser"
        every { preferencesManager.getMesappUrl() } returns ""
        
        // When
        val result = permissionSyncManager.syncPermissions()
        
        // Then
        assertTrue(result is PermissionSyncResult.Failure)
        assertEquals("未配置服务器地址", (result as PermissionSyncResult.Failure).errorMessage)
    }
    
    @Test
    fun `UserPermissions toJson should create correct JSON structure`() {
        // Given
        val permissions = UserPermissions(
            username = "testuser",
            role = "admin",
            canModifyRecords = true,
            canDeleteRecords = true,
            canManageUsers = true,
            canAccessAllProjects = true,
            timestamp = "2025-10-19T23:54:00.163893"
        )
        
        // When
        val json = permissions.toJson()
        
        // Then
        assertTrue(json.contains("\"username\":\"testuser\""))
        assertTrue(json.contains("\"role\":\"admin\""))
        assertTrue(json.contains("\"can_modify_records\":true"))
        assertTrue(json.contains("\"can_delete_records\":true"))
        assertTrue(json.contains("\"can_manage_users\":true"))
        assertTrue(json.contains("\"can_access_all_projects\":true"))
    }
    
    @Test
    fun `UserPermissions isAdmin should return true for admin role`() {
        // Given
        val adminPermissions = UserPermissions(
            username = "admin",
            role = "admin",
            canModifyRecords = true,
            canDeleteRecords = true,
            canManageUsers = true,
            canAccessAllProjects = true,
            timestamp = "2025-10-19T23:54:00"
        )
        
        // Then
        assertTrue(adminPermissions.isAdmin())
    }
    
    @Test
    fun `UserPermissions isAdmin should return false for user role`() {
        // Given
        val userPermissions = UserPermissions(
            username = "user",
            role = "user",
            canModifyRecords = false,
            canDeleteRecords = false,
            canManageUsers = false,
            canAccessAllProjects = false,
            timestamp = "2025-10-19T23:54:00"
        )
        
        // Then
        assertFalse(userPermissions.isAdmin())
    }
    
    @Test
    fun `PermissionSyncResult Success should have success true`() {
        // Given
        val permissions = UserPermissions(
            username = "test",
            role = "user",
            canModifyRecords = false,
            canDeleteRecords = false,
            canManageUsers = false,
            canAccessAllProjects = false,
            timestamp = "2025-10-19T23:54:00"
        )
        val result = PermissionSyncResult.Success(permissions)
        
        // Then
        assertTrue(result.success)
        assertNull(result.errorMessage)
    }
    
    @Test
    fun `PermissionSyncResult Failure should have success false`() {
        // Given
        val result = PermissionSyncResult.Failure("Test error")
        
        // Then
        assertFalse(result.success)
        assertEquals("Test error", result.errorMessage)
    }
}
