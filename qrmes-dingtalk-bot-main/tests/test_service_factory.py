import unittest

from dingtalk_mes_bot.config import BotConfig
from dingtalk_mes_bot.service_factory import create_router


class ServiceFactoryTests(unittest.TestCase):
    def test_create_router_prefers_hermes_when_configured(self):
        config = BotConfig(
            mode='stream', host='0.0.0.0', port=8899, log_level='INFO',
            app_key='', app_secret='', client_id='', client_secret='', robot_code='',
            callback_token='', callback_aes_key='', callback_receive_id='',
            mes_api_base_url='http://127.0.0.1:8891', llm_base_url='', text_model='gpt-5.5',
            vision_model='qwen/qwen3-vl-30b', llm_api_key='', llm_timeout=20.0,
            project_config_db_path='/tmp/projects.db', web_users_db_path='/tmp/web_users.db',
            user_aliases_path='/tmp/aliases.json', unified_db_path='/tmp/unified.db',
            doc_workspace_id='', doc_parent_node_id='', doc_operator_id='', doc_state_path='/tmp/state.json',
            dingtalk_api_base_url='https://api.dingtalk.com',
            hermes_base_url='http://127.0.0.1:8787', hermes_workspace='/tmp', hermes_model='gpt-5.5'
        )
        router = create_router(config)
        self.assertEqual('HermesApiService', router.llm_answer_service.client.__class__.__name__)
        self.assertEqual('IssueDiagnosisService', router.diagnosis_service.__class__.__name__)
        self.assertEqual('gpt-5.5', router.llm_answer_service.model)


if __name__ == '__main__':
    unittest.main()
