from __future__ import annotations

from qrmes_kingdee_integration.client.base import KingdeeQuery

BATCH_TRACE_UI_FORM_ID = "PHZS"
SERIAL_MASTER_UI_FORM_ID = "XLHZD"
BATCH_SERIAL_TRACE_UI_FORM_ID = "PHXLHZHZS"
BATCH_SERIAL_RELATION_UI_FORM_ID = "PHXLHGX"
BATCH_SERIAL_RELATION_LIST_UI_FORM_ID = "PHXLHGXLB"
SERIAL_TRACE_UI_FORM_ID = "XLHZS"
MES_PROCESS_TRACE_UI_FORM_ID = "DJCPJGGCZS"

BATCH_TRACE_FORM_ID = "STK_INVENTORY"
BATCH_TRACE_SAVE_FORM_ID = "STK_LOTADJUST"
SERIAL_MASTER_FORM_ID = "BD_SerialMainFile"
LOT_SERIAL_RELATION_FORM_ID = "QT_LotSNRelation"
SERIAL_TRACE_FORM_ID = "QT_TraceShow"
SERIAL_TRACE_FILTER_FORM_ID = "QT_TraceFilter"
BATCH_SERIAL_TRACE_FORM_ID = "QT_TraceShow"
BATCH_SERIAL_TRACE_FILTER_FORM_ID = "QT_TraceFilter"
MES_PROCESS_TRACE_GATE_FORM_ID = "BOS_FreeTrailForModel"


class BatchTraceFormsService:
    DEFAULT_LIST_FIELDS = "FMaterialId.FNumber,FStockId.FNumber,FLot.FNumber"
    SERIAL_MASTER_FIELDS = "FNumber,FMaterialId.FNumber,FStockId.FNumber,FDocumentStatus,FCreateDate"
    LOT_SERIAL_RELATION_FIELDS = "FID,FLot.FNumber,FSerialNo,FMaterialId.FNumber,FDocumentStatus"

    def __init__(self, client):
        self.client = client

    def query_batch_trace(self, keyword: str = '', limit: int = 50):
        filter_string = ""
        if keyword.strip():
            safe = keyword.replace("'", "''")
            filter_string = f"FLot.FNumber like '%{safe}%' or FMaterialId.FNumber like '%{safe}%'"
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=BATCH_TRACE_FORM_ID,
                field_keys=self.DEFAULT_LIST_FIELDS,
                filter_string=filter_string,
                order_string='FMaterialId.FNumber asc',
                limit=min(max(limit, 1), 200),
            )
        )

    def view_batch_trace(self, number: str):
        return self.client.view(BATCH_TRACE_SAVE_FORM_ID, {'Number': number})

    def query_serial_master(self, keyword: str = '', limit: int = 50):
        filter_string = ''
        if keyword.strip():
            safe = keyword.replace("'", "''")
            filter_string = (
                f"FNumber like '%{safe}%' or "
                f"FMaterialId.FNumber like '%{safe}%' or "
                f"FStockId.FNumber like '%{safe}%'"
            )
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=SERIAL_MASTER_FORM_ID,
                field_keys=self.SERIAL_MASTER_FIELDS,
                filter_string=filter_string,
                order_string='FCreateDate desc',
                limit=min(max(limit, 1), 200),
            )
        )

    def view_serial_master(self, number: str):
        return self.client.view(SERIAL_MASTER_FORM_ID, {'Number': number})

    def query_lot_serial_relation(self, keyword: str = '', limit: int = 50):
        filter_string = ''
        if keyword.strip():
            safe = keyword.replace("'", "''")
            filter_string = (
                f"FSerialNo like '%{safe}%' or "
                f"FLot like '%{safe}%' or "
                f"FLot.FNumber like '%{safe}%' or "
                f"FMaterialId.FNumber like '%{safe}%' or "
                f"FBillNo like '%{safe}%'"
            )
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=LOT_SERIAL_RELATION_FORM_ID,
                field_keys=self.LOT_SERIAL_RELATION_FIELDS,
                filter_string=filter_string,
                order_string='FCreateDate desc',
                limit=min(max(limit, 1), 200),
            )
        )

    def view_lot_serial_relation(self, relation_id: str):
        return self.client.view(LOT_SERIAL_RELATION_FORM_ID, {'Id': relation_id})
