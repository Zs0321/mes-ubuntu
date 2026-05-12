from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qrmes_kingdee_integration.api_models import ApiResult
from qrmes_kingdee_integration.forms.materials import MATERIAL_FORM_ID

SYNC_DATASET_MATERIAL = "material"


@dataclass
class MaterialSyncService:
    store: Any
    forms_service: Any
    push_client: Any

    def sync_from_kingdee(self, limit: int = 100, keyword: str = '') -> ApiResult:
        rows = self.forms_service.query_materials(keyword=keyword, limit=limit)
        synced = 0
        for row in rows:
            business_key = str(row[0])
            self.store.upsert_object(
                dataset=SYNC_DATASET_MATERIAL,
                business_key=business_key,
                form_id=MATERIAL_FORM_ID,
                payload={
                    'number': row[0],
                    'name': row[1] if len(row) > 1 else '',
                    'specification': row[2] if len(row) > 2 else '',
                },
                source='kingdee',
            )
            synced += 1
        return ApiResult(ok=True, data={'dataset': SYNC_DATASET_MATERIAL, 'synced_count': synced})

    def apply_local_change(self, business_key: str, payload: dict[str, Any]) -> ApiResult:
        queue_id = self.store.enqueue_change(dataset=SYNC_DATASET_MATERIAL, business_key=business_key, form_id=MATERIAL_FORM_ID, action='save', payload=payload)
        remote_payload = self.push_client.save(MATERIAL_FORM_ID, payload)
        self.store.mark_change_done(queue_id, remote_payload=remote_payload)
        self.store.upsert_object(dataset=SYNC_DATASET_MATERIAL, business_key=business_key, form_id=MATERIAL_FORM_ID, payload=payload, source='local')
        return ApiResult(ok=True, data={'dataset': SYNC_DATASET_MATERIAL, 'business_key': business_key, 'queue_id': queue_id})

    def process_pending_changes(self, limit: int = 100) -> int:
        processed = 0
        for row in self.store.list_pending_changes(limit=limit):
            if row['dataset'] != SYNC_DATASET_MATERIAL or row['action'] != 'save':
                continue
            remote_payload = self.push_client.save(MATERIAL_FORM_ID, row['payload'])
            self.store.mark_change_done(row['id'], remote_payload=remote_payload)
            self.store.upsert_object(dataset=SYNC_DATASET_MATERIAL, business_key=row['business_key'], form_id=MATERIAL_FORM_ID, payload=row['payload'], source='local')
            processed += 1
        return processed
