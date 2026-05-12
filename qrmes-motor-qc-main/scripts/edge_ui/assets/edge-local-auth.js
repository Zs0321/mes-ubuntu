/* global window, document, fetch, URLSearchParams */
(function initEdgeLocalAuth() {
    "use strict";

    const STORAGE_KEY = "edge_local_mes_auth_v1";
    const DEFAULT_MES_BASE = "http://172.16.30.2:8891";
    const DEFAULT_BRIDGE_URL = "http://127.0.0.1:19091";

    function parseQuery() {
        return new URLSearchParams(window.location.search || "");
    }

    function normalizeMesBase(raw) {
        const text = String(raw || "").trim();
        if (!text) {
            return "";
        }
        if (text.startsWith("http://") || text.startsWith("https://")) {
            return text.replace(/\/$/, "");
        }
        return `http://${text}`.replace(/\/$/, "");
    }

    function normalizeStationId(raw) {
        return String(raw || "S01").trim().replace(/\^+$/, "") || "S01";
    }

    function readSavedAuth() {
        try {
            const raw = String(window.localStorage.getItem(STORAGE_KEY) || "").trim();
            if (!raw) {
                return {};
            }
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === "object" ? parsed : {};
        } catch (_err) {
            return {};
        }
    }

    function saveAuth(auth) {
        const payload = {
            mesBase: String(auth.mesBase || "").trim(),
            username: String(auth.username || "").trim(),
            protocol: String(auth.protocol || "smb").trim().toLowerCase(),
            updatedAt: new Date().toISOString(),
        };
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
        } catch (_err) {
            // ignore local storage failure
        }
    }

    function applyRuntimeDefaults() {
        const q = parseQuery();
        const saved = readSavedAuth();
        const stationId = normalizeStationId(q.get("station_id") || window.MOTOR_QC_EDGE_DEFAULT_STATION || "S01");
        const projectId = String(q.get("edge_project_id") || window.MOTOR_QC_EDGE_DEFAULT_PROJECT_ID || "").trim();
        const processName = String(q.get("edge_process_name") || window.MOTOR_QC_EDGE_DEFAULT_PROCESS_NAME || "").trim();
        const bridgeUrl = String(q.get("bridge_url") || window.MOTOR_QC_EDGE_DEFAULT_BRIDGE_URL || DEFAULT_BRIDGE_URL).trim();
        const mesBase = normalizeMesBase(
            q.get("mes_base") ||
            saved.mesBase ||
            DEFAULT_MES_BASE
        );

        window.MOTOR_QC_TASK_INITIAL_VIEW = "edge";
        window.MOTOR_QC_TASK_PROJECT_ID = "";
        window.MOTOR_QC_EDGE_DEFAULT_STATION = stationId;
        window.MOTOR_QC_EDGE_DEFAULT_PROJECT_ID = projectId;
        window.MOTOR_QC_EDGE_DEFAULT_PROCESS_NAME = processName;
        window.MOTOR_QC_EDGE_DEFAULT_BRIDGE_URL = bridgeUrl;
        window.MOTOR_QC_EDGE_DEFAULT_CAMERA_SOURCE = "local_bridge";
        window.MOTOR_QC_EDGE_DEFAULT_BUTTON_SOURCE = "local_bridge";
        window.EDGE_LOCAL_DEFAULT_MES_BASE = mesBase;
    }

    function installAPIProxyClient() {
        if (!window.MotorQCAPIClient) {
            return;
        }
        const api = new window.MotorQCAPIClient("/edge-api/proxy/motor-qc/api");
        api.recommendSerial = function recommendSerial(serialNumber, params) {
            const serial = String(serialNumber || "").trim();
            if (!serial) {
                return Promise.resolve({
                    success: false,
                    message: "serialNumber is required",
                });
            }
            const query = new URLSearchParams();
            if (params) {
                if (params.current_project) {
                    query.set("current_project", params.current_project);
                }
                if (params.current_product_type) {
                    query.set("current_product_type", params.current_product_type);
                }
            }
            const suffix = query.toString() ? `?${query.toString()}` : "";
            return this.requestAbsolute(`/edge-api/proxy/api/h2/recommend/${encodeURIComponent(serial)}${suffix}`);
        };
        window.motorQCAPI = api;
    }

    function updateAuthGlobals(status) {
        const payload = status && typeof status === "object" ? status : {};
        const loggedIn = Boolean(payload.logged_in);
        const projectsReadPerm = payload.projects_read_permission === true;
        const webPerm = payload.web_qc_permission === true;
        const mobileQcPerm = payload.mobile_qc_permission === true || payload.qc_api_permission === true;
        window.EDGE_LOCAL_AUTH_STATUS = payload;
        window.EDGE_LOCAL_LOGGED_IN = loggedIn;
        window.EDGE_LOCAL_PROJECTS_PERMISSION = projectsReadPerm;
        window.EDGE_LOCAL_WEB_QC_PERMISSION = webPerm;
        window.EDGE_LOCAL_MOBILE_QC_PERMISSION = mobileQcPerm;
        window.EDGE_LOCAL_QC_API_PERMISSION = mobileQcPerm;
        window.EDGE_LOCAL_FORCE_MANUAL_CONFIG = loggedIn && !webPerm;
    }

    function setAuthHint(text, isError) {
        const el = document.getElementById("mes-auth-hint");
        if (!el) {
            return;
        }
        el.textContent = text || "";
        el.style.color = isError ? "#b91c1c" : "";
    }

    function setAuthStatus(text, isError) {
        const el = document.getElementById("mes-auth-status");
        if (!el) {
            return;
        }
        el.textContent = text || "";
        el.style.color = isError ? "#b91c1c" : "";
    }

    function openAuthDialog() {
        const dialog = document.getElementById("mes-auth-dialog");
        if (!dialog) {
            return;
        }
        if (typeof dialog.showModal === "function") {
            dialog.showModal();
            return;
        }
        dialog.setAttribute("open", "open");
    }

    function closeAuthDialog() {
        const dialog = document.getElementById("mes-auth-dialog");
        if (!dialog) {
            return;
        }
        if (typeof dialog.close === "function") {
            dialog.close();
            return;
        }
        dialog.removeAttribute("open");
    }

    async function fetchAuthStatus(mesBase) {
        const query = new URLSearchParams();
        const normalized = normalizeMesBase(mesBase);
        if (normalized) {
            query.set("mes_base", normalized);
        }
        const url = `/edge-api/auth/status${query.toString() ? `?${query.toString()}` : ""}`;
        const resp = await fetch(url, { method: "GET", cache: "no-store" });
        return resp.json();
    }

    async function performLogin() {
        const mesBaseInput = document.getElementById("mes-base-input");
        const protocolSelect = document.getElementById("mes-protocol-select");
        const usernameInput = document.getElementById("mes-username-input");
        const passwordInput = document.getElementById("mes-password-input");

        const mesBase = normalizeMesBase(mesBaseInput && mesBaseInput.value);
        const protocol = String((protocolSelect && protocolSelect.value) || "smb").trim().toLowerCase() || "smb";
        const username = String((usernameInput && usernameInput.value) || "").trim();
        const password = String((passwordInput && passwordInput.value) || "").trim();

        if (!mesBase || !username || !password) {
            setAuthStatus("未登录", true);
            setAuthHint("MES 地址、用户名、密码均为必填", true);
            return;
        }

        setAuthStatus("登录中...", false);
        setAuthHint("正在建立 MES 会话...", false);
        const resp = await fetch("/edge-api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                mes_base: mesBase,
                protocol,
                username,
                password,
            }),
        });
        const payload = await resp.json();
        if (!resp.ok || !payload || !payload.ok) {
            updateAuthGlobals(payload || {});
            setAuthStatus("登录失败", true);
            setAuthHint((payload && payload.message) || `登录失败: HTTP ${resp.status}`, true);
            return;
        }

        updateAuthGlobals(payload || {});
        saveAuth({ mesBase, protocol, username });
        setAuthStatus(`已登录：${payload.username || username}`, false);
        if (payload.projects_read_permission === false) {
            setAuthHint("登录成功，但当前账号无法读取项目配置（/api/projects）", true);
        } else if (payload.web_qc_permission === false && payload.mobile_qc_permission === false) {
            setAuthHint("登录成功（无 web:run_qc，但支持项目配置读取；识别将按移动端接口权限判定）", false);
        } else if (payload.web_qc_permission === false) {
            setAuthHint("登录成功（无 web:run_qc，已切换手动项目/工序模式）", false);
        } else if (payload.mobile_qc_permission === false) {
            setAuthHint("登录成功（移动端QC接口不可用，将使用任务中心模式）", false);
        } else {
            setAuthHint("登录成功，正在刷新页面以加载项目/工序...", false);
        }
        closeAuthDialog();
        window.setTimeout(() => window.location.reload(), 350);
    }

    async function performLogout() {
        try {
            await fetch("/edge-api/auth/logout", { method: "POST" });
        } catch (_err) {
            // ignore
        }
        updateAuthGlobals({});
        setAuthStatus("未登录", false);
        setAuthHint("已退出 MES 登录", false);
    }

    function bindAuthEvents() {
        const loginBtn = document.getElementById("mes-login-btn");
        const logoutBtn = document.getElementById("mes-logout-btn");
        const openBtn = document.getElementById("mes-auth-open-btn");
        const closeBtn = document.getElementById("mes-auth-close-btn");
        const dialog = document.getElementById("mes-auth-dialog");
        const passwordInput = document.getElementById("mes-password-input");

        if (openBtn) {
            openBtn.addEventListener("click", () => {
                openAuthDialog();
            });
        }
        if (closeBtn) {
            closeBtn.addEventListener("click", () => {
                closeAuthDialog();
            });
        }
        if (dialog && typeof dialog.addEventListener === "function") {
            dialog.addEventListener("click", (evt) => {
                const rect = dialog.getBoundingClientRect();
                const outside = (
                    evt.clientX < rect.left ||
                    evt.clientX > rect.right ||
                    evt.clientY < rect.top ||
                    evt.clientY > rect.bottom
                );
                if (outside) {
                    closeAuthDialog();
                }
            });
        }
        if (loginBtn) {
            loginBtn.addEventListener("click", () => {
                performLogin().catch((err) => {
                    setAuthStatus("登录失败", true);
                    setAuthHint(`登录异常: ${err.message || err}`, true);
                });
            });
        }
        if (logoutBtn) {
            logoutBtn.addEventListener("click", () => {
                performLogout().catch(() => {
                    setAuthStatus("未登录", false);
                });
            });
        }
        if (passwordInput) {
            passwordInput.addEventListener("keydown", (evt) => {
                if (evt.key === "Enter") {
                    evt.preventDefault();
                    if (loginBtn) {
                        loginBtn.click();
                    }
                }
            });
        }
    }

    function fillAuthFormDefaults() {
        const saved = readSavedAuth();
        const mesBaseInput = document.getElementById("mes-base-input");
        const protocolSelect = document.getElementById("mes-protocol-select");
        const usernameInput = document.getElementById("mes-username-input");

        const mesBase = window.EDGE_LOCAL_DEFAULT_MES_BASE || saved.mesBase || DEFAULT_MES_BASE;
        const protocol = String(saved.protocol || "smb").trim().toLowerCase() || "smb";
        const username = String(saved.username || "").trim();

        if (mesBaseInput && mesBase) {
            mesBaseInput.value = mesBase;
        }
        if (protocolSelect) {
            protocolSelect.value = protocol === "webdav" ? "webdav" : "smb";
        }
        if (usernameInput && username) {
            usernameInput.value = username;
        }
    }

    async function initAuthPanel() {
        fillAuthFormDefaults();
        bindAuthEvents();
        const mesBaseInput = document.getElementById("mes-base-input");
        const mesBase = normalizeMesBase(mesBaseInput && mesBaseInput.value);
        try {
            const status = await fetchAuthStatus(mesBase);
            updateAuthGlobals(status || {});
            if (status && status.logged_in) {
                setAuthStatus(`已登录：${status.username || "-"}`, false);
                if (status.projects_read_permission === false) {
                    setAuthHint("MES 会话有效，但无法读取项目配置（/api/projects）", true);
                } else if (status.web_qc_permission === false && status.mobile_qc_permission === false) {
                    setAuthHint("MES 会话有效（无 web:run_qc 且移动端QC不可用，仅可预览）", true);
                } else if (status.web_qc_permission === false) {
                    setAuthHint("MES 会话有效（无 web:run_qc，使用手动项目/工序 + 移动端QC模式）", false);
                } else if (status.mobile_qc_permission === false) {
                    setAuthHint("MES 会话有效（移动端QC接口不可用，使用任务中心模式）", false);
                } else {
                    setAuthHint("MES 会话有效，可直接扫码开始", false);
                }
            } else {
                setAuthStatus("未登录", false);
                const reason = status && status.last_error ? `（${status.last_error}）` : "";
                setAuthHint(`请先登录 MES 后再开始识别${reason}`, false);
            }
        } catch (err) {
            updateAuthGlobals({});
            setAuthStatus("状态获取失败", true);
            setAuthHint(`无法连接本地桥接服务：${err.message || err}`, true);
        }
    }

    applyRuntimeDefaults();
    installAPIProxyClient();
    document.addEventListener("DOMContentLoaded", () => {
        initAuthPanel().catch((err) => {
            setAuthStatus("初始化失败", true);
            setAuthHint(`登录模块初始化失败：${err.message || err}`, true);
        });
    });
}());
