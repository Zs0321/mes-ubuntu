from __future__ import annotations

import json
import urllib.request


class HermesApiService:
    def __init__(self, base_url: str, workspace: str, timeout: float = 30.0, model: str = ''):
        self.base_url = (base_url or '').rstrip('/')
        self.workspace = workspace or ''
        self.timeout = timeout
        self.default_model = model or ''

    def chat(self, model: str, system_prompt: str, user_prompt: str) -> str | None:
        if not self.base_url:
            return None
        session_payload = {'workspace': self.workspace}
        if model or self.default_model:
            session_payload['model'] = model or self.default_model
        session = self._post('/api/session/new', session_payload)
        session_id = ((session or {}).get('session') or {}).get('session_id')
        if not session_id:
            return None
        message = user_prompt if not system_prompt else ('%s\n\n%s' % (system_prompt, user_prompt))
        answer = self._post('/api/chat', {
            'session_id': session_id,
            'workspace': self.workspace,
            'model': model or self.default_model,
            'message': message,
        })
        if not isinstance(answer, dict):
            return None
        raw = answer.get('answer')
        return raw.strip() if isinstance(raw, str) and raw.strip() else None

    def _post(self, path: str, payload: dict) -> dict | None:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json; charset=utf-8'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode('utf-8', errors='ignore'))
        except Exception:
            return None
