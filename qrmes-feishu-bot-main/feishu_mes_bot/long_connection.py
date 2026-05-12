from __future__ import annotations

from .message_parser import parse_feishu_event
from .reply_engine import build_reply
from .runtime import create_runtime
from .service_factory import create_feishu_client, create_resource_enrichment_service


class FeishuLongConnectionBot:
    def __init__(self, config, runtime=None, sender=None, enrichment_service=None, parser=None):
        self.config = config
        self.runtime = runtime or create_runtime(config)
        self.sender = sender or create_feishu_client(config)
        self.enrichment_service = enrichment_service or create_resource_enrichment_service(config)
        self.parser = parser or parse_feishu_event

    def handle_event(self, payload: dict) -> None:
        message = self.parser(payload, bot_open_id=self.config.bot_open_id, bot_name=self.config.bot_name)
        if not message or not message.at_bot:
            return
        message = self.enrichment_service.enrich(message)
        reply = build_reply(self.runtime, message)
        if reply:
            self.sender.send_text(message.receive_id, message.receive_id_type, reply)


def run_long_connection(config) -> None:
    try:
        import lark_oapi as lark
        from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
    except ImportError as exc:
        raise RuntimeError('long_connection 模式需要先安装 lark-oapi，请执行 pip install lark-oapi') from exc

    bot = FeishuLongConnectionBot(config)

    def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
        event = data.event
        payload = {
            'header': {'event_type': 'im.message.receive_v1'},
            'event': {
                'sender': {
                    'sender_id': {'open_id': getattr(event.sender.sender_id, 'open_id', '')},
                    'sender_name': getattr(event.sender, 'name', ''),
                },
                'message': {
                    'message_id': getattr(event.message, 'message_id', ''),
                    'chat_id': getattr(event.message, 'chat_id', ''),
                    'chat_type': getattr(event.message, 'chat_type', 'group'),
                    'message_type': getattr(event.message, 'message_type', 'text'),
                    'content': getattr(event.message, 'content', ''),
                    'mentions': [
                        {
                            'key': getattr(m, 'key', ''),
                            'id': {'open_id': getattr(getattr(m, 'id', None), 'open_id', '')},
                        }
                        for m in (getattr(event.message, 'mentions', None) or [])
                    ],
                },
            },
        }
        bot.handle_event(payload)

    event_handler = lark.EventDispatcherHandler.builder('', '').register_p2_im_message_receive_v1(do_p2_im_message_receive_v1).build()
    ws_client = lark.ws.Client(config.app_id, config.app_secret, event_handler=event_handler)
    ws_client.start()
