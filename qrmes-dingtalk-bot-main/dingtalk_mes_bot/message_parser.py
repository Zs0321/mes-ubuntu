from __future__ import annotations
from typing import Any
from .models import IncomingMessage


def _pick_message_type(data: dict[str, Any]) -> str:
    msg_type = data.get("msgtype")
    if isinstance(msg_type, str) and msg_type:
        return msg_type
    return "text"


def _pick_text(data: dict[str, Any]) -> str:
    text = data.get("text")
    if isinstance(text, dict):
        content = text.get("content")
        if isinstance(content, str):
            stripped = content.strip()
            if stripped:
                return stripped
    content = data.get("content")
    if isinstance(content, dict):
        rich_text = content.get("richText")
        if isinstance(rich_text, list):
            parts: list[str] = []
            for item in rich_text:
                if not isinstance(item, dict):
                    continue
                raw = item.get("text")
                if isinstance(raw, str) and raw.strip():
                    parts.append(raw.strip())
            if parts:
                return "".join(parts).strip()
        raw = content.get("text")
        if isinstance(raw, str):
            stripped = raw.strip()
            if stripped:
                return stripped
    if isinstance(content, str):
        stripped = content.strip()
        if stripped:
            return stripped
    raw = data.get("msg")
    if isinstance(raw, str):
        return raw.strip()
    return ""


def _pick_sender(data: dict[str, Any]) -> str:
    for key in ("senderNick", "senderStaffId", "chatbotUserId", "senderId"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    sender = data.get("senderId")
    if isinstance(sender, dict):
        for key in ("staffId", "dingtalkId", "nick"):
            value = sender.get(key)
            if isinstance(value, str) and value:
                return value
    return "unknown"


def _is_group(conversation_type: str) -> bool:
    return conversation_type in {"2", "group", "GROUP"}


def _pick_attachment_download_codes(data: dict[str, Any]) -> tuple[str, ...]:
    codes: list[str] = []
    content = data.get("content")
    if isinstance(content, dict):
        download_code = content.get("downloadCode")
        if isinstance(download_code, str) and download_code:
            codes.append(download_code)
        rich_text = content.get("richText")
        if isinstance(rich_text, list):
            for item in rich_text:
                if not isinstance(item, dict):
                    continue
                raw = item.get("downloadCode")
                if isinstance(raw, str) and raw:
                    codes.append(raw)
    return tuple(codes)


def _at_bot(data: dict[str, Any], robot_code: str, text: str) -> bool:
    conversation_type = str(data.get("conversationType", ""))
    if not _is_group(conversation_type):
        return True
    is_in_at_list = data.get("isInAtList")
    if isinstance(is_in_at_list, bool):
        return is_in_at_list
    at_users = data.get("atUsers")
    if isinstance(at_users, list):
        for user in at_users:
            if not isinstance(user, dict):
                continue
            for key in ("staffId", "dingtalkId", "userId"):
                value = user.get(key)
                if isinstance(value, str) and robot_code and value == robot_code:
                    return True
    if robot_code and robot_code in text:
        return True
    return "@" in text


def parse_message(payload: dict[str, Any], robot_code: str) -> IncomingMessage | None:
    if not isinstance(payload, dict):
        return None
    message_type = _pick_message_type(payload)
    text = _pick_text(payload)
    attachment_download_codes = _pick_attachment_download_codes(payload)
    if not text and not attachment_download_codes:
        return None
    if not text and attachment_download_codes:
        text = "[文件消息]" if message_type == 'file' else "[图片消息]"
    conversation_type = str(payload.get("conversationType", ""))
    session_webhook = payload.get("sessionWebhook")
    if not isinstance(session_webhook, str):
        session_webhook = ""
    return IncomingMessage(
        text=text,
        sender_nick=_pick_sender(payload),
        conversation_type=conversation_type,
        session_webhook=session_webhook,
        at_bot=_at_bot(payload, robot_code, text),
        sender_staff_id=str(payload.get("senderStaffId") or "").strip(),
        message_type=message_type,
        image_download_codes=attachment_download_codes,
    )
