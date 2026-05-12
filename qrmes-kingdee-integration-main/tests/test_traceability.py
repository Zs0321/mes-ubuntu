import json
import sqlite3

from qrmes_kingdee_integration.api.app import create_app
from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.traceability.coding import (
    build_qr_payload,
    generate_batch_code,
    generate_package_code,
    generate_pcba_batch_code,
    generate_serial_code,
)


def test_traceability_coding_rules_are_stable_and_json_payload_is_sorted():
    assert generate_batch_code("MAT-001", "SUP-9", "2026-04-27", 7) == "ML|MAT-001|SUP-9|20260427|0007"
    assert generate_package_code("ML|MAT-001|SUP-9|20260427|0007", 2) == "PK|ML|MAT-001|SUP-9|20260427|0007|02"
    assert generate_serial_code("MAT-001", "20260427", 12) == "SN|MAT-001|20260427|000012"
    assert generate_pcba_batch_code("LINE-A", "2026-04-27", 3) == "PCBA|LINE-A|20260427|0003"

    payload = build_qr_payload(
        code_type="package",
        code="PK|ML|M|S|20260427|0001|01",
        material_code="M",
        supplier_code="供应商A",
        batch_code="ML|M|S|20260427|0001",
        pack_index=1,
        qty=5,
        unit="PCS",
        trace_mode="batch_package",
    )

    assert json.loads(payload)["supplier_code"] == "供应商A"
    assert payload.index('"batch_code"') < payload.index('"code"') < payload.index('"code_type"')


def test_receive_label_writes_batch_packages_inventory_events_and_qr_jobs(tmp_path):
    store = SQLiteSyncStore(tmp_path / "kingdee_sync.db")
    store.upsert_object(
        dataset="purchase_order",
        business_key="PO-001",
        form_id="PUR_PurchaseOrder",
        payload={"number": "PO-001", "supplier_code": "SUP-9", "material_code": "MAT-001"},
        source="kingdee",
    )
    app = create_app(store=store)
    client = app.test_client()

    resp = client.post(
        "/api/traceability/receive-label",
        json={
            "purchase_no": "PO-001",
            "material_code": "MAT-001",
            "supplier_code": "SUP-9",
            "qty": 10,
            "unit": "PCS",
            "package_count": 2,
            "receive_date": "2026-04-27",
            "supplier_qr_raw": "供应商原始码",
            "operator": "张三",
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["batch_code"] == "ML|MAT-001|SUP-9|20260427|0001"
    assert [item["package_code"] for item in payload["packages"]] == [
        "PK|ML|MAT-001|SUP-9|20260427|0001|01",
        "PK|ML|MAT-001|SUP-9|20260427|0001|02",
    ]
    assert json.loads(payload["packages"][0]["qr_payload"])["qty"] == 5

    batch = client.get("/api/traceability/batches/ML|MAT-001|SUP-9|20260427|0001").get_json()
    assert batch["batch"]["batch_status"] == "pending_iqc"
    assert len(batch["packages"]) == 2
    assert batch["inventory"][0]["status"] == "pending_iqc"
    assert batch["qrcodes"][0]["code_type"] == "batch"


def test_receive_labels_new_route_uses_sequence_table_and_creates_print_tasks(tmp_path):
    store = SQLiteSyncStore(tmp_path / "kingdee_sync.db")
    app = create_app(store=store)
    client = app.test_client()

    for _ in range(2):
        resp = client.post(
            "/api/traceability/receive-labels",
            json={
                "purchase_no": "PO-SEQ",
                "material_code": "MAT-SEQ",
                "supplier_code": "SUP-SEQ",
                "qty": 12,
                "unit": "PCS",
                "package_count": 3,
                "receive_date": "2026-04-27",
            },
        )
        assert resp.status_code == 200

    first = client.get("/api/traceability/query?batch_code=ML|MAT-SEQ|SUP-SEQ|20260427|0001").get_json()
    second = client.get("/api/traceability/query?batch_code=ML|MAT-SEQ|SUP-SEQ|20260427|0002").get_json()
    assert first["batch"]["batch_code"].endswith("|0001")
    assert second["batch"]["batch_code"].endswith("|0002")

    tasks = client.get("/api/traceability/print-tasks").get_json()
    assert tasks["rows"][0]["status"] == "pending"
    assert tasks["rows"][0]["printer_type"] == "zebra"
    assert json.loads(tasks["rows"][0]["qr_payload"])["code_type"] == "batch"
    assert len(tasks["rows"]) == 8

    with sqlite3.connect(store.db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("select name from sqlite_master where type='table'").fetchall()
        }
    assert {
        "code_sequences",
        "pcba_transform",
        "test_record",
        "shipment_record",
        "label_print_task",
    } <= tables


def test_iqc_putaway_pick_assembly_and_trace_chain(tmp_path):
    store = SQLiteSyncStore(tmp_path / "kingdee_sync.db")
    app = create_app(store=store)
    client = app.test_client()
    receive = client.post(
        "/api/traceability/receive-label",
        json={
            "purchase_no": "PO-002",
            "material_code": "MAT-002",
            "supplier_code": "SUP-2",
            "qty": 8,
            "unit": "PCS",
            "package_count": 1,
            "receive_date": "2026-04-27",
            "operator": "收货员",
        },
    ).get_json()
    batch_code = receive["batch_code"]
    package_code = receive["packages"][0]["package_code"]

    iqc = client.post(
        "/api/traceability/iqc",
        json={
            "batch_code": batch_code,
            "result": "qualified",
            "report_no": "IQC-001",
            "inspector": "检验员",
            "remark": "OK",
            "attachments": ["report.pdf"],
        },
    )
    putaway = client.post(
        "/api/traceability/stock-in",
        json={"code": package_code, "location_code": "A-01", "qty": 8, "operator": "仓管"},
    )
    pick = client.post(
        "/api/traceability/pick",
        json={
            "work_order_no": "MO-001",
            "product_sn": "PROD-SN-001",
            "material_code": "MAT-002",
            "code": package_code,
            "qty": 2,
            "operator": "配料员",
        },
    )
    bind = client.post(
        "/api/traceability/assembly-bind",
        json={
            "product_sn": "PROD-SN-001",
            "material_code": "MAT-002",
            "package_code": package_code,
            "bind_qty": 2,
            "position_code": "U1",
            "operator": "装配员",
        },
    )

    assert iqc.status_code == 200
    assert putaway.status_code == 200
    assert pick.status_code == 200
    assert bind.status_code == 200

    trace = client.get(f"/api/traceability/query?package_code={package_code}").get_json()
    assert trace["query"]["code"] == package_code
    assert trace["batch"]["batch_code"] == batch_code
    assert trace["packages"][0]["package_code"] == package_code
    assert trace["iqc_records"][0]["result"] == "qualified"
    assert trace["stock_moves"][-1]["move_type"] == "pick"
    assert trace["assembly_binds"][0]["product_sn"] == "PROD-SN-001"

    product_trace = client.get("/api/traceability/query?product_sn=PROD-SN-001").get_json()
    assert product_trace["assembly_binds"][0]["package_code"] == package_code


def test_iqc_attachments_are_saved_and_trace_returns_metadata(tmp_path):
    store = SQLiteSyncStore(tmp_path / "kingdee_sync.db")
    app = create_app(store=store)
    client = app.test_client()
    receive = client.post(
        "/api/traceability/receive-label",
        json={
            "purchase_no": "PO-ATT",
            "material_code": "MAT-ATT",
            "supplier_code": "SUP-ATT",
            "qty": 1,
            "unit": "PCS",
            "package_count": 1,
            "receive_date": "2026-04-27",
        },
    ).get_json()

    resp = client.post(
        "/api/traceability/iqc",
        json={
            "batch_code": receive["batch_code"],
            "result": "qualified",
            "report_no": "RPT-ATT-001",
            "inspector": "检验员A",
            "attachments": [
                {
                    "filename": "report.txt",
                    "content_type": "text/plain",
                    "size": 5,
                    "content_base64": "aGVsbG8=",
                    "note": "原始报告",
                }
            ],
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["attachments"][0]["filename"] == "report.txt"
    assert payload["attachments"][0]["size"] == 5
    assert "content_base64" not in payload["attachments"][0]

    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("select * from iqc_attachment").fetchall()
    assert len(rows) == 1
    assert rows[0]["ref_no"] == payload["iqc_no"]
    assert rows[0]["batch_code"] == receive["batch_code"]
    assert rows[0]["content_base64"] == "aGVsbG8="

    trace = client.get(f"/api/traceability/query?batch_code={receive['batch_code']}").get_json()
    assert trace["iqc_records"][0]["attachments"][0]["filename"] == "report.txt"
    assert trace["iqc_attachments"][0]["attachment_id"] == payload["attachments"][0]["attachment_id"]
    assert "content_base64" not in trace["iqc_attachments"][0]


def test_purchase_order_search_and_formid_plan_endpoint(tmp_path):
    store = SQLiteSyncStore(tmp_path / "kingdee_sync.db")
    store.upsert_object(
        dataset="purchase_order",
        business_key="CG-2026-001",
        form_id="PUR_PurchaseOrder",
        payload={"number": "CG-2026-001", "supplier_name": "华东供应商"},
        source="kingdee",
    )
    app = create_app(store=store)
    client = app.test_client()

    orders = client.get("/api/traceability/purchase-orders?keyword=华东&limit=5").get_json()
    plan = client.get("/api/traceability/formids").get_json()

    assert orders["rows"][0]["business_key"] == "CG-2026-001"
    assert "PUR_PurchaseOrder" in {item["form_id"] for item in plan["verified_api"]}
    assert "SCDD" in {item["code"] for item in plan["ui_menu"]}
    assert "QT_TraceShow" in {item["form_id"] for item in plan["runtime_bridge"]}
    assert any(item["status"] == "pending_confirmation" for item in plan["pending"])
