from qrmes_kingdee_integration.client.base import KingdeeClient, KingdeeQuery
from qrmes_kingdee_integration.config import KingdeeRuntimeConfig


def _config() -> KingdeeRuntimeConfig:
    return KingdeeRuntimeConfig(
        base_url="http://example.com/k3cloud",
        db_id="db-001",
        username="tester",
        app_id="app-001",
        app_secret="secret-001",
        lcid=2052,
        timeout_seconds=15,
        verify_ssl=True,
    )


def test_kingdee_query_payload_contains_expected_fields():
    payload = KingdeeQuery(
        form_id="BD_MATERIAL",
        field_keys="FNumber,FName",
        filter_string="FNumber <> ''",
        order_string="FNumber asc",
        start_row=5,
        limit=50,
    ).to_payload()

    assert payload == {
        "FormId": "BD_MATERIAL",
        "FieldKeys": "FNumber,FName",
        "FilterString": "FNumber <> ''",
        "OrderString": "FNumber asc",
        "TopRowCount": 0,
        "StartRow": 5,
        "Limit": 50,
        "SubSystemId": "",
    }


def test_build_login_payload_uses_signed_login_fields():
    client = KingdeeClient(_config())

    payload = client.build_login_payload(timestamp=1765419679)

    assert payload["acctID"] == "db-001"
    assert payload["username"] == "tester"
    assert payload["appId"] == "app-001"
    assert payload["timestamp"] == 1765419679
    assert payload["lcid"] == 2052
    assert len(payload["sign"]) == 64
