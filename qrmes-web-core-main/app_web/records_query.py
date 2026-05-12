"""Records query helpers."""

import json
from typing import Any, Dict, Iterable, List, Tuple

_NON_MATERIAL_KEYS = {
    "产品序列号",
    "product_serial",
    "产品类型",
    "product_type",
    "项目名称",
    "project_name",
    "操作员",
    "operator",
    "扫描时间",
    "scan_time",
}


def build_records_query(
    project: str = "",
    serial: str = "",
    operator: str = "",
    date_from: str = "",
    date_to: str = "",
    exact_serial: bool = False,
) -> Tuple[str, List[str]]:
    """Build SQL and parameters for /api/records filtering.

    Notes:
    - scan_time is stored as milliseconds since epoch.
    - SQLite DATE() requires unixepoch conversion for integer timestamps.
    """
    where_clauses: List[str] = ["1=1"]
    params: List[str] = []

    if project:
        where_clauses.append("project_name = ?")
        params.append(project)

    if serial:
        if exact_serial:
            where_clauses.append("product_serial = ?")
            params.append(serial)
        else:
            where_clauses.append("product_serial LIKE ?")
            params.append(f"%{serial}%")

    if operator:
        where_clauses.append("operator LIKE ?")
        params.append(f"%{operator}%")

    if date_from:
        where_clauses.append("DATE(scan_time / 1000, 'unixepoch', 'localtime') >= ?")
        params.append(date_from)

    if date_to:
        where_clauses.append("DATE(scan_time / 1000, 'unixepoch', 'localtime') <= ?")
        params.append(date_to)

    where_sql = " AND ".join(where_clauses)
    # 先返回明细行，去重与物料合并在 Python 层完成。
    query = f"""
        SELECT *
        FROM product_records
        WHERE {where_sql}
        ORDER BY scan_time DESC
        LIMIT 5000
    """
    return query, params


def convert_record_row(row: Any) -> Dict[str, Any]:
    """Convert sqlite row to API record shape safely.

    The current DB schema doesn't guarantee optional columns
    (station/result/remark), so we default them to empty strings.
    """
    row_keys = set(row.keys()) if hasattr(row, "keys") else set()

    def get_optional(key: str) -> Any:
        if key in row_keys:
            return row[key]
        return ""

    return {
        "product_serial": row["product_serial"],
        "product_type": row["product_type"],
        "project_name": row["project_name"],
        "operator": row["operator"],
        "scan_time": row["scan_time"],
        "materials": get_optional("materials"),
        # 历史前端使用 raw_data 读取组件信息，这里保持兼容。
        "raw_data": get_optional("materials") or get_optional("raw_data"),
        "station": get_optional("station"),
        "result": get_optional("result"),
        "remark": get_optional("remark"),
    }


def _parse_materials(materials_value: Any, raw_data_value: Any) -> Dict[str, Any]:
    for candidate in (materials_value, raw_data_value):
        if isinstance(candidate, dict):
            return candidate
        if isinstance(candidate, str) and candidate.strip():
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    return {}


def parse_material_map(materials_value: Any, raw_data_value: Any) -> Dict[str, Any]:
    """Public wrapper for parsing material payload."""
    return _parse_materials(materials_value, raw_data_value)


def _is_effective_material_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return text not in {"", "nan", "None", "null", "-"}


def _normalize_material_name(name: str) -> str:
    return str(name or "").strip().lower()


def extract_recorded_materials(material_map: Dict[str, Any]) -> Dict[str, Any]:
    """Extract non-empty material fields from parsed record payload."""
    if not isinstance(material_map, dict):
        return {}
    return {
        str(key).strip(): value
        for key, value in material_map.items()
        if str(key).strip()
        and str(key).strip() not in _NON_MATERIAL_KEYS
        and _is_effective_material_value(value)
    }


def compute_material_status(
    required_materials: List[str], materials_value: Any, raw_data_value: Any
) -> Dict[str, Any]:
    """Compute material completeness summary for a record."""
    required_names: List[str] = []
    required_norms = set()
    for material_name in required_materials or []:
        display_name = str(material_name or "").strip()
        if not display_name:
            continue
        normalized = _normalize_material_name(display_name)
        if not normalized or normalized in required_norms:
            continue
        required_norms.add(normalized)
        required_names.append(display_name)

    material_map = parse_material_map(materials_value, raw_data_value)
    recorded_map = extract_recorded_materials(material_map)
    recorded_norms = {_normalize_material_name(name) for name in recorded_map.keys()}
    recorded_norms.discard("")

    recorded_count = sum(1 for name in required_names if _normalize_material_name(name) in recorded_norms)
    missing_materials = [name for name in required_names if _normalize_material_name(name) not in recorded_norms]
    required_total = len(required_names)
    missing_count = len(missing_materials)
    has_requirements = required_total > 0

    return {
        "required_total": required_total,
        "recorded_count": recorded_count,
        "missing_count": missing_count,
        "missing_materials": missing_materials,
        "complete": has_requirements and missing_count == 0,
        "has_requirements": has_requirements,
    }


def aggregate_records(rows: Iterable[Any], product_limit: int = 1000) -> List[Dict[str, Any]]:
    """Aggregate raw record rows by product_serial and merge materials."""
    grouped: Dict[str, Dict[str, Any]] = {}
    ordered_serials: List[str] = []

    for row in rows:
        item = convert_record_row(row)
        serial = item["product_serial"]
        current_map = _parse_materials(item.get("materials"), item.get("raw_data"))

        if serial not in grouped:
            grouped[serial] = item
            grouped[serial]["_materials_map"] = {}
            ordered_serials.append(serial)

        merged_map = grouped[serial]["_materials_map"]
        # rows 按 scan_time DESC，优先保留最新值；只有键不存在时才补旧值
        for k, v in current_map.items():
            if k not in merged_map and v not in (None, ""):
                merged_map[k] = v

    records: List[Dict[str, Any]] = []
    for serial in ordered_serials[:product_limit]:
        item = grouped[serial]
        merged_map = item.pop("_materials_map", {})
        if merged_map:
            merged_json = json.dumps(merged_map, ensure_ascii=False)
            item["materials"] = merged_json
            item["raw_data"] = merged_json
        records.append(item)
    return records


def summarize_duplicate_serials(rows: Iterable[Any], limit: int = 20) -> Dict[str, Any]:
    """Summarize duplicate serial rows from raw query result (count > 1)."""
    serial_counts: Dict[str, Dict[str, Any]] = {}
    safe_limit = max(1, min(int(limit or 20), 200))

    for row in rows:
        serial = str(row["product_serial"] if hasattr(row, "__getitem__") else "").strip()
        if not serial:
            continue
        scan_time = 0
        try:
            scan_time = int(row["scan_time"]) if hasattr(row, "__getitem__") else 0
        except Exception:
            scan_time = 0

        item = serial_counts.get(serial)
        if not item:
            serial_counts[serial] = {
                "product_serial": serial,
                "duplicate_count": 1,
                "latest_scan_time": scan_time,
                "oldest_scan_time": scan_time,
            }
            continue

        item["duplicate_count"] = int(item.get("duplicate_count") or 0) + 1
        item["latest_scan_time"] = max(int(item.get("latest_scan_time") or 0), scan_time)
        oldest = int(item.get("oldest_scan_time") or 0)
        item["oldest_scan_time"] = scan_time if oldest == 0 else min(oldest, scan_time)

    duplicates = [
        entry
        for entry in serial_counts.values()
        if int(entry.get("duplicate_count") or 0) > 1
    ]
    duplicates.sort(
        key=lambda d: (
            -int(d.get("duplicate_count") or 0),
            -int(d.get("latest_scan_time") or 0),
            d.get("product_serial") or "",
        )
    )

    duplicate_row_count = sum((int(d.get("duplicate_count") or 0) - 1) for d in duplicates)
    return {
        "duplicate_serial_count": len(duplicates),
        "duplicate_row_count": duplicate_row_count,
        "duplicates": duplicates[:safe_limit],
    }
