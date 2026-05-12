from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "app_web" / "static" / "finance_demo" / "index.html"
TEMPLATE_HTML = ROOT / "app_web" / "templates" / "finance_demo.html"


class FinanceDemoSimplifiedHomeTests(unittest.TestCase):
    def test_excel_quote_entry_is_promoted_before_engineer_workspace(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn('id="excelQuoteFile"', html)
        self.assertIn('<section id="engineerView"', html)
        self.assertLess(
            html.index('id="excelQuoteFile"'),
            html.index('<section id="engineerView"'),
            "Excel 报价入口应提升到财务首页，而不是继续留在工程区之后",
        )

    def test_template_applies_finance_home_simplification_rules(self):
        html = TEMPLATE_HTML.read_text(encoding="utf-8")

        self.assertIn(".finance-demo-page #engineerView", html)
        self.assertIn(".finance-demo-page .finance-insight-stack", html)
        self.assertIn(".finance-demo-page .hero-note", html)
        self.assertIn("财务报价 - MESAPP", html)

    def test_template_expands_layout_and_strengthens_modules(self):
        html = TEMPLATE_HTML.read_text(encoding="utf-8")

        self.assertIn("width: min(1480px, calc(100vw - 28px));", html)
        self.assertIn(".finance-demo-page .finance-home-upload", html)
        self.assertIn(".finance-demo-page .finance-top", html)
        self.assertIn(".finance-demo-page .finance-detail-card", html)

    def test_template_renders_four_finance_cards_in_one_row(self):
        html = TEMPLATE_HTML.read_text(encoding="utf-8")

        self.assertIn(".finance-demo-page .finance-module-grid {", html)
        self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr));", html)

    def test_template_keeps_finance_bom_selector_visible(self):
        html = TEMPLATE_HTML.read_text(encoding="utf-8")

        self.assertNotIn('label[for="financeBomHeaderSelect"]', html)
        self.assertNotIn(".finance-demo-page #loadFinanceBomBtn {\n        display: none !important;", html)
        self.assertNotIn(".finance-demo-page .finance-top .toolbar .field.compact:nth-of-type(2)", html)

    def test_template_keeps_finance_detail_table_readable_without_overwide_canvas(self):
        html = TEMPLATE_HTML.read_text(encoding="utf-8")

        self.assertIn(".finance-demo-page .finance-detail-card", html)
        self.assertIn("max-width: min(1420px, 100%);", html)
        self.assertIn("margin-inline: auto;", html)
        self.assertIn("overflow-x: auto;", html)
        self.assertIn("width: max-content;", html)
        self.assertIn("table-layout: auto;", html)

    def test_index_includes_single_bom_calculator_module(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn('class="card single-bom-card finance-module-section"', html)
        self.assertIn('id="singleBomCode"', html)
        self.assertIn('id="singleBomCalcBtn"', html)
        self.assertIn('id="singleBomAddBtn"', html)
        self.assertIn('id="singleBomUnitCost"', html)

    def test_index_includes_name_spec_band_config_entry_card_as_fourth_tile(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn('data-finance-module-target="band-config"', html)
        self.assertIn('data-finance-module="band-config"', html)
        self.assertIn("名称型物料价格区间配置", html)
        self.assertIn("统一维护名称/规格命中的价格区间规则", html)
        self.assertLess(
            html.index('data-finance-module-target="excel-quote"'),
            html.index('data-finance-module-target="band-config"'),
            "名称型物料价格区间配置应作为第 4 个新卡片出现在 Excel 报价入口之后",
        )

    def test_app_js_overrides_core_home_labels_to_fix_visible_garbling(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")

        self.assertIn("上传 Excel 并生成报价", html)
        self.assertIn("BOM明细与异常清单", html)
        self.assertIn("首页只保留上传、总价对比、异常摘要和下载入口。", html)

    def test_app_js_supports_single_bom_preview_and_actions(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function getSingleBomForm()", html)
        self.assertIn("function renderSingleBomPreview()", html)
        self.assertIn('document.getElementById("singleBomCalcBtn")', html)
        self.assertIn('document.getElementById("singleBomAddBtn")', html)

    def test_app_js_explains_kingdee_config_missing_state(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")

        self.assertIn("金蝶未配置完成，暂时无法加载型号", html)
        self.assertIn("KINGDEE_CONFIG_MISSING", html)

    def test_app_js_explains_kingdee_upstream_error_state(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")

        self.assertIn("KINGDEE_UPSTREAM_ERROR", html)
        self.assertIn("金蝶接口登录失败", html)
        self.assertIn("签名失败", html)
        self.assertIn("当前尝试登录的数据中心无法获取到", html)


    def test_finance_home_includes_ai_route_progress_panel(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn('id="aiRouteProgressPanel"', html)
        self.assertIn('id="aiRouteProgressFill"', html)
        self.assertIn('id="aiRouteProgressHint"', html)

    def test_app_js_polls_ai_route_quote_tasks(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function renderAiRouteProgress(", html)
        self.assertIn("function pollAiRouteTask(", html)
        self.assertIn('apiFetchJson(`/api/quote/ai-route/tasks/${encodeURIComponent(taskId)}`', html)
        self.assertIn('apiFetchJson("/api/quote/ai-route"', html)

    def test_finance_demo_bp_exposes_ai_route_task_endpoints(self):
        html = (ROOT / "app_web" / "finance_demo.py").read_text(encoding="utf-8")

        self.assertIn('@finance_demo_bp.route("/api/quote/ai-route", methods=["POST"])', html)
        self.assertIn('@finance_demo_bp.route("/api/quote/ai-route/tasks/<task_id>", methods=["GET"])', html)

    def test_demo_application_ai_route_supports_progress_callback(self):
        html = (ROOT / "app_web" / "backend" / "server.py").read_text(encoding="utf-8")

        self.assertIn("def _enrich_quote_payload(", html)
        self.assertIn("progress_callback=None", html)
        self.assertIn("progress_callback=progress_callback", html)

    def test_finance_demo_ai_route_progress_supports_waiting_heartbeat(self):
        html = (ROOT / "app_web" / "finance_demo.py").read_text(encoding="utf-8")

        self.assertIn("def _build_ai_route_waiting_progress(", html)
        self.assertIn('"waiting_first_result"', html)
        self.assertIn('"elapsed_seconds"', html)

    def test_app_js_renders_ai_route_waiting_state(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")

        self.assertIn("waiting_first_result", html)
        self.assertIn("已等待", html)
        self.assertIn('classList.toggle("is-waiting"', html)

    def test_ai_route_service_uses_longer_pricing_timeout_and_retry_defaults(self):
        html = (ROOT / "app_web" / "backend" / "services" / "ai_route_quote_service.py").read_text(encoding="utf-8")

        self.assertIn('PRICING_QWEN_TIMEOUT', html)
        self.assertIn('90', html)
        self.assertIn('PRICING_QWEN_TIMEOUT_RETRY', html)

    def test_app_js_mentions_traditional_and_ai_quote_outputs(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")

        self.assertIn("传统报价", html)
        self.assertIn("AI报价", html)
        self.assertIn("在线价格查询", html)
        self.assertIn("规则报价计算", html)

    def test_single_bom_ui_mentions_annual_mass_production_and_dual_quote(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")
        index_html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("年产量", html)
        self.assertIn("production_mode", html)
        self.assertIn("annual_volume", html)
        self.assertIn("singleBomAnnualVolume", index_html)
        self.assertIn("套/年", index_html)

    def test_excel_quote_ui_exposes_mass_production_controls(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")
        index_html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("excelQuoteProductionMode", index_html)
        self.assertIn("excelQuoteAnnualVolume", index_html)
        self.assertIn('formData.append("production_mode"', html)
        self.assertIn('formData.append("annual_volume"', html)

    def test_mass_production_ui_exposes_detailed_volume_tier_presets_and_manual_input(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")
        index_html = INDEX_HTML.read_text(encoding="utf-8")

        for value in ("300", "1000", "3000", "5000", "8000", "10000", "20000", "50000", "100000"):
            self.assertIn(f'data-volume="{value}"', index_html)
        self.assertIn("手动输入", index_html)
        self.assertIn("volume-tier-chip", index_html)
        self.assertIn("function bindVolumeTierPresets(", html)
        self.assertIn("function updateVolumeTierPresetState(", html)
        self.assertIn("function getVolumeTierPresetMeta(", html)
        self.assertIn("function formatMassAnnualVolumeLabel(", html)
        self.assertIn("材料约", html)
        self.assertIn("工艺约", html)
        self.assertIn("手动输入年产量", html)
        self.assertIn("基准说明（${massVolumeLabel}）", html)

    def test_mass_production_ui_mentions_tooling_vs_sample_breakdown(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function resolveFinanceApiBase(", html)
        self.assertIn("function apiFetchJson(", html)
        self.assertIn("当前页面未连接到 finance_demo 报价接口", html)
        self.assertIn("function buildMassToolingReference(", html)
        self.assertIn("function buildMassToolingTableCell(", html)
        self.assertIn("function buildToolingMarketReference(", html)
        self.assertIn("function buildToolingMarketVarianceLabel(", html)
        self.assertIn("function renderToolingMarketVarianceBadge(", html)
        self.assertIn("function buildToolingMarketCompactMeta(", html)
        self.assertIn("样品机加工单价", html)
        self.assertIn("量产开模单价", html)
        self.assertIn("开模费", html)
        self.assertIn("开模收益平衡点", html)
        self.assertIn("行业公开参考", html)
        self.assertIn("工艺类型", html)
        self.assertIn("来源简称", html)
        self.assertIn("公开区间", html)
        self.assertIn("行业区间判断", html)
        self.assertIn("RapidDirect", html)
        self.assertIn("Xometry", html)
        self.assertIn("tooling-market-badge", html)
        self.assertIn("is-low", html)
        self.assertIn("is-normal", html)
        self.assertIn("is-high", html)
        self.assertIn("注：公开网页区间仅作行业参考", html)
        self.assertIn("样品/开模对比", html)
        self.assertIn("head-tooling-compare", html)
        self.assertIn("cell-tooling-compare", html)

    def test_single_bom_ui_calls_backend_dual_quote_api(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")
        index_html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn('apiFetchJson("/api/quote/single-bom"', html)
        self.assertIn("singleBomFinanceUnitCost", index_html)
        self.assertIn("singleBomAiUnitCost", index_html)
        self.assertIn("singleBomAiReason", index_html)

    def test_finance_table_renders_ai_reason_and_explicit_failure_labels(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")

        self.assertIn("financeRouteSource", html)
        self.assertIn("aiRouteReasoning", html)
        self.assertIn("缺重量", html)
        self.assertIn("缺材质", html)
        self.assertIn("模型超时", html)
        self.assertIn("AI未配置", html)


    def test_app_js_preserves_and_validates_selected_kingdee_bom(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")

        self.assertIn("selectedFinanceBomNumber", html)
        self.assertIn("function updateFinanceBomSelectionSummary(", html)
        self.assertIn("financeBomSelectionValue", html)
        self.assertIn("financeBomSelectionHint", html)
        self.assertIn("未选中有效 BOM 编号", html)

    def test_app_js_sanitizes_https_connection_pool_reasoning(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")

        self.assertIn("HTTPSConnectionPool", html)
        self.assertIn("sanitizeAiReasonText", html)

    def test_app_js_retries_excel_task_polling_before_marking_failure(self):
        html = (ROOT / "app_web" / "static" / "finance_demo" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function pollExcelQuoteTask(taskId, pollToken, failureCount = 0)", html)
        self.assertIn("连接波动，正在重试报价任务状态", html)
        self.assertIn("window.setTimeout(() => pollExcelQuoteTask(taskId, pollToken, nextFailureCount), 1500)", html)

if __name__ == "__main__":
    unittest.main()
