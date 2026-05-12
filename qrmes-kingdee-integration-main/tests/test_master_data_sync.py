from qrmes_kingdee_integration.forms.master_data import MASTER_DATA_DEFINITIONS, MasterDataFormsService
from qrmes_kingdee_integration.sync.master_data_sync import MasterDataSyncService, build_master_data_business_key
from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore


class DummyClient:
    def __init__(self):
        self.queries = []

    def execute_bill_query(self, query):
        self.queries.append(query)
        return [["FID-001", "SUP-001", "供应商一", "C", "2026-04-01", "2026-04-02"]]


def test_master_data_forms_use_real_form_ids_and_safe_fields():
    client = DummyClient()
    service = MasterDataFormsService(client)

    rows = service.query_master_data("supplier", keyword="SUP'001", limit=500)

    assert rows[0][1] == "SUP-001"
    query = client.queries[0]
    assert query.form_id == "BD_Supplier"
    assert query.field_keys == "FID,FNumber,FName,FDocumentStatus,FCreateDate,FModifyDate"
    assert query.limit == 200
    assert "SUP''001" in query.filter_string


def test_master_data_business_key_fallbacks():
    assert build_master_data_business_key(["FID-001", "SUP-001", "供应商一"]) == "SUP-001"
    assert build_master_data_business_key(["FID-002", "", "无编码对象"]) == "FID-002"
    assert build_master_data_business_key(["", "", "仅名称", "C", "2026-04-01"]) == "仅名称|2026-04-01"


def test_master_data_sync_pulls_supplier_into_local_store(tmp_path):
    store = SQLiteSyncStore(tmp_path / "kingdee_sync.db")
    service = MasterDataSyncService(store=store, forms_service=MasterDataFormsService(DummyClient()), dataset="supplier")

    result = service.sync_from_kingdee(limit=100)
    saved = store.list_objects("supplier")

    assert result.ok is True
    assert result.data["synced_count"] == 1
    assert saved[0]["business_key"] == "SUP-001"
    assert saved[0]["form_id"] == "BD_Supplier"
    assert saved[0]["payload"]["name"] == "供应商一"


def test_master_data_definitions_cover_next_version_low_risk_datasets():
    assert {k: v.form_id for k, v in MASTER_DATA_DEFINITIONS.items()} == {
        "supplier": "BD_Supplier",
        "customer": "BD_Customer",
        "department": "BD_Department",
        "employee": "BD_Empinfo",
        "unit": "BD_UNIT",
        "organization": "ORG_Organizations",
        "material_category": "BD_MATERIALCATEGORY",
        "stock_status": "BD_STOCKSTATUS",
    }
