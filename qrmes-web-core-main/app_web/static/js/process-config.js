/**
 * 工序配置管理前端脚本
 * 支持拖拽排序、增删改查、版本管理等功能
 */

class ProcessConfigManager {
    constructor() {
        this.currentProject = null;
        this.projectConfig = null;
        this.productTypes = [];
        this.sortables = {};
        this.init();
    }

    init() {
        this.loadProjects();
        this.initEventListeners();
    }

    initEventListeners() {
        // 监听文件选择
        document.getElementById('importFile').addEventListener('change', this.handleFileSelect.bind(this));
        
        // 监听折叠事件以更新图标
        document.addEventListener('shown.bs.collapse', (event) => {
            const collapseId = event.target.id;
            const icon = document.getElementById(`icon-${collapseId}`);
            if (icon) {
                icon.classList.remove('collapsed');
            }
        });
        
        document.addEventListener('hidden.bs.collapse', (event) => {
            const collapseId = event.target.id;
            const icon = document.getElementById(`icon-${collapseId}`);
            if (icon) {
                icon.classList.add('collapsed');
            }
        });
    }

    async loadProjects() {
        try {
            const response = await fetch('/api/process-config/projects');
            const result = await response.json();

            if (result.success) {
                this.renderProjectList(result.data);
            } else {
                this.showError('加载项目列表失败: ' + result.error);
            }
        } catch (error) {
            this.showError('加载项目列表失败: ' + error.message);
        }
    }

    renderProjectList(projects) {
        const container = document.getElementById('projectList');
        
        if (projects.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-folder-open"></i>
                    <p>暂无项目</p>
                </div>
            `;
            return;
        }

        const html = projects.map(project => `
            <div class="project-item" onclick="selectProject('${project.name}')">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <div class="fw-bold">${project.displayName}</div>
                        <small class="text-muted">${project.description || '无描述'}</small>
                    </div>
                    <div class="text-end">
                        <span class="badge bg-primary version-badge">v${project.version}</span>
                        <div class="small text-muted">${project.processCount} 个工序</div>
                    </div>
                </div>
            </div>
        `).join('');

        container.innerHTML = html;
    }

    async selectProject(projectName) {
        // 更新选中状态
        document.querySelectorAll('.project-item').forEach(item => {
            item.classList.remove('active');
        });
        event.target.closest('.project-item').classList.add('active');

        this.currentProject = projectName;
        
        // 更新标题
        document.getElementById('currentProjectTitle').textContent = `${projectName} - 工序配置`;
        document.getElementById('currentProjectInfo').textContent = `当前项目: ${projectName}`;
        
        // 启用工具栏按钮
        ['exportBtn', 'importBtn', 'versionBtn'].forEach(id => {
            document.getElementById(id).disabled = false;
        });

        // 加载项目配置
        await this.loadProjectConfig();
    }

    async loadProjectConfig() {
        if (!this.currentProject) return;

        try {
            const response = await fetch(`/api/process-config/projects/${this.currentProject}/config`);
            const result = await response.json();

            if (result.success) {
                this.projectConfig = result.data;
                this.productTypes = result.data.productTypes || [];
                
                // 检查是否需要迁移
                this.checkMigrationNeeded();
                
                // 渲染产品类型和工序列表
                this.renderProductTypeList();
            } else {
                this.showError('加载项目配置失败: ' + result.error);
            }
        } catch (error) {
            this.showError('加载项目配置失败: ' + error.message);
        }
    }
    
    checkMigrationNeeded() {
        const migrationAlert = document.getElementById('migrationAlert');
        
        // 检查是否是旧版本配置（没有schemaVersion或版本为1.0）
        if (!this.projectConfig.schemaVersion || this.projectConfig.schemaVersion === '1.0') {
            migrationAlert.style.display = 'block';
        } else {
            migrationAlert.style.display = 'none';
        }
    }

    renderProductTypeList() {
        const container = document.getElementById('productTypeListContainer');
        
        if (this.productTypes.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-box-open"></i>
                    <h5>暂无产品类型</h5>
                    <p>请先在项目配置中添加产品类型，然后才能配置工序</p>
                </div>
            `;
            return;
        }

        const html = this.productTypes.map((productType, index) => 
            this.renderProductTypeCard(productType, index)
        ).join('');

        container.innerHTML = html;
        
        // 初始化所有产品类型的排序功能
        this.productTypes.forEach((productType, index) => {
            this.initSortableForProductType(productType.typeName, index);
        });
    }
    
    renderProductTypeCard(productType, index) {
        const processes = productType.processSteps || [];
        const collapseId = `collapse-${index}`;
        
        return `
            <div class="product-type-card">
                <div class="product-type-header" data-bs-toggle="collapse" data-bs-target="#${collapseId}">
                    <div class="product-type-title">
                        <div class="product-type-name">
                            <i class="fas fa-chevron-down collapse-icon" id="icon-${collapseId}"></i>
                            <strong>${productType.typeName}</strong>
                            <span class="badge bg-secondary">${processes.length} 个工序</span>
                        </div>
                        <div class="product-type-actions" onclick="event.stopPropagation()">
                            <button class="btn btn-outline-primary btn-sm" onclick="showAddProcessModal('${productType.typeName}')">
                                <i class="fas fa-plus me-1"></i>
                                添加工序
                            </button>
                        </div>
                    </div>
                </div>
                <div class="collapse show" id="${collapseId}">
                    <div class="product-type-body">
                        <div class="materials-section">
                            <strong class="text-muted">物料列表:</strong>
                            <div class="materials-list">
                                ${productType.materials.map(m => 
                                    `<span class="badge bg-light text-dark">${m.name} (${m.partNumber})</span>`
                                ).join('')}
                            </div>
                        </div>
                        <div class="process-section">
                            <div class="process-section-header">
                                <strong class="text-muted">工序配置:</strong>
                            </div>
                            ${this.renderProcessListForProductType(productType.typeName, processes, index)}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    renderProcessListForProductType(productTypeName, processes, productTypeIndex) {
        if (processes.length === 0) {
            return `
                <div class="empty-processes">
                    <i class="fas fa-cogs fa-2x mb-2"></i>
                    <p class="mb-0">暂无工序，点击"添加工序"开始配置</p>
                </div>
            `;
        }
        
        return `
            <div id="processList-${productTypeIndex}" class="process-list" data-product-type="${productTypeName}">
                ${processes.map(process => this.renderProcessItem(process)).join('')}
            </div>
        `;
    }

    renderProcessItem(process) {
        return `
            <div class="process-item" data-id="${process.id}">
                <div class="process-header">
                    <div class="process-title">
                        <i class="fas fa-grip-vertical drag-handle"></i>
                        <span class="process-order">${process.order}</span>
                        <span>${process.name}</span>
                        ${process.required ? '<span class="badge bg-danger ms-2">必需</span>' : ''}
                        ${process.photoRequired ? '<span class="badge bg-info ms-1">拍照</span>' : ''}
                    </div>
                    <div class="process-actions">
                        <button class="btn btn-outline-primary btn-sm" onclick="editProcess('${process.id}')">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-outline-danger btn-sm" onclick="deleteProcess('${process.id}')">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
                <div class="process-details">
                    <div class="detail-row">
                        <span class="detail-label">描述:</span>
                        <span>${process.description || '无描述'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">预计耗时:</span>
                        <span>${this.formatDuration(process.estimatedDuration)}</span>
                    </div>
                </div>
            </div>
        `;
    }

    formatDuration(seconds) {
        if (seconds < 60) {
            return `${seconds} 秒`;
        } else if (seconds < 3600) {
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = seconds % 60;
            return remainingSeconds > 0 ? `${minutes} 分 ${remainingSeconds} 秒` : `${minutes} 分`;
        } else {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            return minutes > 0 ? `${hours} 小时 ${minutes} 分` : `${hours} 小时`;
        }
    }

    initSortableForProductType(productTypeName, productTypeIndex) {
        const processList = document.getElementById(`processList-${productTypeIndex}`);
        if (!processList) return;

        this.sortables[productTypeName] = Sortable.create(processList, {
            handle: '.drag-handle',
            animation: 150,
            ghostClass: 'sortable-ghost',
            chosenClass: 'sortable-chosen',
            onEnd: (evt) => {
                this.handleReorder(productTypeName, evt);
            }
        });
    }

    async handleReorder(productTypeName, evt) {
        const processList = evt.from;
        const processItems = processList.querySelectorAll('.process-item');
        const processOrders = Array.from(processItems).map((item, index) => ({
            id: item.dataset.id,
            order: index + 1
        }));

        try {
            const response = await fetch(`/api/process-config/projects/${this.currentProject}/product-types/${encodeURIComponent(productTypeName)}/processes/reorder`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ processOrders })
            });

            const result = await response.json();

            if (result.success) {
                this.showSuccess('工序排序更新成功');
                await this.loadProjectConfig();
            } else {
                this.showError('工序排序更新失败: ' + result.error);
                await this.loadProjectConfig();
            }
        } catch (error) {
            this.showError('工序排序更新失败: ' + error.message);
            await this.loadProjectConfig();
        }
    }

    showAddProcessModal(productTypeName = null) {
        document.getElementById('processModalTitle').textContent = '添加工序';
        document.getElementById('processForm').reset();
        document.getElementById('processId').value = '';
        document.getElementById('processProductType').value = '';
        
        // 填充产品类型选择器
        this.populateProductTypeSelect();
        
        // 如果指定了产品类型，预选择它
        if (productTypeName) {
            document.getElementById('productTypeSelect').value = productTypeName;
            document.getElementById('productTypeSelect').disabled = false;
            
            // 计算该产品类型的工序数量，设置默认顺序
            const productType = this.productTypes.find(pt => pt.typeName === productTypeName);
            const processCount = productType ? (productType.processSteps || []).length : 0;
            document.getElementById('processOrder').value = processCount + 1;
        } else {
            document.getElementById('productTypeSelect').disabled = false;
            document.getElementById('processOrder').value = 1;
        }
        
        new bootstrap.Modal(document.getElementById('processModal')).show();
    }
    
    populateProductTypeSelect() {
        const select = document.getElementById('productTypeSelect');
        select.innerHTML = '<option value="">请选择产品类型</option>';
        
        this.productTypes.forEach(productType => {
            const option = document.createElement('option');
            option.value = productType.typeName;
            option.textContent = productType.typeName;
            select.appendChild(option);
        });
    }

    async editProcess(processId, productTypeName) {
        // 查找工序
        let process = null;
        for (const productType of this.productTypes) {
            const found = (productType.processSteps || []).find(p => p.id === processId);
            if (found) {
                process = found;
                productTypeName = productType.typeName;
                break;
            }
        }
        
        if (!process) return;

        document.getElementById('processModalTitle').textContent = '编辑工序';
        document.getElementById('processId').value = process.id;
        document.getElementById('processProductType').value = productTypeName;
        document.getElementById('processName').value = process.name;
        document.getElementById('processDescription').value = process.description || '';
        document.getElementById('processOrder').value = process.order;
        document.getElementById('estimatedDuration').value = process.estimatedDuration;
        document.getElementById('processRequired').checked = process.required;
        document.getElementById('photoRequired').checked = process.photoRequired;
        
        // 填充并禁用产品类型选择器（编辑时不允许更改产品类型）
        this.populateProductTypeSelect();
        document.getElementById('productTypeSelect').value = productTypeName;
        document.getElementById('productTypeSelect').disabled = true;

        new bootstrap.Modal(document.getElementById('processModal')).show();
    }

    async saveProcess() {
        const form = document.getElementById('processForm');
        if (!form.checkValidity()) {
            form.reportValidity();
            return;
        }

        const processId = document.getElementById('processId').value;
        const productTypeName = processId ? 
            document.getElementById('processProductType').value : 
            document.getElementById('productTypeSelect').value;
            
        if (!productTypeName) {
            this.showError('请选择产品类型');
            return;
        }

        const processData = {
            name: document.getElementById('processName').value,
            description: document.getElementById('processDescription').value,
            order: parseInt(document.getElementById('processOrder').value),
            estimatedDuration: parseInt(document.getElementById('estimatedDuration').value),
            required: document.getElementById('processRequired').checked,
            photoRequired: document.getElementById('photoRequired').checked,
            productType: productTypeName
        };

        try {
            let response;
            if (processId) {
                // 更新工序
                response = await fetch(`/api/process-config/projects/${this.currentProject}/product-types/${encodeURIComponent(productTypeName)}/processes/${processId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(processData)
                });
            } else {
                // 添加工序
                response = await fetch(`/api/process-config/projects/${this.currentProject}/product-types/${encodeURIComponent(productTypeName)}/processes`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(processData)
                });
            }

            const result = await response.json();

            if (result.success) {
                this.showSuccess(processId ? '工序更新成功' : '工序添加成功');
                bootstrap.Modal.getInstance(document.getElementById('processModal')).hide();
                await this.loadProjectConfig();
            } else {
                this.showError((processId ? '工序更新失败' : '工序添加失败') + ': ' + result.error);
            }
        } catch (error) {
            this.showError((processId ? '工序更新失败' : '工序添加失败') + ': ' + error.message);
        }
    }

    async deleteProcess(processId) {
        // 查找工序及其所属产品类型
        let process = null;
        let productTypeName = null;
        
        for (const productType of this.productTypes) {
            const found = (productType.processSteps || []).find(p => p.id === processId);
            if (found) {
                process = found;
                productTypeName = productType.typeName;
                break;
            }
        }
        
        if (!process || !productTypeName) return;

        if (!confirm(`确定要删除工序"${process.name}"吗？此操作不可撤销。`)) {
            return;
        }

        try {
            const response = await fetch(`/api/process-config/projects/${this.currentProject}/product-types/${encodeURIComponent(productTypeName)}/processes/${processId}`, {
                method: 'DELETE'
            });

            const result = await response.json();

            if (result.success) {
                this.showSuccess('工序删除成功');
                await this.loadProjectConfig();
            } else {
                this.showError('工序删除失败: ' + result.error);
            }
        } catch (error) {
            this.showError('工序删除失败: ' + error.message);
        }
    }

    showCreateProjectModal() {
        document.getElementById('createProjectForm').reset();
        new bootstrap.Modal(document.getElementById('createProjectModal')).show();
    }

    async createProject() {
        const form = document.getElementById('createProjectForm');
        if (!form.checkValidity()) {
            form.reportValidity();
            return;
        }

        const projectData = {
            projectName: document.getElementById('newProjectName').value,
            description: document.getElementById('newProjectDescription').value
        };

        try {
            const response = await fetch('/api/process-config/projects', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(projectData)
            });

            const result = await response.json();

            if (result.success) {
                this.showSuccess('项目创建成功');
                bootstrap.Modal.getInstance(document.getElementById('createProjectModal')).hide();
                await this.loadProjects();
            } else {
                this.showError('项目创建失败: ' + result.error);
            }
        } catch (error) {
            this.showError('项目创建失败: ' + error.message);
        }
    }

    async exportConfig() {
        if (!this.currentProject) return;

        try {
            const response = await fetch(`/api/process-config/projects/${this.currentProject}/export`);
            const result = await response.json();

            if (result.success) {
                const dataStr = JSON.stringify(result.data, null, 2);
                const dataBlob = new Blob([dataStr], { type: 'application/json' });
                
                const link = document.createElement('a');
                link.href = URL.createObjectURL(dataBlob);
                link.download = `${this.currentProject}_config_${new Date().toISOString().slice(0, 10)}.json`;
                link.click();
                
                this.showSuccess('配置导出成功');
            } else {
                this.showError('配置导出失败: ' + result.error);
            }
        } catch (error) {
            this.showError('配置导出失败: ' + error.message);
        }
    }

    showImportModal() {
        document.getElementById('importFile').value = '';
        new bootstrap.Modal(document.getElementById('importModal')).show();
    }

    handleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;

        if (!file.name.endsWith('.json')) {
            this.showError('请选择JSON格式的配置文件');
            event.target.value = '';
        }
    }

    async importConfig() {
        const fileInput = document.getElementById('importFile');
        const file = fileInput.files[0];
        
        if (!file) {
            this.showError('请选择要导入的配置文件');
            return;
        }

        try {
            const fileContent = await this.readFileAsText(file);
            const configData = JSON.parse(fileContent);

            const response = await fetch(`/api/process-config/projects/${this.currentProject}/import`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(configData)
            });

            const result = await response.json();

            if (result.success) {
                this.showSuccess('配置导入成功');
                bootstrap.Modal.getInstance(document.getElementById('importModal')).hide();
                await this.loadProjectConfig();
            } else {
                this.showError('配置导入失败: ' + result.error);
            }
        } catch (error) {
            this.showError('配置导入失败: ' + error.message);
        }
    }
    
    async migrateConfig() {
        if (!this.currentProject) return;
        
        // 显示迁移进度模态框
        const modal = new bootstrap.Modal(document.getElementById('migrationModal'));
        modal.show();
        
        // 重置显示状态
        document.getElementById('migrationProgress').style.display = 'block';
        document.getElementById('migrationResult').style.display = 'none';
        document.getElementById('migrationFooter').style.display = 'none';
        
        try {
            const response = await fetch(`/api/process-config/projects/${this.currentProject}/migrate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();
            
            // 显示结果
            document.getElementById('migrationProgress').style.display = 'none';
            document.getElementById('migrationResult').style.display = 'block';
            document.getElementById('migrationFooter').style.display = 'block';
            
            if (result.success) {
                document.getElementById('migrationSuccessIcon').style.display = 'block';
                document.getElementById('migrationErrorIcon').style.display = 'none';
                document.getElementById('migrationResultTitle').textContent = '迁移成功';
                document.getElementById('migrationResultMessage').textContent = 
                    '配置已成功迁移到新的数据结构。原配置已自动备份。';
                
                // 重新加载配置
                await this.loadProjectConfig();
            } else {
                document.getElementById('migrationSuccessIcon').style.display = 'none';
                document.getElementById('migrationErrorIcon').style.display = 'block';
                document.getElementById('migrationResultTitle').textContent = '迁移失败';
                document.getElementById('migrationResultMessage').textContent = 
                    '配置迁移失败: ' + result.error;
            }
        } catch (error) {
            document.getElementById('migrationProgress').style.display = 'none';
            document.getElementById('migrationResult').style.display = 'block';
            document.getElementById('migrationFooter').style.display = 'block';
            document.getElementById('migrationSuccessIcon').style.display = 'none';
            document.getElementById('migrationErrorIcon').style.display = 'block';
            document.getElementById('migrationResultTitle').textContent = '迁移失败';
            document.getElementById('migrationResultMessage').textContent = 
                '配置迁移失败: ' + error.message;
        }
    }

    readFileAsText(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = e => resolve(e.target.result);
            reader.onerror = e => reject(e);
            reader.readAsText(file);
        });
    }

    async showVersionHistory() {
        if (!this.currentProject) return;

        const modal = new bootstrap.Modal(document.getElementById('versionModal'));
        modal.show();

        try {
            const response = await fetch(`/api/process-config/projects/${this.currentProject}/versions`);
            const result = await response.json();

            if (result.success) {
                this.renderVersionHistory(result.data.versions);
            } else {
                this.showError('加载版本历史失败: ' + result.error);
            }
        } catch (error) {
            this.showError('加载版本历史失败: ' + error.message);
        }
    }

    renderVersionHistory(versions) {
        const container = document.getElementById('versionList');
        
        if (versions.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-history"></i>
                    <p>暂无版本历史</p>
                </div>
            `;
            return;
        }

        const html = versions.map(version => `
            <div class="card mb-2">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <h6 class="card-title mb-1">版本 ${version.version}</h6>
                            <small class="text-muted">${new Date(version.updatedAt).toLocaleString()}</small>
                        </div>
                        <button class="btn btn-outline-primary btn-sm" onclick="restoreVersion(${version.version})">
                            恢复此版本
                        </button>
                    </div>
                </div>
            </div>
        `).join('');

        container.innerHTML = html;
    }

    async restoreVersion(version) {
        if (!confirm(`确定要恢复到版本 ${version} 吗？当前配置将被覆盖。`)) {
            return;
        }

        try {
            const response = await fetch(`/api/process-config/projects/${this.currentProject}/versions/${version}/restore`, {
                method: 'POST'
            });

            const result = await response.json();

            if (result.success) {
                this.showSuccess(`成功恢复到版本 ${version}`);
                bootstrap.Modal.getInstance(document.getElementById('versionModal')).hide();
                await this.loadProjectConfig();
            } else {
                this.showError('版本恢复失败: ' + result.error);
            }
        } catch (error) {
            this.showError('版本恢复失败: ' + error.message);
        }
    }

    showSuccess(message) {
        this.showToast(message, 'success');
    }

    showError(message) {
        this.showToast(message, 'error');
        console.error(message);
    }

    showToast(message, type) {
        // 创建toast元素
        const toastId = 'toast_' + Date.now();
        const toastHtml = `
            <div id="${toastId}" class="toast align-items-center text-white bg-${type === 'success' ? 'success' : 'danger'} border-0" role="alert">
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'} me-2"></i>
                        ${message}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            </div>
        `;

        // 添加到页面
        let toastContainer = document.getElementById('toastContainer');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toastContainer';
            toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
            toastContainer.style.zIndex = '9999';
            document.body.appendChild(toastContainer);
        }

        toastContainer.insertAdjacentHTML('beforeend', toastHtml);

        // 显示toast
        const toastElement = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastElement, { delay: 3000 });
        toast.show();

        // 自动清理
        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    }
}

// 全局函数，供HTML调用
let processConfigManager;

document.addEventListener('DOMContentLoaded', () => {
    processConfigManager = new ProcessConfigManager();
});

function selectProject(projectName) {
    processConfigManager.selectProject(projectName);
}

function showAddProcessModal(productTypeName = null) {
    processConfigManager.showAddProcessModal(productTypeName);
}

function editProcess(processId, productTypeName = null) {
    processConfigManager.editProcess(processId, productTypeName);
}

function saveProcess() {
    processConfigManager.saveProcess();
}

function deleteProcess(processId) {
    processConfigManager.deleteProcess(processId);
}

function showCreateProjectModal() {
    processConfigManager.showCreateProjectModal();
}

function createProject() {
    processConfigManager.createProject();
}

function exportConfig() {
    processConfigManager.exportConfig();
}

function showImportModal() {
    processConfigManager.showImportModal();
}

function importConfig() {
    processConfigManager.importConfig();
}

function showVersionHistory() {
    processConfigManager.showVersionHistory();
}

function restoreVersion(version) {
    processConfigManager.restoreVersion(version);
}

function migrateConfig() {
    processConfigManager.migrateConfig();
}