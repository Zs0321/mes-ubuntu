from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.sync.bom_sync import BomSyncService
from qrmes_kingdee_integration.sync.purchase_order_sync import PurchaseOrderSyncService


class FakeForms:
    def query_boms(self, keyword='', limit=50):
        return []
    def query_purchase_orders(self, keyword='', limit=50):
        return []


class FakePushClient:
    def __init__(self):
        self.calls = []

    def save(self, form_id, data):
        self.calls.append((form_id, data))
        return {'Result': {'ResponseStatus': {'IsSuccess': True}}}


def test_bom_local_change_is_persisted_and_pushed(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    push = FakePushClient()
    service = BomSyncService(store=store, forms_service=FakeForms(), push_client=push)

    result = service.apply_local_change('BOM-001', {'Number': 'BOM-001', 'FName': '测试BOM'})

    assert result.ok is True
    assert push.calls == [('ENG_BOM', {'Number': 'BOM-001', 'FName': '测试BOM'})]
    assert store.get_object('bom', 'BOM-001')['source'] == 'local'


def test_purchase_local_change_is_persisted_and_pushed(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    push = FakePushClient()
    service = PurchaseOrderSyncService(store=store, forms_service=FakeForms(), push_client=push)

    result = service.apply_local_change('PO-001', {'Number': 'PO-001', 'FNote': '测试采购单'})

    assert result.ok is True
    assert push.calls == [('PUR_PurchaseOrder', {'Number': 'PO-001', 'FNote': '测试采购单'})]
    assert store.get_object('purchase_order', 'PO-001')['source'] == 'local'
