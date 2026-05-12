from __future__ import annotations

import logging
from typing import Any

from .config import load_config
from .message_parser import parse_message
from .reply_engine import build_reply
from .runtime import create_runtime
from .services.webhook_sender import send_text_reply


def _to_payload(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        text_obj = message.get("text")
        content = ""
        if isinstance(text_obj, dict):
            raw_content = text_obj.get("content", "")
            content = str(raw_content) if raw_content is not None else ""
        return {
            "msgtype": str(message.get("msgtype", "text")),
            "conversationType": str(message.get("conversationType", "group")),
            "sessionWebhook": str(message.get("sessionWebhook", "")),
            "senderNick": str(message.get("senderNick", "unknown")),
            "senderStaffId": str(message.get("senderStaffId", "")),
            "chatbotUserId": str(message.get("chatbotUserId", "")),
            "senderId": message.get("senderId", ""),
            "atUsers": message.get("atUsers", []),
            "isInAtList": message.get("isInAtList", False),
            "content": message.get("content", {}),
            "text": {"content": content},
        }

    text_obj = getattr(message, "text", None)
    content = getattr(text_obj, "content", "") if text_obj else ""
    content_obj: dict[str, Any] = {}
    image_content = getattr(message, "image_content", None)
    if image_content is not None:
        download_code = getattr(image_content, "download_code", "")
        if download_code:
            content_obj["downloadCode"] = str(download_code)
    rich_text_content = getattr(message, "rich_text_content", None)
    if rich_text_content is not None:
        rich_text_list = getattr(rich_text_content, "rich_text_list", None)
        if isinstance(rich_text_list, list):
            content_obj["richText"] = rich_text_list
    return {
        "msgtype": str(getattr(message, "message_type", "text")),
        "conversationType": str(getattr(message, "conversation_type", "group")),
        "sessionWebhook": str(getattr(message, "session_webhook", "")),
        "senderNick": str(getattr(message, "sender_nick", "unknown")),
        "senderStaffId": str(getattr(message, "sender_staff_id", "")),
        "chatbotUserId": str(getattr(message, "chatbot_user_id", "")),
        "senderId": getattr(message, "sender_id", ""),
        "atUsers": getattr(message, "at_users", []),
        "isInAtList": getattr(message, "is_in_at_list", False),
        "content": content_obj,
        "text": {"content": str(content)},
    }


def main() -> int:
    cfg = load_config()
    runtime = create_runtime(cfg)
    logger = logging.getLogger("dingtalk_mes_bot.stream")

    if not cfg.client_id or not cfg.client_secret:
        raise SystemExit("missing DINGTALK_BOT_CLIENT_ID / DINGTALK_BOT_CLIENT_SECRET")

    import dingtalk_stream

    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO))

    class ChatbotHandler(dingtalk_stream.ChatbotHandler):
        async def process(self, callback):
            raw = callback.data
            logger.info(
                "raw callback data type=%s payload=%s",
                type(raw).__name__,
                raw if isinstance(raw, dict) else getattr(raw, "to_dict", lambda: str(raw))(),
            )
            payload = _to_payload(callback.data)
            message = parse_message(payload, cfg.robot_code)
            logger.info(
                "incoming sender=%s conversation=%s at_bot=%s has_webhook=%s text=%s",
                getattr(message, "sender_nick", "unknown"),
                getattr(message, "conversation_type", ""),
                getattr(message, "at_bot", False),
                bool(getattr(message, "session_webhook", "")),
                getattr(message, "text", ""),
            )
            if not message or not message.at_bot:
                logger.info("skip reply: message missing or not @bot")
                return dingtalk_stream.AckMessage.STATUS_OK, "ignored"

            reply = build_reply(runtime, message)
            if reply and message.session_webhook:
                logger.info("sending reply: %s", reply)
                sent = send_text_reply(message.session_webhook, reply)
                logger.info("reply send result=%s", sent)
            else:
                logger.info("skip reply send: empty reply or missing session webhook")
            return dingtalk_stream.AckMessage.STATUS_OK, "ok"

    credential = dingtalk_stream.Credential(cfg.client_id, cfg.client_secret)
    client = dingtalk_stream.DingTalkStreamClient(credential)
    client.register_callback_handler(dingtalk_stream.ChatbotMessage.TOPIC, ChatbotHandler())
    client.start_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
