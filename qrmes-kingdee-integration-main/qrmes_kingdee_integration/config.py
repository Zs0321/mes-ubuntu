from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KingdeeRuntimeConfig:
    base_url: str
    db_id: str
    username: str
    app_id: str
    app_secret: str
    lcid: int = 2052
    timeout_seconds: int = 15
    verify_ssl: bool = True

    @property
    def is_ready(self) -> bool:
        return all([
            self.base_url,
            self.db_id,
            self.username,
            self.app_id,
            self.app_secret,
        ])

    @property
    def public_summary(self) -> dict:
        return {
            "base_url": self.base_url,
            "db_id": self.db_id,
            "username": self.username,
            "app_id": self.app_id,
            "lcid": self.lcid,
            "verify_ssl": self.verify_ssl,
            "configured": self.is_ready,
            "missing": [
                name for name, value in [
                    ("KINGDEE_BASE_URL", self.base_url),
                    ("KINGDEE_DB_ID", self.db_id),
                    ("KINGDEE_USERNAME", self.username),
                    ("KINGDEE_APP_ID", self.app_id),
                    ("KINGDEE_APP_SECRET", self.app_secret),
                ] if not value
            ],
        }


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    docs_dir: Path
    runtime_dir: Path
    local_db_path: Path
    kingdee: KingdeeRuntimeConfig


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int_value(*values: object, default: int) -> int:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            continue
    return int(default)


def _bool_value(value: object, default: bool = True) -> bool:
    if value in (None, ""):
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _load_json_config() -> dict[str, object]:
    candidates = []
    env_path = _env("QRMES_KINGDEE_CONFIG_JSON")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.extend([
        Path('/Volumes/172.16.30.10/volume2/qrmes-v3.0/qrmes-web-core/app_web/webdav_config.json'),
        Path('/volume2/qrmes-v3.0/qrmes-web-core/app_web/webdav_config.json'),
        Path('/volume2/qrmes/app_web/webdav_config.json'),
    ])
    for path in candidates:
        if not path.exists():
            continue
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
    return {}


def _cfg_value(data: dict[str, object], key: str, default: object = "") -> object:
    value = data.get(key, default)
    if value is None:
        return default
    return value


def load_settings(project_root: Path | None = None) -> AppSettings:
    root = (project_root or Path(__file__).resolve().parents[1]).resolve()
    cfg = _load_json_config()
    default_db_path = '/volume2/MES/QRMES/kingdee_sync.db' if Path('/volume2/MES/QRMES').exists() else '/Volumes/172.16.30.10/volume2/MES/QRMES/kingdee_sync.db'
    local_db_path = Path(_env("QRMES_KINGDEE_DB_PATH") or str(_cfg_value(cfg, 'qrmes_kingdee_db_path', default_db_path))).expanduser()
    return AppSettings(
        project_root=root,
        docs_dir=root / "docs",
        runtime_dir=root / ".runtime",
        local_db_path=local_db_path,
        kingdee=KingdeeRuntimeConfig(
            base_url=_env("KINGDEE_BASE_URL") or str(_cfg_value(cfg, 'kingdee_base_url', '')),
            db_id=_env("KINGDEE_DB_ID") or _env("KINGDEE_ACCT_ID") or str(_cfg_value(cfg, 'kingdee_acct_id', '')),
            username=_env("KINGDEE_USERNAME") or str(_cfg_value(cfg, 'kingdee_username', '')),
            app_id=_env("KINGDEE_APP_ID") or str(_cfg_value(cfg, 'kingdee_app_id', '')),
            app_secret=_env("KINGDEE_APP_SECRET") or str(_cfg_value(cfg, 'kingdee_app_secret', '')),
            lcid=_int_value(_env("KINGDEE_LCID"), _cfg_value(cfg, 'kingdee_lcid', 2052), default=2052),
            timeout_seconds=_int_value(_env("KINGDEE_TIMEOUT_SECS"), _env("KINGDEE_TIMEOUT_SECONDS"), _cfg_value(cfg, 'kingdee_timeout_secs', 15), default=15),
            verify_ssl=_bool_value(_env("KINGDEE_VERIFY_SSL") if _env("KINGDEE_VERIFY_SSL") else _cfg_value(cfg, 'kingdee_verify_ssl', True), default=True),
        ),
    )
