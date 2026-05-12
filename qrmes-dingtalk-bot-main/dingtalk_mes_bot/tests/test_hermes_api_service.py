import json
import unittest
from unittest.mock import patch

from dingtalk_mes_bot.services.hermes_api_service import HermesApiService


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        if isinstance(self.payload, str):
            return self.payload.encode('utf-8')
        return json.dumps(self.payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class HermesApiServiceTests(unittest.TestCase):
    @patch('urllib.request.urlopen')
    def test_chat_uses_session_new_then_chat_start_and_stream(self, mock_urlopen):
        mock_urlopen.side_effect = [
            FakeResponse({'session': {'session_id': 'sess_1'}}),
            FakeResponse({'stream_id': 'stream_1', 'session_id': 'sess_1'}),
            FakeResponse(
                'event: delta\n'
                'data: {"text": "Hermes"}\n\n'
                'event: done\n'
                'data: {"session": {"messages": [{"role": "assistant", "content": "Hermes回答"}]}}\n\n'
            ),
        ]
        service = HermesApiService(base_url='http://127.0.0.1:8787', workspace='/tmp/demo', timeout=30, default_model='gpt-5.5')
        reply = service.chat(model='gpt-5.5', messages=[{'role': 'system', 'content': '你是助手'}, {'role': 'user', 'content': '你好'}])
        self.assertEqual('Hermes回答', reply)
        self.assertEqual(3, mock_urlopen.call_count)
        self.assertIn('/api/chat/start', mock_urlopen.call_args_list[1].args[0].full_url)
        self.assertIn('/api/chat/stream?stream_id=stream_1', mock_urlopen.call_args_list[2].args[0].full_url)

    @patch('urllib.request.urlopen')
    def test_chat_returns_none_when_stream_reports_app_error(self, mock_urlopen):
        mock_urlopen.side_effect = [
            FakeResponse({'session': {'session_id': 'sess_1'}}),
            FakeResponse({'stream_id': 'stream_1', 'session_id': 'sess_1'}),
            FakeResponse(
                'event: apperror\n'
                'data: {"message": "Request timed out", "type": "error"}\n\n'
            ),
        ]
        service = HermesApiService(base_url='http://127.0.0.1:8787', workspace='/tmp/demo', timeout=30, default_model='gpt-5.5')
        reply = service.chat(model='gpt-5.5', messages=[{'role': 'user', 'content': '你好'}])
        self.assertIsNone(reply)


if __name__ == '__main__':
    unittest.main()
