import json

from qrmes_kingdee_integration.client.base import KingdeeClient, KingdeeQuery
from qrmes_kingdee_integration.config import KingdeeRuntimeConfig


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, timeout=None, verify=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout, "verify": verify})
        if url.endswith(KingdeeClient.LOGIN_PATH):
            return FakeResponse({"LoginResultType": 1})
        if url.endswith(KingdeeClient.BILL_QUERY_PATH):
            return FakeResponse([["MO-001", "MAT-001"]])
        if url.endswith(KingdeeClient.VIEW_PATH):
            return FakeResponse({"Result": {"ResponseStatus": {"IsSuccess": True}, "Result": {"Number": "MO-001"}}})
        if url.endswith(KingdeeClient.SAVE_PATH):
            return FakeResponse({"Result": {"ResponseStatus": {"IsSuccess": True}, "Result": {"Number": "MO-001"}}})
        raise AssertionError(f"Unexpected URL: {url}")


def _config() -> KingdeeRuntimeConfig:
    return KingdeeRuntimeConfig(
        base_url="http://example.com/k3cloud",
        db_id="db-001",
        username="tester",
        app_id="app-001",
        app_secret="secret-001",
        lcid=2052,
        timeout_seconds=15,
        verify_ssl=False,
    )


def test_execute_bill_query_logs_in_then_posts_query():
    session = FakeSession()
    client = KingdeeClient(_config(), session=session)

    rows = client.execute_bill_query(KingdeeQuery(form_id="SCDD", field_keys="FBillNo,FMaterialId.FNumber"))

    assert rows == [["MO-001", "MAT-001"]]
    assert len(session.calls) == 2
    assert session.calls[0]["url"].endswith(KingdeeClient.LOGIN_PATH)
    assert session.calls[1]["url"].endswith(KingdeeClient.BILL_QUERY_PATH)
    assert json.loads(session.calls[1]["json"]["data"])["FormId"] == "SCDD"
    assert session.calls[1]["verify"] is False


def test_view_posts_formid_and_data_payload():
    session = FakeSession()
    client = KingdeeClient(_config(), session=session)

    payload = client.view("SCDD", {"Number": "MO-001"})

    assert payload["Result"]["Result"]["Number"] == "MO-001"
    assert len(session.calls) == 2
    assert session.calls[1]["json"]["formid"] == "SCDD"
    assert json.loads(session.calls[1]["json"]["data"]) == {"Number": "MO-001"}


def test_save_posts_formid_and_model_payload():
    session = FakeSession()
    client = KingdeeClient(_config(), session=session)

    payload = client.save("SCDD", {"Number": "MO-001", "FNote": "x"})

    assert payload["Result"]["Result"]["Number"] == "MO-001"
    assert len(session.calls) == 2
    assert session.calls[1]["url"].endswith(KingdeeClient.SAVE_PATH)
    assert session.calls[1]["json"]["formid"] == "SCDD"
    assert json.loads(session.calls[1]["json"]["data"]) == {"Number": "MO-001", "FNote": "x"}
