(() => {
    const reportSamples = [
        {
            id: 'vr-001',
            title: '端盖压装稳定性分析',
            project: 'LIUZHIYU-MES',
            type: '质量分析报告',
            status: 'published',
            statusLabel: '已发布',
            version: 'V1.2',
            range: '2026-04-01 ~ 2026-04-07',
            updated: '2026-04-08 09:30',
            summary: '本周端盖压装良率整体稳定，三号线在周三出现短时波动，建议在换班节点增加首件确认。',
            tags: ['端盖压装', '良率稳定', '三号线关注'],
            checklist: ['导入原始报告', '提取关键指标', '生成趋势摘要', '输出建议动作'],
            bars: [64, 72, 58, 88, 76],
            barLabels: ['周一', '周二', '周三', '周四', '周五']
        },
        {
            id: 'vr-002',
            title: '装配效率趋势周报',
            project: 'QRMES-试产项目',
            type: '生产趋势报告',
            status: 'draft',
            statusLabel: '草稿',
            version: 'V0.9',
            range: '2026-03-28 ~ 2026-04-08',
            updated: '2026-04-08 11:15',
            summary: '装配节拍较上周期提升 6.2%，但夜班切换时段仍存在明显等待损耗，适合后续补充工位对比图。',
            tags: ['装配效率', '节拍提升', '夜班切换'],
            checklist: ['选择周期范围', '导入节拍数据', '匹配工序节点', '生成趋势图'],
            bars: [48, 55, 63, 71, 79],
            barLabels: ['工位1', '工位2', '工位3', '工位4', '工位5']
        },
        {
            id: 'vr-003',
            title: '异常批次追踪报告',
            project: '电机装配示范线',
            type: '异常追踪报告',
            status: 'published',
            statusLabel: '已发布',
            version: 'V2.0',
            range: '2026-04-03 ~ 2026-04-08',
            updated: '2026-04-08 14:20',
            summary: '异常批次已定位到来料尺寸波动与二次装夹偏差，建议把来料批次维度也加入后续可视化筛选。',
            tags: ['异常追踪', '来料波动', '装夹偏差'],
            checklist: ['筛选异常批次', '关联工单与设备', '抽取异常节点', '输出闭环建议'],
            bars: [30, 44, 66, 52, 40],
            barLabels: ['来料', '首检', '过程', '复检', '结案']
        }
    ];

    const tabButtons = Array.from(document.querySelectorAll('[data-vr-tab]'));
    const tabPanels = Array.from(document.querySelectorAll('[data-vr-panel]'));
    const fileInput = document.getElementById('vr-file-input');
    const fileName = document.getElementById('vr-file-name');
    const reportList = document.getElementById('vr-report-list');
    const previewTitle = document.getElementById('vr-preview-title');
    const previewSummary = document.getElementById('vr-preview-summary');
    const metaList = document.getElementById('vr-meta-list');
    const chipWrap = document.getElementById('vr-chip-wrap');
    const checklist = document.getElementById('vr-checklist');
    const chart = document.getElementById('vr-chart');
    const chartLabels = document.getElementById('vr-chart-labels');
    const searchInput = document.getElementById('vr-search');
    const typeFilter = document.getElementById('vr-filter-type');
    const statusFilter = document.getElementById('vr-filter-status');
    const resetButton = document.getElementById('vr-reset-filter');

    let activeReportId = reportSamples[0] ? reportSamples[0].id : null;

    function setActiveTab(tabName) {
        tabButtons.forEach((button) => {
            button.classList.toggle('is-active', button.dataset.vrTab === tabName);
        });

        tabPanels.forEach((panel) => {
            panel.classList.toggle('is-active', panel.dataset.vrPanel === tabName);
        });
    }

    function renderPreview(report) {
        if (!report) {
            previewTitle.textContent = '请选择左侧报告';
            previewSummary.textContent = '选中报告后，这里会显示摘要、标签、关键指标和图表示意。';
            metaList.innerHTML = '<div class="vr-meta-item">暂无数据</div>';
            chipWrap.innerHTML = '<span class="vr-chip">待选择</span>';
            checklist.innerHTML = '<div class="vr-step-item">暂无步骤</div>';
            chart.innerHTML = '';
            chartLabels.innerHTML = '';
            return;
        }

        previewTitle.textContent = report.title;
        previewSummary.textContent = report.summary;

        metaList.innerHTML = [
            `<div class="vr-meta-item"><strong>项目：</strong>${report.project}</div>`,
            `<div class="vr-meta-item"><strong>类型：</strong>${report.type}</div>`,
            `<div class="vr-meta-item"><strong>版本：</strong>${report.version}</div>`,
            `<div class="vr-meta-item"><strong>周期：</strong>${report.range}</div>`,
            `<div class="vr-meta-item"><strong>状态：</strong>${report.statusLabel}</div>`,
            `<div class="vr-meta-item"><strong>更新时间：</strong>${report.updated}</div>`
        ].join('');

        chipWrap.innerHTML = report.tags
            .map((tag) => `<span class="vr-chip">${tag}</span>`)
            .join('');

        checklist.innerHTML = report.checklist
            .map((item, index) => `<div class="vr-step-item"><span class="vr-step-index">${index + 1}</span>${item}</div>`)
            .join('');

        chart.innerHTML = report.bars
            .map((value) => `<div class="vr-bar" style="height: ${Math.max(value, 22)}%;" data-value="${value}%"></div>`)
            .join('');

        chartLabels.innerHTML = report.barLabels
            .map((label) => `<div>${label}</div>`)
            .join('');
    }

    function getFilteredReports() {
        const keyword = (searchInput.value || '').trim().toLowerCase();
        const type = typeFilter.value;
        const status = statusFilter.value;

        return reportSamples.filter((report) => {
            const matchesKeyword = !keyword || [
                report.title,
                report.project,
                report.type,
                ...report.tags
            ].join(' ').toLowerCase().includes(keyword);

            const matchesType = !type || report.type === type;
            const matchesStatus = !status || report.status === status;

            return matchesKeyword && matchesType && matchesStatus;
        });
    }

    function renderReportList() {
        if (!reportList) {
            return;
        }

        const reports = getFilteredReports();
        if (!reports.length) {
            reportList.innerHTML = '<div class="vr-empty">没有匹配的报告，请调整筛选条件。</div>';
            renderPreview(null);
            return;
        }

        if (!reports.some((report) => report.id === activeReportId)) {
            activeReportId = reports[0].id;
        }

        reportList.innerHTML = reports.map((report) => {
            const badgeClass = report.status === 'draft' ? 'vr-badge draft' : 'vr-badge';
            const activeClass = report.id === activeReportId ? 'is-active' : '';
            return `
                <article class="vr-report-item ${activeClass}" data-report-id="${report.id}">
                    <div class="vr-report-top">
                        <div class="vr-report-title">${report.title}</div>
                        <span class="${badgeClass}">${report.statusLabel}</span>
                    </div>
                    <div class="vr-report-meta">
                        <span>${report.project}</span>
                        <span>${report.type}</span>
                        <span>${report.version}</span>
                    </div>
                    <div class="vr-report-summary">${report.summary}</div>
                </article>
            `;
        }).join('');

        reportList.querySelectorAll('[data-report-id]').forEach((item) => {
            item.addEventListener('click', () => {
                activeReportId = item.dataset.reportId;
                renderReportList();
            });
        });

        renderPreview(reports.find((report) => report.id === activeReportId));
    }

    tabButtons.forEach((button) => {
        button.addEventListener('click', () => setActiveTab(button.dataset.vrTab));
    });

    if (fileInput && fileName) {
        fileInput.addEventListener('change', () => {
            const selected = fileInput.files && fileInput.files[0];
            fileName.textContent = selected ? `已选择：${selected.name}` : '未选择文件';
        });
    }

    [searchInput, typeFilter, statusFilter].forEach((element) => {
        if (element) {
            element.addEventListener('input', renderReportList);
            element.addEventListener('change', renderReportList);
        }
    });

    if (resetButton) {
        resetButton.addEventListener('click', () => {
            searchInput.value = '';
            typeFilter.value = '';
            statusFilter.value = '';
            activeReportId = reportSamples[0] ? reportSamples[0].id : null;
            renderReportList();
        });
    }

    renderReportList();
})();
