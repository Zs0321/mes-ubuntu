from __future__ import annotations

import os
from flask import Flask, jsonify, request

from qrmes_kingdee_integration.client.base import KingdeeClient
from qrmes_kingdee_integration.config import load_settings
from qrmes_kingdee_integration.forms.bom import BomFormsService
from qrmes_kingdee_integration.forms.materials import MaterialsFormsService
from qrmes_kingdee_integration.forms.master_data import MASTER_DATA_DEFINITIONS, MASTER_DATA_ENDPOINTS, MasterDataFormsService
from qrmes_kingdee_integration.forms.production_order import ProductionOrderFormsService
from qrmes_kingdee_integration.forms.purchase_order import PurchaseOrderFormsService
from qrmes_kingdee_integration.forms.production_trace import (
    OperationPlanningFormsService,
    OperationReportFormsService,
    ProductionInstockFormsService,
    ProductionMaterialListFormsService,
)
from qrmes_kingdee_integration.forms.routing import RoutingFormsService
from qrmes_kingdee_integration.forms.warehouse import WarehouseFormsService
from qrmes_kingdee_integration.forms.batch_trace import BatchTraceFormsService
from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.api.traceability import create_traceability_blueprint
from qrmes_kingdee_integration.sync.batch_trace_sync import BatchTraceSyncService
from qrmes_kingdee_integration.sync.bom_sync import BomSyncService
from qrmes_kingdee_integration.sync.lot_serial_relation_sync import LotSerialRelationSyncService
from qrmes_kingdee_integration.sync.material_sync import MaterialSyncService
from qrmes_kingdee_integration.sync.master_data_sync import MasterDataSyncService
from qrmes_kingdee_integration.sync.production_order_sync import ProductionOrderSyncService
from qrmes_kingdee_integration.sync.purchase_order_sync import PurchaseOrderSyncService
from qrmes_kingdee_integration.sync.production_trace_sync import (
    OperationPlanningSyncService,
    OperationReportSyncService,
    ProductionInstockSyncService,
    ProductionMaterialListSyncService,
)
from qrmes_kingdee_integration.sync.routing_sync import RoutingSyncService
from qrmes_kingdee_integration.sync.serial_master_sync import SerialMasterSyncService
from qrmes_kingdee_integration.sync.warehouse_sync import WarehouseSyncService
from qrmes_kingdee_integration.sync.worker import SyncWorker


def create_app(
    *,
    store: SQLiteSyncStore | None = None,
    production_sync_service: ProductionOrderSyncService | None = None,
    material_sync_service: MaterialSyncService | None = None,
    bom_sync_service: BomSyncService | None = None,
    purchase_sync_service: PurchaseOrderSyncService | None = None,
    routing_sync_service: RoutingSyncService | None = None,
    warehouse_sync_service: WarehouseSyncService | None = None,
    batch_trace_sync_service: BatchTraceSyncService | None = None,
    serial_master_sync_service: SerialMasterSyncService | None = None,
    lot_serial_relation_sync_service: LotSerialRelationSyncService | None = None,
    production_material_list_sync_service: ProductionMaterialListSyncService | None = None,
    production_instock_sync_service: ProductionInstockSyncService | None = None,
    operation_planning_sync_service: OperationPlanningSyncService | None = None,
    operation_report_sync_service: OperationReportSyncService | None = None,
    master_data_sync_services: dict[str, MasterDataSyncService] | None = None,
) -> Flask:
    app = Flask(__name__)
    settings = load_settings()
    store = store or SQLiteSyncStore(settings.local_db_path)
    shared_client = KingdeeClient(settings.kingdee)
    production_sync_service = production_sync_service or ProductionOrderSyncService(
        store=store,
        forms_service=ProductionOrderFormsService(shared_client),
        push_client=shared_client,
    )
    material_sync_service = material_sync_service or MaterialSyncService(
        store=store,
        forms_service=MaterialsFormsService(shared_client),
        push_client=shared_client,
    )
    bom_sync_service = bom_sync_service or BomSyncService(
        store=store,
        forms_service=BomFormsService(shared_client),
        push_client=shared_client,
    )
    purchase_sync_service = purchase_sync_service or PurchaseOrderSyncService(
        store=store,
        forms_service=PurchaseOrderFormsService(shared_client),
        push_client=shared_client,
    )
    routing_sync_service = routing_sync_service or RoutingSyncService(
        store=store,
        forms_service=RoutingFormsService(shared_client),
        push_client=shared_client,
    )
    warehouse_sync_service = warehouse_sync_service or WarehouseSyncService(
        store=store,
        forms_service=WarehouseFormsService(shared_client),
        push_client=shared_client,
    )
    batch_trace_sync_service = batch_trace_sync_service or BatchTraceSyncService(
        store=store,
        forms_service=BatchTraceFormsService(shared_client),
        push_client=shared_client,
    )
    serial_master_sync_service = serial_master_sync_service or SerialMasterSyncService(
        store=store,
        forms_service=BatchTraceFormsService(shared_client),
        push_client=shared_client,
    )
    lot_serial_relation_sync_service = lot_serial_relation_sync_service or LotSerialRelationSyncService(
        store=store,
        forms_service=BatchTraceFormsService(shared_client),
        push_client=shared_client,
    )
    production_material_list_sync_service = production_material_list_sync_service or ProductionMaterialListSyncService(
        store=store,
        forms_service=ProductionMaterialListFormsService(shared_client),
        push_client=shared_client,
    )
    production_instock_sync_service = production_instock_sync_service or ProductionInstockSyncService(
        store=store,
        forms_service=ProductionInstockFormsService(shared_client),
        push_client=shared_client,
    )
    operation_planning_sync_service = operation_planning_sync_service or OperationPlanningSyncService(
        store=store,
        forms_service=OperationPlanningFormsService(shared_client),
        push_client=shared_client,
    )
    operation_report_sync_service = operation_report_sync_service or OperationReportSyncService(
        store=store,
        forms_service=OperationReportFormsService(shared_client),
        push_client=shared_client,
    )
    master_data_forms_service = MasterDataFormsService(shared_client)
    master_data_sync_services = master_data_sync_services or {
        dataset: MasterDataSyncService(
            store=store,
            forms_service=master_data_forms_service,
            dataset=dataset,
            push_client=shared_client,
        )
        for dataset in MASTER_DATA_DEFINITIONS
    }
    supported_datasets = [
        'material', 'bom', 'purchase_order', 'production_order', 'routing', 'warehouse',
        'batch_trace', 'serial_master', 'lot_serial_relation', 'production_material_list',
        'production_instock', 'operation_planning', 'operation_report', *MASTER_DATA_DEFINITIONS.keys(),
    ]
    auto_sync_enabled = str(os.environ.get('QRMES_KINGDEE_AUTO_SYNC', 'true')).strip().lower() not in {'0', 'false', 'no', 'off'}
    worker = SyncWorker(
        store=store,
        pull_services={
            'material': material_sync_service,
            'bom': bom_sync_service,
            'purchase_order': purchase_sync_service,
            'production_order': production_sync_service,
            'routing': routing_sync_service,
            'warehouse': warehouse_sync_service,
            'batch_trace': batch_trace_sync_service,
            'serial_master': serial_master_sync_service,
            'lot_serial_relation': lot_serial_relation_sync_service,
            'production_material_list': production_material_list_sync_service,
            'production_instock': production_instock_sync_service,
            'operation_planning': operation_planning_sync_service,
            'operation_report': operation_report_sync_service,
            **master_data_sync_services,
        },
        outbound_services={
            'material': material_sync_service,
            'bom': bom_sync_service,
            'purchase_order': purchase_sync_service,
            'production_order': production_sync_service,
            'routing': routing_sync_service,
            'warehouse': warehouse_sync_service,
            'batch_trace': batch_trace_sync_service,
        },
        pull_interval_seconds=int(os.environ.get('QRMES_KINGDEE_PULL_INTERVAL_SECONDS', '300')),
    )
    if auto_sync_enabled:
        worker.start()

    app.register_blueprint(create_traceability_blueprint(store))

    @app.get('/health')
    def health():
        return jsonify({
            'service': 'qrmes-kingdee-integration',
            'kingdee_ready': settings.kingdee.is_ready,
            'missing': settings.kingdee.public_summary['missing'],
            'local_db_path': str(settings.local_db_path),
            'supported_datasets': supported_datasets,
            'auto_sync_enabled': auto_sync_enabled,
            'pull_interval_seconds': worker.pull_interval_seconds,
        })

    @app.get('/api/local-db/<dataset>')
    def list_dataset(dataset: str):
        return jsonify({'dataset': dataset, 'rows': store.list_objects(dataset)})

    @app.get('/api/local-db/trace/serial')
    def trace_serial_from_local_bridge():
        serial_no = (request.args.get('serial_no') or '').strip()
        material_code = (request.args.get('material_code') or '').strip()
        if not serial_no:
            return jsonify({'error': 'serial_no is required'}), 400

        serial_rows = [
            row for row in store.list_objects('serial_master', limit=500)
            if (row.get('payload') or {}).get('serial_no') == serial_no
        ]
        if material_code:
            serial_rows = [
                row for row in serial_rows
                if (row.get('payload') or {}).get('material_code') == material_code
            ]

        relation_rows = [
            row for row in store.list_objects('lot_serial_relation', limit=500)
            if (row.get('payload') or {}).get('serial_no') == serial_no
        ]
        if material_code:
            relation_rows = [
                row for row in relation_rows
                if (row.get('payload') or {}).get('material_code') == material_code
            ]

        return jsonify({
            'query_mode': 'qt_trace_show_local_bridge',
            'resolved_filters': {
                'serial_no': serial_no,
                'material_code': material_code,
                'qt_trace_show_required_fields': ['FMATERIALID', 'FSERIALID'],
            },
            'root_matches': serial_rows,
            'relation_matches': relation_rows,
            'trace_runtime': {
                'ui_form_id': 'XLHZS',
                'show_form_id': 'QT_TraceShow',
                'filter_form_id': 'QT_TraceFilter',
                'source_menu_codes': ['XLHZS', 'PHXLHZHZS'],
            },
            'tree_model': {
                'form_id': 'QT_TreeModel',
                'tree_columns': ['FLEAFTEXT'],
                'detail_columns': ['FSeq', 'FDLOT', 'FDSERIALID'],
            },
            'tree_nodes': [
                {
                    'id': f"root:{row['business_key']}",
                    'label': f"{(row.get('payload') or {}).get('material_code') or ''}【{(row.get('payload') or {}).get('serial_no') or ''}】",
                    'children': [
                        {
                            'id': f"relation:{rel['business_key']}",
                            'label': f"{(rel.get('payload') or {}).get('lot_no') or ''}【{(rel.get('payload') or {}).get('serial_no') or ''}】",
                            'payload': rel.get('payload') or {},
                        }
                        for rel in relation_rows
                    ],
                    'payload': row.get('payload') or {},
                }
                for row in serial_rows
            ],
        })

    @app.post('/api/sync/materials/pull')
    def pull_materials():
        result = material_sync_service.sync_from_kingdee(limit=int(request.args.get('limit', '100')))
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/sync/boms/pull')
    def pull_boms():
        result = bom_sync_service.sync_from_kingdee(limit=int(request.args.get('limit', '100')))
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/sync/purchase-orders/pull')
    def pull_purchase_orders():
        result = purchase_sync_service.sync_from_kingdee(limit=int(request.args.get('limit', '100')))
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/sync/routings/pull')
    def pull_routings():
        result = routing_sync_service.sync_from_kingdee(limit=int(request.args.get('limit', '100')))
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/sync/warehouses/pull')
    def pull_warehouses():
        result = warehouse_sync_service.sync_from_kingdee(limit=int(request.args.get('limit', '100')))
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/sync/batch-traces/pull')
    def pull_batch_traces():
        result = batch_trace_sync_service.sync_from_kingdee(limit=int(request.args.get('limit', '100')))
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/sync/serial-masters/pull')
    def pull_serial_masters():
        result = serial_master_sync_service.sync_from_kingdee(limit=int(request.args.get('limit', '100')))
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/sync/lot-serial-relations/pull')
    def pull_lot_serial_relations():
        result = lot_serial_relation_sync_service.sync_from_kingdee(limit=int(request.args.get('limit', '100')))
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/sync/production-orders/pull')
    def pull_production_orders():
        result = production_sync_service.sync_from_kingdee(limit=int(request.args.get('limit', '100')))
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/sync/production-material-lists/pull')
    def pull_production_material_lists():
        result = production_material_list_sync_service.sync_from_kingdee(limit=int(request.args.get('limit', '100')), keyword=request.args.get('keyword', ''))
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/sync/production-instocks/pull')
    def pull_production_instocks():
        result = production_instock_sync_service.sync_from_kingdee(limit=int(request.args.get('limit', '100')), keyword=request.args.get('keyword', ''))
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/sync/operation-plannings/pull')
    def pull_operation_plannings():
        result = operation_planning_sync_service.sync_from_kingdee(limit=int(request.args.get('limit', '100')), keyword=request.args.get('keyword', ''))
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/sync/operation-reports/pull')
    def pull_operation_reports():
        result = operation_report_sync_service.sync_from_kingdee(limit=int(request.args.get('limit', '100')), keyword=request.args.get('keyword', ''))
        return jsonify(result.data), (200 if result.ok else 500)

    def _register_master_data_pull(dataset: str, endpoint_slug: str):
        @app.post(f'/api/sync/{endpoint_slug}/pull', endpoint=f'pull_master_data_{dataset}')
        def pull_master_data():
            result = master_data_sync_services[dataset].sync_from_kingdee(
                limit=int(request.args.get('limit', '100')),
                keyword=request.args.get('keyword', ''),
            )
            return jsonify(result.data), (200 if result.ok else 500)

    for _dataset, _endpoint_slug in MASTER_DATA_ENDPOINTS.items():
        _register_master_data_pull(_dataset, _endpoint_slug)

    @app.post('/api/local-db/material/<business_key>')
    def update_local_material(business_key: str):
        payload = request.get_json(silent=True) or {}
        result = material_sync_service.apply_local_change(business_key=business_key, payload=payload)
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/local-db/routing/<business_key>')
    def update_local_routing(business_key: str):
        payload = request.get_json(silent=True) or {}
        result = routing_sync_service.apply_local_change(business_key=business_key, payload=payload)
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/local-db/warehouse/<business_key>')
    def update_local_warehouse(business_key: str):
        payload = request.get_json(silent=True) or {}
        result = warehouse_sync_service.apply_local_change(business_key=business_key, payload=payload)
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/local-db/batch_trace/<business_key>')
    def update_local_batch_trace(business_key: str):
        payload = request.get_json(silent=True) or {}
        result = batch_trace_sync_service.apply_local_change(business_key=business_key, payload=payload)
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/local-db/bom/<business_key>')
    def update_local_bom(business_key: str):
        payload = request.get_json(silent=True) or {}
        result = bom_sync_service.apply_local_change(business_key=business_key, payload=payload)
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/local-db/purchase_order/<business_key>')
    def update_local_purchase_order(business_key: str):
        payload = request.get_json(silent=True) or {}
        result = purchase_sync_service.apply_local_change(business_key=business_key, payload=payload)
        return jsonify(result.data), (200 if result.ok else 500)

    @app.post('/api/local-db/production_order/<business_key>')
    def update_local_production_order(business_key: str):
        payload = request.get_json(silent=True) or {}
        result = production_sync_service.apply_local_change(business_key=business_key, payload=payload)
        return jsonify(result.data), (200 if result.ok else 500)

    return app

if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=int(os.environ.get('QRMES_KINGDEE_PORT', '9010')))
