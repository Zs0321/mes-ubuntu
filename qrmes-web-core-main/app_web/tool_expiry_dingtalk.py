#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import quote_plus

import requests

logger = logging.getLogger(__name__)


class DingtalkToolExpiryNotifier:
    def __init__(self, webhook: str = "", secret: str = "", timeout: float = 5.0, logger_: Optional[logging.Logger] = None):
        self.webhook = str(webhook or "").strip()
        self.secret = str(secret or "").strip()
        self.timeout = float(timeout or 5.0)
        self.logger = logger_ or logger

    @classmethod
    def from_app_config(cls, config: Any) -> "DingtalkToolExpiryNotifier":
        webhook = (
            config.get("TOOL_EXPIRY_DINGTALK_WEBHOOK")
            or os.getenv("TOOL_EXPIRY_DINGTALK_WEBHOOK")
            or os.getenv("DINGTALK_TOOL_EXPIRY_WEBHOOK")
            or os.getenv("DINGTALK_BOT_WEBHOOK")
            or ""
        )
        secret = (
            config.get("TOOL_EXPIRY_DINGTALK_SECRET")
            or os.getenv("TOOL_EXPIRY_DINGTALK_SECRET")
            or os.getenv("DINGTALK_TOOL_EXPIRY_SECRET")
            or ""
        )
        timeout = config.get("TOOL_EXPIRY_DINGTALK_TIMEOUT") or os.getenv("TOOL_EXPIRY_DINGTALK_TIMEOUT") or 5
        return cls(webhook=webhook, secret=secret, timeout=float(timeout))

    def send_expiry_reminder(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.webhook:
            self.logger.info("未配置 TOOL_EXPIRY_DINGTALK_WEBHOOK，跳过工具到期钉钉提醒")
            return {"skipped": True, "reason": "webhook_not_configured"}

        message = self._build_message(payload)
        response = requests.post(self._signed_webhook(), json=message, timeout=self.timeout)
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text}
        if isinstance(data, dict) and data.get("errcode") not in (None, 0):
            raise RuntimeError("DingTalk webhook error: %s" % data)
        return data if isinstance(data, dict) else {"response": data}

    def _signed_webhook(self) -> str:
        if not self.secret:
            return self.webhook
        timestamp = str(round(time.time() * 1000))
        string_to_sign = "%s\n%s" % (timestamp, self.secret)
        digest = hmac.new(self.secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
        sign = quote_plus(base64.b64encode(digest))
        separator = "&" if "?" in self.webhook else "?"
        return "%s%stimestamp=%s&sign=%s" % (self.webhook, separator, timestamp, sign)

    @staticmethod
    def _build_message(payload: Dict[str, Any]) -> Dict[str, Any]:
        tool_code = payload.get("toolCode") or "未知工具"
        tool_name = payload.get("toolName") or "未填写"
        valid_until = payload.get("validUntil") or "未知"
        days_remaining = payload.get("daysRemaining")
        stage = payload.get("notifyStage") or ""
        stage_text = "7天内到期" if stage == "7d" else "30天内到期"
        operator = payload.get("operator") or "未记录"
        text = (
            "### 工具二维码到期提醒\n\n"
            "- 工具编码：%s\n"
            "- 工具名称：%s\n"
            "- 有效期：%s\n"
            "- 剩余天数：%s 天\n"
            "- 提醒阶段：%s\n"
            "- 扫码人员：%s\n\n"
            "> 请及时安排校验或更换。"
        ) % (tool_code, tool_name, valid_until, days_remaining, stage_text, operator)
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": "工具到期提醒：%s" % tool_code,
                "text": text,
            },
        }
