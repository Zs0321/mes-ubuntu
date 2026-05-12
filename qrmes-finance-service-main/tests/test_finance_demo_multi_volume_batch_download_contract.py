from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "app_web" / "static" / "finance_demo" / "app.js"


class FinanceDemoMultiVolumeBatchDownloadContractTests(unittest.TestCase):
    def test_app_js_mentions_batch_package_download_for_multi_volume_payloads(self):
        text = APP_JS.read_text(encoding="utf-8")
        self.assertIn("lastExcelQuotePayloads", text)
        self.assertIn("exportQuotePackageBatch", text)
        self.assertIn("submitExcelQuoteForVolumes", text)
        self.assertIn("/api/quote/export-package-batch", text)

    def test_app_js_avoids_cascading_volume_labels_in_multi_volume_payload_decoration(self):
        text = APP_JS.read_text(encoding="utf-8")
        self.assertIn('original_label', text)
        self.assertIn('original_filename', text)
        self.assertIn('nextPayload.model.label = `${originalLabel}｜${requestLabel}`', text)
        self.assertIn('nextPayload.model.filename = `${originalFilename}_${normalizedVolume}套年`', text)
        self.assertIn('reprojectMassQuotePayload(referencePayload, referenceVolume, referenceLabel)', text)


if __name__ == "__main__":
    unittest.main()
