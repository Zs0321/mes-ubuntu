/* global window, document */
(function initStorageCheckPage() {
    "use strict";

    const projectId = String(window.MOTOR_QC_STORAGE_PROJECT_ID || "").trim();
    const api = window.motorQCAPI || new window.MotorQCAPIClient();

    function esc(value) {
        const div = document.createElement("div");
        div.textContent = value == null ? "" : String(value);
        return div.innerHTML;
    }

    function formatTime(value) {
        if (!value) {
            return "-";
        }
        const dt = new Date(value);
        if (Number.isNaN(dt.getTime())) {
            return String(value);
        }
        return dt.toLocaleString("zh-CN");
    }

    function setHint(text) {
        const node = document.getElementById("storage-page-hint");
        if (node) {
            node.textContent = text || "";
        }
    }

    function readFilters() {
        return {
            serial: (document.getElementById("storage-filter-serial").value || "").trim(),
            process: (document.getElementById("storage-filter-process").value || "").trim(),
            status: (document.getElementById("storage-filter-status").value || "").trim(),
        };
    }

    function setSummary(id, value) {
        const node = document.getElementById(id);
        if (node) {
            node.textContent = String(value == null ? 0 : value);
        }
    }

    function renderStatusBreakdown(statusCounts) {
        const node = document.getElementById("storage-status-breakdown");
        if (!node) {
            return;
        }
        const counts = statusCounts || {};
        const labels = {
            pending: "待识别",
            running: "识别中",
            review: "待确认",
            confirmed: "已确认",
            failed: "失败",
        };
        const parts = Object.keys(labels)
            .map((key) => `${labels[key]}: ${Number(counts[key] || 0)}`)
            .join(" / ");
        node.textContent = parts || "";
    }

    function renderRows(rows) {
        const body = document.getElementById("storage-result-body");
        if (!body) {
            return;
        }
        const data = Array.isArray(rows) ? rows : [];
        if (!data.length) {
            body.innerHTML = '<tr><td colspan="8" class="muted">无匹配数据</td></tr>';
            return;
        }
        body.innerHTML = data.map((row) => `
            <tr>
                <td class="mono">${esc(row.serial_number || "-")}</td>
                <td>${esc(row.process_name || "-")}</td>
                <td>${esc(row.status || "-")}</td>
                <td>${Number(row.photo_total || 0)}</td>
                <td>${Number(row.photo_analyzed || 0)}</td>
                <td>${Number(row.photo_pending || 0)}</td>
                <td>${esc(formatTime(row.last_analyzed_at))}</td>
                <td>${esc(formatTime(row.updated_at))}</td>
            </tr>
        `).join("");
    }

    function renderSerialOptions(serials) {
        const list = document.getElementById("storage-serial-options");
        if (!list) {
            return;
        }
        const values = Array.isArray(serials) ? serials : [];
        const unique = [...new Set(values.map((v) => String(v || "").trim()).filter(Boolean))];
        list.innerHTML = unique.map((item) => `<option value="${esc(item)}"></option>`).join("");
    }

    async function loadSerialOptions() {
        if (!projectId) {
            return;
        }
        try {
            const filters = readFilters();
            const data = await api.getProjectTaskOptions(projectId, {
                serial: filters.serial,
                process: filters.process,
                status: filters.status,
                q_serial: filters.serial,
                limit: 250,
            });
            renderSerialOptions(data.serial_numbers || []);
        } catch (_err) {
            // 不阻塞主流程
        }
    }

    async function loadStorage() {
        if (!projectId) {
            return;
        }
        const filters = readFilters();
        setHint("加载中...");
        try {
            const data = await api.getProjectStorageCheck(projectId, {
                serial: filters.serial,
                process: filters.process,
                status: filters.status,
                limit: 300,
            });
            const summary = data.summary || {};
            setSummary("storage-task-total", summary.task_total || 0);
            setSummary("storage-photo-total", summary.photo_total || 0);
            setSummary("storage-photo-analyzed", summary.photo_analyzed || 0);
            setSummary("storage-photo-pending", summary.photo_pending || 0);
            const lastNode = document.getElementById("storage-last-analyzed");
            if (lastNode) {
                lastNode.textContent = formatTime(summary.last_analyzed_at);
            }
            renderStatusBreakdown(summary.status_counts || {});
            renderRows(data.rows || []);
            const rows = Array.isArray(data.rows) ? data.rows.length : 0;
            setHint(`已加载 ${rows} 条明细`);
            await loadSerialOptions();
        } catch (err) {
            setHint(`加载失败: ${err.message || err}`);
        }
    }

    function bindEvents() {
        const searchBtn = document.getElementById("storage-search-btn");
        const resetBtn = document.getElementById("storage-reset-btn");
        const refreshBtn = document.getElementById("storage-refresh-btn");
        const serialInput = document.getElementById("storage-filter-serial");

        if (searchBtn) {
            searchBtn.addEventListener("click", () => loadStorage());
        }
        if (refreshBtn) {
            refreshBtn.addEventListener("click", () => loadStorage());
        }
        if (resetBtn) {
            resetBtn.addEventListener("click", async () => {
                document.getElementById("storage-filter-serial").value = "";
                document.getElementById("storage-filter-process").value = "";
                document.getElementById("storage-filter-status").value = "";
                await loadStorage();
            });
        }
        if (serialInput) {
            serialInput.addEventListener("input", () => {
                window.clearTimeout(bindEvents._timer);
                bindEvents._timer = window.setTimeout(loadSerialOptions, 220);
            });
        }
    }

    bindEvents();
    loadStorage();
})();
