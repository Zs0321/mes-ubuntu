from qrmes_kingdee_integration.client.base import KingdeeQuery
from qrmes_kingdee_integration.forms.batch_trace import BatchTraceFormsService


class DummyClient:
    def __init__(self):
        self.queries = []
        self.views = []

    def execute_bill_query(self, query: KingdeeQuery):
        self.queries.append(query)
        return [[query.form_id, query.field_keys, query.filter_string]]

    def view(self, form_id: str, data: dict):
        self.views.append((form_id, data))
        return {'Result': {'ResponseStatus': {'IsSuccess': True}, 'Result': data}}


def test_batch_trace_service_uses_real_api_inventory_form():
    client = DummyClient()
    rows = BatchTraceFormsService(client).query_batch_trace(keyword='20250101')

    assert rows[0][0] == 'STK_INVENTORY'
    assert "FLot.FNumber like '%20250101%'" in rows[0][2]
