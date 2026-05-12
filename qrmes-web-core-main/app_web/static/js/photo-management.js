/**
 * 工序照片管理JavaScript模块
 */

let currentPhotos = [];
let currentPage = 1;
let photosPerPage = 20;
let currentPhotoId = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    loadPhotoStatistics();
    loadProcessSteps();
    loadPhotos();
});

/**
 * 加载照片统计信息
 */
async function loadPhotoStatistics() {
    try {
        const response = await fetch('/api/photos/statistics');
        const data = await response.json();
        
        if (data.success) {
            const stats = data.statistics;
            document.getElementById('totalPhotos').textContent = stats.totalPhotos || 0;
            document.getElementById('uploadedPhotos').textContent = stats.uploadedPhotos || 0;
            document.getElementById('pendingPhotos').textContent = stats.pendingPhotos || 0;
            document.getElementById('totalSize').textContent = formatFileSize(stats.totalSize || 0);
        }
    } catch (error) {
        console.error('加载统计信息失败:', error);
    }
}

/**
 * 加载工序步骤选项
 */
async function loadProcessSteps() {
    try {
        const response = await fetch('/api/process-config');
        const data = await response.json();
        
        if (data.success) {
            const select = document.getElementById('processStepFilter');
            select.innerHTML = '<option value="">全部工序</option>';
            
            data.configs.forEach(config => {
                const option = document.createElement('option');
                option.value = config.name;
                option.textContent = config.name;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('加载工序步骤失败:', error);
    }
}

/**
 * 加载照片列表
 */
async function loadPhotos() {
    try {
        showLoading();
        
        // 构建查询参数
        const params = new URLSearchParams();
        const productSerial = document.getElementById('productSerialFilter').value.trim();
        const processStep = document.getElementById('processStepFilter').value;
        const dateFrom = document.getElementById('dateFromFilter').value;
        const dateTo = document.getElementById('dateToFilter').value;
        
        if (productSerial) params.append('productSerial', productSerial);
        if (processStep) params.append('processStep', processStep);
        if (dateFrom) params.append('dateFrom', new Date(dateFrom).getTime());
        if (dateTo) params.append('dateTo', new Date(dateTo + ' 23:59:59').getTime());
        params.append('limit', photosPerPage * 10); // 加载更多数据用于分页
        
        const response = await fetch(`/api/photos/search?${params}`);
        const data = await response.json();
        
        if (data.success) {
            currentPhotos = data.photos;
            displayPhotos();
            updatePagination();
        } else {
            showError('加载照片失败: ' + data.error);
        }
    } catch (error) {
        console.error('加载照片失败:', error);
        showError('加载照片失败: ' + error.message);
    }
}

/**
 * 显示照片网格
 */
function displayPhotos() {
    const photoGrid = document.getElementById('photoGrid');
    
    if (currentPhotos.length === 0) {
        photoGrid.innerHTML = `
            <div class="no-photos">
                <i class="bi bi-camera" style="font-size: 3em; color: #5a6f85;"></i>
                <p>没有找到照片</p>
            </div>
        `;
        return;
    }
    
    // 计算当前页的照片
    const startIndex = (currentPage - 1) * photosPerPage;
    const endIndex = startIndex + photosPerPage;
    const pagePhotos = currentPhotos.slice(startIndex, endIndex);
    
    photoGrid.innerHTML = pagePhotos.map(photo => `
        <div class="photo-card">
            <img src="${photo.thumbnailUrl}" 
                 alt="${photo.file_name}" 
                 class="photo-thumbnail"
                 onclick="showPhotoDetails(${photo.id})"
                 onerror="this.src='/static/images/no-image.png'">
            <div class="photo-info">
                <div class="photo-title">${photo.file_name}</div>
                <div class="photo-meta">
                    <i class="bi bi-tag"></i> ${photo.product_serial}
                </div>
                <div class="photo-meta">
                    <i class="bi bi-gear"></i> ${photo.process_step}
                </div>
                <div class="photo-meta">
                    <i class="bi bi-clock"></i> ${formatDateTime(photo.captured_at)}
                </div>
                <div class="photo-meta">
                    <i class="bi bi-person"></i> ${photo.display_name || photo.synology_username || '未知用户'}
                </div>
                <div class="photo-meta">
                    <span class="upload-status ${photo.uploaded_at ? 'uploaded' : 'pending'}">
                        ${photo.uploaded_at ? '已上传' : '待上传'}
                    </span>
                    <span class="ms-2">${formatFileSize(photo.file_size)}</span>
                </div>
                <div class="photo-actions">
                    <button class="btn btn-sm btn-outline-primary" onclick="showPhotoDetails(${photo.id})">
                        <i class="bi bi-eye"></i> 查看
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="confirmDeletePhoto(${photo.id})">
                        <i class="bi bi-trash"></i> 删除
                    </button>
                </div>
            </div>
        </div>
    `).join('');
}

/**
 * 显示照片详情
 */
async function showPhotoDetails(photoId) {
    try {
        const response = await fetch(`/api/photos/${photoId}`);
        const data = await response.json();
        
        if (data.success) {
            const photo = data.photo;
            currentPhotoId = photoId;
            
            // 填充模态框内容
            document.getElementById('photoModalTitle').textContent = photo.file_name;
            document.getElementById('photoModalImage').src = photo.url;
            document.getElementById('modalProductSerial').textContent = photo.product_serial;
            document.getElementById('modalProcessStep').textContent = photo.process_step;
            document.getElementById('modalCapturedAt').textContent = formatDateTime(photo.captured_at);
            document.getElementById('modalCapturedBy').textContent = photo.display_name || photo.synology_username || '未知用户';
            document.getElementById('modalFileSize').textContent = formatFileSize(photo.file_size);
            document.getElementById('modalUploadStatus').innerHTML = `
                <span class="upload-status ${photo.uploaded_at ? 'uploaded' : 'pending'}">
                    ${photo.uploaded_at ? '已上传' : '待上传'}
                </span>
            `;
            document.getElementById('modalMetadata').textContent = JSON.stringify(photo.metadata || {}, null, 2);
            
            // 显示模态框
            const modal = new bootstrap.Modal(document.getElementById('photoModal'));
            modal.show();
        } else {
            showError('获取照片详情失败: ' + data.error);
        }
    } catch (error) {
        console.error('获取照片详情失败:', error);
        showError('获取照片详情失败: ' + error.message);
    }
}

/**
 * 确认删除照片
 */
async function confirmDeletePhoto(photoId) {
    if (confirm('确定要删除这张照片吗？此操作不可撤销。')) {
        await deletePhotoById(photoId);
    }
}

/**
 * 删除照片（从模态框调用）
 */
async function deletePhoto() {
    if (currentPhotoId && confirm('确定要删除这张照片吗？此操作不可撤销。')) {
        await deletePhotoById(currentPhotoId);
        // 关闭模态框
        try {
            const modal = bootstrap.Modal.getInstance(document.getElementById('photoModal'));
            if (modal) {
                modal.hide();
            }
        } catch (e) {
            // 如果使用自定义模态框，调用 closeModal
            if (typeof closeModal === 'function') {
                closeModal('photoModal');
            }
        }
    }
}

/**
 * 根据ID删除照片
 */
async function deletePhotoById(photoId) {
    try {
        const response = await fetch(`/api/photos/${photoId}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        
        if (data.success) {
            showSuccess('照片删除成功');
            loadPhotos(); // 重新加载照片列表
            loadPhotoStatistics(); // 更新统计信息
        } else {
            showError('删除照片失败: ' + data.error);
        }
    } catch (error) {
        console.error('删除照片失败:', error);
        showError('删除照片失败: ' + error.message);
    }
}

/**
 * 搜索照片
 */
function searchPhotos() {
    currentPage = 1;
    loadPhotos();
}

/**
 * 清空过滤器
 */
function clearFilters() {
    document.getElementById('productSerialFilter').value = '';
    document.getElementById('processStepFilter').value = '';
    document.getElementById('dateFromFilter').value = '';
    document.getElementById('dateToFilter').value = '';
    currentPage = 1;
    loadPhotos();
}

/**
 * 刷新照片
 */
function refreshPhotos() {
    loadPhotoStatistics();
    loadPhotos();
}

/**
 * 更新分页
 */
function updatePagination() {
    const totalPages = Math.ceil(currentPhotos.length / photosPerPage);
    const pagination = document.getElementById('pagination');
    
    if (totalPages <= 1) {
        pagination.innerHTML = '';
        return;
    }
    
    let paginationHTML = '';
    
    // 上一页
    paginationHTML += `
        <li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="changePage(${currentPage - 1})">上一页</a>
        </li>
    `;
    
    // 页码
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);
    
    if (startPage > 1) {
        paginationHTML += `<li class="page-item"><a class="page-link" href="#" onclick="changePage(1)">1</a></li>`;
        if (startPage > 2) {
            paginationHTML += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
    }
    
    for (let i = startPage; i <= endPage; i++) {
        paginationHTML += `
            <li class="page-item ${i === currentPage ? 'active' : ''}">
                <a class="page-link" href="#" onclick="changePage(${i})">${i}</a>
            </li>
        `;
    }
    
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            paginationHTML += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
        paginationHTML += `<li class="page-item"><a class="page-link" href="#" onclick="changePage(${totalPages})">${totalPages}</a></li>`;
    }
    
    // 下一页
    paginationHTML += `
        <li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="changePage(${currentPage + 1})">下一页</a>
        </li>
    `;
    
    pagination.innerHTML = paginationHTML;
}

/**
 * 切换页面
 */
function changePage(page) {
    const totalPages = Math.ceil(currentPhotos.length / photosPerPage);
    if (page >= 1 && page <= totalPages) {
        currentPage = page;
        displayPhotos();
        updatePagination();
    }
}

/**
 * 显示加载状态
 */
function showLoading() {
    document.getElementById('photoGrid').innerHTML = `
        <div class="loading">
            <div class="spinner-border" role="status">
                <span class="visually-hidden">加载中...</span>
            </div>
            <p>正在加载照片...</p>
        </div>
    `;
}

/**
 * 显示成功消息
 */
function showSuccess(message) {
    // 可以使用 Toast 或其他通知组件
    alert(message);
}

/**
 * 显示错误消息
 */
function showError(message) {
    // 可以使用 Toast 或其他通知组件
    alert(message);
}

/**
 * 格式化文件大小
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * 格式化日期时间
 */
function formatDateTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}