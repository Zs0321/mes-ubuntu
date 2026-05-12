from __future__ import annotations

import copy
import json
from pathlib import Path

from backend.config import AppConfig


class DemoDataService:
    def __init__(self, config: AppConfig):
        self.config = config

    def load(self) -> dict:
        with self.config.demo_data_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return copy.deepcopy(data)

    def build_payload(self, kingdee_status: dict | None = None) -> dict:
        payload = self.load()
        payload.setdefault("backend", {})
        payload["backend"].update({
            "api_enabled": True,
            "kingdee_status": kingdee_status or {},
        })
        return payload
