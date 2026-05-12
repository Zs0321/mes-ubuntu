(function () {
  const linkedOptions = {
    projects: [],
  };
  const scopedSerialCache = new Map();

  function qs(id) {
    return document.getElementById(id);
  }

  function uniquePush(arr, value) {
    if (!value) return;
    if (!arr.includes(value)) arr.push(value);
  }

  function replaceSelectOptions(selectId, values, placeholderText) {
    const select = qs(selectId);
    const previous = select.value;

    select.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = placeholderText;
    select.appendChild(placeholder);

    for (const value of values) {
      const opt = document.createElement('option');
      opt.value = value;
      opt.textContent = value;
      select.appendChild(opt);
    }

    if (previous && values.includes(previous)) {
      select.value = previous;
    }
  }

  function replaceDatalistOptions(datalistId, values) {
    const list = qs(datalistId);
    if (!list) return;
    list.innerHTML = '';
    for (const value of values) {
      const opt = document.createElement('option');
      opt.value = value;
      list.appendChild(opt);
    }
  }

  function getProjectByName(name) {
    return linkedOptions.projects.find((p) => p && p.name === name) || null;
  }

  function getAllProjectNames() {
    return linkedOptions.projects
      .map((p) => (p && p.name ? p.name : ''))
      .filter(Boolean);
  }

  function getProductTypes(projectName) {
    const all = [];

    if (projectName) {
      const project = getProjectByName(projectName);
      if (!project) return all;
      for (const productType of project.productTypes || []) {
        uniquePush(all, productType.name);
      }
      return all;
    }

    for (const project of linkedOptions.projects) {
      for (const productType of project.productTypes || []) {
        uniquePush(all, productType.name);
      }
    }
    return all;
  }

  function getProcessNames(projectName, productTypeName) {
    if (!projectName || !productTypeName) {
      return [];
    }
    const all = [];
    const projects = [getProjectByName(projectName)].filter(Boolean);

    for (const project of projects) {
      for (const productType of project.productTypes || []) {
        if (productTypeName && productType.name !== productTypeName) continue;
        for (const processName of productType.processSteps || []) {
          uniquePush(all, processName);
        }
      }
    }

    return all;
  }

  function buildScopeKey(projectName, productTypeName) {
    return `${projectName || ''}::${productTypeName || ''}`;
  }

  async function loadScopedSerialOptions(projectName, productTypeName) {
    if (!projectName || !productTypeName) {
      return [];
    }

    const key = buildScopeKey(projectName, productTypeName);
    if (scopedSerialCache.has(key)) {
      return scopedSerialCache.get(key) || [];
    }

    const params = new URLSearchParams();
    params.set('projectName', projectName);
    params.set('productType', productTypeName);

    const resp = await fetch(`/api/documents/options?${params.toString()}`, { method: 'GET' });
    if (!resp.ok) {
      const t = await resp.text();
      throw new Error(`加载序列号选项失败: HTTP ${resp.status} ${t}`);
    }

    const data = await resp.json();
    const options = data.options || {};
    const serials = Array.isArray(options.serialNumbers) ? options.serialNumbers : [];
    scopedSerialCache.set(key, serials);
    return serials;
  }

  async function refreshUploadLinkage() {
    const projectName = (qs('uploadProject').value || '').trim();
    const productTypes = getProductTypes(projectName);
    replaceSelectOptions('uploadProductType', productTypes, '请选择产品类型');

    const uploadProductType = qs('uploadProductType');
    if (!uploadProductType.value && productTypes.length > 0) {
      uploadProductType.value = productTypes[0];
    }

    const processNames = getProcessNames(projectName, uploadProductType.value || '');
    const uploadProcessPlaceholder = processNames.length > 0 ? '请选择工序' : '该产品类型无 PDF 工序';
    replaceSelectOptions('uploadProcess', processNames, uploadProcessPlaceholder);
    const uploadProcess = qs('uploadProcess');
    uploadProcess.disabled = processNames.length === 0;
    if (!uploadProcess.value && processNames.length > 0) {
      uploadProcess.value = processNames[0];
    }

    const scopedSerials = await loadScopedSerialOptions(projectName, uploadProductType.value || '');
    replaceDatalistOptions('uploadSerialList', scopedSerials);
  }

  async function refreshFilterLinkage() {
    const projectName = (qs('filterProject').value || '').trim();
    const productTypes = getProductTypes(projectName);
    replaceSelectOptions('filterProductType', productTypes, '全部产品类型');

    const selectedProductType = (qs('filterProductType').value || '').trim();
    const processNames = getProcessNames(projectName, selectedProductType);
    replaceSelectOptions('filterProcess', processNames, '全部工序');
    qs('filterProcess').disabled = processNames.length === 0;

    const scopedSerials = await loadScopedSerialOptions(projectName, selectedProductType);
    replaceDatalistOptions('filterSerialList', scopedSerials);
  }

  async function applyLinkedOptions() {
    const projectNames = getAllProjectNames();
    replaceSelectOptions('uploadProject', projectNames, '请选择项目');
    replaceSelectOptions('filterProject', projectNames, '全部项目');

    const uploadProject = qs('uploadProject');
    if (!uploadProject.value && projectNames.length > 0) {
      uploadProject.value = projectNames[0];
    }

    await refreshUploadLinkage();
    await refreshFilterLinkage();
  }

  async function loadLinkedOptions() {
    const resp = await fetch('/api/documents/options', { method: 'GET' });
    if (!resp.ok) {
      const t = await resp.text();
      throw new Error(`加载联动选项失败: HTTP ${resp.status} ${t}`);
    }

    const data = await resp.json();
    const options = data.options || {};
    linkedOptions.projects = Array.isArray(options.projects) ? options.projects : [];
    scopedSerialCache.clear();
    await applyLinkedOptions();
  }

  async function safeLoadLinkedOptions() {
    try {
      await loadLinkedOptions();
    } catch (err) {
      if (typeof window.showMessage === 'function') {
        window.showMessage(String(err.message || err), 'error');
      }
    }
  }

  async function loadDocuments() {
    const params = new URLSearchParams();
    const projectName = (qs('filterProject').value || '').trim();
    const productType = (qs('filterProductType').value || '').trim();
    const productSerial = (qs('filterSerial').value || '').trim();
    const processName = (qs('filterProcess').value || '').trim();

    if (projectName) params.set('projectName', projectName);
    if (productType) params.set('productType', productType);
    if (productSerial) params.set('productSerial', productSerial);
    if (processName) params.set('processName', processName);

    const url = '/api/documents/list' + (params.toString() ? `?${params.toString()}` : '');
    const resp = await fetch(url, { method: 'GET' });
    if (!resp.ok) {
      const t = await resp.text();
      throw new Error(`加载文档失败: HTTP ${resp.status} ${t}`);
    }

    const data = await resp.json();
    renderDocuments(Array.isArray(data.documents) ? data.documents : []);
  }

  function resetReportStatus(message) {
    const section = qs('reportStatusSection');
    const hint = qs('reportStatusHint');
    const table = qs('reportStatusTable');
    const tbody = qs('reportStatusBody');

    section.style.display = 'block';
    qs('statusTotal').textContent = '0';
    qs('statusUploaded').textContent = '0';
    qs('statusMissing').textContent = '0';

    tbody.innerHTML = '';
    table.style.display = 'none';
    hint.style.display = 'block';
    hint.textContent = message || '请选择项目和产品类型后点击“查询”查看状态';
  }

  async function loadReportStatus() {
    const projectName = (qs('filterProject').value || '').trim();
    const productType = (qs('filterProductType').value || '').trim();
    const processName = (qs('filterProcess').value || '').trim();

    if (!projectName || !productType) {
      resetReportStatus('请选择项目和产品类型后点击“查询”查看状态');
      return;
    }

    const params = new URLSearchParams();
    params.set('projectName', projectName);
    params.set('productType', productType);
    if (processName) params.set('processName', processName);

    const resp = await fetch(`/api/documents/report-status?${params.toString()}`, { method: 'GET' });
    if (!resp.ok) {
      const t = await resp.text();
      throw new Error(`加载报告状态失败: HTTP ${resp.status} ${t}`);
    }

    const data = await resp.json();
    renderReportStatus(data);
  }

  function renderReportStatus(payload) {
    const section = qs('reportStatusSection');
    const hint = qs('reportStatusHint');
    const table = qs('reportStatusTable');
    const tbody = qs('reportStatusBody');

    section.style.display = 'block';
    qs('statusTotal').textContent = String(payload.totalSerials ?? 0);
    qs('statusUploaded').textContent = String(payload.uploadedSerials ?? 0);
    qs('statusMissing').textContent = String(payload.missingSerials ?? 0);

    const statuses = Array.isArray(payload.statuses) ? payload.statuses.slice() : [];
    if (!statuses.length) {
      tbody.innerHTML = '';
      table.style.display = 'none';
      hint.style.display = 'block';
      hint.textContent = '未找到该项目/产品类型的序列号';
      return;
    }

    statuses.sort((a, b) => {
      const av = a.hasReport ? 1 : 0;
      const bv = b.hasReport ? 1 : 0;
      if (av !== bv) return av - bv; // 红色(未上传)优先
      return String(a.serialNumber || '').localeCompare(String(b.serialNumber || ''), 'zh-CN');
    });

    tbody.innerHTML = statuses.map((item, idx) => `
      <tr>
        <td>${idx + 1}</td>
        <td>${escapeHtml(item.serialNumber || '-')}</td>
        <td>
          <span class="status-badge ${item.hasReport ? 'status-ok' : 'status-missing'}">
            ${item.hasReport ? '已上传' : '未上传'}
          </span>
        </td>
        <td>${item.reportCount || 0}</td>
        <td>${formatDate(item.latestModified || '')}</td>
      </tr>
    `).join('');

    hint.style.display = 'none';
    table.style.display = 'table';
  }

  function renderDocuments(documents) {
    const tbody = qs('documentsBody');
    const emptyHint = qs('emptyHint');
    tbody.innerHTML = '';

    if (!documents.length) {
      emptyHint.style.display = 'block';
      return;
    }
    emptyHint.style.display = 'none';

    for (const doc of documents) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escapeHtml(doc.filename || '')}</td>
        <td>${escapeHtml(doc.projectName || '-')}</td>
        <td>${escapeHtml(doc.productType || '-')}</td>
        <td>${escapeHtml(doc.productSerial || '-')}</td>
        <td>${escapeHtml(doc.processName || '-')}</td>
        <td>${formatSize(doc.size || 0)}</td>
        <td>${formatDate(doc.modified || '')}</td>
        <td>
          <button class="btn btn-secondary" style="padding:0.35rem 0.8rem; font-size:0.85rem;" data-action="view" data-path="${encodeAttr(doc.path || '')}">查看</button>
          <button class="btn btn-primary" style="padding:0.35rem 0.8rem; font-size:0.85rem;" data-action="download" data-path="${encodeAttr(doc.path || '')}">下载</button>
          <button class="btn btn-danger" style="padding:0.35rem 0.8rem; font-size:0.85rem;" data-action="delete" data-path="${encodeAttr(doc.path || '')}">删除</button>
        </td>
      `;
      tbody.appendChild(tr);
    }

    tbody.querySelectorAll('button[data-action="view"]').forEach((btn) => {
      btn.addEventListener('click', () => viewDoc(btn.getAttribute('data-path') || ''));
    });
    tbody.querySelectorAll('button[data-action="download"]').forEach((btn) => {
      btn.addEventListener('click', () => downloadDoc(btn.getAttribute('data-path') || ''));
    });
    tbody.querySelectorAll('button[data-action="delete"]').forEach((btn) => {
      btn.addEventListener('click', () => deleteDoc(btn.getAttribute('data-path') || ''));
    });
  }

  async function loadStats() {
    const resp = await fetch('/api/documents/stats', { method: 'GET' });
    if (!resp.ok) {
      const t = await resp.text();
      throw new Error(`加载统计失败: HTTP ${resp.status} ${t}`);
    }
    const data = await resp.json();
    qs('statTotal').textContent = String(data.total_documents ?? 0);
    qs('statSize').textContent = formatSize(data.total_size_bytes ?? 0);
  }

  function downloadDoc(path) {
    if (!path) return;
    window.location.href = `/api/documents/download/${path}`;
  }

  function viewDoc(path) {
    if (!path) return;
    window.open(`/api/documents/view/${path}`, '_blank', 'noopener');
  }

  async function deleteDoc(path) {
    if (!path) return;
    if (!confirm('确定要删除这个文档吗？')) return;

    const resp = await fetch(`/api/documents/delete/${path}`, { method: 'DELETE' });
    if (!resp.ok) {
      const t = await resp.text();
      throw new Error(`删除失败: HTTP ${resp.status} ${t}`);
    }

    if (typeof window.showMessage === 'function') {
      window.showMessage('删除成功', 'success');
    }

    await loadDocuments();
    await loadStats();
    await safeLoadLinkedOptions();
  }

  async function uploadPdf(e) {
    e.preventDefault();

    const fileEl = qs('uploadFile');
    const file = fileEl.files && fileEl.files[0];
    if (!file) throw new Error('请选择 PDF 文件');

    const form = new FormData();
    form.append('file', file);
    form.append('projectName', (qs('uploadProject').value || '').trim());
    form.append('productType', (qs('uploadProductType').value || '').trim());
    form.append('productSerial', (qs('uploadSerial').value || '').trim());
    form.append('processName', (qs('uploadProcess').value || '').trim());

    const resp = await fetch('/api/documents/upload', {
      method: 'POST',
      body: form,
    });

    if (!resp.ok) {
      const t = await resp.text();
      throw new Error(`上传失败: HTTP ${resp.status} ${t}`);
    }

    if (typeof window.showMessage === 'function') {
      window.showMessage('上传成功', 'success');
    }

    qs('uploadForm').reset();
    await safeLoadLinkedOptions();
    await loadDocuments();
    await loadStats();
  }

  function formatSize(bytes) {
    const n = Number(bytes) || 0;
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(2)} KB`;
    if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(2)} MB`;
    return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }

  function formatDate(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleString('zh-CN');
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function encodeAttr(s) {
    return escapeHtml(s).replaceAll('`', '');
  }

  function init() {
    qs('uploadProject').addEventListener('change', () => {
      refreshUploadLinkage().catch((err) => {
        if (typeof window.showMessage === 'function') {
          window.showMessage(String(err.message || err), 'error');
        }
      });
    });
    qs('uploadProductType').addEventListener('change', () => {
      refreshUploadLinkage().catch((err) => {
        if (typeof window.showMessage === 'function') {
          window.showMessage(String(err.message || err), 'error');
        }
      });
    });
    qs('filterProject').addEventListener('change', () => {
      refreshFilterLinkage().catch((err) => {
        if (typeof window.showMessage === 'function') {
          window.showMessage(String(err.message || err), 'error');
        }
      });
      resetReportStatus('筛选已变化，请点击“查询”刷新状态');
    });
    qs('filterProductType').addEventListener('change', () => {
      refreshFilterLinkage().catch((err) => {
        if (typeof window.showMessage === 'function') {
          window.showMessage(String(err.message || err), 'error');
        }
      });
      resetReportStatus('筛选已变化，请点击“查询”刷新状态');
    });

    qs('filterForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        await Promise.all([loadDocuments(), loadReportStatus()]);
      } catch (err) {
        if (typeof window.showMessage === 'function') {
          window.showMessage(String(err.message || err), 'error');
        }
      }
    });

    qs('uploadForm').addEventListener('submit', async (e) => {
      try {
        await uploadPdf(e);
      } catch (err) {
        if (typeof window.showMessage === 'function') {
          window.showMessage(String(err.message || err), 'error');
        }
      }
    });

    qs('uploadResetBtn').addEventListener('click', () => {
      qs('uploadForm').reset();
      applyLinkedOptions().catch((err) => {
        if (typeof window.showMessage === 'function') {
          window.showMessage(String(err.message || err), 'error');
        }
      });
    });

    (async () => {
      await safeLoadLinkedOptions();
      try {
        await loadDocuments();
        await loadStats();
        resetReportStatus();
      } catch (err) {
        if (typeof window.showMessage === 'function') {
          window.showMessage(String(err.message || err), 'error');
        }
      }
    })();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
