from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP_WEB_ROOT = ROOT / "app_web"
for candidate in (ROOT, APP_WEB_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app_web.backend.services.finance_skill_quote_service import FinanceSkillQuoteService


class FinanceMotorWeightRuleTests(unittest.TestCase):
    def test_piece_pricing_motor_standard_part_with_estimated_weight_is_not_forced_into_weight_review(self):
        item = {
            "name": "轴承",
            "spec": "BS6206-2Z/C3",
            "material": "",
            "process": "",
            "finance_route_unit_price": 16.8,
            "ai_route_unit_price": 17.1,
            "ai_estimated_weight_kg": 0.35,
            "ai_route_status": "AI报价",
        }

        self.assertEqual(FinanceSkillQuoteService._item_status(item), "双路线可比")

    def test_rotor_baffle_has_motor_specific_weight_band(self):
        item = {
            "name": "转子挡板",
            "spec": "内外径45×117mm",
            "material": "A356",
            "process": "",
        }

        band = FinanceSkillQuoteService._resolve_name_spec_weight_band(item)

        self.assertTrue(band)
        self.assertEqual(band.get("category"), "电机转子挡板")
        self.assertGreater(float(band.get("default", 0)), 0)


if __name__ == "__main__":
    unittest.main()
