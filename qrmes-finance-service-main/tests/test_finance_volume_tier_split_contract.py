from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "app_web" / "static" / "finance_demo" / "app.js"
SCRIPT = ROOT / "changjiang-bom-pricing" / "scripts" / "model_volume_pricing.py"


class FinanceVolumeTierSplitContractTests(unittest.TestCase):
    def test_frontend_labels_no_longer_describe_300_and_1000_as_shared_discount_band(self):
        text = APP_JS.read_text(encoding="utf-8")
        self.assertIn("buildMassVolumeRequestLabel", text)
        self.assertIn("折扣档位", text)
        self.assertNotIn("共享折扣区间", text)

    def test_volume_pricing_script_mentions_split_tiers_up_to_5000(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("≤300套/年", text)
        self.assertIn("301-1000套/年", text)
        self.assertIn("1001-3000套/年", text)
        self.assertIn("3001-5000套/年", text)


if __name__ == "__main__":
    unittest.main()
