from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.sync.production_order_sync import ProductionOrderSyncService


class FakeProductionForms:
    def query_orders(self, limit=50, filter_string=''):
        return [
            ['MO-001', 'A', 'MAT-001', '电机A', 12],
            ['MO-002', 'B', 'MAT-002', '电机B', 6],
        ]


class FakePushClient:
    def save(self, form_id, data):
        raise AssertionError('save should not be called during inbound sync')


def test_production_order_sync_pulls_remote_rows_into_local_store(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    service = ProductionOrderSyncService(store=store, forms_service=FakeProductionForms(), push_client=FakePushClient())

    result = service.sync_from_kingdee(limit=100)
    saved = store.list_objects('production_order')

    assert result.ok is True
    assert result.data['synced_count'] == 2
    assert len(saved) == 2
    assert saved[0]['dataset'] == 'production_order'
    assert saved[0]['source'] == 'kingdee'
