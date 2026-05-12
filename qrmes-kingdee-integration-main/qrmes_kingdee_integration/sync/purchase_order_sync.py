from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qrmes_kingdee_integration.api_models import ApiResult
from qrmes_kingdee_integration.forms.purchase_order import PURCHASE_ORDER_FORM_ID

SYNC_DATASET_PURCHASE_ORDER = "purchase_order"


@dataclass
class PurchaseOrderSyncService:
    store: Any
    forms_service: Any
    push_client: Any

    def sync_from_kingdee(self, limit: int = 100, keyword: str = '') -> ApiResult:
        rows = self.forms_service.query_purchase_orders(keyword=keyword, limit=limit)
        synced = 0
        for row in rows:
            business_key = str(row[0])
            self.store.upsert_object(
                dataset=SYNC_DATASET_PURCHASE_ORDER,
                business_key=business_key,
                form_id=PURCHASE_ORDER_FORM_ID,
                payload={
                    'bill_no': row[0],
                    'date': row[1] if len(row) > 1 else '',
                    'supplier_name': row[2] if len(row) > 2 else '',
                },
                source='kingdee',
            )
            synced += 1
        return ApiResult(ok=True, data={'dataset': SYNC_DATASET_PURCHASE_ORDER, 'synced_count': synced})

    def apply_local_change(self, business_key: str, payload: dict[str, Any]) -> ApiResult:
        queue_id = self.store.enqueue_change(dataset=SYNC_DATASET_PURCHASE_ORDER, business_key=business_key, form_id=PURCHASE_ORDER_FORM_ID, action='save', payload=payload)
        remote_payload = self.push_client.save(PURCHASE_ORDER_FORM_ID, payload)
        self.store.mark_change_done(queue_id, remote_payload=remote_payload)
        self.store.upsert_object(dataset=SYNC_DATASET_PURCHASE_ORDER, business_key=business_key, form_id=PURCHASE_ORDER_FORM_ID, payload=payload, source='local')
        return ApiResult(ok=True, data={'dataset': SYNC_DATASET_PURCHASE_ORDER, 'business_key': business_key, 'queue_id': queue_id})

    def process_pending_changes(self, limit: int = 100) -> int:
        processed = 0
        for row in self.store.list_pending_changes(limit=limit):
            if row['dataset'] != SYNC_DATASET_PURCHASE_ORDER or row['action'] != 'save':
                continue
            remote_payload = self.push_client.save(PURCHASE_ORDER_FORM_ID, row['payload'])
            self.store.mark_change_done(row['id'], remote_payload=remote_payload)
            self.store.upsert_object(dataset=SYNC_DATASET_PURCHASE_ORDER, business_key=row['business_key'], form_id=PURCHASE_ORDER_FORM_ID, payload=row['payload'], source='local')
            processed += 1
        return processed
