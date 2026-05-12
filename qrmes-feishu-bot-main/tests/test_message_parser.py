import unittest

from feishu_mes_bot.message_parser import parse_feishu_event


class MessageParserTests(unittest.TestCase):
    def test_parse_group_mention_message(self):
        payload = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_user_1"},
                    "sender_type": "user",
                },
                "message": {
                    "message_id": "om_123",
                    "chat_id": "oc_123",
                    "chat_type": "group",
                    "message_type": "text",
                    "content": '{"text":"@MES助手 web发布后打不开"}',
                    "mentions": [
                        {
                            "key": "@MES助手",
                            "id": {"open_id": "ou_bot_1"},
                            "name": "MES助手",
                        }
                    ],
                },
            },
        }

        message = parse_feishu_event(payload, bot_open_id="ou_bot_1")
        self.assertIsNotNone(message)
        self.assertTrue(message.at_bot)
        self.assertEqual("web发布后打不开", message.text)
        self.assertEqual("group", message.chat_type)
        self.assertEqual("chat_id", message.receive_id_type)
        self.assertEqual("oc_123", message.receive_id)

    def test_parse_p2p_text_message_without_mention(self):
        payload = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_user_2"},
                    "sender_type": "user",
                },
                "message": {
                    "message_id": "om_456",
                    "chat_id": "oc_p2p",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "content": '{"text":"APK更新失败"}',
                },
            },
        }

        message = parse_feishu_event(payload, bot_open_id="ou_bot_1")
        self.assertIsNotNone(message)
        self.assertTrue(message.at_bot)
        self.assertEqual("APK更新失败", message.text)
        self.assertEqual("open_id", message.receive_id_type)
        self.assertEqual("ou_user_2", message.receive_id)

    def test_non_text_message_without_text_returns_placeholder(self):
        payload = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_user_3"},
                },
                "message": {
                    "message_id": "om_789",
                    "chat_id": "oc_789",
                    "chat_type": "group",
                    "message_type": "image",
                    "content": '{}',
                    "mentions": [{"key": "@MES助手", "id": {"open_id": "ou_bot_1"}}],
                },
            },
        }

        message = parse_feishu_event(payload, bot_open_id="ou_bot_1")
        self.assertIsNotNone(message)
        self.assertEqual("[image消息]", message.text)


if __name__ == "__main__":
    unittest.main()
