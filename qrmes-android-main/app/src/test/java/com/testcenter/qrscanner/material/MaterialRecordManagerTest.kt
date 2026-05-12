package com.testcenter.qrscanner.material

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.testcenter.qrscanner.auth.AuthenticationService
import com.testcenter.qrscanner.auth.LocalUserManager.LocalUser
import com.testcenter.qrscanner.auth.LocalUserManager.UserRole
import com.testcenter.qrscanner.auth.PermissionService
import com.testcenter.qrscanner.data.ProductRecord
import com.testcenter.qrscanner.database.UnifiedDataManager
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
 * 物料记录管理器测试
 * 测试已存在记录的权限验证逻辑
 */
@RunWith(AndroidJUnit4::class)
class MaterialRecordManagerTest {

    private lateinit var context: Context
    private lateinit var materialRecordManager: MaterialRecordManager
    
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
        
        materialRecordManager = MaterialRecordManager(
            context = context,
            authenticationService = authenticationService,
            unifiedDataManager = unifiedDataManager
        )
        
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
            materials = emptyMap()
        )
    }

    @Test
    fun testCheckProductRecordExists() = runBlocking {
        // 测试检查已存在的产品记录
        whenever(unifiedDataManager.getRecord("EXISTING001")).thenReturn(existingRecord)
        whenever(authenticationService.canModifyExistingRecord("EXISTING001")).thenReturn(false)
        
        val result = materialRecordManager.checkProductRecord("EXISTING001")
        
        assertTrue(result.exists, "应该检测到记录存在")
        assertFalse(result.canModify, "普通用户不应该能修改")
        assertNotNull(result.record, "应该返回记录数据")
        assertTrue(result.message?.contains("记录已存在") == true, "消息应该说明记录已存在")
    }

    @Test
    fun testCheckProductRecordNotExists() = runBlocking {
        // 测试检查不存在的产品记录
        whenever(unifiedDataManager.getRecord("NEW001")).thenReturn(null)
        
        val result = materialRecordManager.checkProductRecord("NEW001")
        
        assertFalse(result.exists, "应该检测到记录不存在")
        assertTrue(result.canModify, "新记录应该可以创建")
        assertEquals(null, result.record, "不应该返回记录数据")
        assertTrue(result.message?.contains("新产品记录") == true, "消息应该说明是新记录")
    }

    @Test
    fun testValidateMaterialModifyPermissionForAdminWithExistingRecord() = runBlocking {
        // 测试管理员修改已存在记录的权限验证
        whenever(authenticationService.isLoggedIn()).thenReturn(true)
        whenever(authenticationService.getCurrentUser()).thenReturn(adminUser)
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
            .thenReturn(true)
        whenever(unifiedDataManager.getRecord("EXISTING001")).thenReturn(existingRecord)
        whenever(authenticationService.canModifyExistingRecord("EXISTING001")).thenReturn(true)
        
        val result = materialRecordManager.validateMaterialModifyPermission("EXISTING001")
        
        assertTrue(result.allowed, "管理员应该可以修改已存在记录")
        assertFalse(result.isReadOnlyMode, "管理员不应该进入只读模式")
        assertTrue(result.message.contains("管理员用户"), "消息应该说明管理员权限")
    }

    @Test
    fun testValidateMaterialModifyPermissionForRegularUserWithExistingRecord() = runBlocking {
        // 测试普通用户修改已存在记录的权限验证
        whenever(authenticationService.isLoggedIn()).thenReturn(true)
        whenever(authenticationService.getCurrentUser()).thenReturn(regularUser)
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
            .thenReturn(true)
        whenever(unifiedDataManager.getRecord("EXISTING001")).thenReturn(existingRecord)
        whenever(authenticationService.canModifyExistingRecord("EXISTING001")).thenReturn(false)
        
        val result = materialRecordManager.validateMaterialModifyPermission("EXISTING001")
        
        assertFalse(result.allowed, "普通用户不应该能修改已存在记录")
        assertTrue(result.isReadOnlyMode, "普通用户应该进入只读模式")
        assertTrue(result.message.contains("只读模式"), "消息应该说明只读模式")
    }

    @Test
    fun testValidateMaterialModifyPermissionForNewRecord() = runBlocking {
        // 测试新记录的权限验证
        whenever(authenticationService.isLoggedIn()).thenReturn(true)
        whenever(authenticationService.getCurrentUser()).thenReturn(regularUser)
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
            .thenReturn(true)
        whenever(unifiedDataManager.getRecord("NEW001")).thenReturn(null)
        
        val result = materialRecordManager.validateMaterialModifyPermission("NEW001")
        
        assertTrue(result.allowed, "新记录应该允许创建")
        assertFalse(result.isReadOnlyMode, "新记录不应该是只读模式")
        assertTrue(result.message.contains("新产品记录"), "消息应该说明是新记录")
    }

    @Test
    fun testValidateMaterialModifyPermissionForNotLoggedInUser() = runBlocking {
        // 测试未登录用户的权限验证
        whenever(authenticationService.isLoggedIn()).thenReturn(false)
        
        val result = materialRecordManager.validateMaterialModifyPermission("TEST001")
        
        assertFalse(result.allowed, "未登录用户不应该有权限")
        assertTrue(result.message.contains("未登录"), "消息应该说明未登录")
    }

    @Test
    fun testValidateMaterialModifyPermissionWithoutBasicPermission() = runBlocking {
        // 测试没有基本物料记录权限的用户
        whenever(authenticationService.isLoggedIn()).thenReturn(true)
        whenever(authenticationService.getCurrentUser()).thenReturn(regularUser)
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
            .thenReturn(false)
        
        val result = materialRecordManager.validateMaterialModifyPermission("TEST001")
        
        assertFalse(result.allowed, "没有基本权限的用户不应该有权限")
        assertTrue(result.message.contains("没有物料记录权限"), "消息应该说明缺少基本权限")
    }

    @Test
    fun testSaveMaterialRecordWithPermission() = runBlocking {
        // 测试有权限保存物料记录
        whenever(authenticationService.isLoggedIn()).thenReturn(true)
        whenever(authenticationService.getCurrentUser()).thenReturn(adminUser)
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
            .thenReturn(true)
        whenever(unifiedDataManager.getRecord("NEW001")).thenReturn(null)
        whenever(unifiedDataManager.saveRecord(existingRecord, true))
            .thenReturn(true)
        
        val result = materialRecordManager.saveMaterialRecord("NEW001", mapOf("test" to "data"))
        
        assertTrue(result.success, "保存应该成功")
        assertTrue(result.message.contains("保存成功"), "消息应该说明保存成功")
    }

    @Test
    fun testSaveMaterialRecordWithoutPermission() = runBlocking {
        // 测试没有权限保存物料记录
        whenever(authenticationService.isLoggedIn()).thenReturn(true)
        whenever(authenticationService.getCurrentUser()).thenReturn(regularUser)
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
            .thenReturn(true)
        whenever(unifiedDataManager.getRecord("EXISTING001")).thenReturn(existingRecord)
        whenever(authenticationService.canModifyExistingRecord("EXISTING001")).thenReturn(false)
        
        val result = materialRecordManager.saveMaterialRecord("EXISTING001", mapOf("test" to "data"))
        
        assertFalse(result.success, "保存应该失败")
        assertTrue(result.message.contains("保存失败"), "消息应该说明保存失败")
    }

    @Test
    fun testGetCurrentUserPermissionSummaryForAdmin() {
        // 测试获取管理员用户权限摘要
        whenever(authenticationService.getCurrentUser()).thenReturn(adminUser)
        
        val summary = materialRecordManager.getCurrentUserPermissionSummary()
        
        assertTrue(summary.contains("管理员用户"), "摘要应该包含用户名")
        assertTrue(summary.contains("管理员"), "摘要应该包含角色")
    }

    @Test
    fun testGetCurrentUserPermissionSummaryForRegularUser() {
        // 测试获取普通用户权限摘要
        whenever(authenticationService.getCurrentUser()).thenReturn(regularUser)
        
        val summary = materialRecordManager.getCurrentUserPermissionSummary()
        
        assertTrue(summary.contains("普通用户"), "摘要应该包含用户名和角色")
    }

    @Test
    fun testGetCurrentUserPermissionSummaryForNotLoggedIn() {
        // 测试获取未登录用户权限摘要
        whenever(authenticationService.getCurrentUser()).thenReturn(null)
        
        val summary = materialRecordManager.getCurrentUserPermissionSummary()
        
        assertEquals("未登录用户", summary, "应该显示未登录状态")
    }

    @Test
    fun testHasBasicMaterialRecordPermission() {
        // 测试基本物料记录权限检查
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
            .thenReturn(true)
        
        val hasPermission = materialRecordManager.hasBasicMaterialRecordPermission()
        
        assertTrue(hasPermission, "应该有基本物料记录权限")
    }

    @Test
    fun testApplyPermissionControlWithAllowedResult() = runBlocking {
        // 测试应用权限控制 - 允许的结果
        whenever(authenticationService.isLoggedIn()).thenReturn(true)
        whenever(authenticationService.getCurrentUser()).thenReturn(adminUser)
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
            .thenReturn(true)
        whenever(unifiedDataManager.getRecord("NEW001")).thenReturn(null)
        
        var resultReceived: MaterialRecordManager.MaterialModifyResult? = null
        
        materialRecordManager.applyPermissionControl("NEW001") { result ->
            resultReceived = result
        }
        
        assertNotNull(resultReceived, "应该收到权限控制结果")
        assertTrue(resultReceived!!.allowed, "权限应该被允许")
    }

    @Test
    fun testApplyPermissionControlWithDeniedResult() = runBlocking {
        // 测试应用权限控制 - 拒绝的结果
        whenever(authenticationService.isLoggedIn()).thenReturn(true)
        whenever(authenticationService.getCurrentUser()).thenReturn(regularUser)
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
            .thenReturn(true)
        whenever(unifiedDataManager.getRecord("EXISTING001")).thenReturn(existingRecord)
        whenever(authenticationService.canModifyExistingRecord("EXISTING001")).thenReturn(false)
        
        var resultReceived: MaterialRecordManager.MaterialModifyResult? = null
        
        materialRecordManager.applyPermissionControl("EXISTING001") { result ->
            resultReceived = result
        }
        
        assertNotNull(resultReceived, "应该收到权限控制结果")
        assertFalse(resultReceived!!.allowed, "权限应该被拒绝")
        assertTrue(resultReceived!!.isReadOnlyMode, "应该是只读模式")
    }
}