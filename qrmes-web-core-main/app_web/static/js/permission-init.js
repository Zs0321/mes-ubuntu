/**
 * 权限控制初始化脚本
 * 在页面加载完成后自动初始化权限控制系统
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('开始初始化权限控制系统');
    
    // 等待权限控制器加载完成
    if (typeof permissionController !== 'undefined') {
        initializePermissionSystem();
    } else {
        // 如果权限控制器还未加载，等待一段时间后重试
        setTimeout(function() {
            if (typeof permissionController !== 'undefined') {
                initializePermissionSystem();
            } else {
                console.warn('权限控制器加载失败，权限控制功能可能不可用');
            }
        }, 1000);
    }
});

/**
 * 初始化权限控制系统
 */
async function initializePermissionSystem() {
    try {
        // 初始化权限控制器
        await permissionController.initialize();
        
        // 创建权限指令处理器
        const permissionDirectives = new PermissionDirectives(permissionController);
        
        // 创建权限守卫
        const permissionGuard = new PermissionGuard(permissionController);
        
        // 创建表单验证器
        const formValidator = new PermissionFormValidator(permissionController);
        
        // 注册路由守卫
        registerRouteGuards(permissionGuard);
        
        // 设置表单权限验证
        setupFormPermissions(formValidator);
        
        // 设置按钮权限检查
        setupButtonPermissions();
        
        // 处理权限指令
        permissionDirectives.processDirectives();
        
        // 检查当前路由权限
        permissionGuard.checkCurrentRoute();
        
        // 将实例暴露到全局作用域
        window.permissionDirectives = permissionDirectives;
        window.permissionGuard = permissionGuard;
        window.formValidator = formValidator;
        
        console.log('权限控制系统初始化完成');
        
        // 触发自定义事件，通知其他脚本权限系统已就绪
        const event = new CustomEvent('permissionSystemReady', {
            detail: {
                permissionController,
                permissionDirectives,
                permissionGuard,
                formValidator
            }
        });
        document.dispatchEvent(event);
        
    } catch (error) {
        console.error('权限控制系统初始化失败:', error);
    }
}

/**
 * 注册路由守卫
 */
function registerRouteGuards(permissionGuard) {
    // 系统设置页面需要管理员权限
    permissionGuard.registerRouteGuard('/settings', 'web:system_settings', '/');
    
    // 用户管理页面需要管理员权限
    permissionGuard.registerRouteGuard('/admin/users', 'web:manage_users', '/');
    
    // 日志查看需要相应权限
    permissionGuard.registerRouteGuard('/logs', 'web:view_logs', '/');

    // Finance quote page requires quote permission
    permissionGuard.registerRouteGuard('/finance-demo', 'web:finance_quote', '/');
}

/**
 * 设置表单权限验证
 */
function setupFormPermissions(formValidator) {
    // 项目管理表单
    formValidator.addFormValidation(
        '#addProjectForm', 
        'web:manage_projects', 
        '添加项目'
    );
    
    // 测试人员管理表单
    formValidator.addFormValidation(
        '#addTesterForm', 
        'web:manage_users', 
        '添加测试人员'
    );
    
    // 项目配置表单
    formValidator.addFormValidation(
        '#projectConfigForm', 
        'web:manage_process_config', 
        '保存项目配置'
    );
}

/**
 * 设置按钮权限检查
 */
function setupButtonPermissions() {
    // 删除记录按钮
    permissionController.addPermissionCheckToButton(
        '[onclick*="deleteRecord"]',
        permissionController.PERMISSIONS.WEB_DELETE_RECORDS,
        '删除记录'
    );
    
    // 修改记录按钮
    permissionController.addPermissionCheckToButton(
        '[onclick*="editRecord"]',
        permissionController.PERMISSIONS.WEB_MODIFY_RECORDS,
        '修改记录'
    );
    
    // 项目管理按钮
    permissionController.addPermissionCheckToButton(
        '[onclick*="deleteProject"]',
        permissionController.PERMISSIONS.WEB_MANAGE_PROJECTS,
        '删除项目'
    );
    
    // 系统设置按钮
    permissionController.addPermissionCheckToButton(
        '[href*="/settings"]',
        permissionController.PERMISSIONS.WEB_SYSTEM_SETTINGS,
        '访问系统设置'
    );
}

/**
 * 权限变更处理
 */
function handlePermissionChange() {
    if (window.permissionController) {
        // 刷新权限状态
        permissionController.refreshPermissions();
        
        // 重新处理权限指令
        if (window.permissionDirectives) {
            permissionDirectives.refresh();
        }
        
        console.log('权限状态已刷新');
    }
}

/**
 * 用户角色变更处理
 */
function handleRoleChange(newRole) {
    console.log('用户角色变更:', newRole);
    
    // 刷新权限系统
    handlePermissionChange();
    
    // 可能需要重新加载页面以确保所有权限控制生效
    if (confirm('用户角色已变更，是否重新加载页面以应用新权限？')) {
        location.reload();
    }
}

/**
 * 权限错误处理
 */
function handlePermissionError(error) {
    console.error('权限错误:', error);
    
    // 显示用户友好的错误消息
    if (window.permissionController) {
        permissionController.showPermissionDeniedMessage('执行此操作');
    } else {
        alert('权限不足，无法执行此操作');
    }
}

/**
 * 检查页面特定权限
 */
function checkPagePermissions() {
    const currentPath = window.location.pathname;
    
    // 根据当前页面路径检查特定权限
    switch (true) {
        case currentPath.includes('/projects'):
            return permissionController.hasPermission(permissionController.PERMISSIONS.WEB_MANAGE_PROJECTS);
            
        case currentPath.includes('/records'):
            return permissionController.hasPermission(permissionController.PERMISSIONS.WEB_VIEW_RECORDS);
            
        case currentPath.includes('/settings'):
            return permissionController.hasPermission(permissionController.PERMISSIONS.WEB_SYSTEM_SETTINGS);
            
        case currentPath.includes('/logs'):
            return permissionController.hasPermission(permissionController.PERMISSIONS.WEB_VIEW_LOGS);
            
        default:
            return true; // 默认允许访问
    }
}

/**
 * 动态权限检查装饰器
 */
function withPermissionCheck(permission, actionName) {
    return function(originalFunction) {
        return function(...args) {
            if (window.permissionController && 
                !window.permissionController.checkPermissionForAction(permission, actionName)) {
                return false;
            }
            return originalFunction.apply(this, args);
        };
    };
}

// 导出到全局作用域
window.handlePermissionChange = handlePermissionChange;
window.handleRoleChange = handleRoleChange;
window.handlePermissionError = handlePermissionError;
window.checkPagePermissions = checkPagePermissions;
window.withPermissionCheck = withPermissionCheck;

console.log('权限控制初始化脚本加载完成');