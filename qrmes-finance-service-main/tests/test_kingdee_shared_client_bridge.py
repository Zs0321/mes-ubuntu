from backend.kingdee.client import KingdeeClient
from qrmes_kingdee_integration.config import KingdeeRuntimeConfig


def test_finance_kingdee_client_exposes_shared_save_path():
    assert KingdeeClient.SAVE_PATH.endswith('DynamicFormService.Save.common.kdsvc')


def test_finance_kingdee_client_defaults_root_base_url_to_k3cloud_prefix():
    client = KingdeeClient(
        KingdeeRuntimeConfig(
            base_url='http://kingdee.example.com',
            db_id='db',
            username='user',
            app_id='app',
            app_secret='secret',
        )
    )
    assert client._build_url(KingdeeClient.LOGIN_PATH) == 'http://kingdee.example.com/k3cloud/Kingdee.BOS.WebApi.ServicesStub.AuthService.LoginBySign.common.kdsvc'
