from qrmes_kingdee_integration.client.base import parse_response_status


def test_parse_response_status_returns_ok_for_success_payload():
    parsed = parse_response_status({"ResponseStatus": {"IsSuccess": True}, "Result": {"Number": "MO-001"}})

    assert parsed.ok is True
    assert parsed.data["payload"]["Number"] == "MO-001"
    assert parsed.data["errors"] == []


def test_parse_response_status_collects_errors_for_failed_payload():
    parsed = parse_response_status(
        {
            "ResponseStatus": {
                "IsSuccess": False,
                "Errors": [{"Message": "单据不存在", "FieldName": "Number"}],
                "MsgCode": "10",
            }
        }
    )

    assert parsed.ok is False
    assert parsed.data["msg_code"] == "10"
    assert parsed.data["errors"] == [{"field": "Number", "message": "单据不存在"}]
