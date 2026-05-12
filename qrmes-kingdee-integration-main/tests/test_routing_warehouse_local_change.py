from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.sync.routing_sync import RoutingSyncService
from qrmes_kingdee_integration.sync.warehouse_sync import WarehouseSyncService


class FakeRoutingForms:
    def query_routings(self, keyword='', limit=50):
        return []


class FakeWarehouseForms:
    def query_warehouses(self, keyword='', limit=50):
        return []


class FakePushClient:
    def __init__(self):
        self.calls = []

    def save(self, form_id, data):
        self.calls.append((form_id, data))
        return {'Result': {'ResponseStatus': {'IsSuccess': True}}}


def test_routing_local_change_is_persisted_and_pushed(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    push = FakePushClient()
    service = RoutingSyncService(store=store, forms_service=FakeRoutingForms(), push_client=push)

    result = service.apply_local_change('RT-001', {'Number': 'RT-001', 'FName': '测试工艺路线'})

    assert result.ok is True
    assert push.calls == [('ENG_ROUTE', {'Number': 'RT-001', 'FName': '测试工艺路线'})]
    assert store.get_object('routing', 'RT-001')['source'] == 'local'


def test_warehouse_local_change_is_persisted_and_pushed(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    push = FakePushClient()
    service = WarehouseSyncService(store=store, forms_service=FakeWarehouseForms(), push_client=push)

    result = service.apply_local_change('CK-001', {'Number': 'CK-001', 'FName': '测试仓库'})

    assert result.ok is True
    assert push.calls == [('BD_STOCK', {'Number': 'CK-001', 'FName': '测试仓库'})]
    assert store.get_object('warehouse', 'CK-001')['source'] == 'local'
