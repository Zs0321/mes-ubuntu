/* global window, document */
(function initMotorQCEdgeUI() {
    "use strict";

    const pageProjectId = String(window.MOTOR_QC_TASK_PROJECT_ID || "").trim();
    const defaultProjectId = String(window.MOTOR_QC_EDGE_DEFAULT_PROJECT_ID || "").trim();
    const defaultProcessName = String(window.MOTOR_QC_EDGE_DEFAULT_PROCESS_NAME || "").trim();
    const defaultProductType = String(window.MOTOR_QC_EDGE_DEFAULT_PRODUCT_TYPE || "").trim();
    if (
        !window.MotorQCEdgeSessionStore ||
        !window.MotorQCEdgeCamera ||
        !window.MotorQCEdgeSimilarity ||
        !window.MotorQCEdgeUploader ||
        !window.MotorQCEdgeButton
    ) {
        return;
    }

    const initialView = String(window.MOTOR_QC_TASK_INITIAL_VIEW || "center").trim().toLowerCase();
    const store = new window.MotorQCEdgeSessionStore({
        stationId: String(window.MOTOR_QC_EDGE_DEFAULT_STATION || "S01"),
    });
    const api = window.motorQCAPI || new window.MotorQCAPIClient();

    const dom = {
        centerShell: document.getElementById("task-center-shell"),
        edgeShell: document.getElementById("edge-station-shell"),
        centerBtn: document.getElementById("task-view-center-btn"),
        edgeBtn: document.getElementById("task-view-edge-btn"),
        stationInput: document.getElementById("edge-station-id"),
        operatorInput: document.getElementById("edge-operator-id"),
        projectSelect: document.getElementById("edge-project-id"),
        projectInput: document.getElementById("edge-project-id-manual"),
        productTypeSelect: document.getElementById("edge-product-type"),
        productTypeInput: document.getElementById("edge-product-type-manual"),
        processSelect: document.getElementById("edge-process-name"),
        processInput: document.getElementById("edge-process-name-manual"),
        configSaveBtn: document.getElementById("edge-config-save-btn"),
        configStatus: document.getElementById("edge-config-status"),
        cameraSource: document.getElementById("edge-camera-source"),
        buttonSource: document.getElementById("edge-button-source"),
        bridgeUrl: document.getElementById("edge-bridge-url"),
        scanInput: document.getElementById("edge-scan-input"),
        scanBtn: document.getElementById("edge-scan-btn"),
        endBtn: document.getElementById("edge-end-btn"),
        resetBtn: document.getElementById("edge-reset-btn"),
        sessionState: document.getElementById("edge-session-state"),
        backendStatus: document.getElementById("edge-backend-status"),
        cameraStatus: document.getElementById("edge-camera-status"),
        buttonStatus: document.getElementById("edge-button-status"),
        queueSize: document.getElementById("edge-queue-size"),
        serial: document.getElementById("edge-current-serial"),
        project: document.getElementById("edge-current-project"),
        productType: document.getElementById("edge-current-product-type"),
        process: document.getElementById("edge-current-process"),
        countdown: document.getElementById("edge-tick-countdown"),
        lastSimilarity: document.getElementById("edge-last-similarity"),
        lastUpload: document.getElementById("edge-last-upload"),
        lastConclusion: document.getElementById("edge-last-conclusion"),
        conclusionStatus: document.getElementById("edge-conclusion-status"),
        conclusionSummary: document.getElementById("edge-conclusion-summary"),
        conclusionMetrics: document.getElementById("edge-conclusion-metrics"),
        conclusionFindings: document.getElementById("edge-conclusion-findings"),
        promptStatus: document.getElementById("edge-prompt-status"),
        expectedScrewCount: document.getElementById("edge-expected-screw-count"),
        specialProcesses: document.getElementById("edge-special-processes"),
        specialParts: document.getElementById("edge-special-parts"),
        extraFocus: document.getElementById("edge-extra-focus"),
        prePromptText: document.getElementById("edge-preprompt-text"),
        promptGenerateBtn: document.getElementById("edge-prompt-generate-btn"),
        promptSaveBtn: document.getElementById("edge-prompt-save-btn"),
        hint: document.getElementById("edge-hint"),
        video: document.getElementById("edge-live-video"),
        canvas: document.getElementById("edge-live-canvas"),
        timeline: document.getElementById("edge-timeline"),
    };

    if (!dom.edgeShell || !dom.centerShell || !dom.scanInput || !dom.endBtn || !dom.video) {
        return;
    }

    const TICK_SECONDS = 15;
    const DEFAULT_BRIDGE_URL = "http://127.0.0.1:19091";
    const EDGE_CONFIG_STORAGE_KEY = "motor_qc_edge_saved_config_v1";
    const EDGE_PROCESS_PROFILE_STORAGE_KEY = "motor_qc_edge_process_profile_v1";
    let cameraAdapter = null;
    let buttonAdapter = null;
    let buttonSourceName = "manual";
    let tickIntervalId = null;
    let countdownIntervalId = null;
    let lastUploadedCanvas = null;
    let lastUploadedFrameHash = "";
    let decisionInFlight = false;
    let finalizingSession = false;
    let currentProjectConfig = null;
    let projectsCache = [];
    let projectMap = new Map();
    let preferredProjectId = "";
    let preferredProductType = "";
    let preferredProcess = "";
    let manualConfigMode = false;
    let lastBridgeFrameMetaSignature = "";
    let processProfileMap = {};

    const uploader = new window.MotorQCEdgeUploader.EdgeCaptureUploader(api, {
        maxRetries: 3,
        baseDelayMs: 1200,
        onQueueChange: (size) => {
            store.setState({ queueSize: size });
        },
    });

    function setHint(text) {
        if (dom.hint) {
            dom.hint.textContent = text || "";
        }
    }

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function setConfigStatus(text, isError) {
        if (!dom.configStatus) {
            return;
        }
        dom.configStatus.textContent = text || "";
        dom.configStatus.style.color = isError ? "#b91c1c" : "";
    }

    function isManualConfigMode() {
        return manualConfigMode;
    }

    function setManualConfigMode(enabled, reason) {
        manualConfigMode = Boolean(enabled);
        if (dom.projectSelect) {
            dom.projectSelect.classList.toggle("hidden", manualConfigMode);
        }
        if (dom.productTypeSelect) {
            dom.productTypeSelect.classList.toggle("hidden", manualConfigMode);
        }
        if (dom.processSelect) {
            dom.processSelect.classList.toggle("hidden", manualConfigMode);
        }
        if (dom.projectInput) {
            dom.projectInput.classList.toggle("hidden", !manualConfigMode);
        }
        if (dom.productTypeInput) {
            dom.productTypeInput.classList.toggle("hidden", !manualConfigMode);
        }
        if (dom.processInput) {
            dom.processInput.classList.toggle("hidden", !manualConfigMode);
        }

        if (manualConfigMode) {
            if (dom.projectInput && !String(dom.projectInput.value || "").trim()) {
                dom.projectInput.value = String(preferredProjectId || (dom.projectSelect && dom.projectSelect.value) || "").trim();
            }
            if (dom.processInput && !String(dom.processInput.value || "").trim()) {
                dom.processInput.value = String(preferredProcess || (dom.processSelect && dom.processSelect.value) || "").trim();
            }
            if (dom.productTypeInput && !String(dom.productTypeInput.value || "").trim()) {
                dom.productTypeInput.value = String(
                    preferredProductType ||
                    (dom.productTypeSelect && dom.productTypeSelect.value) ||
                    ""
                ).trim();
            }
            if (reason) {
                setConfigStatus(reason, true);
            }
            return;
        }

        if (dom.projectSelect && dom.projectInput) {
            const pid = String(dom.projectInput.value || "").trim();
            if (pid && dom.projectSelect.options && dom.projectSelect.options.length > 0) {
                const has = Array.from(dom.projectSelect.options).some((opt) => String(opt.value || "").trim() === pid);
                if (has) {
                    dom.projectSelect.value = pid;
                }
            }
        }
        if (dom.processSelect && dom.processInput) {
            const proc = String(dom.processInput.value || "").trim();
            if (proc && dom.processSelect.options && dom.processSelect.options.length > 0) {
                const has = Array.from(dom.processSelect.options).some((opt) => String(opt.value || "").trim() === proc);
                if (has) {
                    dom.processSelect.value = proc;
                }
            }
        }
        if (dom.productTypeSelect && dom.productTypeInput) {
            const pt = String(dom.productTypeInput.value || "").trim();
            if (dom.productTypeSelect.options && dom.productTypeSelect.options.length > 0) {
                const has = Array.from(dom.productTypeSelect.options).some((opt) => String(opt.value || "").trim() === pt);
                if (has) {
                    dom.productTypeSelect.value = pt;
                }
            }
        }
    }

    function readSavedConfig() {
        try {
            const raw = String(window.localStorage.getItem(EDGE_CONFIG_STORAGE_KEY) || "").trim();
            if (!raw) {
                return {};
            }
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== "object") {
                return {};
            }
            return parsed;
        } catch (_err) {
            return {};
        }
    }

    function saveConfig(showMessage) {
        const payload = {
            stationId: String((dom.stationInput && dom.stationInput.value) || "S01").trim() || "S01",
            operatorId: String((dom.operatorInput && dom.operatorInput.value) || "").trim(),
            projectId: getSelectedProjectId(),
            productType: getSelectedProductType(),
            processName: getSelectedProcessName(),
            cameraSource: getCameraSource(),
            buttonSource: getButtonSource(),
            bridgeUrl: getBridgeUrl(),
            savedAt: new Date().toISOString(),
        };
        try {
            window.localStorage.setItem(EDGE_CONFIG_STORAGE_KEY, JSON.stringify(payload));
            setConfigStatus("配置已保存到本地", false);
            if (showMessage) {
                setHint("配置已保存：下次启动会自动恢复项目/工序/工位设置");
            }
        } catch (_err) {
            setConfigStatus("配置保存失败（浏览器存储不可用）", true);
            if (showMessage) {
                setHint("配置保存失败，请检查浏览器存储权限");
            }
        }
    }

    function readProcessProfileMap() {
        try {
            const raw = String(window.localStorage.getItem(EDGE_PROCESS_PROFILE_STORAGE_KEY) || "").trim();
            if (!raw) {
                return {};
            }
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== "object") {
                return {};
            }
            return parsed;
        } catch (_err) {
            return {};
        }
    }

    function saveProcessProfileMap() {
        try {
            window.localStorage.setItem(EDGE_PROCESS_PROFILE_STORAGE_KEY, JSON.stringify(processProfileMap || {}));
            return true;
        } catch (_err) {
            return false;
        }
    }

    function buildProcessProfileKey(projectId, productType, processName) {
        const pid = String(projectId || "").trim();
        const ptype = String(productType || "").trim();
        const proc = String(processName || "").trim();
        if (!pid || !proc) {
            return "";
        }
        return `${pid}::${ptype || "_"}::${proc}`;
    }

    function splitTextList(value) {
        const text = String(value || "").trim();
        if (!text) {
            return [];
        }
        return text
            .split(/[,\n，;；]+/g)
            .map((item) => String(item || "").trim())
            .filter(Boolean);
    }

    function normalizePromptProfile(raw) {
        const row = raw && typeof raw === "object" ? raw : {};
        let expectedScrewCount = "";
        if (row.expectedScrewCount !== undefined && row.expectedScrewCount !== null && row.expectedScrewCount !== "") {
            const parsed = Number(row.expectedScrewCount);
            if (Number.isFinite(parsed) && parsed >= 0) {
                expectedScrewCount = String(Math.round(parsed));
            }
        }
        return {
            expectedScrewCount,
            specialProcesses: String(row.specialProcesses || "").trim(),
            specialParts: String(row.specialParts || "").trim(),
            extraFocus: String(row.extraFocus || "").trim(),
            prePrompt: String(row.prePrompt || "").trim(),
        };
    }

    function getPromptProfileFromDom() {
        return normalizePromptProfile({
            expectedScrewCount: dom.expectedScrewCount && dom.expectedScrewCount.value,
            specialProcesses: dom.specialProcesses && dom.specialProcesses.value,
            specialParts: dom.specialParts && dom.specialParts.value,
            extraFocus: dom.extraFocus && dom.extraFocus.value,
            prePrompt: dom.prePromptText && dom.prePromptText.value,
        });
    }

    function applyPromptProfileToDom(profile) {
        const data = normalizePromptProfile(profile);
        if (dom.expectedScrewCount) {
            dom.expectedScrewCount.value = data.expectedScrewCount;
        }
        if (dom.specialProcesses) {
            dom.specialProcesses.value = data.specialProcesses;
        }
        if (dom.specialParts) {
            dom.specialParts.value = data.specialParts;
        }
        if (dom.extraFocus) {
            dom.extraFocus.value = data.extraFocus;
        }
        if (dom.prePromptText) {
            dom.prePromptText.value = data.prePrompt;
        }
    }

    function setPromptStatus(text, isError) {
        if (!dom.promptStatus) {
            return;
        }
        dom.promptStatus.textContent = text || "";
        dom.promptStatus.style.color = isError ? "#b91c1c" : "";
    }

    function getProjectIdFromItem(item) {
        if (!item || typeof item !== "object") {
            return "";
        }
        return String(
            item.project_id ||
            item.projectId ||
            item.project_code ||
            item.projectCode ||
            ""
        ).trim();
    }

    function getProjectNameFromItem(item) {
        if (!item || typeof item !== "object") {
            return "";
        }
        return String(
            item.name ||
            item.project_name ||
            item.projectName ||
            ""
        ).trim();
    }

    function getProjectDisplayText(item) {
        const pid = getProjectIdFromItem(item);
        const name = getProjectNameFromItem(item);
        if (name && pid && name !== pid) {
            return `${name}（${pid}）`;
        }
        return name || pid || "-";
    }

    function getProductTypeList(project) {
        const set = new Set();
        if (!project || typeof project !== "object") {
            return [];
        }
        const explicit = Array.isArray(project.product_types) ? project.product_types : [];
        for (const item of explicit) {
            const text = String(item || "").trim();
            if (text) {
                set.add(text);
            }
        }
        const list = Array.isArray(project.processes) ? project.processes : [];
        for (const item of list) {
            const text = String((item && (item.product_type || item.productType)) || "").trim();
            if (text) {
                set.add(text);
            }
        }
        return Array.from(set.values());
    }

    function getProcessList(project, selectedProductType) {
        const list = (project && Array.isArray(project.processes)) ? project.processes.slice() : [];
        const selectedType = String(selectedProductType || "").trim();
        const normalized = list
            .filter((item) => item && item.name)
            .map((item) => ({
                name: String(item.name || "").trim(),
                order: Number(item.order || 0),
                productType: String(item.product_type || item.productType || "").trim(),
                subChecks: Array.isArray(item.subChecks) ? item.subChecks : [],
                rules: (item.rules && typeof item.rules === "object") ? item.rules : {},
                expectedScrewCount: item.expectedScrewCount || item.expected_screw_count || "",
                specialProcesses: item.specialProcesses || item.special_processes || "",
                specialParts: item.specialParts || item.special_parts || "",
                extraFocus: item.extraFocus || item.extra_focus || "",
                prePrompt: item.prePrompt || item.pre_prompt || "",
            }))
            .filter((item) => {
                if (!selectedType) {
                    return true;
                }
                if (!item.productType) {
                    return true;
                }
                return item.productType === selectedType;
            });
        normalized.sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
        return normalized;
    }

    function getSelectedProjectId() {
        if (isManualConfigMode() && dom.projectInput) {
            return String(dom.projectInput.value || "").trim();
        }
        return String((dom.projectSelect && dom.projectSelect.value) || "").trim();
    }

    function getSelectedProcessName() {
        if (isManualConfigMode() && dom.processInput) {
            return String(dom.processInput.value || "").trim();
        }
        return String((dom.processSelect && dom.processSelect.value) || "").trim();
    }

    function getSelectedProductType() {
        if (isManualConfigMode() && dom.productTypeInput) {
            return String(dom.productTypeInput.value || "").trim();
        }
        return String((dom.productTypeSelect && dom.productTypeSelect.value) || "").trim();
    }

    function findProcessMeta(project, processName, selectedProductType) {
        const target = String(processName || "").trim();
        if (!target) {
            return null;
        }
        const selectedType = String(selectedProductType || "").trim();
        const list = getProcessList(project, selectedType);
        const sameName = list.filter((item) => item.name === target);
        if (!sameName.length) {
            return null;
        }
        if (!selectedType) {
            return sameName[0];
        }
        const exact = sameName.find((item) => item.productType === selectedType);
        if (exact) {
            return exact;
        }
        const generic = sameName.find((item) => !item.productType);
        return generic || sameName[0];
    }

    function getCurrentProcessMeta() {
        return findProcessMeta(
            currentProjectConfig,
            getSelectedProcessName(),
            getSelectedProductType()
        );
    }

    function buildAutoPrePrompt(profile, processMeta) {
        const stepName = getSelectedProcessName();
        const selectedType = getSelectedProductType();
        const screwCount = String(profile.expectedScrewCount || "").trim();
        const specialProcesses = splitTextList(profile.specialProcesses);
        const specialParts = splitTextList(profile.specialParts);
        const extraFocus = splitTextList(profile.extraFocus);
        const checkNames = [];
        if (processMeta && Array.isArray(processMeta.subChecks)) {
            for (const row of processMeta.subChecks) {
                if (row && typeof row === "object") {
                    const name = String(row.name || row.key || "").trim();
                    if (name) {
                        checkNames.push(name);
                    }
                } else {
                    const text = String(row || "").trim();
                    if (text) {
                        checkNames.push(text);
                    }
                }
            }
        }
        if (processMeta && processMeta.rules && Array.isArray(processMeta.rules.check_items)) {
            for (const item of processMeta.rules.check_items) {
                const text = String(item || "").trim();
                if (text) {
                    checkNames.push(text);
                }
            }
        }
        const uniqueChecks = Array.from(new Set(checkNames.filter(Boolean)));
        const lines = [
            "你是电机装配质检专家，请严格按以下工艺要求判定。",
            `当前工序：${stepName || "未配置工序"}`,
        ];
        if (selectedType) {
            lines.push(`产品类型：${selectedType}`);
        }
        if (screwCount) {
            lines.push(`螺钉数量要求：应安装 ${screwCount} 个，关注漏装/错装/未到位。`);
        }
        if (specialProcesses.length) {
            lines.push(`特殊工艺：${specialProcesses.join("、")}`);
        }
        if (specialParts.length) {
            lines.push(`关键零部件：${specialParts.join("、")}`);
        }
        if (extraFocus.length) {
            lines.push(`检测关注点：${extraFocus.join("、")}`);
        }
        if (uniqueChecks.length) {
            lines.push(`必检项：${uniqueChecks.join("、")}`);
        }
        lines.push("输出请包含结论、主要问题、是否需返工。");
        return lines.join("\n");
    }

    function loadPromptProfileForSelection() {
        const profileKey = buildProcessProfileKey(
            getSelectedProjectId(),
            getSelectedProductType(),
            getSelectedProcessName()
        );
        const processMeta = getCurrentProcessMeta();
        const fallback = normalizePromptProfile({
            expectedScrewCount: processMeta && processMeta.expectedScrewCount,
            specialProcesses: processMeta && processMeta.specialProcesses,
            specialParts: processMeta && processMeta.specialParts,
            extraFocus: processMeta && processMeta.extraFocus,
            prePrompt: processMeta && processMeta.prePrompt,
        });
        const savedProfile = profileKey ? normalizePromptProfile(processProfileMap[profileKey] || {}) : {};
        // Priority: central process config > local override.
        const merged = normalizePromptProfile(Object.assign({}, savedProfile, fallback));
        if (!merged.prePrompt) {
            merged.prePrompt = buildAutoPrePrompt(merged, processMeta);
        }
        applyPromptProfileToDom(merged);
        const hasCentralProfile = Boolean(
            fallback.prePrompt ||
            fallback.specialProcesses ||
            fallback.specialParts ||
            fallback.extraFocus ||
            fallback.expectedScrewCount
        );
        if (hasCentralProfile) {
            setPromptStatus("已加载工序配置预设", false);
        } else if (profileKey && processProfileMap[profileKey]) {
            setPromptStatus("已加载本地预设", false);
        } else {
            setPromptStatus("当前工序使用默认预设", false);
        }
    }

    function savePromptProfileForSelection(showMessage) {
        const profileKey = buildProcessProfileKey(
            getSelectedProjectId(),
            getSelectedProductType(),
            getSelectedProcessName()
        );
        if (!profileKey) {
            setPromptStatus("请先选择项目和工序", true);
            if (showMessage) {
                setHint("请先选择项目和工序，再保存预Prompt配置");
            }
            return false;
        }
        const profile = getPromptProfileFromDom();
        if (!profile.prePrompt) {
            profile.prePrompt = buildAutoPrePrompt(profile, getCurrentProcessMeta());
            if (dom.prePromptText) {
                dom.prePromptText.value = profile.prePrompt;
            }
        }
        processProfileMap[profileKey] = profile;
        if (!saveProcessProfileMap()) {
            setPromptStatus("保存失败（浏览器存储不可用）", true);
            return false;
        }
        setPromptStatus("预设已保存", false);
        if (showMessage) {
            setHint("工序预Prompt配置已保存，本机下次会自动恢复");
        }
        return true;
    }

    function buildProcessContextPayload() {
        const profile = getPromptProfileFromDom();
        const processMeta = getCurrentProcessMeta();
        const autoPrompt = buildAutoPrePrompt(profile, processMeta);
        const prePrompt = String(profile.prePrompt || autoPrompt || "").trim();
        return {
            expected_screw_count: profile.expectedScrewCount ? Number(profile.expectedScrewCount) : 0,
            special_processes: splitTextList(profile.specialProcesses),
            special_parts: splitTextList(profile.specialParts),
            extra_focus: splitTextList(profile.extraFocus),
            pre_prompt: prePrompt,
        };
    }

    function renderProjectOptions(selectedProjectId) {
        if (isManualConfigMode()) {
            if (dom.projectInput) {
                dom.projectInput.value = String(selectedProjectId || preferredProjectId || "").trim();
            }
            return;
        }
        if (!dom.projectSelect) {
            return;
        }
        const options = [];
        for (const project of projectsCache) {
            const pid = getProjectIdFromItem(project);
            if (!pid) {
                continue;
            }
            options.push({
                value: pid,
                text: getProjectDisplayText(project),
            });
        }
        if (!options.length) {
            dom.projectSelect.innerHTML = '<option value="">无可用项目</option>';
            dom.projectSelect.value = "";
            return;
        }

        dom.projectSelect.innerHTML = options
            .map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.text)}</option>`)
            .join("");
        const preferred = String(selectedProjectId || "").trim();
        const hasPreferred = options.some((item) => item.value === preferred);
        dom.projectSelect.value = hasPreferred ? preferred : options[0].value;
    }

    function renderProcessOptions(project, selectedProcessName) {
        if (isManualConfigMode()) {
            if (dom.processInput) {
                dom.processInput.value = String(selectedProcessName || preferredProcess || "").trim();
            }
            return;
        }
        if (!dom.processSelect) {
            return;
        }
        const selectedType = getSelectedProductType();
        const processes = getProcessList(project, selectedType);
        if (!processes.length) {
            dom.processSelect.innerHTML = '<option value="">当前项目无可用工序</option>';
            dom.processSelect.value = "";
            return;
        }

        dom.processSelect.innerHTML = processes
            .map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)}</option>`)
            .join("");
        const preferred = String(selectedProcessName || "").trim();
        const hasPreferred = processes.some((item) => item.name === preferred);
        dom.processSelect.value = hasPreferred ? preferred : processes[0].name;
    }

    function renderProductTypeOptions(project, selectedProductType) {
        if (isManualConfigMode()) {
            if (dom.productTypeInput) {
                dom.productTypeInput.value = String(selectedProductType || preferredProductType || "").trim();
            }
            return;
        }
        if (!dom.productTypeSelect) {
            return;
        }
        const productTypes = getProductTypeList(project);
        const options = ['<option value="">自动识别/未指定</option>'].concat(
            productTypes.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`)
        );
        dom.productTypeSelect.innerHTML = options.join("");
        const preferred = String(selectedProductType || "").trim();
        const hasPreferred = productTypes.some((item) => item === preferred);
        dom.productTypeSelect.value = hasPreferred ? preferred : "";
    }

    async function resolveProjectConfig(projectId) {
        const pid = String(projectId || "").trim();
        if (!pid) {
            return null;
        }
        const cached = projectMap.get(pid);
        if (cached && Array.isArray(cached.processes) && cached.processes.length > 0) {
            return cached;
        }
        if (cached && cached.__legacy_source) {
            const legacyResp = await api.getMESProjectConfig(pid);
            const legacyCfg = legacyResp && legacyResp.config ? legacyResp.config : {};
            const mergedLegacy = buildProjectFromLegacyConfig(pid, legacyCfg);
            projectMap.set(pid, mergedLegacy);
            return mergedLegacy;
        }
        const project = await api.getProject(pid);
        const merged = Object.assign({}, cached || {}, project || {}, { project_id: pid });
        projectMap.set(pid, merged);
        return merged;
    }

    function syncConfiguredContextToStore() {
        const pid = getSelectedProjectId();
        const selectedProductType = getSelectedProductType();
        const processName = getSelectedProcessName();
        const projectName = currentProjectConfig
            ? (getProjectNameFromItem(currentProjectConfig) || pid)
            : pid;
        const processMeta = findProcessMeta(currentProjectConfig, processName, selectedProductType);
        store.setState({
            projectId: pid,
            projectName,
            productType: selectedProductType || (processMeta ? String(processMeta.productType || "").trim() : ""),
            processName: processName || "",
            processOrder: processMeta ? Number(processMeta.order || 0) : (isManualConfigMode() ? 1 : 0),
            processContext: buildProcessContextPayload(),
        });
    }

    function getBridgeUrl() {
        const raw = String((dom.bridgeUrl && dom.bridgeUrl.value) || "").trim();
        return raw || DEFAULT_BRIDGE_URL;
    }

    function normalizeStationId(raw) {
        return String(raw || "S01").trim().replace(/\^+$/, "") || "S01";
    }

    function getCameraSource() {
        const value = String((dom.cameraSource && dom.cameraSource.value) || "browser").trim().toLowerCase();
        return value || "browser";
    }

    function getButtonSource() {
        const value = String((dom.buttonSource && dom.buttonSource.value) || "manual").trim().toLowerCase();
        return value || "manual";
    }

    function authFlagExists(name) {
        return Object.prototype.hasOwnProperty.call(window, name);
    }

    function hasWebQCPermission() {
        if (!authFlagExists("EDGE_LOCAL_WEB_QC_PERMISSION")) {
            return true;
        }
        return window.EDGE_LOCAL_WEB_QC_PERMISSION === true;
    }

    function hasMobileQCPermission() {
        if (authFlagExists("EDGE_LOCAL_MOBILE_QC_PERMISSION")) {
            return window.EDGE_LOCAL_MOBILE_QC_PERMISSION === true;
        }
        if (!authFlagExists("EDGE_LOCAL_QC_API_PERMISSION")) {
            return true;
        }
        return window.EDGE_LOCAL_QC_API_PERMISSION === true;
    }

    function hasProjectsReadPermission() {
        if (!authFlagExists("EDGE_LOCAL_PROJECTS_PERMISSION")) {
            return true;
        }
        return window.EDGE_LOCAL_PROJECTS_PERMISSION === true;
    }

    function inEdgeLocalAuthMode() {
        return authFlagExists("EDGE_LOCAL_LOGGED_IN");
    }

    function normalizeLegacyProcessStep(raw, fallbackOrder, productType) {
        if (typeof raw === "string") {
            const nameText = String(raw || "").trim();
            if (!nameText) {
                return null;
            }
            return {
                name: nameText,
                order: Number(fallbackOrder || 0),
                product_type: String(productType || "").trim(),
                productType: String(productType || "").trim(),
                subChecks: [],
                rules: {},
                expectedScrewCount: "",
                specialProcesses: "",
                specialParts: "",
                extraFocus: "",
                prePrompt: "",
            };
        }
        if (!raw || typeof raw !== "object") {
            return null;
        }
        const nameText = String(
            raw.name ||
            raw.stepName ||
            raw.processName ||
            raw.process_name ||
            raw.id ||
            ""
        ).trim();
        if (!nameText) {
            return null;
        }
        return {
            name: nameText,
            order: Number(raw.order || raw.stepOrder || fallbackOrder || 0),
            product_type: String(productType || raw.product_type || raw.productType || "").trim(),
            productType: String(productType || raw.product_type || raw.productType || "").trim(),
            subChecks: Array.isArray(raw.subChecks) ? raw.subChecks : [],
            rules: (raw.rules && typeof raw.rules === "object") ? raw.rules : {},
            expectedScrewCount: raw.expectedScrewCount || raw.expected_screw_count || "",
            specialProcesses: raw.specialProcesses || raw.special_processes || "",
            specialParts: raw.specialParts || raw.special_parts || "",
            extraFocus: raw.extraFocus || raw.extra_focus || "",
            prePrompt: raw.prePrompt || raw.pre_prompt || "",
        };
    }

    function dedupeProcessItems(items) {
        const map = new Map();
        for (const item of items || []) {
            if (!item || !item.name) {
                continue;
            }
            const key = `${String(item.name || "").trim().toLowerCase()}|${String(item.product_type || "").trim().toLowerCase()}`;
            const prev = map.get(key);
            if (!prev || Number(item.order || 0) < Number(prev.order || 0)) {
                map.set(key, item);
            }
        }
        return Array.from(map.values()).sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
    }

    function buildProjectFromLegacyConfig(projectId, config) {
        const pid = String(projectId || "").trim();
        const cfg = (config && typeof config === "object") ? config : {};
        const productTypes = Array.isArray(cfg.productTypes)
            ? cfg.productTypes
            : (Array.isArray(cfg.product_types) ? cfg.product_types : []);
        const processes = [];
        for (const pt of productTypes) {
            const typeName = String((pt && (pt.typeName || pt.type_name || pt.name)) || "").trim();
            const steps = Array.isArray(pt && pt.processSteps) ? pt.processSteps : [];
            let idx = 0;
            for (const step of steps) {
                idx += 1;
                const normalized = normalizeLegacyProcessStep(step, idx, typeName);
                if (normalized) {
                    processes.push(normalized);
                }
            }
        }
        if (!processes.length && Array.isArray(cfg.processSteps)) {
            let idx = 0;
            for (const step of cfg.processSteps) {
                idx += 1;
                const normalized = normalizeLegacyProcessStep(step, idx, "");
                if (normalized) {
                    processes.push(normalized);
                }
            }
        }
        return {
            project_id: pid,
            project_code: String(cfg.projectCode || cfg.project_code || "").trim(),
            name: String(cfg.projectName || cfg.project_name || pid).trim() || pid,
            processes: dedupeProcessItems(processes),
            __legacy_source: true,
        };
    }

    async function tryLoadLegacyProjects() {
        const legacyResp = await api.listMESProjectsLegacy();
        const projectNames = Array.isArray(legacyResp && legacyResp.projects) ? legacyResp.projects : [];
        const normalized = projectNames
            .map((item) => String(item || "").trim())
            .filter(Boolean);
        if (!normalized.length) {
            throw new Error("MES 项目列表为空");
        }
        projectsCache = normalized.map((name) => ({
            project_id: name,
            project_code: "",
            name,
            processes: [],
            __legacy_source: true,
        }));
        projectMap = new Map();
        for (const item of projectsCache) {
            projectMap.set(item.project_id, item);
        }
    }

    function selectIfExists(selectEl, value) {
        if (!selectEl) {
            return;
        }
        const normalized = String(value || "").trim().toLowerCase();
        if (!normalized) {
            return;
        }
        const options = Array.from(selectEl.options || []).map((opt) => String(opt.value || "").trim().toLowerCase());
        if (!options.includes(normalized)) {
            return;
        }
        selectEl.value = normalized;
    }

    function applyInitialDefaults() {
        const saved = readSavedConfig();
        processProfileMap = readProcessProfileMap();
        const station = normalizeStationId(window.MOTOR_QC_EDGE_DEFAULT_STATION || saved.stationId || "");
        const operator = String(window.MOTOR_QC_EDGE_DEFAULT_OPERATOR || saved.operatorId || "").trim();
        const cameraSource = String(window.MOTOR_QC_EDGE_DEFAULT_CAMERA_SOURCE || saved.cameraSource || "").trim().toLowerCase();
        const buttonSource = String(window.MOTOR_QC_EDGE_DEFAULT_BUTTON_SOURCE || saved.buttonSource || "").trim().toLowerCase();
        const bridgeUrl = String(window.MOTOR_QC_EDGE_DEFAULT_BRIDGE_URL || saved.bridgeUrl || "").trim();
        preferredProjectId = String(defaultProjectId || saved.projectId || pageProjectId || "").trim();
        preferredProductType = String(defaultProductType || saved.productType || "").trim();
        preferredProcess = String(defaultProcessName || saved.processName || "").trim();

        if (dom.stationInput && station) {
            dom.stationInput.value = station;
            store.setState({ stationId: station });
        }
        if (dom.operatorInput && operator) {
            dom.operatorInput.value = operator;
            store.setState({ operatorId: operator });
        }
        selectIfExists(dom.cameraSource, cameraSource);
        selectIfExists(dom.buttonSource, buttonSource);
        if (dom.bridgeUrl && bridgeUrl) {
            dom.bridgeUrl.value = bridgeUrl;
        }
        setConfigStatus("可修改项目/工序后点击“保存配置”", false);
        setPromptStatus("可按工序保存预Prompt配置", false);
    }

    function applyPreviewMode(mode) {
        const normalized = String(mode || "video").trim().toLowerCase();
        if (normalized === "canvas") {
            dom.video.classList.add("hidden");
            dom.canvas.classList.remove("hidden");
            return;
        }
        dom.canvas.classList.add("hidden");
        dom.video.classList.remove("hidden");
    }

    function setViewMode(view) {
        const next = view === "edge" ? "edge" : "center";
        if (next === "edge") {
            dom.centerShell.classList.add("hidden");
            dom.edgeShell.classList.remove("hidden");
            dom.centerBtn.classList.remove("btn-primary");
            dom.centerBtn.classList.add("btn-secondary");
            dom.edgeBtn.classList.remove("btn-secondary");
            dom.edgeBtn.classList.add("btn-primary");
        } else {
            dom.centerShell.classList.remove("hidden");
            dom.edgeShell.classList.add("hidden");
            dom.centerBtn.classList.remove("btn-secondary");
            dom.centerBtn.classList.add("btn-primary");
            dom.edgeBtn.classList.remove("btn-primary");
            dom.edgeBtn.classList.add("btn-secondary");
        }
        try {
            window.localStorage.setItem("motor_qc_tasks_view_mode", next);
        } catch (_err) {
            // ignore storage errors
        }
    }

    async function refreshProjectSelection(options) {
        const opts = options || {};
        const selectedProjectId = getSelectedProjectId();
        if (!selectedProjectId) {
            currentProjectConfig = null;
            renderProductTypeOptions(null, "");
            renderProcessOptions(null, "");
            applyPromptProfileToDom({});
            setPromptStatus("请先选择项目和工序", false);
            syncConfiguredContextToStore();
            return;
        }

        if (isManualConfigMode()) {
            const manualProductType = String(
                opts.preferredProductType || preferredProductType || getSelectedProductType() || ""
            ).trim();
            const manualProcessName = String(opts.preferredProcessName || preferredProcess || getSelectedProcessName() || "").trim();
            currentProjectConfig = {
                project_id: selectedProjectId,
                name: selectedProjectId,
                product_types: manualProductType ? [manualProductType] : [],
                processes: manualProcessName
                    ? [{
                        name: manualProcessName,
                        order: 1,
                        product_type: manualProductType,
                        productType: manualProductType,
                    }]
                    : [],
            };
            renderProductTypeOptions(currentProjectConfig, manualProductType);
            renderProcessOptions(currentProjectConfig, manualProcessName);
            loadPromptProfileForSelection();
            preferredProjectId = getSelectedProjectId();
            preferredProductType = getSelectedProductType();
            preferredProcess = getSelectedProcessName();
            syncConfiguredContextToStore();
            if (opts.persist) {
                saveConfig(false);
            }
            if (!opts.silent) {
                const selectedType = getSelectedProductType();
                const processName = getSelectedProcessName();
                const typeSuffix = selectedType ? ` / ${selectedType}` : "";
                setConfigStatus(`手动模式：${selectedProjectId}${typeSuffix} / ${processName || "-"}`, false);
            }
            return;
        }

        try {
            currentProjectConfig = await resolveProjectConfig(selectedProjectId);
            const selectedType = String(opts.preferredProductType || preferredProductType || getSelectedProductType() || "").trim();
            const selectedProcessName = String(opts.preferredProcessName || preferredProcess || getSelectedProcessName() || "").trim();
            renderProductTypeOptions(currentProjectConfig, selectedType);
            renderProcessOptions(currentProjectConfig, selectedProcessName);
            loadPromptProfileForSelection();
            preferredProjectId = getSelectedProjectId();
            preferredProductType = getSelectedProductType();
            preferredProcess = getSelectedProcessName();
            syncConfiguredContextToStore();
            if (opts.persist) {
                saveConfig(false);
            }
            if (!opts.silent) {
                const processName = getSelectedProcessName();
                const currentType = getSelectedProductType();
                const typeSuffix = currentType ? ` / ${currentType}` : "";
                setConfigStatus(`当前：${getProjectDisplayText(currentProjectConfig)}${typeSuffix} / ${processName || "-"}`, false);
            }
        } catch (err) {
            setConfigStatus("项目加载失败", true);
            setHint(`项目加载失败：${err.message || err}`);
        }
    }

    async function loadProjectAndProcessOptions() {
        const presetManualByAuth = window.EDGE_LOCAL_FORCE_MANUAL_CONFIG === true;
        if (presetManualByAuth) {
            setManualConfigMode(true, "当前账号无 web:run_qc，已切换手动项目/工序模式");
        }
        try {
            const data = await api.listProjects();
            projectsCache = Array.isArray(data && data.projects) ? data.projects : [];
            projectMap = new Map();
            for (const item of projectsCache) {
                const pid = getProjectIdFromItem(item);
                if (!pid) {
                    continue;
                }
                projectMap.set(pid, item);
            }
            setManualConfigMode(false, "");
            renderProjectOptions(preferredProjectId);
            await refreshProjectSelection({
                preferredProductType: preferredProductType,
                preferredProcessName: preferredProcess,
                silent: true,
            });
            if (getSelectedProjectId() && getSelectedProcessName()) {
                setConfigStatus("已加载本地配置（可修改后重新保存）", false);
            } else {
                setConfigStatus("请选择项目和工序后点击“保存配置”", false);
            }
        } catch (err) {
            const status = Number(err && err.status) || 0;
            const shouldTryLegacy = inEdgeLocalAuthMode() && status !== 401;
            if (shouldTryLegacy) {
                try {
                    await tryLoadLegacyProjects();
                    setManualConfigMode(false, "");
                    renderProjectOptions(preferredProjectId);
                    await refreshProjectSelection({
                        preferredProductType: preferredProductType,
                        preferredProcessName: preferredProcess,
                        silent: true,
                    });
                    setConfigStatus("已加载 MES 项目配置（兼容接口）", false);
                    setHint("已从 MES 配置中心加载项目/产品类型/工序");
                    return;
                } catch (_legacyErr) {
                    // continue to manual fallback below
                }
            }
            if (status === 401 || status === 403) {
                setManualConfigMode(true, "当前账号无 web:run_qc，已切换手动项目/工序模式");
                renderProjectOptions(preferredProjectId);
                await refreshProjectSelection({
                    preferredProductType: preferredProductType,
                    preferredProcessName: preferredProcess,
                    silent: true,
                });
                if (!hasProjectsReadPermission()) {
                    setHint("当前账号无法读取 MES 项目配置，请联系管理员开通 /api/projects 访问权限");
                } else if (hasMobileQCPermission()) {
                    setHint("当前账号可用移动端QC接口；请手动填写项目/工序并保存后再扫码");
                } else {
                    setHint("当前账号无 web:run_qc 且移动端QC接口不可用；可预览但无法提交识别");
                }
                return;
            }
            setConfigStatus("项目列表加载失败", true);
            setHint(`项目列表加载失败：${err.message || err}`);
        }
    }

    function formatSimilarity(value) {
        if (!value || typeof value !== "object") {
            return "-";
        }
        const screw = `screw(ssim=${value.screw_ssim ?? "-"},hash=${value.screw_phash ?? "-"})`;
        const glue = `glue(ssim=${value.glue_ssim ?? "-"},hash=${value.glue_phash ?? "-"})`;
        return `${screw} ${glue}`;
    }

    function normalizeQCStatus(raw) {
        const status = String(raw || "").trim().toLowerCase();
        if (!status) {
            return "unknown";
        }
        if (status === "pass" || status === "ok" || status === "confirmed") {
            return "pass";
        }
        if (status === "fail" || status === "ng" || status === "error") {
            return "fail";
        }
        return status;
    }

    function formatQCStatusLabel(raw) {
        const normalized = normalizeQCStatus(raw);
        if (normalized === "pass") {
            return "通过";
        }
        if (normalized === "fail") {
            return "不通过";
        }
        if (normalized === "pending") {
            return "待处理";
        }
        return normalized || "未知";
    }

    function buildQCConclusionText(lastUpload) {
        if (!lastUpload || lastUpload.status !== "ok") {
            return "-";
        }
        const statusLabel = formatQCStatusLabel(lastUpload.qcStatus || lastUpload.taskStatus || "");
        const summary = String(lastUpload.qcSummary || "").trim();
        const findings = Number(lastUpload.qcFindings || 0);
        const confidence = Number(lastUpload.qcConfidence || 0);
        const parts = [];
        if (statusLabel && statusLabel !== "unknown") {
            parts.push(`结论:${statusLabel}`);
        }
        if (summary) {
            const shortSummary = summary.length > 64 ? `${summary.slice(0, 64)}...` : summary;
            parts.push(shortSummary);
        }
        if (findings > 0) {
            parts.push(`问题:${findings}`);
        }
        if (confidence > 0) {
            parts.push(`置信:${confidence.toFixed(2)}`);
        }
        return parts.length ? parts.join(" | ") : "-";
    }

    function extractFindingLines(lastUpload) {
        if (!lastUpload || !Array.isArray(lastUpload.qcDefects)) {
            return [];
        }
        return lastUpload.qcDefects
            .map((item) => String(item || "").trim())
            .filter(Boolean)
            .slice(0, 5);
    }

    function renderConclusionPanel(lastUpload) {
        if (!dom.conclusionStatus || !dom.conclusionSummary || !dom.conclusionFindings || !dom.conclusionMetrics) {
            return;
        }
        if (lastUpload && lastUpload.status === "failed") {
            dom.conclusionStatus.textContent = "上传失败";
            dom.conclusionStatus.className = "edge-conclusion-badge fail";
            dom.conclusionSummary.textContent = String(lastUpload.message || "请检查网络与权限").trim();
            dom.conclusionSummary.classList.remove("muted");
            dom.conclusionMetrics.textContent = "等待队列重试";
            dom.conclusionFindings.innerHTML = "<li class=\"muted\">上传失败时不执行识别</li>";
            return;
        }
        if (!lastUpload || lastUpload.status !== "ok") {
            dom.conclusionStatus.textContent = "待检测";
            dom.conclusionStatus.className = "edge-conclusion-badge pending";
            dom.conclusionSummary.textContent = "暂无识别结果";
            dom.conclusionSummary.classList.add("muted");
            dom.conclusionMetrics.textContent = "等待检测";
            dom.conclusionFindings.innerHTML = "<li class=\"muted\">暂无问题明细</li>";
            return;
        }
        const normalized = normalizeQCStatus(lastUpload.qcStatus || lastUpload.taskStatus || "");
        const statusLabel = formatQCStatusLabel(normalized);
        const cls = normalized === "pass" ? "pass" : (normalized === "pending" ? "pending" : "fail");
        dom.conclusionStatus.textContent = statusLabel || "未知";
        dom.conclusionStatus.className = `edge-conclusion-badge ${cls}`;

        const summary = String(lastUpload.qcSummary || "").trim();
        dom.conclusionSummary.textContent = summary || "暂无AI摘要";
        dom.conclusionSummary.classList.toggle("muted", !summary);

        const parts = [];
        const modeLabel = String(lastUpload.mode || "").trim() === "mobile_qc" ? "移动端一致通道" : "任务中心通道";
        parts.push(modeLabel);
        if (Number(lastUpload.qcFindings || 0) > 0) {
            parts.push(`问题:${Number(lastUpload.qcFindings || 0)}`);
        } else {
            parts.push("问题:0");
        }
        if (Number(lastUpload.qcConfidence || 0) > 0) {
            parts.push(`置信:${Number(lastUpload.qcConfidence || 0).toFixed(2)}`);
        }
        if (Number(lastUpload.latencyMs || 0) > 0) {
            parts.push(`${Number(lastUpload.latencyMs || 0)}ms`);
        }
        dom.conclusionMetrics.textContent = parts.join(" / ");

        const lines = extractFindingLines(lastUpload);
        if (!lines.length) {
            dom.conclusionFindings.innerHTML = "<li class=\"muted\">未发现明显缺陷</li>";
            return;
        }
        dom.conclusionFindings.innerHTML = lines
            .map((line) => `<li>${escapeHtml(line)}</li>`)
            .join("");
    }

    function renderTimeline(timeline) {
        if (!dom.timeline) {
            return;
        }
        if (!Array.isArray(timeline) || !timeline.length) {
            dom.timeline.innerHTML = '<div class="small muted">暂无事件</div>';
            return;
        }
        dom.timeline.innerHTML = timeline.map((item) => {
            const eventType = String(item.type || "INFO");
            const seq = Number(item.seq || 0);
            const message = String(item.message || "");
            const ts = new Date(item.ts || Date.now()).toLocaleTimeString("zh-CN");
            return [
                '<div class="edge-timeline-item">',
                `<span class="edge-event-time">${ts}</span>`,
                `<span class="edge-event-type">${eventType}</span>`,
                `<span class="edge-event-seq">#${seq}</span>`,
                `<span class="edge-event-message">${message}</span>`,
                '</div>',
            ].join("");
        }).join("");
    }

    function render(state) {
        dom.sessionState.textContent = state.sessionState || "IDLE";
        dom.backendStatus.textContent = state.backendStatus || "unknown";
        dom.cameraStatus.textContent = state.cameraStatus || "stopped";
        if (dom.buttonStatus) {
            dom.buttonStatus.textContent = state.buttonStatus || "manual";
        }
        dom.queueSize.textContent = String(state.queueSize || 0);
        dom.serial.textContent = state.serialNumber || "-";
        dom.project.textContent = state.projectName || state.projectId || "-";
        dom.productType.textContent = state.productType || "-";
        dom.process.textContent = state.processName || "-";
        dom.countdown.textContent = String(state.countdownSeconds || state.tickSeconds || TICK_SECONDS);
        dom.lastSimilarity.textContent = formatSimilarity(state.lastSimilarity);
        if (state.lastUpload && state.lastUpload.status === "ok") {
            const status = formatQCStatusLabel(state.lastUpload.qcStatus || state.lastUpload.taskStatus || "pending");
            const latencyText = Number(state.lastUpload.latencyMs || 0) > 0
                ? ` / ${Number(state.lastUpload.latencyMs)}ms`
                : "";
            dom.lastUpload.textContent = `成功（task=${state.lastUpload.taskId || "-"} / ${status}${latencyText}）`;
            if (dom.lastConclusion) {
                dom.lastConclusion.textContent = buildQCConclusionText(state.lastUpload);
            }
        } else if (state.lastUpload && state.lastUpload.status === "failed") {
            dom.lastUpload.textContent = `失败（${state.lastUpload.message || "unknown"}）`;
            if (dom.lastConclusion) {
                dom.lastConclusion.textContent = "-";
            }
        } else {
            dom.lastUpload.textContent = "-";
            if (dom.lastConclusion) {
                dom.lastConclusion.textContent = "-";
            }
        }
        renderConclusionPanel(state.lastUpload);
        const sessionLocked = state.sessionState === "RUNNING" || state.sessionState === "ENDING";
        if (dom.projectSelect) {
            dom.projectSelect.disabled = sessionLocked;
        }
        if (dom.processSelect) {
            dom.processSelect.disabled = sessionLocked;
        }
        if (dom.productTypeSelect) {
            dom.productTypeSelect.disabled = sessionLocked;
        }
        if (dom.projectInput) {
            dom.projectInput.disabled = sessionLocked;
        }
        if (dom.productTypeInput) {
            dom.productTypeInput.disabled = sessionLocked;
        }
        if (dom.processInput) {
            dom.processInput.disabled = sessionLocked;
        }
        if (dom.configSaveBtn) {
            dom.configSaveBtn.disabled = sessionLocked;
        }
        if (dom.expectedScrewCount) {
            dom.expectedScrewCount.disabled = sessionLocked;
        }
        if (dom.specialProcesses) {
            dom.specialProcesses.disabled = sessionLocked;
        }
        if (dom.specialParts) {
            dom.specialParts.disabled = sessionLocked;
        }
        if (dom.extraFocus) {
            dom.extraFocus.disabled = sessionLocked;
        }
        if (dom.prePromptText) {
            dom.prePromptText.disabled = sessionLocked;
        }
        if (dom.promptGenerateBtn) {
            dom.promptGenerateBtn.disabled = sessionLocked;
        }
        if (dom.promptSaveBtn) {
            dom.promptSaveBtn.disabled = sessionLocked;
        }
        dom.endBtn.disabled = state.sessionState !== "RUNNING";
        renderTimeline(state.timeline || []);
    }

    store.subscribe(render);

    async function ensureCameraReady() {
        if (cameraAdapter && cameraAdapter.isReady()) {
            return;
        }
        const source = getCameraSource();
        const state = store.getState();
        const onBridgeFrameMeta = source === "local_bridge"
            ? (meta) => {
                const mock = Boolean(meta && meta.mock);
                const src = String((meta && meta.source) || "").trim().toLowerCase();
                const err = String((meta && meta.error) || "").trim();
                const signature = `${mock ? "1" : "0"}|${src}|${err}`;
                if (signature !== lastBridgeFrameMetaSignature) {
                    lastBridgeFrameMetaSignature = signature;
                    if (mock && err) {
                        setHint(src === "mvs"
                            ? `桥接已连通，但MVS相机未出帧：${err}`
                            : `桥接已连通，但相机未出帧：${err}`);
                    } else if (!mock && src) {
                        setHint(`相机预览已连接（${src}）`);
                    }
                }
                const targetStatus = source === "local_bridge"
                    ? (mock ? "bridge(mock)" : "bridge")
                    : source;
                if ((store.getState().cameraStatus || "") !== targetStatus) {
                    store.setState({ cameraStatus: targetStatus });
                }
            }
            : null;
        store.setState({ cameraStatus: source === "local_bridge" ? "starting(bridge)" : "starting" });
        cameraAdapter = window.MotorQCEdgeCamera.createAdapter({
            source,
            width: 1280,
            height: 720,
            baseUrl: getBridgeUrl(),
            stationId: state.stationId || "S01",
            fps: source === "local_bridge" ? 5 : 10,
            requestTimeoutMs: 2500,
            decodeTimeoutMs: 2200,
            onFrameMeta: onBridgeFrameMeta,
        });
        try {
            await cameraAdapter.start(dom.video, dom.canvas);
            applyPreviewMode(
                typeof cameraAdapter.getPreviewMode === "function"
                    ? cameraAdapter.getPreviewMode()
                    : "video"
            );
            if (source === "local_bridge" && typeof cameraAdapter.getLastFrameMeta === "function") {
                const meta = cameraAdapter.getLastFrameMeta();
                if (onBridgeFrameMeta) {
                    onBridgeFrameMeta(meta);
                } else {
                    store.setState({ cameraStatus: "bridge" });
                }
            } else {
                store.setState({ cameraStatus: source });
            }
        } catch (err) {
            if (source !== "mock") {
                // Fallback to mock when selected camera source is unavailable.
                cameraAdapter = window.MotorQCEdgeCamera.createAdapter({
                    source: "mock",
                    width: 1280,
                    height: 720,
                });
                await cameraAdapter.start(dom.video, dom.canvas);
                applyPreviewMode("canvas");
                store.setState({ cameraStatus: "mock" });
                setHint(`相机不可用，已切换模拟画面：${err.message || err}`);
                return;
            }
            store.setState({ cameraStatus: "error" });
            throw err;
        }
    }

    function refreshCameraPreview() {
        ensureCameraReady().catch((err) => {
            store.setState({ cameraStatus: "error" });
            setHint(`相机预览启动失败：${err.message || err}`);
        });
    }

    async function startButtonListener() {
        const source = getButtonSource();
        const state = store.getState();
        const shouldReuse = buttonAdapter && buttonSourceName === source;
        if (shouldReuse) {
            return;
        }

        if (buttonAdapter && typeof buttonAdapter.stop === "function") {
            buttonAdapter.stop();
        }
        buttonSourceName = source;
        buttonAdapter = window.MotorQCEdgeButton.createAdapter({
            source,
            baseUrl: getBridgeUrl(),
            stationId: state.stationId || "S01",
            pollMs: 300,
        });
        store.setState({
            buttonStatus: source === "manual" ? "manual" : `listening(${source})`,
        });
        await buttonAdapter.start((event) => {
            const snapshot = store.getState();
            if (snapshot.sessionState !== "RUNNING") {
                return;
            }
            const origin = String((event && event.source) || source);
            store.setState({ buttonStatus: `triggered(${origin})` });
            store.addTimelineEvent({
                type: "BUTTON_END",
                seq: Number(snapshot.seq || 0),
                message: `收到结束事件（${origin}）`,
            });
            endSessionNow(origin);
        });
    }

    function stopDecisionTimers() {
        if (tickIntervalId) {
            window.clearInterval(tickIntervalId);
            tickIntervalId = null;
        }
        if (countdownIntervalId) {
            window.clearInterval(countdownIntervalId);
            countdownIntervalId = null;
        }
    }

    function startDecisionTimers() {
        stopDecisionTimers();
        store.setState({ countdownSeconds: TICK_SECONDS, tickSeconds: TICK_SECONDS });
        countdownIntervalId = window.setInterval(() => {
            const current = store.getState();
            const next = current.countdownSeconds > 1 ? current.countdownSeconds - 1 : TICK_SECONDS;
            store.setState({ countdownSeconds: next });
        }, 1000);
        tickIntervalId = window.setInterval(runTickDecision, TICK_SECONDS * 1000);
    }

    function canvasToBlob(canvas) {
        return new Promise((resolve, reject) => {
            canvas.toBlob((blob) => {
                if (!blob) {
                    reject(new Error("capture blob is empty"));
                    return;
                }
                resolve(blob);
            }, "image/jpeg", 0.92);
        });
    }

    function buildFileName(state, seq, isFinal) {
        const serial = String(state.serialNumber || "UNKNOWN");
        const process = String(state.processName || "PROCESS").replace(/\s+/g, "_");
        const now = new Date();
        const date = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}`;
        const time = `${String(now.getHours()).padStart(2, "0")}${String(now.getMinutes()).padStart(2, "0")}${String(now.getSeconds()).padStart(2, "0")}`;
        const suffix = isFinal ? "final" : "chg";
        return `${serial}_${process}_${date}_${time}_seq${seq}_${suffix}.jpg`;
    }

    async function captureFramePayload(isFinal) {
        await ensureCameraReady();
        const canvas = cameraAdapter.captureFrame();
        if (!canvas) {
            throw new Error("capture failed: camera not ready");
        }
        if (dom.canvas) {
            dom.canvas.width = canvas.width;
            dom.canvas.height = canvas.height;
            const ctx = dom.canvas.getContext("2d");
            ctx.drawImage(canvas, 0, 0);
        }
        const state = store.getState();
        const seq = Number(state.seq || 0) + 1;
        const blob = await canvasToBlob(canvas);
        const frameHash = window.MotorQCEdgeSimilarity.frameHash(canvas);
        store.setState({ seq, countdownSeconds: TICK_SECONDS });
        return {
            seq,
            canvas,
            blob,
            frameHash,
            capturedAt: new Date().toISOString(),
            isFinal: Boolean(isFinal),
        };
    }

    async function pollTaskStatusAndUpdate(sessionState, responsePayload) {
        const taskId = Number(responsePayload && responsePayload.task_id) || 0;
        if (!taskId) {
            return;
        }
        try {
            const taskData = await api.getTask(taskId);
            const task = taskData && taskData.task ? taskData.task : null;
            if (!task) {
                return;
            }
            const bestResult = (task.best_result_json && typeof task.best_result_json === "object")
                ? task.best_result_json
                : {};
            const summary = String(bestResult.summary || bestResult.primary_reason || "").trim();
            const details = Array.isArray(bestResult.details) ? bestResult.details : [];
            const defects = details
                .map((row) => String((row && (row.best_reason || row.reason || row.detail_label)) || "").trim())
                .filter(Boolean)
                .slice(0, 5);
            const qcStatus = normalizeQCStatus(
                bestResult.overall_status ||
                bestResult.status ||
                task.status ||
                "pending"
            );
            store.setState({
                lastUpload: {
                    status: "ok",
                    taskId,
                    taskStatus: String(task.status || ""),
                    qcStatus,
                    qcSummary: summary,
                    qcFindings: defects.length,
                    qcConfidence: Number(bestResult.confidence || 0) || 0,
                    qcDefects: defects,
                    mode: "task_center",
                },
            });
            store.addTimelineEvent({
                type: "TASK_STATUS",
                seq: Number(sessionState.seq || 0),
                message: `任务状态 ${task.status || "pending"}${summary ? `：${summary.slice(0, 44)}` : ""}`,
            });
        } catch (_err) {
            // polling errors should not interrupt edge workflow
        }
    }

    async function uploadCapture(payload, isFinal, similarity) {
        const state = store.getState();
        const fileName = buildFileName(state, payload.seq, isFinal);
        const sessionContext = {
            stationId: state.stationId,
            projectId: state.projectId,
            projectName: state.projectName,
            processName: state.processName,
            serialNumber: state.serialNumber,
            productType: state.productType,
            uploadMode: state.uploadMode || (isManualConfigMode() ? "mobile_qc" : "task_center"),
            processContext: state.processContext || buildProcessContextPayload(),
        };
        const capturePayload = {
            seq: payload.seq,
            blob: payload.blob,
            fileName,
            capturedAt: payload.capturedAt,
            frameHash: payload.frameHash,
            isFinal,
            similarity: similarity || {},
        };
        const uploadStartedAt = Date.now();
        const response = await uploader.enqueueUpload(sessionContext, capturePayload);
        const latency = Date.now() - uploadStartedAt;
        const qcStatus = normalizeQCStatus(
            response.task_status ||
            response.qc_status ||
            response.status ||
            (response.raw && response.raw.status) ||
            (response.mode === "mobile_qc" ? "pending" : "pending")
        );
        const qcSummary = String(response.summary || (response.raw && response.raw.summary) || "").trim();
        const qcFindings = Number(
            response.findings_count ||
            (response.raw && Array.isArray(response.raw.findings) ? response.raw.findings.length : 0) ||
            0
        ) || 0;
        const qcDefects = (
            response.raw && Array.isArray(response.raw.findings)
                ? response.raw.findings.map((row) => {
                    if (row && typeof row === "object") {
                        return String(row.description || row.type || "").trim();
                    }
                    return String(row || "").trim();
                })
                : []
        ).filter(Boolean);
        const qcConfidence = Number(
            response.confidence ||
            (response.raw && response.raw.confidence) ||
            0
        ) || 0;
        store.setState({
            backendStatus: "ok",
            lastUpload: {
                status: "ok",
                taskId: Number(response.task_id || 0) || null,
                taskStatus: String(qcStatus || "pending"),
                qcStatus,
                qcSummary,
                qcFindings,
                qcDefects,
                qcConfidence,
                latencyMs: latency,
                mode: String(response.mode || "").trim() || sessionContext.uploadMode,
            },
        });
        const summaryShort = qcSummary ? (qcSummary.length > 48 ? `${qcSummary.slice(0, 48)}...` : qcSummary) : "";
        store.addTimelineEvent({
            type: isFinal ? "FINAL_UPLOAD" : "CHANGED_UPLOAD",
            seq: payload.seq,
            message: response.mode === "mobile_qc"
                ? `移动端QC识别完成（${formatQCStatusLabel(qcStatus)}，${latency}ms）${summaryShort ? ` ${summaryShort}` : ""}`
                : `上传成功（${latency}ms）`,
        });
        if (payload.frameHash) {
            lastUploadedFrameHash = String(payload.frameHash);
        }
        if (response.mode === "mobile_qc" && isFinal) {
            const finalText = buildQCConclusionText({
                status: "ok",
                qcStatus,
                qcSummary,
                qcFindings,
                qcConfidence,
            });
            if (finalText && finalText !== "-") {
                setHint(`最终图识别完成：${finalText}`);
            }
        }
        if (response.mode !== "mobile_qc") {
            await pollTaskStatusAndUpdate(store.getState(), response);
        }
    }

    async function runTickDecision() {
        const state = store.getState();
        if (state.sessionState !== "RUNNING") {
            return;
        }
        if (decisionInFlight || finalizingSession) {
            return;
        }
        decisionInFlight = true;
        try {
            const payload = await captureFramePayload(false);
            if (finalizingSession || store.getState().sessionState !== "RUNNING") {
                return;
            }
            const compare = window.MotorQCEdgeSimilarity.compareFrames(
                lastUploadedCanvas,
                payload.canvas,
                state.roiConfig || {}
            );
            store.setState({ lastSimilarity: compare.metrics || null });

            if (!compare.changed) {
                store.addTimelineEvent({
                    type: "UNCHANGED_SKIP",
                    seq: payload.seq,
                    message: "与上一张15秒上传帧一致，跳过上传",
                });
                return;
            }

            if (payload.frameHash && payload.frameHash === lastUploadedFrameHash) {
                store.addTimelineEvent({
                    type: "DUPLICATE_SKIP",
                    seq: payload.seq,
                    message: "帧哈希与上一上传一致，跳过重复上传",
                });
                return;
            }
            await uploadCapture(payload, false, compare.metrics || {});
            lastUploadedCanvas = payload.canvas;
        } catch (err) {
            store.setState({
                backendStatus: "error",
                lastUpload: {
                    status: "failed",
                    message: String(err.message || err),
                },
            });
            store.addTimelineEvent({
                type: "UPLOAD_FAIL",
                seq: Number(store.getState().seq || 0),
                message: `上传失败：${err.message || err}`,
            });
        } finally {
            decisionInFlight = false;
        }
    }

    function resolveRecommendation(recommendResp) {
        const recommendation = recommendResp && recommendResp.recommendation ? recommendResp.recommendation : {};
        return {
            recommendedProjectName: String(recommendation.recommended_project_name || "").trim(),
            recommendedProductType: String(recommendation.recommended_product_type || "").trim(),
        };
    }

    async function startSessionByScan(serialInput) {
        const serial = String(serialInput || "").trim();
        if (!serial) {
            setHint("请先扫码或输入序列号");
            return;
        }
        if (store.getState().sessionState === "RUNNING") {
            setHint("已有进行中会话，请先结束或重置");
            return;
        }

        setHint("正在根据扫码信息加载项目与工序...");
        store.setState({ backendStatus: "checking" });
        const stationId = String(dom.stationInput.value || "S01").trim() || "S01";
        const normalizedStationId = normalizeStationId(stationId);
        const operatorId = String(dom.operatorInput.value || "").trim();
        const configuredProjectId = getSelectedProjectId();
        const selectedProductType = getSelectedProductType();
        const configuredProcessName = getSelectedProcessName();
        const processContext = buildProcessContextPayload();
        const webPerm = hasWebQCPermission();
        const mobileQcPerm = hasMobileQCPermission();
        if (inEdgeLocalAuthMode() && !webPerm && !mobileQcPerm) {
            store.setState({ backendStatus: "error" });
            setHint("当前账号无 web:run_qc 且移动端QC接口不可用，无法提交识别");
            return;
        }
        if (!configuredProjectId) {
            store.setState({ backendStatus: "error" });
            setHint("请先选择项目并保存配置");
            setConfigStatus("未选择项目", true);
            return;
        }
        if (!configuredProcessName) {
            store.setState({ backendStatus: "error" });
            setHint("请先选择工序并保存配置");
            setConfigStatus("未选择工序", true);
            return;
        }

        let productType = "";
        let recommendedProjectName = "";
        try {
            const rec = await api.recommendSerial(serial, { current_project: configuredProjectId });
            const resolved = resolveRecommendation(rec);
            productType = resolved.recommendedProductType;
            recommendedProjectName = resolved.recommendedProjectName;
        } catch (_err) {
            // recommendation failure is non-fatal for edge start
        }

        try {
            if (!isManualConfigMode() && (!currentProjectConfig || getProjectIdFromItem(currentProjectConfig) !== configuredProjectId)) {
                currentProjectConfig = await resolveProjectConfig(configuredProjectId);
            }
            const processMeta = isManualConfigMode()
                ? {
                    name: configuredProcessName,
                    order: 1,
                    productType: selectedProductType || productType || "",
                }
                : findProcessMeta(currentProjectConfig, configuredProcessName, selectedProductType);
            if (!processMeta) {
                throw new Error("当前项目未找到已配置工序，请重新选择");
            }
            if (selectedProductType) {
                productType = selectedProductType;
            } else if (!productType) {
                productType = String(processMeta.productType || processMeta.product_type || "").trim();
            }
            let uploadMode = "task_center";
            if (mobileQcPerm) {
                uploadMode = "mobile_qc";
            } else if (!webPerm) {
                throw new Error("当前账号无可用识别接口（web_qc/mobile_qc）");
            }

            store.setState({
                sessionState: "RUNNING",
                stationId: normalizedStationId,
                operatorId,
                serialNumber: serial,
                projectId: configuredProjectId,
                projectName: getProjectNameFromItem(currentProjectConfig) || configuredProjectId,
                productType,
                processName: processMeta.name,
                processOrder: processMeta.order,
                uploadMode,
                processContext,
                seq: 0,
                tickSeconds: TICK_SECONDS,
                countdownSeconds: TICK_SECONDS,
                backendStatus: "ok",
                lastSimilarity: null,
                lastUpload: null,
                timeline: [],
            });
            saveConfig(false);
            lastUploadedCanvas = null;
            lastUploadedFrameHash = "";
            decisionInFlight = false;
            finalizingSession = false;
            await ensureCameraReady();
            await startButtonListener();
            startDecisionTimers();
            store.addTimelineEvent({
                type: "SESSION_START",
                seq: 0,
                message: `扫码开始：${serial}（${configuredProjectId}/${processMeta.name}）`,
            });
            if (
                recommendedProjectName &&
                recommendedProjectName !== (getProjectNameFromItem(currentProjectConfig) || "").trim()
            ) {
                setHint(`已开始（使用已配置项目/工序）；扫码推荐项目为：${recommendedProjectName}`);
            } else {
                const channelText = uploadMode === "mobile_qc"
                    ? "移动端一致上传+识别"
                    : "任务中心异步识别";
                setHint(`会话已开始，系统将每15秒判定一次变化（${channelText}）`);
            }
        } catch (err) {
            store.setState({ sessionState: "ERROR", backendStatus: "error" });
            setHint(`启动失败：${err.message || err}`);
        }
    }

    async function endSessionNow(triggerSource) {
        const state = store.getState();
        if (state.sessionState !== "RUNNING" || finalizingSession) {
            return;
        }
        finalizingSession = true;
        store.transition("ENDING");
        stopDecisionTimers();
        const sourceText = triggerSource ? `（${triggerSource}）` : "";
        setHint(`正在上传最终图${sourceText}...`);
        try {
            const payload = await captureFramePayload(true);
            await uploadCapture(payload, true, state.lastSimilarity || {});
            lastUploadedCanvas = payload.canvas;
            store.transition("CLOSED");
            store.addTimelineEvent({
                type: "SESSION_END",
                seq: payload.seq,
                message: `最终图上传成功${sourceText}，会话闭环`,
            });
            setHint("最终图已上传，工序会话完成");
        } catch (err) {
            store.transition("ERROR");
            store.setState({
                lastUpload: { status: "failed", message: String(err.message || err) },
                backendStatus: "error",
            });
            store.addTimelineEvent({
                type: "FINAL_UPLOAD_FAIL",
                seq: Number(store.getState().seq || 0),
                message: `最终图上传失败：${err.message || err}`,
            });
            setHint(`最终图上传失败，队列将重试：${err.message || err}`);
        } finally {
            finalizingSession = false;
        }
    }

    function resetSession() {
        stopDecisionTimers();
        lastUploadedCanvas = null;
        lastUploadedFrameHash = "";
        decisionInFlight = false;
        finalizingSession = false;
        store.resetForNextSession();
        syncConfiguredContextToStore();
        startButtonListener().catch(() => {
            store.setState({ buttonStatus: "error" });
        });
        setHint("已重置，等待扫码开始");
    }

    function bindEvents() {
        dom.centerBtn.addEventListener("click", () => setViewMode("center"));
        dom.edgeBtn.addEventListener("click", () => setViewMode("edge"));

        dom.scanBtn.addEventListener("click", () => startSessionByScan(dom.scanInput.value));
        dom.scanInput.addEventListener("keydown", (evt) => {
            if (evt.key === "Enter") {
                evt.preventDefault();
                startSessionByScan(dom.scanInput.value);
            }
        });
        dom.endBtn.addEventListener("click", () => endSessionNow("manual_button"));
        dom.resetBtn.addEventListener("click", resetSession);

        if (dom.projectSelect) {
            dom.projectSelect.addEventListener("change", async () => {
                if (isManualConfigMode()) {
                    return;
                }
                const snapshot = store.getState();
                if (snapshot.sessionState === "RUNNING" || snapshot.sessionState === "ENDING") {
                    setHint("会话进行中，不能切换项目");
                    if (snapshot.projectId) {
                        dom.projectSelect.value = snapshot.projectId;
                    }
                    return;
                }
                preferredProjectId = getSelectedProjectId();
                preferredProductType = "";
                preferredProcess = "";
                await refreshProjectSelection({
                    preferredProductType: preferredProductType,
                    preferredProcessName: preferredProcess,
                    persist: false,
                    silent: false,
                });
            });
        }
        if (dom.productTypeSelect) {
            dom.productTypeSelect.addEventListener("change", () => {
                if (isManualConfigMode()) {
                    return;
                }
                const snapshot = store.getState();
                if (snapshot.sessionState === "RUNNING" || snapshot.sessionState === "ENDING") {
                    setHint("会话进行中，不能切换产品类型");
                    if (dom.productTypeSelect) {
                        dom.productTypeSelect.value = String(snapshot.productType || "").trim();
                    }
                    return;
                }
                preferredProductType = getSelectedProductType();
                const currentProcessName = getSelectedProcessName();
                renderProcessOptions(currentProjectConfig, currentProcessName || preferredProcess || "");
                preferredProcess = getSelectedProcessName();
                loadPromptProfileForSelection();
                syncConfiguredContextToStore();
                setConfigStatus("产品类型已修改，点击“保存配置”生效", false);
            });
        }
        if (dom.processSelect) {
            dom.processSelect.addEventListener("change", () => {
                if (isManualConfigMode()) {
                    return;
                }
                const snapshot = store.getState();
                if (snapshot.sessionState === "RUNNING" || snapshot.sessionState === "ENDING") {
                    setHint("会话进行中，不能切换工序");
                    if (snapshot.processName) {
                        dom.processSelect.value = snapshot.processName;
                    }
                    return;
                }
                preferredProcess = getSelectedProcessName();
                loadPromptProfileForSelection();
                syncConfiguredContextToStore();
                setConfigStatus("工序已修改，点击“保存配置”生效", false);
            });
        }
        if (dom.projectInput) {
            dom.projectInput.addEventListener("change", () => {
                preferredProjectId = getSelectedProjectId();
                loadPromptProfileForSelection();
                syncConfiguredContextToStore();
                setConfigStatus("项目已修改，点击“保存配置”生效", false);
            });
        }
        if (dom.productTypeInput) {
            dom.productTypeInput.addEventListener("change", () => {
                preferredProductType = getSelectedProductType();
                loadPromptProfileForSelection();
                syncConfiguredContextToStore();
                setConfigStatus("产品类型已修改，点击“保存配置”生效", false);
            });
        }
        if (dom.processInput) {
            dom.processInput.addEventListener("change", () => {
                preferredProcess = getSelectedProcessName();
                loadPromptProfileForSelection();
                syncConfiguredContextToStore();
                setConfigStatus("工序已修改，点击“保存配置”生效", false);
            });
        }
        if (dom.configSaveBtn) {
            dom.configSaveBtn.addEventListener("click", () => {
                if (!getSelectedProjectId()) {
                    setConfigStatus("请先选择项目", true);
                    setHint("请先选择项目后再保存");
                    return;
                }
                if (!getSelectedProcessName()) {
                    setConfigStatus("请先选择工序", true);
                    setHint("请先选择工序后再保存");
                    return;
                }
                syncConfiguredContextToStore();
                saveConfig(true);
            });
        }
        if (dom.promptGenerateBtn) {
            dom.promptGenerateBtn.addEventListener("click", () => {
                const profile = getPromptProfileFromDom();
                const autoPrompt = buildAutoPrePrompt(profile, getCurrentProcessMeta());
                if (dom.prePromptText) {
                    dom.prePromptText.value = autoPrompt;
                }
                setPromptStatus("已按当前工序生成Prompt", false);
            });
        }
        if (dom.promptSaveBtn) {
            dom.promptSaveBtn.addEventListener("click", () => {
                savePromptProfileForSelection(true);
            });
        }
        const promptInputs = [
            dom.expectedScrewCount,
            dom.specialProcesses,
            dom.specialParts,
            dom.extraFocus,
            dom.prePromptText,
        ];
        for (const input of promptInputs) {
            if (!input) {
                continue;
            }
            input.addEventListener("change", () => {
                setPromptStatus("已修改，点击“保存预设”生效", false);
            });
        }

        if (dom.stationInput) {
            dom.stationInput.addEventListener("change", () => {
                const stationId = normalizeStationId(dom.stationInput.value || "S01");
                dom.stationInput.value = stationId;
                store.setState({ stationId });
                // Station changes need listener recreation for local bridge integrations.
                if (buttonAdapter && typeof buttonAdapter.stop === "function") {
                    buttonAdapter.stop();
                    buttonAdapter = null;
                }
                buttonSourceName = "";
                if (cameraAdapter && typeof cameraAdapter.stop === "function") {
                    cameraAdapter.stop();
                    cameraAdapter = null;
                    store.setState({ cameraStatus: "stopped" });
                }
                refreshCameraPreview();
                setConfigStatus("工位已修改，点击“保存配置”生效", false);
            });
        }
        if (dom.operatorInput) {
            dom.operatorInput.addEventListener("change", () => {
                store.setState({ operatorId: String(dom.operatorInput.value || "").trim() });
                setConfigStatus("操作员已修改，点击“保存配置”生效", false);
            });
        }
        if (dom.cameraSource) {
            dom.cameraSource.addEventListener("change", () => {
                if (cameraAdapter && typeof cameraAdapter.stop === "function") {
                    cameraAdapter.stop();
                    cameraAdapter = null;
                }
                applyPreviewMode(getCameraSource() === "browser" ? "video" : "canvas");
                store.setState({ cameraStatus: "stopped" });
                refreshCameraPreview();
                setConfigStatus("相机来源已修改，点击“保存配置”生效", false);
            });
        }
        if (dom.buttonSource) {
            dom.buttonSource.addEventListener("change", async () => {
                if (buttonAdapter && typeof buttonAdapter.stop === "function") {
                    buttonAdapter.stop();
                    buttonAdapter = null;
                }
                buttonSourceName = "";
                try {
                    await startButtonListener();
                } catch (_err) {
                    store.setState({ buttonStatus: "error" });
                }
                setConfigStatus("按钮来源已修改，点击“保存配置”生效", false);
            });
        }
        if (dom.bridgeUrl) {
            dom.bridgeUrl.addEventListener("change", () => {
                if (cameraAdapter && typeof cameraAdapter.stop === "function") {
                    cameraAdapter.stop();
                    cameraAdapter = null;
                    store.setState({ cameraStatus: "stopped" });
                }
                if (buttonAdapter && typeof buttonAdapter.stop === "function") {
                    buttonAdapter.stop();
                    buttonAdapter = null;
                }
                buttonSourceName = "";
                setConfigStatus("桥接地址已修改，点击“保存配置”生效", false);
                refreshCameraPreview();
            });
        }

        window.addEventListener("beforeunload", () => {
            stopDecisionTimers();
            if (cameraAdapter && typeof cameraAdapter.stop === "function") {
                cameraAdapter.stop();
                cameraAdapter = null;
            }
            if (buttonAdapter && typeof buttonAdapter.stop === "function") {
                buttonAdapter.stop();
                buttonAdapter = null;
            }
        });
    }

    function getInitialViewMode() {
        if (initialView === "edge") {
            return "edge";
        }
        try {
            const cached = String(window.localStorage.getItem("motor_qc_tasks_view_mode") || "").trim().toLowerCase();
            if (cached === "edge") {
                return "edge";
            }
        } catch (_err) {
            // ignore storage errors
        }
        return "center";
    }

    async function init() {
        applyInitialDefaults();
        bindEvents();
        await loadProjectAndProcessOptions();
        syncConfiguredContextToStore();
        setViewMode(getInitialViewMode());
        applyPreviewMode(getCameraSource() === "browser" ? "video" : "canvas");
        render(store.getState());
        try {
            await startButtonListener();
        } catch (_err) {
            store.setState({ buttonStatus: "error" });
        }
        refreshCameraPreview();
        if (getSelectedProjectId() && getSelectedProcessName()) {
            setHint("扫码开始，按钮结束；每15秒仅变化帧上传，最终图立即必传");
        } else {
            setHint("请先选择项目和工序并保存配置，然后扫码开始");
        }
        dom.scanInput.focus();
    }

    document.addEventListener("DOMContentLoaded", () => {
        init();
    });
}());
