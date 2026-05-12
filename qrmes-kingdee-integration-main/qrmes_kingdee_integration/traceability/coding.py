from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def _compact_date(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value or "").strip()
    if not text:
        raise ValueError("date is required")
    if len(text) == 8 and text.isdigit():
        return text
    return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%Y%m%d")


def generate_batch_code(material_code: str, supplier_code: str, receive_date: str | date | datetime, sequence: int) -> str:
    return f"ML|{str(material_code).strip()}|{str(supplier_code).strip()}|{_compact_date(receive_date)}|{int(sequence):04d}"


def generate_package_code(batch_code: str, package_index: int) -> str:
    return f"PK|{str(batch_code).strip()}|{int(package_index):02d}"


def generate_serial_code(material_code: str, date_value: str | date | datetime, sequence: int) -> str:
    return f"SN|{str(material_code).strip()}|{_compact_date(date_value)}|{int(sequence):06d}"


def generate_pcba_batch_code(line_code: str, date_value: str | date | datetime, sequence: int) -> str:
    return f"PCBA|{str(line_code).strip()}|{_compact_date(date_value)}|{int(sequence):04d}"


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def build_qr_payload(
    *,
    code_type: str,
    code: str,
    material_code: str,
    supplier_code: str = "",
    batch_code: str = "",
    pack_index: int | None = None,
    qty: int | float | str | None = None,
    unit: str = "",
    trace_mode: str = "batch_package",
    **extra: Any,
) -> str:
    payload = {
        "code_type": code_type,
        "code": code,
        "material_code": material_code,
        "supplier_code": supplier_code,
        "batch_code": batch_code,
        "pack_index": pack_index,
        "qty": qty,
        "unit": unit,
        "trace_mode": trace_mode,
    }
    payload.update({key: value for key, value in extra.items() if value is not None})
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)
