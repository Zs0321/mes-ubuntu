import unittest

from feishu_mes_bot.long_connection import FeishuLongConnectionBot
from feishu_mes_bot.models import IncomingMessage


class FakeParser:
    def __call__(self, payload, bot_open_id='', bot_name=''):
        return IncomingMessage(
            text='web发布后打不开',
            sender_name='tester',
            sender_open_id='ou_user',
            chat_id='oc_1',
            chat_type='group',
            message_id='om_1',
            at_bot=True,
            receive_id='oc_1',
            receive_id_type='chat_id',
        )


class FakeEnrichment:
    def enrich(self, message):
        return message


class FakeRuntime:
    class Router:
        def route(self, message):
            return '诊断完成'
    router = Router()


class FakeSender:
    def __init__(self):
        self.calls = []

    def send_text(self, receive_id, receive_id_type, text):
        self.calls.append((receive_id, receive_id_type, text))
        return True


class LongConnectionTests(unittest.TestCase):
    def test_handle_event_routes_and_replies(self):
        sender = FakeSender()
        bot = FeishuLongConnectionBot(
            config=type('C', (), {'bot_open_id': 'ou_bot', 'bot_name': 'MES助手'})(),
            runtime=FakeRuntime(),
            sender=sender,
            enrichment_service=FakeEnrichment(),
            parser=FakeParser(),
        )
        bot.handle_event({'schema': '2.0'})
        self.assertEqual([('oc_1', 'chat_id', '诊断完成')], sender.calls)


if __name__ == '__main__':
    unittest.main()
