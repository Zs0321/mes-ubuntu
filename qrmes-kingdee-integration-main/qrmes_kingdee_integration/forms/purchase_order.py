from __future__ import annotations

from qrmes_kingdee_integration.client.base import KingdeeQuery

PURCHASE_ORDER_FORM_ID = "PUR_PurchaseOrder"


class PurchaseOrderFormsService:
    DEFAULT_LIST_FIELDS = "FBillNo,FDate,FSupplierId.FName"

    def __init__(self, client):
        self.client = client

    def query_purchase_orders(self, keyword: str = '', limit: int = 50):
        filter_string = ""
        if keyword.strip():
            safe = keyword.replace("'", "''")
            filter_string = f"FBillNo like '%{safe}%'"
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=PURCHASE_ORDER_FORM_ID,
                field_keys=self.DEFAULT_LIST_FIELDS,
                filter_string=filter_string,
                order_string='FDate desc',
                limit=min(max(limit, 1), 200),
            )
        )

    def view_purchase_order(self, number: str):
        return self.client.view(PURCHASE_ORDER_FORM_ID, {'Number': number})
