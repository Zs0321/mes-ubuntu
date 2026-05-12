import tempfile
import unittest

from feishu_mes_bot.services.feishu_file_service import FeishuFileService


class FeishuFileServiceTests(unittest.TestCase):
    def test_build_download_url_for_image(self):
        service = FeishuFileService(app_id='a', app_secret='b')
        self.assertIn('/image/v4/get', service.build_download_url('image', 'img_xxx'))

    def test_save_bytes_to_temp_file(self):
        service = FeishuFileService(app_id='a', app_secret='b')
        with tempfile.TemporaryDirectory() as tmp:
            path = service.save_resource_bytes(tmp, 'error.log', b'hello world')
            with open(path, 'rb') as fh:
                self.assertEqual(b'hello world', fh.read())


if __name__ == '__main__':
    unittest.main()
