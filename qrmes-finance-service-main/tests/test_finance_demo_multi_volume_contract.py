from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "app_web" / "static" / "finance_demo" / "app.js"
INDEX_HTML = ROOT / "app_web" / "static" / "finance_demo" / "index.html"


class FinanceDemoMultiVolumeContractTests(unittest.TestCase):
    def test_index_html_mentions_multi_volume_selection_for_excel_quote(self):
        text = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn("excelQuoteVolumeMultiField", text)
        self.assertIn("excelQuoteVolumeMultiSummary", text)
        self.assertIn("data-multi-volume", text)
        self.assertIn("300", text)
        self.assertIn("1000", text)
        self.assertIn("3000", text)
        self.assertIn("5000", text)
        self.assertIn("年产量（可多选）", text)

    def test_app_js_mentions_multi_volume_selection_helpers_and_distinguishes_300_1000(self):
        text = APP_JS.read_text(encoding="utf-8")
        self.assertIn("getExcelQuoteSelectedAnnualVolumes", text)
        self.assertIn("buildMassVolumeRequestLabel", text)
        self.assertIn("折扣档位", text)
        self.assertIn("显示档位", text)
        self.assertIn("submitExcelQuoteForVolumes", text)
        self.assertIn("reprojectMassQuotePayload", text)
        self.assertIn("/api/quote/reproject-volume", text)
        self.assertIn("refreshProductionModeHint", text)
        self.assertIn("syncExcelQuoteAnnualVolumeDisplay", text)
        self.assertIn('selected.join(", ")', text)

    def test_app_js_reprojects_and_exports_via_resolved_finance_api_base(self):
        text = APP_JS.read_text(encoding="utf-8")
        self.assertIn("function buildFinanceApiTargets(", text)
        self.assertIn(":9003", text)
        self.assertNotIn('fetch("/api/quote/reproject-volume"', text)
        self.assertNotIn('fetch("/api/quote/export-package-batch"', text)
        self.assertNotIn('fetch("/api/quote/export-package"', text)


if __name__ == "__main__":
    unittest.main()
