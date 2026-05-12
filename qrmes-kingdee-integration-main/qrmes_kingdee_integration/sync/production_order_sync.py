from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qrmes_kingdee_integration.api_models import ApiResult
from qrmes_kingdee_integration.forms.production_order import PRODUCTION_ORDER_FORM_ID

SYNC_DATASET_PRODUCTION_ORDER = "production_order"


@dataclass
class ProductionOrderSyncService:
    store: Any
    forms_service: Any
    push_client: Any

    def sync_from_kingdee(self, limit: int = 100, filter_string: str = "") -> ApiResult:
        rows = self.forms_service.query_orders(limit=limit, filter_string=filter_string)
        synced = 0
        for row in rows:
            business_key = str(row[0])
            self.store.upsert_object(
                dataset=SYNC_DATASET_PRODUCTION_ORDER,
                business_key=business_key,
                form_id=PRODUCTION_ORDER_FORM_ID,
                payload={
                    'bill_no': row[0],
                    'document_status': row[1] if len(row) > 1 else '',
                    'material_code': row[2] if len(row) > 2 else '',
                    'material_name': row[3] if len(row) > 3 else '',
                    'qty': row[4] if len(row) > 4 else 0,
                },
                source='kingdee',
            )
            synced += 1
        return ApiResult(ok=True, data={'dataset': SYNC_DATASET_PRODUCTION_ORDER, 'synced_count': synced})

    def apply_local_change(self, business_key: str, payload: dict[str, Any]) -> ApiResult:
        queue_id = self.store.enqueue_change(
            dataset=SYNC_DATASET_PRODUCTION_ORDER,
            business_key=business_key,
            form_id=PRODUCTION_ORDER_FORM_ID,
            action='save',
            payload=payload,
        )
        remote_payload = self.push_client.save(PRODUCTION_ORDER_FORM_ID, payload)
        self.store.mark_change_done(queue_id, remote_payload=remote_payload)
        self.store.upsert_object(
            dataset=SYNC_DATASET_PRODUCTION_ORDER,
            business_key=business_key,
            form_id=PRODUCTION_ORDER_FORM_ID,
            payload=payload,
            source='local',
        )
        return ApiResult(ok=True, data={'dataset': SYNC_DATASET_PRODUCTION_ORDER, 'business_key': business_key, 'queue_id': queue_id})

    def process_pending_changes(self, limit: int = 100) -> int:
        processed = 0
        for row in self.store.list_pending_changes(limit=limit):
            if row['dataset'] != SYNC_DATASET_PRODUCTION_ORDER or row['action'] != 'save':
                continue
            remote_payload = self.push_client.save(PRODUCTION_ORDER_FORM_ID, row['payload'])
            self.store.mark_change_done(row['id'], remote_payload=remote_payload)
            self.store.upsert_object(dataset=SYNC_DATASET_PRODUCTION_ORDER, business_key=row['business_key'], form_id=PRODUCTION_ORDER_FORM_ID, payload=row['payload'], source='local')
            processed += 1
        return processed
