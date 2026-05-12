/**
 * 记录管理页面权限控制
 * 实现记录查看、修改、删除操作的权限验证
 */

class RecordsPermissionController {
    constructor() {
        this.currentUser = null;
        this.permissions = new Set();
        this.isAdmin = false;
        this.initialized = false;
        
        console.log('记录权限控制器初始化');
    }
    
    /**
     * 初始化权限控制器
     */
    async initialize() {
        try {
            await this.loadUserPermissions();
            this.setupPermissionChecks();
            this.initialized = true;
            console.log('记录权限控制器初始化完成');
        } catch (error) {
            console.error('记录权限控制器初始化失败:', error);
        }
    }
    
    /**
     * 加载用户权限信息
     */
    async loadUserPermissions() {
        try {
            const response = await fetch('/api/user/current-permissions');
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.currentUser = data.user;
                    this.permissions = new Set(data.permissions);
                    this.isAdmin = data.user && data.user.role === 'admin';
                    
                    console.log('用户权限加载成功:', {
                        user: this.currentUser?.synology_username,
                        role: this.currentUser?.role,
                        permissions: Array.from(this.permissions)
                    });
                }
            }
        } catch (error) {
            console.error('加载用户权限异常:', error);
        }
    }
    
    /**
     * 检查用户是否具有指定权限
     */
    hasPermission(permission) {
        return this.permissions.has(permission);
    }
    
    /**
     * 检查用户是否为管理员
     */
    isUserAdmin() {
        return this.isAdmin;
    }
    
    /**
     * 设置权限检查
     */
    setupPermissionChecks() {
        // 隐藏无权限的按钮
        this.hideUnauthorizedElements();
        
        // 为操作按钮添加权限检查
        this.addPermissionChecksToButtons();
        
        console.log('权限检查设置完成');
    }
    
    /**
     * 隐藏无权限的元素
     */
    hideUnauthorizedElements() {
        // 检查查看权限
        if (!this.hasPermission('web:view_records')) {
            this.hideElement(document.getElementById('searchForm'));
            this.showPermissionMessage('您没有查看记录的权限');
            return;
        }
        
        // 检查修改权限
        if (!this.hasPermission('web:modify_records')) {
            const syncBtn = document.getElementById('syncBtn');
            const backupBtn = document.getElementById('backupBtn');
            
            if (syncBtn) this.disableElement(syncBtn, '需要修改权限');
            if (backupBtn) this.disableElement(backupBtn, '需要修改权限');
        }
        
        // 检查导出权限
        if (!this.hasPermission('web:view_records')) {
            const exportBtn = document.getElementById('exportBtn');
            if (exportBtn) this.disableElement(exportBtn, '需要查看权限');
        }
    }
    
    /**
     * 为按钮添加权限检查
     */
    addPermissionChecksToButtons() {
        // 重写删除函数以添加权限检查
        window.originalDeleteRecord = window.deleteRecord;
        window.deleteRecord = (productSerial, recordIndex) => {
            if (!this.checkDeletePermission()) {
                return;
            }
            window.originalDeleteRecord(productSerial, recordIndex);
        };
        
        // 重写导出函数以添加权限检查
        window.originalExportRecords = window.exportRecords;
        window.exportRecords = () => {
            if (!this.checkExportPermission()) {
                return;
            }
            window.originalExportRecords();
        };
        
        // 重写同步函数以添加权限检查
        window.originalSyncDataToH2 = window.syncDataToH2;
        window.syncDataToH2 = () => {
            if (!this.checkModifyPermission('同步数据到H2')) {
                return;
            }
            window.originalSyncDataToH2();
        };
        
        // 重写备份函数以添加权限检查
        window.originalBackupAndClearCSV = window.backupAndClearCSV;
        window.backupAndClearCSV = () => {
            if (!this.checkModifyPermission('备份清空CSV')) {
                return;
            }
            window.originalBackupAndClearCSV();
        };
    }
    
    /**
     * 检查删除权限
     */
    checkDeletePermission() {
        if (!this.hasPermission('web:delete_records')) {
            this.showPermissionDeniedDialog('删除记录', 'web:delete_records', 
                '删除记录需要管理员权限。普通用户无法删除已存在的记录。');
            return false;
        }
        return true;
    }
    
    /**
     * 检查导出权限
     */
    checkExportPermission() {
        if (!this.hasPermission('web:view_records')) {
            this.showPermissionDeniedDialog('导出记录', 'web:view_records', 
                '导出记录需要查看记录权限。');
            return false;
        }
        return true;
    }
    
    /**
     * 检查修改权限
     */
    checkModifyPermission(actionName) {
        if (!this.hasPermission('web:modify_records')) {
            this.showPermissionDeniedDialog(actionName, 'web:modify_records', 
                '此操作需要修改记录权限。普通用户无法执行数据修改操作。');
            return false;
        }
        return true;
    }
    
    /**
     * 检查记录修改权限（针对特定产品序列号）
     */
    async checkRecordModifyPermission(productSerial) {
        try {
            const response = await fetch(`/api/records/check-modify-permission/${encodeURIComponent(productSerial)}`);
            const result = await response.json();
            
            if (result.success) {
                if (!result.can_modify) {
                    this.showPermissionDeniedDialog('修改记录', 'web:modify_records', 
                        result.message || '您没有修改此记录的权限');
                    return false;
                }
                return true;
            } else {
                console.error('权限检查失败:', result.message);
                return false;
            }
        } catch (error) {
            console.error('权限检查异常:', error);
            return false;
        }
    }
    
    /**
     * 显示权限拒绝对话框
     */
    showPermissionDeniedDialog(actionName, requiredPermission, detailMessage) {
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.6); z-index: 1001; display: flex;
            align-items: center; justify-content: center; padding: 2rem;
        `;
        
        modal.innerHTML = `
            <div style="background: white; border-radius: 12px; max-width: 500px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.3);">
                <div style="padding: 2rem; border-bottom: 1px solid #e9ecef; text-align: center;">
                    <div style="font-size: 3rem; color: #ffc107; margin-bottom: 1rem;">🔒</div>
                    <h3 style="margin: 0 0 1rem 0; color: #dc3545;">权限不足</h3>
                    <p style="margin: 0; color: #6c757d; line-height: 1.5;">
                        您没有执行"<strong>${actionName}</strong>"操作的权限。
                    </p>
                </div>
                
                <div style="padding: 2rem;">
                    <div style="background: #f8f9fa; border-left: 4px solid #ffc107; padding: 1rem; margin-bottom: 1rem;">
                        <div style="font-weight: bold; color: #856404; margin-bottom: 0.5rem;">详细说明：</div>
                        <div style="color: #856404; font-size: 0.9em;">${detailMessage}</div>
                    </div>
                    
                    <div style="background: #e9ecef; padding: 1rem; border-radius: 6px; font-size: 0.9em;">
                        <div><strong>当前用户：</strong> ${this.currentUser?.synology_username || '未知'}</div>
                        <div><strong>用户角色：</strong> ${this.currentUser?.role || '未知'}</div>
                        <div><strong>需要权限：</strong> ${requiredPermission}</div>
                    </div>
                    
                    <div style="margin-top: 1rem; padding: 1rem; background: #d1ecf1; border-radius: 6px; color: #0c5460; font-size: 0.9em;">
                        💡 <strong>解决方法：</strong><br>
                        请联系系统管理员为您分配相应的权限，或使用管理员账户登录。
                    </div>
                </div>
                
                <div style="padding: 1.5rem 2rem; border-top: 1px solid #e9ecef; display: flex; justify-content: center; background: #f8f9fa; border-radius: 0 0 12px 12px;">
                    <button onclick="this.closest('.permission-denied-modal').remove()" class="btn btn-primary" style="padding: 0.5rem 2rem;">
                        我知道了
                    </button>
                </div>
            </div>
        `;
        
        modal.className = 'permission-denied-modal';
        document.body.appendChild(modal);
        
        // 点击背景关闭
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.remove();
            }
        });
        
        // 记录权限拒绝日志
        console.warn(`权限拒绝: ${actionName} - 用户: ${this.currentUser?.synology_username}, 需要权限: ${requiredPermission}`);
    }
    
    /**
     * 隐藏元素
     */
    hideElement(element) {
        if (element) {
            element.style.display = 'none';
        }
    }
    
    /**
     * 禁用元素
     */
    disableElement(element, reason) {
        if (element) {
            element.disabled = true;
            element.style.opacity = '0.5';
            element.style.cursor = 'not-allowed';
            element.title = reason;
            
            // 添加点击事件显示权限提示
            element.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.showPermissionDeniedDialog('此操作', 'required_permission', reason);
            });
        }
    }
    
    /**
     * 显示权限消息
     */
    showPermissionMessage(message) {
        const container = document.getElementById('recordsContainer');
        if (container) {
            container.innerHTML = `
                <div style="text-align: center; padding: 3rem; color: #6c757d;">
                    <div style="font-size: 4rem; margin-bottom: 1rem;">🔒</div>
                    <h3 style="color: #dc3545; margin-bottom: 1rem;">权限不足</h3>
                    <p style="font-size: 1.1em; margin-bottom: 2rem;">${message}</p>
                    <div style="background: #f8f9fa; padding: 1.5rem; border-radius: 8px; display: inline-block;">
                        <div><strong>当前用户：</strong> ${this.currentUser?.synology_username || '未登录'}</div>
                        <div><strong>用户角色：</strong> ${this.currentUser?.role || '无'}</div>
                    </div>
                </div>
            `;
        }
    }
    
    /**
     * 为记录卡片添加权限控制
     */
    applyRecordPermissions(recordElements) {
        recordElements.forEach((element, index) => {
            const deleteButton = element.querySelector('[onclick*="deleteRecord"]');
            
            if (deleteButton && !this.hasPermission('web:delete_records')) {
                // 替换删除按钮为权限提示
                deleteButton.outerHTML = `
                    <span style="color: #6c757d; font-size: 0.8em; padding: 0.3rem 0.8rem; cursor: not-allowed;" 
                          title="权限不足：需要删除记录权限"
                          onclick="recordsPermissionController.showPermissionDeniedDialog('删除记录', 'web:delete_records', '删除记录需要管理员权限')">
                        🔒 删除
                    </span>
                `;
            }
        });
    }
    
    /**
     * 刷新权限状态
     */
    async refreshPermissions() {
        await this.loadUserPermissions();
        this.setupPermissionChecks();
        console.log('记录权限状态已刷新');
    }
}

// 创建全局实例
const recordsPermissionController = new RecordsPermissionController();

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    recordsPermissionController.initialize();
});

// 导出到全局作用域
window.RecordsPermissionController = RecordsPermissionController;
window.recordsPermissionController = recordsPermissionController;

// 重写 displayRecords 函数以添加权限控制
if (typeof window.originalDisplayRecords === 'undefined') {
    window.originalDisplayRecords = window.displayRecords;
    
    window.displayRecords = function(records) {
        // 调用原始函数
        window.originalDisplayRecords(records);
        
        // 应用权限控制
        if (recordsPermissionController.initialized) {
            const recordElements = document.querySelectorAll('#recordsContainer > div > div');
            recordsPermissionController.applyRecordPermissions(recordElements);
        }
    };
}

console.log('记录权限控制组件加载完成');