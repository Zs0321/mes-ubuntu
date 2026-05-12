from __future__ import annotations

from qrmes_kingdee_integration.client.base import KingdeeQuery

MATERIAL_FORM_ID = "BD_MATERIAL"


class MaterialsFormsService:
    DEFAULT_LIST_FIELDS = "FNumber,FName,FSpecification"

    def __init__(self, client):
        self.client = client

    def query_materials(self, keyword: str = '', limit: int = 50):
        filter_string = ""
        if keyword.strip():
            safe = keyword.replace("'", "''")
            filter_string = f"FNumber like '%{safe}%' or FName like '%{safe}%'"
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=MATERIAL_FORM_ID,
                field_keys=self.DEFAULT_LIST_FIELDS,
                filter_string=filter_string,
                order_string='FNumber asc',
                limit=min(max(limit, 1), 200),
            )
        )

    def view_material(self, number: str):
        return self.client.view(MATERIAL_FORM_ID, {'Number': number})
