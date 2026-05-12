from __future__ import annotations

from qrmes_kingdee_integration.client.base import KingdeeQuery

WAREHOUSE_UI_FORM_ID = "CK"
BIN_VALUE_SET_UI_FORM_ID = "CWZJ"
OUTSOURCE_WAREHOUSE_SETTING_UI_FORM_ID = "WWCKSZ"

WAREHOUSE_FORM_ID = "BD_STOCK"
BIN_VALUE_SET_FORM_ID = "CWZJ"
OUTSOURCE_WAREHOUSE_SETTING_FORM_ID = "WWCKSZ"


class WarehouseFormsService:
    DEFAULT_LIST_FIELDS = "FNumber,FName,FUseOrgId.FName,FForbidStatus"

    def __init__(self, client):
        self.client = client

    def query_warehouses(self, keyword: str = "", limit: int = 50):
        filter_string = ""
        if keyword.strip():
            safe = keyword.replace("'", "''")
            filter_string = f"FNumber like '%{safe}%' or FName like '%{safe}%'"
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=WAREHOUSE_FORM_ID,
                field_keys=self.DEFAULT_LIST_FIELDS,
                filter_string=filter_string,
                order_string="FNumber asc",
                limit=min(max(limit, 1), 200),
            )
        )

    def view_warehouse(self, number: str):
        return self.client.view(WAREHOUSE_FORM_ID, {"Number": number})
