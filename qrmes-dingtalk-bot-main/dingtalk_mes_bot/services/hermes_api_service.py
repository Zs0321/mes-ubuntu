from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class HermesApiService:
    base_url: str
    workspace: str
    timeout: float = 30.0
    default_model: str = ''

    def chat(self, *, model: str, messages: list[dict[str, Any]], temperature: float = 0.2, max_tokens: int = 400) -> str | None:
        if not self.base_url.strip() or not messages:
            return None
        session_payload = {'workspace': self.workspace}
        target_model = (model or self.default_model).strip()
        if target_model:
            session_payload['model'] = target_model
        session = self._post('/api/session/new', session_payload)
        session_id = ((session or {}).get('session') or {}).get('session_id')
        if not session_id:
            return None
        merged = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = str(msg.get('content') or '').strip()
            if not content:
                continue
            role = str(msg.get('role') or 'user').strip()
            merged.append(f'[{role}] {content}')
        prompt = '\n\n'.join(merged).strip()
        if not prompt:
            return None
        started = self._post('/api/chat/start', {
            'session_id': session_id,
            'workspace': self.workspace,
            'model': target_model,
            'message': prompt,
            'no_tools': True,
        })
        stream_id = str((started or {}).get('stream_id') or '').strip()
        if not stream_id:
            return None
        return self._consume_stream(stream_id)

    def _consume_stream(self, stream_id: str) -> str | None:
        url = self.base_url.rstrip('/') + '/api/chat/stream?' + urllib.parse.urlencode({'stream_id': stream_id})
        request = urllib.request.Request(url, headers={'Accept': 'text/event-stream'}, method='GET')
        stream_timeout = max(float(self.timeout or 0), 180.0)
        try:
            with urllib.request.urlopen(request, timeout=stream_timeout) as response:
                raw = response.read().decode('utf-8', errors='replace')
        except Exception:
            return None
        return self._parse_stream_response(raw)

    @staticmethod
    def _parse_stream_response(raw: str) -> str | None:
        if not raw.strip():
            return None
        current_event = ''
        data_lines: list[str] = []
        for line in raw.splitlines():
            if line.startswith('event:'):
                current_event = line.split(':', 1)[1].strip()
                continue
            if line.startswith('data:'):
                data_lines.append(line.split(':', 1)[1].strip())
                continue
            if line.strip():
                continue
            if not current_event:
                data_lines = []
                continue
            payload_text = '\n'.join(data_lines).strip()
            payload = {}
            if payload_text:
                try:
                    payload = json.loads(payload_text)
                except json.JSONDecodeError:
                    payload = {}
            if current_event == 'done':
                session = payload.get('session') if isinstance(payload, dict) else None
                messages = session.get('messages') if isinstance(session, dict) else None
                if isinstance(messages, list):
                    for message in reversed(messages):
                        if not isinstance(message, dict):
                            continue
                        if message.get('role') != 'assistant':
                            continue
                        content = str(message.get('content') or '').strip()
                        if content:
                            return content
                answer = payload.get('answer') if isinstance(payload, dict) else None
                if isinstance(answer, str) and answer.strip():
                    return answer.strip()
                return None
            if current_event in {'apperror', 'error', 'cancel'}:
                return None
            current_event = ''
            data_lines = []
        return None

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        request = urllib.request.Request(
            self.base_url.rstrip('/') + path,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode('utf-8', errors='replace')
        except Exception:
            return None
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
