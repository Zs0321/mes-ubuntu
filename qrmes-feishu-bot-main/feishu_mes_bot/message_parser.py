from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Tuple

from .models import IncomingMessage


PLACEHOLDER_TEMPLATE = "[{message_type}消息]"


def _load_content(raw_content: Any) -> Dict[str, Any]:
    if isinstance(raw_content, dict):
        return raw_content
    if isinstance(raw_content, str) and raw_content.strip():
        try:
            parsed = json.loads(raw_content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {"text": raw_content}
    return {}


def _extract_post_text(content: Dict[str, Any]) -> str:
    zh_cn = content.get("zh_cn")
    if not isinstance(zh_cn, dict):
        return ""
    parts: List[str] = []
    blocks = zh_cn.get("content")
    if isinstance(blocks, list):
        for line in blocks:
            if not isinstance(line, list):
                continue
            for item in line:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
    return " ".join(parts).strip()


def _normalize_text(content: Dict[str, Any], message_type: str) -> str:
    if message_type == "post":
        post_text = _extract_post_text(content)
        if post_text:
            return post_text
    for key in ("text", "title"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _strip_mention_text(text: str, mention_keys: Iterable[str], bot_name: str) -> str:
    normalized = text or ""
    for key in mention_keys:
        if isinstance(key, str) and key.strip():
            normalized = normalized.replace(key.strip(), " ")
    if bot_name:
        normalized = normalized.replace("@%s" % bot_name, " ")
    return " ".join(normalized.split()).strip()


def _extract_resource(content: Dict[str, Any], message_type: str) -> Tuple[str, str]:
    if message_type == 'image':
        key = content.get('image_key')
        if isinstance(key, str):
            return key, ''
    if message_type == 'file':
        key = content.get('file_key')
        name = content.get('file_name')
        return (key if isinstance(key, str) else ''), (name if isinstance(name, str) else '')
    return '', ''


def parse_feishu_event(payload: Dict[str, Any], bot_open_id: str = "", bot_name: str = "") -> IncomingMessage | None:
    if not isinstance(payload, dict):
        return None
    header = payload.get("header") or {}
    if header.get("event_type") != "im.message.receive_v1":
        return None

    event = payload.get("event") or {}
    message = event.get("message") or {}
    sender = event.get("sender") or {}
    sender_id = sender.get("sender_id") or {}
    sender_open_id = sender_id.get("open_id") if isinstance(sender_id, dict) else ""
    sender_open_id = sender_open_id or ""

    message_type = message.get("message_type") or "text"
    content = _load_content(message.get("content"))
    raw_text = _normalize_text(content, message_type)
    resource_key, resource_name = _extract_resource(content, message_type)
    mention_keys = []
    mentions = []
    for item in message.get("mentions") or []:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if isinstance(key, str) and key.strip():
            mention_keys.append(key.strip())
        mention_id = item.get("id") or {}
        open_id = mention_id.get("open_id") if isinstance(mention_id, dict) else ""
        if isinstance(open_id, str) and open_id:
            mentions.append(open_id)
    text = _strip_mention_text(raw_text, mention_keys, bot_name)
    if not text:
        text = PLACEHOLDER_TEMPLATE.format(message_type=message_type)

    chat_type = message.get("chat_type") or "group"
    at_bot = chat_type == "p2p" or (bool(bot_open_id) and bot_open_id in mentions)
    if not at_bot and chat_type != "p2p" and bot_name and ("@%s" % bot_name) in raw_text:
        at_bot = True

    if chat_type == "p2p":
        receive_id = sender_open_id
        receive_id_type = "open_id"
    else:
        receive_id = message.get("chat_id") or ""
        receive_id_type = "chat_id"

    return IncomingMessage(
        text=text,
        sender_name=(sender.get("sender_name") or sender_open_id or "unknown"),
        sender_open_id=sender_open_id,
        chat_id=message.get("chat_id") or "",
        chat_type=chat_type,
        message_id=message.get("message_id") or "",
        at_bot=at_bot,
        receive_id=receive_id,
        receive_id_type=receive_id_type,
        message_type=message_type,
        mentions=tuple(mentions),
        resource_key=resource_key,
        resource_type=message_type if resource_key else '',
        resource_name=resource_name,
    )
