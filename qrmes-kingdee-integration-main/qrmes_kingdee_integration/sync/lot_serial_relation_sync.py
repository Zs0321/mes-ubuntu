from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qrmes_kingdee_integration.api_models import ApiResult
from qrmes_kingdee_integration.forms.batch_trace import LOT_SERIAL_RELATION_FORM_ID

SYNC_DATASET_LOT_SERIAL_RELATION = "lot_serial_relation"


@dataclass
class LotSerialRelationSyncService:
    store: Any
    forms_service: Any
    push_client: Any

    def sync_from_kingdee(self, limit: int = 100, keyword: str = "") -> ApiResult:
        rows = self.forms_service.query_lot_serial_relation(keyword=keyword, limit=limit)
        synced = 0
        for row in rows:
            relation_id = str(row[0]) if len(row) > 0 else ''
            lot_no = row[1] if len(row) > 1 else ''
            serial_no = row[2] if len(row) > 2 else ''
            material_code = row[3] if len(row) > 3 else ''
            document_status = row[4] if len(row) > 4 else ''
            business_key = '|'.join(part for part in [relation_id, lot_no, serial_no] if part)
            self.store.upsert_object(
                dataset=SYNC_DATASET_LOT_SERIAL_RELATION,
                business_key=business_key,
                form_id=LOT_SERIAL_RELATION_FORM_ID,
                payload={
                    'relation_id': relation_id,
                    'lot_no': lot_no,
                    'serial_no': serial_no,
                    'material_code': material_code,
                    'document_status': document_status,
                },
                source='kingdee',
            )
            synced += 1
        return ApiResult(ok=True, data={'dataset': SYNC_DATASET_LOT_SERIAL_RELATION, 'synced_count': synced})

    def process_pending_changes(self, limit: int = 100) -> int:
        return 0
