package com.testcenter.qrscanner.integration

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.testcenter.qrscanner.auth.AuthenticationService
import com.testcenter.qrscanner.auth.LocalUserManager
import com.testcenter.qrscanner.auth.LocalUserManager.LocalUser
import com.testcenter.qrscanner.auth.LocalUserManager.UserRole
import com.testcenter.qrscanner.auth.PermissionService
import com.testcenter.qrscanner.data.ProductRecord
import com.testcenter.qrscanner.database.UnifiedDataManager
import com.testcenter.qrscanner.material.MaterialRecordManager
import com.testcenter.qrscanner.material.MaterialUIController
import com.testcenter.qrscanner.ui.PermissionDialogManager
import kotlinx.coroutines.runBlocking
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.Mock
import org.mockito.MockitoAnnotations
import org.mockito.kotlin.whenever
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * 移动端权限控制集成测试
 * 测试完整的权限控制流程
 */
@RunWith(AndroidJUnit4::class)
class MobilePermissionIntegrationTest {

    private lateinit var context: Context
    private lateinit var permissionService: PermissionService
    private lateinit var materialRecordManager: MaterialRecordManager
    private lateinit var materialUIController: MaterialUIController
    private lateinit var permissionDialogManager: PermissionDialogManager
    
    @Mock
    private lateinit var localUserManager: LocalUserManager
    
    @Mock
    private lateinit var authenticationService: AuthenticationService
    
    @Mock
    private lateinit var unifiedDataManager: UnifiedDataManager
    
    private lateinit var adminUser: LocalUser
    private lateinit var regularUser: LocalUser
    private lateinit var existingRecord: ProductRecord

    @Before
    fun setUp() {
        MockitoAnnotations.openMocks(this)
        context = ApplicationProvider.getApplicationContext()
        
        // 初始化服务
        permissionService = PermissionService(localUserManager)
        materialRecordManager = MaterialRecordManager(context, authenticationService, unifiedDataManager)
        materialUIController = MaterialUIController(context)
        permissionDialogManager = PermissionDialogManager(context)
        
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
        
        // 创建已存在的产品记录
        existingRecord = ProductRecord(
            productSerial = "EXISTING001",
            productType = "测试产品",
            projectName = "测试项目",
            operator = "测试操作员",
            scanTime = System.currentTimeMillis(),
            materials = mapOf("物料1" to "SN001", "物料2" to "SN002")
        )
    }

    @Test
    fun testCompletePermissionFlowForAdminUser() = runBlocking {
        // 测试管理员用户的完整权限流程
        
        // 1. 权限服务测试
        val hasBasicPermission = permissionService.hasPermission(
            adminUser, 
            PermissionService.Permission.MOBILE_MATERIAL_RECORD
        )
        assertTrue(hasBasicPermission, "管理员应该有基本物料记录权限")
        
        val canModifyExisting = permissionService.hasPermission(
            adminUser,
            PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL
        )
        assertTrue(canModifyExisting, "管理员应该能修改已存在物料")
        
        // 2. 模拟已存在记录的权限验证
        whenever(authenticationService.isLoggedIn()).thenReturn(true)
        whenever(authenticationService.getCurrentUser()).thenReturn(adminUser)
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
            .thenReturn(true)
        whenever(unifiedDataManager.getRecord("EXISTING001")).thenReturn(existingRecord)
        whenever(authenticationService.canModifyExistingRecord("EXISTING001")).thenReturn(true)
        
        val permissionResult = materialRecordManager.validateMaterialModifyPermission("EXISTING001")
        
        assertTrue(permissionResult.allowed, "管理员应该被允许修改已存在记录")
        assertFalse(permissionResult.isReadOnlyMode, "管理员不应该进入只读模式")
        
        // 3. UI控制器测试
        val statusView = materialUIController.createPermissionStatusView(
            userRole = "管理员",
            canModify = true,
            productSerial = "EXISTING001"
        )
        assertNotNull(statusView, "应该能创建管理员权限状态视图")
    }

    @Test
    fun testCompletePermissionFlowForRegularUser() = runBlocking {
        // 测试普通用户的完整权限流程
        
        // 1. 权限服务测试
        val hasBasicPermission = permissionService.hasPermission(
            regularUser,
            PermissionService.Permission.MOBILE_MATERIAL_RECORD
        )
        assertTrue(hasBasicPermission, "普通用户应该有基本物料记录权限")
        
        val canModifyExisting = permissionService.hasPermission(
            regularUser,
            PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL
        )
        assertFalse(canModifyExisting, "普通用户不应该能修改已存在物料")
        
        // 2. 模拟已存在记录的权限验证
        whenever(authenticationService.isLoggedIn()).thenReturn(true)
        whenever(authenticationService.getCurrentUser()).thenReturn(regularUser)
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
            .thenReturn(true)
        whenever(unifiedDataManager.getRecord("EXISTING001")).thenReturn(existingRecord)
        whenever(authenticationService.canModifyExistingRecord("EXISTING001")).thenReturn(false)
        
        val permissionResult = materialRecordManager.validateMaterialModifyPermission("EXISTING001")
        
        assertFalse(permissionResult.allowed, "普通用户不应该被允许修改已存在记录")
        assertTrue(permissionResult.isReadOnlyMode, "普通用户应该进入只读模式")
        assertTrue(permissionResult.message.contains("只读模式"), "消息应该说明只读模式")
        
        // 3. UI控制器测试
        val statusView = materialUIController.createPermissionStatusView(
            userRole = "普通用户",
            canModify = false,
            productSerial = "EXISTING001"
        )
        assertNotNull(statusView, "应该能创建普通用户权限状态视图")
    }

    @Test
    fun testNewRecordPermissionFlow() = runBlocking {
        // 测试新记录的权限流程
        
        // 普通用户对新记录应该有权限
        whenever(authenticationService.isLoggedIn()).thenReturn(true)
        whenever(authenticationService.getCurrentUser()).thenReturn(regularUser)
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
            .thenReturn(true)
        whenever(unifiedDataManager.getRecord("NEW001")).thenReturn(null)
        
        val permissionResult = materialRecordManager.validateMaterialModifyPermission("NEW001")
        
        assertTrue(permissionResult.allowed, "普通用户应该能创建新记录")
        assertFalse(permissionResult.isReadOnlyMode, "新记录不应该是只读模式")
        assertTrue(permissionResult.message.contains("新产品记录"), "消息应该说明是新记录")
    }

    @Test
    fun testPermissionDeniedScenarios() {
        // 测试权限拒绝场景
        
        // 场景1：未登录用户
        whenever(authenticationService.getCurrentUser()).thenReturn(null)
        
        val noUserPermission = permissionService.hasPermission(
            null,
            PermissionService.Permission.MOBILE_MATERIAL_RECORD
        )
        assertFalse(noUserPermission, "未登录用户不应该有任何权限")
        
        // 场景2：权限验证结果
        val validationResult = permissionService.validatePermission(
            PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL
        )
        assertFalse(validationResult.allowed, "未登录时权限验证应该失败")
        assertEquals("用户未登录", validationResult.message, "应该显示未登录消息")
    }

    @Test
    fun testPermissionUIIntegration() {
        // 测试权限UI集成
        
        // 测试各种对话框创建
        try {
            materialUIController.showPermissionDeniedDialog("权限不足测试")
            materialUIController.showReadOnlyModeDialog("TEST001", "普通用户")
            materialUIController.showModificationAttemptDeniedDialog("TEST001", "修改物料")
            materialUIController.showSessionExpiredDialog()
            materialUIController.showPermissionValidationFailedDialog("网络错误")
            materialUIController.showModificationBlockedDialog("TEST001")
            
            assertTrue(true, "所有权限UI对话框应该能正常创建")
        } catch (e: Exception) {
            assertTrue(false, "权限UI对话框创建异常: ${e.message}")
        }
    }

    @Test
    fun testPermissionServiceRoleMapping() {
        // 测试权限服务角色映射
        
        val adminPermissions = permissionService.getUserPermissions(adminUser)
        val userPermissions = permissionService.getUserPermissions(regularUser)
        
        // 管理员权限检查
        assertTrue(adminPermissions.contains(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
        assertTrue(adminPermissions.contains(PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL))
        assertTrue(adminPermissions.contains(PermissionService.Permission.WEB_MODIFY_RECORDS))
        assertTrue(adminPermissions.contains(PermissionService.Permission.WEB_DELETE_RECORDS))
        
        // 普通用户权限检查
        assertTrue(userPermissions.contains(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
        assertFalse(userPermissions.contains(PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL))
        assertFalse(userPermissions.contains(PermissionService.Permission.WEB_MODIFY_RECORDS))
        assertFalse(userPermissions.contains(PermissionService.Permission.WEB_DELETE_RECORDS))
        
        // 权限数量检查
        assertTrue(adminPermissions.size > userPermissions.size, "管理员权限应该比普通用户多")
    }

    @Test
    fun testPermissionDescriptions() {
        // 测试权限描述
        
        val materialRecordDesc = permissionService.getPermissionDescription(
            PermissionService.Permission.MOBILE_MATERIAL_RECORD
        )
        assertEquals("移动端物料记录", materialRecordDesc)
        
        val modifyExistingDesc = permissionService.getPermissionDescription(
            PermissionService.Permission.MOBILE_MODIFY_EXISTING_MATERIAL
        )
        assertEquals("修改已存在物料", modifyExistingDesc)
        
        val adminRoleDesc = permissionService.getRoleDescription(UserRole.ADMIN)
        assertEquals("管理员", adminRoleDesc)
        
        val userRoleDesc = permissionService.getRoleDescription(UserRole.USER)
        assertEquals("普通用户", userRoleDesc)
    }

    @Test
    fun testPermissionDialogManager() {
        // 测试权限对话框管理器
        
        // 测试创建权限状态视图
        val adminStatusView = permissionDialogManager.createPermissionStatusView(
            userRole = "管理员",
            canModify = true,
            productSerial = "TEST001"
        )
        assertNotNull(adminStatusView, "管理员权限状态视图应该创建成功")
        
        val userStatusView = permissionDialogManager.createPermissionStatusView(
            userRole = "普通用户",
            canModify = false,
            productSerial = "TEST001"
        )
        assertNotNull(userStatusView, "普通用户权限状态视图应该创建成功")
        
        // 测试显示各种对话框（不会抛出异常即为成功）
        try {
            permissionDialogManager.showPermissionDeniedDialog("测试权限拒绝")
            permissionDialogManager.showMaterialModificationDeniedDialog("TEST001")
            permissionDialogManager.showReadOnlyModeDialog("TEST001", "普通用户")
            permissionDialogManager.showOperationBlockedDialog("修改操作", "权限不足")
            permissionDialogManager.showSessionExpiredDialog()
            permissionDialogManager.showPermissionValidationFailedDialog("验证失败")
            
            assertTrue(true, "所有权限对话框应该能正常显示")
        } catch (e: Exception) {
            assertTrue(false, "权限对话框显示异常: ${e.message}")
        }
    }
}