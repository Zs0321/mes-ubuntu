/**
 * 权限指令处理器
 * 提供声明式的权限控制指令
 */

class PermissionDirectives {
    constructor(permissionController) {
        this.permissionController = permissionController;
        this.directiveHandlers = new Map();
        this.setupDirectiveHandlers();
    }
    
    /**
     * 设置指令处理器
     */
    setupDirectiveHandlers() {
        // v-permission 指令：检查特定权限
        this.directiveHandlers.set('v-permission', (element, value) => {
            if (!this.permissionController.hasPermission(value)) {
                this.hideElement(element);
                return false;
            }
            return true;
        });
        
        // v-admin 指令：仅管理员可见
        this.directiveHandlers.set('v-admin', (element, value) => {
            if (!this.permissionController.isUserAdmin()) {
                this.hideElement(element);
                return false;
            }
            return true;
        });
        
        // v-user 指令：仅普通用户可见
        this.directiveHandlers.set('v-user', (element, value) => {
            if (this.permissionController.isUserAdmin()) {
                this.hideElement(element);
                return false;
            }
            return true;
        });
        
        // v-role 指令：检查特定角色
        this.directiveHandlers.set('v-role', (element, value) => {
            const userRole = this.permissionController.getCurrentUser()?.role;
            if (userRole !== value) {
                this.hideElement(element);
                return false;
            }
            return true;
        });
        
        // v-permission-any 指令：检查多个权限中的任意一个
        this.directiveHandlers.set('v-permission-any', (element, value) => {
            const permissions = value.split(',').map(p => p.trim());
            const hasAnyPermission = permissions.some(permission => 
                this.permissionController.hasPermission(permission)
            );
            
            if (!hasAnyPermission) {
                this.hideElement(element);
                return false;
            }
            return true;
        });
        
        // v-permission-all 指令：检查多个权限全部拥有
        this.directiveHandlers.set('v-permission-all', (element, value) => {
            const permissions = value.split(',').map(p => p.trim());
            const hasAllPermissions = permissions.every(permission => 
                this.permissionController.hasPermission(permission)
            );
            
            if (!hasAllPermissions) {
                this.hideElement(element);
                return false;
            }
            return true;
        });
        
        // v-permission-disable 指令：权限不足时禁用而非隐藏
        this.directiveHandlers.set('v-permission-disable', (element, value) => {
            if (!this.permissionController.hasPermission(value)) {
                this.disableElement(element);
                return false;
            }
            return true;
        });
        
        // v-permission-tooltip 指令：权限不足时显示提示
        this.directiveHandlers.set('v-permission-tooltip', (element, value) => {
            const [permission, message] = value.split('|').map(s => s.trim());
            
            if (!this.permissionController.hasPermission(permission)) {
                this.addPermissionTooltip(element, message || '权限不足');
                this.disableElement(element);
                return false;
            }
            return true;
        });
    }
    
    /**
     * 处理所有权限指令
     */
    processDirectives(container = document) {
        this.directiveHandlers.forEach((handler, directive) => {
            const elements = container.querySelectorAll(`[${directive}]`);
            elements.forEach(element => {
                const value = element.getAttribute(directive);
                try {
                    handler(element, value);
                } catch (error) {
                    console.error(`处理权限指令 ${directive} 失败:`, error);
                }
            });
        });
    }
    
    /**
     * 隐藏元素
     */
    hideElement(element) {
        const hideMethod = element.getAttribute('data-hide-method') || 'display';
        
        switch (hideMethod) {
            case 'visibility':
                element.style.visibility = 'hidden';
                break;
            case 'opacity':
                element.style.opacity = '0';
                element.style.pointerEvents = 'none';
                break;
            case 'remove':
                element.remove();
                return;
            case 'display':
            default:
                element.style.display = 'none';
                break;
        }
        
        element.setAttribute('data-permission-hidden', 'true');
    }
    
    /**
     * 禁用元素
     */
    disableElement(element) {
        if (element.tagName === 'BUTTON' || element.tagName === 'INPUT' || element.tagName === 'SELECT' || element.tagName === 'TEXTAREA') {
            element.disabled = true;
        }
        
        element.classList.add('permission-disabled');
        element.setAttribute('data-permission-disabled', 'true');
        
        // 阻止点击事件
        element.addEventListener('click', this.preventClick, true);
    }
    
    /**
     * 启用元素
     */
    enableElement(element) {
        if (element.tagName === 'BUTTON' || element.tagName === 'INPUT' || element.tagName === 'SELECT' || element.tagName === 'TEXTAREA') {
            element.disabled = false;
        }
        
        element.classList.remove('permission-disabled');
        element.removeAttribute('data-permission-disabled');
        
        // 移除点击事件阻止
        element.removeEventListener('click', this.preventClick, true);
    }
    
    /**
     * 阻止点击事件
     */
    preventClick(event) {
        event.preventDefault();
        event.stopPropagation();
        return false;
    }
    
    /**
     * 添加权限提示
     */
    addPermissionTooltip(element, message) {
        element.classList.add('permission-tooltip');
        element.setAttribute('data-permission-message', message);
        element.setAttribute('title', message);
    }
    
    /**
     * 移除权限提示
     */
    removePermissionTooltip(element) {
        element.classList.remove('permission-tooltip');
        element.removeAttribute('data-permission-message');
        element.removeAttribute('title');
    }
    
    /**
     * 刷新所有指令
     */
    refresh(container = document) {
        // 先恢复所有被权限控制的元素
        this.restoreElements(container);
        
        // 重新处理指令
        this.processDirectives(container);
    }
    
    /**
     * 恢复所有被权限控制的元素
     */
    restoreElements(container = document) {
        // 恢复隐藏的元素
        const hiddenElements = container.querySelectorAll('[data-permission-hidden="true"]');
        hiddenElements.forEach(element => {
            element.style.display = '';
            element.style.visibility = '';
            element.style.opacity = '';
            element.style.pointerEvents = '';
            element.removeAttribute('data-permission-hidden');
        });
        
        // 恢复禁用的元素
        const disabledElements = container.querySelectorAll('[data-permission-disabled="true"]');
        disabledElements.forEach(element => {
            this.enableElement(element);
            this.removePermissionTooltip(element);
        });
    }
}

/**
 * 权限守卫类
 * 用于路由和页面级别的权限控制
 */
class PermissionGuard {
    constructor(permissionController) {
        this.permissionController = permissionController;
        this.guards = new Map();
    }
    
    /**
     * 注册路由守卫
     */
    registerRouteGuard(path, permission, redirectTo = '/') {
        this.guards.set(path, { permission, redirectTo });
    }
    
    /**
     * 检查当前路由权限
     */
    checkCurrentRoute() {
        const currentPath = window.location.pathname;
        
        for (const [path, guard] of this.guards) {
            if (this.matchPath(currentPath, path)) {
                if (!this.permissionController.hasPermission(guard.permission)) {
                    this.handleUnauthorizedAccess(guard.redirectTo);
                    return false;
                }
            }
        }
        
        return true;
    }
    
    /**
     * 路径匹配
     */
    matchPath(currentPath, guardPath) {
        // 简单的路径匹配，支持通配符
        if (guardPath.includes('*')) {
            const pattern = guardPath.replace(/\*/g, '.*');
            return new RegExp(`^${pattern}$`).test(currentPath);
        }
        
        return currentPath === guardPath || currentPath.startsWith(guardPath + '/');
    }
    
    /**
     * 处理未授权访问
     */
    handleUnauthorizedAccess(redirectTo) {
        console.warn('权限不足，重定向到:', redirectTo);
        
        // 显示权限不足消息
        this.permissionController.showPermissionDeniedMessage('访问此页面');
        
        // 延迟重定向，让用户看到提示
        setTimeout(() => {
            window.location.href = redirectTo;
        }, 2000);
    }
    
    /**
     * 检查页面操作权限
     */
    checkPageAction(actionName, permission) {
        if (!this.permissionController.hasPermission(permission)) {
            this.permissionController.showPermissionDeniedMessage(actionName);
            return false;
        }
        return true;
    }
}

/**
 * 权限表单验证器
 */
class PermissionFormValidator {
    constructor(permissionController) {
        this.permissionController = permissionController;
    }
    
    /**
     * 验证表单提交权限
     */
    validateFormSubmission(form, permission, actionName = '提交表单') {
        if (!this.permissionController.hasPermission(permission)) {
            this.permissionController.showPermissionDeniedMessage(actionName);
            return false;
        }
        return true;
    }
    
    /**
     * 为表单添加权限验证
     */
    addFormValidation(formSelector, permission, actionName) {
        const forms = document.querySelectorAll(formSelector);
        
        forms.forEach(form => {
            form.addEventListener('submit', (event) => {
                if (!this.validateFormSubmission(form, permission, actionName)) {
                    event.preventDefault();
                    event.stopPropagation();
                    return false;
                }
            });
        });
    }
    
    /**
     * 为表单字段添加权限控制
     */
    addFieldPermissionControl(fieldSelector, permission) {
        const fields = document.querySelectorAll(fieldSelector);
        
        fields.forEach(field => {
            if (!this.permissionController.hasPermission(permission)) {
                field.disabled = true;
                field.classList.add('permission-disabled');
                field.setAttribute('title', '权限不足，无法编辑此字段');
            }
        });
    }
}

// 导出类
window.PermissionDirectives = PermissionDirectives;
window.PermissionGuard = PermissionGuard;
window.PermissionFormValidator = PermissionFormValidator;

console.log('权限指令处理器加载完成');