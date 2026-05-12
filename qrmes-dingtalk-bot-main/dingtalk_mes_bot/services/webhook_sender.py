from __future__ import annotations

import json
import logging
import urllib.request

logger = logging.getLogger("dingtalk_mes_bot.webhook")


def send_text_reply(session_webhook: str, content: str, timeout: float = 6.0) -> bool:
    if not session_webhook or not content:
        logger.info("skip webhook send: missing session webhook or content")
        return False

    body = json.dumps({"msgtype": "text", "text": {"content": content}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        session_webhook,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
            ok = int(resp.status) == 200
            logger.info("webhook reply status=%s body=%s", resp.status, payload)
            return ok
    except Exception as exc:
        logger.exception("webhook reply failed: %s", exc)
        return False
