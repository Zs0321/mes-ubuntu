/**
 * 工序照片管理JavaScript模块 V2
 * 支持按工序分组显示
 */

// 使用 window 对象确保全局可访问
window.currentPhotos = [];
let photosPerPage = 20;
window.currentPage = 1;
const PHOTO_VIEW_MODES = {
    GRID: 'grid',
    GROUPED: 'grouped',
};

function normalizePhotoViewMode(viewType) {
    return viewType === PHOTO_VIEW_MODES.GRID ? PHOTO_VIEW_MODES.GRID : PHOTO_VIEW_MODES.GROUPED;
}

function setPhotoViewMode(viewType) {
    const normalized = normalizePhotoViewMode(viewType);
    window.currentView = normalized;
    window.__photoViewMode = normalized;
    return normalized;
}

function getPhotoViewMode() {
    return normalizePhotoViewMode(window.__photoViewMode || window.currentView);
}

window.getPhotoViewMode = getPhotoViewMode;
window.setPhotoViewMode = setPhotoViewMode;
setPhotoViewMode(PHOTO_VIEW_MODES.GROUPED); // 默认使用分组视图

window.toggleView = function(viewType) {
    const mode = setPhotoViewMode(viewType);
    const gridView = document.getElementById('photoContainer');
    const groupedView = document.getElementById('photoGroupedContainer');
    const btnGrid = document.getElementById('btnGridView');
    const btnGrouped = document.getElementById('btnGroupedView');

    if (gridView) {
        gridView.style.display = mode === PHOTO_VIEW_MODES.GRID ? 'grid' : 'none';
    }
    if (groupedView) {
        groupedView.style.display = mode === PHOTO_VIEW_MODES.GRID ? 'none' : 'block';
    }
    if (btnGrid) {
        btnGrid.classList.toggle('btn-primary', mode === PHOTO_VIEW_MODES.GRID);
        btnGrid.classList.toggle('btn-secondary', mode !== PHOTO_VIEW_MODES.GRID);
    }
    if (btnGrouped) {
        btnGrouped.classList.toggle('btn-primary', mode !== PHOTO_VIEW_MODES.GRID);
        btnGrouped.classList.toggle('btn-secondary', mode === PHOTO_VIEW_MODES.GRID);
    }

    if (mode === PHOTO_VIEW_MODES.GRID) {
        if (typeof window.displayPhotos === 'function') {
            window.displayPhotos();
        }
    } else if (typeof window.displayPhotosGrouped === 'function') {
        window.displayPhotosGrouped(Array.isArray(window.currentPhotos) ? window.currentPhotos : []);
    }

    if (typeof updatePagination === 'function') {
        updatePagination();
    }
};

window.currentGroupBy = 'date'; // 'product' | 'process' | 'date'（默认按日期分组）
window.currentPhotoId = null;
let photoStats = {
    totalPhotos: 0,
    totalSizeBytes: 0,
    productCount: 0,
    processCount: 0,
    dateCount: 0
};
let photoMetadataCache = {}; // 只缓存照片元数据，不缓存图片数据
let serverScopeStats = null; // 后端返回的范围统计（例如 recent 全量统计）
const DEFAULT_RECENT_DAYS = 2;
const DEFAULT_RECENT_LIMIT = 200;
let currentDataScope = 'recent'; // 'recent' | 'scan'
let lastCacheInfo = null;
let globalFilterOptions = {
    projects: [],
    products: [],
    uploaders: [],
};

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    const projectFilter = document.getElementById('projectFilter');
    if (projectFilter) {
        projectFilter.addEventListener('change', async function() {
            await loadGlobalFilterOptions(projectFilter.value || '');
            buildFilterOptions(Object.values(photoMetadataCache || {}));
        });
    }

    loadPhotos();
    // 默认按日期分组显示分组视图
    if (typeof changeGroupBy === 'function') {
        changeGroupBy('date');
    } else {
        window.currentGroupBy = 'date';
    }
    if (typeof window.toggleView === 'function') {
        window.toggleView('grouped');
    }
});

/**
 * 从文件名解析照片信息
 * 文件名格式: {产品序列号}_{工序名称}_{时间戳}.jpg
 */
function parsePhotoFileName(fileName) {
    const parts = fileName.replace('.jpg', '').split('_');
    if (parts.length >= 3) {
        return {
            productSerial: parts[0],
            processStep: parts[1],
            timestamp: parts.slice(2).join('_')
        };
    }
    return null;
}

function buildPhotoStatsFromPhotos(photos) {
    const productSet = new Set();
    const processSet = new Set();
    const dateSet = new Set();
    let totalSize = 0;

    photos.forEach(p => {
        if (p.product_serial) {
           productSet.add(p.product_serial);
        }
        if (p.process_step) {
           processSet.add(p.process_step);
        }
        if (p.captured_at) {
           dateSet.add(formatDateKey(p.captured_at));
        }
        if (typeof p.file_size === 'number') {
           totalSize += p.file_size;
        }
    });

    return {
        totalPhotos: photos.length,
        totalSizeBytes: totalSize,
        productCount: productSet.size,
        processCount: processSet.size,
        dateCount: dateSet.size
    };
}

function normalizeServerStats(stats) {
    if (!stats || typeof stats !== 'object') {
        return null;
    }
    return {
        totalPhotos: Number(stats.totalPhotos ?? stats.total_photos ?? 0) || 0,
        totalSizeBytes: Number(stats.totalSizeBytes ?? stats.total_size_bytes ?? 0) || 0,
        productCount: Number(stats.productCount ?? stats.product_count ?? 0) || 0,
        processCount: Number(stats.processCount ?? stats.process_count ?? 0) || 0,
        dateCount: Number(stats.dateCount ?? stats.date_count ?? 0) || 0
    };
}

/**
 * 加载照片统计信息（默认优先使用后端完整统计）
 */
function loadPhotoStatistics() {
    const photos = Array.isArray(currentPhotos) ? currentPhotos : [];
    const localStats = buildPhotoStatsFromPhotos(photos);
    const cacheSize = Object.keys(photoMetadataCache || {}).length;
    const isSubsetView = cacheSize > 0 && photos.length !== cacheSize;
    const useServerStats = Boolean(serverScopeStats && currentDataScope === 'recent' && !isSubsetView);

    photoStats = useServerStats ? serverScopeStats : localStats;

    const totalPhotosEl = document.getElementById('totalPhotos');
    const uploadedPhotosEl = document.getElementById('uploadedPhotos');
    const totalSizeEl = document.getElementById('totalSize');
    const totalProcessesEl = document.getElementById('totalProcesses');
    const totalProcessesLabelEl = document.getElementById('totalProcessesLabel');

    if (totalPhotosEl) {
        totalPhotosEl.textContent = photoStats.totalPhotos || 0;
    }
    if (uploadedPhotosEl) {
        // 目录扫描视角下，认为全部为“已上传”
        uploadedPhotosEl.textContent = photoStats.totalPhotos || 0;
    }
    if (totalSizeEl) {
        totalSizeEl.textContent = formatFileSize(photoStats.totalSizeBytes || 0);
    }

    if (totalProcessesEl) {
        if (window.currentGroupBy === 'product') {
            totalProcessesEl.textContent = photoStats.productCount || 0;
            if (totalProcessesLabelEl) totalProcessesLabelEl.textContent = '产品数量';
        } else if (window.currentGroupBy === 'process') {
            totalProcessesEl.textContent = photoStats.processCount || 0;
            if (totalProcessesLabelEl) totalProcessesLabelEl.textContent = '工序数量';
        } else {
            totalProcessesEl.textContent = photoStats.dateCount || 0;
            if (totalProcessesLabelEl) totalProcessesLabelEl.textContent = '日期数量';
        }
    }
}

/**
 * 加载工序步骤选项
 */
async function loadProcessSteps() {
    // 如果已经有缓存数据，直接基于缓存构建下拉
    if (Object.keys(photoMetadataCache).length > 0) {
        buildProcessStepOptions(Object.values(photoMetadataCache));
        return;
    }

    try {
        // 默认从 recent 结果构建下拉，避免首次加载触发全量扫描
        const response = await fetch(`/api/photos/async/recent?days=${DEFAULT_RECENT_DAYS}&limit=${DEFAULT_RECENT_LIMIT}`);
        const data = await response.json();
        
        if (data.success) {
            buildProcessStepOptions(data.photos || []);
        }
    } catch (error) {
        console.error('加载工序步骤失败:', error);
    }
}

/**
 * 基于已有照片列表构建工序下拉选项
 */
function buildProcessStepOptions(photos) {
    try {
        const select = document.getElementById('processStepFilter');
        if (!select) return;

        const processSteps = new Set();
        (photos || []).forEach(photo => {
            const step = photo.process_step || photo.processStep;
            if (step) processSteps.add(step);
        });

        select.innerHTML = '<option value="">全部工序</option>';
        Array.from(processSteps).sort().forEach(step => {
            const option = document.createElement('option');
            option.value = step;
            option.textContent = step;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('构建工序步骤选项失败:', error);
    }
}

function buildSelectOptions(selectId, values, defaultLabel) {
    const select = document.getElementById(selectId);
    if (!select) return;

    const valueSet = new Set();
    (values || []).forEach((item) => {
        const text = String(item || '').trim();
        if (text) {
            valueSet.add(text);
        }
    });

    const currentValue = select.value;
    select.innerHTML = `<option value="">${defaultLabel}</option>`;

    Array.from(valueSet).sort((a, b) => a.localeCompare(b, 'zh-CN')).forEach((item) => {
        const option = document.createElement('option');
        option.value = item;
        option.textContent = item;
        select.appendChild(option);
    });

    if (currentValue && valueSet.has(currentValue)) {
        select.value = currentValue;
    }
}

function uniqueSortedValues(values) {
    const set = new Set();
    (values || []).forEach((item) => {
        const text = String(item || '').trim();
        if (text) {
            set.add(text);
        }
    });
    return Array.from(set).sort((a, b) => a.localeCompare(b, 'zh-CN'));
}

async function loadGlobalFilterOptions(projectName = '') {
    const query = new URLSearchParams();
    if (projectName) query.set('projectName', projectName);
    const qs = query.toString();
    const url = `/api/photos/async/filter-options${qs ? `?${qs}` : ''}`;

    try {
        const response = await fetch(url);
        const data = await response.json();
        if (data && data.success && data.options) {
            globalFilterOptions = {
                projects: uniqueSortedValues(data.options.projects),
                products: uniqueSortedValues(data.options.products),
                uploaders: uniqueSortedValues(data.options.uploaders),
            };
        }
    } catch (error) {
        console.warn('加载全量筛选选项失败，回退到当前结果集:', error);
    }
}

function getPhotoMetadataValuesByProject(projectName = '') {
    const all = Object.values(photoMetadataCache || {});
    const targetProject = String(projectName || '').trim();
    const filtered = !targetProject
        ? all
        : all.filter((item) => String(item.project_name || '').trim() === targetProject);

    return {
        projects: filtered.map((item) => item.project_name),
        products: filtered.map((item) => item.product_type),
        uploaders: filtered.map((item) => resolveUploaderLabel(item)),
    };
}

function resolveUploaderLabel(photo) {
    return String(
        photo?.uploader ||
        photo?.display_name ||
        photo?.synology_username ||
        photo?.captured_by ||
        photo?.capturedBy ||
        '系统'
    ).trim() || '系统';
}

function buildFilterOptions(photos) {
    buildProcessStepOptions(photos);
    const selectedProject = document.getElementById('projectFilter')?.value || '';
    const localValues = getPhotoMetadataValuesByProject(selectedProject);
    const photoValues = {
        projects: (photos || []).map((photo) => photo.projectName || photo.project_name),
        products: (photos || []).map((photo) => photo.productName || photo.product_type),
        uploaders: (photos || []).map((photo) => resolveUploaderLabel(photo)),
    };

    const projects = uniqueSortedValues([...(globalFilterOptions.projects || []), ...localValues.projects, ...photoValues.projects]);
    const products = uniqueSortedValues([...(globalFilterOptions.products || []), ...localValues.products, ...photoValues.products]);
    const uploaders = uniqueSortedValues([...(globalFilterOptions.uploaders || []), ...localValues.uploaders, ...photoValues.uploaders]);

    buildSelectOptions(
        'projectFilter',
        projects,
        '全部项目'
    );
    buildSelectOptions(
        'productTypeFilter',
        products,
        '全部产品'
    );
    buildSelectOptions(
        'uploaderFilter',
        uploaders,
        '全部上传人'
    );
}

function collectCurrentFilters() {
    return {
        productSerial: document.getElementById('productSerialFilter')?.value?.trim() || '',
        processStep: document.getElementById('processStepFilter')?.value || '',
        projectName: document.getElementById('projectFilter')?.value || '',
        productType: document.getElementById('productTypeFilter')?.value || '',
        uploader: document.getElementById('uploaderFilter')?.value || '',
        dateFrom: document.getElementById('dateFromFilter')?.value || '',
        dateTo: document.getElementById('dateToFilter')?.value || '',
    };
}

function buildScanDirectoryQueryString(filters) {
    const query = new URLSearchParams();
    if (filters.projectName) query.set('projectName', filters.projectName);
    if (filters.productType) query.set('productName', filters.productType);
    if (filters.productSerial) query.set('serialNumber', filters.productSerial);
    if (filters.processStep) query.set('processStep', filters.processStep);
    if (filters.uploader) query.set('uploader', filters.uploader);
    if (filters.dateFrom) query.set('dateFrom', filters.dateFrom);
    if (filters.dateTo) query.set('dateTo', filters.dateTo);
    const qs = query.toString();
    return qs ? `?${qs}` : '';
}

/**
 * 加载照片列表并刷新缓存
 */
async function loadPhotos() {
    try {
        showLoading();

        const filters = collectCurrentFilters();
        const mode = hasActiveFilters() ? 'scan' : 'recent';
        const url = mode === 'recent'
            ? `/api/photos/async/recent?days=${DEFAULT_RECENT_DAYS}&limit=${DEFAULT_RECENT_LIMIT}`
            : `/api/photos/async/scan-directory-async${buildScanDirectoryQueryString(filters)}`;

        // 默认使用 recent，只有当用户筛选/搜索时才触发全量扫描
        const response = await fetch(url);
        const data = await response.json();

        if (data.success) {
            currentDataScope = mode;
            lastCacheInfo = data.cacheInfo || null;
            // recent 接口同时返回 statsAll（全量统计）与 stats（当前 recent 范围）
            // 默认统计卡片优先显示全量统计，避免被 200 条展示上限误导
            serverScopeStats = normalizeServerStats(data.statsAll || data.stats);
            updateScopeHint(currentDataScope, lastCacheInfo);

            // 只缓存元数据，不缓存图片数据
            const photos = Array.isArray(data.photos) ? data.photos : [];
            
            // 将元数据存入缓存
            photoMetadataCache = {};
            photos.forEach(photo => {
                photoMetadataCache[photo.id] = {
                    id: photo.id,
                    file_name: photo.filename || photo.file_name,
                    product_serial: photo.serialNumber || photo.product_serial,
                    process_step: photo.processStep || photo.process_step,
                    project_name: photo.projectName || photo.project_name,
                    product_type: photo.productName || photo.product_type,
                    captured_at: photo.timestamp || photo.captured_at,
                    captured_by: photo.capturedBy || photo.captured_by || '',
                    uploader: resolveUploaderLabel(photo),
                    file_size: photo.size || photo.file_size,
                    file_path: photo.id,
                    url: photo.fullUrl || photo.url,
                    originalUrl: photo.originalUrl,
                    thumbnailUrl: photo.thumbnailUrl
                };
            });

            await loadGlobalFilterOptions(filters.projectName);

            // 基于最新数据构建筛选下拉
            buildFilterOptions(photos);

            // 应用当前过滤条件并渲染
            applyPhotoFilters();
            
            // 显示提示信息
            if (data.cacheInfo && data.cacheInfo.willGenerateInBackground) {
                console.log('照片列表已加载，缓存将在后台生成');
            }
        } else {
            serverScopeStats = null;
            showError('加载照片失败: ' + data.error);
        }
    } catch (error) {
        serverScopeStats = null;
        console.error('加载照片失败:', error);
        showError('加载照片失败: ' + error.message);
    }
}

function hasActiveFilters() {
    try {
        const {
            productSerial,
            processStep,
            projectName,
            productType,
            uploader,
            dateFrom,
            dateTo,
        } = collectCurrentFilters();
        return Boolean(productSerial || processStep || projectName || productType || uploader || dateFrom || dateTo);
    } catch (e) {
        return false;
    }
}

function updateScopeHint(scope, cacheInfo) {
    const el = document.getElementById('photoScopeHint');
    if (!el) return;

    if (scope === 'recent') {
        let msg = `默认显示最近${DEFAULT_RECENT_DAYS}天 / ${DEFAULT_RECENT_LIMIT}张。设置筛选条件后点击“搜索”可扫描全量查看更多。`;
        if (cacheInfo && cacheInfo.indexReady === false) {
            msg += '（索引未就绪，正在后台构建，稍后点击“刷新”）';
        }
        el.textContent = msg;
        return;
    }

    el.textContent = '当前为全量扫描结果（可能较慢）。清空筛选后可回到默认最近视图。';
}

/**
 * 在前端基于缓存数据应用过滤条件并更新视图
 */
function applyPhotoFilters() {
    // 从元数据缓存中获取照片列表
    let allPhotos = Object.values(photoMetadataCache);

    // 应用筛选条件
    const {
        productSerial,
        processStep,
        projectName,
        productType,
        uploader,
        dateFrom,
        dateTo,
    } = collectCurrentFilters();

    if (productSerial) {
        allPhotos = allPhotos.filter(p => (p.product_serial || '').includes(productSerial));
    }
    if (processStep) {
        allPhotos = allPhotos.filter(p => p.process_step === processStep);
    }
    if (projectName) {
        allPhotos = allPhotos.filter(p => (p.project_name || '') === projectName);
    }
    if (productType) {
        allPhotos = allPhotos.filter(p => (p.product_type || '') === productType);
    }
    if (uploader) {
        allPhotos = allPhotos.filter(p => resolveUploaderLabel(p) === uploader);
    }
    if (dateFrom) {
        const fromTime = new Date(dateFrom).getTime();
        allPhotos = allPhotos.filter(p => typeof p.captured_at === 'number' && p.captured_at >= fromTime);
    }
    if (dateTo) {
        const toTime = new Date(dateTo + ' 23:59:59').getTime();
        allPhotos = allPhotos.filter(p => typeof p.captured_at === 'number' && p.captured_at <= toTime);
    }

    currentPhotos = allPhotos;

    // 基于当前照片列表更新统计信息
    loadPhotoStatistics();

    // 根据当前视图模式更新视图内容
    if (getPhotoViewMode() === 'grouped' && typeof window.displayPhotosGrouped === 'function') {
        // 分组视图
        window.displayPhotosGrouped(currentPhotos);
    } else {
        // 网格视图
        displayPhotos();
    }
}

/**
 * 显示照片
 */
function displayPhotos() {
    // 网格容器始终渲染网格视图，分组视图由 toggleView 控制显示容器
    displayPhotosGrid();
}

/**
 * 网格视图显示照片
 */
function displayPhotosGrid() {
    const container = document.getElementById('photoContainer');
    
    if (currentPhotos.length === 0) {
        container.innerHTML = `
            <div class="no-photos">
                <i class="bi bi-camera" style="font-size: 3em; color: #ccc;"></i>
                <p>没有找到照片</p>
            </div>
        `;
        return;
    }
    
    // 计算当前页的照片
    const startIndex = ((window.currentPage || 1) - 1) * photosPerPage;
    const endIndex = startIndex + photosPerPage;
    const pagePhotos = currentPhotos.slice(startIndex, endIndex);
    
    // 让 .photo-container 直接承载 .photo-card，匹配模板 CSS 的 grid 布局
    container.innerHTML = pagePhotos.map(photo => createPhotoCard(photo)).join('');
    
    updatePagination();
}

/**
 * 创建照片卡片HTML
 */
function createPhotoCard(photo) {
    const processStep = photo.process_step || '未知工序';
    const productSerial = photo.product_serial || '未知产品';
    const projectName = photo.project_name || '';
    const productType = photo.product_type || '';
    const uploader = resolveUploaderLabel(photo);
    const serialStatus = photo.__serialProcessStatus || null;
    let processStatusHtml = '';
    if (serialStatus && serialStatus.has_requirements) {
        const complete = Boolean(serialStatus.complete);
        const color = complete ? '#198754' : '#dc3545';
        const summary = complete
            ? `🧾 工序状态：${serialStatus.recorded_count}/${serialStatus.required_total}（完成）`
            : `🧾 工序状态：${serialStatus.recorded_count}/${serialStatus.required_total}，缺失 ${serialStatus.missing_count}`;
        const inferred = serialStatus.inferred_current_process || (complete ? '全部工序已完成' : '待开始');
        processStatusHtml = `
            <div class="photo-meta" style="color:${color}; font-weight:600;">${summary}</div>
            <div class="photo-meta" style="color:${color};">📍 推测当前工序：${inferred}</div>
        `;
    }
    
    // 转义文件路径中的特殊字符
    const escapedPath = (photo.file_path || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    
    return `
        <div class="photo-card" data-photo-path="${photo.file_path || ''}">
            <img src="${photo.thumbnailUrl || photo.url}"
                 alt="${photo.file_name}"
                 class="photo-img"
                 onclick="showPhotoDetailsFromFile('${escapedPath}')"
                 onerror="handleImageError(this, '${photo.thumbnailUrl || photo.url}')"
                 data-retry-count="0">
            <div class="photo-info">
                <h4 title="${photo.file_name}">${photo.file_name}</h4>
                <div class="photo-meta">
                    <i class="bi bi-tag"></i> ${productSerial}
                </div>
                <div class="photo-meta">
                    <span class="process-badge">
                        <i class="bi bi-gear"></i> ${processStep}
                    </span>
                </div>
                ${projectName ? `<div class="photo-meta"><i class="bi bi-folder"></i> ${projectName}</div>` : ''}
                ${productType ? `<div class="photo-meta"><i class="bi bi-box"></i> ${productType}</div>` : ''}
                ${uploader ? `<div class="photo-meta"><i class="bi bi-person"></i> ${uploader}</div>` : ''}
                ${processStatusHtml}
                <div class="photo-meta">
                    <i class="bi bi-clock"></i> ${formatDateTime(photo.captured_at)}
                </div>
                <div class="photo-meta">
                    <span class="upload-status uploaded">已上传</span>
                    <span class="ms-2">${formatFileSize(photo.file_size)}</span>
                </div>
                <div class="photo-actions">
                    <button class="btn btn-sm btn-outline-primary" onclick="showPhotoDetailsFromFile('${escapedPath}')">
                        <i class="bi bi-eye"></i> 查看
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="confirmDeletePhotoFile('${escapedPath}')">
                        <i class="bi bi-trash"></i> 删除
                    </button>
                </div>
            </div>
        </div>
    `;
}

/**
 * 切换工序分组的展开/折叠
 */
function toggleProcessGroup(groupId) {
    const body = document.getElementById(groupId);
    const icon = document.getElementById(`${groupId}-icon`);
    
    if (body.classList.contains('collapsed')) {
        body.classList.remove('collapsed');
        icon.classList.remove('bi-chevron-right');
        icon.classList.add('bi-chevron-down');
    } else {
        body.classList.add('collapsed');
        icon.classList.remove('bi-chevron-down');
        icon.classList.add('bi-chevron-right');
    }
}

/**
 * 切换视图模式
 */
/**
 * 显示照片详情（从文件路径）
 */
function showPhotoDetailsFromFile(filePath) {
    // 从当前照片列表中查找
    const photo = currentPhotos.find(p => p.file_path === filePath);
    
    if (!photo) {
        showError('照片不存在');
        console.error('照片未找到:', filePath);
        return;
    }
    
    console.log('显示照片详情:', photo);
    
    // 填充模态框内容
    document.getElementById('photoModalTitle').textContent = photo.file_name;
    
    // 设置图片URL，优先使用压缩图，失败时回退到原图
    const imgElement = document.getElementById('photoModalImage');
    imgElement.src = photo.url || photo.originalUrl || photo.thumbnailUrl;
    
    // 添加错误处理
    imgElement.onerror = function() {
        console.error('图片加载失败:', this.src);
        // 尝试使用原图URL
        if (this.src !== photo.originalUrl && photo.originalUrl) {
            console.log('尝试加载原图:', photo.originalUrl);
            this.src = photo.originalUrl;
        } else if (this.src !== photo.thumbnailUrl && photo.thumbnailUrl) {
            console.log('尝试加载缩略图:', photo.thumbnailUrl);
            this.src = photo.thumbnailUrl;
        } else {
            // 所有URL都失败，显示错误图片
            this.src = '/static/images/no-image.png';
            showError('照片加载失败，文件可能不存在或已损坏');
        }
    };
    
    // 添加加载成功处理
    imgElement.onload = function() {
        console.log('图片加载成功:', this.src);
    };
    
    document.getElementById('modalProductSerial').textContent = photo.product_serial || '未知';
    document.getElementById('modalProcessStep').textContent = photo.process_step || '未知';
    document.getElementById('modalCapturedAt').textContent = formatDateTime(photo.captured_at);
    document.getElementById('modalCapturedBy').textContent = resolveUploaderLabel(photo);
    document.getElementById('modalFileSize').textContent = formatFileSize(photo.file_size);
    document.getElementById('modalUploadStatus').innerHTML = `
        <span class="upload-status uploaded">已上传</span>
    `;
    
    // 显示元数据
    const metadata = {
        '项目': photo.project_name || '-',
        '产品类型': photo.product_type || '-',
        '上传人': resolveUploaderLabel(photo),
        '文件路径': photo.file_path,
        '压缩图URL': photo.url || '-',
        '原图URL': photo.originalUrl || '-',
        '缩略图URL': photo.thumbnailUrl || '-'
    };
    document.getElementById('modalMetadata').textContent = JSON.stringify(metadata, null, 2);
    
    // 保存当前照片路径
    window.currentPhotoId = filePath;
    if (typeof window.resetModalPhotoRotation === 'function') {
        window.resetModalPhotoRotation();
    }
    
    // 显示模态框
    const modal = new bootstrap.Modal(document.getElementById('photoModal'));
    modal.show();
}

/**
 * 显示照片详情（旧版本，保持兼容）
 */
async function showPhotoDetails(photoId) {
    try {
        const response = await fetch(`/api/photos/${photoId}`);
        const data = await response.json();
        
        if (data.success) {
            const photo = data.photo;
            const parsed = parsePhotoFileName(photo.file_name);
            window.currentPhotoId = photoId;
            
            // 填充模态框内容
            document.getElementById('photoModalTitle').textContent = photo.file_name;
            document.getElementById('photoModalImage').src = photo.url;
            document.getElementById('modalProductSerial').textContent = parsed ? parsed.productSerial : (photo.product_serial || '未知');
            document.getElementById('modalProcessStep').textContent = parsed ? parsed.processStep : (photo.process_step || '未知');
            document.getElementById('modalCapturedAt').textContent = formatDateTime(photo.captured_at);
            document.getElementById('modalCapturedBy').textContent = photo.display_name || photo.synology_username || '未知用户';
            document.getElementById('modalFileSize').textContent = formatFileSize(photo.file_size);
            document.getElementById('modalUploadStatus').innerHTML = `
                <span class="upload-status ${photo.uploaded_at ? 'uploaded' : 'pending'}">
                    ${photo.uploaded_at ? '已上传' : '待上传'}
                </span>
            `;
            document.getElementById('modalMetadata').textContent = JSON.stringify(photo.metadata || {}, null, 2);
            if (typeof window.resetModalPhotoRotation === 'function') {
                window.resetModalPhotoRotation();
            }
            
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
 * 确认删除照片文件
 */
async function confirmDeletePhotoFile(filePath) {
    if (confirm('确定要删除这张照片吗？此操作不可撤销。')) {
        try {
            const response = await fetch('/api/photos/delete-file', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ filePath: filePath })
            });
            
            const data = await response.json();
            
            if (data.success) {
                showSuccess('照片删除成功');
                loadPhotos(); // 重新加载照片列表
            } else {
                showError('删除照片失败: ' + data.error);
            }
        } catch (error) {
            console.error('删除照片失败:', error);
            showError('删除照片失败: ' + error.message);
        }
    }
}

/**
 * 确认删除照片
 */
function confirmDeletePhoto(photoId) {
    if (confirm('确定要删除这张照片吗？此操作不可撤销。')) {
        deletePhotoById(photoId);
    }
}

/**
 * 删除照片（从模态框调用）
 */
async function deletePhoto() {
    if (!window.currentPhotoId) {
        showError('没有选中的照片');
        return;
    }
    
    if (!confirm('确定要删除这张照片吗？此操作不可撤销。')) {
        return;
    }
    
    try {
        let success = false;
        
        // 判断 currentPhotoId 是文件路径还是数字ID
        if (typeof window.currentPhotoId === 'string' && window.currentPhotoId.includes('/')) {
            // 文件路径，使用文件删除API
            const response = await fetch('/api/photos/delete-file', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ filePath: window.currentPhotoId })
            });
            const data = await response.json();
            if (data.success) {
                success = true;
                showSuccess('照片删除成功');
            } else {
                showError('删除照片失败: ' + (data.error || '未知错误'));
            }
        } else {
            // 数字ID，使用原有的删除API
            const response = await fetch(`/api/photos/${window.currentPhotoId}`, {
                method: 'DELETE'
            });
            const data = await response.json();
            if (data.success) {
                success = true;
                showSuccess('照片删除成功');
            } else {
                showError('删除照片失败: ' + (data.error || '未知错误'));
            }
        }
        
        if (success) {
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
            
            // 重新加载照片列表
            loadPhotos();
        }
    } catch (error) {
        console.error('删除照片失败:', error);
        showError('删除照片失败: ' + error.message);
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
    window.currentPage = 1;
    // 搜索表示“扩大范围”：从 recent 切换到全量扫描
    if (hasActiveFilters()) {
        loadPhotos();
        return;
    }
    applyPhotoFilters();
}

/**
 * 清空过滤器
 */
function clearFilters() {
    document.getElementById('productSerialFilter').value = '';
    document.getElementById('processStepFilter').value = '';
    const projectFilter = document.getElementById('projectFilter');
    if (projectFilter) projectFilter.value = '';
    const productTypeFilter = document.getElementById('productTypeFilter');
    if (productTypeFilter) productTypeFilter.value = '';
    const uploaderFilter = document.getElementById('uploaderFilter');
    if (uploaderFilter) uploaderFilter.value = '';
    document.getElementById('dateFromFilter').value = '';
    document.getElementById('dateToFilter').value = '';
    window.currentPage = 1;
    // 回到默认 recent 视图
    loadPhotos();
}

/**
 * 刷新照片
 */
function refreshPhotos() {
    loadPhotos();
}

/**
 * 更新分页
 */
function updatePagination() {
    if (getPhotoViewMode() !== 'grid') {
        // 分组视图不需要分页
        document.getElementById('pagination').innerHTML = '';
        return;
    }
    
    const totalPages = Math.ceil(currentPhotos.length / photosPerPage);
    const pagination = document.getElementById('pagination');
    
    if (totalPages <= 1) {
        pagination.innerHTML = '';
        return;
    }
    
    let paginationHTML = '';
    
    // 上一页
    paginationHTML += `
        <li class="page-item ${(window.currentPage || 1) === 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="changePage(${(window.currentPage || 1) - 1})">上一页</a>
        </li>
    `;
    
    // 页码
    const startPage = Math.max(1, (window.currentPage || 1) - 2);
    const endPage = Math.min(totalPages, (window.currentPage || 1) + 2);
    
    if (startPage > 1) {
        paginationHTML += `<li class="page-item"><a class="page-link" href="#" onclick="changePage(1)">1</a></li>`;
        if (startPage > 2) {
            paginationHTML += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
    }
    
    for (let i = startPage; i <= endPage; i++) {
        paginationHTML += `
            <li class="page-item ${i === (window.currentPage || 1) ? 'active' : ''}">
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
        <li class="page-item ${(window.currentPage || 1) === totalPages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="changePage(${(window.currentPage || 1) + 1})">下一页</a>
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
        window.currentPage = page;
        displayPhotos();
    }
}

function changeGroupBy(groupBy) {
    if (groupBy !== 'product' && groupBy !== 'process' && groupBy !== 'date') {
        groupBy = 'date'; // 默认使用日期分组
    }
    window.currentGroupBy = groupBy;
    
    // 更新下拉选择器的值
    const groupBySelect = document.getElementById('groupBySelect');
    if (groupBySelect) {
        groupBySelect.value = groupBy;
    }
    
    loadPhotoStatistics();
    if (typeof window.displayPhotosGrouped === 'function') {
        window.displayPhotosGrouped(currentPhotos);
    }
}

/**
 * 显示加载状态
 */
function showLoading() {
    const html = `
      <div class="loading">
          <div class="spinner-border" role="status">
              <span class="visually-hidden">加载中...</span>
          </div>
          <p>正在加载照片...</p>
      </div>
    `;

    const grid = document.getElementById('photoContainer');
    const grouped = document.getElementById('photoGroupedContainer');
    if (grid) grid.innerHTML = html;
    if (grouped) grouped.innerHTML = html;
}

/**
 * 显示成功消息
 */
function showSuccess(message) {
    alert(message);
}

/**
 * 显示错误消息
 */
function showError(message) {
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

function formatDateKey(timestamp) {
    const date = new Date(timestamp);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}${month}${day}`;
}


/**
 * 处理图片加载错误（包括缓存错误）
 * 实现重试机制和缓存清除
 */
function handleImageError(img, originalUrl) {
    const retryCount = parseInt(img.getAttribute('data-retry-count') || '0');
    
    // 第一次失败：尝试添加时间戳清除缓存
    if (retryCount === 0) {
        console.log('图片加载失败，尝试清除缓存重试:', originalUrl);
        img.setAttribute('data-retry-count', '1');
        // 添加时间戳参数清除浏览器缓存
        const separator = originalUrl.includes('?') ? '&' : '?';
        img.src = originalUrl + separator + '_t=' + Date.now();
        return;
    }
    
    // 第二次失败：尝试使用原图URL
    if (retryCount === 1 && img.hasAttribute('data-original-url')) {
        console.log('缩略图加载失败，尝试加载原图:', img.getAttribute('data-original-url'));
        img.setAttribute('data-retry-count', '2');
        const originalImgUrl = img.getAttribute('data-original-url');
        const separator = originalImgUrl.includes('?') ? '&' : '?';
        img.src = originalImgUrl + separator + '_t=' + Date.now();
        return;
    }
    
    // 所有重试都失败：显示占位图
    console.error('图片加载完全失败:', originalUrl);
    img.src = '/static/images/no-image.png';
    img.setAttribute('data-retry-count', '3');
}

/**
 * 清除浏览器缓存并重新加载照片
 */
function clearCacheAndReload() {
    if (confirm('这将清除浏览器缓存并重新加载页面。是否继续？')) {
        // 清除 Service Worker 缓存（如果有）
        if ('caches' in window) {
            caches.keys().then(function(names) {
                for (let name of names) {
                    caches.delete(name);
                }
            });
        }
        
        // 硬刷新页面
        window.location.reload(true);
    }
}
