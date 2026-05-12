from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP_WEB_ROOT = ROOT / "app_web"
for candidate in (ROOT, APP_WEB_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app_web.backend.services.finance_skill_quote_service import FinanceSkillQuoteService

SERVICE_FILE = ROOT / "app_web" / "backend" / "services" / "finance_skill_quote_service.py"


class FinanceSkillQuoteServiceContractTests(unittest.TestCase):
    def test_finance_skill_quote_service_file_exists(self):
        self.assertTrue(
            SERVICE_FILE.exists(),
            "统一 skill 报价服务文件还不存在，说明 Excel 与场景 AI 还没有真正收口到同一条主引擎",
        )

    def test_finance_skill_quote_service_mentions_expected_stage_names(self):
        text = SERVICE_FILE.read_text(encoding="utf-8")

        self.assertIn("market_pricing", text)
        self.assertIn("rule_pricing", text)
        self.assertIn("ai_supplement", text)
        self.assertIn("finalizing", text)

    def test_finance_skill_quote_service_mentions_dual_quote_fields(self):
        text = SERVICE_FILE.read_text(encoding="utf-8")

        self.assertIn("finance_route_unit_price", text)
        self.assertIn("finance_route_source", text)
        self.assertIn("ai_route_unit_price", text)
        self.assertIn("route_gap_unit_price", text)

    def test_finance_skill_quote_service_mentions_mass_production_fields(self):
        text = SERVICE_FILE.read_text(encoding="utf-8")

        self.assertIn("production_mode", text)
        self.assertIn("annual_volume", text)
        self.assertIn("model_volume_pricing.py", text)

    def test_describe_volume_tier_label_uses_detailed_mass_breakpoints(self):
        self.assertEqual("<=300", FinanceSkillQuoteService._describe_volume_tier_label(300))
        self.assertEqual("301-1000", FinanceSkillQuoteService._describe_volume_tier_label(1000))
        self.assertEqual("1001-3000", FinanceSkillQuoteService._describe_volume_tier_label(3000))
        self.assertEqual("3001-5000", FinanceSkillQuoteService._describe_volume_tier_label(5000))
        self.assertEqual("5001-8000", FinanceSkillQuoteService._describe_volume_tier_label(8000))
        self.assertEqual("8001-10000", FinanceSkillQuoteService._describe_volume_tier_label(10000))

    def test_finance_skill_quote_service_mentions_explicit_ai_failure_reasons(self):
        text = SERVICE_FILE.read_text(encoding="utf-8")

        self.assertIn("缺重量", text)
        self.assertIn("缺材质", text)
        self.assertIn("模型超时", text)
        self.assertIn("AI未配置", text)


    def test_finance_skill_quote_service_mentions_https_connection_timeout_keywords(self):
        text = SERVICE_FILE.read_text(encoding="utf-8")

        self.assertIn("httpsconnectionpool", text.lower())

    def test_finance_skill_quote_service_surfaces_script_stderr_details(self):
        text = SERVICE_FILE.read_text(encoding="utf-8")

        self.assertIn("CalledProcessError", text)
        self.assertIn("stderr", text)
        self.assertIn("stdout", text)
        self.assertIn("script_name", text)

    def test_script_first_fallback_does_not_lock_bearing_to_rule_price_when_below_name_spec_band(self):
        fallback = FinanceSkillQuoteService._script_first_ai_fallback({
            "name": "轴承",
            "spec": "6309-2Z/AEM3/C3GJN",
            "material": "轴承钢 (高碳铬钢)",
            "process": "冷镦成型、车削加工、热处理、精密磨削、清洗及装配",
            "name_spec_price_band": {"category": "轴承", "low": 20.0, "high": 80.0, "basis": "电机常用轴承单件区间"},
            "ai_skill_context": {
                "rule_unit_price": 0.8,
                "material_cost": 0.0,
                "process_cost": 0.8,
                "process_rule": "冷镦成型、车削加工、热处理、精密磨削、清洗及装配",
                "process_unit_label": "0.80 元/件",
            },
        })

        self.assertIsNone(
            fallback,
            "像轴承这类有明确名称规格价格带的件价物料，不应被明显异常的低 script 规则价直接锁定为 AI 报价",
        )

    def test_large_bearing_with_special_suffix_gets_higher_name_spec_price_band(self):
        band = FinanceSkillQuoteService._resolve_name_spec_price_band({
            "name": "轴承",
            "spec": "6309-2Z/AEM3/C3GJN",
            "material": "轴承钢 (高碳铬钢)",
            "weight_kg": 0.36,
        })

        self.assertEqual(band.get("category"), "轴承")
        self.assertGreaterEqual(
            float(band.get("low") or 0),
            120.0,
            "6309 这类大规格且带特殊后缀的电机轴承不应继续沿用 20-80 元的通用低价带",
        )

    def test_large_bearing_price_below_band_is_anchored_upward(self):
        item = {
            "name": "轴承",
            "spec": "6309-2Z/AEM3/C3GJN",
            "material": "轴承钢 (高碳铬钢)",
            "weight_kg": 0.36,
        }
        item["name_spec_price_band"] = FinanceSkillQuoteService._resolve_name_spec_price_band(item)

        price, reasoning = FinanceSkillQuoteService._apply_name_spec_price_band(item, 28.5, "")

        self.assertGreaterEqual(price, 140.0)
        self.assertIn("轴承", reasoning)
        self.assertIn("规格", reasoning)

    def test_build_skill_input_reference_text_includes_effective_process_material_and_weight(self):
        text = FinanceSkillQuoteService._build_skill_input_reference_text({
            "skills_input_process": "硅钢片冲压与叠压固化",
            "skills_input_material": "35W300",
            "skills_input_weight_kg": 7.37,
            "skills_input_process_source": "AI高置信工艺覆盖原始工艺",
        })

        self.assertIn("skills实际采用输入", text)
        self.assertIn("工艺=硅钢片冲压与叠压固化", text)
        self.assertIn("材质=35W300", text)
        self.assertIn("重量=7.3700kg", text)
        self.assertIn("AI高置信工艺覆盖原始工艺", text)

    def test_normalize_material_for_skills_handles_verbose_alloy_and_casting_text(self):
        self.assertEqual(FinanceSkillQuoteService._normalize_material_for_skills("20CrMnTi 合金结构钢"), "20CrMnTi")
        self.assertEqual(FinanceSkillQuoteService._normalize_material_for_skills("压铸铝合金 (如 ADC12)"), "ADC12")
        self.assertEqual(FinanceSkillQuoteService._normalize_material_for_skills("球墨铸铁 (QT450-10)"), "QT450-10")

    def test_end_cover_prefers_name_spec_formula_when_script_price_far_below_band(self):
        self.assertTrue(FinanceSkillQuoteService._should_prefer_name_spec_formula({
            "name_spec_price_band": {"category": "电机精密结构端盖", "low": 159.0, "high": 235.0}
        }))

    def test_precision_shaft_prefers_formula_when_name_spec_band_is_hit(self):
        self.assertTrue(FinanceSkillQuoteService._should_prefer_name_spec_formula({
            "name_spec_price_band": {"category": "高精轴类机加工件", "low": 420.0, "high": 920.0}
        }))

    def test_large_harness_prefers_formula_when_name_spec_band_is_hit(self):
        self.assertTrue(FinanceSkillQuoteService._should_prefer_name_spec_formula({
            "name_spec_price_band": {"category": "电机大线径线束", "low": 90.0, "high": 260.0}
        }))

    def test_motor_shell_prefers_formula_when_name_spec_band_is_hit(self):
        self.assertTrue(FinanceSkillQuoteService._should_prefer_name_spec_formula({
            "name_spec_price_band": {"category": "电机壳体盖板类结构件", "low": 110.0, "high": 260.0}
        }))

    def test_derive_mass_volume_prices_falls_back_to_annual_volume_discount_when_ratios_missing(self):
        prices = FinanceSkillQuoteService._derive_mass_volume_prices(
            baseline_unit=100.0,
            annual_volume=3000,
            conservative_ratio=0.0,
            aggressive_ratio=0.0,
            manual_surcharge_unit=0.0,
        )

        self.assertEqual(prices["baseline_unit_price"], 100.0)
        self.assertGreater(prices["conservative_unit_price"], 0.0)
        self.assertGreater(prices["aggressive_unit_price"], 0.0)
        self.assertLess(prices["conservative_unit_price"], 100.0)
        self.assertLess(prices["aggressive_unit_price"], prices["conservative_unit_price"])
        self.assertEqual(prices["conservative_discount"], 0.03)
        self.assertEqual(prices["aggressive_discount"], 0.06)

    def test_mass_tooling_discount_fallback_uses_split_breakpoints_for_300_1000_3000_5000(self):
        self.assertEqual(FinanceSkillQuoteService._mass_tooling_discount_fallback(300), (0.01, 0.03))
        self.assertEqual(FinanceSkillQuoteService._mass_tooling_discount_fallback(1000), (0.02, 0.04))
        self.assertEqual(FinanceSkillQuoteService._mass_tooling_discount_fallback(3000), (0.03, 0.06))
        self.assertEqual(FinanceSkillQuoteService._mass_tooling_discount_fallback(5000), (0.04, 0.08))

    def test_derive_mass_volume_prices_uses_different_discounts_for_300_1000_3000_5000(self):
        prices_300 = FinanceSkillQuoteService._derive_mass_volume_prices(baseline_unit=100.0, annual_volume=300)
        prices_1000 = FinanceSkillQuoteService._derive_mass_volume_prices(baseline_unit=100.0, annual_volume=1000)
        prices_3000 = FinanceSkillQuoteService._derive_mass_volume_prices(baseline_unit=100.0, annual_volume=3000)
        prices_5000 = FinanceSkillQuoteService._derive_mass_volume_prices(baseline_unit=100.0, annual_volume=5000)

        self.assertEqual(prices_300["conservative_unit_price"], 99.0)
        self.assertEqual(prices_1000["conservative_unit_price"], 98.0)
        self.assertEqual(prices_3000["conservative_unit_price"], 97.0)
        self.assertEqual(prices_5000["conservative_unit_price"], 96.0)
        self.assertEqual(prices_300["aggressive_unit_price"], 97.0)
        self.assertEqual(prices_1000["aggressive_unit_price"], 96.0)
        self.assertEqual(prices_3000["aggressive_unit_price"], 94.0)
        self.assertEqual(prices_5000["aggressive_unit_price"], 92.0)

    def test_ensure_mass_volume_prices_fills_zero_conservative_and_aggressive_values(self):
        item = {
            "production_mode": "mass",
            "annual_volume": 5000,
            "ai_route_unit_price": 28.66,
            "volume_baseline_unit_price": 28.66,
            "volume_conservative_unit_price": 0,
            "volume_aggressive_unit_price": 0,
            "volume_pricing_summary": "量产口径（5000套/年，3001-5000档）：基准 28.66 / 保守 0.00 / 激进 0.00 元",
        }
        FinanceSkillQuoteService._ensure_mass_volume_prices(item, qty=1, manual_surcharge_unit=0)

        self.assertGreater(item["volume_conservative_unit_price"], 0)
        self.assertGreater(item["volume_aggressive_unit_price"], 0)
        self.assertIn("保守 27.51", item["volume_pricing_summary"])
        self.assertIn("激进 26.37", item["volume_pricing_summary"])

    def test_reproject_mass_payload_for_volume_keeps_same_ai_baseline_and_only_changes_volume_tier(self):
        service = FinanceSkillQuoteService(config=None, kingdee_service=None, ai_route_service=None)
        payload = {
            "model": {"label": "川崎高速油泵", "production_mode": "mass", "annual_volume": 3000},
            "summary": {},
            "items": [
                {
                    "code": "T45110282.A0",
                    "name": "电机轴",
                    "qty": 1,
                    "production_mode": "mass",
                    "annual_volume": 3000,
                    "ai_route_unit_price": 154.2054,
                    "ai_route_reasoning": "量产开模口径（3000套/年）：当前单件按开模后工艺计 154.21 元。",
                    "ai_route_source": "mass-tooling-route",
                    "sample_machining_unit_price": 649.64,
                    "mass_tooling_unit_price": 154.2054,
                    "tooling_cost": 57982.0,
                    "mass_break_even_volume": 118,
                    "mass_process_route": "锻造模+精加工治具",
                    "volume_baseline_unit_price": 154.2054,
                    "volume_conservative_unit_price": 149.5792,
                    "volume_aggressive_unit_price": 144.9531,
                    "volume_pricing_summary": "量产口径（3000套/年，1001-3000档）：基准 154.21 / 保守 149.58 / 激进 144.95 元",
                }
            ],
        }

        reprojected = service.reproject_mass_payload_for_volume(payload, annual_volume=1000)
        item = reprojected["items"][0]
        reprojected_3000 = service.reproject_mass_payload_for_volume(payload, annual_volume=3000)
        item_3000 = reprojected_3000["items"][0]

        self.assertEqual(reprojected["model"]["annual_volume"], 1000)
        self.assertEqual(item["annual_volume"], 1000)
        self.assertEqual(item["ai_route_unit_price"], 154.2054)
        self.assertEqual(item["volume_baseline_unit_price"], 154.2054)
        self.assertIn("301-1000档", item["volume_pricing_summary"])
        self.assertIn("量产档位已沿用同一基准AI结果重算", item["ai_route_reasoning"])
        self.assertGreater(item["volume_conservative_unit_price"], item["volume_aggressive_unit_price"])
        self.assertNotEqual(item["volume_conservative_unit_price"], 149.5792)
        self.assertNotEqual(item["volume_aggressive_unit_price"], 144.9531)
        self.assertGreater(item["volume_conservative_unit_price"], item_3000["volume_conservative_unit_price"])

    def test_build_summary_uses_volume_baseline_total_as_ai_total_in_mass_mode(self):
        summary = FinanceSkillQuoteService._build_summary([
            {
                "qty": 1,
                "production_mode": "mass",
                "ai_route_unit_price": 154.2054,
                "volume_baseline_unit_price": 154.2054,
                "volume_conservative_unit_price": 149.5792,
                "volume_aggressive_unit_price": 144.9531,
                "finance_route_unit_price": 100,
            },
            {
                "qty": 1,
                "production_mode": "mass",
                "ai_route_unit_price": 260.216,
                "volume_baseline_unit_price": 260.216,
                "volume_conservative_unit_price": 257.83,
                "volume_aggressive_unit_price": 255.45,
                "finance_route_unit_price": 120,
            },
        ])

        self.assertEqual(summary["ai_total"], summary["volume_baseline_total"])
        self.assertEqual(summary["route_gap_total"], summary["ai_total"] - summary["finance_total"])

    def test_build_summary_accumulates_mass_volume_totals(self):
        summary = FinanceSkillQuoteService._build_summary([
            {
                "qty": 2,
                "weight_kg": 3,
                "finance_route_unit_price": 10,
                "ai_route_unit_price": 20,
                "selected_quote_unit_price": 20,
                "volume_baseline_unit_price": 18,
                "volume_conservative_unit_price": 17,
                "volume_aggressive_unit_price": 16,
            },
            {
                "qty": 1,
                "weight_kg": 4,
                "finance_route_unit_price": 5,
                "ai_route_unit_price": 9,
                "selected_quote_unit_price": 9,
                "volume_baseline_unit_price": 8,
                "volume_conservative_unit_price": 7.5,
                "volume_aggressive_unit_price": 7,
            },
        ])

        self.assertEqual(summary["volume_baseline_total"], 44.0)
        self.assertEqual(summary["volume_conservative_total"], 41.5)
        self.assertEqual(summary["volume_aggressive_total"], 39.0)

if __name__ == "__main__":
    unittest.main()
