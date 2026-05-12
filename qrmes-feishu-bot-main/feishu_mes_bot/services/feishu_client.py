from __future__ import annotations

import json
import urllib.error
import urllib.request


class FeishuBotClient:
    def __init__(self, app_id: str, app_secret: str, timeout: float = 10.0):
        self.app_id = app_id or ""
        self.app_secret = app_secret or ""
        self.timeout = timeout
        self._tenant_access_token = None

    def send_text(self, receive_id: str, receive_id_type: str, text: str) -> bool:
        if not self.app_id or not self.app_secret or not receive_id:
            return False
        token = self._get_tenant_access_token()
        if not token:
            return False
        body = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        request = urllib.request.Request(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=%s" % receive_id_type,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": "Bearer %s" % token,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        except (urllib.error.URLError, ValueError):
            return False
        return payload.get("code") == 0 if isinstance(payload, dict) else False

    def _get_tenant_access_token(self) -> str | None:
        if self._tenant_access_token:
            return self._tenant_access_token
        request = urllib.request.Request(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            data=json.dumps({"app_id": self.app_id, "app_secret": self.app_secret}).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        except (urllib.error.URLError, ValueError):
            return None
        token = payload.get("tenant_access_token") if isinstance(payload, dict) else None
        if isinstance(token, str) and token:
            self._tenant_access_token = token
            return token
        return None
