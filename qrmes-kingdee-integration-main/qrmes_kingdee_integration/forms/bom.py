from __future__ import annotations

from qrmes_kingdee_integration.client.base import KingdeeQuery

BOM_FORM_ID = "ENG_BOM"


class BomFormsService:
    DEFAULT_LIST_FIELDS = "FNumber,FName,FMATERIALID.FNumber"

    def __init__(self, client):
        self.client = client

    def query_boms(self, keyword: str = '', limit: int = 50):
        filter_string = ""
        if keyword.strip():
            safe = keyword.replace("'", "''")
            filter_string = f"FNumber like '%{safe}%' or FName like '%{safe}%'"
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=BOM_FORM_ID,
                field_keys=self.DEFAULT_LIST_FIELDS,
                filter_string=filter_string,
                order_string='FNumber asc',
                limit=min(max(limit, 1), 200),
            )
        )

    def view_bom(self, number: str):
        return self.client.view(BOM_FORM_ID, {'Number': number})
