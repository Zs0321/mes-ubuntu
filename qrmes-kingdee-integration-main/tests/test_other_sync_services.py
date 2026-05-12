from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.sync.batch_trace_sync import BatchTraceSyncService
from qrmes_kingdee_integration.sync.lot_serial_relation_sync import LotSerialRelationSyncService
from qrmes_kingdee_integration.sync.routing_sync import RoutingSyncService
from qrmes_kingdee_integration.sync.serial_master_sync import SerialMasterSyncService
from qrmes_kingdee_integration.sync.warehouse_sync import WarehouseSyncService


class FakeRoutingForms:
    def query_routings(self, keyword='', limit=50):
        return [['GY-001', '工艺A', '100组织', 'C']]


class FakeWarehouseForms:
    def query_warehouses(self, keyword='', limit=50):
        return [['CK-001', '成品仓', '100组织', 'A']]


class FakeBatchForms:
    def query_batch_trace(self, keyword='', limit=50):
        return [['LOT-001', 'C', '2026-04-22 10:00:00']]


class FakePushClient:
    def save(self, form_id, data):
        return {'form_id': form_id, 'payload': data}


class FakeSerialMasterForms:
    def query_serial_master(self, keyword='', limit=50):
        return [['SN-001', 'MAT-001', 'CK-001', 'A', '2025-01-09T16:04:44.813']]


class FakeLotSerialRelationForms:
    def query_lot_serial_relation(self, keyword='', limit=50):
        return [['1', 'LOT-001', 'SN-001', 'MAT-001', 'A']]


def test_other_sync_services_can_pull_into_store(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    push = FakePushClient()

    RoutingSyncService(store, FakeRoutingForms(), push).sync_from_kingdee()
    WarehouseSyncService(store, FakeWarehouseForms(), push).sync_from_kingdee()
    BatchTraceSyncService(store, FakeBatchForms(), push).sync_from_kingdee()
    SerialMasterSyncService(store, FakeSerialMasterForms(), push).sync_from_kingdee()
    LotSerialRelationSyncService(store, FakeLotSerialRelationForms(), push).sync_from_kingdee()

    assert store.list_objects('routing')[0]['business_key'] == 'GY-001'
    assert store.list_objects('warehouse')[0]['business_key'] == 'CK-001'
    assert store.list_objects('batch_trace')[0]['business_key'] == 'LOT-001|C|2026-04-22 10:00:00'
    assert store.list_objects('serial_master')[0]['business_key'] == 'SN-001'
    assert store.list_objects('lot_serial_relation')[0]['business_key'] == '1|LOT-001|SN-001'
