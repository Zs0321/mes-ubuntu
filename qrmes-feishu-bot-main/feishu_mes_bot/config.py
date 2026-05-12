from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class BotConfig:
    mode: str
    host: str
    port: int
    log_level: str
    app_id: str
    app_secret: str
    verification_token: str
    encrypt_key: str
    bot_open_id: str
    bot_name: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout: float
    workspace_root: str
    resource_cache_dir: str
    hermes_base_url: str
    hermes_workspace: str


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def load_config() -> BotConfig:
    try:
        port = int(_env("FEISHU_BOT_PORT", "8898"))
    except ValueError:
        port = 8898
    try:
        llm_timeout = float(_env("FEISHU_BOT_LLM_TIMEOUT", "20"))
    except ValueError:
        llm_timeout = 20.0
    workspace_root = _env(
        "FEISHU_BOT_WORKSPACE_ROOT",
        "/Volumes/172.16.30.10/volume2/mes_ubuntu_split_result",
    )
    hermes_workspace = _env('FEISHU_BOT_HERMES_WORKSPACE', workspace_root)
    mode = _env('FEISHU_BOT_MODE', 'callback').lower()
    if mode not in ('callback', 'long_connection'):
        mode = 'callback'
    return BotConfig(
        mode=mode,
        host=_env("FEISHU_BOT_HOST", "0.0.0.0"),
        port=port,
        log_level=_env("FEISHU_BOT_LOG_LEVEL", "INFO"),
        app_id=_env("FEISHU_BOT_APP_ID"),
        app_secret=_env("FEISHU_BOT_APP_SECRET"),
        verification_token=_env("FEISHU_BOT_VERIFICATION_TOKEN"),
        encrypt_key=_env("FEISHU_BOT_ENCRYPT_KEY"),
        bot_open_id=_env("FEISHU_BOT_OPEN_ID"),
        bot_name=_env("FEISHU_BOT_NAME", "MES助手"),
        llm_base_url=_env("FEISHU_BOT_LLM_BASE_URL"),
        llm_api_key=_env("FEISHU_BOT_LLM_API_KEY"),
        llm_model=_env("FEISHU_BOT_LLM_MODEL", "qwen3.5-35b-a3b"),
        llm_timeout=llm_timeout,
        workspace_root=workspace_root,
        resource_cache_dir=_env("FEISHU_BOT_RESOURCE_CACHE_DIR", os.path.join(workspace_root, 'qrmes-feishu-bot', 'runtime_cache')),
        hermes_base_url=_env('FEISHU_BOT_HERMES_BASE_URL', 'http://127.0.0.1:8787'),
        hermes_workspace=hermes_workspace,
    )
