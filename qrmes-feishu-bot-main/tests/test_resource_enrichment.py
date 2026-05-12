import os
import tempfile
import unittest

from feishu_mes_bot.models import IncomingMessage
from feishu_mes_bot.services.resource_enrichment_service import ResourceEnrichmentService


class FakeFileService:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def download_resource(self, resource_type, resource_key):
        self.calls.append((resource_type, resource_key))
        return self.payload

    def save_resource_bytes(self, target_dir, resource_name, content):
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, resource_name or 'resource.bin')
        with open(path, 'wb') as fh:
            fh.write(content)
        return path


class ResourceEnrichmentServiceTests(unittest.TestCase):
    def test_enrich_file_message_appends_log_excerpt(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = ResourceEnrichmentService(FakeFileService(b'ERROR one\nTraceback two\nlast line\n'), tmp)
            message = IncomingMessage(
                text='[file消息]', sender_name='u', sender_open_id='ou', chat_id='oc', chat_type='group',
                message_id='om', at_bot=True, receive_id='oc', receive_id_type='chat_id',
                message_type='file', resource_key='file_x', resource_type='file', resource_name='error.log'
            )
            enriched = service.enrich(message)
            self.assertIn('上传文件摘要', enriched.text)
            self.assertIn('Traceback two', enriched.text)
            self.assertTrue(enriched.resource_name.endswith('error.log'))


if __name__ == '__main__':
    unittest.main()
