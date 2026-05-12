import unittest

from feishu_mes_bot.services.issue_diagnosis_service import IssueDiagnosisService
from feishu_mes_bot.services.repository_catalog import RepositoryCatalog


class FakeProbeService:
    def __init__(self):
        self.calls = []

    def collect(self, targets):
        self.calls.append(tuple(targets))
        return {
            "qrmes-web-core": {
                "health": [{"label": "web health", "ok": False, "detail": "connection refused"}],
                "scripts": [{"path": "scripts/healthcheck.sh", "exists": True}],
                "files": [{"path": "runtime.log", "exists": False}],
            },
            "qrmes-android": {
                "health": [],
                "scripts": [{"path": "scripts/deploy_apk_to_qrmes_apk.sh", "exists": True}],
                "files": [],
            },
        }


class IssueDiagnosisServiceTests(unittest.TestCase):
    def test_can_handle_known_keywords(self):
        service = IssueDiagnosisService(repository_catalog=RepositoryCatalog(), probe_service=FakeProbeService())
        self.assertTrue(service.can_handle("APK更新失败"))
        self.assertTrue(service.can_handle("web发布后打不开"))
        self.assertFalse(service.can_handle("帮我写周报"))

    def test_diagnose_apk_update_problem(self):
        probe = FakeProbeService()
        service = IssueDiagnosisService(repository_catalog=RepositoryCatalog(), probe_service=probe)

        reply = service.diagnose("APK更新失败，web端正常")
        self.assertIn("问题归类", reply)
        self.assertIn("APK 更新", reply)
        self.assertIn("versionCode", reply)
        self.assertIn("/api/apk/latest", reply)
        self.assertIn("qrmes-android", reply)
        self.assertIn("qrmes-web-core", reply)
        self.assertEqual([("qrmes-android", "qrmes-web-core")], probe.calls)

    def test_diagnose_web_publish_problem(self):
        service = IssueDiagnosisService(repository_catalog=RepositoryCatalog(), probe_service=FakeProbeService())

        reply = service.diagnose("web发布后打不开")
        self.assertIn("Web 发布后打不开", reply)
        self.assertIn("/health", reply)
        self.assertIn("runtime.log", reply)
        self.assertIn("connection refused", reply)


if __name__ == "__main__":
    unittest.main()
