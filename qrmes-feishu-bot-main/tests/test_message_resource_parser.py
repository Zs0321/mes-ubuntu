import unittest

from feishu_mes_bot.message_parser import parse_feishu_event


class MessageResourceParserTests(unittest.TestCase):
    def test_parse_image_message_extracts_image_key(self):
        payload = {
            'header': {'event_type': 'im.message.receive_v1'},
            'event': {
                'sender': {'sender_id': {'open_id': 'ou_user'}},
                'message': {
                    'message_id': 'om_img',
                    'chat_id': 'oc_1',
                    'chat_type': 'group',
                    'message_type': 'image',
                    'content': '{"image_key":"img_xxx"}',
                    'mentions': [{'key': '@MES助手', 'id': {'open_id': 'ou_bot'}}],
                },
            },
        }
        message = parse_feishu_event(payload, bot_open_id='ou_bot', bot_name='MES助手')
        self.assertEqual('img_xxx', message.resource_key)
        self.assertEqual('image', message.resource_type)

    def test_parse_file_message_extracts_file_key_and_name(self):
        payload = {
            'header': {'event_type': 'im.message.receive_v1'},
            'event': {
                'sender': {'sender_id': {'open_id': 'ou_user'}},
                'message': {
                    'message_id': 'om_file',
                    'chat_id': 'oc_1',
                    'chat_type': 'group',
                    'message_type': 'file',
                    'content': '{"file_key":"file_xxx","file_name":"error.log"}',
                    'mentions': [{'key': '@MES助手', 'id': {'open_id': 'ou_bot'}}],
                },
            },
        }
        message = parse_feishu_event(payload, bot_open_id='ou_bot', bot_name='MES助手')
        self.assertEqual('file_xxx', message.resource_key)
        self.assertEqual('file', message.resource_type)
        self.assertEqual('error.log', message.resource_name)


if __name__ == '__main__':
    unittest.main()
