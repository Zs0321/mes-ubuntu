from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import requests

from qrmes_kingdee_integration.api_models import ApiResult
from qrmes_kingdee_integration.auth.signer import generate_signature
from qrmes_kingdee_integration.config import KingdeeRuntimeConfig


class KingdeeConfigError(RuntimeError):
    pass


class KingdeeApiError(RuntimeError):
    pass


@dataclass
class KingdeeQuery:
    form_id: str
    field_keys: str
    filter_string: str = ""
    order_string: str = ""
    top_row_count: int = 0
    start_row: int = 0
    limit: int = 2000
    sub_system_id: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "FormId": self.form_id,
            "FieldKeys": self.field_keys,
            "FilterString": self.filter_string,
            "OrderString": self.order_string,
            "TopRowCount": self.top_row_count,
            "StartRow": self.start_row,
            "Limit": self.limit,
            "SubSystemId": self.sub_system_id,
        }


def parse_response_status(payload: dict[str, Any]) -> ApiResult:
    response_status = (payload or {}).get("ResponseStatus") or {}
    is_success = bool(response_status.get("IsSuccess"))
    errors = [
        {
            "field": item.get("FieldName", ""),
            "message": item.get("Message", ""),
        }
        for item in (response_status.get("Errors") or [])
    ]
    return ApiResult(
        ok=is_success,
        data={
            "payload": (payload or {}).get("Result"),
            "errors": errors,
            "msg_code": response_status.get("MsgCode", ""),
            "raw": payload,
        },
    )


class KingdeeClient:
    LOGIN_PATH = "Kingdee.BOS.WebApi.ServicesStub.AuthService.LoginBySign.common.kdsvc"
    BILL_QUERY_PATH = "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"
    VIEW_PATH = "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.View.common.kdsvc"
    SAVE_PATH = "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Save.common.kdsvc"

    def __init__(self, config: KingdeeRuntimeConfig, session: requests.Session | Any | None = None):
        self.config = config
        self.session = session or requests.Session()
        self._logged_in = False

    def ensure_ready(self) -> None:
        if self.config.is_ready:
            return
        missing = ", ".join(self.config.public_summary["missing"])
        raise KingdeeConfigError(f"Missing Kingdee config: {missing}")

    def build_login_payload(self, timestamp: int) -> dict[str, Any]:
        self.ensure_ready()
        return {
            "acctID": self.config.db_id,
            "username": self.config.username,
            "appId": self.config.app_id,
            "timestamp": timestamp,
            "sign": generate_signature(
                db_id=self.config.db_id,
                username=self.config.username,
                app_id=self.config.app_id,
                app_secret=self.config.app_secret,
                timestamp=timestamp,
            ),
            "lcid": self.config.lcid,
        }

    def login(self) -> dict[str, Any]:
        payload = self.build_login_payload(timestamp=int(time.time()))
        response = self._post(self.LOGIN_PATH, payload)
        result_type = int(response.get("LoginResultType", -1))
        if result_type not in (1, -5):
            raise KingdeeApiError(f"Kingdee login failed with LoginResultType={result_type}")
        self._logged_in = True
        return response

    def execute_bill_query(self, query: KingdeeQuery):
        self._login_if_needed()
        return self._post(self.BILL_QUERY_PATH, {"data": json.dumps(query.to_payload(), ensure_ascii=False)})

    def view(self, form_id: str, data: dict[str, Any]):
        self._login_if_needed()
        return self._post(self.VIEW_PATH, {"formid": form_id, "data": json.dumps(data, ensure_ascii=False)})

    def save(self, form_id: str, data: dict[str, Any]):
        self._login_if_needed()
        return self._post(self.SAVE_PATH, {"formid": form_id, "data": json.dumps(data, ensure_ascii=False)})

    def _login_if_needed(self) -> None:
        if not self._logged_in:
            self.login()

    def _post(self, path: str, payload: dict[str, Any]):
        response = self.session.post(
            self._build_url(path),
            json=payload,
            timeout=self.config.timeout_seconds,
            verify=self.config.verify_ssl,
        )
        try:
            return response.json()
        except Exception as exc:  # pragma: no cover
            raise KingdeeApiError(f"Invalid JSON response from Kingdee: {exc}") from exc

    def _build_url(self, path: str) -> str:
        base = self.config.base_url.rstrip("/")
        lower_base = base.lower()
        if "/k3cloud" not in lower_base:
            base = f"{base}/k3cloud"
        return base.rstrip("/") + "/" + path.lstrip("/")
