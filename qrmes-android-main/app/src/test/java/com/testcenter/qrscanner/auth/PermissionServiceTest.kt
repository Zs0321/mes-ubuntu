package com.testcenter.qrscanner.auth

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.testcenter.qrscanner.auth.LocalUserManager.LocalUser
import com.testcenter.qrscanner.auth.LocalUserManager.UserRole
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.Mock
import org.mockito.MockitoAnnotations
import org.mockito.kotlin.whenever
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * 权限服务测试
 * 测试不同角色用户的物料修改权限
 */
@RunWith(AndroidJUnit4::class)
class PermissionServiceTest {

    @Mock
    private lateinit var localUserManager: LocalUserManager
    
    private lateinit var permissionService: PermissionService
    
    private lateinit var adminUser: LocalUser
    private lateinit var regularUser: LocalUser

    @Before
    fun setUp() {
        MockitoAnnotations.openMocks(this)
        permissionService = PermissionService(localUserManager)
        
        // 创建测试用户
        adminUser = LocalUser(
            id = "admin-001",
            synologyUsername = "admin",
            displayName = "管理员用户",
            role = UserRole.ADMIN,
            createdAt = System.currentTimeMillis(),
            updatedAt = System.currentTimeMillis(),
            lastLoginAt = System.currentTimeMillis()
        )
        
        regularUser = LocalUser(
            id = "user-001", 
            synologyUsername = "user",
            displayName = "普通用户",
            role = UserRole.USER,
            createdAt = System.currentTimeMillis(),
            updatedAt = System.currentTimeMillis(),
            lastLoginAt = System.currentTimeMillis()
        )
    }

    @Test
    fun testAdminUserHasMaterialRecordPermission() {
        // 测试管理员用户具有物料记录权限
        val hasPermission = permissionService.hasPermission(
            adminUser, 
            PermissionService.Permission.MOBILE_MATERIAL_RECORD
        )
        assertTrue(hasPermission, "管理员应该具有物料记录权限")
    }

    @Test
    fun testRegularUserHasMaterialRecordPermission() {
        // 测试普通用户具有物料记录权限
        val hasPermission = permissionService.hasPermission(
            regularUser,
            PermissionService.Permission.MOBILE_MATERIAL_RECORD
        )
        assertTrue(hasPermission, "普通用户应该具有物料记录权限")
    }

    @Test
    fun testAdminUserCanModifyExistingMaterial() {
        // 测试管理员用户可以修改已存在物料
        val hasPermission = permissionService.hasPermission(
            adminUser,
            PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL
        )
        assertTrue(hasPermission, "管理员应该可以修改已存在物料")
    }

    @Test
    fun testRegularUserCannotModifyExistingMaterial() {
        // 测试普通用户不能修改已存在物料
        val hasPermission = permissionService.hasPermission(
            regularUser,
            PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL
        )
        assertFalse(hasPermission, "普通用户不应该能修改已存在物料")
    }

    @Test
    fun testCanModifyExistingRecordForAdmin() {
        // 测试管理员可以修改已存在记录
        val canModify = permissionService.canModifyExistingRecord(adminUser, "TEST001")
        assertTrue(canModify, "管理员应该可以修改已存在记录")
    }

    @Test
    fun testCannotModifyExistingRecordForRegularUser() {
        // 测试普通用户不能修改已存在记录
        val canModify = permissionService.canModifyExistingRecord(regularUser, "TEST001")
        assertFalse(canModify, "普通用户不应该能修改已存在记录")
    }

    @Test
    fun testNullUserHasNoPermissions() {
        // 测试空用户没有任何权限
        val hasPermission = permissionService.hasPermission(
            null,
            PermissionService.Permission.MOBILE_MATERIAL_RECORD
        )
        assertFalse(hasPermission, "空用户不应该有任何权限")
    }

    @Test
    fun testValidatePermissionForLoggedInAdmin() {
        // 测试已登录管理员的权限验证
        whenever(localUserManager.getCurrentUser()).thenReturn(adminUser)
        
        val result = permissionService.validatePermission(
            PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL
        )
        
        assertTrue(result.allowed, "管理员权限验证应该通过")
        assertEquals(null, result.message, "成功时不应该有错误消息")
    }

    @Test
    fun testValidatePermissionForLoggedInRegularUser() {
        // 测试已登录普通用户的权限验证
        whenever(localUserManager.getCurrentUser()).thenReturn(regularUser)
        
        val result = permissionService.validatePermission(
            PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL
        )
        
        assertFalse(result.allowed, "普通用户权限验证应该失败")
        assertTrue(result.message?.contains("权限不足") == true, "应该包含权限不足的消息")
    }

    @Test
    fun testValidatePermissionForNotLoggedInUser() {
        // 测试未登录用户的权限验证
        whenever(localUserManager.getCurrentUser()).thenReturn(null)
        
        val result = permissionService.validatePermission(
            PermissionService.Permission.MOBILE_MATERIAL_RECORD
        )
        
        assertFalse(result.allowed, "未登录用户权限验证应该失败")
        assertEquals("用户未登录", result.message, "应该显示未登录消息")
    }

    @Test
    fun testValidateModifyExistingRecordForAdmin() {
        // 测试管理员修改已存在记录的权限验证
        whenever(localUserManager.getCurrentUser()).thenReturn(adminUser)
        
        val result = permissionService.validateModifyExistingRecord("TEST001")
        
        assertTrue(result.allowed, "管理员应该可以修改已存在记录")
    }

    @Test
    fun testValidateModifyExistingRecordForRegularUser() {
        // 测试普通用户修改已存在记录的权限验证
        whenever(localUserManager.getCurrentUser()).thenReturn(regularUser)
        
        val result = permissionService.validateModifyExistingRecord("TEST001")
        
        assertFalse(result.allowed, "普通用户不应该能修改已存在记录")
        assertTrue(result.message?.contains("普通用户不能修改") == true, "应该包含权限限制消息")
    }

    @Test
    fun testIsAdminForAdminUser() {
        // 测试管理员用户身份检查
        assertTrue(permissionService.isAdmin(adminUser), "应该识别管理员用户")
    }

    @Test
    fun testIsAdminForRegularUser() {
        // 测试普通用户身份检查
        assertFalse(permissionService.isAdmin(regularUser), "不应该将普通用户识别为管理员")
    }

    @Test
    fun testGetUserPermissionsForAdmin() {
        // 测试获取管理员用户权限
        val permissions = permissionService.getUserPermissions(adminUser)
        
        assertTrue(permissions.contains(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
        assertTrue(permissions.contains(PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL))
        assertTrue(permissions.contains(PermissionService.Permission.WEB_MODIFY_RECORDS))
        assertTrue(permissions.contains(PermissionService.Permission.WEB_DELETE_RECORDS))
    }

    @Test
    fun testGetUserPermissionsForRegularUser() {
        // 测试获取普通用户权限
        val permissions = permissionService.getUserPermissions(regularUser)
        
        assertTrue(permissions.contains(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
        assertFalse(permissions.contains(PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL))
        assertFalse(permissions.contains(PermissionService.Permission.WEB_MODIFY_RECORDS))
        assertFalse(permissions.contains(PermissionService.Permission.WEB_DELETE_RECORDS))
    }

    @Test
    fun testGetPermissionDescription() {
        // 测试权限描述获取
        val description = permissionService.getPermissionDescription(
            PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL
        )
        assertEquals("修改已存在物料", description)
    }

    @Test
    fun testGetRoleDescription() {
        // 测试角色描述获取
        assertEquals("管理员", permissionService.getRoleDescription(UserRole.ADMIN))
        assertEquals("普通用户", permissionService.getRoleDescription(UserRole.USER))
    }
}