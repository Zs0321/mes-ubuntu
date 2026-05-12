from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from qrmes_shared_core.config import config as shared_config
except Exception:  # pragma: no cover
    shared_config = None


@dataclass(frozen=True)
class KingdeeConfig:
    base_url: str
    db_id: str
    username: str
    app_id: str
    app_secret: str
    lcid: int
    timeout_seconds: int
    verify_ssl: bool

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
class AppConfig:
    project_root: Path
    static_dir: Path
    demo_data_path: Path
    kingdee: KingdeeConfig


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _shared(key: str, default=""):
    if shared_config is None:
        return default
    value = shared_config.get(key, default)
    if value is None:
        return default
    return value


def _int_value(*values, default: int) -> int:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return int(default)


def load_config(project_root: Path | None = None, static_dir: Path | None = None) -> AppConfig:
    root = (project_root or Path(__file__).resolve().parents[1]).resolve()
    static_root = (static_dir or root / "static" / "finance_demo").resolve()
    kingdee = KingdeeConfig(
        base_url=_env("KINGDEE_BASE_URL") or str(_shared("kingdee_base_url", "http://172.16.30.251/k3cloud") or "http://172.16.30.251/k3cloud").strip(),
        db_id=_env("KINGDEE_ACCT_ID") or _env("KINGDEE_DB_ID") or str(_shared("kingdee_acct_id", "") or "").strip(),
        username=_env("KINGDEE_USERNAME") or str(_shared("kingdee_username", "") or "").strip(),
        app_id=_env("KINGDEE_APP_ID") or str(_shared("kingdee_app_id", "") or "").strip(),
        app_secret=_env("KINGDEE_APP_SECRET") or str(_shared("kingdee_app_secret", "") or "").strip(),
        lcid=_int_value(_env("KINGDEE_LCID"), _shared("kingdee_lcid", 2052), default=2052),
        timeout_seconds=_int_value(
            _env("KINGDEE_TIMEOUT_SECS"),
            _env("KINGDEE_TIMEOUT_SECONDS"),
            _shared("kingdee_timeout_secs", 15),
            default=15,
        ),
        verify_ssl=str(_env("KINGDEE_VERIFY_SSL") or _shared("kingdee_verify_ssl", True)).strip().lower() not in {"0", "false", "no", "off"},
    )
    return AppConfig(
        project_root=root,
        static_dir=static_root,
        demo_data_path=static_root / "data" / "demo_data.json",
        kingdee=kingdee,
    )
