from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FINANCE_DEMO = ROOT / "app_web" / "finance_demo.py"
EXCEL_SERVICE = ROOT / "app_web" / "backend" / "services" / "excel_quote_service.py"


class FinanceDemoSkillQuoteRouteTests(unittest.TestCase):
    def test_finance_demo_ai_route_uses_unified_skill_service(self):
        text = FINANCE_DEMO.read_text(encoding="utf-8")

        self.assertIn("FinanceSkillQuoteService", text)
        self.assertIn("get_finance_skill_quote_service", text)
        self.assertIn("market_pricing", text)
        self.assertIn("rule_pricing", text)

    def test_excel_quote_service_uses_unified_skill_service(self):
        text = EXCEL_SERVICE.read_text(encoding="utf-8")

        self.assertIn("FinanceSkillQuoteService", text)
        self.assertIn("skill_quote_service", text)
        self.assertIn("quote_items(", text)

    def test_excel_quote_service_mentions_clear_invalid_workbook_message(self):
        text = EXCEL_SERVICE.read_text(encoding="utf-8")

        self.assertIn("BadZipFile", text)
        self.assertIn(".xlsx", text)
        self.assertIn("不是有效的 Excel 工作簿", text)

    def test_finance_demo_export_package_mentions_skill_outputs(self):
        text = FINANCE_DEMO.read_text(encoding="utf-8")
        excel_text = EXCEL_SERVICE.read_text(encoding="utf-8")

        self.assertIn("/api/quote/export-package", text)
        self.assertIn("/api/quote/export-package-batch", text)
        self.assertIn("/api/quote/reproject-volume", text)
        self.assertIn("export_quote_package", text)
        self.assertIn("export_quote_package_batch", text)
        self.assertIn("reproject_mass_payload_for_volume", excel_text + text)
        self.assertIn("skill_outputs", excel_text)
        self.assertIn("export_quote_package", excel_text)

    def test_finance_demo_mentions_single_bom_quote_route(self):
        text = FINANCE_DEMO.read_text(encoding="utf-8")

        self.assertIn("/api/quote/single-bom", text)
        self.assertIn("annual_volume", text)
        self.assertIn("production_mode", text)

    def test_finance_demo_export_filename_uses_timestamp_project_and_mass_flag(self):
        text = FINANCE_DEMO.read_text(encoding="utf-8")

        self.assertIn("def _build_quote_download_name", text)
        self.assertIn('suffix="报价清单"', text)
        self.assertIn('suffix="报价汇总包"', text)
        self.assertIn('return "量产" if mode in {"mass", "volume", "量产"} else "非量产"', text)
        self.assertIn('if normalized in {"粘贴表格报价", "报价结果", "报价汇总包"}', text)
        self.assertIn('requested_annual_volume', text)
        self.assertIn('annual_volume', text)
        self.assertIn('套年', text)


if __name__ == "__main__":
    unittest.main()
