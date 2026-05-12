import json
import sqlite3


def test_log_ai_token_usage_writes_system_log(monkeypatch, tmp_path):
    from app_web.motor_qc.services import token_usage_logger as usage_logger

    monkeypatch.setattr(usage_logger, "_get_data_dir", lambda: tmp_path)
    db_path = tmp_path / "log" / "system_logs.db"

    usage_logger.log_ai_token_usage(
        provider="qwen",
        model="qwen-vl-max-latest",
        usage={"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
        image_path=str(tmp_path / "picture" / "P1" / "电机A" / "SN001" / "SN001_点胶_20260217_101010.jpg"),
        latency_ms=890,
        success=True,
        error_message="",
    )

    conn = sqlite3.connect(str(db_path), timeout=5)
    try:
        row = conn.execute(
            "SELECT action, target, details_json FROM system_logs WHERE action = 'AI_VISION_USAGE' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == "AI_VISION_USAGE"
    assert "qwen:qwen-vl-max-latest" in (row[1] or "")

    details = json.loads(row[2] or "{}")
    assert details.get("prompt_tokens") == 120
    assert details.get("completion_tokens") == 30
    assert details.get("total_tokens") == 150
    assert details.get("serial_number") == "SN001"


def test_extract_context_keeps_hyphenated_serial_for_qc_temp_name():
    from app_web.motor_qc.services import token_usage_logger as usage_logger

    context = usage_logger._extract_photo_context(
        "/tmp/qc__TZ310D-06A20002__后端盖打胶__0_abcd1234.jpg"
    )

    assert context.get("serial_number") == "TZ310D-06A20002"
    assert context.get("process_step") == "后端盖打胶"
