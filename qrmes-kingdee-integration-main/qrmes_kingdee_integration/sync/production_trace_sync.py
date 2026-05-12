from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qrmes_kingdee_integration.api_models import ApiResult
from qrmes_kingdee_integration.forms.production_trace import (
    OPERATION_PLANNING_FORM_ID,
    OPERATION_REPORT_FORM_ID,
    PRODUCTION_INSTOCK_FORM_ID,
    PRODUCTION_MATERIAL_LIST_FORM_ID,
)

SYNC_DATASET_PRODUCTION_MATERIAL_LIST = "production_material_list"
SYNC_DATASET_PRODUCTION_INSTOCK = "production_instock"
SYNC_DATASET_OPERATION_PLANNING = "operation_planning"
SYNC_DATASET_OPERATION_REPORT = "operation_report"


@dataclass
class ProductionMaterialListSyncService:
    store: Any
    forms_service: Any
    push_client: Any

    def sync_from_kingdee(self, limit: int = 100, keyword: str = "") -> ApiResult:
        rows = self.forms_service.query_production_material_lists(limit=limit, keyword=keyword)
        synced = 0
        for row in rows:
            bill_no = _clean(_value(row, 1))
            self.store.upsert_object(
                dataset=SYNC_DATASET_PRODUCTION_MATERIAL_LIST,
                business_key=_business_key(bill_no, _value(row, 0), _value(row, 3), _value(row, 11), _value(row, 12)),
                form_id=PRODUCTION_MATERIAL_LIST_FORM_ID,
                payload={
                    "id": _value(row, 0),
                    "bill_no": bill_no,
                    "document_status": _value(row, 2),
                    "material_code": _value(row, 3),
                    "material_name": _value(row, 4),
                    "material_spec": _value(row, 5),
                    "workshop_code": _value(row, 6),
                    "workshop_name": _value(row, 7),
                    "production_order_no": _value(row, 8),
                    "qty": _value(row, 9),
                    "unit_name": _value(row, 10),
                    "stock_code": _value(row, 11),
                    "lot_no": _value(row, 12),
                },
                source="kingdee",
            )
            synced += 1
        return ApiResult(ok=True, data={"dataset": SYNC_DATASET_PRODUCTION_MATERIAL_LIST, "synced_count": synced})

    def process_pending_changes(self, limit: int = 100) -> int:
        return 0


@dataclass
class ProductionInstockSyncService:
    store: Any
    forms_service: Any
    push_client: Any

    def sync_from_kingdee(self, limit: int = 100, keyword: str = "") -> ApiResult:
        rows = self.forms_service.query_production_instocks(limit=limit, keyword=keyword)
        synced = 0
        for row in rows:
            bill_no = _clean(_value(row, 1))
            self.store.upsert_object(
                dataset=SYNC_DATASET_PRODUCTION_INSTOCK,
                business_key=_business_key(bill_no, _value(row, 0), _value(row, 12), _value(row, 11), _value(row, 4), _value(row, 10)),
                form_id=PRODUCTION_INSTOCK_FORM_ID,
                payload={
                    "id": _value(row, 0),
                    "bill_no": bill_no,
                    "document_status": _value(row, 2),
                    "date": _value(row, 3),
                    "material_code": _value(row, 4),
                    "material_name": _value(row, 5),
                    "stock_org_code": _value(row, 6),
                    "production_order_no": _value(row, 7),
                    "qty": _value(row, 8),
                    "unit_name": _value(row, 9),
                    "stock_code": _value(row, 10),
                    "lot_no": _value(row, 11),
                    "serial_no": _value(row, 12),
                },
                source="kingdee",
            )
            synced += 1
        return ApiResult(ok=True, data={"dataset": SYNC_DATASET_PRODUCTION_INSTOCK, "synced_count": synced})

    def process_pending_changes(self, limit: int = 100) -> int:
        return 0


@dataclass
class OperationPlanningSyncService:
    store: Any
    forms_service: Any
    push_client: Any

    def sync_from_kingdee(self, limit: int = 100, keyword: str = "") -> ApiResult:
        rows = self.forms_service.query_operation_plannings(limit=limit, keyword=keyword)
        synced = 0
        for row in rows:
            bill_no = _clean(_value(row, 1))
            self.store.upsert_object(
                dataset=SYNC_DATASET_OPERATION_PLANNING,
                business_key=_business_key(bill_no, _value(row, 0), _value(row, 3), _value(row, 4), _value(row, 6)),
                form_id=OPERATION_PLANNING_FORM_ID,
                payload={
                    "id": _value(row, 0),
                    "bill_no": bill_no,
                    "document_status": _value(row, 2),
                    "production_order_no": _value(row, 3),
                    "operation_no": _value(row, 4),
                    "operation_description": _value(row, 5),
                    "product_code": _value(row, 6),
                    "qualified_qty": _value(row, 7),
                    "rework_qty": _value(row, 8),
                    "source_bill_no": _value(row, 9),
                },
                source="kingdee",
            )
            synced += 1
        return ApiResult(ok=True, data={"dataset": SYNC_DATASET_OPERATION_PLANNING, "synced_count": synced})

    def process_pending_changes(self, limit: int = 100) -> int:
        return 0


@dataclass
class OperationReportSyncService:
    store: Any
    forms_service: Any
    push_client: Any

    def sync_from_kingdee(self, limit: int = 100, keyword: str = "") -> ApiResult:
        rows = self.forms_service.query_operation_reports(limit=limit, keyword=keyword)
        synced = 0
        for row in rows:
            bill_no = _clean(_value(row, 1))
            self.store.upsert_object(
                dataset=SYNC_DATASET_OPERATION_REPORT,
                business_key=_business_key(bill_no, _value(row, 0), _value(row, 7), _value(row, 5), _value(row, 10)),
                form_id=OPERATION_REPORT_FORM_ID,
                payload={
                    "id": _value(row, 0),
                    "bill_no": bill_no,
                    "document_status": _value(row, 2),
                    "date": _value(row, 3),
                    "production_order_no": _value(row, 4),
                    "operation_no": _value(row, 5),
                    "operation_description": _value(row, 6),
                    "serial_no": _value(row, 7),
                    "finish_qty": _value(row, 8),
                    "rework_qty": _value(row, 9),
                    "source_bill_no": _value(row, 10),
                },
                source="kingdee",
            )
            synced += 1
        return ApiResult(ok=True, data={"dataset": SYNC_DATASET_OPERATION_REPORT, "synced_count": synced})

    def process_pending_changes(self, limit: int = 100) -> int:
        return 0


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def _business_key(primary: Any, fallback: Any, *parts: Any) -> str:
    base = _clean(primary)
    if base in (None, ""):
        base = _clean(fallback)
    clean_parts = [str(_clean(part)) for part in parts if _clean(part) not in (None, "")]
    if clean_parts:
        return "|".join([str(base), *clean_parts])
    return str(base)


def _value(row: list[Any], index: int, default: Any = "") -> Any:
    return row[index] if len(row) > index else default
