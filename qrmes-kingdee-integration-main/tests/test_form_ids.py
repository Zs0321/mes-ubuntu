from qrmes_kingdee_integration.forms.batch_trace import (
    BATCH_SERIAL_RELATION_LIST_UI_FORM_ID,
    BATCH_SERIAL_RELATION_UI_FORM_ID,
    BATCH_SERIAL_TRACE_FILTER_FORM_ID,
    BATCH_SERIAL_TRACE_FORM_ID,
    BATCH_SERIAL_TRACE_UI_FORM_ID,
    BATCH_TRACE_FORM_ID,
    BATCH_TRACE_UI_FORM_ID,
    LOT_SERIAL_RELATION_FORM_ID,
    SERIAL_MASTER_FORM_ID,
    SERIAL_MASTER_UI_FORM_ID,
    SERIAL_TRACE_FILTER_FORM_ID,
    SERIAL_TRACE_FORM_ID,
    SERIAL_TRACE_UI_FORM_ID,
)
from qrmes_kingdee_integration.forms.production_order import (
    PRODUCTION_ORDER_FORM_ID,
    PRODUCTION_ORDER_UI_FORM_ID,
    PRODUCTION_ORDER_UI_LIST_FORM_ID,
)
from qrmes_kingdee_integration.forms.routing import ROUTING_FORM_ID, ROUTING_UI_FORM_ID, ROUTING_UI_LIST_FORM_ID
from qrmes_kingdee_integration.forms.warehouse import BIN_VALUE_SET_FORM_ID, WAREHOUSE_FORM_ID, WAREHOUSE_UI_FORM_ID


def test_confirmed_form_ids_match_verified_menu_codes_and_real_api_ids():
    assert ROUTING_UI_FORM_ID == "GYLX"
    assert ROUTING_UI_LIST_FORM_ID == "GYLXLB"
    assert ROUTING_FORM_ID == "ENG_ROUTE"
    assert PRODUCTION_ORDER_UI_FORM_ID == "SCDD"
    assert PRODUCTION_ORDER_UI_LIST_FORM_ID == "SCDDLB"
    assert PRODUCTION_ORDER_FORM_ID == "PRD_MO"
    assert WAREHOUSE_UI_FORM_ID == "CK"
    assert WAREHOUSE_FORM_ID == "BD_STOCK"
    assert BIN_VALUE_SET_FORM_ID == "CWZJ"
    assert BATCH_TRACE_UI_FORM_ID == "PHZS"
    assert BATCH_TRACE_FORM_ID == "STK_INVENTORY"
    assert SERIAL_MASTER_UI_FORM_ID == "XLHZD"
    assert SERIAL_MASTER_FORM_ID == "BD_SerialMainFile"
    assert BATCH_SERIAL_RELATION_UI_FORM_ID == "PHXLHGX"
    assert BATCH_SERIAL_RELATION_LIST_UI_FORM_ID == "PHXLHGXLB"
    assert LOT_SERIAL_RELATION_FORM_ID == "QT_LotSNRelation"
    assert SERIAL_TRACE_UI_FORM_ID == "XLHZS"
    assert SERIAL_TRACE_FORM_ID == "QT_TraceShow"
    assert SERIAL_TRACE_FILTER_FORM_ID == "QT_TraceFilter"
    assert BATCH_SERIAL_TRACE_UI_FORM_ID == "PHXLHZHZS"
    assert BATCH_SERIAL_TRACE_FORM_ID == "QT_TraceShow"
    assert BATCH_SERIAL_TRACE_FILTER_FORM_ID == "QT_TraceFilter"
