from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.sync.material_sync import MaterialSyncService


class FakeMaterialForms:
    def query_materials(self, keyword='', limit=50):
        return [
            ['MAT-001', '电机壳体', 'AL-01'],
            ['MAT-002', '接插件', 'CN-02'],
        ]


class FakePushClient:
    def save(self, form_id, data):
        return {'Result': {'ResponseStatus': {'IsSuccess': True}}}


def test_material_sync_pulls_remote_rows_into_local_store(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    service = MaterialSyncService(store=store, forms_service=FakeMaterialForms(), push_client=FakePushClient())

    result = service.sync_from_kingdee(limit=100)
    saved = store.list_objects('material')

    assert result.ok is True
    assert result.data['synced_count'] == 2
    assert saved[0]['form_id'] == 'BD_MATERIAL'
