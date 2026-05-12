from qrmes_kingdee_integration.forms.production_trace import (
    OperationPlanningFormsService,
    OperationReportFormsService,
    ProductionInstockFormsService,
    ProductionMaterialListFormsService,
)
from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.sync.production_trace_sync import (
    OperationPlanningSyncService,
    OperationReportSyncService,
    ProductionInstockSyncService,
    ProductionMaterialListSyncService,
)


class DummyClient:
    def __init__(self):
        self.queries = []

    def execute_bill_query(self, query):
        self.queries.append(query)
        return [[query.form_id, query.field_keys, query.filter_string]]


class FakeForms:
    def __init__(self, rows):
        self.rows = rows

    def query_production_material_lists(self, limit=100, keyword=''):
        return self.rows

    def query_production_instocks(self, limit=100, keyword=''):
        return self.rows

    def query_operation_plannings(self, limit=100, keyword=''):
        return self.rows

    def query_operation_reports(self, limit=100, keyword=''):
        return self.rows


class FakePushClient:
    def save(self, form_id, data):
        return {'form_id': form_id, 'data': data}


def test_production_trace_form_services_use_verified_form_ids_and_filters():
    client = DummyClient()

    material_rows = ProductionMaterialListFormsService(client).query_production_material_lists(keyword='MO000001')
    instock_rows = ProductionInstockFormsService(client).query_production_instocks(keyword='SN001')
    planning_rows = OperationPlanningFormsService(client).query_operation_plannings(keyword='MO000026')
    report_rows = OperationReportFormsService(client).query_operation_reports(keyword='VCU')

    assert material_rows[0][0] == 'PRD_PPBOM'
    assert 'FMoBillNo like' in material_rows[0][2]
    assert instock_rows[0][0] == 'PRD_INSTOCK'
    assert 'FSerialNo like' in instock_rows[0][2]
    assert planning_rows[0][0] == 'SFC_OperationPlanning'
    assert 'FMONumber like' in planning_rows[0][2]
    assert report_rows[0][0] == 'SFC_OperationReport'
    assert 'FSerialNo like' in report_rows[0][2]


def test_production_material_list_sync_maps_production_bom_rows(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    service = ProductionMaterialListSyncService(
        store=store,
        forms_service=FakeForms([[
            100001,
            'PPBOM00000001',
            'C',
            'Genesis-XiTSP-F15-B',
            '多合一控制器',
            '仙途清扫车二合一电控',
            'BM000005',
            '制造工程部',
            'MO000001',
            20.0,
            'Pcs',
            None,
            None,
        ]]),
        push_client=FakePushClient(),
    )

    result = service.sync_from_kingdee()
    rows = store.list_objects('production_material_list')

    assert result.ok is True
    assert rows[0]['business_key'] == 'PPBOM00000001|Genesis-XiTSP-F15-B'
    assert rows[0]['form_id'] == 'PRD_PPBOM'
    assert rows[0]['payload']['production_order_no'] == 'MO000001'
    assert rows[0]['payload']['qty'] == 20.0


def test_production_instock_sync_maps_serial_and_lot_rows(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    service = ProductionInstockSyncService(
        store=store,
        forms_service=FakeForms([[
            100001,
            'SCRK00000001',
            'C',
            '2025-01-30T00:00:00',
            'Genesis-XiTSP-F15-B',
            '多合一控制器',
            '100',
            'MO000001',
            1.0,
            'Pcs',
            'CK001',
            '20250110',
            'XiTSPF15B2025010600105',
        ]]),
        push_client=FakePushClient(),
    )

    service.sync_from_kingdee()
    row = store.list_objects('production_instock')[0]

    assert row['business_key'] == 'SCRK00000001|XiTSPF15B2025010600105|20250110|Genesis-XiTSP-F15-B|CK001'
    assert row['form_id'] == 'PRD_INSTOCK'
    assert row['payload']['serial_no'] == 'XiTSPF15B2025010600105'
    assert row['payload']['lot_no'] == '20250110'


def test_operation_planning_and_report_sync_map_work_order_and_operation(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    planning = OperationPlanningSyncService(
        store=store,
        forms_service=FakeForms([[100001, 'OP000001', 'C', 'MO000026', '10', '生产装配', 'Exodus-VCU-AL12-RV-B1', 10.0, 0.0, 'MO000026']]),
        push_client=FakePushClient(),
    )
    report = OperationReportSyncService(
        store=store,
        forms_service=FakeForms([[100007, 'GXHB000003', 'C', '2025-02-13T00:00:00', 'MO000026', '10', '生产装配', 'VCUAL12RVC12025021100226', 10.0, 0.0, 'OP000002']]),
        push_client=FakePushClient(),
    )

    planning.sync_from_kingdee()
    report.sync_from_kingdee()

    planning_row = store.list_objects('operation_planning')[0]
    report_row = store.list_objects('operation_report')[0]
    assert planning_row['form_id'] == 'SFC_OperationPlanning'
    assert planning_row['payload']['production_order_no'] == 'MO000026'
    assert planning_row['payload']['operation_no'] == '10'
    assert report_row['form_id'] == 'SFC_OperationReport'
    assert report_row['payload']['serial_no'] == 'VCUAL12RVC12025021100226'
    assert report_row['payload']['finish_qty'] == 10.0


def test_same_bill_no_rows_keep_distinct_business_keys(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    service = ProductionMaterialListSyncService(
        store=store,
        forms_service=FakeForms([
            [100001, 'PPBOM00000001', 'C', 'MAT-A', '物料A', '', 'BM001', '车间', 'MO000001', 1.0, 'Pcs', 'CK001', 'LOT-A'],
            [100001, 'PPBOM00000001', 'C', 'MAT-B', '物料B', '', 'BM001', '车间', 'MO000001', 2.0, 'Pcs', 'CK001', 'LOT-B'],
        ]),
        push_client=FakePushClient(),
    )

    service.sync_from_kingdee()
    rows = store.list_objects('production_material_list')

    assert len(rows) == 2
    assert {row['payload']['material_code'] for row in rows} == {'MAT-A', 'MAT-B'}
    assert all(row['business_key'].startswith('PPBOM00000001|') for row in rows)


def test_blank_bill_no_falls_back_to_stable_id_business_key(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    service = OperationReportSyncService(
        store=store,
        forms_service=FakeForms([[118764, ' ', 'Z', '2026-04-09T00:00:00', 'MO001054', 0, '生产电机合装', 'SN-001', 1.0, 0.0, ' ']]),
        push_client=FakePushClient(),
    )

    service.sync_from_kingdee()
    row = store.list_objects('operation_report')[0]

    assert row['business_key'] == '118764|SN-001|0'
    assert row['payload']['bill_no'] == ''
