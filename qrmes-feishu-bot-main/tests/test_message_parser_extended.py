import unittest

from feishu_mes_bot.message_parser import parse_feishu_event


class MessageParserExtendedTests(unittest.TestCase):
    def test_parse_post_message_extracts_text(self):
        payload = {
            'header': {'event_type': 'im.message.receive_v1'},
            'event': {
                'sender': {'sender_id': {'open_id': 'ou_user'}},
                'message': {
                    'message_id': 'om_1',
                    'chat_id': 'oc_1',
                    'chat_type': 'group',
                    'message_type': 'post',
                    'content': '{"zh_cn":{"title":"排障","content":[[{"tag":"text","text":"@MES助手 APK更新失败"}]]}}',
                    'mentions': [{'key': '@MES助手', 'id': {'open_id': 'ou_bot'}}],
                },
            },
        }
        message = parse_feishu_event(payload, bot_open_id='ou_bot', bot_name='MES助手')
        self.assertEqual('APK更新失败', message.text)

    def test_parse_file_message_uses_placeholder(self):
        payload = {
            'header': {'event_type': 'im.message.receive_v1'},
            'event': {
                'sender': {'sender_id': {'open_id': 'ou_user'}},
                'message': {
                    'message_id': 'om_2',
                    'chat_id': 'oc_1',
                    'chat_type': 'group',
                    'message_type': 'file',
                    'content': '{"file_key":"file_xxx","file_name":"err.log"}',
                    'mentions': [{'key': '@MES助手', 'id': {'open_id': 'ou_bot'}}],
                },
            },
        }
        message = parse_feishu_event(payload, bot_open_id='ou_bot', bot_name='MES助手')
        self.assertEqual('[file消息]', message.text)


if __name__ == '__main__':
    unittest.main()
