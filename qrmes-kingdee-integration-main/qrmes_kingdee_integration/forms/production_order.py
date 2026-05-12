from __future__ import annotations

from qrmes_kingdee_integration.client.base import KingdeeQuery

PRODUCTION_ORDER_UI_FORM_ID = "SCDD"
PRODUCTION_ORDER_UI_LIST_FORM_ID = "SCDDLB"
PRODUCTION_MATERIAL_LIST_UI_FORM_ID = "SCYLQDLB"
PRODUCTION_MATERIAL_CHANGE_UI_FORM_ID = "SCYLQDBGD"
PRODUCTION_MATERIAL_CHANGE_LIST_UI_FORM_ID = "SCYLQDBGDLB"

PRODUCTION_ORDER_FORM_ID = "PRD_MO"
PRODUCTION_OPERATION_PLANNING_FORM_ID = "SFC_OperationPlanning"
PRODUCTION_OPERATION_REPORT_FORM_ID = "SFC_OperationReport"


class ProductionOrderFormsService:
    DEFAULT_LIST_FIELDS = "FBillNo,FMaterialId.FNumber,FRptFinishQty"

    def __init__(self, client):
        self.client = client

    def query_orders(self, limit: int = 50, filter_string: str = ""):
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=PRODUCTION_ORDER_FORM_ID,
                field_keys=self.DEFAULT_LIST_FIELDS,
                filter_string=filter_string,
                order_string="FBillNo desc",
                limit=min(max(limit, 1), 200),
            )
        )

    def view_order(self, bill_no: str):
        return self.client.view(PRODUCTION_ORDER_FORM_ID, {"Number": bill_no})
