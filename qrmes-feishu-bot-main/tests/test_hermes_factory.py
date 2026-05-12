import unittest

from feishu_mes_bot.config import BotConfig
from feishu_mes_bot.service_factory import create_router


class HermesFactoryTests(unittest.TestCase):
    def test_create_router_prefers_hermes_for_summary_and_fallback(self):
        config = BotConfig(
            mode='callback',
            host='0.0.0.0', port=8898, log_level='INFO', app_id='', app_secret='', verification_token='',
            encrypt_key='', bot_open_id='', bot_name='MES助手',
            llm_base_url='', llm_api_key='', llm_model='gpt-5.4', llm_timeout=20.0,
            workspace_root='/tmp', resource_cache_dir='/tmp/cache',
            hermes_base_url='http://127.0.0.1:8787', hermes_workspace='/tmp'
        )
        router = create_router(config)
        self.assertEqual('HermesApiService', router.llm_answer_service.client.__class__.__name__)
        self.assertEqual('HermesApiService', router.diagnosis_service.summary_service.client.__class__.__name__)


if __name__ == '__main__':
    unittest.main()
