/* global window, document */
(function initMotorQCTasksPage() {
    "use strict";

    const projectId = String(window.MOTOR_QC_TASK_PROJECT_ID || "").trim();
    const pageMode = String(window.MOTOR_QC_TASK_PAGE_MODE || "tasks").trim().toLowerCase();
    const initialView = String(window.MOTOR_QC_TASK_INITIAL_VIEW || "center").trim().toLowerCase();
    const reviewOnlyMode = pageMode === "manual_review";
    const api = window.motorQCAPI || new window.MotorQCAPIClient();

    const statusOrder = ["pending", "running", "review", "confirmed", "failed"];
    const statusLabels = {
        pending: "待识别",
        running: "识别中",
        review: "待确认",
        confirmed: "已确认",
        failed: "失败",
    };
    const statusAlias = {
        ok: "pass",
        qualified: "pass",
        ng: "fail",
        unqualified: "fail",
        error: "failed",
        todo: "pending",
    };

    const state = {
        tasks: [],
        expandedTaskIds: new Set(),
        detailByTaskId: Object.create(null),
        loadingDetailTaskIds: new Set(),
        pendingEditsByTaskId: Object.create(null),
        dirtyTaskIds: new Set(),
        autoRefreshEnabled: true,
        autoRefreshTimer: null,
        optionTimer: null,
        optionsLoading: false,
    };

    function esc(value) {
        const div = document.createElement("div");
        div.textContent = value == null ? "" : String(value);
        return div.innerHTML;
    }

    function normalizeStatus(value) {
        const raw = String(value || "").trim().toLowerCase();
        if (!raw) {
            return "pending";
        }
        return statusAlias[raw] || raw;
    }

    function statusLabel(value) {
        const normalized = normalizeStatus(value);
        return statusLabels[normalized] || normalized || "未检测";
    }

    function badgeClassForStatus(value) {
        const normalized = normalizeStatus(value);
        if (normalized === "pass" || normalized === "confirmed") {
            return "status-pass";
        }
        if (normalized === "fail" || normalized === "failed" || normalized === "review") {
            return "status-fail";
        }
        if (normalized === "running" || normalized === "ng") {
            return "status-ng";
        }
        return "status-pending";
    }

    function overdueClass(level) {
        if (level === "danger") {
            return "task-overdue-danger";
        }
        if (level === "warning") {
            return "task-overdue-warning";
        }
        return "";
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
        const hint = document.getElementById("task-page-hint");
        if (hint) {
            hint.textContent = text || "";
        }
    }

    function readFilters() {
        return {
            status: (document.getElementById("task-filter-status").value || "").trim(),
            serial: (document.getElementById("task-filter-serial").value || "").trim(),
            process: (document.getElementById("task-filter-process").value || "").trim(),
            productType: (document.getElementById("task-filter-product-type").value || "").trim(),
            dateFrom: (document.getElementById("task-filter-date-from").value || "").trim(),
            dateTo: (document.getElementById("task-filter-date-to").value || "").trim(),
            overdue: (document.getElementById("task-filter-overdue").value || "").trim(),
            ai: (document.getElementById("task-filter-ai") && document.getElementById("task-filter-ai").value || "").trim(),
        };
    }

    function resolveTaskAiStatus(task) {
        const bestResult = task && typeof task.best_result_json === "object" ? task.best_result_json : {};
        const aiStatus = normalizeStatus(
            bestResult.overall_status ||
            bestResult.status ||
            task.ai_overall_status ||
            ""
        );
        return aiStatus || "pending";
    }

    function applyOverdueFilter(tasks, overdue) {
        if (!overdue) {
            return tasks;
        }
        return tasks.filter((task) => String(task.overdue_level || "") === overdue);
    }

    function applyAiFilter(tasks, aiFilter) {
        const rawFilter = String(aiFilter || "").trim();
        if (!rawFilter) {
            return tasks;
        }
        const filter = normalizeStatus(rawFilter);
        return tasks.filter((task) => {
            const aiStatus = resolveTaskAiStatus(task);
            if (filter === "pass") {
                return aiStatus === "pass";
            }
            if (filter === "fail") {
                return aiStatus === "fail" || aiStatus === "ng" || aiStatus === "failed" || aiStatus === "review";
            }
            return aiStatus === filter;
        });
    }

    function getTaskById(taskId) {
        const id = Number(taskId) || 0;
        if (!id) {
            return null;
        }
        return state.tasks.find((task) => Number(task.id) === id) || null;
    }

    function ensurePendingEdit(taskId) {
        const id = Number(taskId) || 0;
        if (!id) {
            return null;
        }
        if (!state.pendingEditsByTaskId[id]) {
            state.pendingEditsByTaskId[id] = {
                detailStatusByKey: Object.create(null),
                notes: "",
            };
        }
        return state.pendingEditsByTaskId[id];
    }

    function getPendingEdit(taskId) {
        const id = Number(taskId) || 0;
        if (!id) {
            return null;
        }
        return state.pendingEditsByTaskId[id] || null;
    }

    function markTaskDirty(taskId, dirty) {
        const id = Number(taskId) || 0;
        if (!id) {
            return;
        }
        if (dirty) {
            state.dirtyTaskIds.add(id);
        } else {
            state.dirtyTaskIds.delete(id);
        }
    }

    function setSummaryCount(status, value) {
        const node = document.getElementById(`count-${status}`);
        if (!node) {
            return;
        }
        node.textContent = String(value || 0);
    }

    function updateSummary(tasks) {
        const counts = {
            pending: 0,
            running: 0,
            review: 0,
            confirmed: 0,
            failed: 0,
        };
        for (const task of tasks) {
            const key = normalizeStatus(task.status);
            if (counts[key] === undefined) {
                counts.failed += 1;
            } else {
                counts[key] += 1;
            }
        }
        setSummaryCount("pending", counts.pending);
        setSummaryCount("running", counts.running);
        setSummaryCount("review", counts.review);
        setSummaryCount("confirmed", counts.confirmed);
    }

    function updateAiSummary(tasks) {
        const aiCounts = { pass: 0, fail: 0 };
        for (const task of tasks) {
            const aiStatus = resolveTaskAiStatus(task);
            if (aiStatus === "pass") {
                aiCounts.pass += 1;
            } else if (aiStatus === "fail" || aiStatus === "ng" || aiStatus === "failed" || aiStatus === "review") {
                aiCounts.fail += 1;
            }
        }
        setSummaryCount("ai-pass", aiCounts.pass);
        setSummaryCount("ai-fail", aiCounts.fail);
    }

    function renderDatalist(targetId, values) {
        const list = document.getElementById(targetId);
        if (!list) {
            return;
        }
        const normalized = [];
        const seen = new Set();
        for (const item of values || []) {
            const v = String(item || "").trim();
            if (!v || seen.has(v)) {
                continue;
            }
            seen.add(v);
            normalized.push(v);
        }
        list.innerHTML = normalized.map((item) => `<option value="${esc(item)}"></option>`).join("");
    }

    async function loadTaskOptions() {
        if (!projectId || state.optionsLoading) {
            return;
        }
        state.optionsLoading = true;
        try {
            const filters = readFilters();
            if (filters.dateFrom && filters.dateTo && filters.dateFrom > filters.dateTo) {
                return;
            }
            const data = await api.getProjectTaskOptions(projectId, {
                status: filters.status,
                serial: filters.serial,
                process: filters.process,
                productType: filters.productType,
                dateFrom: filters.dateFrom,
                dateTo: filters.dateTo,
                q_serial: filters.serial,
                q_process: filters.process,
                q_product_type: filters.productType,
                limit: 180,
            });
            renderDatalist("task-serial-options", data.serial_numbers || []);
            renderDatalist("task-process-options", data.process_names || []);
            renderDatalist("task-product-type-options", data.product_types || []);
        } catch (_err) {
            // 筛选建议失败不阻塞主流程
        } finally {
            state.optionsLoading = false;
        }
    }

    function scheduleLoadTaskOptions() {
        if (state.optionTimer) {
            window.clearTimeout(state.optionTimer);
        }
        state.optionTimer = window.setTimeout(loadTaskOptions, 220);
    }

    function trimDetailCaches(tasks) {
        const keepIds = new Set(tasks.map((item) => Number(item.id) || 0));
        for (const key of Object.keys(state.detailByTaskId)) {
            const id = Number(key) || 0;
            if (!keepIds.has(id)) {
                delete state.detailByTaskId[key];
            }
        }
        for (const key of Object.keys(state.pendingEditsByTaskId)) {
            const id = Number(key) || 0;
            if (!keepIds.has(id)) {
                delete state.pendingEditsByTaskId[key];
                state.dirtyTaskIds.delete(id);
                state.expandedTaskIds.delete(id);
            }
        }
    }

    function autoExpandReviewTasks(tasks) {
        if (state.expandedTaskIds.size > 0) {
            return;
        }
        let picked = 0;
        for (const task of tasks) {
            if (normalizeStatus(task.status) !== "review") {
                continue;
            }
            const id = Number(task.id) || 0;
            if (!id) {
                continue;
            }
            state.expandedTaskIds.add(id);
            picked += 1;
            if (picked >= 6) {
                break;
            }
        }
    }

    function renderAiSummary(task) {
        const bestResult = task && typeof task.best_result_json === "object" ? task.best_result_json : {};
        const overallStatus = resolveTaskAiStatus(task) || normalizeStatus(task.status);
        const detailItems = Array.isArray(task && task.detail_items) ? task.detail_items : [];
        const summaryFromDetail = detailItems
            .map((item) => String(item.ai_reason || item.reason || "").trim())
            .find((text) => text.length > 0) || "";
        const summary = String(
            bestResult.summary ||
            bestResult.primary_reason ||
            summaryFromDetail ||
            bestResult.message ||
            task.error_message ||
            "等待识别或人工确认"
        ).trim();

        return `
            <div class="task-ai-summary">
                <span class="status-badge ${badgeClassForStatus(overallStatus)}">${esc(statusLabel(overallStatus))}</span>
                <span class="small">${esc(summary || "-")}</span>
            </div>
        `;
    }

    function renderTaskPhotos(task) {
        const photos = Array.isArray(task.photos) ? task.photos : [];
        if (!photos.length) {
            return '<div class="small muted">当前任务暂无照片</div>';
        }

        return `
            <div class="task-photo-grid">
                ${photos.map((photo) => {
                    const url = String(photo.view_url || "").trim();
                    const name = String(photo.photo_name || "照片").trim() || "照片";
                    if (!url) {
                        return `
                            <div class="task-photo-item task-photo-item-empty">
                                <div class="small muted">${esc(name)}</div>
                            </div>
                        `;
                    }
                    return `
                        <button
                            type="button"
                            class="task-photo-item"
                            data-open-photo="1"
                            data-photo-url="${esc(url)}"
                            data-photo-name="${esc(name)}"
                            title="点击放大查看"
                        >
                            <img src="${esc(url)}" alt="${esc(name)}" loading="lazy">
                            <span class="task-photo-caption">${esc(name)}</span>
                        </button>
                    `;
                }).join("")}
            </div>
        `;
    }

    function renderTaskDetailRows(task) {
        const detailItems = Array.isArray(task.detail_items) ? task.detail_items : [];
        if (!detailItems.length) {
            return '<div class="small muted">暂无可确认的细节项</div>';
        }
        const bestResult = task && typeof task.best_result_json === "object" ? task.best_result_json : {};
        const taskLevelReason = String(bestResult.primary_reason || bestResult.summary || "").trim();

        const photoById = Object.create(null);
        for (const photo of Array.isArray(task.photos) ? task.photos : []) {
            const id = Number(photo.id) || 0;
            if (id) {
                photoById[id] = photo;
            }
        }

        const pending = getPendingEdit(task.id);
        const pendingMap = (pending && pending.detailStatusByKey) || Object.create(null);

        return `
            <div class="task-detail-list">
                ${detailItems.map((item) => {
                    const detailKey = String(item.detail_key || "").trim();
                    const label = String(item.detail_label || detailKey || "未命名细节").trim();
                    const source = String(item.source || "-").trim();
                    const aiStatus = normalizeStatus(item.best_status || "pending");
                    const aiReason = String(item.ai_reason || item.reason || taskLevelReason || "").trim();
                    const selectedStatus = pendingMap[detailKey] !== undefined
                        ? String(pendingMap[detailKey] || "")
                        : String(item.confirmed_status || "").trim();

                    const bestPhoto = photoById[Number(item.best_photo_id) || 0] || null;
                    const previewUrl = String(item.best_photo_url || (bestPhoto && bestPhoto.view_url) || "").trim();
                    const previewName = String(item.best_photo_name || (bestPhoto && bestPhoto.photo_name) || "证据图").trim();

                    return `
                        <div class="task-detail-item" data-detail-key="${esc(detailKey)}">
                            <div class="task-detail-main">
                                <div class="task-detail-label">${esc(label)}</div>
                                <div class="small muted">来源: ${esc(source === "config" ? "配置项" : source)}</div>
                                <div class="small muted">AI结论: ${esc(aiReason || "AI未返回文本结论，仅给出状态，请人工确认")}</div>
                            </div>
                            <div class="task-detail-ai">
                                <span class="status-badge ${badgeClassForStatus(aiStatus)}">AI: ${esc(statusLabel(aiStatus))}</span>
                            </div>
                            <div class="task-detail-confirm">
                                <select class="task-detail-status" data-detail-key="${esc(detailKey)}">
                                    <option value="">未确认</option>
                                    <option value="pass" ${selectedStatus === "pass" ? "selected" : ""}>${reviewOnlyMode ? "识别正确(合格)" : "合格"}</option>
                                    <option value="fail" ${selectedStatus === "fail" ? "selected" : ""}>${reviewOnlyMode ? "识别错误(不合格)" : "不合格"}</option>
                                    <option value="pending" ${selectedStatus === "pending" ? "selected" : ""}>待确认</option>
                                </select>
                            </div>
                            <div class="task-detail-photo">
                                ${previewUrl ? `
                                    <button
                                        type="button"
                                        class="task-detail-photo-btn"
                                        data-open-photo="1"
                                        data-photo-url="${esc(previewUrl)}"
                                        data-photo-name="${esc(previewName)}"
                                    >
                                        <img src="${esc(previewUrl)}" alt="${esc(previewName)}" loading="lazy">
                                    </button>
                                ` : '<span class="small muted">无证据图</span>'}
                            </div>
                        </div>
                    `;
                }).join("")}
            </div>
        `;
    }

    function renderTaskCard(task) {
        const taskId = Number(task.id) || 0;
        const detailTask = state.detailByTaskId[taskId] || null;
        const renderTask = detailTask || task;
        const expanded = state.expandedTaskIds.has(taskId);
        const hasDetails = !!detailTask;
        const pendingEdit = getPendingEdit(taskId);
        const notesValue = pendingEdit ? String(pendingEdit.notes || "") : "";
        const detailTotal = Number(renderTask.detail_total) || 0;
        const detailConfirmed = Number(renderTask.detail_confirmed) || 0;
        const isDirty = state.dirtyTaskIds.has(taskId);

        return `
            <article class="task-stream-card ${overdueClass(task.overdue_level)}" data-task-id="${taskId}">
                <header class="task-stream-head">
                    <div>
                        <div class="task-stream-serial mono">${esc(task.serial_number || "-")}</div>
                        <div class="small muted">${esc(task.process_name || "-")} · ${esc(task.product_type || "未指定产品类型")}</div>
                    </div>
                    <div class="task-stream-badges">
                        <span class="status-badge ${badgeClassForStatus(task.status)}">${esc(statusLabel(task.status))}</span>
                        ${task.overdue_level && task.overdue_level !== "none" ? `<span class="task-overdue-tag ${overdueClass(task.overdue_level)}">${task.overdue_level === "danger" ? "超时>30分钟" : "超时>10分钟"}</span>` : ""}
                    </div>
                </header>

                <div class="task-stream-meta small muted">
                    <span>照片 ${Number(task.photo_count) || 0} 张</span>
                    <span>细节确认 ${detailConfirmed}/${detailTotal}</span>
                    <span>更新时间 ${esc(formatTime(task.updated_at))}</span>
                </div>

                ${renderAiSummary(renderTask)}

                <div class="task-stream-actions">
                    <button type="button" class="btn btn-secondary task-expand-btn" data-toggle-task="1" data-task-id="${taskId}">
                        ${expanded ? "收起详情" : "展开详情"}
                    </button>
                    ${isDirty ? '<span class="small task-dirty-hint">有未提交修改</span>' : ""}
                </div>

                ${expanded ? `
                    <section class="task-stream-detail">
                        ${hasDetails ? `
                            <div class="task-detail-section">
                                <h4>工序照片预览（${Array.isArray(renderTask.photos) ? renderTask.photos.length : 0}）</h4>
                                ${renderTaskPhotos(renderTask)}
                            </div>
                            <div class="task-detail-section">
                                <h4>细节确认（${detailConfirmed}/${detailTotal}）</h4>
                                ${renderTaskDetailRows(renderTask)}
                            </div>
                            <div class="task-confirm-toolbar">
                                <input
                                    type="text"
                                    class="task-confirm-notes"
                                    data-notes-input="1"
                                    placeholder="确认备注（可选）"
                                    value="${esc(notesValue)}"
                                >
                                <button type="button" class="btn btn-secondary" data-fill-status="pass" data-task-id="${taskId}">${reviewOnlyMode ? "全部判定识别正确" : "全部设为合格"}</button>
                                <button type="button" class="btn btn-secondary" data-fill-status="fail" data-task-id="${taskId}">${reviewOnlyMode ? "全部判定识别错误" : "全部设为不合格"}</button>
                                <button type="button" class="btn btn-primary" data-submit-confirm="1" data-task-id="${taskId}">提交确认</button>
                            </div>
                        ` : `
                            <div class="small muted">正在加载详情...</div>
                        `}
                    </section>
                ` : ""}
            </article>
        `;
    }

    function buildStatusGroups(tasks) {
        const groups = {
            pending: [],
            running: [],
            review: [],
            confirmed: [],
            failed: [],
        };
        for (const task of tasks) {
            const key = normalizeStatus(task.status);
            if (groups[key]) {
                groups[key].push(task);
            } else {
                groups.failed.push(task);
            }
        }
        return groups;
    }

    function renderTaskGroups(tasks) {
        const container = document.getElementById("task-groups");
        if (!container) {
            return;
        }
        if (!tasks.length) {
            container.innerHTML = '<div class="card"><div class="small muted">暂无任务</div></div>';
            return;
        }

        const groups = buildStatusGroups(tasks);
        container.innerHTML = statusOrder
            .map((status) => {
                const rows = groups[status] || [];
                return `
                    <section class="card task-group" data-status="${esc(status)}">
                        <div class="task-group-head">
                            <h3>${esc(statusLabel(status))}</h3>
                            <span class="task-group-count">${rows.length}</span>
                        </div>
                        ${rows.length
                            ? `<div class="task-group-list">${rows.map(renderTaskCard).join("")}</div>`
                            : '<div class="small muted">暂无任务</div>'
                        }
                    </section>
                `;
            })
            .join("");
    }

    async function loadTaskDetail(taskId) {
        const id = Number(taskId) || 0;
        if (!id || state.loadingDetailTaskIds.has(id) || state.detailByTaskId[id]) {
            return;
        }
        state.loadingDetailTaskIds.add(id);
        try {
            const data = await api.getTask(id);
            if (data && data.task) {
                state.detailByTaskId[id] = data.task;
            }
        } catch (err) {
            setHint(`任务 ${id} 详情加载失败: ${err.message || err}`);
        } finally {
            state.loadingDetailTaskIds.delete(id);
            renderTaskGroups(state.tasks);
        }
    }

    async function loadTasks(options) {
        const loadOptions = options || {};
        if (!projectId) {
            if (initialView !== "edge") {
                setHint("缺少 project_id");
            }
            return;
        }

        const filters = readFilters();
        if (filters.dateFrom && filters.dateTo && filters.dateFrom > filters.dateTo) {
            setHint("开始日期不能晚于结束日期");
            return;
        }
        if (!loadOptions.silent) {
            setHint("正在加载任务...");
        }

        try {
            const data = await api.listProjectTasks(projectId, {
                status: reviewOnlyMode ? "review" : filters.status,
                serial: filters.serial,
                process: filters.process,
                productType: filters.productType,
                dateFrom: filters.dateFrom,
                dateTo: filters.dateTo,
                include_children: reviewOnlyMode,
                per_page: 200,
                page: 1,
                seed_if_empty: true,
            });

            let tasks = Array.isArray(data.tasks) ? data.tasks : [];
            tasks = applyOverdueFilter(tasks, filters.overdue);
            tasks = applyAiFilter(tasks, filters.ai);

            state.tasks = tasks;
            trimDetailCaches(tasks);
            autoExpandReviewTasks(tasks);
            updateSummary(tasks);
            updateAiSummary(tasks);
            renderTaskGroups(tasks);

            const seededTasks = Number(data.seeded_tasks || 0);
            const seededPhotos = Number(data.seeded_photos || 0);
            const nowText = new Date().toLocaleTimeString("zh-CN");
            if (seededTasks > 0 || seededPhotos > 0) {
                setHint(`已加载 ${tasks.length} 条任务（首次回填: ${seededTasks} 任务 / ${seededPhotos} 张照片），更新时间 ${nowText}`);
            } else {
                setHint(`已加载 ${tasks.length} 条任务，更新时间 ${nowText}`);
            }

            await loadTaskOptions();

            // 保持展开状态的任务会自动补拉详情
            for (const id of state.expandedTaskIds) {
                if (getTaskById(id)) {
                    loadTaskDetail(id);
                }
            }
        } catch (err) {
            setHint(`任务加载失败: ${err.message || err}`);
            updateSummary([]);
            renderTaskGroups([]);
        }
    }

    function inferHumanResult(details) {
        const values = (details || []).map((row) => normalizeStatus(row.confirmed_status));
        if (!values.length) {
            return "";
        }
        if (values.includes("fail")) {
            return "fail";
        }
        if (values.every((item) => item === "pass")) {
            return "pass";
        }
        return "pending";
    }

    function collectTaskConfirmPayload(taskId, card) {
        const id = Number(taskId) || 0;
        if (!id || !card) {
            return null;
        }

        const details = [];
        const selects = card.querySelectorAll(".task-detail-status[data-detail-key]");
        for (const select of selects) {
            const detailKey = String(select.getAttribute("data-detail-key") || "").trim();
            const confirmedStatus = String(select.value || "").trim();
            if (!detailKey || !confirmedStatus) {
                continue;
            }
            details.push({
                detail_key: detailKey,
                confirmed_status: confirmedStatus,
            });
        }

        const notesInput = card.querySelector(".task-confirm-notes[data-notes-input]");
        const notes = notesInput ? String(notesInput.value || "").trim() : "";
        const payload = {
            details,
            notes,
            human_result: inferHumanResult(details),
        };
        return payload;
    }

    async function submitTaskConfirm(taskId, card, submitButton) {
        const id = Number(taskId) || 0;
        if (!id || !card) {
            return;
        }

        const payload = collectTaskConfirmPayload(id, card);
        if (!payload || !Array.isArray(payload.details) || !payload.details.length) {
            setHint("请先至少确认一个细节项，再提交。");
            return;
        }

        if (submitButton) {
            submitButton.disabled = true;
        }

        try {
            await api.confirmTask(id, payload);
            delete state.pendingEditsByTaskId[id];
            state.dirtyTaskIds.delete(id);
            setHint(`任务 ${id} 已提交确认`);
            await loadTasks({ silent: true });
            if (state.expandedTaskIds.has(id)) {
                loadTaskDetail(id);
            }
        } catch (err) {
            setHint(`任务 ${id} 提交失败: ${err.message || err}`);
        } finally {
            if (submitButton) {
                submitButton.disabled = false;
            }
        }
    }

    function fillAllDetailStatus(taskId, status, card) {
        const id = Number(taskId) || 0;
        if (!id || !card) {
            return;
        }
        const normalized = normalizeStatus(status);
        if (normalized !== "pass" && normalized !== "fail") {
            return;
        }

        const pending = ensurePendingEdit(id);
        const selects = card.querySelectorAll(".task-detail-status[data-detail-key]");
        for (const select of selects) {
            const detailKey = String(select.getAttribute("data-detail-key") || "").trim();
            if (!detailKey) {
                continue;
            }
            select.value = normalized;
            pending.detailStatusByKey[detailKey] = normalized;
        }
        markTaskDirty(id, true);
        renderTaskGroups(state.tasks);
        loadTaskDetail(id);
    }

    function toggleTask(taskId) {
        const id = Number(taskId) || 0;
        if (!id) {
            return;
        }
        if (state.expandedTaskIds.has(id)) {
            state.expandedTaskIds.delete(id);
            renderTaskGroups(state.tasks);
            return;
        }

        state.expandedTaskIds.add(id);
        renderTaskGroups(state.tasks);
        loadTaskDetail(id);
    }

    function openPhotoPreview(url, name) {
        const modal = document.getElementById("task-photo-preview-modal");
        const image = document.getElementById("task-photo-preview-image");
        const caption = document.getElementById("task-photo-preview-caption");
        if (!modal || !image || !caption) {
            return;
        }

        image.src = url || "";
        image.alt = name || "工序照片";
        caption.textContent = name || "";
        modal.classList.remove("hidden");
        document.body.style.overflow = "hidden";
    }

    function closePhotoPreview() {
        const modal = document.getElementById("task-photo-preview-modal");
        const image = document.getElementById("task-photo-preview-image");
        const caption = document.getElementById("task-photo-preview-caption");
        if (!modal || !image || !caption) {
            return;
        }
        image.src = "";
        caption.textContent = "";
        modal.classList.add("hidden");
        document.body.style.overflow = "";
    }

    function canAutoRefreshNow() {
        if (!state.autoRefreshEnabled) {
            return false;
        }
        if (state.loadingDetailTaskIds.size > 0) {
            return false;
        }
        if (state.dirtyTaskIds.size > 0) {
            setHint(`存在 ${state.dirtyTaskIds.size} 条未提交修改，已暂停自动刷新`);
            return false;
        }
        return true;
    }

    function startAutoRefresh() {
        if (state.autoRefreshTimer) {
            window.clearInterval(state.autoRefreshTimer);
        }
        state.autoRefreshTimer = window.setInterval(() => {
            if (!canAutoRefreshNow()) {
                return;
            }
            loadTasks({ silent: true });
        }, 10000);
    }

    function bindFilters() {
        const filterIds = [
            "task-filter-status",
            "task-filter-serial",
            "task-filter-process",
            "task-filter-product-type",
            "task-filter-date-from",
            "task-filter-date-to",
            "task-filter-overdue",
            "task-filter-ai",
        ];

        for (const id of filterIds) {
            const input = document.getElementById(id);
            if (!input) {
                continue;
            }
            input.addEventListener("input", scheduleLoadTaskOptions);
            input.addEventListener("change", scheduleLoadTaskOptions);
            if (id !== "task-filter-overdue") {
                input.addEventListener("keydown", (evt) => {
                    if (evt.key === "Enter") {
                        evt.preventDefault();
                        loadTasks();
                    }
                });
            }
        }

        const searchBtn = document.getElementById("task-search-btn");
        const refreshBtn = document.getElementById("task-refresh-btn");
        const resetBtn = document.getElementById("task-reset-btn");
        const autoBtn = document.getElementById("task-auto-refresh-btn");

        if (searchBtn) {
            searchBtn.addEventListener("click", () => loadTasks());
        }
        if (refreshBtn) {
            refreshBtn.addEventListener("click", () => loadTasks());
        }
        if (resetBtn) {
            resetBtn.addEventListener("click", () => {
                const statusFilter = document.getElementById("task-filter-status");
                if (statusFilter) {
                    statusFilter.value = reviewOnlyMode ? "review" : "";
                }
                document.getElementById("task-filter-serial").value = "";
                document.getElementById("task-filter-process").value = "";
                document.getElementById("task-filter-product-type").value = "";
                document.getElementById("task-filter-date-from").value = "";
                document.getElementById("task-filter-date-to").value = "";
                document.getElementById("task-filter-overdue").value = "";
                const aiFilter = document.getElementById("task-filter-ai");
                if (aiFilter) {
                    aiFilter.value = "";
                }
                loadTasks();
                scheduleLoadTaskOptions();
            });
        }

        if (autoBtn) {
            autoBtn.addEventListener("click", () => {
                state.autoRefreshEnabled = !state.autoRefreshEnabled;
                autoBtn.textContent = `自动刷新: ${state.autoRefreshEnabled ? "开" : "关"}`;
                if (state.autoRefreshEnabled) {
                    startAutoRefresh();
                }
            });
        }
    }

    function bindTaskActions() {
        document.addEventListener("click", (evt) => {
            const target = evt.target;
            if (!target || !target.closest) {
                return;
            }

            const toggleBtn = target.closest("[data-toggle-task]");
            if (toggleBtn) {
                const taskId = Number(toggleBtn.getAttribute("data-task-id") || "0");
                toggleTask(taskId);
                return;
            }

            const fillBtn = target.closest("[data-fill-status]");
            if (fillBtn) {
                const taskId = Number(fillBtn.getAttribute("data-task-id") || "0");
                const status = String(fillBtn.getAttribute("data-fill-status") || "").trim();
                const card = fillBtn.closest("[data-task-id]");
                fillAllDetailStatus(taskId, status, card);
                return;
            }

            const submitBtn = target.closest("[data-submit-confirm]");
            if (submitBtn) {
                const taskId = Number(submitBtn.getAttribute("data-task-id") || "0");
                const card = submitBtn.closest("[data-task-id]");
                submitTaskConfirm(taskId, card, submitBtn);
                return;
            }

            const photoBtn = target.closest("[data-open-photo]");
            if (photoBtn) {
                const url = String(photoBtn.getAttribute("data-photo-url") || "").trim();
                if (!url) {
                    return;
                }
                const name = String(photoBtn.getAttribute("data-photo-name") || "").trim();
                openPhotoPreview(url, name);
                return;
            }

            const closeBtn = target.closest("[data-close-photo-modal]");
            if (closeBtn) {
                closePhotoPreview();
            }
        });

        document.addEventListener("change", (evt) => {
            const target = evt.target;
            if (!(target instanceof HTMLSelectElement)) {
                return;
            }
            if (!target.classList.contains("task-detail-status")) {
                return;
            }

            const card = target.closest("[data-task-id]");
            const taskId = card ? Number(card.getAttribute("data-task-id") || "0") : 0;
            const detailKey = String(target.getAttribute("data-detail-key") || "").trim();
            if (!taskId || !detailKey) {
                return;
            }

            const pending = ensurePendingEdit(taskId);
            pending.detailStatusByKey[detailKey] = String(target.value || "").trim();
            markTaskDirty(taskId, true);
            renderTaskGroups(state.tasks);
            loadTaskDetail(taskId);
        });

        document.addEventListener("input", (evt) => {
            const target = evt.target;
            if (!(target instanceof HTMLInputElement)) {
                return;
            }
            if (!target.matches(".task-confirm-notes[data-notes-input]")) {
                return;
            }

            const card = target.closest("[data-task-id]");
            const taskId = card ? Number(card.getAttribute("data-task-id") || "0") : 0;
            if (!taskId) {
                return;
            }
            const pending = ensurePendingEdit(taskId);
            pending.notes = String(target.value || "");
            markTaskDirty(taskId, true);
        });

        const modal = document.getElementById("task-photo-preview-modal");
        if (modal) {
            modal.addEventListener("click", (event) => {
                const clicked = event.target;
                if (!clicked) {
                    return;
                }
                if (clicked.id === "task-photo-preview-modal" || (clicked.closest && clicked.closest("[data-close-photo-modal]"))) {
                    closePhotoPreview();
                }
            });
        }

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                closePhotoPreview();
            }
        });
    }

    async function init() {
        if (!projectId) {
            if (initialView !== "edge") {
                setHint("缺少 project_id，无法加载任务");
            }
            return;
        }

        if (reviewOnlyMode) {
            const statusSelect = document.getElementById("task-filter-status");
            if (statusSelect) {
                statusSelect.value = "review";
                statusSelect.disabled = true;
            }
        }

        bindFilters();
        bindTaskActions();
        startAutoRefresh();
        await loadTaskOptions();
        await loadTasks();
    }

    document.addEventListener("DOMContentLoaded", init);
}());
