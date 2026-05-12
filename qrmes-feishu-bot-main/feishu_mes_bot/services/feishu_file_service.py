from __future__ import annotations

import os
import urllib.parse
import urllib.request

from .feishu_client import FeishuBotClient


class FeishuFileService(FeishuBotClient):
    def build_download_url(self, resource_type: str, resource_key: str) -> str:
        if resource_type == 'image':
            return 'https://open.feishu.cn/open-apis/image/v4/get?image_key=%s' % urllib.parse.quote(resource_key)
        if resource_type == 'file':
            return 'https://open.feishu.cn/open-apis/im/v1/files/%s' % urllib.parse.quote(resource_key)
        raise ValueError('unsupported resource type: %s' % resource_type)

    def download_resource(self, resource_type: str, resource_key: str) -> bytes | None:
        token = self._get_tenant_access_token()
        if not token:
            return None
        request = urllib.request.Request(
            self.build_download_url(resource_type, resource_key),
            headers={'Authorization': 'Bearer %s' % token},
            method='GET',
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except Exception:
            return None

    def save_resource_bytes(self, target_dir: str, resource_name: str, content: bytes) -> str:
        os.makedirs(target_dir, exist_ok=True)
        filename = resource_name or 'resource.bin'
        path = os.path.join(target_dir, filename)
        with open(path, 'wb') as fh:
            fh.write(content)
        return path
