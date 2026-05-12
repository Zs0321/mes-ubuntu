from qrmes_kingdee_integration.api.app import create_app
from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore


class FakeSyncService:
    def __init__(self, store, dataset='production_order'):
        self.store = store
        self.dataset = dataset
        self.pulled = 0
        self.local_changes = []

    def sync_from_kingdee(self, limit=100, filter_string='', keyword=''):
        self.pulled += 1
        key = {
            'production_order': 'MO-001',
            'material': 'MAT-001',
            'bom': 'BOM-001',
            'purchase_order': 'PO-001',
            'serial_master': 'SN-001',
            'lot_serial_relation': '1|LOT-001|SN-001',
            'production_material_list': 'PPBOM00000001',
            'production_instock': 'SCRK00000001',
            'operation_planning': 'OP000001',
            'operation_report': 'GXHB000003',
            'supplier': 'SUP-001',
            'customer': 'CUS-001',
            'department': 'DEP-001',
            'employee': 'EMP-001',
            'unit': 'UNIT-001',
            'organization': 'ORG-001',
            'material_category': 'MC-001',
            'stock_status': 'SS-001',
        }[self.dataset]
        form = {
            'production_order': 'PRD_MO',
            'material': 'BD_MATERIAL',
            'bom': 'ENG_BOM',
            'purchase_order': 'PUR_PurchaseOrder',
            'serial_master': 'BD_SerialMainFile',
            'lot_serial_relation': 'QT_LotSNRelation',
            'production_material_list': 'PRD_PPBOM',
            'production_instock': 'PRD_INSTOCK',
            'operation_planning': 'SFC_OperationPlanning',
            'operation_report': 'SFC_OperationReport',
            'supplier': 'BD_Supplier',
            'customer': 'BD_Customer',
            'department': 'BD_Department',
            'employee': 'BD_Empinfo',
            'unit': 'BD_UNIT',
            'organization': 'ORG_Organizations',
            'material_category': 'BD_MATERIALCATEGORY',
            'stock_status': 'BD_STOCKSTATUS',
        }[self.dataset]
        self.store.upsert_object(dataset=self.dataset, business_key=key, form_id=form, payload={'number': key}, source='kingdee')
        return type('R', (), {'ok': True, 'data': {'synced_count': 1}})()

    def apply_local_change(self, business_key, payload):
        self.local_changes.append((business_key, payload))
        self.store.upsert_object(dataset=self.dataset, business_key=business_key, form_id='X', payload=payload, source='local')
        return type('R', (), {'ok': True, 'data': {'business_key': business_key}})()

    def process_pending_changes(self, limit=100):
        return 0


def test_api_app_supports_pull_and_local_db_access(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    app = create_app(store=store, production_sync_service=FakeSyncService(store, 'production_order'))
    client = app.test_client()

    pull_resp = client.post('/api/sync/production-orders/pull')
    list_resp = client.get('/api/local-db/production_order')

    assert pull_resp.status_code == 200
    assert pull_resp.get_json()['synced_count'] == 1
    assert list_resp.status_code == 200
    assert list_resp.get_json()['rows'][0]['business_key'] == 'MO-001'


def test_api_app_supports_local_change_writeback_entry(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    sync_service = FakeSyncService(store, 'production_order')
    app = create_app(store=store, production_sync_service=sync_service)
    client = app.test_client()

    resp = client.post('/api/local-db/production_order/MO-009', json={'Number': 'MO-009', 'FNote': 'edited'})

    assert resp.status_code == 200
    assert sync_service.local_changes == [('MO-009', {'Number': 'MO-009', 'FNote': 'edited'})]


def test_api_app_supports_material_bom_purchase_local_writeback(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    material = FakeSyncService(store, 'material')
    bom = FakeSyncService(store, 'bom')
    purchase = FakeSyncService(store, 'purchase_order')
    app = create_app(store=store, material_sync_service=material, bom_sync_service=bom, purchase_sync_service=purchase, production_sync_service=FakeSyncService(store, 'production_order'))
    client = app.test_client()

    assert client.post('/api/local-db/material/MAT-001', json={'Number': 'MAT-001'}).status_code == 200
    assert client.post('/api/local-db/bom/BOM-001', json={'Number': 'BOM-001'}).status_code == 200
    assert client.post('/api/local-db/purchase_order/PO-001', json={'Number': 'PO-001'}).status_code == 200
    assert material.local_changes == [('MAT-001', {'Number': 'MAT-001'})]
    assert bom.local_changes == [('BOM-001', {'Number': 'BOM-001'})]
    assert purchase.local_changes == [('PO-001', {'Number': 'PO-001'})]


def test_api_app_supports_serial_master_and_lot_relation_pull(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    serial_master = FakeSyncService(store, 'serial_master')
    lot_relation = FakeSyncService(store, 'lot_serial_relation')
    app = create_app(
        store=store,
        production_sync_service=FakeSyncService(store, 'production_order'),
        serial_master_sync_service=serial_master,
        lot_serial_relation_sync_service=lot_relation,
    )
    client = app.test_client()

    assert client.post('/api/sync/serial-masters/pull').status_code == 200
    assert client.post('/api/sync/lot-serial-relations/pull').status_code == 200
    assert client.get('/api/local-db/serial_master').get_json()['rows'][0]['business_key'] == 'SN-001'
    assert client.get('/api/local-db/lot_serial_relation').get_json()['rows'][0]['business_key'] == '1|LOT-001|SN-001'


def test_api_app_supports_production_trace_pull_endpoints(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    production_material_list = FakeSyncService(store, 'production_material_list')
    production_instock = FakeSyncService(store, 'production_instock')
    operation_planning = FakeSyncService(store, 'operation_planning')
    operation_report = FakeSyncService(store, 'operation_report')
    app = create_app(
        store=store,
        production_sync_service=FakeSyncService(store, 'production_order'),
        production_material_list_sync_service=production_material_list,
        production_instock_sync_service=production_instock,
        operation_planning_sync_service=operation_planning,
        operation_report_sync_service=operation_report,
    )
    client = app.test_client()

    assert client.post('/api/sync/production-material-lists/pull').status_code == 200
    assert client.post('/api/sync/production-instocks/pull').status_code == 200
    assert client.post('/api/sync/operation-plannings/pull').status_code == 200
    assert client.post('/api/sync/operation-reports/pull').status_code == 200
    assert client.get('/api/local-db/production_material_list').get_json()['rows'][0]['business_key'] == 'PPBOM00000001'
    assert client.get('/api/local-db/production_instock').get_json()['rows'][0]['business_key'] == 'SCRK00000001'
    assert client.get('/api/local-db/operation_planning').get_json()['rows'][0]['business_key'] == 'OP000001'
    assert client.get('/api/local-db/operation_report').get_json()['rows'][0]['business_key'] == 'GXHB000003'


def test_api_app_supports_next_version_master_data_pull_endpoints(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    master_services = {
        dataset: FakeSyncService(store, dataset)
        for dataset in ['supplier', 'customer', 'department', 'employee', 'unit', 'organization', 'material_category', 'stock_status']
    }
    app = create_app(
        store=store,
        production_sync_service=FakeSyncService(store, 'production_order'),
        master_data_sync_services=master_services,
    )
    client = app.test_client()

    health = client.get('/health').get_json()
    for dataset in master_services:
        assert dataset in health['supported_datasets']

    endpoints = {
        'supplier': '/api/sync/suppliers/pull',
        'customer': '/api/sync/customers/pull',
        'department': '/api/sync/departments/pull',
        'employee': '/api/sync/employees/pull',
        'unit': '/api/sync/units/pull',
        'organization': '/api/sync/organizations/pull',
        'material_category': '/api/sync/material-categories/pull',
        'stock_status': '/api/sync/stock-statuses/pull',
    }
    for dataset, endpoint in endpoints.items():
        assert client.post(endpoint).status_code == 200
        assert client.get(f'/api/local-db/{dataset}').get_json()['rows'][0]['business_key']


def test_api_app_supports_trace_query_from_local_bridge(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    store.upsert_object(
        dataset='serial_master',
        business_key='SN-001',
        form_id='BD_SerialMainFile',
        payload={
            'serial_no': 'SN-001',
            'material_code': 'MAT-001',
            'stock_code': 'CK-001',
            'document_status': 'A',
            'created_at': '2026-03-30T10:00:00',
        },
        source='kingdee',
    )
    store.upsert_object(
        dataset='lot_serial_relation',
        business_key='1|LOT-001|SN-001',
        form_id='QT_LotSNRelation',
        payload={
            'relation_id': '1',
            'lot_no': 'LOT-001',
            'serial_no': 'SN-001',
            'material_code': 'MAT-001',
            'document_status': 'A',
        },
        source='kingdee',
    )
    app = create_app(store=store, production_sync_service=FakeSyncService(store, 'production_order'))
    client = app.test_client()

    resp = client.get('/api/local-db/trace/serial?serial_no=SN-001&material_code=MAT-001')

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['query_mode'] == 'qt_trace_show_local_bridge'
    assert payload['resolved_filters']['serial_no'] == 'SN-001'
    assert payload['resolved_filters']['material_code'] == 'MAT-001'
    assert payload['root_matches'][0]['payload']['serial_no'] == 'SN-001'
    assert payload['relation_matches'][0]['payload']['lot_no'] == 'LOT-001'
    assert payload['tree_model']['form_id'] == 'QT_TreeModel'
    assert payload['tree_model']['tree_columns'] == ['FLEAFTEXT']
    assert payload['tree_model']['detail_columns'] == ['FSeq', 'FDLOT', 'FDSERIALID']
    assert payload['tree_nodes'][0]['label'] == 'MAT-001【SN-001】'
    assert payload['tree_nodes'][0]['children'][0]['label'] == 'LOT-001【SN-001】'
