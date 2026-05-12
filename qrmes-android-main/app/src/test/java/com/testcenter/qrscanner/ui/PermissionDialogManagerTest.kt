package com.testcenter.qrscanner.ui

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.testcenter.qrscanner.auth.AuthenticationService
import com.testcenter.qrscanner.auth.LocalUserManager
import com.testcenter.qrscanner.auth.PermissionService
import com.testcenter.qrscanner.data.LocalUser
import com.testcenter.qrscanner.data.UserRole
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.Mock
import org.mockito.MockitoAnnotations
import org.mockito.kotlin.whenever
import java.time.LocalDateTime

/**
 * 权限对话框管理器测试
 */
@RunWith(AndroidJUnit4::class)
class PermissionDialogManagerTest {

    private lateinit var context: Context
    private lateinit var permissionDialogManager: PermissionDialogManager
    
    @Mock
    private lateinit var authenticationService: AuthenticationService

    @Before
    fun setUp() {
        MockitoAnnotations.openMocks(this)
        context = ApplicationProvider.getApplicationContext()
        permissionDialogManager = PermissionDialogManager(context)
    }

    @Test
    fun testPermissionDialogManagerCreation() {
        // 测试权限对话框管理器是否能正常创建
        assert(permissionDialogManager != null)
    }

    @Test
    fun testCreatePermissionStatusView() {
        // 测试创建权限状态视图
        val statusView = permissionDialogManager.createPermissionStatusView(
            userRole = "普通用户",
            canModify = false,
            productSerial = "TEST001"
        )
        
        assert(statusView != null)
    }

    @Test
    fun testCreatePermissionStatusViewForAdmin() {
        // 测试为管理员创建权限状态视图
        val statusView = permissionDialogManager.createPermissionStatusView(
            userRole = "管理员",
            canModify = true,
            productSerial = "TEST002"
        )
        
        assert(statusView != null)
    }

    @Test
    fun testShowUserPermissionStatusDialog() {
        // 模拟用户数据
        val mockUser = LocalUser(
            id = "test-user-id",
            synologyUsername = "testuser",
            displayName = "测试用户",
            role = UserRole.USER,
            createdAt = LocalDateTime.now(),
            updatedAt = LocalDateTime.now(),
            lastLoginAt = LocalDateTime.now()
        )

        whenever(authenticationService.getCurrentUser()).thenReturn(mockUser)
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MATERIAL_RECORD))
            .thenReturn(true)
        whenever(authenticationService.hasPermission(PermissionService.Permission.MOBILE_MODIFY_EXISTING))
            .thenReturn(false)

        // 测试显示用户权限状态对话框
        val dialog = permissionDialogManager.showUserPermissionStatusDialog(authenticationService)
        assert(dialog != null)
        assert(dialog.isShowing)
        
        dialog.dismiss()
    }

    @Test
    fun testShowPermissionDeniedDialog() {
        // 测试显示权限拒绝对话框
        var retryCallbackCalled = false
        var cancelCallbackCalled = false

        val dialog = permissionDialogManager.showPermissionDeniedDialog(
            title = "测试权限不足",
            message = "这是一个测试消息",
            onRetry = { retryCallbackCalled = true },
            onCancel = { cancelCallbackCalled = true }
        )

        assert(dialog != null)
        assert(dialog.isShowing)
        
        dialog.dismiss()
    }

    @Test
    fun testShowMaterialModificationDeniedDialog() {
        // 测试显示物料修改权限拒绝对话框
        var contactAdminCalled = false

        val dialog = permissionDialogManager.showMaterialModificationDeniedDialog(
            productSerial = "TEST003",
            onContactAdmin = { contactAdminCalled = true }
        )

        assert(dialog != null)
        assert(dialog.isShowing)
        
        dialog.dismiss()
    }

    @Test
    fun testShowReadOnlyModeDialog() {
        // 测试显示只读模式对话框
        var continueCalled = false

        val dialog = permissionDialogManager.showReadOnlyModeDialog(
            productSerial = "TEST004",
            userRole = "普通用户",
            onContinue = { continueCalled = true }
        )

        assert(dialog != null)
        assert(dialog.isShowing)
        
        dialog.dismiss()
    }

    @Test
    fun testShowOperationBlockedDialog() {
        // 测试显示操作被阻止对话框
        var retryAsAdminCalled = false

        val dialog = permissionDialogManager.showOperationBlockedDialog(
            operation = "修改物料信息",
            reason = "普通用户权限不足",
            onRetryAsAdmin = { retryAsAdminCalled = true }
        )

        assert(dialog != null)
        assert(dialog.isShowing)
        
        dialog.dismiss()
    }

    @Test
    fun testShowSessionExpiredDialog() {
        // 测试显示会话过期对话框
        var reLoginCalled = false

        val dialog = permissionDialogManager.showSessionExpiredDialog(
            onReLogin = { reLoginCalled = true }
        )

        assert(dialog != null)
        assert(dialog.isShowing)
        
        dialog.dismiss()
    }

    @Test
    fun testShowPermissionValidationFailedDialog() {
        // 测试显示权限验证失败对话框
        var retryCalled = false

        val dialog = permissionDialogManager.showPermissionValidationFailedDialog(
            error = "网络连接失败",
            onRetry = { retryCalled = true }
        )

        assert(dialog != null)
        assert(dialog.isShowing)
        
        dialog.dismiss()
    }
}