import importlib
import json
from pathlib import Path
from typing import Optional


REPO_ROOT = Path("/Volumes/172.16.30.10/volume2/mes_ubuntu_split_result/qrmes-finance-service")
CONFIG_FILE = REPO_ROOT / "qrmes_shared_core" / "webdav_config.json"


def _write_config(payload: dict) -> Optional[str]:
    original_text = CONFIG_FILE.read_text(encoding="utf-8") if CONFIG_FILE.exists() else None
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return original_text


def _restore_config(original_text: Optional[str]) -> None:
    if original_text is None:
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
        return
    CONFIG_FILE.write_text(original_text, encoding="utf-8")


def test_finance_runtime_loads_kingdee_and_ai_route_settings_from_webdav_config(monkeypatch):
    original_text = _write_config(
        {
            "kingdee_base_url": "http://kingdee-from-config.example/k3cloud",
            "kingdee_acct_id": "acct-from-config",
            "kingdee_username": "finance-user",
            "kingdee_app_id": "finance-app-id",
            "kingdee_app_secret": "finance-app-secret",
            "kingdee_lcid": 2052,
            "kingdee_timeout_secs": 27,
            "pricing_ai_api_key": "cfg-hermes-key",
            "pricing_ai_base_url": "http://127.0.0.1:8899/openai/v1",
            "pricing_ai_model": "gpt-5.4",
            "qwen_api_key": "cfg-qwen-key",
            "qwen_base_url": "https://dashscope.example/v1",
            "pricing_qwen_model": "pricing-model-from-config",
            "pricing_qwen_timeout": 120,
            "pricing_qwen_timeout_retry": 2,
            "pricing_ai_max_workers": 4,
        }
    )

    for key in (
        "KINGDEE_BASE_URL",
        "KINGDEE_DB_ID",
        "KINGDEE_ACCT_ID",
        "KINGDEE_USERNAME",
        "KINGDEE_APP_ID",
        "KINGDEE_APP_SECRET",
        "KINGDEE_LCID",
        "KINGDEE_TIMEOUT_SECONDS",
        "PRICING_AI_API_KEY",
        "PRICING_AI_BASE_URL",
        "PRICING_AI_MODEL",
        "PRICING_QWEN_MODEL",
        "QWEN_MODEL",
        "QWEN_API_KEY",
        "DASHSCOPE_API_KEY",
        "QWEN_BASE_URL",
        "PRICING_QWEN_TIMEOUT",
        "PRICING_QWEN_TIMEOUT_RETRY",
        "PRICING_AI_MAX_WORKERS",
    ):
        monkeypatch.delenv(key, raising=False)

    try:
        import qrmes_shared_core.config as shared_config_module
        shared_config_module.Config._instance = None
        importlib.reload(shared_config_module)

        import app_web.backend.config as backend_config_module
        backend_config_module = importlib.reload(backend_config_module)

        import app_web.backend.services.ai_route_quote_service as ai_route_module
        ai_route_module = importlib.reload(ai_route_module)

        loaded = backend_config_module.load_config()
        service = ai_route_module.AIRouteQuoteService()

        assert loaded.kingdee.base_url == "http://kingdee-from-config.example/k3cloud"
        assert loaded.kingdee.db_id == "acct-from-config"
        assert loaded.kingdee.username == "finance-user"
        assert loaded.kingdee.app_id == "finance-app-id"
        assert loaded.kingdee.app_secret == "finance-app-secret"
        assert loaded.kingdee.timeout_seconds == 27

        assert service.api_key == "cfg-hermes-key"
        assert service.base_url == "http://127.0.0.1:8899/openai/v1"
        assert service.model == "gpt-5.4"
        assert service.timeout == 120
        assert service.timeout_retry_count == 2
        assert service.max_workers == 4
    finally:
        _restore_config(original_text)
        import qrmes_shared_core.config as shared_config_module
        shared_config_module.Config._instance = None
        importlib.reload(shared_config_module)
        import app_web.backend.config as backend_config_module
        importlib.reload(backend_config_module)
        import app_web.backend.services.ai_route_quote_service as ai_route_module
        importlib.reload(ai_route_module)
