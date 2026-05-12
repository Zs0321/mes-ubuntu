#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

VALID_NOTIFY_STAGES = {"30d", "7d"}


class ToolExpiryError(ValueError):
    """Raised when a tool expiry QR code cannot be parsed or validated."""


@dataclass(frozen=True)
class ParsedToolCode:
    tool_code: str
    valid_until: date


def parse_raw_code(raw_code: str) -> ParsedToolCode:
    text = str(raw_code or "").strip()
    if "##" not in text:
        raise ToolExpiryError("工具二维码格式错误，应为：工具编码##YYYY-MM-DD")

    tool_code, valid_until_text = [part.strip() for part in text.split("##", 1)]
    if not tool_code:
        raise ToolExpiryError("工具二维码缺少工具编码")
    if not valid_until_text:
        raise ToolExpiryError("工具二维码缺少有效期")

    try:
        valid_until = datetime.strptime(valid_until_text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ToolExpiryError("工具二维码有效期格式错误，应为 YYYY-MM-DD") from exc

    return ParsedToolCode(tool_code=tool_code, valid_until=valid_until)


def resolve_notify_stage(days_remaining: int) -> str:
    if days_remaining < 0:
        return "expired"
    if days_remaining <= 7:
        return "7d"
    if days_remaining <= 30:
        return "30d"
    return "none"


def _utc_now_text() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class ToolExpiryService:
    def __init__(
        self,
        db_path: Any,
        notifier: Optional[Any] = None,
        today_provider: Optional[Callable[[], date]] = None,
        logger_: Optional[logging.Logger] = None,
    ) -> None:
        self.db_path = Path(str(db_path))
        self.notifier = notifier
        self.today_provider = today_provider or date.today
        self.logger = logger_ or logger

    def ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_expiry_scan_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_code TEXT NOT NULL,
                    tool_name TEXT NOT NULL DEFAULT '',
                    valid_until TEXT NOT NULL,
                    notify_stage TEXT NOT NULL,
                    raw_code TEXT NOT NULL,
                    operator TEXT NOT NULL DEFAULT '',
                    days_remaining INTEGER NOT NULL,
                    notified_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_error TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_tool_expiry_unique_stage
                ON tool_expiry_scan_records(tool_code, valid_until, notify_stage)
                """
            )
            conn.commit()

    def handle_scan(self, raw_code: str, tool_name: str = "", operator: str = "") -> Dict[str, Any]:
        parsed = parse_raw_code(raw_code)
        today = self.today_provider()
        days_remaining = (parsed.valid_until - today).days
        notify_stage = resolve_notify_stage(days_remaining)
        should_notify = notify_stage in VALID_NOTIFY_STAGES
        now_text = _utc_now_text()
        notified = False
        deduplicated = False
        notification_error = ""

        self.ensure_schema()
        record = {
            "toolCode": parsed.tool_code,
            "toolName": str(tool_name or "").strip(),
            "validUntil": parsed.valid_until.isoformat(),
            "daysRemaining": days_remaining,
            "notifyStage": notify_stage,
            "rawCode": str(raw_code or "").strip(),
            "operator": str(operator or "").strip(),
        }

        try:
            inserted = self._insert_record(record, now_text)
        except sqlite3.IntegrityError:
            inserted = False
            deduplicated = True
            self._touch_duplicate(record, now_text)

        if should_notify and inserted:
            try:
                if self.notifier is not None:
                    send_result = self.notifier.send_expiry_reminder(record)
                    if isinstance(send_result, dict) and send_result.get("skipped"):
                        notification_error = str(send_result.get("reason") or "notification_skipped")
                        self._mark_error(record, notification_error, now_text)
                    else:
                        notified = True
                        self._mark_notified(record, now_text)
                else:
                    notification_error = "notifier_not_configured"
                    self._mark_error(record, notification_error, now_text)
            except Exception as exc:  # noqa: BLE001 - webhook failure must not fail scan
                notification_error = str(exc)
                self.logger.warning("工具到期钉钉提醒发送失败: %s", exc, exc_info=True)
                self._mark_error(record, notification_error, now_text)

        message = self._message_for(notify_stage, days_remaining, notified, deduplicated, notification_error)
        result = {
            "success": True,
            "toolCode": record["toolCode"],
            "toolName": record["toolName"],
            "validUntil": record["validUntil"],
            "daysRemaining": days_remaining,
            "notifyStage": notify_stage,
            "notified": notified,
            "deduplicated": deduplicated,
            "message": message,
        }
        if notification_error:
            result["notificationError"] = notification_error
        return result

    def _insert_record(self, record: Dict[str, Any], now_text: str) -> bool:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO tool_expiry_scan_records (
                    tool_code, tool_name, valid_until, notify_stage, raw_code,
                    operator, days_remaining, notified_at, created_at, updated_at, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, '')
                """,
                (
                    record["toolCode"],
                    record["toolName"],
                    record["validUntil"],
                    record["notifyStage"],
                    record["rawCode"],
                    record["operator"],
                    record["daysRemaining"],
                    now_text,
                    now_text,
                ),
            )
            conn.commit()
        return True

    def _touch_duplicate(self, record: Dict[str, Any], now_text: str) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                UPDATE tool_expiry_scan_records
                SET tool_name = COALESCE(NULLIF(?, ''), tool_name),
                    raw_code = ?,
                    operator = COALESCE(NULLIF(?, ''), operator),
                    days_remaining = ?,
                    updated_at = ?
                WHERE tool_code = ? AND valid_until = ? AND notify_stage = ?
                """,
                (
                    record["toolName"],
                    record["rawCode"],
                    record["operator"],
                    record["daysRemaining"],
                    now_text,
                    record["toolCode"],
                    record["validUntil"],
                    record["notifyStage"],
                ),
            )
            conn.commit()

    def _mark_notified(self, record: Dict[str, Any], now_text: str) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                UPDATE tool_expiry_scan_records
                SET notified_at = ?, updated_at = ?, last_error = ''
                WHERE tool_code = ? AND valid_until = ? AND notify_stage = ?
                """,
                (now_text, now_text, record["toolCode"], record["validUntil"], record["notifyStage"]),
            )
            conn.commit()

    def _mark_error(self, record: Dict[str, Any], error: str, now_text: str) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                UPDATE tool_expiry_scan_records
                SET updated_at = ?, last_error = ?
                WHERE tool_code = ? AND valid_until = ? AND notify_stage = ?
                """,
                (now_text, error[:1000], record["toolCode"], record["validUntil"], record["notifyStage"]),
            )
            conn.commit()

    @staticmethod
    def _message_for(stage: str, days_remaining: int, notified: bool, deduplicated: bool, error: str) -> str:
        if stage == "expired":
            return "工具已过有效期，本次仅记录扫码结果"
        if stage == "none":
            return "工具有效期正常，本次仅记录扫码结果"
        if deduplicated:
            return "该工具本有效期、本提醒阶段已提醒过，本次不重复发送"
        if error:
            return "工具到期提醒命中，但钉钉发送失败，扫码结果已保留"
        if notified:
            return "工具将在 %s 天后到期，已发送钉钉提醒" % days_remaining
        return "工具到期提醒已记录"
