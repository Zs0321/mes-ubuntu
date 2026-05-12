import json
import unittest
from unittest.mock import patch

from feishu_mes_bot.services.hermes_api_service import HermesApiService


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class HermesApiServiceTests(unittest.TestCase):
    @patch('urllib.request.urlopen')
    def test_chat_uses_session_new_then_chat_sync(self, mock_urlopen):
        mock_urlopen.side_effect = [
            FakeResponse({'session': {'session_id': 'sess_1'}}),
            FakeResponse({'answer': 'Hermes总结'})
        ]
        service = HermesApiService(base_url='http://127.0.0.1:8787', workspace='/tmp/demo')
        reply = service.chat('gpt-5.4', '系统提示', '用户问题')
        self.assertEqual('Hermes总结', reply)
        self.assertEqual(2, mock_urlopen.call_count)


if __name__ == '__main__':
    unittest.main()
