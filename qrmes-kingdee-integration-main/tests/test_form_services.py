from qrmes_kingdee_integration.client.base import KingdeeQuery
from qrmes_kingdee_integration.forms.batch_trace import BatchTraceFormsService
from qrmes_kingdee_integration.forms.bom import BomFormsService
from qrmes_kingdee_integration.forms.materials import MaterialsFormsService
from qrmes_kingdee_integration.forms.production_order import ProductionOrderFormsService
from qrmes_kingdee_integration.forms.purchase_order import PurchaseOrderFormsService
from qrmes_kingdee_integration.forms.routing import RoutingFormsService
from qrmes_kingdee_integration.forms.warehouse import WarehouseFormsService


class DummyClient:
    def __init__(self):
        self.queries = []
        self.views = []

    def execute_bill_query(self, query: KingdeeQuery):
        self.queries.append(query)
        return [[query.form_id, query.field_keys, query.filter_string]]

    def view(self, form_id: str, data: dict):
        self.views.append((form_id, data))
        return {"Result": {"ResponseStatus": {"IsSuccess": True}, "Result": data}}


def test_production_order_service_uses_real_api_form_and_view():
    client = DummyClient()
    service = ProductionOrderFormsService(client)

    rows = service.query_orders(limit=20, filter_string="FDocumentStatus='A'")
    detail = service.view_order("MO-001")

    assert rows == [["PRD_MO", service.DEFAULT_LIST_FIELDS, "FDocumentStatus='A'"]]
    assert detail["Result"]["Result"] == {"Number": "MO-001"}
    assert client.views == [("PRD_MO", {"Number": "MO-001"})]


def test_material_bom_purchase_services_use_documented_api_form_ids():
    client = DummyClient()

    materials_rows = MaterialsFormsService(client).query_materials(keyword="电机")
    bom_rows = BomFormsService(client).query_boms(keyword="Leviticus")
    purchase_rows = PurchaseOrderFormsService(client).query_purchase_orders(keyword="CGDD")

    assert materials_rows[0][0] == "BD_MATERIAL"
    assert "电机" in materials_rows[0][2]
    assert bom_rows[0][0] == "ENG_BOM"
    assert "Leviticus" in bom_rows[0][2]
    assert purchase_rows[0][0] == "PUR_PurchaseOrder"
    assert "CGDD" in purchase_rows[0][2]


def test_routing_warehouse_and_batch_services_keep_real_api_candidates():
    client = DummyClient()

    routing_rows = RoutingFormsService(client).query_routings(keyword="电机")
    warehouse_rows = WarehouseFormsService(client).query_warehouses(keyword="成品")
    batch_rows = BatchTraceFormsService(client).query_batch_trace(keyword="LOT-001")

    assert routing_rows[0][0] == "ENG_ROUTE"
    assert "FName like '%电机%'" in routing_rows[0][2]
    assert warehouse_rows[0][0] == "BD_STOCK"
    assert "FName like '%成品%'" in warehouse_rows[0][2]
    assert batch_rows[0][0] == "STK_INVENTORY"
    assert "LOT-001" in batch_rows[0][2]


def test_batch_trace_service_exposes_serial_master_and_lot_relation_queries():
    client = DummyClient()

    service = BatchTraceFormsService(client)
    serial_rows = service.query_serial_master(keyword="2025")
    relation_rows = service.query_lot_serial_relation(keyword="SN-001")

    assert serial_rows[0][0] == "BD_SerialMainFile"
    assert "FNumber like '%2025%'" in serial_rows[0][2]
    assert relation_rows[0][0] == "QT_LotSNRelation"
    assert "FSerialNo like '%SN-001%'" in relation_rows[0][2]
