const f2 = (n) => Number(n || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money = (n) => `￥${f2(n)}`;
const signedMoney = (n) => `${Number(n || 0) >= 0 ? "+" : "-"}${money(Math.abs(Number(n || 0)))}`;
const f4 = (n) => Number(n || 0).toLocaleString("zh-CN", { minimumFractionDigits: 4, maximumFractionDigits: 4 });

const state = {
  data: null,
  loadMode: "static",
  activeView: "finance",
  financeModule: "warehouse-recheck",
  showBreakdown: false,
  scenarioItems: {},
  scenarios: [],
  financeScenario: null,
  engineerScenario: null,
  bomHeaders: [],
  lastExcelScenarioId: null,
  lastExcelQuotePayload: null,
  lastExcelQuotePayloads: [],
  excelQuoteTaskId: null,
  excelQuotePollToken: 0,
  aiRouteTaskId: null,
  aiRoutePollToken: 0,
  lastAiRoutePayload: null,
  singleBomQuotePayload: null,
  bomHeadersStatus: "idle",
  bomHeadersMessage: "",
  bomHeadersKeyword: "",
  bomHeadersOffset: 0,
  bomHeadersHasMore: false,
  selectedFinanceBomNumber: "",
  selectedFinanceBomLabel: "",
  financeStatusFilter: "all",
  nameSpecBands: [],
  nameSpecBandConfigPath: "",
};

const EXCEL_PASTE_HEADER_ALIASES = {
  code: ["物料编码", "子项物料编码", "子件物料编码", "子项编码", "组件编码", "编码", "料号", "物料号", "materialcode", "code", "itemcode"],
  name: ["物料名称", "子项名称", "子件物料名称", "零件名称", "名称", "品名", "materialname", "name", "itemname"],
  spec: ["规格", "规格型号", "型号", "型号规格", "规格/型号", "spec", "specification", "itemmodel"],
  material: ["材质", "材料", "材质/材料", "材质牌号", "原材料", "材料名称", "material", "materialtype"],
  weight_kg: ["单件重量kg", "重量kg", "单重kg", "净重kg", "重量", "单件重量", "单件净重", "每件重量", "单重", "weightkg", "weight", "netweight"],
  qty: ["数量", "用量", "qty", "quantity", "单位用量", "单台用量", "件数", "需求数量", "数量/台"],
  process: ["工艺", "工序", "process", "processtype", "工艺路线", "加工工艺", "制造工艺", "工序名称", "工艺名称"],
  current_unit_price: ["采购单价", "当前单价", "参考单价", "含税单价", "未税单价", "最近采购价", "参考采购价", "单价", "单价(元)", "price", "currentunitprice"],
};

const VOLUME_TIER_PRESETS = {
  300: {
    label: "300套/年",
    discountSummary: "轻试量产折扣：材料约 0.5%-3%，工艺约 3%-6%",
  },
  1000: {
    label: "1000套/年",
    discountSummary: "轻中量产折扣：材料约 1%-4%，工艺约 4%-8%",
  },
  3000: {
    label: "3000套/年",
    discountSummary: "中档量产折扣：材料约 1.5%-5%，工艺约 5%-10%",
  },
  5000: {
    label: "5000套/年",
    discountSummary: "标准量产折扣：材料约 1%-6%，工艺约 3%-12%",
  },
  8000: {
    label: "8000套/年",
    discountSummary: "增强量产折扣：材料约 2%-10%，工艺约 6%-16%",
  },
  10000: {
    label: "10000套/年",
    discountSummary: "增强量产折扣：材料约 2%-12%，工艺约 6%-22%",
  },
  20000: {
    label: "20000套/年",
    discountSummary: "中高量产折扣：材料约 3%-12%，工艺约 8%-22%",
  },
  50000: {
    label: "50000套/年",
    discountSummary: "高量产折扣：材料约 4%-15%，工艺约 10%-26%",
  },
  100000: {
    label: "100000套/年",
    discountSummary: "超高量产折扣：材料约 5%-18%，工艺约 12%-32%",
  },
};

function setNodeText(selector, text) {
  const node = document.querySelector(selector);
  if (node) node.textContent = text;
}

function setLabelText(controlId, text) {
  const control = document.getElementById(controlId);
  const label = control?.closest("label");
  if (!label) return;
  const textNode = Array.from(label.childNodes).find((node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
  if (textNode) {
    textNode.textContent = `${text}\n                  `;
  }
}

function resolveFinanceApiBase() {
  const explicit = String(window.FINANCE_DEMO_API_BASE || document.body?.dataset?.financeApiBase || "").trim();
  return explicit.replace(/\/$/, "");
}

function buildFinanceApiTargets(path) {
  const normalizedPath = String(path || "").startsWith("/") ? String(path || "") : `/${String(path || "")}`;
  const explicit = resolveFinanceApiBase();
  if (explicit) return [`${explicit}${normalizedPath}`];

  const targets = [normalizedPath];
  try {
    const url = new URL(window.location.href);
    const currentPort = String(url.port || (url.protocol === "https:" ? "443" : "80"));
    if (currentPort !== "9003") {
      targets.push(`${url.protocol}//${url.hostname}:9003${normalizedPath}`);
    }
  } catch (_) {
    // ignore URL parsing failure and keep relative path only
  }
  return [...new Set(targets)];
}

async function apiFetchResponse(path, options = {}, requestLabel = "请求") {
  const targets = buildFinanceApiTargets(path);
  let lastResponse = null;
  let lastTarget = targets[targets.length - 1] || String(path || "");
  let lastError = null;

  for (const target of targets) {
    lastTarget = target;
    let response;
    try {
      response = await fetch(target, options);
    } catch (error) {
      lastError = error;
      continue;
    }
    if (response.status === 404 && target !== targets[targets.length - 1]) {
      lastResponse = response;
      continue;
    }
    return { response, target };
  }

  if (lastError) {
    throw new Error(`当前页面未连接到 finance_demo 报价接口：${requestLabel}失败，无法访问 ${lastTarget}。请确认页面所在服务已挂载报价 API，或显式设置 FINANCE_DEMO_API_BASE。`);
  }
  return { response: lastResponse, target: lastTarget };
}

async function apiFetchJson(path, options = {}, requestLabel = "请求") {
  const { response, target } = await apiFetchResponse(path, options, requestLabel);
  const contentType = String(response.headers.get("content-type") || "").toLowerCase();
  const isJson = contentType.includes("application/json");
  const payload = isJson ? await response.json().catch(() => ({})) : await response.text().catch(() => "");
  if (!response.ok) {
    const message = isJson
      ? (payload.message || payload.error || `${requestLabel}失败(${response.status})`)
      : `${requestLabel}失败(${response.status})`;
    if (response.status === 401 || response.status === 403) {
      throw new Error(`${message}：请先登录当前报价系统，或确认当前页面连接的是 finance_demo 后端。`);
    }
    if (response.status === 404) {
      throw new Error(`${message}：当前页面未连接到 finance_demo 报价接口 ${target}。`);
    }
    throw new Error(message);
  }
  return isJson ? payload : { success: true, raw_text: payload };
}

async function apiFetchBlob(path, options = {}, requestLabel = "请求") {
  const { response, target } = await apiFetchResponse(path, options, requestLabel);
  if (!response.ok) {
    const contentType = String(response.headers.get("content-type") || "").toLowerCase();
    let message = `${requestLabel}失败(${response.status})`;
    try {
      if (contentType.includes("application/json")) {
        const payload = await response.json();
        message = payload.message || payload.error || message;
      }
    } catch (_) {
      // ignore
    }
    if (response.status === 401 || response.status === 403) {
      throw new Error(`${message}：请先登录当前报价系统，或确认当前页面连接的是 finance_demo 后端。`);
    }
    if (response.status === 404) {
      throw new Error(`${message}：当前页面未连接到 finance_demo 报价接口 ${target}。`);
    }
    throw new Error(message);
  }
  return { blob: await response.blob(), disposition: response.headers.get("Content-Disposition") || "" };
}

function getVolumeTierPresetMeta(value) {
  const normalized = String(Math.max(0, Math.round(normalizeNumber(value || 0)))).trim();
  return VOLUME_TIER_PRESETS[normalized] || null;
}

function getDetailedVolumeTierLabel(value) {
  const volume = Math.max(0, Math.round(normalizeNumber(value || 0)));
  if (volume <= 300) return "<=300";
  if (volume <= 1000) return "301-1000";
  if (volume <= 3000) return "1001-3000";
  if (volume <= 5000) return "3001-5000";
  if (volume <= 8000) return "5001-8000";
  if (volume <= 10000) return "8001-10000";
  if (volume <= 20000) return "10001-20000";
  if (volume <= 50000) return "20001-50000";
  return ">50000";
}

function getSharedDiscountBandLabel(value) {
  const volume = Math.max(0, Math.round(normalizeNumber(value || 0)));
  if (volume <= 300) return "<=300套/年";
  if (volume <= 1000) return "301-1000套/年";
  if (volume <= 3000) return "1001-3000套/年";
  if (volume <= 5000) return "3001-5000套/年";
  if (volume <= 8000) return "5001-8000套/年";
  if (volume <= 10000) return "8001-10000套/年";
  if (volume <= 20000) return "10001-20000套/年";
  if (volume <= 50000) return "20001-50000套/年";
  return ">50000套/年";
}

function buildMassVolumeRequestLabel(value) {
  const volume = Math.max(0, Math.round(normalizeNumber(value || 0)));
  if (volume <= 0) return "量产";
  return `${volume}套/年（显示档位 ${getDetailedVolumeTierLabel(volume)}；折扣档位 ${getSharedDiscountBandLabel(volume)}）`;
}

function parseAnnualVolumeInputValues(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return [];
  return [...new Set(
    raw
      .split(/[，,、;；\s]+/)
      .map((part) => Math.max(0, Math.round(normalizeNumber(String(part || "").trim()))))
      .filter((part) => part > 0)
  )].sort((a, b) => a - b);
}

function getExcelQuoteAnnualVolumeInputNode() {
  return document.getElementById("excelQuoteAnnualVolume");
}

function clearExcelQuoteMultiVolumeSelection() {
  const field = document.getElementById("excelQuoteVolumeMultiField");
  if (!field) return;
  field.querySelectorAll("[data-multi-volume].is-active").forEach((button) => {
    button.classList.remove("is-active");
    button.setAttribute("aria-pressed", "false");
  });
}

function syncExcelQuoteAnnualVolumeDisplay(selected = getExcelQuoteSelectedAnnualVolumes(), { preserveManual = false } = {}) {
  const input = getExcelQuoteAnnualVolumeInputNode();
  if (!input) return;
  if (selected.length) {
    if (!preserveManual && parseAnnualVolumeInputValues(input.value).length <= 1) {
      const manualValue = Math.max(0, Math.round(normalizeNumber(input.value || 0)));
      input.dataset.manualValue = manualValue > 0 ? String(manualValue) : (input.dataset.manualValue || "10000");
    }
    input.value = selected.join(", ");
    input.dataset.multiDisplay = "1";
    return;
  }
  if (input.dataset.multiDisplay === "1") {
    const restored = String(input.dataset.manualValue || "10000").trim();
    input.value = restored || "10000";
  }
  input.dataset.multiDisplay = "0";
}

function updateExcelQuoteMultiVolumeState() {
  const field = document.getElementById("excelQuoteVolumeMultiField");
  const summaryNode = document.getElementById("excelQuoteVolumeMultiSummary");
  if (!field || !summaryNode) return;
  const selected = [...field.querySelectorAll("[data-multi-volume].is-active")]
    .map((button) => Math.max(0, Math.round(normalizeNumber(button.dataset.multiVolume || 0))))
    .filter((value) => value > 0)
    .sort((a, b) => a - b);
  field.querySelectorAll("[data-multi-volume]").forEach((button) => {
    const active = selected.includes(Math.max(0, Math.round(normalizeNumber(button.dataset.multiVolume || 0))));
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  syncExcelQuoteAnnualVolumeDisplay(selected);
  updateVolumeTierPresetState("excelQuoteAnnualVolume");
  summaryNode.textContent = selected.length
    ? `本次会分别生成 ${selected.length} 组量产报价：${selected.map((volume) => buildMassVolumeRequestLabel(volume)).join("；")}`
    : "未勾选时按上方单个年产量报价；勾选后会分别生成多个量产报价结果。";
  refreshProductionModeHint("excelQuoteProductionMode", "excelQuoteAnnualVolume", "excelQuoteProductionModeHint", {
    sample: "样品/小批：按当前参考价直接测算，不启用年产量。",
    mass: "量产：会额外生成批量测算结果，并把年产量传给 AI 作为量产参考。",
  });
}

function bindExcelQuoteMultiVolumeField() {
  const field = document.getElementById("excelQuoteVolumeMultiField");
  if (!field || field.dataset.bound === "1") return;
  field.dataset.bound = "1";
  field.querySelectorAll("[data-multi-volume]").forEach((button) => {
    button.addEventListener("click", () => {
      button.classList.toggle("is-active");
      updateExcelQuoteMultiVolumeState();
    });
  });
  const input = getExcelQuoteAnnualVolumeInputNode();
  if (input && input.dataset.multiBound !== "1") {
    input.dataset.multiBound = "1";
    const syncFromInput = () => {
      const parsed = parseAnnualVolumeInputValues(input.value);
      if (parsed.length <= 1) {
        input.dataset.manualValue = parsed[0] ? String(parsed[0]) : String(input.dataset.manualValue || input.value || "10000").trim();
      }
      field.querySelectorAll("[data-multi-volume]").forEach((button) => {
        const volume = Math.max(0, Math.round(normalizeNumber(button.dataset.multiVolume || 0)));
        const active = parsed.length > 1 && parsed.includes(volume);
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
      if (parsed.length > 1) {
        syncExcelQuoteAnnualVolumeDisplay(parsed, { preserveManual: true });
      } else {
        input.dataset.multiDisplay = "0";
      }
      updateExcelQuoteMultiVolumeState();
    };
    input.addEventListener("change", syncFromInput);
    input.addEventListener("blur", syncFromInput);
  }
  updateExcelQuoteMultiVolumeState();
}

function getExcelQuoteSelectedAnnualVolumes() {
  const field = document.getElementById("excelQuoteVolumeMultiField");
  const input = getExcelQuoteAnnualVolumeInputNode();
  const activeVolumes = field
    ? [...field.querySelectorAll("[data-multi-volume].is-active")]
        .map((button) => Math.max(0, Math.round(normalizeNumber(button.dataset.multiVolume || 0))))
        .filter((value) => value > 0)
    : [];
  const inputVolumes = input ? parseAnnualVolumeInputValues(input.value) : [];
  const combined = inputVolumes.length > 1 ? [...activeVolumes, ...inputVolumes] : activeVolumes;
  return [...new Set(combined)].sort((a, b) => a - b);
}

function updateVolumeTierPresetState(inputId) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const parsedValues = parseAnnualVolumeInputValues(input.value);
  const normalizedValue = String(Math.max(0, Math.round(normalizeNumber(parsedValues[0] || input.value || 0)))).trim();
  const presetMeta = parsedValues.length > 1 ? null : getVolumeTierPresetMeta(normalizedValue);
  const discountNode = document.querySelector(`.volume-tier-discount[data-target-input="${inputId}"]`);
  if (discountNode) {
    discountNode.textContent = parsedValues.length > 1
      ? `多档量产：${parsedValues.map((value) => `${value}套/年`).join("，")}；会分别按各自量产档位测算。`
      : (presetMeta
          ? `${presetMeta.label}：${presetMeta.discountSummary}`
          : `手动输入：当前为 ${normalizedValue || '-'} 套/年，折扣力度按实际量产年产量测算。`);
  }
  document.querySelectorAll(`.volume-tier-presets[data-target-input="${inputId}"] .volume-tier-chip`).forEach((button) => {
    const matched = parsedValues.length <= 1 && String(button.dataset.volume || "").trim() === normalizedValue;
    button.classList.toggle("is-active", matched);
    button.setAttribute("aria-pressed", matched ? "true" : "false");
    const meta = getVolumeTierPresetMeta(button.dataset.volume || "");
    if (meta?.discountSummary) button.title = meta.discountSummary;
  });
}

function bindVolumeTierPresets(inputId) {
  const input = document.getElementById(inputId);
  const container = document.querySelector(`.volume-tier-presets[data-target-input="${inputId}"]`);
  if (!input || !container || container.dataset.bound === "1") return;
  container.dataset.bound = "1";
  const refreshHint = () => {
    if (inputId === "excelQuoteAnnualVolume") {
      refreshProductionModeHint("excelQuoteProductionMode", "excelQuoteAnnualVolume", "excelQuoteProductionModeHint", {
        sample: "样品/小批：按当前参考价直接测算，不启用年产量。",
        mass: "量产：会额外生成批量测算结果，并把年产量传给 AI 作为量产参考。",
      });
    } else if (inputId === "singleBomAnnualVolume") {
      refreshProductionModeHint("singleBomProductionMode", "singleBomAnnualVolume", "singleBomProductionModeHint", {
        sample: "样品/小批：按当前材料、重量和工艺直接试算，不启用年产量。",
        mass: "量产：会把年产量传给 AI，并额外生成量产测算参考。",
      });
    }
  };
  container.querySelectorAll(".volume-tier-chip").forEach((button) => {
    button.addEventListener("click", () => {
      const nextValue = String(button.dataset.volume || "").trim();
      if (inputId === "excelQuoteAnnualVolume") {
        clearExcelQuoteMultiVolumeSelection();
        input.dataset.manualValue = nextValue;
        input.dataset.multiDisplay = "0";
      }
      input.value = nextValue;
      updateVolumeTierPresetState(inputId);
      if (inputId === "excelQuoteAnnualVolume") {
        updateExcelQuoteMultiVolumeState();
      }
      refreshHint();
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
  input.addEventListener("input", () => {
    if (inputId === "excelQuoteAnnualVolume" && parseAnnualVolumeInputValues(input.value).length <= 1) {
      input.dataset.manualValue = String(input.value || "").trim();
    }
    updateVolumeTierPresetState(inputId);
    refreshHint();
  });
  input.addEventListener("change", () => {
    if (inputId === "excelQuoteAnnualVolume" && parseAnnualVolumeInputValues(input.value).length <= 1) {
      input.dataset.manualValue = String(input.value || "").trim();
    }
    updateVolumeTierPresetState(inputId);
    refreshHint();
  });
  updateVolumeTierPresetState(inputId);
  refreshHint();
}

function refreshProductionModeHint(modeSelectId, annualInputId, hintId, messages = {}) {
  const modeSelect = document.getElementById(modeSelectId);
  const annualInput = document.getElementById(annualInputId);
  const hint = document.getElementById(hintId);
  if (!modeSelect || !annualInput || !hint) return;
  const isMass = (modeSelect.value || "sample") === "mass";
  const presetMeta = getVolumeTierPresetMeta(annualInput.value);
  const selectedMassVolumes = modeSelectId === "excelQuoteProductionMode" ? getExcelQuoteSelectedAnnualVolumes() : [];
  hint.classList.toggle("sample", !isMass);
  hint.classList.toggle("mass", isMass);
  hint.textContent = isMass
    ? (selectedMassVolumes.length
        ? `${messages.mass || "量产：会额外生成批量测算结果，并把年产量传给 AI 作为量产参考。"} 当前已勾选 ${selectedMassVolumes.map((volume) => buildMassVolumeRequestLabel(volume)).join("；")}。`
        : (presetMeta
            ? `${messages.mass || "量产：会额外生成批量测算结果，并把年产量传给 AI 作为量产参考。"} 当前档位 ${presetMeta.label}，${presetMeta.discountSummary}。`
            : `${messages.mass || "量产：会额外生成批量测算结果，并把年产量传给 AI 作为量产参考。"} 当前为手动输入年产量，折扣力度会按实际年产量测算。`))
    : (messages.sample || "样品/小批：按当前参考价直接测算，不启用年产量。");
}

function syncProductionModeUi(modeSelectId, annualFieldId, annualInputId, hintId, messages = {}) {
  const modeSelect = document.getElementById(modeSelectId);
  const annualField = document.getElementById(annualFieldId);
  const annualInput = document.getElementById(annualInputId);
  const hint = document.getElementById(hintId);
  if (!modeSelect || !annualField || !annualInput || !hint) return;

  bindVolumeTierPresets(annualInputId);
  if (modeSelectId === "excelQuoteProductionMode") {
    bindExcelQuoteMultiVolumeField();
  }
  const isMass = (modeSelect.value || "sample") === "mass";
  annualField.classList.toggle("hidden", !isMass);
  annualField.classList.toggle("is-active", isMass);
  annualInput.disabled = !isMass;
  if (!isMass) {
    annualInput.setAttribute("aria-hidden", "true");
  } else {
    annualInput.removeAttribute("aria-hidden");
    if (normalizeNumber(annualInput.value) <= 0) annualInput.value = 10000;
  }
  if (modeSelectId === "excelQuoteProductionMode") {
    const multiField = document.getElementById("excelQuoteVolumeMultiField");
    if (multiField) multiField.classList.toggle("hidden", !isMass);
    updateExcelQuoteMultiVolumeState();
  }
  updateVolumeTierPresetState(annualInputId);
  refreshProductionModeHint(modeSelectId, annualInputId, hintId, messages);
}

function getMassAnnualVolume(items = getActiveItems()) {
  if (!Array.isArray(items) || !items.length) return 0;
  return normalizeNumber(
    items[0]?.annual_volume
    || items[0]?.annualVolume
    || state.lastExcelQuotePayload?.model?.annual_volume
    || 0
  );
}

function formatMassAnnualVolumeLabel(items = getActiveItems()) {
  const annualVolume = getMassAnnualVolume(items);
  return annualVolume > 0 ? `${Math.round(annualVolume)}套/年` : "量产";
}

function setBomHeadersState(status, message = "") {
  state.bomHeadersStatus = status;
  state.bomHeadersMessage = message;
}

function normalizeKingdeeBomHeaderErrorMessage(errorCode = "", message = "") {
  const code = String(errorCode || "").trim();
  const text = String(message || "").trim();
  const lowered = text.toLowerCase();
  if (code === "KINGDEE_CONFIG_MISSING") return "金蝶未配置完成，暂时无法加载型号";
  if (code === "KINGDEE_UPSTREAM_ERROR") {
    if (text.includes("签名失败")) return `金蝶接口登录失败：${text}`;
    if (text.includes("当前尝试登录的数据中心无法获取到")) return `金蝶数据中心配置异常：${text}`;
    if (lowered.includes("invalid json response from kingdee")) return "金蝶接口返回了非 JSON 响应，请检查 base_url 是否指向 /k3cloud 入口以及第三方应用签名是否有效";
    return text ? `金蝶接口异常：${text}` : "金蝶接口异常，暂时无法加载型号";
  }
  return text || "金蝶接口异常，暂时无法加载型号";
}

function getBomHeaderPlaceholder() {
  if ((state.bomHeaders || []).length) return "请选择金蝶已有型号";
  if (state.bomHeadersStatus === "config_missing") return "金蝶未配置完成，暂时无法加载型号";
  if (state.bomHeadersStatus === "upstream_error") return state.bomHeadersMessage || "金蝶接口异常，暂时无法加载型号";
  if (state.bomHeadersStatus === "empty") return "当前未查询到匹配型号";
  if (state.bomHeadersStatus === "loading") return "金蝶型号加载中...";
  return "未加载到金蝶型号";
}

function getBomHeaderLabel(item, fallback = "") {
  return item?.parent_name || item?.bom_name || item?.bom_number || fallback || "";
}

function updateFinanceBomSelectionSummary(bomNumber = "", label = "") {
  const normalizedBomNumber = String(bomNumber || "").trim();
  const selected = (state.bomHeaders || []).find((item) => item.bom_number === normalizedBomNumber);
  const resolvedBomNumber = selected?.bom_number || normalizedBomNumber;
  const resolvedLabel = label || getBomHeaderLabel(selected, resolvedBomNumber);
  const valueNode = document.getElementById("financeBomSelectionValue");
  const hintNode = document.getElementById("financeBomSelectionHint");
  if (!valueNode || !hintNode) return;

  if (!resolvedBomNumber) {
    state.selectedFinanceBomNumber = "";
    state.selectedFinanceBomLabel = "";
    valueNode.textContent = "未选中有效 BOM 编号";
    hintNode.textContent = "请先从下拉框选择一个金蝶已有型号，再点击“开始报价测算”。";
    return;
  }

  state.selectedFinanceBomNumber = resolvedBomNumber;
  state.selectedFinanceBomLabel = resolvedLabel || resolvedBomNumber;
  valueNode.textContent = `${state.selectedFinanceBomLabel} | ${resolvedBomNumber}`;
  hintNode.textContent = "当前按钮会按这个 BOM 编号发起金蝶明细导入。";
}

function ensureExcelQuoteProgressUi() {
  const panel = document.getElementById("excelQuoteProgressPanel");
  if (!panel) return;
  let meta = panel.querySelector(".excel-progress-meta");
  if (!meta) {
    meta = document.createElement("div");
    meta.className = "excel-progress-meta";
    meta.innerHTML = [
      '<span id="excelQuoteProgressStageTag" class="excel-progress-stage">未启动</span>',
      '<span id="excelQuoteProgressDetail" class="excel-progress-detail">上传后会立即创建报价任务</span>',
    ].join("");
    const head = panel.querySelector(".excel-progress-head");
    if (head && head.nextSibling) {
      panel.insertBefore(meta, head.nextSibling);
    } else {
      panel.appendChild(meta);
    }
  }
  let plan = panel.querySelector(".script-plan-card");
  if (!plan) {
    plan = document.createElement("div");
    plan.className = "script-plan-card hidden";
    plan.id = "excelQuoteScriptPlanCard";
    plan.innerHTML = [
      '<strong class="script-plan-title">本次 AI 决策脚本</strong>',
      '<div id="excelQuoteScriptPlanList" class="script-plan-list"></div>',
      '<p id="excelQuoteScriptPlanReason" class="script-plan-reason"></p>',
    ].join("");
    panel.appendChild(plan);
  }
  ensureProgressLogUi("excelQuote", panel, "实时分析日志");
}

function ensureAiRouteProgressUi() {
  const panel = document.getElementById("aiRouteProgressPanel");
  if (!panel) return;
  let meta = panel.querySelector(".excel-progress-meta");
  if (!meta) {
    meta = document.createElement("div");
    meta.className = "excel-progress-meta";
    meta.innerHTML = [
      '<span id="aiRouteProgressStageTag" class="excel-progress-stage">未启动</span>',
      '<span id="aiRouteProgressDetail" class="excel-progress-detail">千问会结合 skills 知识内容生成 AI 报价</span>',
    ].join("");
    const head = panel.querySelector(".excel-progress-head");
    if (head && head.nextSibling) {
      panel.insertBefore(meta, head.nextSibling);
    } else {
      panel.appendChild(meta);
    }
  }
  let plan = panel.querySelector(".script-plan-card");
  if (!plan) {
    plan = document.createElement("div");
    plan.className = "script-plan-card hidden";
    plan.id = "aiRouteScriptPlanCard";
    plan.innerHTML = [
      '<strong class="script-plan-title">本次 AI 决策脚本</strong>',
      '<div id="aiRouteScriptPlanList" class="script-plan-list"></div>',
      '<p id="aiRouteScriptPlanReason" class="script-plan-reason"></p>',
    ].join("");
    panel.appendChild(plan);
  }
  ensureProgressLogUi("aiRoute", panel, "实时分析日志");
}

function getScriptPlanMeta(plan) {
  if (!plan || typeof plan !== "object") return null;
  const selected = Array.isArray(plan.selected_scripts)
    ? plan.selected_scripts.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  const registry = Array.isArray(plan.registry)
    ? plan.registry.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  const source = String(plan.source || "").trim();
  const reason = String(plan.reason || "").trim();
  if (!selected.length && !registry.length && !reason) return null;
  return { selected, registry, source, reason };
}

function localizeScriptPlanReason(reason = "") {
  const text = String(reason || "").trim();
  const lower = text.toLowerCase();
  if (!text) return "";
  if (lower.includes("no user input or task provided")) {
    return "未提供额外特殊任务约束，系统按默认脚本白名单执行报价链路";
  }
  if (lower.includes("no whitelist was supplied")) {
    return "未提供额外脚本约束，系统按默认脚本白名单执行报价链路";
  }
  if (lower.includes("model did not provide") || lower.includes("default script chain")) {
    return "未提供额外决策说明，系统按默认脚本链路执行";
  }
  return text;
}

function renderScriptPlan(prefix, plan) {
  const card = document.getElementById(`${prefix}ScriptPlanCard`);
  const list = document.getElementById(`${prefix}ScriptPlanList`);
  const reasonNode = document.getElementById(`${prefix}ScriptPlanReason`);
  if (!card || !list || !reasonNode) return;
  const meta = getScriptPlanMeta(plan);
  if (!meta) {
    card.classList.add("hidden");
    list.innerHTML = "";
    reasonNode.textContent = "";
    return;
  }
  const selectedBadges = meta.selected.length
    ? meta.selected.map((item) => `<span class="script-plan-badge is-active">${item}</span>`).join("")
    : '<span class="script-plan-badge">未选择脚本</span>';
  const registryText = meta.registry.length ? `白名单：${meta.registry.join(" / ")}` : "";
  const sourceText = meta.source ? `来源：${meta.source}` : "";
  list.innerHTML = selectedBadges;
  reasonNode.textContent = [localizeScriptPlanReason(meta.reason), registryText, sourceText].filter(Boolean).join(" · ");
  card.classList.remove("hidden");
}

function downloadTextFile(filename, content) {
  const text = String(content || "").trim();
  if (!text) return;
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || "analysis_log.txt";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function buildProgressLogFilename(prefix) {
  const stamp = new Date().toISOString().replace(/[:T]/g, "-").replace(/\..+/, "");
  return `${prefix === "aiRoute" ? "AI报价分析日志" : "报价分析日志"}_${stamp}.txt`;
}

function ensureProgressLogUi(prefix, panel, title) {
  if (!panel) return null;
  let card = panel.querySelector(".progress-log-card");
  if (!card) {
    card = document.createElement("div");
    card.className = "progress-log-card hidden";
    card.id = `${prefix}ProgressLogCard`;
    card.innerHTML = [
      '<div class="progress-log-head">',
      `<strong class="progress-log-title">${title}</strong>`,
      `<button id="${prefix}ProgressLogDownload" class="ghost progress-log-download" type="button">下载日志</button>`,
      "</div>",
      `<pre id="${prefix}ProgressLogPre" class="progress-log-pre"></pre>`,
    ].join("");
    panel.appendChild(card);
  }
  const button = document.getElementById(`${prefix}ProgressLogDownload`);
  if (button && !button.dataset.bound) {
    button.dataset.bound = "1";
    button.addEventListener("click", () => {
      const text = document.getElementById(`${prefix}ProgressLogPre`)?.textContent || "";
      downloadTextFile(buildProgressLogFilename(prefix), text);
    });
  }
  return card;
}

function renderProgressLog(prefix, text, visible = true) {
  const card = document.getElementById(`${prefix}ProgressLogCard`);
  const pre = document.getElementById(`${prefix}ProgressLogPre`);
  const button = document.getElementById(`${prefix}ProgressLogDownload`);
  const content = String(text || "").trim();
  if (!card || !pre || !button) return;
  if (!visible || !content) {
    pre.textContent = "";
    card.classList.add("hidden");
    button.disabled = true;
    return;
  }
  pre.textContent = content;
  button.disabled = false;
  card.classList.remove("hidden");
}

function simplifyFinanceHomeLayout() {
  state.activeView = "finance";
  const engineerView = document.getElementById("engineerView");
  const legacyExcelCard = engineerView?.querySelector("#excelQuoteFile")?.closest("section.card");
  if (legacyExcelCard) legacyExcelCard.remove();
  const detailCard = document.querySelector("#financeView .table-wrap")?.closest("section.card");
  if (detailCard) detailCard.classList.add("finance-detail-card");
}

function hydrateStaticLabels() {
  document.documentElement.lang = "zh-CN";
  setNodeText("title", "财务报价工作台 Demo");
  setNodeText(".hero h1", "财务报价工作台");
  setNodeText(".hero-sub", "上传 Excel 后直接查看财务传统报价、AI 报价差异和待复核项，首页不再堆叠工程补录与演示信息。");
  setNodeText("#financeTab", "财务首页");
  setNodeText('.finance-module-card[data-finance-module-target="warehouse-recheck"] strong', "仓库报价重新核算");
  setNodeText('.finance-module-card[data-finance-module-target="single-bom"] strong', "单物料 BOM 价格试算");
  setNodeText('.finance-module-card[data-finance-module-target="excel-quote"] strong', "上传 Excel 并生成报价");
  setNodeText('.finance-module-card[data-finance-module-target="band-config"] strong', "名称型物料价格区间配置");
  setNodeText(".hero-note strong", "当前原则");
  setNodeText(".hero-note span", "当前页面只保留财务三类常用动作：仓库报价重新核算、单物料 BOM 价格试算、上传 Excel 并生成报价；BOM 明细与异常清单统一放在页面底部复核。");
  setNodeText(".finance-home-upload .section-title h2", "上传 Excel 并生成报价");
  setNodeText(".finance-top .section-title h2", "仓库报价重新核算");
  setNodeText(".single-bom-card .section-title h2", "单物料 BOM 价格试算");
  setNodeText(".single-bom-card .section-kicker", "单物料试算");
  setNodeText(".single-bom-intro", "快速估算单个物料的材料成本、工艺附加和数量小计，确认后可直接加入当前报价型号。");
  setLabelText("scenarioSelect", "报价型号");
  setLabelText("financeBomSearchKeyword", "搜索金蝶型号");
  setLabelText("financeBomHeaderSelect", "金蝶已有型号");
  setNodeText("#financeSearchBomBtn", "搜索型号");
  setNodeText("#loadFinanceBomBtn", "开始报价测算");
  setLabelText("singleBomCode", "物料编码");
  setLabelText("singleBomName", "物料名称");
  setLabelText("singleBomMaterial", "材质");
  setLabelText("singleBomWeight", "单件重量(kg)");
  setLabelText("singleBomQty", "数量");
  setLabelText("singleBomProductionMode", "报价模式");
  setLabelText("singleBomAnnualVolume", "年产量");
  setLabelText("singleBomProcess", "工艺");
  setLabelText("singleBomLoss", "损耗率");
  setLabelText("singleBomCt", "节拍 CT(分钟/件)");
  setLabelText("singleBomRate", "费率(元/小时)");
  setLabelText("singleBomExtra", "采购/外协附加(元/件)");
  setNodeText("#singleBomCalcBtn", "更新试算");
  setNodeText("#singleBomAddBtn", "加入当前BOM");
  setNodeText("#singleBomExportBtn", "导出当前BOM");
  setNodeText("#singleBomResetBtn", "清空试算参数");
  setNodeText(".quote-lanes .finance-route p", "财务传统报价");
  setNodeText(".quote-lanes .ai-route p", "AI报价");
  setNodeText("#aiRouteSummaryLabel", "千问 + skills 知识报价");
  setNodeText("#aiRouteStatusChip", "等待启动");
  setNodeText("#aiRouteProgressLabel", "等待并行生成");
  setNodeText("#aiRouteProgressPercent", "0%");
  setNodeText("#aiRouteProgressHint", "千问会结合 skills 知识内容生成 AI 报价，当前页面展示的是模型最终结果。");
  const unifiedSkillStageLabels = ["在线价格查询", "规则报价计算", "AI补充复核"];
  window.__financeSkillStageLabels = unifiedSkillStageLabels;
  const summaryTitles = document.querySelectorAll("#financeView .summary-card p");
  const summaryHints = document.querySelectorAll("#financeView .summary-card span");
  if (summaryTitles[0]) summaryTitles[0].textContent = "基准与财务价差";
  if (summaryTitles[1]) summaryTitles[1].textContent = "整机总重量";
  if (summaryTitles[2]) summaryTitles[2].textContent = "报价条目数";
  if (summaryTitles[3]) summaryTitles[3].textContent = "待复核项";
  if (summaryHints[0]) summaryHints[0].textContent = "用于财务快速复核";
  if (summaryHints[1]) summaryHints[1].textContent = "报价时可直接引用";
  if (summaryHints[2]) summaryHints[2].textContent = "当前参与计算的物料数";
  if (summaryHints[3]) summaryHints[3].textContent = "含高价差与待补参数";
  setNodeText("#toggleBreakdownBtn", "查看价格组成");
  setNodeText("#exportQuoteExcelBtn", "导出报价结果 Excel");
  setNodeText("#breakdownPanel .section-title h2", "价格组成");
  const breakTitles = document.querySelectorAll("#breakdownPanel .break-item p");
  if (breakTitles[0]) breakTitles[0].textContent = "材料成本";
  if (breakTitles[1]) breakTitles[1].textContent = "工艺附加";
  if (breakTitles[2]) breakTitles[2].textContent = "参考采购覆盖";
  setNodeText(".comparison-card h2", "价格对比图");
  setNodeText(".analysis-card h2", "价格不一致原因");
  setNodeText("#meta", "首页只保留上传、总价对比、异常摘要和下载入口。");
  setNodeText(".low-key-card h2", "金蝶接入说明");
  setLabelText("excelQuoteFile", "Excel 文件");
  setLabelText("excelQuoteModelLabel", "报价型号名称");
  setLabelText("excelQuoteProductionMode", "报价模式");
  setLabelText("excelQuoteAnnualVolume", "年产量");
  setNodeText("#quoteExcelBtn", "开始报价");
  setNodeText("#useExcelScenarioBtn", "打开最近一次结果");
  setNodeText("#downloadExcelPackageBtn", "下载 AI 报价汇总包");
  setNodeText(".finance-detail-card .section-title h2", "BOM明细与异常清单");
  setNodeText("#excelQuoteProgressLabel", "等待开始");
  setNodeText("#excelQuoteProgressPercent", "0%");
  setNodeText("#excelQuoteProgressHint", "上传后会先生成财务传统报价，再并行生成 AI 报价结果");
  setNodeText("#excelQuoteExportsSummary", "完成后会在这里汇总展示多个报价 Excel 结果。");
  const financeHomeImportTitles = document.querySelectorAll(".finance-home-upload .import-line strong");
  if (financeHomeImportTitles[0]) financeHomeImportTitles[0].textContent = "报价规则来源";
  if (financeHomeImportTitles[1]) financeHomeImportTitles[1].textContent = "AI 报价输出";
  if (financeHomeImportTitles[2]) financeHomeImportTitles[2].textContent = "处理状态";
  if (financeHomeImportTitles[3]) financeHomeImportTitles[3].textContent = "金蝶价格参考";
  const financeHomeImportSpans = document.querySelectorAll(".finance-home-upload .import-line span");
  if (financeHomeImportSpans[1]) financeHomeImportSpans[1].textContent = "并行完成后会生成报价总表、AI 明细、财务参考对照和差异复核清单，并自动汇总成一个下载包";
  ensureExcelQuoteProgressUi();
  ensureAiRouteProgressUi();
}

const processDefaults = {
  "定子绕线": { lossRate: 0.03, processFactor: 1.2 },
  "定子绕线总成": { lossRate: 0.05, processFactor: 2.35 },
  "铁芯冲压叠压": { lossRate: 0.05, processFactor: 1.55 },
  "冲压开模件": { lossRate: 0.08, processFactor: 1.08 },
  "拉伸件": { lossRate: 0.06, processFactor: 1.12 },
  "拉伸开模件": { lossRate: 0.06, processFactor: 1.12 },
  "低压铸铝": { lossRate: 0.06, processFactor: 1.15 },
  "高压铸铝": { lossRate: 0.05, processFactor: 1.14 },
  "机加工": { lossRate: 0.04, processFactor: 1.18 },
};

function normalizeNumber(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
}

function optionalNumberInput(id) {
  const node = document.getElementById(id);
  if (!node) return null;
  const raw = String(node.value ?? "").trim();
  if (!raw) return null;
  const num = Number(raw);
  return Number.isFinite(num) ? num : null;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatSourceTagDisplay(value) {
  const text = String(value || "").trim();
  if (!text) return "-";
  return text
    .replace(/已有\s*BOM/g, "本地预置BOM")
    .replace(/已加载BOM/g, "本地预置BOM")
    .replace(/Excel导入/g, "Excel导入BOM")
    .replace(/金蝶导入/g, "金蝶导入BOM")
    .replace(/单物料试算/g, "单物料试算结果")
    .replace(/财务:Excel\/金蝶\/目标/g, "Excel采购参考 / 金蝶采购参考 / 目标价参考")
    .replace(/财务:Excel\/金蝶/g, "Excel采购参考 / 金蝶采购参考")
    .replace(/财务:Excel\/目标/g, "Excel采购参考 / 目标价参考")
    .replace(/财务:金蝶\/目标/g, "金蝶采购参考 / 目标价参考")
    .replace(/财务:Excel/g, "Excel采购参考")
    .replace(/财务:金蝶/g, "金蝶采购参考")
    .replace(/财务:目标/g, "目标价参考")
    .replace(/\bAI报价\b/g, "AI基准报价")
    .replace(/(?:^| \/ )估重(?= \/|$)/g, (match) => match.replace("估重", "AI估重"));
}

function splitSourceReferences(value) {
  const normalized = formatSourceTagDisplay(value);
  if (!normalized || normalized === "-") {
    return { finance: "-", aiSkills: "-" };
  }
  const financeParts = [];
  const aiParts = [];
  normalized.split(/\s*\/\s*/).forEach((token) => {
    const text = String(token || "").trim();
    if (!text) return;
    if (/(AI|skills|估重)/i.test(text)) {
      aiParts.push(text);
    } else {
      financeParts.push(text);
    }
  });
  return {
    finance: financeParts.length ? financeParts.join(" / ") : "-",
    aiSkills: aiParts.length ? aiParts.join(" / ") : "-",
  };
}

function materialAlias(text = "") {
  const normalized = String(text || "").toLowerCase();
  if (normalized.includes("铜")) return "铜";
  if (normalized.includes("硅钢") || normalized.includes("35w") || normalized.includes("b30")) return "硅钢";
  if (normalized.includes("铝")) return "铝";
  if (normalized.includes("钕") || normalized.includes("n35") || normalized.includes("n38") || normalized.includes("n40") || normalized.includes("n42") || normalized.includes("n45") || normalized.includes("n48") || normalized.includes("n50") || normalized.includes("n52") || normalized.includes("磁")) return "磁材";
  if (normalized.includes("20cr") || normalized.includes("钢")) return "钢材";
  return text || "未识别";
}

function processDefaultsFor(processName = "") {
  return processDefaults[processName] || { lossRate: 0.05, processFactor: 1.1 };
}

function latestRawPrice(materialInput) {
  const alias = materialAlias(materialInput);
  const live = (state.data?.market_prices_cny_per_kg || {})[alias];
  if (live) return { price: live, source: "live_or_merged" };
  const list = (state.data?.trend_items || []).filter((item) => materialAlias(item.material) === alias && item.raw_price_26_jan_feb);
  if (!list.length) return { price: 0, source: "none" };
  const picked = list.reduce((a, b) => (normalizeNumber(a.raw_price_26_jan_feb) > normalizeNumber(b.raw_price_26_jan_feb) ? a : b));
  return { price: normalizeNumber(picked.raw_price_26_jan_feb), source: "trend" };
}

function estimateChangjiangProcessCost(item, materialCost) {
  const combined = `${item.name || ""} ${item.process || ""}`.trim();
  const weight = normalizeNumber(item.weight_kg || item.weight);
  if (["绕组", "嵌线", "绕线", "定子总成"].some((token) => combined.includes(token))) {
    return { processCost: 0, source: "长江规则-绕组差异口径", note: "单个绕组类组件默认不额外叠加工艺单价" };
  }
  if (["叠压", "焊接", "铁芯", "冲压叠片"].some((token) => combined.includes(token))) {
    return { processCost: weight * 17, source: "长江规则-铁芯叠装", note: "按 17 元/kg 粗估" };
  }
  if (["磁钢", "烧结", "磁材"].some((token) => combined.includes(token))) {
    return { processCost: weight * 35, source: "长江规则-磁材加工", note: "按 35 元/kg 粗估" };
  }
  if (["高压铸铝", "低压铸铝", "压铸", "铸造"].some((token) => combined.includes(token))) {
    return { processCost: weight * 8, source: "长江规则-铸造", note: "按 8 元/kg 粗估" };
  }
  if (combined.includes("冲压")) {
    return { processCost: weight * 4.5, source: "长江规则-冲压", note: "按 4.5 元/kg 粗估" };
  }
  if ((combined.includes("拉伸") && (combined.includes("机加工") || combined.includes("焊"))) || combined.includes("摩擦焊")) {
    return { processCost: weight * 18, source: "长江规则-结构件综合", note: "按 18 元/kg 粗估" };
  }
  if (["拉伸件", "拉伸开模件"].some((token) => combined.includes(token))) {
    return { processCost: weight * 18, source: "长江规则-拉伸综合", note: "按 18 元/kg 粗估" };
  }
  const defaults = processDefaultsFor(item.process);
  const factorDelta = Math.max(defaults.processFactor - 1, 0);
  if (materialCost > 0 && factorDelta > 0) {
    return {
      processCost: materialCost * factorDelta,
      source: "长江规则-默认系数兜底",
      note: "未命中明确工艺规则，按默认系数估算工艺附加",
    };
  }
  return { processCost: 0, source: "长江规则-待补工艺", note: "当前仅保留材料成本" };
}

function estimateChangjiangRoute(item) {
  const defaults = processDefaultsFor(item.process);
  const rawLookup = latestRawPrice(item.material || item.name || item.spec || "");
  const rawPrice = normalizeNumber(item.material_price_used || item.materialPriceUsed || item.material_price || item.materialPrice || rawLookup.price);
  const lossRate = normalizeNumber(item.loss || item.lossRate) || defaults.lossRate;
  const weight = normalizeNumber(item.weight_kg || item.weight);
  const materialCost = rawPrice * weight * (1 + lossRate);
  const processRoute = estimateChangjiangProcessCost(item, materialCost);
  const extra = normalizeNumber(item.extra);
  const unitPrice = materialCost + processRoute.processCost + extra;
  return {
    rawPrice,
    lossRate,
    materialCost,
    processCost: processRoute.processCost,
    unitPrice,
    source: processRoute.source,
    status: unitPrice > 0 ? "规则可用" : "待补参数",
    note: processRoute.note,
  };
}

function estimateFinanceRoute(item) {
  const providedUnitPrice = normalizeNumber(item.finance_route_unit_price ?? item.financeRouteUnitPrice ?? item.reference_unit_price ?? item.referenceUnitPrice);
  const providedSource = item.finance_route_source || item.financeRouteSource || item.reference_source || item.referenceSource || "";
  const providedStatus = item.finance_route_status || item.financeRouteStatus || "";
  const providedNote = item.finance_route_note || item.financeRouteNote || "";
  const providedHasReference = item.finance_route_has_reference ?? item.financeRouteHasReference;
  if (providedUnitPrice > 0 || providedSource || providedStatus) {
    return {
      unitPrice: providedUnitPrice,
      source: providedSource || (providedUnitPrice > 0 ? "传统参考" : "待补传统参考"),
      hasReference: typeof providedHasReference === "boolean" ? providedHasReference : providedUnitPrice > 0,
      status: providedStatus || (providedUnitPrice > 0 ? "传统参考命中" : "缺传统参考"),
      note: providedNote,
    };
  }

  const extra = normalizeNumber(item.extra);
  const references = [
    { price: normalizeNumber(item.current_unit_price), source: "Excel表格采购价" },
    { price: normalizeNumber(item.kingdee_reference_price), source: "金蝶最近采购价" },
    { price: normalizeNumber(item.target_unit_price), source: "Excel目标价" },
  ];
  const picked = references.find((entry) => entry.price > 0);
  if (picked) {
    return {
      unitPrice: picked.price + extra,
      source: picked.source,
      hasReference: true,
      status: "传统参考命中",
      note: picked.source === "金蝶最近采购价" && item.kingdee_supplier_name
        ? `${item.kingdee_supplier_name}${item.kingdee_reference_date ? ` / ${item.kingdee_reference_date}` : ""}`
        : "已命中传统采购参考",
    };
  }
  return {
    unitPrice: 0,
    source: "待补传统参考",
    hasReference: false,
    status: "缺传统参考",
    note: "当前没有可用采购参考价",
  };
}

function estimateAiRoute(item, changjiangRoute, financeRoute) {
  const providedUnitPrice = normalizeNumber(item.ai_route_unit_price ?? item.aiRouteUnitPrice);
  const providedSource = item.ai_route_source || item.aiRouteSource || "";
  const providedStatus = item.ai_route_status || item.aiRouteStatus || "";
  const providedConfidence = normalizeNumber(item.ai_route_confidence ?? item.aiRouteConfidence);
  const providedReasoning = item.ai_route_reasoning || item.aiRouteReasoning || "";
  if (providedUnitPrice > 0 || providedSource || providedStatus || providedReasoning) {
    const normalizedStatus = providedStatus || (providedUnitPrice > 0 ? "AI报价" : "待AI报价");
    return {
      unitPrice: providedUnitPrice,
      source: providedSource || "Qwen+skills",
      status: normalizedStatus,
      confidence: providedConfidence,
      reasoning: providedReasoning || "未返回基准说明",
      note: providedReasoning || "未返回基准说明",
      ready: providedUnitPrice > 0,
    };
  }

  return {
    unitPrice: 0,
    source: "待AI报价",
    status: "待AI报价",
    confidence: 0,
    reasoning: "仓库报价重新核算需点击“开始报价测算”后，由后端千问 + skills 知识链路统一生成 AI 报价。",
    note: "仓库报价重新核算需点击“开始报价测算”后，由后端千问 + skills 知识链路统一生成 AI 报价。",
    ready: false,
  };
}

function differenceCategory(item, financeRoute, aiRoute, changjiangRoute) {
  const financeUnit = normalizeNumber(financeRoute.unitPrice);
  const aiUnit = normalizeNumber(aiRoute.unitPrice);
  if (financeUnit <= 0) return "传统参考缺失";
  if (aiUnit <= 0) return "待AI报价";
  const gapRatio = Math.abs(aiUnit - financeUnit) / Math.max(financeUnit, aiUnit, 1);
  if (gapRatio < 0.08) return "基本一致";
  const text = `${item.name || ""} ${item.process || ""}`;
  if (["总成", "组件", "绕线", "叠压", "焊接", "测试"].some((token) => text.includes(token))) return "总成工艺判断";
  if (["Excel表格采购价", "金蝶最近采购价", "Excel目标价"].includes(financeRoute.source)) return "参考价口径";
  const changjiangUnit = normalizeNumber(changjiangRoute.unitPrice);
  if (changjiangUnit > 0 && Math.abs(aiUnit - changjiangUnit) < Math.abs(aiUnit - financeUnit)) return "原材工艺影响";
  return "供应商批量差异";
}

function analyzeRouteDifference(item, financeRoute, aiRoute, changjiangRoute) {
  const explicit = item.comparison_reason_summary || item.comparisonReasonSummary;
  if (explicit) {
    return {
      summary: explicit,
      category: differenceCategory(item, financeRoute, aiRoute, changjiangRoute),
    };
  }

  const financeUnit = normalizeNumber(financeRoute.unitPrice);
  const aiUnit = normalizeNumber(aiRoute.unitPrice);
  const changjiangUnit = normalizeNumber(changjiangRoute.unitPrice);
  const text = `${item.name || ""} ${item.process || ""}`;

  if (financeUnit <= 0 && aiUnit <= 0) {
    return { summary: "传统参考和基准报价都未形成有效价格，通常是重量、材质或采购参考不足。", category: "数据缺失" };
  }
  if (financeUnit <= 0) {
    return { summary: "传统路线缺少采购参考，当前由千问基于 skills 知识内容生成 AI 报价补位。", category: "传统参考缺失" };
  }
  if (aiUnit <= 0) {
    return { summary: `当前未形成 AI 报价，原因：${aiRoute.reasoning || aiRoute.status || "接口未返回结果"}。`, category: "待AI报价" };
  }

  const gapRatio = Math.abs(aiUnit - financeUnit) / Math.max(financeUnit, aiUnit, 1);
  if (gapRatio < 0.08) {
    return { summary: "传统报价与 AI 报价接近。", category: "基本一致" };
  }

  const reasons = [];
  if (["Excel表格采购价", "金蝶最近采购价"].includes(financeRoute.source)) {
    reasons.push("传统路线沿用历史采购价，可能受到批量、供应商、时间点和税口径影响");
  } else if (financeRoute.source === "Excel目标价") {
    reasons.push("传统路线采用目标价口径，和千问基于 skills 知识内容生成的 AI 报价口径天然存在差异");
  }
  if (["总成", "组件", "绕线", "叠压", "焊接", "测试"].some((token) => text.includes(token))) {
    reasons.push("Skill 规则会对多工序或总成件提高装配、测试和管理加成");
  }
  if (changjiangUnit > 0) {
    if (aiUnit > Math.max(financeUnit, changjiangUnit) * 1.1) {
      reasons.push("当前基准报价对工艺复杂度或供应商加成判断更高");
    } else if (aiUnit < Math.min(financeUnit, changjiangUnit) * 0.9) {
      reasons.push("当前基准报价更偏向批量采购或标准件价格区间");
    }
  }
  if (!item.material || item.material === "未识别" || normalizeNumber(item.weight_kg || item.weight) <= 0) {
    reasons.push("BOM 基础字段不完整，会放大两条路线的口径差异");
  }
  if (normalizeNumber(aiRoute.confidence) > 0 && normalizeNumber(aiRoute.confidence) < 0.55) {
    reasons.push("模型置信度偏低，这条物料建议人工复核");
  }

  return {
    summary: `${reasons[0] || "两条路线存在口径差异"}。${reasons[1] || ""}`,
    category: differenceCategory(item, financeRoute, aiRoute, changjiangRoute),
  };
}

function calcQuoteItem(item, sourceTag = "已导入") {
  const qty = normalizeNumber(item.qty) || 1;
  const weight = normalizeNumber(item.weight_kg || item.weight);
  const normalizedItem = { ...item, qty, weight_kg: weight };
  const changjiangRoute = estimateChangjiangRoute(normalizedItem);
  const financeRoute = estimateFinanceRoute(normalizedItem);
  const aiRoute = estimateAiRoute(normalizedItem, changjiangRoute, financeRoute);
  const totalWeight = weight * qty;
  const financeSubtotal = financeRoute.unitPrice * qty;
  const aiSubtotal = aiRoute.unitPrice * qty;
  const changjiangSubtotal = changjiangRoute.unitPrice * qty;
  const routeGapUnitPrice = aiRoute.unitPrice - financeRoute.unitPrice;
  const routeGapTotal = aiSubtotal - financeSubtotal;
  const comparison = analyzeRouteDifference(normalizedItem, financeRoute, aiRoute, changjiangRoute);
  const explicitSummary = item.comparisonReasonSummary || item.comparison_reason_summary || "";
  const explicitCategory = item.comparisonCategory || item.comparison_category || "";

  let status = item.status || "双路线可比";
  if (!status || ["参考价优先", "规则兜底"].includes(status)) {
    if (financeRoute.unitPrice <= 0 && aiRoute.unitPrice <= 0) status = "待补参数";
    else if (financeRoute.unitPrice <= 0) status = "缺传统参考";
    else if (aiRoute.unitPrice <= 0) status = "待AI报价";
    else if (Math.abs(routeGapUnitPrice) / Math.max(financeRoute.unitPrice, aiRoute.unitPrice, 1) >= 0.15) status = "价差待复核";
    else status = "双路线可比";
  }

  return {
    ...item,
    qty,
    weight_kg: weight,
    rawPrice: changjiangRoute.rawPrice,
    lossRate: changjiangRoute.lossRate,
    materialCost: changjiangRoute.materialCost,
    processCost: changjiangRoute.processCost,
    unitCost: financeRoute.unitPrice,
    subtotal: financeSubtotal,
    totalWeight,
    sourceTag,
    status,
    priceSource: financeRoute.source,
    referenceUnitPrice: financeRoute.unitPrice,
    financeRouteUnitPrice: financeRoute.unitPrice,
    financeRouteSource: financeRoute.source,
    financeRouteStatus: financeRoute.status,
    financeRouteHasReference: financeRoute.hasReference,
    financeRouteNote: financeRoute.note,
    financeSubtotal,
    aiRouteUnitPrice: aiRoute.unitPrice,
    aiRouteSource: aiRoute.source,
    aiRouteStatus: aiRoute.status,
    aiRouteConfidence: aiRoute.confidence,
    aiRouteReasoning: aiRoute.reasoning,
    aiRouteNote: aiRoute.note,
    aiSubtotal,
    changjiangRouteUnitPrice: changjiangRoute.unitPrice,
    changjiangRouteSource: changjiangRoute.source,
    changjiangRouteStatus: changjiangRoute.status,
    changjiangRouteNote: changjiangRoute.note,
    changjiangMaterialCost: changjiangRoute.materialCost,
    changjiangProcessCost: changjiangRoute.processCost,
    changjiangSubtotal,
    routeGapUnitPrice,
    routeGapTotal,
    comparisonReasonSummary: explicitSummary || comparison.summary,
    comparisonCategory: explicitCategory || comparison.category,
    kingdeeReferencePrice: normalizeNumber(item.kingdee_reference_price),
  };
}

function buildQuoteSummary(items) {
  const pendingStatuses = ["待补参数", "缺传统参考", "待AI报价", "缺重量", "缺材质", "模型超时", "AI未配置", "价差待复核", "估重待复核", "名称规格推断报价"];
  return {
    total_weight: items.reduce((sum, item) => sum + normalizeNumber(item.totalWeight), 0),
    finance_total: items.reduce((sum, item) => sum + normalizeNumber(item.financeSubtotal), 0),
    ai_total: items.reduce((sum, item) => sum + normalizeNumber(item.aiSubtotal), 0),
    volume_baseline_total: items.reduce((sum, item) => sum + normalizeNumber(item.volume_baseline_total_price || item.volumeBaselineTotalPrice), 0),
    volume_conservative_total: items.reduce((sum, item) => sum + normalizeNumber(item.volume_conservative_total_price || item.volumeConservativeTotalPrice), 0),
    volume_aggressive_total: items.reduce((sum, item) => sum + normalizeNumber(item.volume_aggressive_total_price || item.volumeAggressiveTotalPrice), 0),
    route_gap_total: items.reduce((sum, item) => sum + normalizeNumber(item.routeGapTotal), 0),
    uploaded_price_count: items.filter((item) => normalizeNumber(item.current_unit_price) > 0).length,
    kingdee_reference_count: items.filter((item) => normalizeNumber(item.kingdeeReferencePrice || item.kingdee_reference_price) > 0).length,
    target_price_count: items.filter((item) => normalizeNumber(item.target_unit_price) > 0).length,
    finance_reference_count: items.filter((item) => item.financeRouteHasReference).length,
    finance_missing_count: items.filter((item) => normalizeNumber(item.financeRouteUnitPrice) <= 0).length,
    ai_ready_count: items.filter((item) => normalizeNumber(item.aiRouteUnitPrice) > 0).length,
    ai_unavailable_count: items.filter((item) => normalizeNumber(item.aiRouteUnitPrice) <= 0).length,
    high_gap_count: items.filter((item) => {
      const finance = normalizeNumber(item.financeRouteUnitPrice);
      const ai = normalizeNumber(item.aiRouteUnitPrice);
      return finance > 0 && ai > 0 && Math.abs(normalizeNumber(item.routeGapUnitPrice)) / Math.max(finance, ai, 1) >= 0.15;
    }).length,
    pending_count: items.filter((item) => pendingStatuses.includes(item.status)).length,
  };
}

async function syncBomFromKingdee(bomNumber) {
  return apiFetchJson("/api/kingdee/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ bom_number: bomNumber }),
  }, "金蝶同步");
}

async function fetchBomHeaders(keyword = "", offset = 0, limit = 30) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (keyword.trim()) params.set("keyword", keyword.trim());
  return apiFetchJson(`/api/kingdee/bom-headers?${params.toString()}`, { headers: { Accept: "application/json" } }, "金蝶型号查询");
}

async function fetchAllBomHeaders(keyword = "") {
  const normalizedKeyword = keyword.trim();
  const pageSize = 100;
  const maxTotal = 2000;
  let offset = 0;
  let page = 0;
  let rows = [];
  let payload = {};
  while (offset < maxTotal) {
    payload = await fetchBomHeaders(normalizedKeyword, offset, pageSize);
    if (payload?.error) return payload;
    const pageRows = Array.isArray(payload?.rows) ? payload.rows : [];
    rows = rows.concat(pageRows);
    page += 1;
    const nextOffset = Number(payload?.next_offset ?? (offset + pageRows.length)) || rows.length;
    if (!payload?.has_more || !pageRows.length || nextOffset <= offset || rows.length >= maxTotal || page >= 30) {
      break;
    }
    offset = nextOffset;
  }
  return {
    ...payload,
    rows,
    offset: 0,
    next_offset: rows.length,
    has_more: false,
    loaded_count: rows.length,
  };
}

async function quoteExcelWorkbook(file, modelLabel = "", options = {}) {
  const formData = new FormData();
  formData.append("file", file);
  if (modelLabel.trim()) formData.append("model_label", modelLabel.trim());
  if (options.productionMode) formData.append("production_mode", options.productionMode);
  formData.append("annual_volume", String(normalizeNumber(options.annualVolume)));
  return apiFetchJson("/api/quote/excel", {
    method: "POST",
    headers: { Accept: "application/json" },
    body: formData,
  }, "Excel报价");
}

async function quoteExcelPastedTable(tableText, modelLabel = "", options = {}) {
  return apiFetchJson("/api/quote/excel-paste", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      table_text: String(tableText || ""),
      model_label: modelLabel.trim(),
      production_mode: options.productionMode || "sample",
      annual_volume: normalizeNumber(options.annualVolume),
    }),
  }, "粘贴表格报价");
}

function normalizePasteHeader(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s_\-/（）()【】\[\]：:，,\.]+/g, "");
}

function detectPastedTableDelimiter(text) {
  const sample = String(text || "");
  if (sample.includes("\t")) return "\t";
  if (sample.includes(",")) return ",";
  return "";
}

function parseDelimitedLine(line, delimiter) {
  const result = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (char === delimiter && !inQuotes) {
      result.push(current);
      current = "";
      continue;
    }
    current += char;
  }
  result.push(current);
  return result.map((cell) => String(cell || "").trim());
}

function findAliasIndex(headers, aliases) {
  const normalizedAliases = new Set((aliases || []).map((item) => normalizePasteHeader(item)));
  for (let i = 0; i < headers.length; i += 1) {
    const header = headers[i];
    if (header && normalizedAliases.has(header)) return i;
  }
  for (let i = 0; i < headers.length; i += 1) {
    const header = headers[i];
    if (!header) continue;
    for (const alias of normalizedAliases) {
      if (!alias || alias.length < 2) continue;
      if (header.includes(alias) || alias.includes(header)) return i;
    }
  }
  return -1;
}

function analyzePastedExcelTable(text) {
  const rawText = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
  if (!rawText) {
    return { ok: false, message: "请先粘贴从 Excel 复制的表格数据" };
  }
  const delimiter = detectPastedTableDelimiter(rawText);
  if (!delimiter) {
    return { ok: false, message: "未识别出表格分隔符，请直接从 Excel 复制带表头的数据区域" };
  }
  const lines = rawText.split("\n").filter((line) => line.trim());
  if (lines.length < 2) {
    return { ok: false, message: "请至少粘贴表头和一行数据" };
  }
  const rows = lines.map((line) => parseDelimitedLine(line, delimiter));
  const headerRow = rows[0];
  const normalizedHeaders = headerRow.map((item) => normalizePasteHeader(item));
  const fieldMap = {};
  Object.entries(EXCEL_PASTE_HEADER_ALIASES).forEach(([field, aliases]) => {
    const idx = findAliasIndex(normalizedHeaders, aliases);
    fieldMap[field] = idx >= 0 ? headerRow[idx] : "";
  });
  const previewRows = rows.slice(1);
  const recognizedCount = Object.values(fieldMap).filter(Boolean).length;
  return {
    ok: true,
    delimiter,
    rowCount: rows.length - 1,
    columnCount: headerRow.length,
    recognizedCount,
    headers: headerRow,
    previewRows,
    fieldMap,
  };
}

function renderExcelPasteRecognition(result) {
  const summaryNode = document.getElementById("excelQuotePasteDetectSummary");
  const previewNode = document.getElementById("excelQuotePastePreview");
  const metaNode = document.getElementById("excelQuotePastePreviewMeta");
  const fieldMapNode = document.getElementById("excelQuotePasteFieldMap");
  const headNode = document.getElementById("excelQuotePastePreviewHead");
  const bodyNode = document.getElementById("excelQuotePastePreviewBody");
  if (!summaryNode || !previewNode || !metaNode || !fieldMapNode || !headNode || !bodyNode) return;

  if (!result || !result.ok) {
    summaryNode.textContent = result?.message || "等待识别";
    metaNode.textContent = result?.message || "等待粘贴表格数据";
    fieldMapNode.innerHTML = "";
    headNode.innerHTML = "";
    bodyNode.innerHTML = "";
    previewNode.classList.add("hidden");
    return;
  }

  const delimiterLabel = result.delimiter === "\t" ? "制表符" : "逗号";
  summaryNode.textContent = `已识别 ${result.rowCount} 行，${result.columnCount} 列，命中 ${result.recognizedCount} 个关键字段`;
  metaNode.textContent = `分隔符：${delimiterLabel}；可滚动查看全部 ${result.previewRows.length} 行识别结果；可直接进入报价`;
  previewNode.classList.remove("hidden");

  const fieldLabels = {
    code: "物料编码",
    name: "物料名称",
    spec: "规格",
    material: "材质",
    weight_kg: "重量",
    process: "工艺",
    qty: "数量",
    current_unit_price: "单价",
  };
  fieldMapNode.innerHTML = Object.entries(fieldLabels).map(([field, label]) => {
    const mapped = result.fieldMap[field];
    return `<span class="excel-paste-field-chip${mapped ? "" : " missing"}">${label}：${mapped || "未识别"}</span>`;
  }).join("");

  headNode.innerHTML = `<tr>${result.headers.map((header) => `<th>${escapeHtml(header || "-")}</th>`).join("")}</tr>`;
  bodyNode.innerHTML = result.previewRows.map((row) => {
    const padded = row.concat(Array.from({ length: Math.max(result.headers.length - row.length, 0) }, () => ""));
    return `<tr>${padded.map((cell) => `<td>${cell ? escapeHtml(cell) : '<span class="excel-paste-empty">空</span>'}</td>`).join("")}</tr>`;
  }).join("");
}

function setNameSpecBandConfigStatus(message, tone = "") {
  const node = document.getElementById("nameSpecBandConfigStatus");
  if (!node) return;
  node.textContent = message || "";
  node.className = `band-config-status${tone ? ` ${tone}` : ""}`;
}

function normalizeNameSpecBandRow(row = {}) {
  return {
    category: String(row.category || "").trim(),
    keywords: Array.isArray(row.keywords)
      ? row.keywords.map((item) => String(item || "").trim()).filter(Boolean).join(", ")
      : String(row.keywords || "").trim(),
    low: normalizeNumber(row.low),
    high: normalizeNumber(row.high),
    basis: String(row.basis || "").trim(),
  };
}

function collectNameSpecBandRows() {
  return Array.from(document.querySelectorAll("#nameSpecBandTableBody tr")).map((row) => ({
    category: row.querySelector('[data-field="category"]')?.value || "",
    keywords: row.querySelector('[data-field="keywords"]')?.value || "",
    low: row.querySelector('[data-field="low"]')?.value || "",
    high: row.querySelector('[data-field="high"]')?.value || "",
    basis: row.querySelector('[data-field="basis"]')?.value || "",
  }));
}

function renderNameSpecBandConfig() {
  const body = document.getElementById("nameSpecBandTableBody");
  const pathNode = document.getElementById("nameSpecBandConfigPath");
  if (!body || !pathNode) return;
  pathNode.textContent = state.nameSpecBandConfigPath || "未加载配置文件";
  const rows = (state.nameSpecBands || []).map(normalizeNameSpecBandRow);
  body.innerHTML = rows.map((row, index) => `
    <tr data-index="${index}">
      <td><input data-field="category" value="${escapeHtml(row.category)}" placeholder="如：轴承" /></td>
      <td><input data-field="keywords" value="${escapeHtml(row.keywords)}" placeholder="逗号分隔关键词" /></td>
      <td><input data-field="low" type="number" step="0.01" min="0" value="${row.low || row.low === 0 ? escapeHtml(String(row.low)) : ""}" /></td>
      <td><input data-field="high" type="number" step="0.01" min="0" value="${row.high || row.high === 0 ? escapeHtml(String(row.high)) : ""}" /></td>
      <td><input data-field="basis" value="${escapeHtml(row.basis)}" placeholder="区间依据说明" /></td>
      <td><button class="ghost band-row-remove-btn" type="button" data-index="${index}">删除</button></td>
    </tr>
  `).join("");
  body.querySelectorAll(".band-row-remove-btn").forEach((button) => {
    button.onclick = () => {
      const index = Number(button.dataset.index || -1);
      if (index < 0) return;
      state.nameSpecBands.splice(index, 1);
      renderNameSpecBandConfig();
      setNameSpecBandConfigStatus("已从当前页面移除一条区间，记得点击“保存区间”生效。");
    };
  });
}

async function loadNameSpecBandConfig(showStatus = false) {
  try {
    if (showStatus) setNameSpecBandConfigStatus("正在加载名称型物料价格区间...");
    const payload = await fetchNameSpecBands();
    state.nameSpecBands = (payload.rows || []).map(normalizeNameSpecBandRow);
    state.nameSpecBandConfigPath = payload.config_path || "";
    renderNameSpecBandConfig();
    setNameSpecBandConfigStatus(`已加载 ${state.nameSpecBands.length} 条名称型物料价格区间。`, "success");
  } catch (error) {
    renderNameSpecBandConfig();
    setNameSpecBandConfigStatus(`价格区间加载失败：${error.message}`, "error");
  }
}

async function handleSaveNameSpecBandConfig() {
  const rows = collectNameSpecBandRows();
  try {
    setNameSpecBandConfigStatus("正在保存名称型物料价格区间...");
    const payload = await saveNameSpecBands(rows);
    if (payload.error) throw new Error(payload.message || payload.error);
    state.nameSpecBands = (payload.rows || []).map(normalizeNameSpecBandRow);
    state.nameSpecBandConfigPath = payload.config_path || "";
    renderNameSpecBandConfig();
    setNameSpecBandConfigStatus(payload.message || "名称型物料价格区间已保存。", "success");
  } catch (error) {
    setNameSpecBandConfigStatus(`保存失败：${error.message}`, "error");
  }
}

async function quoteSingleBomItem(item, model = {}) {
  return apiFetchJson("/api/quote/single-bom", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      item,
      model,
      production_mode: model.production_mode || item.production_mode || "sample",
      annual_volume: normalizeNumber(model.annual_volume ?? item.annual_volume),
    }),
  }, "单物料报价");
}

async function fetchExcelQuoteTask(taskId) {
  return apiFetchJson(`/api/quote/excel/tasks/${encodeURIComponent(taskId)}`, { headers: { Accept: "application/json" } }, "Excel报价任务查询");
}

async function exportQuoteWorkbook(payload) {
  return apiFetchBlob("/api/quote/export", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
    body: JSON.stringify(payload),
  }, "导出报价结果");
}

async function exportQuotePackage(payload) {
  return apiFetchBlob("/api/quote/export-package", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/zip" },
    body: JSON.stringify(payload),
  }, "AI报价汇总包导出");
}

async function exportQuotePackageBatch(payloads) {
  return apiFetchBlob("/api/quote/export-package-batch", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/zip" },
    body: JSON.stringify({ payloads }),
  }, "多量产汇总包导出");
}

async function reprojectMassQuotePayload(payload, annualVolume, requestedVolumeLabel = "") {
  return apiFetchJson("/api/quote/reproject-volume", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      payload,
      annual_volume: annualVolume,
      requested_volume_label: requestedVolumeLabel,
    }),
  }, "量产档位重算");
}

async function fetchNameSpecBands() {
  return apiFetchJson("/api/quote/name-spec-bands", {
    headers: { Accept: "application/json" },
  }, "名称型物料价格区间加载");
}

async function saveNameSpecBands(rows) {
  return apiFetchJson("/api/quote/name-spec-bands", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ rows }),
  }, "名称型物料价格区间保存");
}

async function startAiRouteQuoteTask(items, model = {}, scenarioSource = "金蝶导入") {
  return apiFetchJson("/api/quote/ai-route", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ items, model, scenario_source: scenarioSource }),
  }, "AI报价任务创建");
}

async function fetchAiRouteTask(taskId) {
  return apiFetchJson(`/api/quote/ai-route/tasks/${encodeURIComponent(taskId)}`, { headers: { Accept: "application/json" } }, "AI报价任务查询");
}

async function loadDemoData() {
  try {
    const payload = await apiFetchJson("/api/demo-data", { headers: { Accept: "application/json" } }, "演示数据加载");
    state.loadMode = "api";
    return payload;
  } catch (_) {
    const fallback = await fetch("./data/demo_data.json");
    state.loadMode = "static";
    return await fallback.json();
  }
}

function getScenarioList() {
  return [{
    id: "double20_drive",
    code: "double20_drive",
    label: "双二十行驱动电机总成",
    description: "财务直接查看整机结果，工程师只处理新增 BOM 子项。",
  }];
}

function getActiveItems() {
  return state.scenarioItems[state.financeScenario] || [];
}

function getEngineerItems() {
  return state.scenarioItems[state.engineerScenario] || [];
}

function getActiveScenario() {
  return state.scenarios.find((item) => item.id === state.financeScenario) || null;
}

function isMassPricingMode(items = getActiveItems()) {
  if ((items || []).some((item) =>
    normalizeNumber(item.volume_baseline_unit_price || item.volumeBaselineUnitPrice) > 0
    || normalizeNumber(item.volume_conservative_unit_price || item.volumeConservativeUnitPrice) > 0
    || normalizeNumber(item.volume_aggressive_unit_price || item.volumeAggressiveUnitPrice) > 0
  )) {
    return true;
  }
  if ((items || []).some((item) => String(item.production_mode || item.productionMode || "").toLowerCase() === "mass")) {
    return true;
  }
  const modelMode = String(state.lastExcelQuotePayload?.model?.production_mode || "").toLowerCase();
  return modelMode === "mass" && state.financeScenario === state.lastExcelScenarioId;
}

function getAvailableFinanceStatuses(items = getActiveItems()) {
  return [...new Set((items || []).map((item) => String(item.status || "").trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
}

function buildFinanceStatusFilterHeader(items = getActiveItems()) {
  const options = ['<option value="all">全部状态</option>']
    .concat(getAvailableFinanceStatuses(items).map((status) => `<option value="${escapeHtml(status)}"${state.financeStatusFilter === status ? " selected" : ""}>${escapeHtml(status)}</option>`))
    .join("");
  return `
    <div class="status-filter-head">
      <span>状态</span>
      <select id="financeStatusFilter" class="status-filter-select" aria-label="按状态筛选报价明细">
        ${options}
      </select>
    </div>
  `;
}

function renderQuotedMoneyCell(unitPrice, qty, className = "") {
  const safeQty = normalizeNumber(qty) || 1;
  const totalPrice = unitPrice * safeQty;
  const subtotal = safeQty > 1
    ? `<div class="cell-subnote">小计 ${money(totalPrice)}</div>`
    : "";
  return `<td class="cell-money ${className}"><div>${money(unitPrice || 0)}</div>${subtotal}</td>`;
}

function renderQuotedGapCell(unitGap, qty) {
  const safeQty = normalizeNumber(qty) || 1;
  const totalGap = unitGap * safeQty;
  const subtotal = safeQty > 1
    ? `<div class="cell-subnote">总差 ${signedMoney(totalGap)}</div>`
    : "";
  return `<td class="cell-money"><div>${signedMoney(unitGap || 0)}</div>${subtotal}</td>`;
}

function renderWeightCell(item) {
  const originalWeight = normalizeNumber(item.weight_kg);
  const estimatedWeight = normalizeNumber(item.ai_estimated_weight_kg || item.aiEstimatedWeightKg);
  const estimateNote = String(item.ai_estimated_weight_note || item.aiEstimatedWeightNote || "").trim();
  if (originalWeight > 0) {
    return `<td class="cell-number"><div>${f4(originalWeight)}</div></td>`;
  }
  if (estimatedWeight > 0) {
    const tooltip = estimateNote ? ` title="${escapeHtml(estimateNote)}"` : "";
    return `<td class="cell-number cell-weight-estimated"${tooltip}><div>${f4(estimatedWeight)}</div><div class="cell-subnote">AI估重</div></td>`;
  }
  return '<td class="cell-number"><div>0.0000</div><div class="cell-subnote">待补重量</div></td>';
}

function renderFinanceTableLayout(items = getActiveItems()) {
  const table = document.querySelector("#financeView .finance-data-table");
  const colgroup = document.getElementById("financeTableColgroup");
  const thead = document.getElementById("financeTableHead");
  if (!table || !colgroup || !thead) return;

  const isMass = isMassPricingMode(items);
  table.classList.toggle("is-mass-mode", isMass);

  if (isMass) {
    const massVolumeLabel = formatMassAnnualVolumeLabel(items);
    colgroup.innerHTML = `
      <col class="col-code" />
      <col class="col-name" />
      <col class="col-source-finance" />
      <col class="col-source-ai" />
      <col class="col-material" />
      <col class="col-qty" />
      <col class="col-weight" />
      <col class="col-finance" />
      <col class="col-volume" />
      <col class="col-volume" />
      <col class="col-volume" />
      <col class="col-tooling-compare" />
      <col class="col-gap" />
      <col class="col-analysis" />
      <col class="col-status" />
      <col class="col-finance-source" />
      <col class="col-ai-reason" />
    `;
    thead.innerHTML = `
      <tr class="group-head">
        <th colspan="7">BOM 信息</th>
        <th colspan="5">报价结果（${massVolumeLabel}）</th>
        <th colspan="3">对比结果</th>
        <th colspan="2">路线说明</th>
      </tr>
      <tr class="finance-column-head">
        <th>物料编码</th>
        <th>物料名称</th>
        <th>财务参考</th>
        <th>AI/skills参考</th>
        <th>材质</th>
        <th>数量</th>
        <th>重量(kg)</th>
        <th class="head-finance">财务传统报价(元)</th>
        <th class="head-volume-base">基准(${massVolumeLabel},元)</th>
        <th class="head-volume-cons">保守(${massVolumeLabel},元)</th>
        <th class="head-volume-aggr">激进(${massVolumeLabel},元)</th>
        <th class="head-tooling-compare">样品/开模对比</th>
        <th>价差(元)</th>
        <th>差异分析</th>
        <th>${buildFinanceStatusFilterHeader(items)}</th>
        <th>财务来源</th>
        <th>基准说明（${massVolumeLabel}）</th>
      </tr>
    `;
    return;
  }

  colgroup.innerHTML = `
    <col class="col-code" />
    <col class="col-name" />
    <col class="col-source-finance" />
    <col class="col-source-ai" />
    <col class="col-material" />
    <col class="col-qty" />
    <col class="col-weight" />
    <col class="col-finance" />
    <col class="col-ai-price" />
    <col class="col-gap" />
    <col class="col-analysis" />
    <col class="col-status" />
    <col class="col-finance-source" />
    <col class="col-ai-reason" />
  `;
  thead.innerHTML = `
    <tr class="group-head">
      <th colspan="7">BOM 信息</th>
      <th colspan="2">双路线报价</th>
      <th colspan="3">对比结果</th>
      <th colspan="2">路线说明</th>
    </tr>
    <tr class="finance-column-head">
      <th>物料编码</th>
      <th>物料名称</th>
      <th>财务参考</th>
      <th>AI/skills参考</th>
      <th>材质</th>
      <th>数量</th>
      <th>重量(kg)</th>
      <th class="head-finance">财务传统报价(元)</th>
      <th class="head-ai">基准报价(元)</th>
      <th>价差(元)</th>
      <th>差异分析</th>
      <th>${buildFinanceStatusFilterHeader(items)}</th>
      <th>财务来源</th>
      <th>基准说明</th>
    </tr>
  `;
}

function buildExportPayload() {
  const items = getActiveItems();
  const scenario = getActiveScenario();
  return {
    dataset: "finance_quote_export",
    source: scenario?.id?.startsWith("excel_") ? "excel_upload" : "finance_view",
    rules_source: "mes_ubuntu/changjiang-bom-pricing",
    model: {
      label: scenario?.label || "当前报价结果",
      filename: scenario?.code || "",
      sheet_name: scenario?.description || "",
      item_count: items.length,
      production_mode: items[0]?.production_mode || items[0]?.productionMode || state.lastExcelQuotePayload?.model?.production_mode || "sample",
      annual_volume: normalizeNumber(items[0]?.annual_volume || items[0]?.annualVolume || state.lastExcelQuotePayload?.model?.annual_volume),
    },
    summary: buildQuoteSummary(items),
    items,
  };
}

function downloadBlob(blob, disposition, fallbackName) {
  const match = disposition.match(/filename\*=UTF-8''([^;]+)/i) || disposition.match(/filename="?([^"]+)"?/i);
  const rawName = match?.[1] ? decodeURIComponent(match[1]) : fallbackName;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = rawName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function nextExcelQuotePollToken() {
  state.excelQuotePollToken += 1;
  return state.excelQuotePollToken;
}

function nextAiRoutePollToken() {
  state.aiRoutePollToken += 1;
  return state.aiRoutePollToken;
}

function buildExportVolumeLabel(model = {}) {
  const requested = String(model.requested_volume_label || "").trim();
  const requestedSimple = requested.match(/\d+套\/年/)?.[0] || "";
  if (requestedSimple) return requestedSimple;
  if (requested) return requested;
  const annualVolume = Math.max(0, Math.round(normalizeNumber(model.requested_annual_volume || model.annual_volume || 0)));
  return annualVolume > 0 ? `${annualVolume}套/年` : "";
}

function buildExcelExportList(payload = {}) {
  const exports = Array.isArray(payload.exports) ? payload.exports : [];
  if (exports.length) return exports;
  const items = payload.items || [];
  const summary = payload.summary || {};
  const labelBase = payload.model?.label || payload.model?.filename || "报价结果";
  const volumeLabel = buildExportVolumeLabel(payload.model || {});
  const label = volumeLabel && !String(labelBase).includes(volumeLabel) ? `${labelBase}_${volumeLabel}` : labelBase;
  return [
    {
      id: "quote_summary",
      label: "报价总表",
      filename: `${label}_报价总表.xlsx`,
      description: "总价概览、汇总指标与完整报价明细",
      item_count: items.length,
    },
    {
      id: "ai_routes",
      label: "基准报价明细",
      filename: `${label}_基准报价明细.xlsx`,
      description: "千问基于 skills 知识内容生成的 AI 报价说明与建议工艺",
      item_count: normalizeNumber(summary.ai_ready_count),
    },
    {
      id: "finance_references",
      label: "财务参考对照",
      filename: `${label}_财务参考对照.xlsx`,
      description: "Excel、金蝶与财务传统报价来源对照",
      item_count: normalizeNumber(summary.finance_reference_count),
    },
    {
      id: "gap_review",
      label: "差异复核清单",
      filename: `${label}_差异复核清单.xlsx`,
      description: "高价差、缺传统参考、AI 未形成报价的重点项",
      item_count: normalizeNumber(summary.high_gap_count) + normalizeNumber(summary.finance_missing_count) + normalizeNumber(summary.ai_unavailable_count),
    },
  ];
}

function getExcelQuoteDownloadPayloads() {
  if (Array.isArray(state.lastExcelQuotePayloads) && state.lastExcelQuotePayloads.length) {
    return state.lastExcelQuotePayloads.filter((payload) => payload?.items?.length);
  }
  return state.lastExcelQuotePayload?.items?.length ? [state.lastExcelQuotePayload] : [];
}

function buildExcelExportGroups(payloadOrPayloads = null) {
  const payloads = Array.isArray(payloadOrPayloads)
    ? payloadOrPayloads.filter((payload) => payload?.items?.length)
    : (payloadOrPayloads?.items?.length ? [payloadOrPayloads] : []);
  return payloads.map((payload) => {
    const model = payload.model || {};
    const volumeLabel = buildExportVolumeLabel(model) || "样品/小批";
    const groupLabel = model.label || model.filename || volumeLabel || "报价结果";
    return {
      payload,
      groupLabel,
      volumeLabel,
      exports: buildExcelExportList(payload),
    };
  });
}

function deriveExcelQuoteProgress(progress = {}) {
  const stage = String(progress.stage || "");
  const processed = normalizeNumber(progress.processed);
  const total = normalizeNumber(progress.total);
  const parallelWorkers = normalizeNumber(progress.parallel_workers);
  const elapsedSeconds = normalizeNumber(progress.elapsed_seconds);
  const waitingFirstResult = Boolean(progress.waiting_first_result);
  const ratio = total > 0 ? Math.min(Math.max(processed / total, 0), 1) : 0;
  const weighted = {
    queued: [0, 4],
    preparing: [4, 14],
    market_pricing: [14, 32],
    rule_pricing: [32, 58],
    pricing: [14, 42],
    ai_supplement: [58, 90],
    ai_pricing: [42, 92],
    finalizing: [92, 99],
    done: [100, 100],
  };
  const [start, end] = weighted[stage] || [0, 95];
  let percent = normalizeNumber(progress.percent);
  if (!percent) {
    percent = start === end ? end : start + (end - start) * ratio;
  }
  percent = Math.min(Math.max(percent, 0), 100);
  const stageLabels = {
    queued: "排队中",
    preparing: "准备 Excel 数据",
    market_pricing: "在线价格查询",
    rule_pricing: "规则报价计算",
    pricing: "生成财务传统报价",
    ai_supplement: "AI补充复核",
    ai_pricing: "并行生成 AI 报价",
    finalizing: "汇总报价结果",
    done: "报价完成",
  };
  let hint = String(progress.hint || "").trim();
  if (!hint && stage === "ai_pricing" && waitingFirstResult) {
    hint = `AI 报价首批结果返回较慢，当前已等待 ${Math.max(1, Math.round(elapsedSeconds))} 秒，服务端仍在并行处理。`;
  }
  if (!hint && stage === "ai_pricing") {
    hint = progress.parallel_workers ? `AI 报价阶段正在并行执行，当前并发 ${progress.parallel_workers} 路` : "AI 报价阶段正在并行执行";
  }
  if (!hint && stage === "market_pricing") {
    hint = "正在查询在线原材价格与市场快照";
  }
  if (!hint && stage === "rule_pricing") {
    hint = "正在执行最新 skill 原生脚本，生成传统报价与规则估算";
  }
  if (!hint && stage === "ai_supplement") {
    hint = progress.parallel_workers ? `正在并行生成 AI 报价，当前并发 ${progress.parallel_workers} 路` : "正在生成 AI 报价";
  }
  if (!hint && stage === "pricing") {
    hint = "先计算财务传统报价，再由千问结合 skills 知识内容生成 AI 报价";
  }
  if (!hint && stage === "finalizing") {
    hint = "正在汇总多个报价 Excel 表格";
  }
  let detail = "";
  if (["market_pricing", "rule_pricing", "pricing", "ai_supplement", "ai_pricing", "finalizing"].includes(stage) && total > 0) {
    detail = `已处理 ${processed} / ${total}`;
  }
  if (["ai_pricing", "ai_supplement"].includes(stage) && parallelWorkers > 0) {
    detail = detail ? `${detail} · 并发 ${parallelWorkers} 路` : `并发 ${parallelWorkers} 路`;
  }
  if (stage === "ai_pricing" && waitingFirstResult) {
    detail = detail
      ? `${detail} · 已等待 ${Math.max(1, Math.round(elapsedSeconds))} 秒`
      : `已等待 ${Math.max(1, Math.round(elapsedSeconds))} 秒`;
  }
  const stageTags = {
    queued: "已提交",
    preparing: "准备中",
    market_pricing: "在线询价",
    rule_pricing: "规则报价",
    pricing: "传统报价",
    ai_supplement: "AI补充",
    ai_pricing: "AI 并行",
    finalizing: "汇总中",
    done: "已完成",
  };
  return {
    stage,
    percent,
    stageLabel: String(progress.stage_label || stageLabels[stage] || "报价处理中"),
    hint: hint || "正在处理报价任务",
    detail,
    stageTag: stageTags[stage] || "处理中",
    waiting: waitingFirstResult,
    scriptPlan: progress.script_plan || progress.skill_script_plan || null,
    analysisLogText: String(progress.analysis_log_text || progress.analysisLogText || "").trim(),
  };
}

function renderExcelQuoteProgress(meta, visible = true) {
  ensureExcelQuoteProgressUi();
  const panel = document.getElementById("excelQuoteProgressPanel");
  const fill = document.getElementById("excelQuoteProgressFill");
  const stage = String(meta.stage || "");
  ["stage-queued", "stage-preparing", "stage-market_pricing", "stage-rule_pricing", "stage-pricing", "stage-ai_supplement", "stage-ai_pricing", "stage-finalizing", "stage-done"].forEach((name) => {
    panel.classList.remove(name);
  });
  if (stage) panel.classList.add(`stage-${stage}`);
  panel.classList.toggle("hidden", !visible);
  document.getElementById("excelQuoteProgressLabel").textContent = meta.stageLabel || "报价处理中";
  document.getElementById("excelQuoteProgressPercent").textContent = `${Math.round(normalizeNumber(meta.percent))}%`;
  document.getElementById("excelQuoteProgressStageTag").textContent = meta.stageTag || "处理中";
  document.getElementById("excelQuoteProgressDetail").textContent = meta.detail || "等待任务继续推进";
  document.getElementById("excelQuoteProgressHint").textContent = meta.hint || "";
  fill.style.width = `${Math.min(Math.max(normalizeNumber(meta.percent), 0), 100)}%`;
  renderScriptPlan("excelQuote", meta.scriptPlan);
  renderProgressLog("excelQuote", meta.analysisLogText, visible);
}

function resetExcelQuoteProgress() {
  renderExcelQuoteProgress({
    stage: "queued",
    stageTag: "未启动",
    stageLabel: "等待开始",
    percent: 0,
    detail: "上传后会立即创建报价任务",
    hint: "上传后会先生成财务传统报价，再由千问结合 skills 知识内容生成 AI 报价",
    analysisLogText: "",
  }, true);
}

function renderAiRouteProgress(meta, visible = true) {
  ensureAiRouteProgressUi();
  const panel = document.getElementById("aiRouteProgressPanel");
  const fill = document.getElementById("aiRouteProgressFill");
  if (!panel || !fill) return;
  const stage = String(meta.stage || "");
  ["stage-queued", "stage-preparing", "stage-market_pricing", "stage-rule_pricing", "stage-pricing", "stage-ai_supplement", "stage-ai_pricing", "stage-finalizing", "stage-done"].forEach((name) => {
    panel.classList.remove(name);
  });
  if (stage) panel.classList.add(`stage-${stage}`);
  panel.classList.toggle("is-waiting", Boolean(meta.waiting));
  panel.classList.toggle("hidden", !visible);
  document.getElementById("aiRouteProgressLabel").textContent = meta.stageLabel || "AI 报价处理中";
  document.getElementById("aiRouteProgressPercent").textContent = `${Math.round(normalizeNumber(meta.percent))}%`;
  document.getElementById("aiRouteProgressStageTag").textContent = meta.stageTag || "处理中";
  document.getElementById("aiRouteProgressDetail").textContent = meta.detail || "等待任务继续推进";
  document.getElementById("aiRouteProgressHint").textContent = meta.hint || "";
  fill.style.width = `${Math.min(Math.max(normalizeNumber(meta.percent), 0), 100)}%`;
  renderScriptPlan("aiRoute", meta.scriptPlan);
  renderProgressLog("aiRoute", meta.analysisLogText, visible);
}

function resetAiRouteProgress() {
  renderAiRouteProgress({
    stage: "queued",
    stageTag: "未启动",
    stageLabel: "等待并行生成",
    percent: 0,
    detail: "开始报价测算后启动 AI 独立报价",
    hint: "千问会结合 skills 知识内容生成 AI 报价，当前页面展示的是模型最终结果。",
    analysisLogText: "",
  }, false);
  setNodeText("#aiRouteStatusChip", "等待启动");
}

function renderExcelQuoteExports(payloadOrPayloads = null) {
  const panel = document.getElementById("excelQuoteExports");
  const list = document.getElementById("excelQuoteExportsList");
  const summaryNode = document.getElementById("excelQuoteExportsSummary");
  const groups = buildExcelExportGroups(payloadOrPayloads);
  const exports = groups.flatMap((group) => group.exports.map((item) => ({ ...item, groupLabel: group.groupLabel, volumeLabel: group.volumeLabel })));
  if (!exports.length) {
    panel.classList.add("hidden");
    list.innerHTML = "";
    summaryNode.textContent = "完成后会在这里汇总展示多个报价 Excel 结果。";
    document.getElementById("downloadExcelPackageBtn").disabled = true;
    return;
  }
  panel.classList.remove("hidden");
  summaryNode.textContent = groups.length > 1
    ? `已汇总 ${groups.length} 个量产档位、共 ${exports.length} 份报价 Excel 结果，可一键下载总压缩包。`
    : `已汇总 ${exports.length} 份报价 Excel 结果，可一键下载打包文件。`;
  list.innerHTML = exports.map((item) => `
    <div class="excel-export-item">
      <strong>${item.groupLabel}${item.volumeLabel && !String(item.groupLabel).includes(item.volumeLabel) ? `｜${item.volumeLabel}` : ""}｜${item.label}</strong>
      <span>${item.item_count || 0} 条</span>
      <span>${item.description || ""}</span>
      <span>${item.filename || ""}</span>
    </div>
  `).join("");
  document.getElementById("downloadExcelPackageBtn").disabled = false;
}

function setExcelQuoteStatus(task) {
  syncExcelQuoteTaskUi(task);
}

function finalizeExcelQuoteTask(payload) {
  loadExcelScenario(payload);
  const summary = payload.summary || {};
  document.getElementById("excelQuoteStatus").textContent =
    `已生成 ${payload.model?.item_count || 0} 条报价，财务传统 ${money(summary.finance_total || 0)}，基准报价 ${money(summary.ai_total || 0)}`;
  document.getElementById("excelQuoteKingdeeHint").textContent =
    summary.finance_missing_count
      ? `当前有 ${summary.finance_missing_count} 条缺传统采购参考，系统已按千问 + skills 知识内容生成 AI 报价补位；另有 ${summary.high_gap_count || 0} 条价差超过 15%`
      : `已命中 ${summary.kingdee_reference_count || 0} 条金蝶参考价，并同步生成 AI 报价与差异分析`;
}

function syncExcelQuoteTaskUi(task) {
  const progress = task?.progress || {};
  const processed = normalizeNumber(progress.processed);
  const total = normalizeNumber(progress.total);
  const stage = String(progress.stage || "");
  const baseMessage = String(progress.message || "").trim();
  if (baseMessage) {
    document.getElementById("excelQuoteStatus").textContent = baseMessage;
  } else if (["pricing", "ai_pricing"].includes(stage) && total > 0) {
    document.getElementById("excelQuoteStatus").textContent = `正在报价，已处理 ${processed} / ${total}`;
  } else if (stage === "preparing") {
    document.getElementById("excelQuoteStatus").textContent = "正在准备报价";
  } else {
    document.getElementById("excelQuoteStatus").textContent = "报价中";
  }
  renderExcelQuoteProgress(deriveExcelQuoteProgress(progress), true);
}

function completeExcelQuoteTask(payload) {
  finalizeExcelQuoteTask(payload);
  state.lastExcelQuotePayload = payload;
  const payloads = Array.isArray(state.lastExcelQuotePayloads) ? [...state.lastExcelQuotePayloads] : [];
  const requestVolume = normalizeNumber(payload?.model?.requested_annual_volume || payload?.model?.annual_volume || 0);
  const sameIndex = payloads.findIndex((item) => normalizeNumber(item?.model?.requested_annual_volume || item?.model?.annual_volume || 0) === requestVolume);
  if (sameIndex >= 0) {
    payloads[sameIndex] = payload;
  } else {
    payloads.push(payload);
  }
  state.lastExcelQuotePayloads = payloads;
  const summary = payload.summary || {};
  document.getElementById("excelQuoteKingdeeHint").textContent =
    summary.finance_missing_count
      ? `当前有 ${summary.finance_missing_count} 条缺传统采购参考，系统已按千问 + skills 知识内容生成 AI 报价补位；另有 ${summary.high_gap_count || 0} 条价差超过 15%，系统已汇总多份 Excel 结果包`
      : `已命中 ${summary.kingdee_reference_count || 0} 条金蝶参考价，并同步生成 AI 报价、多份 Excel 结果与汇总下载包`;
  renderExcelQuoteProgress({
    stage: "done",
    stageTag: "已完成",
    stageLabel: "报价完成",
    percent: 100,
    detail: `已生成 ${payload.model?.item_count || 0} 条报价记录`,
    hint: `Skill 报价结果已生成 ${buildExcelExportList(payload).length} 份 Excel，可下载汇总包`,
    scriptPlan: payload.backend?.skill_script_plan || null,
    analysisLogText: payload.analysis_log_text || "",
  }, true);
  renderExcelQuoteExports(state.lastExcelQuotePayloads);
}

function syncAiRouteTaskUi(task) {
  const progress = task?.progress || {};
  const stage = String(progress.stage || "");
  const meta = deriveExcelQuoteProgress(progress);
  renderAiRouteProgress(meta, true);
  if (stage === "done") {
    setNodeText("#aiRouteStatusChip", "已完成");
  } else if (stage === "finalizing") {
    setNodeText("#aiRouteStatusChip", "汇总中");
  } else if (stage === "ai_pricing") {
    setNodeText("#aiRouteStatusChip", "并行生成");
  } else if (stage === "preparing") {
    setNodeText("#aiRouteStatusChip", "准备中");
  } else {
    setNodeText("#aiRouteStatusChip", meta.stageTag || "处理中");
  }
}

function completeAiRouteTask(task, scenarioId, scenarioSource = "金蝶导入") {
  const payload = task?.payload || {};
  state.aiRouteTaskId = null;
  state.lastAiRoutePayload = payload;
  state.lastExcelQuotePayload = payload;
  state.lastExcelQuotePayloads = payload?.items?.length ? [payload] : [];
  renderExcelQuoteExports(state.lastExcelQuotePayloads);
  state.scenarioItems[scenarioId] = (payload.items || []).map((item) => calcQuoteItem(item, item.source_tag || scenarioSource));
  if (state.financeScenario === scenarioId || state.engineerScenario === scenarioId) {
    renderAll();
  }
  renderAiRouteProgress({
    stage: "done",
    stageTag: "已完成",
    stageLabel: "AI报价处理完成",
    percent: 100,
    detail: `已生成 ${payload.model?.item_count || state.scenarioItems[scenarioId]?.length || 0} 条基准报价记录`,
    hint: `AI 报价结果已同步生成 ${buildExcelExportList(payload).length} 份 Excel，可在上方下载汇总包`,
    scriptPlan: payload.backend?.skill_script_plan || null,
    analysisLogText: payload.analysis_log_text || "",
  }, true);
  setNodeText("#aiRouteStatusChip", "已完成");
  document.getElementById("importStatus").textContent = `已导入 ${payload.model?.item_count || state.scenarioItems[scenarioId]?.length || 0} 条，基准报价已刷新`;
}

function pollAiRouteTask(taskId, pollToken, scenarioId, scenarioSource = "金蝶导入") {
  fetchAiRouteTask(taskId)
    .then((task) => {
      if (pollToken !== state.aiRoutePollToken) return;
      if (task.error && !["TASK_NOT_FOUND"].includes(task.error) && task.status !== "failed") {
        throw new Error(task.message || task.error);
      }
      if (task.status === "succeeded") {
        completeAiRouteTask(task, scenarioId, scenarioSource);
        return;
      }
      if (task.status === "failed") {
        const meta = deriveExcelQuoteProgress(task.progress || {});
        renderAiRouteProgress({
          ...meta,
          stageTag: "失败",
          stageLabel: "AI报价处理失败",
          percent: 100,
          detail: task.message || task.error || meta.detail || "AI报价处理失败",
          hint: "请检查 Skill 规则输入、金蝶 BOM 数据或 AI 接口状态后重试。",
        }, true);
        setNodeText("#aiRouteStatusChip", "失败");
        document.getElementById("importStatus").textContent = `基准报价刷新失败：${task.message || task.error || "AI报价处理失败"}`;
        state.aiRouteTaskId = null;
        alert(`AI报价处理失败：${task.message || task.error || "AI报价处理失败"}`);
        return;
      }
      syncAiRouteTaskUi(task);
      window.setTimeout(() => pollAiRouteTask(taskId, pollToken, scenarioId, scenarioSource), 1200);
    })
    .catch((err) => {
      if (pollToken !== state.aiRoutePollToken) return;
      state.aiRouteTaskId = null;
      renderAiRouteProgress({
        stage: "ai_pricing",
        stageTag: "失败",
        stageLabel: "AI报价处理失败",
        percent: 100,
        detail: err.message,
        hint: "请检查 Skill 规则输入、金蝶 BOM 数据或 AI 接口状态后重试。",
      }, true);
      setNodeText("#aiRouteStatusChip", "失败");
      document.getElementById("importStatus").textContent = `基准报价刷新失败：${err.message}`;
      alert(`AI报价处理失败：${err.message}`);
    });
}

function pollExcelQuoteTask(taskId, pollToken, failureCount = 0) {
  fetchExcelQuoteTask(taskId)
    .then((task) => {
      if (pollToken !== state.excelQuotePollToken) return;
      if (task.error && !["TASK_NOT_FOUND"].includes(task.error) && task.status !== "failed") {
        throw new Error(task.message || task.error);
      }
      if (task.status === "succeeded") {
        completeExcelQuoteTask(task.payload || {});
        return;
      }
      if (task.status === "failed") {
        renderExcelQuoteProgress({
          ...deriveExcelQuoteProgress(task.progress || {}),
          stageTag: "失败",
          stageLabel: "报价处理失败",
          percent: 100,
          detail: task.message || task.error || "报价失败",
          hint: "请检查 Excel 模板、必填字段和服务状态后重试。",
        }, true);
        document.getElementById("excelQuoteStatus").textContent = "报价失败";
        alert(`Excel 报价失败：${task.message || task.error || "报价失败"}`);
        return;
      }
      syncExcelQuoteTaskUi(task);
      window.setTimeout(() => pollExcelQuoteTask(taskId, pollToken, 0), 1200);
    })
    .catch((err) => {
      if (pollToken !== state.excelQuotePollToken) return;
      const nextFailureCount = failureCount + 1;
      if (nextFailureCount <= 3) {
        document.getElementById("excelQuoteStatus").textContent = `连接波动，正在重试报价任务状态（${nextFailureCount}/3）`;
        window.setTimeout(() => pollExcelQuoteTask(taskId, pollToken, nextFailureCount), 1500);
        return;
      }
      document.getElementById("excelQuoteStatus").textContent = "报价失败";
      alert(`Excel 报价失败：${err.message}`);
    });
}

function getForm() {
  return {
    code: document.getElementById("code").value.trim(),
    name: document.getElementById("name").value.trim(),
    material: document.getElementById("material").value.trim(),
    weight_kg: normalizeNumber(document.getElementById("weight").value),
    loss: normalizeNumber(document.getElementById("loss").value),
    process: document.getElementById("process").value.trim(),
    ct: normalizeNumber(document.getElementById("ct").value),
    rate: normalizeNumber(document.getElementById("rate").value),
    qty: normalizeNumber(document.getElementById("qty").value) || 1,
    extra: normalizeNumber(document.getElementById("extra").value),
  };
}

function getSingleBomForm() {
  const productionMode = document.getElementById("singleBomProductionMode").value || "sample";
  return {
    code: document.getElementById("singleBomCode").value.trim(),
    name: document.getElementById("singleBomName").value.trim(),
    material: document.getElementById("singleBomMaterial").value.trim(),
    weight_kg: normalizeNumber(document.getElementById("singleBomWeight").value),
    loss: optionalNumberInput("singleBomLoss"),
    process: document.getElementById("singleBomProcess").value.trim(),
    ct: optionalNumberInput("singleBomCt"),
    rate: optionalNumberInput("singleBomRate"),
    qty: normalizeNumber(document.getElementById("singleBomQty").value) || 1,
    extra: optionalNumberInput("singleBomExtra"),
    production_mode: productionMode,
    annual_volume: productionMode === "mass" ? normalizeNumber(document.getElementById("singleBomAnnualVolume").value) : 0,
  };
}

function getExcelQuoteOptions() {
  const productionMode = document.getElementById("excelQuoteProductionMode")?.value || "sample";
  const parsedAnnualVolumes = productionMode === "mass"
    ? parseAnnualVolumeInputValues(document.getElementById("excelQuoteAnnualVolume")?.value)
    : [];
  const annualVolumes = productionMode === "mass" ? getExcelQuoteSelectedAnnualVolumes() : [];
  const annualVolume = productionMode === "mass"
    ? (annualVolumes[0] || parsedAnnualVolumes[0] || 0)
    : 0;
  return {
    productionMode,
    annualVolume,
    annualVolumes,
  };
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function decorateExcelQuotePayloadForVolume(payload, requestedAnnualVolume, requestIndex, totalRequests) {
  const normalizedVolume = Math.max(0, Math.round(normalizeNumber(requestedAnnualVolume || 0)));
  if (!payload || normalizedVolume <= 0) return payload;
  const nextPayload = { ...payload, model: { ...(payload.model || {}) } };
  const originalLabel = String(nextPayload.model.original_label || nextPayload.model.label || nextPayload.model.filename || `Excel报价_${Date.now()}`).trim();
  const originalFilename = String(nextPayload.model.original_filename || nextPayload.model.filename || originalLabel).trim();
  const requestLabel = buildMassVolumeRequestLabel(normalizedVolume);
  nextPayload.model.original_label = originalLabel;
  nextPayload.model.original_filename = originalFilename;
  nextPayload.model.annual_volume = normalizedVolume;
  nextPayload.model.requested_annual_volume = normalizedVolume;
  nextPayload.model.requested_volume_label = requestLabel;
  nextPayload.model.label = `${originalLabel}｜${requestLabel}`;
  nextPayload.model.filename = `${originalFilename}_${normalizedVolume}套年`;
  nextPayload.model.request_index = requestIndex + 1;
  nextPayload.model.request_count = totalRequests;
  return nextPayload;
}

async function waitForExcelQuoteTask(taskId, pollToken) {
  let failureCount = 0;
  while (true) {
    if (pollToken !== state.excelQuotePollToken) {
      throw new Error("报价任务已被新的提交替换");
    }
    try {
      const task = await fetchExcelQuoteTask(taskId);
      if (task.error && !["TASK_NOT_FOUND"].includes(task.error) && task.status !== "failed") {
        throw new Error(task.message || task.error);
      }
      if (task.status === "succeeded") {
        return task.payload || {};
      }
      if (task.status === "failed") {
        throw new Error(task.message || task.error || "报价失败");
      }
      syncExcelQuoteTaskUi(task);
      failureCount = 0;
      await delay(1200);
    } catch (error) {
      failureCount += 1;
      if (failureCount <= 3) {
        document.getElementById("excelQuoteStatus").textContent = `连接波动，正在重试报价任务状态（${failureCount}/3）`;
        await delay(1500);
        continue;
      }
      throw error;
    }
  }
}

async function submitExcelQuoteForVolumes({ file = null, tableText = "", modelLabel = "", options = {} }) {
  const normalizedText = String(tableText || "").trim();
  const productionMode = options.productionMode || "sample";
  const requestedVolumes = productionMode === "mass"
    ? (Array.isArray(options.annualVolumes) && options.annualVolumes.length ? options.annualVolumes : [options.annualVolume])
        .map((value) => Math.max(0, Math.round(normalizeNumber(value || 0))))
        .filter((value) => value > 0)
    : [0];
  const volumes = requestedVolumes.length ? [...new Set(requestedVolumes)] : [0];
  const payloads = [];
  state.lastExcelQuotePayloads = [];

  const referenceVolume = productionMode === "mass" && volumes.length > 1
    ? (volumes.includes(3000) ? 3000 : volumes[volumes.length - 1])
    : volumes[0];
  const referenceIndex = volumes.indexOf(referenceVolume);
  const referenceLabel = productionMode === "mass" ? buildMassVolumeRequestLabel(referenceVolume) : "样品/小批";
  const pollToken = prepareExcelQuoteSubmission(
    `正在提交基准量产报价：${referenceLabel}`,
    `报价任务已提交（基准档位 ${referenceLabel}）`,
  );
  const requestOptions = {
    productionMode,
    annualVolume: referenceVolume,
    annualVolumes: volumes,
  };
  const task = file
    ? await quoteExcelWorkbook(file, modelLabel, requestOptions)
    : await quoteExcelPastedTable(normalizedText, modelLabel, requestOptions);
  if (task.error) throw new Error(task.message || task.error);
  state.excelQuoteTaskId = task.task_id || null;
  syncExcelQuoteTaskUi(task);
  const referencePayload = await waitForExcelQuoteTask(task.task_id, pollToken);
  const alignedReferencePayload = productionMode === "mass"
    ? await reprojectMassQuotePayload(referencePayload, referenceVolume, referenceLabel)
    : referencePayload;
  const decoratedReferencePayload = decorateExcelQuotePayloadForVolume(alignedReferencePayload, referenceVolume, referenceIndex, volumes.length);
  completeExcelQuoteTask(decoratedReferencePayload);
  payloads.push(decoratedReferencePayload);

  if (productionMode === "mass" && volumes.length > 1) {
    for (let index = 0; index < volumes.length; index += 1) {
      const annualVolume = volumes[index];
      if (annualVolume === referenceVolume) continue;
      const requestLabel = buildMassVolumeRequestLabel(annualVolume);
      document.getElementById("excelQuoteStatus").textContent = `正在沿用同一基准 AI 结果重算：${requestLabel}`;
      const reprojection = await reprojectMassQuotePayload(referencePayload, annualVolume, requestLabel);
      const decoratedPayload = decorateExcelQuotePayloadForVolume(reprojection, annualVolume, index, volumes.length);
      completeExcelQuoteTask(decoratedPayload);
      payloads.push(decoratedPayload);
    }
  }

  payloads.sort((left, right) => normalizeNumber(left?.model?.requested_annual_volume || left?.model?.annual_volume) - normalizeNumber(right?.model?.requested_annual_volume || right?.model?.annual_volume));
  state.lastExcelQuotePayloads = payloads;
  state.lastExcelQuotePayload = payloads[payloads.length - 1] || decoratedReferencePayload;
  if (payloads.length > 1) {
    renderExcelQuoteExports(state.lastExcelQuotePayloads);
    document.getElementById("excelQuoteStatus").textContent = `已完成 ${payloads.length} 组量产报价：${payloads.map((payload) => payload.model?.requested_volume_label || payload.model?.annual_volume || "-").join("；")}`;
  }
  return payloads;
}

function calcManualPreview(item) {
  const rawLookup = latestRawPrice(item.material);
  const rawPrice = normalizeNumber(rawLookup.price);
  const loss = normalizeNumber(item.loss);
  const ct = normalizeNumber(item.ct);
  const rate = normalizeNumber(item.rate);
  const extra = normalizeNumber(item.extra);
  const materialCost = rawPrice * item.weight_kg * (1 + loss);
  const processCost = (ct / 60) * rate;
  return { rawPrice, unitCost: materialCost + processCost + extra, materialCost, processCost, extra, loss };
}

function formatSingleBomCalcNote(payloadItem = null, form = getSingleBomForm()) {
  const loss = normalizeNumber(payloadItem?.loss ?? form.loss);
  const effectiveWeight = normalizeNumber(payloadItem?.effectiveWeightKg ?? payloadItem?.effective_weight_kg ?? 0);
  const manualProcessUnit = normalizeNumber(payloadItem?.manualProcessUnit ?? payloadItem?.manual_process_unit ?? ((normalizeNumber(form.ct) / 60) * normalizeNumber(form.rate)));
  const manualExtraUnit = normalizeNumber(payloadItem?.manualExtraUnit ?? payloadItem?.manual_extra_unit ?? form.extra);
  const notes = [];
  if (loss > 0 && effectiveWeight > 0) {
    notes.push(`损耗率 ${f2(loss * 100)}% 已折算到计价重量 ${f4(effectiveWeight)} kg`);
  } else if (loss > 0) {
    notes.push(`损耗率 ${f2(loss * 100)}% 已记录，但当前重量为空，未参与重量放大`);
  }
  if (manualProcessUnit > 0) {
    notes.push(`节拍费率附加 ${money(manualProcessUnit)}/件`);
  }
  if (manualExtraUnit > 0) {
    notes.push(`采购/外协附加 ${money(manualExtraUnit)}/件`);
  }
  return notes.length ? notes.join("；") : "未填写可选项时，系统按基础 BOM 信息直接试算。";
}

function applySingleBomQuotePreview(result = null) {
  const form = getSingleBomForm();
  const manual = calcManualPreview(form);
  const payloadItem = result?.items?.[0] ? calcQuoteItem(result.items[0], result.items[0].source_tag || "单物料试算") : null;
  const financeUnit = payloadItem ? normalizeNumber(payloadItem.financeRouteUnitPrice) : manual.unitCost;
  const aiUnit = payloadItem ? normalizeNumber(payloadItem.aiRouteUnitPrice) : 0;
  const qty = normalizeNumber(payloadItem?.qty ?? form.qty) || 1;
  const rawPrice = payloadItem ? normalizeNumber(payloadItem.rawPrice ?? payloadItem.material_price ?? payloadItem.materialPrice) : manual.rawPrice;

  document.getElementById("singleBomUnitCost").textContent = money(financeUnit);
  document.getElementById("singleBomFinanceUnitCost").textContent = money(financeUnit);
  document.getElementById("singleBomRawPrice").textContent = rawPrice ? `${f2(rawPrice)} 元/kg` : "暂无参考价";
  document.getElementById("singleBomSubtotal").textContent = money(financeUnit * qty);
  document.getElementById("singleBomFinanceSubtotal").textContent = money(financeUnit * qty);
  document.getElementById("singleBomFinanceSource").textContent = payloadItem?.financeRouteSource || "等待计算";
  document.getElementById("singleBomAiUnitCost").textContent = money(aiUnit);
  document.getElementById("singleBomAiSubtotal").textContent = money(aiUnit * qty);
  document.getElementById("singleBomAiStatus").textContent = payloadItem?.aiRouteStatus || "等待计算";
  document.getElementById("singleBomAiReason").textContent = payloadItem?.aiRouteReasoning || "点击“更新试算”后生成 AI 报价说明";
  document.getElementById("singleBomCalcNote").textContent = formatSingleBomCalcNote(payloadItem, form);
}

function renderMeta() {
  const liveFlag = state.data?.meta?.live_price_enabled ? "已启用在线行情价" : "未启用在线行情价";
  const loadModeLabel = state.loadMode === "api" ? "后端 API 驱动" : "静态 JSON 回退";
  document.getElementById("meta").textContent = `当前数据源：${state.data?.meta?.bom_source || "-"} + ${state.data?.meta?.trend_source || "-"}，${liveFlag}，${loadModeLabel}。`;
}

function renderTabs() {
  const financeActive = state.activeView === "finance";
  document.getElementById("financeTab").classList.toggle("active", financeActive);
  document.getElementById("engineerTab").classList.toggle("active", !financeActive);
  document.getElementById("financeView").classList.toggle("active", financeActive);
  document.getElementById("engineerView").classList.toggle("active", !financeActive);
}

function renderFinanceModules() {
  const activeModule = state.financeModule || "warehouse-recheck";
  document.querySelectorAll("[data-finance-module-target]").forEach((node) => {
    node.classList.toggle("active", node.dataset.financeModuleTarget === activeModule);
  });
  document.querySelectorAll(".finance-module-section").forEach((node) => {
    node.classList.toggle("active", node.dataset.financeModule === activeModule);
  });
  document.querySelectorAll(".finance-detail-card, .finance-bottom-detail, #financeView .table-wrap").forEach((node) => {
    const detailCard = node.closest("section.card") || node;
    detailCard.style.display = activeModule === "band-config" ? "none" : "";
  });
}

function renderScenarioSelect() {
  const select = document.getElementById("scenarioSelect");
  select.innerHTML = state.scenarios.map((item) => `<option value="${item.id}">${item.label}</option>`).join("");
  state.financeScenario = state.financeScenario || state.scenarios[0]?.id || null;
  if (state.financeScenario) select.value = state.financeScenario;
}

function renderFinanceSummary() {
  const items = getActiveItems();
  const summary = buildQuoteSummary(items);
  const financeTotal = normalizeNumber(summary.finance_total);
  const aiTotal = normalizeNumber(summary.ai_total);
  const volumeBaselineTotal = normalizeNumber(summary.volume_baseline_total);
  const volumeConservativeTotal = normalizeNumber(summary.volume_conservative_total);
  const volumeAggressiveTotal = normalizeNumber(summary.volume_aggressive_total);
  const routeGap = normalizeNumber(summary.route_gap_total);
  const totalWeight = normalizeNumber(summary.total_weight);
  const reviewCount = items.filter((item) => ["待补参数", "缺传统参考", "待AI报价", "价差待复核", "缺重量", "缺材质", "模型超时", "AI未配置", "AI接口异常", "估重待复核", "名称规格推断报价"].includes(item.status)).length;
  const materialCost = items.reduce((sum, item) => sum + normalizeNumber(item.changjiangMaterialCost) * normalizeNumber(item.qty), 0);
  const processCost = items.reduce((sum, item) => sum + normalizeNumber(item.changjiangProcessCost) * normalizeNumber(item.qty), 0);
  const financeCoverage = items.length ? (items.filter((item) => item.financeRouteHasReference).length / items.length) * 100 : 0;
  const currentScenario = getActiveScenario();
  const hasMassTotals = volumeBaselineTotal > 0 || volumeConservativeTotal > 0 || volumeAggressiveTotal > 0;

  document.getElementById("financeTotal").textContent = money(financeTotal);
  document.getElementById("aiTotal").textContent = money(aiTotal);
  document.getElementById("routeGap").textContent = signedMoney(routeGap);
  document.getElementById("financeWeight").textContent = `${f2(totalWeight)} kg`;
  document.getElementById("financeItemCount").textContent = String(items.length);
  document.getElementById("financePending").textContent = String(reviewCount);
  document.getElementById("breakMat").textContent = money(materialCost);
  document.getElementById("breakProc").textContent = money(processCost);
  document.getElementById("breakCoverage").textContent = `${f2(financeCoverage)}%`;
  document.getElementById("financeModelName").textContent = currentScenario?.label || "-";
  document.getElementById("aiRouteSummaryLabel").textContent = hasMassTotals
    ? `量产总价：基准 ${money(volumeBaselineTotal)} / 保守 ${money(volumeConservativeTotal)} / 激进 ${money(volumeAggressiveTotal)}`
    : "独立 AI 路线估价";

  if (summary.high_gap_count > 0) {
    document.getElementById("financeStatus").textContent = "存在价差分歧";
    document.getElementById("financeHeadline").textContent = hasMassTotals
      ? `当前有 ${summary.high_gap_count} 条物料基准报价与财务传统价差超过 15%，量产总价概览为基准 ${money(volumeBaselineTotal)} / 保守 ${money(volumeConservativeTotal)} / 激进 ${money(volumeAggressiveTotal)}。`
      : `当前有 ${summary.high_gap_count} 条物料基准报价与财务传统价差超过 15%，建议优先复核差异最大的子项。`;
  } else if (summary.finance_missing_count > 0) {
    document.getElementById("financeStatus").textContent = "缺传统参考";
    document.getElementById("financeHeadline").textContent = hasMassTotals
      ? `当前有 ${summary.finance_missing_count} 条缺传统采购参考，量产总价概览为基准 ${money(volumeBaselineTotal)} / 保守 ${money(volumeConservativeTotal)} / 激进 ${money(volumeAggressiveTotal)}。`
      : `当前有 ${summary.finance_missing_count} 条缺传统采购参考，千问基于 skills 知识内容生成的 AI 报价可作为补充参考。`;
  } else if (summary.ai_unavailable_count > 0) {
    document.getElementById("financeStatus").textContent = "待AI报价";
    document.getElementById("financeHeadline").textContent = `当前有 ${summary.ai_unavailable_count} 条未形成有效 AI 报价，请优先补齐材质、重量、工艺后重试。`;
  } else {
    document.getElementById("financeStatus").textContent = "双路线已齐";
    document.getElementById("financeHeadline").textContent = hasMassTotals
      ? `财务传统和 AI 报价已全部生成，当前总价差 ${signedMoney(routeGap)}；量产总价概览为基准 ${money(volumeBaselineTotal)} / 保守 ${money(volumeConservativeTotal)} / 激进 ${money(volumeAggressiveTotal)}。`
      : `财务传统和 AI 报价已全部生成，当前总价差 ${signedMoney(routeGap)}。`;
  }
  if (!state.aiRouteTaskId) {
    if (summary.ai_ready_count > 0) {
      setNodeText("#aiRouteStatusChip", "已生成");
    } else if (summary.ai_unavailable_count > 0) {
      setNodeText("#aiRouteStatusChip", "待生成");
    } else {
      setNodeText("#aiRouteStatusChip", "等待启动");
    }
  }
}

function renderFinanceTable() {
  const items = getActiveItems();
  const filteredItems = state.financeStatusFilter === "all"
    ? items
    : items.filter((item) => String(item.status || "").trim() === state.financeStatusFilter);
  renderFinanceTableLayout(items);
  const tbody = document.getElementById("financeTable");
  const isMass = isMassPricingMode(items);
  if (!filteredItems.length) {
    const colspan = isMass ? 17 : 14;
    tbody.innerHTML = `<tr><td class="cell-empty-state" colspan="${colspan}">当前筛选条件下没有匹配的报价记录</td></tr>`;
    return;
  }
  tbody.innerHTML = filteredItems.map((item) => {
    const financeValue = normalizeNumber(item.financeRouteUnitPrice || item.finance_route_unit_price);
    const baselineValue = normalizeNumber(item.aiRouteUnitPrice || item.ai_route_unit_price || item.volume_baseline_unit_price);
    const qty = normalizeNumber(item.qty || 1) || 1;
    const sourceRefs = splitSourceReferences(item.sourceTag || item.source_tag || "-");
    const displayedGapUnit = isMass && normalizeNumber(item.volume_baseline_unit_price) > 0
      ? baselineValue - financeValue
      : normalizeNumber(item.routeGapUnitPrice || item.route_gap_unit_price);
    const displayedReason = isMass && normalizeNumber(item.volume_baseline_unit_price) > 0
      ? formatMassBaselineReason(item)
      : formatAiReason(item);
    const volumeCells = isMass ? `
      ${renderQuotedMoneyCell(baselineValue || 0, qty, "cell-volume-base")}
      ${renderQuotedMoneyCell(normalizeNumber(item.volume_conservative_unit_price || 0), qty, "cell-volume-cons")}
      ${renderQuotedMoneyCell(normalizeNumber(item.volume_aggressive_unit_price || 0), qty, "cell-volume-aggr")}
      ${buildMassToolingTableCell(item)}
    ` : "";
    const baselineCell = !isMass ? renderQuotedMoneyCell(baselineValue || 0, qty, "cell-ai-main") : "";
    return `
      <tr>
        <td class="cell-code">${item.code || ""}</td>
        <td class="cell-name">${item.name || ""}</td>
        <td class="cell-source"><span class="source-tag">${sourceRefs.finance}</span></td>
        <td class="cell-source"><span class="source-tag">${sourceRefs.aiSkills}</span></td>
        <td class="cell-material">${item.material || "-"}</td>
        <td class="cell-number">${f2(qty)}</td>
        ${renderWeightCell(item)}
        ${renderQuotedMoneyCell(financeValue || 0, qty, "cell-finance-main")}
        ${baselineCell}
        ${volumeCells}
        ${renderQuotedGapCell(displayedGapUnit || 0, qty)}
        ${renderComparisonReasonCell(item, displayedReason)}
        <td class="cell-status"><span class="row-status ${item.status === "双路线可比" ? "ok" : "warn"}">${item.status}</span></td>
        <td class="cell-finance-source">${item.financeRouteSource || "-"}</td>
        ${renderAiReasonCell(item, displayedReason)}
      </tr>
    `;
  }).join("");
}

function renderComparisonChart() {
  const items = getActiveItems();
  const topGapItems = [...items]
    .filter((item) => Math.abs(normalizeNumber(item.routeGapTotal)) > 0)
    .sort((a, b) => Math.abs(normalizeNumber(b.routeGapTotal)) - Math.abs(normalizeNumber(a.routeGapTotal)))
    .slice(0, 5);
  const maxGap = Math.max(...topGapItems.map((item) => Math.abs(normalizeNumber(item.routeGapTotal))), 1);

  const content = !items.length
    ? '<div class="empty-state">当前还没有可对比的报价数据</div>'
    : `
    <div class="chart-group">
      <div class="chart-caption">价差最大的子项</div>
      ${topGapItems.length ? topGapItems.map((item) => `
        <div class="chart-row compact">
          <span class="chart-label">${item.name}</span>
          <div class="chart-bar"><span class="chart-fill gap" style="width:${(Math.abs(normalizeNumber(item.routeGapTotal)) / maxGap) * 100}%"></span></div>
          <span class="chart-value">${signedMoney(item.routeGapTotal)}</span>
        </div>
      `).join("") : '<div class="empty-state">当前两条路线还没有形成有效价差</div>'}
    </div>
  `;
  ["comparisonChart", "excelComparisonChart"].forEach((id) => {
    const host = document.getElementById(id);
    if (host) host.innerHTML = content;
  });
}

function renderComparisonAnalysis() {
  const items = getActiveItems();
  const content = !items.length
    ? '<div class="empty-state">当前还没有可分析的报价数据</div>'
    : (() => {
      const summary = buildQuoteSummary(items);
      const categories = new Map();
      items.forEach((item) => {
        const key = item.comparisonCategory || "其他";
        categories.set(key, (categories.get(key) || 0) + 1);
      });
      const topCategories = [...categories.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
      const topGapItems = [...items]
        .filter((item) => Math.abs(normalizeNumber(item.routeGapUnitPrice)) > 0)
        .sort((a, b) => Math.abs(normalizeNumber(b.routeGapUnitPrice)) - Math.abs(normalizeNumber(a.routeGapUnitPrice)))
        .slice(0, 4);
      const direction = normalizeNumber(summary.route_gap_total) >= 0
        ? `AI 总价比财务传统高 ${money(summary.route_gap_total)}`
        : `AI 总价比财务传统低 ${money(Math.abs(summary.route_gap_total))}`;
      return `
    <div class="analysis-item">
      <h3>整体判断</h3>
      <p>${direction}，当前共有 ${summary.high_gap_count || 0} 条物料的价差超过 15%，${summary.finance_missing_count || 0} 条缺传统参考。</p>
    </div>
    <div class="analysis-item">
      <h3>主要差异来源</h3>
      <p>${topCategories.length ? topCategories.map(([label, count]) => `${label} ${count} 条`).join("，") : "当前两条路线整体较为接近。"}</p>
    </div>
    <div class="analysis-item">
      <h3>建议优先复核</h3>
      <div class="analysis-lines">
        ${topGapItems.length ? topGapItems.map((item) => `<div class="analysis-line"><strong>${item.name}</strong><span>${item.comparisonReasonSummary || "建议结合供应商和批量进一步确认"}</span></div>`).join("") : '<div class="empty-state">当前没有明显的高差异物料</div>'}
      </div>
    </div>
  `;
    })();
  ["comparisonAnalysis", "excelComparisonAnalysis"].forEach((id) => {
    const host = document.getElementById(id);
    if (host) host.innerHTML = content;
  });
}

function renderEngineerTable() {
  const tbody = document.getElementById("engineerTable");
  tbody.innerHTML = getEngineerItems().map((item) => `
    <tr>
      <td>${item.code || ""}</td>
      <td>${item.name || ""}</td>
      <td>${item.process || "-"}</td>
      <td>${f2(item.qty)}</td>
      <td>${formatSourceTagDisplay(item.sourceTag || item.source_tag || "-")}</td>
    </tr>
  `).join("");
}

function renderPresetOptions() {
  const presetSelect = document.getElementById("presetSelect");
  const options = ['<option value="">璇烽€夋嫨鍘嗗彶瀛愰」</option>'].concat(
    (state.data?.bom_items || []).map((item, index) => `<option value="${index}">${item.code} | ${item.name}</option>`)
  );
  presetSelect.innerHTML = options.join("");
}

function renderPreview() {
  const form = getForm();
  const preview = calcManualPreview(form);
  document.getElementById("previewUnitCost").textContent = money(preview.unitCost);
  document.getElementById("previewRawPrice").textContent = preview.rawPrice ? `${f2(preview.rawPrice)} 元/kg` : "暂无参考价";
}

function renderSingleBomPreview() {
  applySingleBomQuotePreview(state.singleBomQuotePayload);
}

function sanitizeAiReasonText(reasoning = "") {
  const text = String(reasoning || "").trim();
  const lower = text.toLowerCase();
  if (!text) return "";
  if (
    text.includes("HTTPSConnectionPool")
    || lower.includes("httpsconnectionpool")
    || lower.includes("readtimeout")
    || lower.includes("connecttimeout")
    || lower.includes("timed out")
    || lower.includes("read timed out")
  ) {
    return "模型超时：千问接口未在限定时间内返回结果，可重试本次报价";
  }
  if (
    lower.includes("proxyerror")
    || lower.includes("sslerror")
    || lower.includes("max retries exceeded")
    || lower.includes("newconnectionerror")
    || lower.includes("connection aborted")
    || lower.includes("connection reset")
  ) {
    return "AI接口异常：千问接口当前连接不稳定，请稍后重试";
  }
  if (
    lower.includes("invalid chat format")
    || lower.includes("invalid_request_error")
    || lower.includes("expected 'text' field")
    || lower.includes("qwen pricing api error 400")
    || text.includes("AI接口请求格式异常")
    || text.includes("服务已调整，请重新报价")
  ) {
    return "AI补价未成功，请重新报价";
  }
  return text;
}

function formatAiReason(item) {
  const status = String(item.aiRouteStatus || item.ai_route_status || "").trim();
  const reasoning = sanitizeAiReasonText(item.aiRouteReasoning || item.ai_route_reasoning || "");
  const explicitStatuses = ["缺重量", "缺材质", "模型超时", "AI未配置", "待AI报价", "AI接口异常", "估重待复核", "名称规格推断报价"];
  const parts = [];
  if (status && explicitStatuses.includes(status)) {
    parts.push(status);
  }
  if (reasoning && !parts.some((part) => reasoning.includes(part))) {
    parts.push(reasoning);
  }
  if (!parts.length && status) {
    parts.push(status);
  }
  return parts.join("：") || "未返回基准说明";
}

function buildAiAnalysisBreakdown(item) {
  const materialCost = normalizeNumber(item.ai_material_cost_reference ?? item.aiMaterialCostReference ?? 0);
  const processCost = normalizeNumber(item.ai_process_cost_reference ?? item.aiProcessCostReference ?? 0);
  const processRule = String(item.ai_process_rule_reference ?? item.aiProcessRuleReference ?? "").trim();
  const processRuleLabel = String(item.ai_process_rule_label ?? item.aiProcessRuleLabel ?? "").trim();
  const parts = [];
  if (materialCost > 0) parts.push(`材料费：${f2(materialCost)} 元`);
  if (processCost > 0) parts.push(`工艺费：${f2(processCost)} 元`);
  if (processRule) {
    parts.push(processRuleLabel ? `命中的工艺规则：${processRule}（计价口径：${processRuleLabel}）` : `命中的工艺规则：${processRule}`);
  }
  if (!parts.length) return { text: "", html: "" };
  return {
    text: `AI分析拆分（AI计算）：${parts.join("；")}`,
    html: `
      <div class="ai-analysis-breakdown">
        <div class="ai-analysis-title">AI分析拆分（AI计算）</div>
        ${parts.map((part) => `<div class="ai-analysis-item">${escapeHtml(part)}</div>`).join("")}
      </div>
    `,
  };
}

function buildAiInferenceReference(item) {
  const used = Boolean(item.ai_second_stage_used ?? item.aiSecondStageUsed);
  if (!used) return { text: "", html: "" };
  const process = String(item.ai_inferred_process_reference ?? item.aiInferredProcessReference ?? "").trim();
  const material = String(item.ai_inferred_material_reference ?? item.aiInferredMaterialReference ?? "").trim();
  const weight = normalizeNumber(item.ai_inferred_weight_reference ?? item.aiInferredWeightReference ?? 0);
  const confidence = normalizeNumber(item.ai_inference_confidence ?? item.aiInferenceConfidence ?? 0);
  const parts = [];
  if (process) parts.push(`工艺：${process}`);
  if (material) parts.push(`材质：${material}`);
  if (weight > 0) parts.push(`重量：${f4(weight)}kg`);
  if (confidence > 0) parts.push(`置信度：${confidence.toFixed(2)}`);
  if (!parts.length) return { text: "", html: "" };
  return {
    text: `AI推断参考（AI计算，用于本次AI报价）：${parts.join("；")}` ,
    html: `
      <div class="ai-inference-reference">
        <div class="ai-inference-title">AI推断参考（AI计算，用于本次AI报价）</div>
        ${parts.map((part) => `<div class="ai-inference-item">${escapeHtml(part)}</div>`).join("")}
      </div>
    `,
  };
}

function buildSkillsInputReference(item) {
  const process = String(item.skills_input_process ?? item.skillsInputProcess ?? "").trim();
  const material = String(item.skills_input_material ?? item.skillsInputMaterial ?? "").trim();
  const weight = normalizeNumber(item.skills_input_weight_kg ?? item.skillsInputWeightKg ?? 0);
  const processSource = String(item.skills_input_process_source ?? item.skillsInputProcessSource ?? "").trim();
  const materialSource = String(item.skills_input_material_source ?? item.skillsInputMaterialSource ?? "").trim();
  const weightSource = String(item.skills_input_weight_source ?? item.skillsInputWeightSource ?? "").trim();
  const parts = [];
  if (process) parts.push(`工艺：${process}`);
  if (material) parts.push(`材质：${material}`);
  if (weight > 0) parts.push(`重量：${f4(weight)}kg`);
  const sources = [processSource, materialSource, weightSource].filter(Boolean);
  if (sources.length) parts.push(`来源：${[...new Set(sources)].join("；")}`);
  if (!parts.length) return { text: "", html: "" };
  return {
    text: `skills实际采用输入：${parts.join("；")}`,
    html: `
      <div class="ai-inference-reference skills-input-reference">
        <div class="ai-inference-title">skills实际采用输入</div>
        ${parts.map((part) => `<div class="ai-inference-item">${escapeHtml(part)}</div>`).join("")}
      </div>
    `,
  };
}

function buildMassToolingReference(item) {
  const sampleUnit = normalizeNumber(item.sample_machining_unit_price ?? item.sampleMachiningUnitPrice ?? 0);
  const toolingUnit = normalizeNumber(item.mass_tooling_unit_price ?? item.massToolingUnitPrice ?? 0);
  const toolingCost = normalizeNumber(item.tooling_cost ?? item.toolingCost ?? 0);
  const breakEven = normalizeNumber(item.mass_break_even_volume ?? item.massBreakEvenVolume ?? 0);
  const processRoute = String(item.mass_process_route ?? item.massProcessRoute ?? "").trim();
  const parts = [];
  if (sampleUnit > 0) parts.push(`样品机加工单价：${money(sampleUnit)}/件`);
  if (toolingUnit > 0) parts.push(`量产开模单价：${money(toolingUnit)}/件`);
  if (toolingCost > 0) parts.push(`开模费：${money(toolingCost)}`);
  if (breakEven > 0) parts.push(`开模收益平衡点：${Math.round(breakEven)}套/年`);
  if (processRoute) parts.push(`量产工艺：${processRoute}`);
  if (!parts.length) return { text: "", html: "" };
  return {
    text: `量产开模对比：${parts.join("；")}`,
    html: `
      <div class="ai-inference-reference mass-tooling-reference">
        <div class="ai-inference-title">量产开模对比</div>
        ${parts.map((part) => `<div class="ai-inference-item">${escapeHtml(part)}</div>`).join("")}
      </div>
    `,
  };
}

function buildToolingMarketVarianceLabel(toolingCost, rangeText) {
  const cost = normalizeNumber(toolingCost || 0);
  const text = String(rangeText || "").trim();
  const matches = [...text.matchAll(/([0-9][0-9,]*)/g)].map((item) => Number(String(item[1] || "").replace(/,/g, ""))).filter((value) => Number.isFinite(value) && value > 0);
  if (cost <= 0 || matches.length < 2) return "";
  const low = Math.min(matches[0], matches[1]);
  const high = Math.max(matches[0], matches[1]);
  if (cost < low) return "低于行业公开区间";
  if (cost > high) return "高于行业公开区间";
  return "落在行业公开区间内";
}

function renderToolingMarketVarianceBadge(label) {
  const text = String(label || "").trim();
  if (!text) return "";
  let cls = "tooling-market-badge";
  if (text.includes("低于")) cls += " is-low";
  else if (text.includes("高于")) cls += " is-high";
  else cls += " is-normal";
  return `<span class="${cls}">${escapeHtml(text)}</span>`;
}

function buildToolingMarketCompactMeta(category, range, sourceShort, varianceLabel) {
  const varianceBadge = renderToolingMarketVarianceBadge(varianceLabel);
  const rows = [];
  if (category) rows.push(`<div class="ai-inference-item"><strong>工艺类型</strong>：${escapeHtml(category)}</div>`);
  if (sourceShort) rows.push(`<div class="ai-inference-item"><strong>来源简称</strong>：${escapeHtml(sourceShort)}</div>`);
  if (range) rows.push(`<div class="ai-inference-item"><strong>公开区间</strong>：${escapeHtml(range)}</div>`);
  if (varianceLabel) rows.push(`<div class="ai-inference-item"><strong>行业区间判断</strong>：${varianceBadge}</div>`);
  return rows.join("");
}

function buildToolingMarketReference(item) {
  const name = String(item.name || "").trim();
  const spec = String(item.spec || "").trim();
  const process = String(item.process || item.mass_process_route || item.massProcessRoute || "").trim();
  const combined = `${name} ${spec} ${process}`.toLowerCase();
  const toolingCost = normalizeNumber(item.tooling_cost ?? item.toolingCost ?? 0);
  let category = "";
  let range = "";
  let source = "";
  let sourceShort = "";

  if (["前端盖", "后端盖", "端盖", "接线盒", "盖板", "后盖板", "三相盖板"].some((token) => `${name} ${spec}`.includes(token))) {
    category = "压铸/铸造模具";
    range = "USD 5,000–100,000";
    source = "RapidDirect die casting cost article";
    sourceShort = "RapidDirect";
  } else if (["轴", "电机轴", "转轴", "主轴", "花键轴"].some((token) => `${name} ${spec}`.includes(token))) {
    category = "锻造/成形工装";
    range = "当前未接公开网页精确单类区间，建议沿用本地公式估算";
    source = "本页暂未挂外部单类报价";
    sourceShort = "本地公式";
  } else if (combined.includes("注塑") || combined.includes("塑胶")) {
    category = "注塑模具";
    range = "USD 10,000–100,000";
    source = "Xometry injection molding cost article";
    sourceShort = "Xometry";
  }

  if (!category || !range) return { text: "", html: "" };
  const varianceLabel = buildToolingMarketVarianceLabel(toolingCost, range);
  const compactMetaHtml = buildToolingMarketCompactMeta(category, range, sourceShort, varianceLabel);
  const lines = [
    `工艺类型：${category}`,
    `来源简称：${sourceShort || source}`,
    `公开区间：${range}`,
    varianceLabel ? `行业区间判断：${varianceLabel}` : "",
    `参考来源：${source}`,
    "注：公开网页区间仅作行业参考，不直接替代当前物料开模费公式",
  ].filter(Boolean);
  return {
    text: lines.join("；"),
    html: `
      <div class="ai-inference-reference tooling-market-reference">
        <div class="ai-inference-title">行业公开参考</div>
        ${compactMetaHtml}
        <div class="ai-inference-item">${escapeHtml(`参考来源：${source}`)}</div>
        <div class="ai-inference-item">${escapeHtml("注：公开网页区间仅作行业参考，不直接替代当前物料开模费公式")}</div>
      </div>
    `,
  };
}

function buildMassToolingTableCell(item) {
  const sampleUnit = normalizeNumber(item.sample_machining_unit_price ?? item.sampleMachiningUnitPrice ?? 0);
  const toolingUnit = normalizeNumber(item.mass_tooling_unit_price ?? item.massToolingUnitPrice ?? 0);
  const toolingCost = normalizeNumber(item.tooling_cost ?? item.toolingCost ?? 0);
  const breakEven = normalizeNumber(item.mass_break_even_volume ?? item.massBreakEvenVolume ?? 0);
  const marketRef = buildToolingMarketReference(item);
  const parts = [];
  if (sampleUnit > 0) parts.push(`<div><strong>样品机加工单价</strong>：${money(sampleUnit)}/件</div>`);
  if (toolingUnit > 0) parts.push(`<div><strong>量产开模单价</strong>：${money(toolingUnit)}/件</div>`);
  if (toolingCost > 0) parts.push(`<div><strong>开模费</strong>：${money(toolingCost)}</div>`);
  if (breakEven > 0) parts.push(`<div><strong>开模收益平衡点</strong>：${Math.round(breakEven)}套/年</div>`);
  if (marketRef.html) parts.push(marketRef.html);
  if (!parts.length) return '<td class="cell-tooling-compare">-</td>';
  return `<td class="cell-tooling-compare">${parts.join("")}</td>`;
}

function normalizeTextForCompare(value) {
  return String(value || "")
    .replace(/\s+/g, "")
    .replace(/[，。；：、,.\-—_]/g, "")
    .trim();
}

function formatCompactTableText(value, fallback = "-") {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text || fallback;
}

function renderComparisonReasonCell(item, displayedReason) {
  const rawSummary = formatCompactTableText(item.comparisonReasonSummary || item.comparisonCategory || "-");
  const rawCategory = formatCompactTableText(item.comparisonCategory || item.status || "差异说明");
  const summaryKey = normalizeTextForCompare(rawSummary);
  const reasonKey = normalizeTextForCompare(displayedReason);
  const title = [rawSummary, displayedReason].filter(Boolean).join("\n");
  const bothDescribePendingAi = /当前未形成\s*AI\s*报价|待AI报价/.test(rawSummary) && /当前未形成\s*AI\s*报价|待AI报价/.test(displayedReason);

  if (bothDescribePendingAi || (summaryKey && reasonKey && (summaryKey === reasonKey || reasonKey.includes(summaryKey) || summaryKey.includes(reasonKey)))) {
    return `<td class="cell-analysis compact" title="${escapeHtml(title)}"><span class="analysis-chip">${escapeHtml(rawCategory)}</span><div class="cell-clamp muted">同基准说明，移至右侧查看</div></td>`;
  }

  return `<td class="cell-analysis" title="${escapeHtml(title)}"><span class="analysis-chip">${escapeHtml(rawCategory)}</span><div class="cell-clamp">${escapeHtml(rawSummary)}</div></td>`;
}

function renderAiReasonCell(item, displayedReason) {
  const breakdown = buildAiAnalysisBreakdown(item);
  const inference = buildAiInferenceReference(item);
  const skillsInput = buildSkillsInputReference(item);
  const massTooling = buildMassToolingReference(item);
  const toolingMarket = buildToolingMarketReference(item);
  const compactReason = formatCompactTableText(displayedReason, "未返回基准说明");
  const title = [compactReason, breakdown.text, inference.text, skillsInput.text, massTooling.text, toolingMarket.text].filter(Boolean).join("\n");
  return `<td class="cell-ai-reason" title="${escapeHtml(title)}"><div class="cell-clamp ai-reason-main">${escapeHtml(compactReason)}</div><div class="reason-detail-stack">${breakdown.html}${inference.html}${skillsInput.html}${massTooling.html}${toolingMarket.html}</div></td>`;
}

function formatMassBaselineReason(item) {
  const volumeSummary = String(item.volume_pricing_summary || "").trim();
  const aiReason = formatAiReason(item);
  const aiUnit = normalizeNumber(item.aiRouteUnitPrice || item.ai_route_unit_price);
  if (aiUnit > 0) {
    return aiReason || volumeSummary || "已生成量产基准说明";
  }
  if (volumeSummary && aiReason && !volumeSummary.includes(aiReason)) {
    return `${volumeSummary}；AI补充说明：${aiReason}`;
  }
  return volumeSummary || aiReason || "已生成量产基准说明";
}

function resetSingleBomForm() {
  ["singleBomCode", "singleBomName", "singleBomMaterial", "singleBomWeight", "singleBomProcess"].forEach((id) => {
    document.getElementById(id).value = "";
  });
  document.getElementById("singleBomQty").value = 1;
  document.getElementById("singleBomProductionMode").value = "sample";
  document.getElementById("singleBomAnnualVolume").value = 10000;
  document.getElementById("singleBomLoss").value = "";
  document.getElementById("singleBomCt").value = "";
  document.getElementById("singleBomRate").value = "";
  document.getElementById("singleBomExtra").value = "";
  syncProductionModeUi("singleBomProductionMode", "singleBomAnnualVolumeField", "singleBomAnnualVolume", "singleBomProductionModeHint", {
    sample: "样品/小批：按当前材料、重量和工艺直接试算，不启用年产量。",
    mass: "量产：会把年产量传给 AI，并额外生成量产测算参考。",
  });
  state.singleBomQuotePayload = null;
}

function renderIntegration() {
  const backendStatus = state.data?.backend?.kingdee_status || {};
  const kingdee = state.data?.kingdee || {};
  const missing = backendStatus.config?.missing || [];
  const summary = backendStatus.ready
    ? "已有 BOM 后续将通过后端 API 从金蝶读取，工程师只需要维护新型号和缺失字段。"
    : `金蝶后端代理已就位，但当前还缺配置：${missing.join("、") || "待补充"}。在补齐前页面继续使用演示数据。`;
  document.getElementById("integrationSummary").textContent = summary;
  document.getElementById("importSource").textContent = state.data?.meta?.bom_source || "-";
  document.getElementById("importStatus").textContent = backendStatus.ready ? "可接真实金蝶" : "等待配置";
  document.getElementById("kingdeeCards").innerHTML = (kingdee.forms || []).map((form) => `
    <article class="mini-card">
      <h3>${form.name}</h3>
      <p>${form.purpose}</p>
    </article>
  `).join("");
}

function renderBomHeaderOptions() {
  const list = state.bomHeaders || [];
  const baseOption = `<option value="">${getBomHeaderPlaceholder()}</option>`;
  const html = [baseOption].concat(
    list.map((item) => `<option value="${item.bom_number}">${item.parent_name || item.bom_number} | ${item.bom_number}</option>`)
  ).join("");
  const bomHeaderSelect = document.getElementById("bomHeaderSelect");
  const financeBomHeaderSelect = document.getElementById("financeBomHeaderSelect");
  const preferredBomNumber = [
    financeBomHeaderSelect?.value,
    state.selectedFinanceBomNumber,
    document.getElementById("importBomNumber")?.value,
  ].map((value) => String(value || "").trim()).find((value) => value);
  const hasPreferredBom = preferredBomNumber && list.some((item) => item.bom_number === preferredBomNumber);

  bomHeaderSelect.innerHTML = html;
  financeBomHeaderSelect.innerHTML = html;
  if (hasPreferredBom) {
    bomHeaderSelect.value = preferredBomNumber;
    financeBomHeaderSelect.value = preferredBomNumber;
  }
  updateFinanceBomSelectionSummary(hasPreferredBom ? preferredBomNumber : "");
}

function applyBomHeadersPayload(payload, { append = false, keyword = "" } = {}) {
  const rows = Array.isArray(payload?.rows) ? payload.rows : [];
  state.bomHeadersKeyword = keyword;
  state.bomHeadersOffset = Number(payload?.next_offset ?? (append ? state.bomHeadersOffset + rows.length : rows.length)) || 0;
  state.bomHeadersHasMore = Boolean(payload?.has_more);
  state.bomHeaders = append ? state.bomHeaders.concat(rows) : rows;
  setBomHeadersState(state.bomHeaders.length ? "ready" : "empty");
  renderBomHeaderOptions();
  const importStatus = document.getElementById("importStatus");
  if (importStatus) {
    importStatus.textContent = state.bomHeaders.length
      ? `已加载 ${state.bomHeaders.length} 个型号，可直接下拉滚动选择`
      : "当前未查询到匹配型号";
  }
}

function resetBomHeadersPagination(keyword = "") {
  state.bomHeadersKeyword = keyword.trim();
  state.bomHeadersOffset = 0;
  state.bomHeadersHasMore = false;
}

async function loadFinanceBomHeaders(keyword = "", { append = false } = {}) {
  const normalizedKeyword = keyword.trim();
  resetBomHeadersPagination(normalizedKeyword);
  setBomHeadersState("loading");
  renderBomHeaderOptions();
  const payload = await fetchAllBomHeaders(normalizedKeyword);
  if (payload.error) {
    const message = normalizeKingdeeBomHeaderErrorMessage(payload.error, payload.message || payload.error);
    const isConfigMissing = payload.error === "KINGDEE_CONFIG_MISSING";
    state.bomHeaders = [];
    state.bomHeadersHasMore = false;
    setBomHeadersState(
      isConfigMissing ? "config_missing" : "upstream_error",
      message,
    );
    renderBomHeaderOptions();
    const importStatus = document.getElementById("importStatus");
    if (importStatus) importStatus.textContent = state.bomHeadersMessage;
    return payload;
  }
  applyBomHeadersPayload(payload, { append: false, keyword: normalizedKeyword });
  return payload;
}

async function ensureFinanceBomHeadersLoaded(keyword = "", { force = false } = {}) {
  const normalizedKeyword = String(keyword || "").trim();
  const currentKeyword = String(state.bomHeadersKeyword || "").trim();
  const hasRows = Array.isArray(state.bomHeaders) && state.bomHeaders.length > 0;
  const needsReload = force
    || !hasRows
    || state.bomHeadersStatus === "empty"
    || state.bomHeadersStatus === "upstream_error"
    || state.bomHeadersStatus === "config_missing"
    || normalizedKeyword !== currentKeyword;
  if (!needsReload) return { reused: true, rows: state.bomHeaders };

  const importStatus = document.getElementById("importStatus");
  if (importStatus) {
    importStatus.textContent = normalizedKeyword
      ? `正在搜索：${normalizedKeyword}`
      : "正在加载金蝶型号...";
  }

  try {
    return await loadFinanceBomHeaders(normalizedKeyword);
  } catch (err) {
    state.bomHeaders = [];
    state.bomHeadersHasMore = false;
    setBomHeadersState("upstream_error", "金蝶接口异常，暂时无法加载型号");
    renderBomHeaderOptions();
    if (importStatus) importStatus.textContent = `型号列表加载失败：${err.message}`;
    throw err;
  }
}

function loadScenarioBom(scenarioId) {
  if (!scenarioId) return;
  if (!state.scenarioItems[scenarioId]?.length && scenarioId === "double20_drive") {
    state.scenarioItems[scenarioId] = (state.data?.bom_items || []).map((item) => calcQuoteItem(item, "已有 BOM"));
  }
  renderAll();
}

function createScenario(code, name) {
  const safeCode = code.trim();
  const safeName = name.trim();
  if (!safeCode || !safeName) {
    alert("请先填写新型号编码和新型号名称");
    return;
  }
  const existing = state.scenarios.find((item) => item.code === safeCode || item.label === safeName);
  if (existing) {
    state.financeScenario = existing.id;
    state.engineerScenario = existing.id;
    renderAll();
    return;
  }
  const id = `custom_${Date.now()}`;
  state.scenarios.push({ id, code: safeCode, label: safeName, description: "工程师新增型号，待后续同步到金蝶。" });
  state.scenarioItems[id] = [];
  state.financeScenario = id;
  state.engineerScenario = id;
  document.getElementById("modelCode").value = "";
  document.getElementById("modelName").value = "";
  renderAll();
}

function loadSyncedScenario(syncPayload) {
  const model = syncPayload.model || {};
  const bomNumber = model.bom_number || `bom_${Date.now()}`;
  const modelLabel = model.label || bomNumber;
  const existing = state.scenarios.find((item) => item.code === bomNumber);
  const scenarioId = existing?.id || `kingdee_${Date.now()}`;
  if (!existing) {
    state.scenarios.push({ id: scenarioId, code: bomNumber, label: modelLabel, description: "金蝶 BOM 实时导入" });
  }
  state.scenarioItems[scenarioId] = (syncPayload.items || []).map((item) => calcQuoteItem(item, item.source_tag || "金蝶导入"));
  state.financeScenario = scenarioId;
  state.engineerScenario = scenarioId;
  document.getElementById("importBomNumber").value = bomNumber;
  renderAll();
  return scenarioId;
}

async function syncFinanceScenarioFromKingdeeSelection(bomNumber, label = "", { startAi = false } = {}) {
  const normalizedBomNumber = String(bomNumber || "").trim();
  if (!normalizedBomNumber) {
    updateFinanceBomSelectionSummary("");
    document.getElementById("importStatus").textContent = "未选中有效 BOM 编号";
    return null;
  }

  const initialLabel = String(label || "").trim() || normalizedBomNumber;
  applySelectedBom(normalizedBomNumber, initialLabel);
  document.getElementById("importStatus").textContent = startAi
    ? `准备导入：${initialLabel}`
    : `正在同步：${initialLabel}`;

  const payload = await syncBomFromKingdee(normalizedBomNumber);
  if (payload.error) throw new Error(payload.message || payload.error);

  const scenarioId = loadSyncedScenario(payload);
  const resolvedLabel = String(label || payload.model?.label || normalizedBomNumber).trim() || normalizedBomNumber;
  applySelectedBom(normalizedBomNumber, resolvedLabel);
  state.activeView = "finance";
  state.financeModule = "warehouse-recheck";
  state.aiRouteTaskId = null;
  state.lastAiRoutePayload = null;
  resetAiRouteProgress();
  renderAll();

  const itemCount = payload.model?.item_count || payload.items?.length || 0;
  if (startAi) {
    document.getElementById("importStatus").textContent = `已导入 ${itemCount} 条，AI 报价计算中`;
    refreshScenarioAiRoute(scenarioId, payload.model || {}, "金蝶导入");
  } else {
    document.getElementById("importStatus").textContent = `已导入 ${itemCount} 条，财务传统报价已刷新`;
  }
  return { payload, scenarioId };
}

function refreshScenarioAiRoute(scenarioId, model = {}, scenarioSource = "金蝶导入") {
  const items = state.scenarioItems[scenarioId] || [];
  if (!items.length) return;
  const pollToken = nextAiRoutePollToken();
  state.lastAiRoutePayload = null;
  state.aiRouteTaskId = null;
  renderAiRouteProgress({
    stage: "queued",
    stageTag: "已提交",
    stageLabel: "AI报价任务已提交",
    percent: 4,
    detail: "等待服务开始结合 skills 知识内容生成 AI 报价",
    hint: "千问会结合 skills 知识内容生成 AI 报价，当前页面展示的是模型最终结果。",
  }, true);
  setNodeText("#aiRouteStatusChip", "已提交");
  document.getElementById("importStatus").textContent = "AI报价任务已提交";
  document.getElementById("aiRouteProgressPanel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  startAiRouteQuoteTask(items, model, scenarioSource)
    .then((task) => {
      if (task.error) throw new Error(task.message || task.error);
      state.aiRouteTaskId = task.task_id || null;
      syncAiRouteTaskUi(task);
      pollAiRouteTask(task.task_id, pollToken, scenarioId, scenarioSource);
    })
    .catch((err) => {
      state.aiRouteTaskId = null;
      renderAiRouteProgress({
        stage: "ai_pricing",
        stageTag: "失败",
        stageLabel: "AI报价处理失败",
        percent: 100,
        detail: err.message,
        hint: "请检查 Skill 规则输入、金蝶 BOM 数据或 AI 接口状态后重试。",
      }, true);
      setNodeText("#aiRouteStatusChip", "失败");
      document.getElementById("importStatus").textContent = `基准报价刷新失败：${err.message}`;
    });
}

function loadExcelScenario(payload) {
  const model = payload.model || {};
  const label = model.label || model.filename || `Excel鎶ヤ环_${Date.now()}`;
  const code = model.filename || label;
  const scenarioDescription = model.requested_volume_label
    ? `Excel报价 · ${model.requested_volume_label}`
    : "Excel 琛ㄦ牸瀵煎叆鎶ヤ环";
  const existing = state.scenarios.find((item) => item.code === code && String(item.id).startsWith("excel_"));
  const scenarioId = existing?.id || `excel_${Date.now()}`;
  if (!existing) {
    state.scenarios.push({ id: scenarioId, code, label, description: scenarioDescription });
  } else {
    existing.label = label;
    existing.description = scenarioDescription;
  }
  state.scenarioItems[scenarioId] = (payload.items || []).map((item) => calcQuoteItem(item, item.source_tag || "Excel瀵煎叆"));
  state.financeScenario = scenarioId;
  state.engineerScenario = scenarioId;
  state.lastExcelScenarioId = scenarioId;
  state.activeView = "finance";
  state.financeModule = "excel-quote";
  renderAll();
}

function renderAll() {
  renderTabs();
  renderFinanceModules();
  renderMeta();
  renderScenarioSelect();
  renderFinanceSummary();
  renderFinanceTable();
  renderComparisonChart();
  renderComparisonAnalysis();
  renderEngineerTable();
  renderPresetOptions();
  renderPreview();
  renderSingleBomPreview();
  renderIntegration();
  renderBomHeaderOptions();
  renderExcelQuoteExports(getExcelQuoteDownloadPayloads());
  const engineerScenario = state.scenarios.find((item) => item.id === state.engineerScenario);
  document.getElementById("engineerModelLabel").textContent = engineerScenario?.label || "-";
  document.getElementById("breakdownPanel").classList.toggle("hidden", !state.showBreakdown);
}

function invalidateSingleBomQuotePreview() {
  state.singleBomQuotePayload = null;
  applySingleBomQuotePreview(null);
}

async function requestSingleBomQuote() {
  const form = getSingleBomForm();
  if (!form.code || !form.name || !form.material) {
    throw new Error("请至少填写：物料编码、物料名称、材质");
  }
  state.financeModule = "single-bom";
  renderFinanceModules();
  const calcBtn = document.getElementById("singleBomCalcBtn");
  const originalText = calcBtn.textContent;
  calcBtn.disabled = true;
  calcBtn.textContent = "计算中...";
  document.getElementById("singleBomAiStatus").textContent = "计算中";
  document.getElementById("singleBomAiReason").textContent = "正在调用 skill 原生脚本和 AI 双路线计算";
  try {
    const payload = await quoteSingleBomItem(form, {
      label: "单物料试算",
      production_mode: form.production_mode,
      annual_volume: form.annual_volume,
    });
    if (payload.error) throw new Error(payload.message || payload.error);
    state.singleBomQuotePayload = payload;
    applySingleBomQuotePreview(payload);
    return payload;
  } finally {
    calcBtn.disabled = false;
    calcBtn.textContent = originalText;
  }
}

function applySelectedBom(bomNumber, label = "") {
  const normalizedBomNumber = String(bomNumber || "").trim();
  document.getElementById("importBomNumber").value = normalizedBomNumber;
  document.getElementById("selectedBomLabel").textContent = label || normalizedBomNumber || "-";
  document.getElementById("bomHeaderSelect").value = normalizedBomNumber;
  document.getElementById("financeBomHeaderSelect").value = normalizedBomNumber;
  updateFinanceBomSelectionSummary(normalizedBomNumber, label);
}

function prepareExcelQuoteSubmission(stageDetail, statusText, { preserveExports = false } = {}) {
  state.financeModule = "excel-quote";
  renderFinanceModules();
  const pollToken = nextExcelQuotePollToken();
  state.lastExcelQuotePayload = null;
  if (!preserveExports) {
    state.lastExcelQuotePayloads = [];
    renderExcelQuoteExports(null);
  }
  resetExcelQuoteProgress();
  renderExcelQuoteProgress({
    stage: "queued",
    stageTag: "已提交",
    stageLabel: "任务已提交",
    percent: 4,
    detail: stageDetail,
    hint: "正在创建报价任务，马上开始读取报价表数据",
  }, true);
  document.getElementById("excelQuoteProgressPanel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  document.getElementById("excelQuoteStatus").textContent = statusText;
  return pollToken;
}

function buildExcelQuoteRunLabel(options = {}) {
  if (options.productionMode !== "mass") return "样品/小批";
  const selected = Array.isArray(options.annualVolumes) ? options.annualVolumes.filter((value) => normalizeNumber(value) > 0) : [];
  if (selected.length) return selected.map((volume) => buildMassVolumeRequestLabel(volume)).join("；");
  if (normalizeNumber(options.annualVolume) > 0) return buildMassVolumeRequestLabel(options.annualVolume);
  return "量产";
}

function bindEvents() {
  document.getElementById("financeTab").onclick = () => {
    state.activeView = "finance";
    renderTabs();
  };
  document.getElementById("engineerTab").onclick = () => {
    state.activeView = "engineer";
    renderTabs();
  };
  document.querySelectorAll("[data-finance-module-target]").forEach((node) => {
    node.onclick = () => {
      state.financeModule = node.dataset.financeModuleTarget || "warehouse-recheck";
      renderFinanceModules();
      document.querySelector(`.finance-module-section[data-finance-module="${state.financeModule}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    };
  });
  document.getElementById("toggleBreakdownBtn").onclick = () => {
    state.showBreakdown = !state.showBreakdown;
    document.getElementById("breakdownPanel").classList.toggle("hidden", !state.showBreakdown);
    document.getElementById("toggleBreakdownBtn").textContent = state.showBreakdown ? "收起价格组成" : "查看价格组成";
  };
  document.getElementById("exportQuoteExcelBtn").onclick = () => {
    const items = getActiveItems();
    if (!items.length) {
      alert("当前没有可导出的报价结果");
      return;
    }
    const scenario = getActiveScenario();
    const fallbackName = `${scenario?.label || "报价结果"}.xlsx`;
    exportQuoteWorkbook(buildExportPayload())
      .then(({ blob, disposition }) => downloadBlob(blob, disposition, fallbackName))
      .catch((err) => alert(`导出报价结果失败：${err.message}`));
  };
  document.getElementById("downloadExcelPackageBtn").onclick = () => {
    const payloads = getExcelQuoteDownloadPayloads();
    if (!payloads.length) {
      alert("还没有可下载的 AI 报价结果");
      return;
    }
    if (payloads.length > 1) {
      const latestPayload = payloads[payloads.length - 1] || {};
      const fallbackLabelBase = latestPayload.model?.label || "多量产报价汇总包";
      const fallbackName = `${fallbackLabelBase}_多量产报价汇总包.zip`;
      exportQuotePackageBatch(payloads)
        .then(({ blob, disposition }) => downloadBlob(blob, disposition, fallbackName))
        .catch((err) => alert(`下载 AI 报价汇总包失败：${err.message}`));
      return;
    }
    const payload = payloads[0];
    const fallbackLabelBase = payload.model?.label || "报价汇总包";
    const fallbackVolume = buildExportVolumeLabel(payload.model || {});
    const fallbackName = `${fallbackVolume && !String(fallbackLabelBase).includes(fallbackVolume) ? `${fallbackLabelBase}_${fallbackVolume}` : fallbackLabelBase}.zip`;
    exportQuotePackage(payload)
      .then(({ blob, disposition }) => downloadBlob(blob, disposition, fallbackName))
      .catch((err) => alert(`下载 AI 报价汇总包失败：${err.message}`));
  };
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
  });
  document.getElementById("scenarioSelect").onchange = (event) => {
    state.financeScenario = event.target.value;
    state.engineerScenario = event.target.value;
    state.aiRouteTaskId = null;
    resetAiRouteProgress();
    loadScenarioBom(state.financeScenario);
  };
  document.getElementById("financeBomHeaderSelect").onchange = (event) => {
    const bomNumber = event.target.value;
    const selected = state.bomHeaders.find((item) => item.bom_number === bomNumber);
    syncFinanceScenarioFromKingdeeSelection(bomNumber, selected?.parent_name || selected?.bom_number || "-")
      .catch((err) => {
        document.getElementById("importStatus").textContent = `财务传统报价刷新失败：${err.message}`;
        alert(`刷新财务传统报价失败：${err.message}`);
      });
  };
  document.getElementById("financeBomHeaderSelect").addEventListener("focus", () => {
    if (state.bomHeadersStatus === "empty" || !(state.bomHeaders || []).length) {
      ensureFinanceBomHeadersLoaded(document.getElementById("financeBomSearchKeyword").value || "").catch(() => {});
    }
  });
  document.getElementById("financeSearchBomBtn").onclick = () => {
    const keyword = document.getElementById("financeBomSearchKeyword").value.trim();
    ensureFinanceBomHeadersLoaded(keyword, { force: true }).catch((err) => {
      alert(`搜索金蝶型号失败：${err.message}`);
    });
  };
  document.getElementById("financeBomSearchKeyword").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    document.getElementById("financeSearchBomBtn").click();
  });
  document.getElementById("financeBomSearchKeyword").addEventListener("input", (event) => {
    if (String(event.target.value || "").trim()) return;
    if ((state.bomHeaders || []).length && state.bomHeadersStatus === "ready") return;
    ensureFinanceBomHeadersLoaded("", { force: true }).catch(() => {});
  });
  document.getElementById("loadFinanceBomBtn").onclick = () => {
    const bomNumber = String(document.getElementById("financeBomHeaderSelect").value || state.selectedFinanceBomNumber || "").trim();
    if (!bomNumber) {
      updateFinanceBomSelectionSummary("");
      document.getElementById("importStatus").textContent = "未选中有效 BOM 编号";
      return;
    }
    const selected = state.bomHeaders.find((item) => item.bom_number === bomNumber);
    syncFinanceScenarioFromKingdeeSelection(bomNumber, selected?.parent_name || selected?.bom_number || bomNumber, { startAi: true })
      .catch((err) => alert(`开始报价测算失败：${err.message}`));
  };
  document.getElementById("searchBomBtn").onclick = () => {
    const keyword = document.getElementById("bomSearchKeyword").value.trim();
    document.getElementById("importStatus").textContent = "搜索中...";
    setBomHeadersState("loading");
    renderBomHeaderOptions();
    fetchBomHeaders(keyword)
      .then((payload) => {
        if (payload.error) {
          const isConfigMissing = payload.error === "KINGDEE_CONFIG_MISSING";
          const message = normalizeKingdeeBomHeaderErrorMessage(payload.error, payload.message || payload.error);
          setBomHeadersState(
            isConfigMissing ? "config_missing" : "upstream_error",
            message,
          );
          state.bomHeaders = [];
          renderBomHeaderOptions();
          document.getElementById("importStatus").textContent = state.bomHeadersMessage;
          return;
        }
        state.bomHeaders = payload.rows || [];
        setBomHeadersState(state.bomHeaders.length ? "ready" : "empty");
        renderBomHeaderOptions();
        document.getElementById("importStatus").textContent = state.bomHeaders.length
          ? `已找到 ${state.bomHeaders.length} 个型号`
          : "当前未查询到匹配型号";
      })
      .catch((err) => {
        setBomHeadersState("upstream_error", "金蝶接口异常，暂时无法加载型号");
        state.bomHeaders = [];
        renderBomHeaderOptions();
        document.getElementById("importStatus").textContent = state.bomHeadersMessage;
        alert(`搜索金蝶型号失败：${err.message}`);
      });
  };
  document.getElementById("bomHeaderSelect").onchange = (event) => {
    const bomNumber = event.target.value;
    const selected = state.bomHeaders.find((item) => item.bom_number === bomNumber);
    applySelectedBom(bomNumber, selected?.parent_name || selected?.bom_number || "-");
  };
  document.addEventListener("change", (event) => {
    if (event.target?.id !== "financeStatusFilter") return;
    state.financeStatusFilter = event.target.value || "all";
    renderFinanceTable();
  });
  document.getElementById("importBomBtn").onclick = () => {
    const bomNumber = document.getElementById("importBomNumber").value.trim();
    if (!bomNumber) {
      alert("请先输入金蝶 BOM 编号");
      return;
    }
    const oldText = document.getElementById("importStatus").textContent;
    document.getElementById("importStatus").textContent = "导入中...";
    syncBomFromKingdee(bomNumber)
      .then((payload) => {
        if (payload.error) throw new Error(payload.message || payload.error);
        const scenarioId = loadSyncedScenario(payload);
        state.activeView = "engineer";
        renderAll();
        document.getElementById("selectedBomLabel").textContent = payload.model?.label || bomNumber;
        document.getElementById("importStatus").textContent = `已导入 ${payload.model?.item_count || 0} 条，AI 报价计算中`;
        refreshScenarioAiRoute(scenarioId, payload.model || {}, "金蝶导入");
      })
      .catch((err) => {
        document.getElementById("importStatus").textContent = oldText;
        alert(`金蝶导入失败：${err.message}`);
      });
  };
  document.getElementById("createModelBtn").onclick = () => {
    createScenario(document.getElementById("modelCode").value, document.getElementById("modelName").value);
    state.activeView = "engineer";
    renderTabs();
  };
  document.getElementById("useFinanceModelBtn").onclick = () => {
    state.engineerScenario = state.financeScenario;
    renderAll();
  };
  document.getElementById("syncHintBtn").onclick = () => {
    state.activeView = "engineer";
    renderTabs();
    document.querySelector(".low-key-card").scrollIntoView({ behavior: "smooth", block: "start" });
  };
  document.getElementById("quoteExcelBtn").onclick = () => {
    const fileInput = document.getElementById("excelQuoteFile");
    const file = fileInput.files?.[0];
    const tableText = document.getElementById("excelQuotePasteText")?.value || "";
    const trimmedTableText = String(tableText || "").trim();
    const options = getExcelQuoteOptions();

    if (file && trimmedTableText) {
      alert("Excel 文件和粘贴数据不能同时存在，请只保留一种输入方式");
      return;
    }

    if (!file && !trimmedTableText) {
      renderExcelPasteRecognition(analyzePastedExcelTable(trimmedTableText));
      alert("请先选择一个 .xlsx 文件，或粘贴从 Excel 复制的表格数据");
      return;
    }

    if (!file) {
      const recognized = analyzePastedExcelTable(trimmedTableText);
      renderExcelPasteRecognition(recognized);
      if (!recognized.ok) {
        alert("请先选择一个 .xlsx 文件，或粘贴从 Excel 复制的表格数据");
        return;
      }
    }

    const modelLabel = document.getElementById("excelQuoteModelLabel").value;
    const runLabel = buildExcelQuoteRunLabel(options);
    document.getElementById("excelQuoteStatus").textContent = `报价处理中：${runLabel}`;
    submitExcelQuoteForVolumes({
      file,
      tableText: trimmedTableText,
      modelLabel,
      options,
    }).catch((err) => {
      document.getElementById("excelQuoteStatus").textContent = "报价失败";
      alert(`${file ? "Excel 报价" : "粘贴表格报价"}失败：${err.message}`);
    });
  };
  const runExcelPasteRecognition = () => {
    const tableText = document.getElementById("excelQuotePasteText")?.value || "";
    renderExcelPasteRecognition(analyzePastedExcelTable(tableText));
  };
  let excelPasteDetectTimer = 0;
  const fileInputNode = document.getElementById("excelQuoteFile");
  const pasteTextNode = document.getElementById("excelQuotePasteText");
  if (fileInputNode) {
    fileInputNode.addEventListener("change", () => {
      const hasFile = !!fileInputNode.files?.[0];
      if (!hasFile) return;
      if (pasteTextNode && String(pasteTextNode.value || "").trim()) {
        pasteTextNode.value = "";
        renderExcelPasteRecognition(null);
      }
    });
  }
  if (pasteTextNode) {
    pasteTextNode.addEventListener("input", () => {
      if (fileInputNode?.files?.length) {
        fileInputNode.value = "";
      }
      window.clearTimeout(excelPasteDetectTimer);
      excelPasteDetectTimer = window.setTimeout(runExcelPasteRecognition, 180);
    });
    pasteTextNode.addEventListener("paste", () => {
      if (fileInputNode?.files?.length) {
        fileInputNode.value = "";
      }
      window.clearTimeout(excelPasteDetectTimer);
      excelPasteDetectTimer = window.setTimeout(runExcelPasteRecognition, 30);
    });
  }
  renderExcelPasteRecognition(null);
  renderNameSpecBandConfig();
  document.getElementById("addNameSpecBandBtn").onclick = () => {
    state.nameSpecBands = state.nameSpecBands || [];
    state.nameSpecBands.push({ category: "", keywords: "", low: "", high: "", basis: "" });
    renderNameSpecBandConfig();
    setNameSpecBandConfigStatus("已新增一条空白区间，填写后点击“保存区间”生效。");
  };
  document.getElementById("reloadNameSpecBandBtn").onclick = () => loadNameSpecBandConfig(true);
  document.getElementById("saveNameSpecBandBtn").onclick = () => handleSaveNameSpecBandConfig();
  document.getElementById("useExcelScenarioBtn").onclick = () => {
    if (!state.lastExcelScenarioId || !state.scenarioItems[state.lastExcelScenarioId]?.length) {
      alert("还没有可查看的 Excel 报价结果");
      return;
    }
    state.financeScenario = state.lastExcelScenarioId;
    state.engineerScenario = state.lastExcelScenarioId;
    state.activeView = "finance";
    state.financeModule = "excel-quote";
    renderAll();
  };
  document.getElementById("presetSelect").onchange = (event) => {
    const idx = Number(event.target.value);
    if (Number.isNaN(idx)) return;
    const item = state.data?.bom_items?.[idx];
    if (!item) return;
    document.getElementById("code").value = item.code || "";
    document.getElementById("name").value = item.name || "";
    document.getElementById("material").value = item.material || "";
    document.getElementById("weight").value = item.weight_kg || 0;
    document.getElementById("qty").value = item.qty || 1;
    document.getElementById("process").value = item.process || "";
    document.getElementById("loss").value = 0.08;
    document.getElementById("ct").value = 0;
    document.getElementById("rate").value = 0;
    document.getElementById("extra").value = 0;
    renderPreview();
  };
  ["code", "name", "material", "weight", "loss", "process", "ct", "rate", "qty", "extra"].forEach((id) => {
    document.getElementById(id).addEventListener("input", renderPreview);
  });
  ["singleBomCode", "singleBomName", "singleBomMaterial", "singleBomWeight", "singleBomLoss", "singleBomProcess", "singleBomCt", "singleBomRate", "singleBomQty", "singleBomExtra", "singleBomAnnualVolume"].forEach((id) => {
    document.getElementById(id).addEventListener("input", invalidateSingleBomQuotePreview);
  });
  document.getElementById("singleBomProductionMode").addEventListener("change", () => {
    syncProductionModeUi("singleBomProductionMode", "singleBomAnnualVolumeField", "singleBomAnnualVolume", "singleBomProductionModeHint", {
      sample: "样品/小批：按当前材料、重量和工艺直接试算，不启用年产量。",
      mass: "量产：会把年产量传给 AI，并额外生成量产测算参考。",
    });
    invalidateSingleBomQuotePreview();
  });
  document.getElementById("excelQuoteProductionMode").addEventListener("change", () => {
    syncProductionModeUi("excelQuoteProductionMode", "excelQuoteAnnualVolumeField", "excelQuoteAnnualVolume", "excelQuoteProductionModeHint", {
      sample: "样品/小批：按当前参考价直接测算，不启用年产量。",
      mass: "量产：会额外生成批量测算结果，并把年产量传给 AI 作为量产参考。",
    });
  });
  syncProductionModeUi("singleBomProductionMode", "singleBomAnnualVolumeField", "singleBomAnnualVolume", "singleBomProductionModeHint", {
    sample: "样品/小批：按当前材料、重量和工艺直接试算，不启用年产量。",
    mass: "量产：会把年产量传给 AI，并额外生成量产测算参考。",
  });
  syncProductionModeUi("excelQuoteProductionMode", "excelQuoteAnnualVolumeField", "excelQuoteAnnualVolume", "excelQuoteProductionModeHint", {
    sample: "样品/小批：按当前参考价直接测算，不启用年产量。",
    mass: "量产：会额外生成批量测算结果，并把年产量传给 AI 作为量产参考。",
  });
  document.getElementById("calcBtn").onclick = () => {
    const form = getForm();
    if (!form.code || !form.name || !form.material) {
      alert("请至少填写：物料编码、物料名称、材质");
      return;
    }
    if (!state.engineerScenario) {
      alert("请先选择或新建一个型号");
      return;
    }
    state.scenarioItems[state.engineerScenario] = state.scenarioItems[state.engineerScenario] || [];
    state.scenarioItems[state.engineerScenario].push(calcQuoteItem(form, "新增 BOM"));
    state.financeScenario = state.engineerScenario;
    state.activeView = "finance";
    state.financeModule = "warehouse-recheck";
    renderAll();
  };
  document.getElementById("singleBomCalcBtn").onclick = async () => {
    try {
      await requestSingleBomQuote();
    } catch (err) {
      applySingleBomQuotePreview(null);
      document.getElementById("singleBomAiStatus").textContent = "失败";
      document.getElementById("singleBomAiReason").textContent = err.message;
      alert(`单物料试算失败：${err.message}`);
    }
  };
  document.getElementById("singleBomAddBtn").onclick = async () => {
    const form = getSingleBomForm();
    if (!form.code || !form.name || !form.material) {
      alert("请至少填写：物料编码、物料名称、材质");
      return;
    }
    if (!state.financeScenario) {
      alert("请先选择一个报价型号");
      return;
    }
    let payload = state.singleBomQuotePayload;
    const payloadItem = payload?.items?.[0];
    const sameItem = payloadItem && payloadItem.code === form.code && payloadItem.name === form.name;
    if (!sameItem) {
      try {
        payload = await requestSingleBomQuote();
      } catch (err) {
        alert(`加入当前报价型号失败：${err.message}`);
        return;
      }
    }
    state.scenarioItems[state.financeScenario] = state.scenarioItems[state.financeScenario] || [];
    const quotedItem = payload?.items?.[0] || form;
    state.scenarioItems[state.financeScenario].push(calcQuoteItem(quotedItem, quotedItem.source_tag || "单物料试算"));
    state.engineerScenario = state.financeScenario;
    state.activeView = "finance";
    state.financeModule = "single-bom";
    renderAll();
    document.querySelector(".finance-detail-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  document.getElementById("singleBomExportBtn").onclick = () => {
    const items = getActiveItems();
    if (!items.length) {
      alert("当前BOM还没有可导出的报价条目");
      return;
    }
    const scenario = getActiveScenario();
    const fallbackName = `${scenario?.label || "当前BOM"}_报价结果.xlsx`;
    exportQuoteWorkbook(buildExportPayload())
      .then(({ blob, disposition }) => downloadBlob(blob, disposition, fallbackName))
      .catch((err) => alert(`导出当前BOM失败：${err.message}`));
  };
  document.getElementById("singleBomResetBtn").onclick = () => {
    resetSingleBomForm();
    renderSingleBomPreview();
  };
  document.getElementById("resetBtn").onclick = () => {
    ["code", "name", "material", "weight", "process"].forEach((id) => { document.getElementById(id).value = ""; });
    document.getElementById("qty").value = 1;
    document.getElementById("loss").value = 0.08;
    document.getElementById("ct").value = 0;
    document.getElementById("rate").value = 0;
    document.getElementById("extra").value = 0;
    document.getElementById("presetSelect").value = "";
    renderPreview();
  };
}

(async function init() {
  state.data = await loadDemoData();
  state.scenarios = getScenarioList();
  state.financeScenario = state.scenarios[0]?.id || null;
  state.engineerScenario = state.financeScenario;
  state.scenarioItems[state.financeScenario] = (state.data?.bom_items || []).map((item) => calcQuoteItem(item, "本地预置BOM"));
  state.bomHeaders = [];
  setBomHeadersState("loading");
  bindEvents();
  simplifyFinanceHomeLayout();
  hydrateStaticLabels();
  renderAll();
  resetExcelQuoteProgress();
  resetAiRouteProgress();
  renderExcelQuoteExports(getExcelQuoteDownloadPayloads());
  await loadNameSpecBandConfig();
  document.getElementById("excelQuoteStatus").textContent = "等待上传 Excel";
  document.getElementById("importStatus").textContent = "正在加载金蝶型号...";
  loadFinanceBomHeaders("")
    .catch((err) => {
      state.bomHeaders = [];
      state.bomHeadersHasMore = false;
      setBomHeadersState("upstream_error", "金蝶接口异常，暂时无法加载型号");
      renderBomHeaderOptions();
      document.getElementById("importStatus").textContent = `型号列表加载失败：${err.message}`;
    });
})();
















