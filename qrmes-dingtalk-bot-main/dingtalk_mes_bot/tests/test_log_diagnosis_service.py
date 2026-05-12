import unittest

from dingtalk_mes_bot.models import IncomingMessage, DownloadedImage
from dingtalk_mes_bot.services.issue_diagnosis_service import IssueDiagnosisService


class FakeProbeService:
    def collect(self, targets):
        return {'qrmes-web-core': {'health': [], 'files': [], 'scripts': []}}


class FakeDownloader:
    def download_images(self, download_codes):
        return [DownloadedImage(download_code=download_codes[0], mime_type='text/plain', data=b'Traceback\nrequests.exceptions.ConnectionError: connection refused\nHTTP 500\n')]


class LogDiagnosisServiceTests(unittest.TestCase):
    def test_diagnose_message_with_uploaded_log_file(self):
        service = IssueDiagnosisService(probe_service=FakeProbeService(), file_downloader=FakeDownloader())
        msg = IncomingMessage('[文件消息]', 'tester', '2', '', True, message_type='file', image_download_codes=('code1',))
        reply = service.diagnose_message(msg)
        self.assertIn('日志诊断', reply)
        self.assertIn('connection refused', reply)
        self.assertIn('HTTP 500', reply)


if __name__ == '__main__':
    unittest.main()
