from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.sync.batch_trace_sync import BatchTraceSyncService


class FakeBatchForms:
    def query_batch_trace(self, keyword='', limit=50):
        return [['S31030040.A0', 'CK006', '20250101']]


class FakePushClient:
    def __init__(self):
        self.calls = []

    def save(self, form_id, data):
        self.calls.append((form_id, data))
        return {'Result': {'ResponseStatus': {'IsSuccess': True}}}


def test_batch_trace_sync_pulls_remote_rows_into_local_store(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    push = FakePushClient()
    service = BatchTraceSyncService(store=store, forms_service=FakeBatchForms(), push_client=push)

    result = service.sync_from_kingdee(limit=100)
    saved = store.list_objects('batch_trace')

    assert result.ok is True
    assert result.data['synced_count'] == 1
    assert saved[0]['form_id'] == 'STK_INVENTORY'
    assert saved[0]['payload']['material_code'] == 'S31030040.A0'


def test_batch_trace_local_change_is_persisted_and_pushed(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    push = FakePushClient()
    service = BatchTraceSyncService(store=store, forms_service=FakeBatchForms(), push_client=push)

    result = service.apply_local_change('S31030040.A0|CK006|20250101', {'FMaterialId': {'FNumber': 'S31030040.A0'}})

    assert result.ok is True
    assert push.calls == [('STK_LOTADJUST', {'FMaterialId': {'FNumber': 'S31030040.A0'}})]
    assert store.get_object('batch_trace', 'S31030040.A0|CK006|20250101')['source'] == 'local'
