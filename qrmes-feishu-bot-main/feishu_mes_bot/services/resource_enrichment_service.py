from __future__ import annotations

import os
from dataclasses import replace

from ..models import IncomingMessage


class ResourceEnrichmentService:
    def __init__(self, file_service, cache_dir: str):
        self.file_service = file_service
        self.cache_dir = cache_dir

    def enrich(self, message: IncomingMessage) -> IncomingMessage:
        if not message.resource_key or not message.resource_type:
            return message
        payload = self.file_service.download_resource(message.resource_type, message.resource_key)
        if not payload:
            return message
        local_path = self.file_service.save_resource_bytes(self.cache_dir, message.resource_name or '', payload)
        extra_text = self._build_extra_text(message.resource_type, message.resource_name, local_path, payload)
        return replace(message, text=(message.text + '\n' + extra_text).strip(), resource_name=local_path)

    def _build_extra_text(self, resource_type: str, resource_name: str, local_path: str, payload: bytes) -> str:
        label = '上传图片摘要' if resource_type == 'image' else '上传文件摘要'
        excerpt = ''
        if resource_type == 'file':
            excerpt = payload.decode('utf-8', errors='ignore').strip().splitlines()[-5:]
            excerpt = ' | '.join(excerpt)
        return '%s: name=%s, saved=%s%s' % (
            label,
            resource_name or os.path.basename(local_path),
            local_path,
            ', excerpt=%s' % excerpt if excerpt else ''
        )
