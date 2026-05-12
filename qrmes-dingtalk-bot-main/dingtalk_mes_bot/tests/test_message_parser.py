import unittest

from dingtalk_mes_bot.message_parser import parse_message


class MessageParserTests(unittest.TestCase):
    def test_parse_group_at(self):
        payload = {
            "text": {"content": "@bot query serial Genesis-LiGEx-FP15-A"},
            "conversationType": "2",
            "sessionWebhook": "http://example.com",
            "senderNick": "tester",
            "senderStaffId": "staff-001",
            "atUsers": [{"staffId": "bot"}],
        }
        msg = parse_message(payload, "bot")
        self.assertIsNotNone(msg)
        self.assertTrue(msg.at_bot)
        self.assertEqual("staff-001", msg.sender_staff_id)

    def test_parse_group_is_in_at_list(self):
        payload = {
            "text": {"content": "你好"},
            "conversationType": "2",
            "sessionWebhook": "http://example.com",
            "senderNick": "tester",
            "isInAtList": True,
        }
        msg = parse_message(payload, "bot")
        self.assertIsNotNone(msg)
        self.assertTrue(msg.at_bot)

    def test_parse_rich_text_message(self):
        payload = {
            "text": {"content": ""},
            "msgtype": "richText",
            "content": {"richText": [{"text": "@bot"}, {"text": " 为什么待复核"}]},
            "conversationType": "2",
            "sessionWebhook": "http://example.com",
            "senderNick": "tester",
            "isInAtList": True,
        }
        msg = parse_message(payload, "bot")
        self.assertIsNotNone(msg)
        self.assertEqual("richText", msg.message_type)
        self.assertIn("为什么待复核", msg.text)

    def test_parse_picture_message(self):
        payload = {
            "msgtype": "picture",
            "content": {"downloadCode": "img-code-001"},
            "conversationType": "2",
            "sessionWebhook": "http://example.com",
            "senderNick": "tester",
            "isInAtList": True,
        }
        msg = parse_message(payload, "bot")
        self.assertIsNotNone(msg)
        self.assertEqual("picture", msg.message_type)
        self.assertEqual(("img-code-001",), msg.image_download_codes)
        self.assertTrue(msg.at_bot)

    def test_parse_rich_text_picture_message_keeps_download_code(self):
        payload = {
            "text": {"content": ""},
            "msgtype": "richText",
            "content": {
                "richText": [
                    {"text": "@MES小客服"},
                    {"text": "这个图片有哪些工序"},
                    {"type": "picture", "pictureDownloadCode": "preview-code-001", "downloadCode": "img-code-002"},
                ]
            },
            "conversationType": "2",
            "sessionWebhook": "http://example.com",
            "senderNick": "tester",
            "isInAtList": True,
        }
        msg = parse_message(payload, "dinggunioxywb6gvu8gf")
        self.assertIsNotNone(msg)
        self.assertEqual("richText", msg.message_type)
        self.assertIn("这个图片有哪些工序", msg.text)
        self.assertEqual(("img-code-002",), msg.image_download_codes)
        self.assertTrue(msg.at_bot)

    def test_parse_file_message(self):
        payload = {
            "msgtype": "file",
            "conversationType": "2",
            "content": {"downloadCode": "file-code-001"},
            "senderNick": "tester",
            "sessionWebhook": "https://example.com",
            "isInAtList": True,
        }
        msg = parse_message(payload, "")
        self.assertIsNotNone(msg)
        self.assertEqual("[文件消息]", msg.text)
        self.assertEqual(("file-code-001",), msg.image_download_codes)


if __name__ == "__main__":
    unittest.main()
