from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class OpenAiCompatibleService:
    base_url: str
    api_key: str = ""
    timeout: float = 20.0

    def chat(self, *, model: str, messages: list[dict[str, Any]], temperature: float = 0.2, max_tokens: int = 400) -> str | None:
        if not self.base_url.strip() or not model.strip() or not messages:
            return None

        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            try:
                exc.read()
            except Exception:
                pass
            return None
        except Exception:
            return None

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return None

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        first = choices[0]
        if not isinstance(first, dict):
            return None
        message = first.get("message")
        if not isinstance(message, dict):
            return None
        content = message.get("content")
        if not isinstance(content, str):
            return None
        reply = content.strip()
        return reply or None
