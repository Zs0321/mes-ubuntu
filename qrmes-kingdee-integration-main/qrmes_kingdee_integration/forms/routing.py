from __future__ import annotations

from qrmes_kingdee_integration.client.base import KingdeeQuery

ROUTING_UI_FORM_ID = "GYLX"
ROUTING_UI_LIST_FORM_ID = "GYLXLB"
ROUTING_LINE_UI_FORM_ID = "GYLXCX"
ROUTING_LINE_UI_LIST_FORM_ID = "GYLXCXLB"

ROUTING_FORM_ID = "ENG_ROUTE"
ROUTING_LIST_FORM_ID = "ENG_ROUTE"

PROCESS_RELATED_FORM_IDS = [
    "GXHB",
    "GXHBLB",
    "GXJHLB",
    "GXZYD",
    "GXKZM",
    "GXKZMLB",
]


class RoutingFormsService:
    DEFAULT_LIST_FIELDS = "FNumber,FName,FUseOrgId.FName,FDocumentStatus"

    def __init__(self, client):
        self.client = client

    def query_routings(self, keyword: str = "", limit: int = 50):
        filter_string = ""
        if keyword.strip():
            safe = keyword.replace("'", "''")
            filter_string = f"FNumber like '%{safe}%' or FName like '%{safe}%'"
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=ROUTING_FORM_ID,
                field_keys=self.DEFAULT_LIST_FIELDS,
                filter_string=filter_string,
                order_string="FNumber asc",
                limit=min(max(limit, 1), 200),
            )
        )

    def view_routing(self, number: str):
        return self.client.view(ROUTING_FORM_ID, {"Number": number})
