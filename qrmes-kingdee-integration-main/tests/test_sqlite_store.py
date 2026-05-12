import json

from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore


def test_sqlite_store_upserts_objects_and_lists_by_dataset(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')

    store.upsert_object(
        dataset='production_order',
        business_key='MO-001',
        form_id='SCDD',
        payload={'bill_no': 'MO-001', 'status': 'A'},
        source='kingdee',
    )

    rows = store.list_objects('production_order')

    assert len(rows) == 1
    assert rows[0]['business_key'] == 'MO-001'
    assert rows[0]['form_id'] == 'SCDD'
    assert rows[0]['payload']['status'] == 'A'


def test_sqlite_store_records_outbound_change_queue(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')

    queue_id = store.enqueue_change(
        dataset='production_order',
        business_key='MO-001',
        form_id='SCDD',
        action='save',
        payload={'Number': 'MO-001', 'FNote': 'updated'},
    )
    pending = store.list_pending_changes(limit=10)

    assert queue_id > 0
    assert len(pending) == 1
    assert pending[0]['id'] == queue_id
    assert pending[0]['payload'] == {'Number': 'MO-001', 'FNote': 'updated'}

    store.mark_change_done(queue_id, remote_payload={'Result': {'ResponseStatus': {'IsSuccess': True}}})

    assert store.list_pending_changes(limit=10) == []
