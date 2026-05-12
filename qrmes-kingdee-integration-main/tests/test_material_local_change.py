from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.sync.material_sync import MaterialSyncService


class FakeMaterialForms:
    def query_materials(self, keyword='', limit=50):
        return []


class FakePushClient:
    def __init__(self):
        self.calls = []

    def save(self, form_id, data):
        self.calls.append((form_id, data))
        return {'Result': {'ResponseStatus': {'IsSuccess': True}}}


def test_material_local_change_is_persisted_and_pushed(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    push = FakePushClient()
    service = MaterialSyncService(store=store, forms_service=FakeMaterialForms(), push_client=push)

    result = service.apply_local_change('MAT-001', {'Number': 'MAT-001', 'FName': '测试物料'})

    assert result.ok is True
    assert push.calls == [('BD_MATERIAL', {'Number': 'MAT-001', 'FName': '测试物料'})]
    assert store.get_object('material', 'MAT-001')['source'] == 'local'
