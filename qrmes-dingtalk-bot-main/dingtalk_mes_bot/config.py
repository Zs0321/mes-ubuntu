from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class BotConfig:
    mode: str
    host: str
    port: int
    log_level: str
    app_key: str
    app_secret: str
    client_id: str
    client_secret: str
    robot_code: str
    callback_token: str
    callback_aes_key: str
    callback_receive_id: str
    mes_api_base_url: str
    llm_base_url: str
    text_model: str
    vision_model: str
    llm_api_key: str
    llm_timeout: float
    project_config_db_path: str
    web_users_db_path: str
    user_aliases_path: str
    unified_db_path: str
    doc_workspace_id: str
    doc_parent_node_id: str
    doc_operator_id: str
    doc_state_path: str
    dingtalk_api_base_url: str
    hermes_base_url: str
    hermes_workspace: str
    hermes_model: str


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def load_config() -> BotConfig:
    mode = _env("DINGTALK_BOT_MODE", "stream").lower()
    if mode not in {"stream", "http"}:
        mode = "stream"

    try:
        port = int(_env("DINGTALK_BOT_PORT", "8899"))
    except ValueError:
        port = 8899

    try:
        llm_timeout = float(_env("DINGTALK_BOT_LLM_TIMEOUT", "20"))
    except ValueError:
        llm_timeout = 20.0

    client_id = _env("DINGTALK_BOT_CLIENT_ID") or _env("DINGTALK_BOT_APP_KEY")
    client_secret = _env("DINGTALK_BOT_CLIENT_SECRET") or _env("DINGTALK_BOT_APP_SECRET")

    return BotConfig(
        mode=mode,
        host=_env("DINGTALK_BOT_HOST", "0.0.0.0"),
        port=port,
        log_level=_env("DINGTALK_BOT_LOG_LEVEL", "INFO"),
        app_key=_env("DINGTALK_BOT_APP_KEY"),
        app_secret=_env("DINGTALK_BOT_APP_SECRET"),
        client_id=client_id,
        client_secret=client_secret,
        robot_code=_env("DINGTALK_BOT_ROBOT_CODE"),
        callback_token=_env("DINGTALK_BOT_CALLBACK_TOKEN"),
        callback_aes_key=_env("DINGTALK_BOT_CALLBACK_AES_KEY"),
        callback_receive_id=_env("DINGTALK_BOT_CALLBACK_RECEIVE_ID") or client_id,
        mes_api_base_url=_env("MES_BOT_API_BASE", "http://127.0.0.1:8891"),
        llm_base_url=_env("DINGTALK_BOT_LLM_BASE_URL", "http://172.16.20.201:1234/v1"),
        text_model=_env("DINGTALK_BOT_TEXT_MODEL", _env("DINGTALK_BOT_LLM_MODEL", "qwen3.5-35b-a3b")),
        vision_model=_env("DINGTALK_BOT_VISION_MODEL", "qwen/qwen3-vl-30b"),
        llm_api_key=_env("DINGTALK_BOT_LLM_API_KEY"),
        llm_timeout=llm_timeout,
        project_config_db_path=_env("DINGTALK_BOT_PROJECT_CONFIG_DB_PATH", "/volume2/MES/QRMES/projects/project_configs.db"),
        web_users_db_path=_env("DINGTALK_BOT_WEB_USERS_DB_PATH", "/volume2/MES/QRMES/web_users.db"),
        user_aliases_path=_env("DINGTALK_BOT_USER_ALIASES_PATH", "/volume2/qrmes-v3.0/qrmes-dingtalk-bot/dingtalk_mes_bot/mes_user_aliases.json"),
        unified_db_path=_env("DINGTALK_BOT_UNIFIED_DB_PATH", "/volume2/MES/QRMES/unified.db"),
        doc_workspace_id=_env("DINGTALK_BOT_DOC_WORKSPACE_ID"),
        doc_parent_node_id=_env("DINGTALK_BOT_DOC_PARENT_NODE_ID"),
        doc_operator_id=_env("DINGTALK_BOT_DOC_OPERATOR_ID"),
        doc_state_path=_env("DINGTALK_BOT_DOC_STATE_PATH", "/volume2/qrmes-v3.0/qrmes-dingtalk-bot/dingtalk_mes_bot/cache/daily_docs.json"),
        dingtalk_api_base_url=_env("DINGTALK_BOT_API_BASE_URL", "https://api.dingtalk.com"),
        hermes_base_url=_env("DINGTALK_BOT_HERMES_BASE_URL", "http://127.0.0.1:8787"),
        hermes_workspace=_env("DINGTALK_BOT_HERMES_WORKSPACE", "/Volumes/172.16.30.10/volume2/qrmes-v3.0/qrmes-dingtalk-bot"),
        hermes_model=_env("DINGTALK_BOT_HERMES_MODEL", "gpt-5.5"),
    )
