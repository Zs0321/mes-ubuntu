import unittest

from feishu_mes_bot.services.issue_diagnosis_service import IssueDiagnosisService
from feishu_mes_bot.services.repository_catalog import RepositoryCatalog


class FakeProbeService:
    def collect(self, targets):
        return {'qrmes-web-core': {'health': [], 'scripts': [], 'files': []}}


class FakeSummaryService:
    def __init__(self):
        self.calls = []

    def summarize(self, user_text, diagnosis_text):
        self.calls.append((user_text, diagnosis_text))
        return '追问建议：请补充项目名和报错时间。'


class DiagnosisSummaryTests(unittest.TestCase):
    def test_diagnose_appends_llm_followup_summary(self):
        summary_service = FakeSummaryService()
        service = IssueDiagnosisService(
            repository_catalog=RepositoryCatalog(),
            probe_service=FakeProbeService(),
            summary_service=summary_service,
        )

        reply = service.diagnose('web发布后打不开')
        self.assertIn('追问建议', reply)
        self.assertEqual(1, len(summary_service.calls))


if __name__ == '__main__':
    unittest.main()
