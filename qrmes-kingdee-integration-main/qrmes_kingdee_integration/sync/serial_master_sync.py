from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qrmes_kingdee_integration.api_models import ApiResult
from qrmes_kingdee_integration.forms.batch_trace import SERIAL_MASTER_FORM_ID

SYNC_DATASET_SERIAL_MASTER = "serial_master"


@dataclass
class SerialMasterSyncService:
    store: Any
    forms_service: Any
    push_client: Any

    def sync_from_kingdee(self, limit: int = 100, keyword: str = "") -> ApiResult:
        rows = self.forms_service.query_serial_master(keyword=keyword, limit=limit)
        synced = 0
        for row in rows:
            serial_no = row[0] if len(row) > 0 else ''
            material_code = row[1] if len(row) > 1 else ''
            stock_code = row[2] if len(row) > 2 else ''
            document_status = row[3] if len(row) > 3 else ''
            created_at = row[4] if len(row) > 4 else ''
            business_key = serial_no or f"{material_code}|{stock_code}|{created_at}"
            self.store.upsert_object(
                dataset=SYNC_DATASET_SERIAL_MASTER,
                business_key=business_key,
                form_id=SERIAL_MASTER_FORM_ID,
                payload={
                    'serial_no': serial_no,
                    'material_code': material_code,
                    'stock_code': stock_code,
                    'document_status': document_status,
                    'created_at': created_at,
                },
                source='kingdee',
            )
            synced += 1
        return ApiResult(ok=True, data={'dataset': SYNC_DATASET_SERIAL_MASTER, 'synced_count': synced})

    def process_pending_changes(self, limit: int = 100) -> int:
        return 0
