from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.sync.production_order_sync import ProductionOrderSyncService


class FakeProductionForms:
    def query_orders(self, limit=50, filter_string=''):
        return []


class FakePushClient:
    def __init__(self):
        self.calls = []

    def save(self, form_id, data):
        self.calls.append((form_id, data))
        return {'Result': {'ResponseStatus': {'IsSuccess': True}, 'Number': data.get('Number', '')}}


def test_local_change_is_persisted_and_pushed_to_kingdee(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    push_client = FakePushClient()
    service = ProductionOrderSyncService(store=store, forms_service=FakeProductionForms(), push_client=push_client)

    result = service.apply_local_change(
        business_key='MO-001',
        payload={'Number': 'MO-001', 'FNote': 'from local db'},
    )

    assert result.ok is True
    assert push_client.calls == [('PRD_MO', {'Number': 'MO-001', 'FNote': 'from local db'})]
    saved = store.get_object('production_order', 'MO-001')
    assert saved['payload']['FNote'] == 'from local db'
    assert saved['source'] == 'local'
    assert store.list_pending_changes(limit=10) == []
