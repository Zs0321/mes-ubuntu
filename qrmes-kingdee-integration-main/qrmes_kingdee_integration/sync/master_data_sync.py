from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qrmes_kingdee_integration.api_models import ApiResult
from qrmes_kingdee_integration.forms.master_data import MASTER_DATA_DEFINITIONS


def _cell(row: list[Any] | tuple[Any, ...], index: int, default: str = "") -> Any:
    if index >= len(row):
        return default
    value = row[index]
    return default if value is None else value


def _safe_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def build_master_data_business_key(row: list[Any] | tuple[Any, ...]) -> str:
    """优先 number，其次 id，最后用保守复合键避免空 key 覆盖。"""
    fid = _safe_text(_cell(row, 0))
    number = _safe_text(_cell(row, 1))
    name = _safe_text(_cell(row, 2))
    create_date = _safe_text(_cell(row, 4))
    if number:
        return number
    if fid:
        return fid
    return "|".join(part for part in [name, create_date] if part) or "unknown"


@dataclass
class MasterDataSyncService:
    store: Any
    forms_service: Any
    dataset: str
    push_client: Any | None = None

    @property
    def form_id(self) -> str:
        return MASTER_DATA_DEFINITIONS[self.dataset].form_id

    def sync_from_kingdee(self, limit: int = 100, keyword: str = "") -> ApiResult:
        rows = self.forms_service.query_master_data(self.dataset, keyword=keyword, limit=limit)
        synced = 0
        for row in rows:
            business_key = build_master_data_business_key(row)
            self.store.upsert_object(
                dataset=self.dataset,
                business_key=business_key,
                form_id=self.form_id,
                payload={
                    "id": _cell(row, 0),
                    "number": _cell(row, 1),
                    "name": _cell(row, 2),
                    "document_status": _cell(row, 3),
                    "created_at": _cell(row, 4),
                    "modified_at": _cell(row, 5),
                },
                source="kingdee",
            )
            synced += 1
        return ApiResult(ok=True, data={"dataset": self.dataset, "synced_count": synced})
