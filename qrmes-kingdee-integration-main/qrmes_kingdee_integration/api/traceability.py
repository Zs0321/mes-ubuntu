from __future__ import annotations

from flask import Blueprint, jsonify, request

from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.traceability.formids import formid_registry, legacy_formid_plan_items
from qrmes_kingdee_integration.traceability.store import TraceabilityStore


FORMID_PLAN_ITEMS = [
    {
        "form_id": "PUR_PurchaseOrder",
        "name": "采购订单",
        "usage": "收货贴标的来源单据；当前已从本地 kingdee_objects/purchase_order 读取。",
        "status": "available_local_read",
    },
    {
        "form_id": "PUR_ReceiveBill",
        "name": "采购收料/收料通知",
        "usage": "后续把收货贴标结果写回金蝶收料明细或自定义字段的候选对象。",
        "status": "pending_confirmation",
    },
    {
        "form_id": "STK_InStock",
        "name": "采购入库单",
        "usage": "入库动作的金蝶写回候选对象。",
        "status": "pending_confirmation",
    },
    {
        "form_id": "STK_INVENTORY",
        "name": "即时库存",
        "usage": "批次库存基础查询；当前已有基础同步能力。",
        "status": "available_local_read",
    },
    {
        "form_id": "STK_LOTADJUST",
        "name": "批号调整单",
        "usage": "批次调整/回写候选；已有基础批次链路可复用但字段需校准。",
        "status": "field_mapping_required",
    },
    {
        "form_id": "BD_MATERIAL",
        "name": "物料",
        "usage": "物料编码、名称、单位等基础资料。",
        "status": "available_local_read",
    },
    {
        "form_id": "BD_Supplier",
        "name": "供应商",
        "usage": "供应商编码与供应商二维码映射来源。",
        "status": "available_local_read",
    },
    {
        "form_id": "BD_STOCK",
        "name": "仓库/仓位基础资料",
        "usage": "入库仓位校验和库存落点。",
        "status": "field_mapping_required",
    },
    {
        "form_id": "QMS/IQC",
        "name": "质量/来料检对象",
        "usage": "来料检报告和判定结果写回；需通过账套搜索或前端 XHR 确认真实 FormId。",
        "status": "pending_confirmation",
    },
    {
        "form_id": "CUSTOM_QR_FIELDS",
        "name": "二维码写回自定义字段",
        "usage": "优先建议加到采购收料/入库单明细，或批次/序列号主档。",
        "status": "design_required",
    },
]


def create_traceability_blueprint(sync_store: SQLiteSyncStore) -> Blueprint:
    bp = Blueprint("traceability", __name__, url_prefix="/api/traceability")
    store = TraceabilityStore(sync_store)

    @bp.get("/health")
    def health():
        return jsonify({
            "service": "material-traceability",
            "mode": "local_sqlite_only",
            "db_path": str(store.db_path),
            "tables": [
                "material_batch", "material_package", "supplier_qr_map", "receive_record",
                "iqc_record", "inventory_stock", "stock_move", "pick_record",
                "assembly_bind", "trace_event_log", "material_qrcode", "label_print_task",
                "code_sequences", "pcba_transform", "test_record", "shipment_record",
            ],
        })

    @bp.get("/purchase-orders")
    def purchase_orders():
        rows = store.list_purchase_orders(
            keyword=str(request.args.get("keyword") or ""),
            limit=int(request.args.get("limit", "50") or "50"),
        )
        return jsonify({"rows": rows})

    @bp.post("/receive-label")
    def receive_label():
        return _json_call(store.receive_label, request.get_json(silent=True) or {})

    @bp.post("/receive-labels")
    def receive_labels():
        return _json_call(store.receive_label, request.get_json(silent=True) or {})

    @bp.get("/batches/<path:batch_code>")
    def get_batch(batch_code: str):
        result = store.get_batch(batch_code)
        if not result:
            return jsonify({"error": "BATCH_NOT_FOUND", "message": f"批次不存在: {batch_code}"}), 404
        return jsonify(result)

    @bp.post("/iqc")
    def iqc():
        return _json_call(store.record_iqc, request.get_json(silent=True) or {})

    @bp.post("/putaway")
    def putaway():
        return _json_call(store.putaway, request.get_json(silent=True) or {})

    @bp.post("/stock-in")
    def stock_in():
        return _json_call(store.putaway, request.get_json(silent=True) or {})

    @bp.post("/pick")
    def pick():
        return _json_call(store.pick, request.get_json(silent=True) or {})

    @bp.post("/assembly-bind")
    def assembly_bind():
        return _json_call(store.assembly_bind, request.get_json(silent=True) or {})

    @bp.get("/trace/<path:code>")
    def trace(code: str):
        return jsonify(store.trace(code))

    @bp.get("/query")
    def query():
        code = (
            request.args.get("code")
            or request.args.get("package_code")
            or request.args.get("batch_code")
            or request.args.get("product_sn")
            or ""
        ).strip()
        if not code:
            return jsonify({"error": "VALIDATION_ERROR", "message": "code, batch_code, package_code, or product_sn is required"}), 400
        return jsonify(store.trace(code))

    @bp.get("/print-tasks")
    def print_tasks():
        status = str(request.args.get("status") or "").strip()
        limit = int(request.args.get("limit", "100") or "100")
        return jsonify({"rows": store.list_print_tasks(status=status, limit=limit)})

    @bp.get("/formids")
    def formids():
        return jsonify(formid_registry())

    @bp.get("/formid-plan")
    def formid_plan():
        return jsonify({
            "mode": "local_sqlite_mvp_no_unknown_kingdee_writeback",
            "items": legacy_formid_plan_items() or FORMID_PLAN_ITEMS,
        })

    return bp


def _json_call(func, payload: dict):
    try:
        return jsonify(func(payload))
    except ValueError as exc:
        return jsonify({"error": "VALIDATION_ERROR", "message": str(exc)}), 400
    except KeyError as exc:
        return jsonify({"error": "NOT_FOUND", "message": str(exc).strip("'")}), 404
