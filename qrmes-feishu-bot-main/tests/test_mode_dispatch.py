import unittest
from unittest.mock import patch

from feishu_mes_bot.main import run


class ModeDispatchTests(unittest.TestCase):
    @patch('feishu_mes_bot.main.run_callback_server')
    @patch('feishu_mes_bot.main.run_long_connection')
    def test_run_chooses_long_connection(self, mock_long, mock_callback):
        config = type('C', (), {'mode': 'long_connection'})()
        run(config)
        mock_long.assert_called_once_with(config)
        mock_callback.assert_not_called()


if __name__ == '__main__':
    unittest.main()
