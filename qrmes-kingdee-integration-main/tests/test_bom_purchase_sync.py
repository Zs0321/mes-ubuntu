from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.sync.bom_sync import BomSyncService
from qrmes_kingdee_integration.sync.purchase_order_sync import PurchaseOrderSyncService


class FakeBomForms:
    def query_boms(self, keyword='', limit=50):
        return [['BOM-001', '电机BOM', 'MAT-001']]


class FakePurchaseForms:
    def query_purchase_orders(self, keyword='', limit=50):
        return [['PO-001', '2026-04-22T00:00:00', '供应商A']]


class FakePushClient:
    def save(self, form_id, data):
        return {'Result': {'ResponseStatus': {'IsSuccess': True}}}


def test_bom_and_purchase_sync_pull_into_store(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    push = FakePushClient()

    bom_result = BomSyncService(store=store, forms_service=FakeBomForms(), push_client=push).sync_from_kingdee()
    purchase_result = PurchaseOrderSyncService(store=store, forms_service=FakePurchaseForms(), push_client=push).sync_from_kingdee()

    assert bom_result.data['synced_count'] == 1
    assert purchase_result.data['synced_count'] == 1
    assert store.list_objects('bom')[0]['form_id'] == 'ENG_BOM'
    assert store.list_objects('purchase_order')[0]['form_id'] == 'PUR_PurchaseOrder'
