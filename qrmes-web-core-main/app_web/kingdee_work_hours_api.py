"""Kingdee work-hour integration routes and storage."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests
from flask import Response, current_app, jsonify, render_template, request, session

from qrmes_shared_core.config import config
from mes_readonly_work_hours import (
    build_completed_work_hour_rows,
    build_department_hour_summaries_for_serials,
    default_last_month_range,
    get_mes_remote_settings,
    _find_suffix_match,
    _load_product_configs,
    _load_product_records,
    refresh_mes_snapshot,
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _now_seconds() -> int:
    return int(time.time())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except Exception:
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    return default


def _normalize_serial(serial: Any) -> str:
    text = _text(serial)
    if not text:
        return ""
    return re.sub(r"[\x00-\x1f\x7f\s]+", "", text)


def _normalize_process_token(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    text = re.sub(r"\s+", "", text)
    return text.casefold()


def _build_process_key(process_code: str, process_name: str, process_desc: str) -> str:
    preferred = _normalize_process_token(process_code) or _normalize_process_token(process_name)
    if preferred:
        return preferred
    return _normalize_process_token(process_desc)


def _coalesce_str(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _normalize_base_url(value: Any) -> str:
    text = _text(value).rstrip("/")
    if not text:
        return ""
    if text.lower().endswith("/k3cloud"):
        return text[:-8]
    return text


class KingdeeConfigError(RuntimeError):
    """Raised when Kingdee configuration is incomplete."""


DEFAULT_PRODUCTION_ORDER_FORM_ID = "PRD_MO"
DEFAULT_PRODUCTION_ORDER_FIELD_KEYS = [
    "FBillNo",
    "FMaterialId.FNumber",
    "FSerialNo",
    "FRptFinishQty",
]
DEFAULT_PRODUCTION_ORDER_FILTER_TEMPLATE = "FSerialNo='{serial_escaped}'"
DEFAULT_WORKHOUR_REPORT_FORM_ID = "SFC_OperationReport"
DEFAULT_WORKHOUR_REPORT_FIELD_KEYS = [
    "FBillNo",
    "FCreateDate",
    "FDocumentStatus",
    "FMONumber",
    "FOperNumber",
    "FOperDescription",
    "FMaterialId.FNumber",
    "FMaterialId.FSpecification",
    "FUnitID.FName",
    "FReworkQty",
    "FFinishQty",
]


class KingdeeClient:
    """Minimal Kingdee Cloud API client for signed login + ExecuteBillQuery."""

    def __init__(self, logger, settings: Optional[Dict[str, Any]] = None) -> None:
        self.logger = logger
        self.settings = settings or {}

    def _cfg(self, key: str, default: Any = None) -> Any:
        if key in self.settings:
            return self.settings.get(key)
        return config.get(key, default)

    def _validate_auth_config(self) -> None:
        required_keys = {
            "kingdee_base_url": "Kingdee Base URL",
            "kingdee_acct_id": "Account ID",
            "kingdee_username": "Username",
            "kingdee_app_id": "AppId",
            "kingdee_app_secret": "AppSecret",
        }
        for key, label in required_keys.items():
            if not _text(self._cfg(key, "")):
                raise KingdeeConfigError(f"Kingdee config missing: {label} ({key})")

    def validate(self) -> None:
        self._validate_auth_config()
        required_keys = {
            "kingdee_base_url": "Kingdee Base URL",
            "kingdee_acct_id": "Account ID",
            "kingdee_username": "Username",
            "kingdee_app_id": "AppId",
            "kingdee_app_secret": "AppSecret",
            "kingdee_workhour_form_id": "Work-hour FormId",
            "kingdee_workhour_filter_template": "Work-hour filter template",
        }
        for key, label in required_keys.items():
            if not _text(self._cfg(key, "")):
                raise KingdeeConfigError(f"Kingdee work-hour config missing: {label} ({key})")

        field_keys = self._field_keys()
        if not field_keys:
            raise KingdeeConfigError("閲戣澏宸ユ椂閰嶇疆涓嶅畬鏁达紝缂哄皯瀛楁鍒楄〃 kingdee_workhour_field_keys")

        required_mapping_keys = [
            "kingdee_workhour_product_code_field",
            "kingdee_workhour_work_order_field",
        ]
        missing_mapping = [key for key in required_mapping_keys if not _text(self._cfg(key, ""))]
        if missing_mapping:
            raise KingdeeConfigError(
                "閲戣澏宸ユ椂閰嶇疆涓嶅畬鏁达紝缂哄皯瀛楁鏄犲皠: " + ", ".join(missing_mapping)
            )
        if not _text(self._cfg("kingdee_workhour_process_name_field", "")) and not _text(
            self._cfg("kingdee_workhour_process_desc_field", "")
        ):
            raise KingdeeConfigError(
                "閲戣澏宸ユ椂閰嶇疆涓嶅畬鏁达紝鑷冲皯闇€瑕侀厤缃伐搴忓悕绉板瓧娈垫垨宸ュ簭璇存槑瀛楁"
            )

    def query_process_rows(self, serial_number: str) -> List[Dict[str, Any]]:
        self.validate()
        serial = _normalize_serial(serial_number)
        if not serial:
            return []

        session = requests.Session()
        timeout = max(5, _safe_int(self._cfg("kingdee_timeout_secs", 15), 15))
        verify_ssl = _as_bool(self._cfg("kingdee_verify_ssl", True), True)

        self._login(session, timeout, verify_ssl)
        production_contexts = self._resolve_production_contexts(session, serial, timeout, verify_ssl)
        mapped_rows: List[Dict[str, Any]] = []

        if production_contexts:
            work_order_map: Dict[str, Dict[str, Optional[float]]] = {}
            for item in production_contexts:
                work_order_no = _text(item.get("work_order_no"))
                if not work_order_no:
                    continue
                product_code = _text(item.get("product_code"))
                completed_qty = _safe_float(item.get("completed_qty"))
                bucket = work_order_map.setdefault(work_order_no, {})
                if product_code and product_code not in bucket:
                    bucket[product_code] = completed_qty

            for work_order_no, product_qty_map in work_order_map.items():
                raw_rows = self._execute_bill_query(session, work_order_no, timeout, verify_ssl)
                rows_for_order = self._map_rows(raw_rows, default_serial=serial)
                if product_qty_map:
                    filtered_rows = [
                        row for row in rows_for_order
                        if not _text(row.get("product_code")) or _text(row.get("product_code")) in product_qty_map
                    ]
                    if filtered_rows:
                        rows_for_order = filtered_rows
                    for row in rows_for_order:
                        product_code = _text(row.get("product_code"))
                        if product_code in product_qty_map and product_qty_map[product_code] is not None:
                            row["completed_qty"] = product_qty_map[product_code]
                mapped_rows.extend(rows_for_order)
        else:
            raw_rows = self._execute_bill_query(session, serial, timeout, verify_ssl)
            mapped_rows = self._map_rows(raw_rows, default_serial=serial)

        mapped_rows = self._deduplicate_process_rows(mapped_rows)
        self.logger.info(
            "[Kingdee work-hours] Serial %s matched %s process records",
            serial,
            len(mapped_rows),
        )
        return mapped_rows

    def query_work_order_payloads(self, work_order_no: str) -> List[Dict[str, Any]]:
        self.validate()
        work_order = _text(work_order_no)
        if not work_order:
            return []

        session = requests.Session()
        timeout = max(5, _safe_int(self._cfg("kingdee_timeout_secs", 15), 15))
        verify_ssl = _as_bool(self._cfg("kingdee_verify_ssl", True), True)

        self._login(session, timeout, verify_ssl)
        production_contexts = self._resolve_production_contexts_for_work_order(
            session,
            work_order,
            timeout,
            verify_ssl,
        )
        if not production_contexts:
            return []

        mapped_rows = self._query_work_order_process_rows(
            session,
            work_order,
            timeout,
            verify_ssl,
        )
        payloads: List[Dict[str, Any]] = []

        for item in production_contexts:
            serial_number = _normalize_serial(item.get("serial_number"))
            if not serial_number:
                continue

            product_code = _text(item.get("product_code"))
            completed_qty = _safe_float(item.get("completed_qty"))
            rows_for_serial = [
                dict(row)
                for row in mapped_rows
                if not product_code
                or not _text(row.get("product_code"))
                or _text(row.get("product_code")) == product_code
            ]
            if not rows_for_serial:
                rows_for_serial = [dict(row) for row in mapped_rows]
            if completed_qty is not None:
                for row in rows_for_serial:
                    row["completed_qty"] = completed_qty

            payloads.append(
                {
                    "serial_number": serial_number,
                    "work_order_no": work_order,
                    "product_code": product_code,
                    "completed_qty": completed_qty,
                    "process_rows": rows_for_serial,
                }
            )

        payloads = self._deduplicate_work_order_payloads(payloads)

        self.logger.info(
            "[閲戣澏宸ユ椂] 宸ュ崟 %s 鏌ヨ鍒?%s 涓簭鍒楀彿鍥炲～杞借嵎",
            work_order,
            len(payloads),
        )
        return payloads

    def query_serial_production_contexts(self, serial_number: str) -> List[Dict[str, Any]]:
        """Read-only lookup of production/work-order context by serial number."""
        self.validate()
        serial = _normalize_serial(serial_number)
        if not serial:
            return []

        session = requests.Session()
        timeout = max(5, _safe_int(self._cfg("kingdee_timeout_secs", 15), 15))
        verify_ssl = _as_bool(self._cfg("kingdee_verify_ssl", True), True)

        self._login(session, timeout, verify_ssl)
        contexts = self._resolve_production_contexts(session, serial, timeout, verify_ssl)

        deduped: List[Dict[str, Any]] = []
        seen = set()
        for item in contexts:
            key = (
                _text(item.get("work_order_no")),
                _text(item.get("product_code")),
                _normalize_serial(item.get("serial_number")),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(dict(item))

        self.logger.info(
            "[Kingdee鍙鏌ヨ] Serial %s matched %s production context rows",
            serial,
            len(deduped),
        )
        return deduped

    def query_planning_contexts_by_serial_product(
        self,
        serial_number: str,
        product_code: str,
    ) -> List[Dict[str, Any]]:
        """Read-only fallback lookup of work-order context from OperationPlanning."""
        self.validate()
        serial = _normalize_serial(serial_number)
        product = _text(product_code)
        if not serial or not product:
            return []

        session = requests.Session()
        timeout = max(5, _safe_int(self._cfg("kingdee_timeout_secs", 15), 15))
        verify_ssl = _as_bool(self._cfg("kingdee_verify_ssl", True), True)

        self._login(session, timeout, verify_ssl)
        raw_rows = self._query_planning_rows_for_product(session, product, timeout, verify_ssl)
        mapped_rows = self._deduplicate_process_rows(self._map_rows(raw_rows, default_serial=serial))

        candidates = _derive_serial_lookup_candidates(serial, product)
        scored_contexts: List[Tuple[int, int, Dict[str, Any]]] = []
        seen: set[tuple[str, str]] = set()
        for index, row in enumerate(mapped_rows):
            work_order_no = _text(row.get("work_order_no"))
            row_product = _text(row.get("product_code")) or product
            if not work_order_no:
                continue
            if row_product and row_product.casefold() != product.casefold():
                continue
            key = (work_order_no, row_product)
            if key in seen:
                continue
            seen.add(key)

            haystack = " ".join(
                _text(value)
                for value in [
                    work_order_no,
                    row.get("serial_number"),
                    row.get("process_code"),
                    row.get("process_name"),
                    row.get("process_desc"),
                    json.dumps(row.get("raw") or {}, ensure_ascii=False),
                ]
            )
            score = 10
            for candidate in candidates:
                if candidate and candidate in haystack:
                    score = 100
                    break

            scored_contexts.append(
                (
                    score,
                    -index,
                    {
                        "work_order_no": work_order_no,
                        "product_code": row_product,
                        "serial_number": serial,
                        "completed_qty": _safe_float(row.get("completed_qty")),
                        "source": "operation_planning",
                        "raw": row.get("raw") or {},
                    },
                )
            )

        scored_contexts.sort(reverse=True, key=lambda item: (item[0], item[1]))
        contexts = [item[2] for item in scored_contexts]
        self.logger.info(
            "[Kingdee read-only lookup] Serial %s product %s matched %s operation-planning context rows",
            serial,
            product,
            len(contexts),
        )
        return contexts

    def query_work_order_process_rows_readonly(self, work_order_no: str) -> List[Dict[str, Any]]:
        """Read-only lookup of process/report rows for a work order."""
        self.validate()
        work_order = _text(work_order_no)
        if not work_order:
            return []

        session = requests.Session()
        timeout = max(5, _safe_int(self._cfg("kingdee_timeout_secs", 15), 15))
        verify_ssl = _as_bool(self._cfg("kingdee_verify_ssl", True), True)

        self._login(session, timeout, verify_ssl)
        rows = self._query_work_order_process_rows(session, work_order, timeout, verify_ssl)
        self.logger.info(
            "[Kingdee鍙鏌ヨ] Work order %s matched %s process/report rows",
            work_order,
            len(rows),
        )
        return rows

    def query_work_order_planning_rows_readonly(self, work_order_no: str) -> List[Dict[str, Any]]:
        """Read-only lookup of OperationPlanning rows for a work order."""
        self.validate()
        work_order = _text(work_order_no)
        if not work_order:
            return []

        session = requests.Session()
        timeout = max(5, _safe_int(self._cfg("kingdee_timeout_secs", 15), 15))
        verify_ssl = _as_bool(self._cfg("kingdee_verify_ssl", True), True)

        self._login(session, timeout, verify_ssl)
        raw_rows = self._execute_bill_query(session, work_order, timeout, verify_ssl)
        rows = self._deduplicate_process_rows(self._map_rows(raw_rows, default_serial=""))
        self.logger.info(
            "[Kingdee鍙鏌ヨ] Work order %s matched %s operation-planning rows",
            work_order,
            len(rows),
        )
        return rows

    def query_work_order_production_contexts_readonly(self, work_order_no: str) -> List[Dict[str, Any]]:
        """Read-only lookup of production serial contexts for a work order."""
        self.validate()
        work_order = _text(work_order_no)
        if not work_order:
            return []

        session = requests.Session()
        timeout = max(5, _safe_int(self._cfg("kingdee_timeout_secs", 15), 15))
        verify_ssl = _as_bool(self._cfg("kingdee_verify_ssl", True), True)

        self._login(session, timeout, verify_ssl)
        contexts = self._resolve_production_contexts_for_work_order(
            session,
            work_order,
            timeout,
            verify_ssl,
        )

        deduped: List[Dict[str, Any]] = []
        seen = set()
        for item in contexts:
            key = (
                _text(item.get("work_order_no")),
                _text(item.get("product_code")),
                _normalize_serial(item.get("serial_number")),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(dict(item))

        self.logger.info(
            "[Kingdee鍙鏌ヨ] Work order %s matched %s production context rows",
            work_order,
            len(deduped),
        )
        return deduped

    def _query_work_order_process_rows(
        self,
        session: requests.Session,
        work_order_no: str,
        timeout: int,
        verify_ssl: bool,
    ) -> List[Dict[str, Any]]:
        report_rows = self._query_report_rows_for_work_order(
            session,
            work_order_no,
            timeout,
            verify_ssl,
        )
        if report_rows:
            return report_rows

        raw_rows = self._execute_bill_query(session, work_order_no, timeout, verify_ssl)
        return self._deduplicate_process_rows(self._map_rows(raw_rows, default_serial=""))

    def _query_planning_rows_for_product(
        self,
        session: requests.Session,
        product_code: str,
        timeout: int,
        verify_ssl: bool,
    ) -> List[Dict[str, Any]]:
        product_field = _text(self._cfg("kingdee_workhour_product_code_field", "FProductId.FNumber"))
        filter_template = _text(self._cfg("kingdee_workhour_product_filter_template", ""))
        if not filter_template:
            filter_template = f"{product_field}='{{value_escaped}}'"

        return self._execute_bill_query(
            session,
            product_code,
            timeout,
            verify_ssl,
            form_id=_text(self._cfg("kingdee_workhour_form_id", "")),
            field_keys=self._field_keys(),
            filter_template=filter_template,
            order_string=_text(self._cfg("kingdee_workhour_order_string", "FID DESC")),
            top_rows=_safe_int(self._cfg("kingdee_workhour_top_rows", 0), 0),
            limit=max(200, _safe_int(self._cfg("kingdee_workhour_limit", 200), 200)),
            start_row=_safe_int(self._cfg("kingdee_workhour_start_row", 0), 0),
        )

    def _resolve_production_contexts(
        self,
        session: requests.Session,
        serial_number: str,
        timeout: int,
        verify_ssl: bool,
    ) -> List[Dict[str, Any]]:
        raw_rows = self._execute_bill_query(
            session,
            serial_number,
            timeout,
            verify_ssl,
            form_id=_text(self._cfg("kingdee_production_form_id", DEFAULT_PRODUCTION_ORDER_FORM_ID)),
            field_keys=self._production_field_keys(),
            filter_template=_text(
                self._cfg(
                    "kingdee_production_filter_template",
                    DEFAULT_PRODUCTION_ORDER_FILTER_TEMPLATE,
                )
            ),
            order_string=_text(self._cfg("kingdee_production_order_string", "")),
            top_rows=_safe_int(self._cfg("kingdee_production_top_rows", 0), 0),
            limit=_safe_int(self._cfg("kingdee_production_limit", 50), 50),
            start_row=_safe_int(self._cfg("kingdee_production_start_row", 0), 0),
        )
        return self._map_production_rows(raw_rows)

    def _resolve_production_contexts_for_work_order(
        self,
        session: requests.Session,
        work_order_no: str,
        timeout: int,
        verify_ssl: bool,
    ) -> List[Dict[str, Any]]:
        work_order_field = _text(self._cfg("kingdee_production_work_order_field", "FBillNo")) or "FBillNo"
        filter_template = _text(self._cfg("kingdee_production_work_order_filter_template", ""))
        if not filter_template:
            filter_template = f"{work_order_field}='{{value_escaped}}'"

        raw_rows = self._execute_bill_query(
            session,
            work_order_no,
            timeout,
            verify_ssl,
            form_id=_text(self._cfg("kingdee_production_form_id", DEFAULT_PRODUCTION_ORDER_FORM_ID)),
            field_keys=self._production_field_keys(),
            filter_template=filter_template,
            order_string=_text(self._cfg("kingdee_production_order_string", "")),
            top_rows=_safe_int(self._cfg("kingdee_production_top_rows", 0), 0),
            limit=max(500, _safe_int(self._cfg("kingdee_production_limit", 50), 50)),
            start_row=_safe_int(self._cfg("kingdee_production_start_row", 0), 0),
        )
        return [
            row
            for row in self._map_production_rows(raw_rows)
            if _text(row.get("work_order_no")) == _text(work_order_no)
        ]

    def _login(self, session: requests.Session, timeout: int, verify_ssl: bool) -> None:
        base_url = _normalize_base_url(self._cfg("kingdee_base_url", ""))
        url = (
            f"{base_url}/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.AuthService."
            "LoginBySign.common.kdsvc"
        )
        acct_id = _text(self._cfg("kingdee_acct_id", ""))
        username = _text(self._cfg("kingdee_username", ""))
        app_id = _text(self._cfg("kingdee_app_id", ""))
        app_secret = _text(self._cfg("kingdee_app_secret", ""))
        timestamp = str(_now_seconds())
        parts = sorted([acct_id, username, app_id, app_secret, timestamp])
        sign = hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()
        payload = {
            "acctID": acct_id,
            "username": username,
            "appId": app_id,
            "timestamp": timestamp,
            "sign": sign,
            "lcid": _safe_int(self._cfg("kingdee_lcid", 2052), 2052),
        }
        response = session.post(url, json=payload, timeout=timeout, verify=verify_ssl)
        response.raise_for_status()
        response_json = self._parse_json(response)
        if not self._is_login_success(response_json, session):
            raise RuntimeError(f"閲戣澏鐧诲綍澶辫触: {json.dumps(response_json, ensure_ascii=False)}")

    def _execute_bill_query(
        self,
        session: requests.Session,
        query_value: str,
        timeout: int,
        verify_ssl: bool,
        *,
        form_id: Optional[str] = None,
        field_keys: Optional[Sequence[str]] = None,
        filter_template: Optional[str] = None,
        order_string: Optional[str] = None,
        top_rows: Optional[int] = None,
        limit: Optional[int] = None,
        start_row: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        base_url = _normalize_base_url(self._cfg("kingdee_base_url", ""))
        url = (
            f"{base_url}/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService."
            "ExecuteBillQuery.common.kdsvc"
        )
        query_value = _text(query_value)
        normalized_field_keys = [item for item in (field_keys or self._field_keys()) if _text(item)]
        filter_template = _text(filter_template if filter_template is not None else self._cfg("kingdee_workhour_filter_template", ""))
        filter_string = filter_template.format(
            serial=query_value,
            serial_number=query_value,
            serial_escaped=query_value.replace("'", "''"),
            product_code=query_value,
            product_code_escaped=query_value.replace("'", "''"),
            value=query_value,
            value_escaped=query_value.replace("'", "''"),
        )
        payload = {
            "FormId": _text(form_id if form_id is not None else self._cfg("kingdee_workhour_form_id", "")),
            "FieldKeys": ",".join(normalized_field_keys),
            "FilterString": filter_string,
            "OrderString": _text(order_string if order_string is not None else self._cfg("kingdee_workhour_order_string", "")),
            "TopRowCount": _safe_int(top_rows if top_rows is not None else self._cfg("kingdee_workhour_top_rows", 0), 0),
            "Limit": _safe_int(limit if limit is not None else self._cfg("kingdee_workhour_limit", 200), 200),
            "StartRow": _safe_int(start_row if start_row is not None else self._cfg("kingdee_workhour_start_row", 0), 0),
        }

        request_payload = {"data": json.dumps(payload, ensure_ascii=False)}
        response = session.post(url, json=request_payload, timeout=timeout, verify=verify_ssl)
        response.raise_for_status()
        response_json = self._parse_json(response)
        rows = self._extract_query_rows(response_json)
        normalized_rows: List[Dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                normalized_rows.append(row)
                continue
            if isinstance(row, (list, tuple)):
                normalized_rows.append(
                    {
                        normalized_field_keys[index]: row[index] if index < len(row) else None
                        for index in range(len(normalized_field_keys))
                    }
                )
        return normalized_rows

    def _execute_dynamic_form_action(
        self,
        session: requests.Session,
        action_name: str,
        payload: Dict[str, Any],
        timeout: int,
        verify_ssl: bool,
    ) -> Dict[str, Any]:
        base_url = _normalize_base_url(self._cfg("kingdee_base_url", ""))
        url = (
            f"{base_url}/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService."
            f"{action_name}.common.kdsvc"
        )
        request_payload = {"data": json.dumps(payload, ensure_ascii=False)}
        response = session.post(url, json=request_payload, timeout=timeout, verify=verify_ssl)
        response.raise_for_status()
        return self._parse_json(response)

    def _field_keys(self) -> List[str]:
        raw = self._cfg("kingdee_workhour_field_keys", [])
        if isinstance(raw, list):
            return [_text(item) for item in raw if _text(item)]
        if isinstance(raw, str):
            return [_text(item) for item in raw.split(",") if _text(item)]
        return []

    def _production_field_keys(self) -> List[str]:
        raw = self._cfg("kingdee_production_field_keys", DEFAULT_PRODUCTION_ORDER_FIELD_KEYS)
        if isinstance(raw, list):
            return [_text(item) for item in raw if _text(item)]
        if isinstance(raw, str):
            return [_text(item) for item in raw.split(",") if _text(item)]
        return list(DEFAULT_PRODUCTION_ORDER_FIELD_KEYS)

    def _report_field_keys(self) -> List[str]:
        raw = self._cfg("kingdee_workhour_report_field_keys", DEFAULT_WORKHOUR_REPORT_FIELD_KEYS)
        if isinstance(raw, list):
            field_keys = [_text(item) for item in raw if _text(item)]
        elif isinstance(raw, str):
            field_keys = [_text(item) for item in raw.split(",") if _text(item)]
        else:
            field_keys = list(DEFAULT_WORKHOUR_REPORT_FIELD_KEYS)
        actual_hours_field = _text(self._cfg("kingdee_workhour_report_actual_hours_field", ""))
        if actual_hours_field and actual_hours_field not in field_keys:
            field_keys.append(actual_hours_field)
        return field_keys

    def _report_form_id(self) -> str:
        return _text(self._cfg("kingdee_workhour_report_form_id", DEFAULT_WORKHOUR_REPORT_FORM_ID))

    def _query_report_rows_for_work_order(
        self,
        session: requests.Session,
        work_order_no: str,
        timeout: int,
        verify_ssl: bool,
    ) -> List[Dict[str, Any]]:
        form_id = self._report_form_id()
        if not form_id:
            return []

        field_keys = self._report_field_keys()
        if not field_keys:
            return []

        work_order_field = _text(self._cfg("kingdee_workhour_report_work_order_field", "FMONumber")) or "FMONumber"
        filter_template = _text(self._cfg("kingdee_workhour_report_filter_template", ""))
        if not filter_template:
            filter_template = f"{work_order_field}='{{value_escaped}}'"

        try:
            raw_rows = self._execute_bill_query(
                session,
                work_order_no,
                timeout,
                verify_ssl,
                form_id=form_id,
                field_keys=field_keys,
                filter_template=filter_template,
                order_string=_text(self._cfg("kingdee_workhour_report_order_string", "FID DESC")),
                top_rows=_safe_int(self._cfg("kingdee_workhour_report_top_rows", 0), 0),
                limit=max(1, _safe_int(self._cfg("kingdee_workhour_report_limit", 500), 500)),
                start_row=_safe_int(self._cfg("kingdee_workhour_report_start_row", 0), 0),
            )
        except Exception:
            self.logger.exception("[閲戣澏宸ユ椂] 宸ュ簭姹囨姤鍙ｅ緞鏌ヨ澶辫触锛屽皢鍥為€€鍒版棫鍙ｅ緞")
            return []

        return self._deduplicate_process_rows(self._map_report_rows(raw_rows))

    def _map_rows(
        self,
        rows: Sequence[Dict[str, Any]],
        *,
        default_serial: str = "",
    ) -> List[Dict[str, Any]]:
        serial_field = _text(self._cfg("kingdee_workhour_serial_field", ""))
        work_order_field = _text(self._cfg("kingdee_workhour_work_order_field", ""))
        process_name_field = _text(self._cfg("kingdee_workhour_process_name_field", ""))
        process_desc_field = _text(self._cfg("kingdee_workhour_process_desc_field", ""))
        process_code_field = _text(self._cfg("kingdee_workhour_process_code_field", ""))
        product_code_field = _text(self._cfg("kingdee_workhour_product_code_field", ""))
        spec_model_field = _text(self._cfg("kingdee_workhour_spec_model_field", ""))
        qty_field = _coalesce_str(
            self._cfg("kingdee_workhour_completed_qty_field", ""),
            self._cfg("kingdee_workhour_qty_field", ""),
        )

        mapped: List[Dict[str, Any]] = []
        for row in rows:
            product_code = _text(row.get(product_code_field))
            work_order_no = _text(row.get(work_order_field))
            serial_number = _normalize_serial(row.get(serial_field)) if serial_field else ""
            if not serial_number:
                serial_number = default_serial
            process_name = _text(row.get(process_name_field)) if process_name_field else ""
            process_desc = _text(row.get(process_desc_field)) if process_desc_field else ""
            if not process_name:
                process_name = process_desc
            process_code = _text(row.get(process_code_field))
            if not work_order_no or not process_name:
                continue
            mapped.append(
                {
                    "product_code": product_code,
                    "spec_model": _text(row.get(spec_model_field)) if spec_model_field else "",
                    "work_order_no": work_order_no,
                    "serial_number": serial_number,
                    "process_code": process_code,
                    "process_name": process_name,
                    "process_desc": process_desc,
                    "completed_qty": _safe_float(row.get(qty_field)),
                    "raw": row,
                }
            )
        return mapped

    def _map_production_rows(self, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        work_order_field = _text(self._cfg("kingdee_production_work_order_field", "FBillNo"))
        product_code_field = _text(self._cfg("kingdee_production_product_code_field", "FMaterialId.FNumber"))
        serial_field = _text(self._cfg("kingdee_production_serial_field", "FSerialNo"))
        completed_qty_field = _text(self._cfg("kingdee_production_completed_qty_field", "FRptFinishQty"))

        mapped: List[Dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            work_order_no = _text(row.get(work_order_field))
            product_code = _text(row.get(product_code_field))
            serial_number = _normalize_serial(row.get(serial_field))
            if not work_order_no:
                continue
            signature = (work_order_no, product_code, serial_number)
            if signature in seen:
                continue
            seen.add(signature)
            mapped.append(
                {
                    "work_order_no": work_order_no,
                    "product_code": product_code,
                    "serial_number": serial_number,
                    "completed_qty": _safe_float(row.get(completed_qty_field)),
                    "raw": row,
                }
            )
        return mapped

    def _map_report_rows(self, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        work_order_field = _text(self._cfg("kingdee_workhour_report_work_order_field", "FMONumber")) or "FMONumber"
        product_code_field = _text(self._cfg("kingdee_workhour_report_product_code_field", "FMaterialId.FNumber"))
        process_code_field = _text(self._cfg("kingdee_workhour_report_process_code_field", "FOperNumber"))
        process_name_field = _text(self._cfg("kingdee_workhour_report_process_name_field", "FOperDescription"))
        process_desc_field = _text(self._cfg("kingdee_workhour_report_process_desc_field", "FOperDescription"))
        completed_qty_field = _text(self._cfg("kingdee_workhour_report_completed_qty_field", "FFinishQty"))
        bill_no_field = _text(self._cfg("kingdee_workhour_report_bill_no_field", "FBillNo"))
        created_at_field = _text(self._cfg("kingdee_workhour_report_created_at_field", "FCreateDate"))
        status_field = _text(self._cfg("kingdee_workhour_report_status_field", "FDocumentStatus"))
        unit_field = _text(self._cfg("kingdee_workhour_report_unit_field", "FUnitID.FName"))
        rework_qty_field = _text(self._cfg("kingdee_workhour_report_rework_qty_field", "FReworkQty"))
        actual_hours_field = _text(self._cfg("kingdee_workhour_report_actual_hours_field", ""))

        mapped: List[Dict[str, Any]] = []
        for row in rows:
            work_order_no = _text(row.get(work_order_field))
            process_name = _text(row.get(process_name_field))
            process_desc = _text(row.get(process_desc_field))
            if not process_name:
                process_name = process_desc
            if not work_order_no or not process_name:
                continue

            mapped.append(
                {
                    "product_code": _text(row.get(product_code_field)),
                    # 瑙勬牸鍨嬪彿鍙厑璁告潵鑷伐搴忚鍒掑垪琛紝閬垮厤鐢ㄥ伐搴忔眹鎶ュ彛寰勯┍鍔ㄩ瑁呴厤鏃堕棿銆?                    "spec_model": "",
                    "work_order_no": work_order_no,
                    "serial_number": "",
                    "process_code": _text(row.get(process_code_field)),
                    "process_name": process_name,
                    "process_desc": process_desc,
                    "completed_qty": _safe_float(row.get(completed_qty_field)),
                    "report_bill_no": _text(row.get(bill_no_field)),
                    "report_created_at": _text(row.get(created_at_field)),
                    "report_status": _text(row.get(status_field)),
                    "unit_name": _text(row.get(unit_field)),
                    "rework_qty": _safe_float(row.get(rework_qty_field)),
                    "reported_actual_work_hours": _safe_float(row.get(actual_hours_field)),
                    "raw": row,
                }
            )
        return mapped

    def _deduplicate_process_rows(self, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for row in rows:
            signature = (
                _text(row.get("serial_number")),
                _text(row.get("work_order_no")),
                _text(row.get("product_code")),
                _text(row.get("process_code")),
                _text(row.get("process_desc")) or _text(row.get("process_name")),
            )
            if signature in seen:
                continue
            seen.add(signature)
            deduped.append(row)
        return deduped

    def _deduplicate_work_order_payloads(
        self,
        payloads: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        best_by_serial: Dict[str, Dict[str, Any]] = {}
        for payload in payloads:
            serial_number = _normalize_serial(payload.get("serial_number"))
            if not serial_number:
                continue

            current = best_by_serial.get(serial_number)
            if current is None:
                best_by_serial[serial_number] = payload
                continue

            current_process_count = len(current.get("process_rows") or [])
            next_process_count = len(payload.get("process_rows") or [])
            current_product_code = _text(current.get("product_code"))
            next_product_code = _text(payload.get("product_code"))

            should_replace = False
            if next_process_count > current_process_count:
                should_replace = True
            elif next_process_count == current_process_count and next_product_code and not current_product_code:
                should_replace = True

            if should_replace:
                best_by_serial[serial_number] = payload

        return list(best_by_serial.values())

    def _parse_json(self, response: requests.Response) -> Any:
        try:
            return response.json()
        except Exception:
            text = response.text.strip()
            if not text:
                return {}
            try:
                return json.loads(text)
            except Exception:
                return {"raw": text}

    def _is_login_success(self, payload: Any, session: requests.Session) -> bool:
        if isinstance(payload, dict):
            if _as_bool(payload.get("IsSuccessByAPI"), False):
                return True
            if _safe_int(payload.get("LoginResultType"), 0) == 1:
                return True
            if _safe_int(payload.get("ResultType"), 0) == 1:
                return True
            response_status = payload.get("ResponseStatus")
            if isinstance(response_status, dict) and _as_bool(response_status.get("IsSuccess"), False):
                return True
        if isinstance(payload, list) and payload:
            first = payload[0]
            if first in (1, "1", True):
                return True
            if isinstance(first, dict):
                return self._is_login_success(first, session)
        return bool(session.cookies)

    def _extract_query_rows(self, payload: Any) -> List[Any]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
                return self._extract_query_rows(parsed)
            except Exception:
                return []
        if isinstance(payload, dict):
            for key in ("Result", "result", "Data", "data", "NeedReturnData", "needReturnData"):
                if key in payload:
                    rows = self._extract_query_rows(payload[key])
                    if rows:
                        return rows
            for value in payload.values():
                rows = self._extract_query_rows(value)
                if rows:
                    return rows
        return []

    def _normalize_action_response(self, payload: Any) -> Dict[str, Any]:
        result = payload.get("Result") if isinstance(payload, dict) else {}
        response_status = result.get("ResponseStatus") if isinstance(result, dict) else {}
        errors = response_status.get("Errors") or []
        success_entities = response_status.get("SuccessEntitys") or []
        is_success = bool(response_status.get("IsSuccess"))

        created_entity = None
        for entity in success_entities:
            if isinstance(entity, dict) and (_text(entity.get("Id")) or _text(entity.get("Number"))):
                created_entity = entity
                break

        normalized_errors: List[str] = []
        warnings: List[str] = []
        for error in errors:
            message = _text(error.get("Message") if isinstance(error, dict) else error)
            if not message:
                continue
            if created_entity is not None:
                warnings.append(message)
            else:
                normalized_errors.append(message)

        return {
            "success": is_success or created_entity is not None,
            "created": created_entity is not None,
            "id": _text(created_entity.get("Id")) if created_entity else "",
            "number": _text(created_entity.get("Number")) if created_entity else "",
            "errors": normalized_errors,
            "warnings": warnings,
            "raw": payload,
        }

    def generate_operation_report(
        self,
        payload: Dict[str, Any],
        *,
        action_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._validate_auth_config()
        timeout = _safe_int(self._cfg("kingdee_timeout", 30), 30)
        verify_ssl = _as_bool(self._cfg("kingdee_verify_ssl", False), False)
        action = _text(
            action_name if action_name is not None else self._cfg("kingdee_generate_operation_report_action", "GenOperRpt")
        ) or "GenOperRpt"

        with requests.Session() as session:
            self._login(session, timeout=timeout, verify_ssl=verify_ssl)
            raw_result = self._execute_dynamic_form_action(
                session,
                action,
                payload,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )
        return self._normalize_action_response(raw_result)


class WorkHourStore:
    """SQLite storage for per-process work-hour snapshots."""

    def __init__(self, db_path: Path, logger) -> None:
        self.db_path = db_path
        self.logger = logger
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=2000;")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS work_hour_process_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    serial_number TEXT NOT NULL,
                    work_order_no TEXT NOT NULL,
                    process_key TEXT NOT NULL,
                    product_code TEXT,
                    process_code TEXT,
                    process_name TEXT NOT NULL,
                    process_desc TEXT,
                    completed_qty REAL,
                    project_name TEXT,
                    product_type TEXT,
                    start_time_ms INTEGER,
                    end_time_ms INTEGER,
                    duration_ms INTEGER,
                    material_scan_operator TEXT,
                    process_operator TEXT,
                    material_scan_source TEXT,
                    process_complete_source TEXT,
                    kingdee_payload_json TEXT,
                    report_bill_no TEXT,
                    report_created_at TEXT,
                    report_status TEXT,
                    unit_name TEXT,
                    rework_qty REAL,
                    reported_actual_work_hours REAL,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL,
                    UNIQUE(serial_number, work_order_no, process_key)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_work_hour_work_order
                ON work_hour_process_records(work_order_no)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_work_hour_serial
                ON work_hour_process_records(serial_number)
                """
            )
            existing_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(work_hour_process_records)").fetchall()
            }
            extra_columns = {
                "report_bill_no": "TEXT",
                "report_created_at": "TEXT",
                "report_status": "TEXT",
                "unit_name": "TEXT",
                "rework_qty": "REAL",
                "reported_actual_work_hours": "REAL",
            }
            for column_name, column_type in extra_columns.items():
                if column_name not in existing_columns:
                    conn.execute(
                        f"ALTER TABLE work_hour_process_records ADD COLUMN {column_name} {column_type}"
                    )
            conn.commit()

    def sync_material_scan(
        self,
        serial_number: str,
        process_rows: Sequence[Dict[str, Any]],
        *,
        project_name: str,
        product_type: str,
        operator: str,
        started_at_ms: int,
        source: str,
    ) -> Dict[str, Any]:
        inserted = 0
        updated = 0
        now_ms = _now_ms()
        sample_work_order = ""
        sample_product_code = ""

        with self._connect() as conn:
            for row in process_rows:
                work_order_no = _text(row.get("work_order_no"))
                process_name = _text(row.get("process_name"))
                process_desc = _text(row.get("process_desc"))
                process_code = _text(row.get("process_code"))
                process_key = _build_process_key(process_code, process_name, process_desc)
                if not work_order_no or not process_key:
                    continue
                product_code = _text(row.get("product_code"))
                completed_qty = _safe_float(row.get("completed_qty"))
                report_bill_no = _text(row.get("report_bill_no"))
                report_created_at = _text(row.get("report_created_at"))
                report_status = _text(row.get("report_status"))
                unit_name = _text(row.get("unit_name"))
                rework_qty = _safe_float(row.get("rework_qty"))
                reported_actual_work_hours = _safe_float(row.get("reported_actual_work_hours"))
                payload_json = json.dumps(row.get("raw", {}), ensure_ascii=False)

                existing = conn.execute(
                    """
                    SELECT id, start_time_ms FROM work_hour_process_records
                    WHERE serial_number = ? AND work_order_no = ? AND process_key = ?
                    """,
                    (serial_number, work_order_no, process_key),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE work_hour_process_records
                        SET product_code = ?,
                            process_code = ?,
                            process_name = ?,
                            process_desc = ?,
                            completed_qty = ?,
                            project_name = ?,
                            product_type = ?,
                            start_time_ms = CASE
                                WHEN start_time_ms IS NULL THEN ?
                                WHEN ? <= 0 THEN start_time_ms
                                ELSE MIN(start_time_ms, ?)
                            END,
                            material_scan_operator = COALESCE(NULLIF(?, ''), material_scan_operator),
                            material_scan_source = COALESCE(NULLIF(?, ''), material_scan_source),
                            kingdee_payload_json = ?,
                            report_bill_no = COALESCE(NULLIF(?, ''), report_bill_no),
                            report_created_at = COALESCE(NULLIF(?, ''), report_created_at),
                            report_status = COALESCE(NULLIF(?, ''), report_status),
                            unit_name = COALESCE(NULLIF(?, ''), unit_name),
                            rework_qty = CASE
                                WHEN ? IS NULL THEN rework_qty
                                ELSE ?
                            END,
                            reported_actual_work_hours = CASE
                                WHEN ? IS NULL THEN reported_actual_work_hours
                                ELSE ?
                            END,
                            updated_at_ms = ?
                        WHERE id = ?
                        """,
                        (
                            product_code,
                            process_code,
                            process_name,
                            process_desc,
                            completed_qty,
                            project_name,
                            product_type,
                            started_at_ms,
                            started_at_ms,
                            started_at_ms,
                            operator,
                            source,
                            payload_json,
                            report_bill_no,
                            report_created_at,
                            report_status,
                            unit_name,
                            rework_qty,
                            rework_qty,
                            reported_actual_work_hours,
                            reported_actual_work_hours,
                            now_ms,
                            existing["id"],
                        ),
                    )
                    updated += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO work_hour_process_records (
                            serial_number,
                            work_order_no,
                            process_key,
                            product_code,
                            process_code,
                            process_name,
                            process_desc,
                            completed_qty,
                            project_name,
                            product_type,
                            start_time_ms,
                            material_scan_operator,
                            material_scan_source,
                            kingdee_payload_json,
                            report_bill_no,
                            report_created_at,
                            report_status,
                            unit_name,
                            rework_qty,
                            reported_actual_work_hours,
                            created_at_ms,
                            updated_at_ms
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            serial_number,
                            work_order_no,
                            process_key,
                            product_code,
                            process_code,
                            process_name,
                            process_desc,
                            completed_qty,
                            project_name,
                            product_type,
                            started_at_ms,
                            operator,
                            source,
                            payload_json,
                            report_bill_no,
                            report_created_at,
                            report_status,
                            unit_name,
                            rework_qty,
                            reported_actual_work_hours,
                            now_ms,
                            now_ms,
                        ),
                    )
                    inserted += 1

                sample_work_order = sample_work_order or work_order_no
                sample_product_code = sample_product_code or product_code

            conn.commit()

        return {
            "serial_number": serial_number,
            "work_order_no": sample_work_order,
            "product_code": sample_product_code,
            "inserted_count": inserted,
            "updated_count": updated,
            "process_count": len(process_rows),
        }

    def complete_process(
        self,
        *,
        serial_number: str,
        process_name: str,
        process_desc: str,
        operator: str,
        ended_at_ms: int,
        project_name: str,
        product_type: str,
        source: str,
    ) -> Optional[Dict[str, Any]]:
        rows = self.list_serial_records(serial_number)
        if not rows:
            return None

        target = self._select_process_row(rows, process_name, process_desc)
        if not target:
            return None

        end_time_ms = ended_at_ms if ended_at_ms > 0 else _now_ms()
        start_time_ms = _safe_int(target.get("start_time_ms"), 0)
        duration_ms = None
        if start_time_ms > 0 and end_time_ms >= start_time_ms:
            duration_ms = end_time_ms - start_time_ms

        now_ms = _now_ms()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE work_hour_process_records
                SET project_name = ?,
                    product_type = ?,
                    end_time_ms = CASE
                        WHEN end_time_ms IS NULL THEN ?
                        ELSE MAX(end_time_ms, ?)
                    END,
                    duration_ms = CASE
                        WHEN ? IS NULL THEN duration_ms
                        WHEN duration_ms IS NULL THEN ?
                        ELSE MAX(duration_ms, ?)
                    END,
                    process_operator = COALESCE(NULLIF(?, ''), process_operator),
                    process_complete_source = COALESCE(NULLIF(?, ''), process_complete_source),
                    updated_at_ms = ?
                WHERE id = ?
                """,
                (
                    project_name,
                    product_type,
                    end_time_ms,
                    end_time_ms,
                    duration_ms,
                    duration_ms,
                    duration_ms,
                    operator,
                    source,
                    now_ms,
                    target["id"],
                ),
            )
            conn.commit()

        return self.get_record_by_id(_safe_int(target["id"]))

    def list_serial_records(self, serial_number: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM work_hour_process_records
                WHERE serial_number = ?
                ORDER BY work_order_no, process_name, id
                """,
                (serial_number,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_work_order_records(self, work_order_no: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM work_hour_process_records
                WHERE work_order_no = ?
                ORDER BY product_code, serial_number, process_name, id
                """,
                (work_order_no,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_record_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM work_hour_process_records WHERE id = ?",
                (record_id,),
            ).fetchone()
        return dict(row) if row else None

    def summarize_work_order(self, work_order_no: str) -> Dict[str, Any]:
        with self._connect() as conn:
            serial_rows = conn.execute(
                """
                SELECT
                    work_order_no,
                    product_code,
                    serial_number,
                    MAX(completed_qty) AS completed_qty,
                    MIN(start_time_ms) AS first_start_time_ms,
                    MAX(end_time_ms) AS last_end_time_ms,
                    MAX(material_scan_operator) AS material_scan_operator,
                    MAX(process_operator) AS process_operator,
                    COUNT(*) AS process_record_count,
                    SUM(CASE WHEN end_time_ms IS NOT NULL THEN 1 ELSE 0 END) AS completed_process_count
                FROM work_hour_process_records
                WHERE work_order_no = ?
                GROUP BY work_order_no, product_code, serial_number
                ORDER BY product_code, serial_number
                """,
                (work_order_no,),
            ).fetchall()
            process_rows = conn.execute(
                """
                SELECT
                    work_order_no,
                    product_code,
                    process_key,
                    process_code,
                    process_name,
                    process_desc,
                    COUNT(DISTINCT serial_number) AS tracked_serial_count,
                    COUNT(DISTINCT CASE WHEN end_time_ms IS NOT NULL THEN serial_number END) AS completed_serial_count,
                    MAX(completed_qty) AS completed_qty,
                    MIN(start_time_ms) AS first_start_time_ms,
                    MAX(end_time_ms) AS last_end_time_ms,
                    SUM(COALESCE(reported_actual_work_hours, 0)) AS reported_actual_work_hours,
                    SUM(
                        CASE
                            WHEN start_time_ms IS NOT NULL
                                AND end_time_ms IS NOT NULL
                                AND end_time_ms >= start_time_ms
                            THEN end_time_ms - start_time_ms
                            ELSE 0
                        END
                    ) AS total_duration_ms
                FROM work_hour_process_records
                WHERE work_order_no = ?
                GROUP BY work_order_no, product_code, process_key, process_code, process_name, process_desc
                ORDER BY product_code, CAST(process_code AS INTEGER), process_code, process_name
                """,
                (work_order_no,),
            ).fetchall()
        serial_summaries: List[Dict[str, Any]] = []
        first_start_values: List[int] = []
        last_end_values: List[int] = []
        product_summaries: List[Dict[str, Any]] = []
        product_buckets: Dict[str, Dict[str, Any]] = {}

        for row in serial_rows:
            item = dict(row)
            start_time_ms = _safe_int(item.get("first_start_time_ms"), 0)
            end_time_ms = _safe_int(item.get("last_end_time_ms"), 0)
            total_duration_ms = None
            if start_time_ms > 0 and end_time_ms >= start_time_ms:
                total_duration_ms = end_time_ms - start_time_ms
            item["total_duration_ms"] = total_duration_ms
            item["operator"] = _coalesce_str(item.get("process_operator"), item.get("material_scan_operator"))
            item["status"] = "done" if end_time_ms > 0 and total_duration_ms is not None else "pending"
            serial_summaries.append(item)

            if start_time_ms > 0:
                first_start_values.append(start_time_ms)
            if end_time_ms > 0:
                last_end_values.append(end_time_ms)

            product_code = _text(item.get("product_code")) or "-"
            bucket = product_buckets.setdefault(
                product_code,
                {
                    "work_order_no": work_order_no,
                    "product_code": product_code,
                    "tracked_serial_count": 0,
                    "completed_serial_count": 0,
                    "completed_qty": 0.0,
                    "first_start_time_ms": None,
                    "last_end_time_ms": None,
                    "total_duration_ms": 0,
                    "reported_actual_work_hours": None,
                    "kingdee_serial_numbers": [],
                },
            )
            bucket["tracked_serial_count"] += 1
            if total_duration_ms is not None:
                bucket["completed_serial_count"] += 1
                bucket["total_duration_ms"] += int(total_duration_ms or 0)
            completed_qty = _safe_float(item.get("completed_qty"))
            if completed_qty is not None:
                bucket["completed_qty"] += completed_qty
            if start_time_ms > 0:
                existing_start = _safe_int(bucket.get("first_start_time_ms"), 0)
                bucket["first_start_time_ms"] = start_time_ms if existing_start <= 0 else min(existing_start, start_time_ms)
            if end_time_ms > 0:
                existing_end = _safe_int(bucket.get("last_end_time_ms"), 0)
                bucket["last_end_time_ms"] = max(existing_end, end_time_ms)
            bucket["kingdee_serial_numbers"].append(_normalize_serial(item.get("serial_number")))

        for row in process_rows:
            item = dict(row)
            item["product_code"] = _text(item.get("product_code")) or "-"
            item["process_code"] = _text(item.get("process_code")) or _text(item.get("process_key"))
            item["process_name"] = _coalesce_str(
                item.get("process_name"),
                item.get("process_desc"),
                item.get("process_code"),
                "-",
            )
            bucket = product_buckets.setdefault(
                item["product_code"],
                {
                    "work_order_no": work_order_no,
                    "product_code": item["product_code"],
                    "tracked_serial_count": 0,
                    "completed_serial_count": 0,
                    "completed_qty": 0.0,
                    "first_start_time_ms": None,
                    "last_end_time_ms": None,
                    "total_duration_ms": 0,
                    "reported_actual_work_hours": None,
                    "kingdee_serial_numbers": [],
                },
            )
            reported_actual = _safe_float(item.get("reported_actual_work_hours"))
            if reported_actual is not None:
                bucket["reported_actual_work_hours"] = (
                    reported_actual
                    if bucket.get("reported_actual_work_hours") is None
                    else float(bucket["reported_actual_work_hours"]) + reported_actual
                )

        for bucket in product_buckets.values():
            serial_numbers = sorted({serial for serial in bucket.get("kingdee_serial_numbers") or [] if serial})
            bucket["kingdee_serial_numbers"] = serial_numbers
            if bucket.get("completed_qty") is not None:
                bucket["completed_qty"] = int(bucket["completed_qty"]) if float(bucket["completed_qty"]).is_integer() else bucket["completed_qty"]
            product_summaries.append(bucket)

        product_summaries.sort(key=lambda item: (_text(item.get("product_code")), _text(item.get("work_order_no"))))

        total_duration_ms = sum(
            int(item.get("total_duration_ms") or 0)
            for item in serial_summaries
        )
        completed_serial_count = sum(
            1
            for item in serial_summaries
            if item.get("total_duration_ms") is not None
        )
        overview = {
            "work_order_no": work_order_no,
            "product_code_count": len(product_summaries),
            "tracked_serial_count": len(serial_summaries),
            "completed_serial_count": completed_serial_count,
            "total_duration_ms": total_duration_ms,
            "first_start_time_ms": min(first_start_values) if first_start_values else None,
            "last_end_time_ms": max(last_end_values) if last_end_values else None,
        } if serial_summaries else None

        return {
            "work_order_no": work_order_no,
            "overview": overview,
            "product_summaries": product_summaries,
            "serial_summaries": serial_summaries,
            "processes": [],
        }

    def _select_process_row(
        self,
        rows: Sequence[Dict[str, Any]],
        process_name: str,
        process_desc: str,
    ) -> Optional[Dict[str, Any]]:
        target_name = _normalize_process_token(process_name)
        target_desc = _normalize_process_token(process_desc)
        scored: List[Tuple[int, int, Dict[str, Any]]] = []

        for row in rows:
            row_name = _normalize_process_token(row.get("process_name"))
            row_desc = _normalize_process_token(row.get("process_desc"))
            score = 0
            if target_name and row_name == target_name:
                score = max(score, 100)
            if target_desc and row_desc == target_desc:
                score = max(score, 95)
            if target_name and row_desc == target_name:
                score = max(score, 92)
            if target_desc and row_name == target_desc:
                score = max(score, 90)
            if target_name and row_name and (target_name in row_name or row_name in target_name):
                score = max(score, 80)
            if target_desc and row_desc and (target_desc in row_desc or row_desc in target_desc):
                score = max(score, 76)
            if target_name and row_desc and (target_name in row_desc or row_desc in target_name):
                score = max(score, 72)
            if target_desc and row_name and (target_desc in row_name or row_name in target_desc):
                score = max(score, 70)
            if score <= 0:
                continue
            unfinished_bonus = 1 if row.get("end_time_ms") is None else 0
            scored.append((score, unfinished_bonus, row))

        if not scored:
            return None
        scored.sort(
            key=lambda item: (
                item[0],
                item[1],
                -_safe_int(item[2].get("start_time_ms"), 0),
            ),
            reverse=True,
        )
        return scored[0][2]


class SerialLookupStore:
    """SQLite cache for serial-level product/work-order lookup summaries."""

    def __init__(self, db_path: Path, logger) -> None:
        self.db_path = db_path
        self.logger = logger
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=2000;")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS serial_lookup_records (
                    serial_number TEXT PRIMARY KEY,
                    short_serial_number TEXT,
                    product_code TEXT NOT NULL,
                    work_order_no TEXT NOT NULL,
                    completed_qty REAL,
                    actual_total_work_hours REAL,
                    source TEXT,
                    payload_json TEXT,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_serial_lookup_short_serial
                ON serial_lookup_records(short_serial_number)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_serial_lookup_work_order
                ON serial_lookup_records(work_order_no)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_serial_lookup_product_code
                ON serial_lookup_records(product_code)
                """
            )
            conn.commit()

    def get_by_serial(self, serial_number: str) -> Optional[Dict[str, Any]]:
        serial = _normalize_serial(serial_number)
        if not serial:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM serial_lookup_records
                WHERE (serial_number = ? OR short_serial_number = ?)
                  AND COALESCE(source, '') != 'operation_planning'
                ORDER BY updated_at_ms DESC
                LIMIT 1
                """,
                (serial, serial),
            ).fetchone()
        return dict(row) if row else None

    def get_work_order_no(self, serial_number: str) -> str:
        row = self.get_by_serial(serial_number)
        return _text(row.get("work_order_no")) if row else ""

    def upsert_summary(
        self,
        *,
        serial_number: str,
        short_serial_number: str = "",
        product_code: str,
        work_order_no: str,
        completed_qty: Optional[float] = None,
        actual_total_work_hours: Optional[float] = None,
        source: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        serial = _normalize_serial(serial_number)
        short_serial = _normalize_serial(short_serial_number)
        product = _text(product_code)
        work_order = _text(work_order_no)
        if not serial or not product or not work_order:
            return None

        now_ms = _now_ms()
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at_ms FROM serial_lookup_records WHERE serial_number = ?",
                (serial,),
            ).fetchone()
            created_at_ms = _safe_int(existing["created_at_ms"], now_ms) if existing else now_ms
            conn.execute(
                """
                INSERT INTO serial_lookup_records (
                    serial_number,
                    short_serial_number,
                    product_code,
                    work_order_no,
                    completed_qty,
                    actual_total_work_hours,
                    source,
                    payload_json,
                    created_at_ms,
                    updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(serial_number) DO UPDATE SET
                    short_serial_number = excluded.short_serial_number,
                    product_code = excluded.product_code,
                    work_order_no = excluded.work_order_no,
                    completed_qty = excluded.completed_qty,
                    actual_total_work_hours = excluded.actual_total_work_hours,
                    source = excluded.source,
                    payload_json = excluded.payload_json,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (
                    serial,
                    short_serial,
                    product,
                    work_order,
                    completed_qty,
                    actual_total_work_hours,
                    _text(source),
                    payload_json,
                    created_at_ms,
                    now_ms,
                ),
            )
            conn.commit()
        return self.get_by_serial(serial)


def _derive_serial_lookup_candidates(serial_number: Any, product_code: Any = "") -> List[str]:
    serial = _normalize_serial(serial_number)
    product = _text(product_code)
    candidates: List[str] = []

    def _append(value: Any) -> None:
        candidate = _normalize_serial(value)
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    _append(serial)
    if product and serial.startswith(product):
        _append(serial[len(product):])

    suffix_match = re.search(r"(T\d[0-9A-Za-z-]{5,})$", serial)
    if suffix_match:
        _append(suffix_match.group(1))

    return candidates


def _sum_reported_actual_work_hours(
    rows: Sequence[Dict[str, Any]],
    *,
    product_code: Any = "",
) -> Optional[float]:
    target_product = _text(product_code)
    total = 0.0
    found = False
    for row in rows:
        row_product = _text(row.get("product_code"))
        if target_product and row_product and row_product != target_product:
            continue
        value = _safe_float(row.get("reported_actual_work_hours"))
        if value is None:
            continue
        total += value
        found = True
    return total if found else None


def _resolve_operator_name() -> str:
    if hasattr(request, "mobile_user") and request.mobile_user:
        return _text(request.mobile_user.get("username")) or "mobile"
    user = session.get("user")
    if isinstance(user, dict):
        return _coalesce_str(user.get("display_name"), user.get("username"), "web")
    return "system"


def _parse_field_keys(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [_text(item) for item in raw if _text(item)]
    if raw is None:
        return []
    text = str(raw).replace("\r", "\n")
    parts = []
    for chunk in text.split("\n"):
        parts.extend(piece.strip() for piece in chunk.split(","))
    return [item for item in parts if item]


def _extract_settings_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "kingdee_workhour_enabled": _as_bool(data.get("kingdee_workhour_enabled"), False),
        "kingdee_base_url": _text(data.get("kingdee_base_url")),
        "kingdee_acct_id": _text(data.get("kingdee_acct_id")),
        "kingdee_username": _text(data.get("kingdee_username")),
        "kingdee_app_id": _text(data.get("kingdee_app_id")),
        "kingdee_lcid": _safe_int(data.get("kingdee_lcid"), 2052),
        "kingdee_verify_ssl": _as_bool(data.get("kingdee_verify_ssl"), True),
        "kingdee_timeout_secs": max(5, _safe_int(data.get("kingdee_timeout_secs"), 15)),
        "kingdee_workhour_form_id": _text(data.get("kingdee_workhour_form_id")),
        "kingdee_workhour_field_keys": _parse_field_keys(data.get("kingdee_workhour_field_keys")),
        "kingdee_workhour_filter_template": _text(data.get("kingdee_workhour_filter_template")),
        "kingdee_workhour_order_string": _text(data.get("kingdee_workhour_order_string")),
        "kingdee_workhour_top_rows": max(0, _safe_int(data.get("kingdee_workhour_top_rows"), 0)),
        "kingdee_workhour_limit": max(1, _safe_int(data.get("kingdee_workhour_limit"), 200)),
        "kingdee_workhour_start_row": max(0, _safe_int(data.get("kingdee_workhour_start_row"), 0)),
        "kingdee_workhour_product_code_field": _text(data.get("kingdee_workhour_product_code_field")),
        "kingdee_workhour_work_order_field": _text(data.get("kingdee_workhour_work_order_field")),
        "kingdee_workhour_serial_field": _text(data.get("kingdee_workhour_serial_field")),
        "kingdee_workhour_process_code_field": _text(data.get("kingdee_workhour_process_code_field")),
        "kingdee_workhour_process_name_field": _text(data.get("kingdee_workhour_process_name_field")),
        "kingdee_workhour_process_desc_field": _text(data.get("kingdee_workhour_process_desc_field")),
        "kingdee_workhour_completed_qty_field": _text(data.get("kingdee_workhour_completed_qty_field")),
        "kingdee_workhour_qty_field": _text(data.get("kingdee_workhour_completed_qty_field"))
            or _text(data.get("kingdee_workhour_qty_field")),
        "kingdee_workhour_report_actual_hours_field": _text(data.get("kingdee_workhour_report_actual_hours_field")),
    }

    raw_secret = data.get("kingdee_app_secret")
    clear_secret = _as_bool(data.get("clear_kingdee_app_secret"), False)
    if clear_secret:
        payload["kingdee_app_secret"] = ""
    elif raw_secret not in (None, "") and _text(raw_secret) != "******":
        payload["kingdee_app_secret"] = str(raw_secret)

    return payload


def _current_settings_payload() -> Dict[str, Any]:
    app_secret = _text(config.get("kingdee_app_secret", ""))
    return {
        "kingdee_workhour_enabled": _as_bool(config.get("kingdee_workhour_enabled", False), False),
        "kingdee_base_url": _text(config.get("kingdee_base_url", "")),
        "kingdee_acct_id": _text(config.get("kingdee_acct_id", "")),
        "kingdee_username": _text(config.get("kingdee_username", "")),
        "kingdee_app_id": _text(config.get("kingdee_app_id", "")),
        "kingdee_app_secret": "******" if app_secret else "",
        "kingdee_app_secret_configured": bool(app_secret),
        "kingdee_lcid": _safe_int(config.get("kingdee_lcid", 2052), 2052),
        "kingdee_verify_ssl": _as_bool(config.get("kingdee_verify_ssl", True), True),
        "kingdee_timeout_secs": _safe_int(config.get("kingdee_timeout_secs", 15), 15),
        "kingdee_workhour_form_id": _text(config.get("kingdee_workhour_form_id", "")),
        "kingdee_workhour_field_keys": config.get("kingdee_workhour_field_keys", []),
        "kingdee_workhour_filter_template": _text(config.get("kingdee_workhour_filter_template", "")),
        "kingdee_workhour_order_string": _text(config.get("kingdee_workhour_order_string", "")),
        "kingdee_workhour_top_rows": _safe_int(config.get("kingdee_workhour_top_rows", 0), 0),
        "kingdee_workhour_limit": _safe_int(config.get("kingdee_workhour_limit", 200), 200),
        "kingdee_workhour_start_row": _safe_int(config.get("kingdee_workhour_start_row", 0), 0),
        "kingdee_workhour_product_code_field": _text(config.get("kingdee_workhour_product_code_field", "")),
        "kingdee_workhour_work_order_field": _text(config.get("kingdee_workhour_work_order_field", "")),
        "kingdee_workhour_serial_field": _text(config.get("kingdee_workhour_serial_field", "")),
        "kingdee_workhour_process_code_field": _text(config.get("kingdee_workhour_process_code_field", "")),
        "kingdee_workhour_process_name_field": _text(config.get("kingdee_workhour_process_name_field", "")),
        "kingdee_workhour_process_desc_field": _text(config.get("kingdee_workhour_process_desc_field", "")),
        "kingdee_workhour_completed_qty_field": _coalesce_str(
            config.get("kingdee_workhour_completed_qty_field", ""),
            config.get("kingdee_workhour_qty_field", ""),
        ),
        "kingdee_workhour_report_actual_hours_field": _text(
            config.get("kingdee_workhour_report_actual_hours_field", "")
        ),
    }


def register_kingdee_work_hours_api(app, deps: Dict[str, Any]) -> None:
    """Register Kingdee work-hour sync routes."""

    login_required = deps["login_required"]
    admin_required = deps["admin_required"]
    logger = deps["logger"]
    data_dir = Path(deps["data_dir"])
    db_path = data_dir / "log" / "work_hours.db"
    serial_lookup_db_path = data_dir / "lookup_cache" / "serial_lookup.db"
    store = WorkHourStore(db_path, logger)
    serial_lookup_store = SerialLookupStore(serial_lookup_db_path, logger)
    local_only_message = (
        "Kingdee read-only lookup is enabled for work-order backfill; write operations remain disabled."
    )

    def _build_client() -> KingdeeClient:
        return KingdeeClient(logger)

    def _infer_serial_product_context_from_mes_snapshot(serial_number: str) -> Dict[str, Any]:
        serial = _normalize_serial(serial_number)
        if not serial:
            return {}
        try:
            settings = get_mes_remote_settings()
            snapshot_dir = refresh_mes_snapshot(settings, force=False, logger=logger)
        except Exception as exc:
            logger.warning("[工时] 刷新 MES 快照失败，无法为串号 %s 推断产品型号: %s", serial, exc)
            return {}

        try:
            product_records = _load_product_records(snapshot_dir)
            product_configs = _load_product_configs(snapshot_dir)
        except Exception as exc:
            logger.warning("[工时] 读取 MES 快照失败，无法为串号 %s 推断产品型号: %s", serial, exc)
            return {}

        records_by_serial: Dict[str, Dict[str, Any]] = {}
        for record in product_records:
            record_serial = _text(record.get("product_serial"))
            if not record_serial:
                continue
            existing = records_by_serial.get(record_serial)
            if existing is None or _safe_int(record.get("scan_time"), 0) > _safe_int(existing.get("scan_time"), 0):
                records_by_serial[record_serial] = record

        record_key = _find_suffix_match(records_by_serial, serial)
        if not record_key:
            return {}

        record = records_by_serial.get(record_key) or {}
        config_item = product_configs.get((record.get("project_name"), record.get("product_type"))) or {}
        product_code = _coalesce_str(
            config_item.get("model_number"),
            record.get("product_code"),
            record.get("model_number"),
            record.get("product_type"),
        )
        if not product_code:
            return {}
        return {
            "serial_number": record_key,
            "product_code": product_code,
            "project_name": _text(record.get("project_name")),
            "product_type": _text(record.get("product_type")),
        }

    def _lookup_serial_summary_from_kingdee(
        serial_number: str,
        product_code: str = "",
    ) -> Optional[Dict[str, Any]]:
        serial = _normalize_serial(serial_number)
        if not serial:
            return None

        client = _build_client()
        context_rows: List[Dict[str, Any]] = []
        candidate_used = serial
        for candidate in _derive_serial_lookup_candidates(serial, product_code):
            context_rows = client.query_serial_production_contexts(candidate)
            if context_rows:
                candidate_used = candidate
                break
        if not context_rows:
            return None

        context = None
        for item in context_rows:
            if _text(item.get("work_order_no")) and _text(item.get("product_code")):
                context = dict(item)
                break
        if context is None:
            context = dict(context_rows[0])

        work_order_no = _text(context.get("work_order_no"))
        resolved_product_code = _text(context.get("product_code")) or _text(product_code)
        if not work_order_no or not resolved_product_code:
            return None

        short_serial_candidates = _derive_serial_lookup_candidates(serial, resolved_product_code)
        short_serial_number = ""
        for candidate in short_serial_candidates:
            if candidate != serial:
                short_serial_number = candidate
                break
        if not short_serial_number and candidate_used != serial:
            short_serial_number = candidate_used

        process_rows = client.query_work_order_process_rows_readonly(work_order_no)
        matching_rows = [
            dict(row)
            for row in process_rows
            if not resolved_product_code
            or not _text(row.get("product_code"))
            or _text(row.get("product_code")) == resolved_product_code
        ]
        actual_total_work_hours = _sum_reported_actual_work_hours(
            matching_rows or process_rows,
            product_code=resolved_product_code if matching_rows else "",
        )

        return serial_lookup_store.upsert_summary(
            serial_number=serial,
            short_serial_number=short_serial_number,
            product_code=resolved_product_code,
            work_order_no=work_order_no,
            completed_qty=_safe_float(context.get("completed_qty")),
            actual_total_work_hours=actual_total_work_hours,
            source=_text(context.get("source")) or "kingdee_serial_lookup",
            payload={
                "requested_serial_number": serial,
                "requested_product_code": _text(product_code),
                "candidate_used": candidate_used,
                "production_contexts": context_rows,
                "process_rows": matching_rows or process_rows,
            },
        )

    def _get_serial_lookup_summary(
        serial_number: str,
        *,
        product_code: str = "",
        allow_kingdee: bool = True,
    ) -> Tuple[Optional[Dict[str, Any]], str, Dict[str, Any]]:
        serial = _normalize_serial(serial_number)
        if not serial:
            return None, "missing", {}

        cached = serial_lookup_store.get_by_serial(serial)
        if cached:
            return cached, "cache", {
                "serial_number": _text(cached.get("serial_number")) or serial,
                "product_code": _text(cached.get("product_code")),
                "source": "cache",
            }

        inferred_context: Dict[str, Any] = {}
        resolved_product_code = _text(product_code)
        if resolved_product_code:
            inferred_context = {
                "serial_number": serial,
                "product_code": resolved_product_code,
                "source": "request",
            }
        else:
            snapshot_context = _infer_serial_product_context_from_mes_snapshot(serial)
            resolved_product_code = _text(snapshot_context.get("product_code"))
            if resolved_product_code:
                inferred_context = {
                    **snapshot_context,
                    "source": "mes_snapshot",
                }

        if not allow_kingdee or not _as_bool(config.get("kingdee_workhour_enabled", False), False):
            return None, "missing", inferred_context

        summary = _lookup_serial_summary_from_kingdee(serial, resolved_product_code)
        if summary:
            return summary, "kingdee", inferred_context
        return None, "missing", inferred_context

    def _infer_process_responsible_department(process_name: Any, process_code: Any = "") -> str:
        """Map a Kingdee process row to the MES department bucket used by the UI."""
        name = _text(process_name)
        code = _text(process_code)
        text = f"{name} {code}"
        if any(keyword in text.lower() for keyword in ("package", "boxing", "warehouse", "shipment", "shipping", "stock in")):
            return "Project推进部-仓库"
        if any(keyword in text.lower() for keyword in ("test", "aging", "bench", "back-emf", "sample receive", "inspection")):
            return "测试和实验室"
        if any(keyword in text.lower() for keyword in ("assembly", "install", "production", "press", "embed", "glue", "airtight")):
            return "智能制造部-生产"
        return ""

    def _resolve_mes_process_responsible_department(
        row: Dict[str, Any],
        product_configs: Dict[tuple, Dict[str, Any]],
    ) -> str:
        """Resolve row-level department from MES product/process config first."""
        product_code = _text(row.get("product_code"))
        process_name = _text(row.get("process_name")) or _text(row.get("process_desc"))
        if not product_code or not process_name:
            return ""

        process_token = _normalize_process_token(process_name)
        if not process_token:
            return ""

        candidates: List[Dict[str, Any]] = []
        for config_item in product_configs.values():
            model_number = _text(config_item.get("model_number"))
            product_type = _text(config_item.get("type_name"))
            if model_number == product_code:
                candidates.insert(0, config_item)
            elif model_number and (product_code in model_number or model_number in product_code):
                candidates.append(config_item)
            elif product_code and product_code in product_type:
                candidates.append(config_item)

        seen_configs: set[int] = set()
        unique_candidates: List[Dict[str, Any]] = []
        for config_item in candidates:
            marker = id(config_item)
            if marker in seen_configs:
                continue
            seen_configs.add(marker)
            unique_candidates.append(config_item)

        for config_item in unique_candidates:
            for step in config_item.get("steps") or []:
                step_name = _text(step.get("name"))
                step_token = _normalize_process_token(step_name)
                if not step_token:
                    continue
                if step_token != process_token and step_token not in process_token and process_token not in step_token:
                    continue
                departments = [
                    _text(department)
                    for department in (step.get("responsible_departments") or [])
                    if _text(department) and "璐ㄩ噺" not in _text(department)
                ]
                if departments:
                    return ", ".join(dict.fromkeys(departments))
        return ""

    def _enrich_product_summary_department_hours(summary: Dict[str, Any]) -> None:
        """Attach MES picture-based department hour breakdowns to product rows."""
        product_summaries = summary.get("product_summaries")
        serial_summaries = summary.get("serial_summaries")
        if not product_summaries:
            return
        if current_app.config.get("TESTING"):
            return

        def _empty_department_hours() -> Dict[str, Any]:
            return {
                "department_work_hours_display": "-",
                "department_rows": [
                    {"responsible_department": "智能制造部-生产", "duration_ms": 0, "duration_hours": 0.0},
                    {"responsible_department": "测试和实验室", "duration_ms": 0, "duration_hours": 0.0},
                    {"responsible_department": "项目推进部-仓库", "duration_ms": 0, "duration_hours": 0.0},
                ],
                "department_total_duration_ms": 0,
                "department_total_formula_display": "-",
                "matched_serial_count": 0,
                "completed_serial_count": 0,
            }

        def _apply_department_hours(row: Dict[str, Any], item: Dict[str, Any]) -> None:
            row["department_work_hours_display"] = item.get("department_work_hours_display") or ""
            row["department_work_hours_detail"] = item.get("department_rows") or []
            row["department_total_duration_ms"] = _safe_int(item.get("department_total_duration_ms"), 0)
            row["department_total_formula_display"] = item.get("department_total_formula_display") or ""
            if row["department_total_duration_ms"] > 0:
                row["total_duration_ms"] = row["department_total_duration_ms"]
            row["department_completed_serial_count"] = _safe_int(item.get("completed_serial_count"), 0)
            row["department_matched_serial_count"] = _safe_int(item.get("matched_serial_count"), 0)

        serials_by_product: Dict[str, List[str]] = {}
        for row in serial_summaries or []:
            product_code = _text(row.get("product_code"))
            serial_number = _normalize_serial(row.get("serial_number"))
            if not product_code or not serial_number:
                continue
            serials_by_product.setdefault(product_code, []).append(serial_number)

        try:
            settings = get_mes_remote_settings()
            snapshot_dir = refresh_mes_snapshot(settings, force=False, logger=logger)
        except Exception:
            logger.exception("[MES work-hours] Failed to refresh read-only MES snapshot; skipping product summary calculation")
            empty = _empty_department_hours()
            for row in product_summaries:
                _apply_department_hours(row, empty)
            return

        try:
            product_configs = _load_product_configs(snapshot_dir)
        except Exception:
            logger.exception("[MES work-hours] Failed to load MES department responsibility config; using fallback department rules")
            product_configs = {}

        cached_by_key: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        empty_hours = _empty_department_hours()
        for row in product_summaries:
            row["responsible_department"] = (
                _resolve_mes_process_responsible_department(row, product_configs)
                or _infer_process_responsible_department(row.get("process_name"), row.get("process_code"))
                or _text(row.get("responsible_department"))
            )
            product_code = _text(row.get("product_code"))
            serial_numbers = [
                _normalize_serial(item)
                for item in (row.get("kingdee_serial_numbers") or serials_by_product.get(product_code) or [])
                if _normalize_serial(item)
            ]
            serial_numbers = sorted(set(serial_numbers))
            if not product_code or not serial_numbers:
                _apply_department_hours(row, empty_hours)
                continue
            cache_key = (product_code, _text(row.get("spec_model")), "|".join(serial_numbers))
            if cache_key not in cached_by_key:
                try:
                    cached_by_key[cache_key] = build_department_hour_summaries_for_serials(
                        snapshot_dir,
                        serial_numbers,
                        require_all_departments_complete=False,
                        preassembly_context={
                            "kingdee_spec_model": _text(row.get("spec_model")),
                            "require_kingdee_spec_model": True,
                            "product_code": product_code,
                            "process_name": _text(row.get("process_name")),
                        },
                    )
                except Exception:
                    logger.exception("[MES宸ユ椂] 璁＄畻浜у搧 %s 閮ㄩ棬宸ユ椂澶辫触", product_code)
                    cached_by_key[cache_key] = empty_hours
            _apply_department_hours(row, cached_by_key[cache_key])

        overview = summary.get("overview")
        if isinstance(overview, dict):
            completed_serial_count = sum(
                _safe_int(row.get("department_completed_serial_count"), 0)
                for row in product_summaries
            )
            total_duration_ms = sum(
                _safe_int(row.get("department_total_duration_ms"), 0)
                for row in product_summaries
            )
            overview["completed_serial_count"] = completed_serial_count
            overview["total_duration_ms"] = total_duration_ms if completed_serial_count > 0 else None

    def _refresh_product_summaries_from_kingdee(summary: Dict[str, Any], work_order: str) -> None:
        """Use Kingdee read-only process/report rows to avoid stale local product-code rows."""
        if current_app.config.get("TESTING"):
            return
        if not _as_bool(config.get("kingdee_workhour_enabled", False), False):
            return

        try:
            client = _build_client()
            rows = client.query_work_order_process_rows_readonly(work_order)
        except Exception:
            logger.exception("[MES work-hours] Read-only Kingdee product/process summary query failed; keeping local summary")
            return
        if not rows:
            return

        planning_rows: List[Dict[str, Any]] = []
        try:
            planning_rows = client.query_work_order_planning_rows_readonly(work_order)
        except Exception:
            logger.exception("[MES宸ユ椂] 閲戣澏宸ュ簭璁″垝瑙勬牸鍨嬪彿鏌ヨ澶辫触锛岄瑁呴厤鏃堕棿灏嗕笉浣跨敤瑙勬牸鍨嬪彿")

        planning_spec_by_key: Dict[Tuple[str, str, str], str] = {}
        planning_spec_by_code: Dict[Tuple[str, str], str] = {}
        planning_spec_by_product: Dict[str, str] = {}
        for planning in planning_rows:
            planning_product = _text(planning.get("product_code"))
            planning_process_code = _text(planning.get("process_code"))
            planning_process_name = _coalesce_str(
                planning.get("process_name"),
                planning.get("process_desc"),
                planning_process_code,
                "-",
            )
            planning_spec = _text(planning.get("spec_model"))
            if not planning_product or not planning_spec:
                continue
            planning_spec_by_product.setdefault(planning_product, planning_spec)
            planning_spec_by_code.setdefault((planning_product, planning_process_code), planning_spec)
            planning_spec_by_key.setdefault(
                (planning_product, planning_process_code, planning_process_name),
                planning_spec,
            )

        serials_by_product: Dict[str, List[str]] = {}
        try:
            contexts = client.query_work_order_production_contexts_readonly(work_order)
        except Exception:
            logger.exception("[MES work-hours] Read-only Kingdee serial context query failed; refreshing product/process rows only")
            contexts = []
        for item in contexts:
            product_code = _text(item.get("product_code"))
            serial_number = _normalize_serial(item.get("serial_number"))
            if not product_code or not serial_number:
                continue
            serials_by_product.setdefault(product_code, []).append(serial_number)

        local_rows = summary.get("product_summaries") or []
        local_by_key: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for row in local_rows:
            key = (
                _text(row.get("product_code")),
                _text(row.get("process_code")),
                _text(row.get("process_name")),
            )
            local_by_key[key] = row

        refreshed: List[Dict[str, Any]] = []
        seen = set()
        for row in rows:
            product_code = _text(row.get("product_code")) or "-"
            process_code = _text(row.get("process_code"))
            process_name = _coalesce_str(row.get("process_name"), row.get("process_desc"), process_code, "-")
            key = (product_code, process_code, process_name)
            if key in seen:
                continue
            seen.add(key)
            planning_spec_model = (
                planning_spec_by_key.get(key)
                or planning_spec_by_code.get((product_code, process_code))
                or planning_spec_by_product.get(product_code)
                or ""
            )

            local = dict(local_by_key.get(key) or {})
            completed_qty = row.get("completed_qty")
            count_value = completed_qty if completed_qty is not None else local.get("tracked_serial_count", 0)
            local.update(
                {
                    "work_order_no": work_order,
                    "product_code": product_code,
                    "process_key": _coalesce_str(row.get("process_key"), process_code, process_name),
                    "process_code": process_code,
                    "process_name": process_name,
                    "process_desc": _coalesce_str(row.get("process_desc"), process_name),
                    "spec_model": planning_spec_model,
                    "spec_model_source": "SFC_OperationPlanning" if planning_spec_model else "",
                    "responsible_department": _infer_process_responsible_department(process_name, process_code),
                    "completed_qty": completed_qty if completed_qty is not None else local.get("completed_qty", 0),
                    "tracked_serial_count": local.get("tracked_serial_count") or count_value or 0,
                    "completed_serial_count": local.get("completed_serial_count") or count_value or 0,
                    "first_start_time_ms": local.get("first_start_time_ms"),
                    "last_end_time_ms": local.get("last_end_time_ms"),
                    "total_duration_ms": local.get("total_duration_ms") or 0,
                    "kingdee_serial_numbers": sorted(set(serials_by_product.get(product_code) or [])),
                    "kingdee_serial_count": len(set(serials_by_product.get(product_code) or [])),
                }
            )
            refreshed.append(local)

        refreshed_product_codes = {
            _text(row.get("product_code"))
            for row in refreshed
            if _text(row.get("product_code"))
        }
        for product_code, serial_numbers in sorted(serials_by_product.items()):
            if not product_code or product_code in refreshed_product_codes:
                continue
            planning_spec_model = planning_spec_by_product.get(product_code) or ""
            serials = sorted(set(serial_numbers))
            refreshed.append(
                {
                    "work_order_no": work_order,
                    "product_code": product_code,
                    "process_key": product_code,
                    "process_code": "",
                    "process_name": "",
                    "process_desc": "",
                    "spec_model": planning_spec_model,
                    "spec_model_source": "SFC_OperationPlanning" if planning_spec_model else "",
                    "responsible_department": "",
                    "completed_qty": len(serials),
                    "tracked_serial_count": len(serials),
                    "completed_serial_count": len(serials),
                    "first_start_time_ms": None,
                    "last_end_time_ms": None,
                    "total_duration_ms": 0,
                    "kingdee_serial_numbers": serials,
                    "kingdee_serial_count": len(serials),
                }
            )

        if not refreshed:
            return
        summary["product_summaries"] = refreshed
        overview = summary.get("overview")
        if isinstance(overview, dict):
            overview["product_code_count"] = len(refreshed)

    def _sync_work_order_snapshot(
        work_order_no: str,
        *,
        project_name: str = "",
        product_type: str = "",
        operator: str = "",
        started_at_ms: Optional[int] = None,
        source: str = "work_order_sync",
    ) -> Dict[str, Any]:
        work_order = _text(work_order_no)
        if not work_order:
            raise ValueError("workOrderNo 涓嶈兘涓虹┖")

        client = _build_client()
        payloads = client.query_work_order_payloads(work_order)
        if not payloads:
            raise LookupError("鏈粠閲戣澏鏌ヨ鍒拌宸ュ崟鍙峰搴旂殑搴忓垪鍙锋垨宸ュ簭鏁版嵁")

        started_ms = started_at_ms if started_at_ms is not None else _now_ms()
        inserted_count = 0
        updated_count = 0
        process_count = 0
        synced_serial_numbers: List[str] = []
        skipped_serial_numbers: List[str] = []

        for payload in payloads:
            serial_number = _normalize_serial(payload.get("serial_number"))
            process_rows = payload.get("process_rows") or []
            if not serial_number or not process_rows:
                if serial_number:
                    skipped_serial_numbers.append(serial_number)
                continue

            sync_result = store.sync_material_scan(
                serial_number,
                process_rows,
                project_name=project_name,
                product_type=product_type,
                operator=operator,
                started_at_ms=started_ms,
                source=source,
            )
            inserted_count += _safe_int(sync_result.get("inserted_count"), 0)
            updated_count += _safe_int(sync_result.get("updated_count"), 0)
            process_count += _safe_int(sync_result.get("process_count"), 0)
            synced_serial_numbers.append(serial_number)
            serial_lookup_store.upsert_summary(
                serial_number=serial_number,
                short_serial_number="",
                product_code=_text(payload.get("product_code")),
                work_order_no=work_order,
                completed_qty=_safe_float(payload.get("completed_qty")),
                actual_total_work_hours=_sum_reported_actual_work_hours(
                    process_rows,
                    product_code=payload.get("product_code"),
                ),
                source=source,
                payload=payload,
            )

        return {
            "workOrderNo": work_order,
            "syncedSerialCount": len(synced_serial_numbers),
            "skippedSerialCount": len(skipped_serial_numbers),
            "insertedCount": inserted_count,
            "updatedCount": updated_count,
            "processCount": process_count,
            "syncedSerialNumbers": synced_serial_numbers[:20],
            "skippedSerialNumbers": skipped_serial_numbers[:20],
            "summary": store.summarize_work_order(work_order),
        }

    @app.route('/mes-work-hours')
    @app.route('/mes/work-hours')
    @app.route('/kingdee/work-hours')
    @login_required
    def mes_work_hours_page():
        return render_template('mes_work_hours.html')

    @app.route('/api/settings/kingdee-work-hours', methods=['GET'])
    @admin_required
    def api_get_kingdee_work_hour_settings():
        return jsonify(
            {
                "success": True,
                "disabled": False,
                "message": local_only_message,
                "settings": _current_settings_payload(),
            }
        )

    @app.route('/api/settings/kingdee-work-hours', methods=['PUT'])
    @admin_required
    def api_save_kingdee_work_hour_settings():
        return jsonify({"success": False, "message": local_only_message}), 410

    @app.route('/api/settings/kingdee-work-hours/preview', methods=['POST'])
    @admin_required
    def api_preview_kingdee_work_hour_query():
        return jsonify({"success": False, "message": local_only_message}), 410

    @app.route('/api/kingdee/work-hours/material-scan', methods=['POST'])
    @login_required
    def api_kingdee_work_hours_material_scan():
        return jsonify({"success": False, "message": local_only_message}), 410

    @app.route('/api/kingdee/work-hours/generate-operation-report', methods=['POST'])
    @login_required
    def api_kingdee_work_hours_generate_operation_report():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"success": False, "message": "JSON object payload is required"}), 400

        try:
            client = _build_client()
            result = client.generate_operation_report(payload)
        except Exception as exc:
            logger.exception("[Kingdee work-hours] Failed to generate operation report")
            return jsonify({"success": False, "message": f"Generate operation report failed: {exc}"}), 500

        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.route('/api/kingdee/work-hours/process-complete', methods=['POST'])
    @login_required
    def api_kingdee_work_hours_process_complete():
        return jsonify({"success": False, "message": local_only_message}), 410

    @app.route('/api/kingdee/work-hours/serial/<serial_number>', methods=['GET'])
    @login_required
    def api_kingdee_work_hours_serial_summary(serial_number: str):
        serial = _normalize_serial(serial_number)
        rows = store.list_serial_records(serial)
        lookup_summary, lookup_source, inferred_context = _get_serial_lookup_summary(serial, allow_kingdee=True)
        return jsonify(
            {
                "success": True,
                "serialNumber": serial,
                "count": len(rows),
                "records": rows,
                "lookup": lookup_summary,
                "lookup_found": lookup_summary is not None,
                "lookup_source": lookup_source,
                "inferred_serial_number": _text(inferred_context.get("serial_number")),
                "inferred_product_code": _text(inferred_context.get("product_code")),
                "inferred_project_name": _text(inferred_context.get("project_name")),
                "inferred_product_type": _text(inferred_context.get("product_type")),
                "inferred_product_context_source": _text(inferred_context.get("source")),
            }
        )

    @app.route('/api/mes/work-hours/work-order/<work_order_no>', methods=['GET'])
    @app.route('/api/kingdee/work-hours/work-order/<work_order_no>', methods=['GET'])
    @login_required
    def api_kingdee_work_hours_work_order_summary(work_order_no: str):
        work_order = _text(work_order_no)
        include_records = _as_bool(request.args.get("includeRecords"), False)
        auto_sync_requested = _as_bool(request.args.get("autoSync"), True)
        summary = store.summarize_work_order(work_order)
        auto_sync_attempted = False
        auto_sync_succeeded = False
        auto_sync_message = ""

        if (
            not (summary.get("serial_summaries") or [])
            and work_order
            and auto_sync_requested
            and _as_bool(config.get("kingdee_workhour_enabled", False), False)
        ):
            auto_sync_attempted = True
            try:
                sync_result = _sync_work_order_snapshot(
                    work_order,
                    operator=_resolve_operator_name(),
                    source="api_work_order_lookup",
                )
                summary = sync_result.get("summary") or store.summarize_work_order(work_order)
                auto_sync_succeeded = bool((summary.get("serial_summaries") or []))
                auto_sync_message = (
                    f"Synced from Kingdee: {sync_result.get('syncedSerialCount', 0)} serial(s), "
                    f"{sync_result.get('processCount', 0)} process row(s)."
                )
            except Exception as exc:
                logger.exception("[Kingdee work-hours] Work order auto-sync failed for %s", work_order)
                auto_sync_message = f"Kingdee auto-sync failed: {exc}"

        try:
            _enrich_product_summary_department_hours(summary)
        except Exception:
            logger.exception("[MES work-hours] Failed to enrich department-hour summary for %s", work_order)

        if include_records:
            summary["records"] = store.list_work_order_records(work_order)
        return jsonify(
            {
                "success": True,
                "auto_sync_attempted": auto_sync_attempted,
                "auto_sync_succeeded": auto_sync_succeeded,
                "auto_sync_message": auto_sync_message,
                **summary,
            }
        )

    def _parse_completed_range_from_request() -> Tuple[int, int, str, str, Optional[Response]]:
        start_date = _text(request.args.get("startDate"))
        end_date = _text(request.args.get("endDate"))
        if start_date and end_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0)
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999000)
                start_ms = int(start_dt.timestamp() * 1000)
                end_ms = int(end_dt.timestamp() * 1000)
            except ValueError:
                return 0, 0, start_date, end_date, jsonify({"success": False, "message": "Date format must be YYYY-MM-DD"})
        else:
            start_ms, end_ms = default_last_month_range()
            start_date = datetime.fromtimestamp(start_ms / 1000).strftime("%Y-%m-%d")
            end_date = datetime.fromtimestamp(end_ms / 1000).strftime("%Y-%m-%d")

        if end_ms < start_ms:
            return start_ms, end_ms, start_date, end_date, jsonify({"success": False, "message": "End date cannot be earlier than start date"})
        return start_ms, end_ms, start_date, end_date, None

    def _canonical_export_department(department: str) -> str:
        name = _text(department)
        if "生产" in name:
            return "智能制造部-生产"
        if "测试" in name or "实验室" in name:
            return "测试和实验室"
        if "仓库" in name:
            return "项目推进部-仓库"
        return name

    def _summarize_completed_export_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        department_labels = ["智能制造部-生产", "测试和实验室", "项目推进部-仓库"]
        grouped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for row in rows:
            key = (
                _text(row.get("work_order_no")),
                _text(row.get("product_code")),
                _normalize_serial(row.get("serial_number")),
            )
            if not key[2]:
                continue
            item = grouped.setdefault(
                key,
                {
                    "work_order_no": key[0],
                    "product_code": key[1],
                    "serial_number": key[2],
                    "completed_quantity": _safe_int(row.get("completed_quantity"), 1) or 1,
                    "department_durations": {label: 0 for label in department_labels},
                    "serial_completed_at_ms": _safe_int(row.get("serial_completed_at_ms"), 0),
                },
            )
            department = _canonical_export_department(row.get("responsible_department"))
            if department in item["department_durations"]:
                item["department_durations"][department] += _safe_int(row.get("department_duration_ms"), 0)
            item["serial_completed_at_ms"] = max(
                _safe_int(item.get("serial_completed_at_ms"), 0),
                _safe_int(row.get("serial_completed_at_ms"), 0),
            )

        result: List[Dict[str, Any]] = []
        for item in grouped.values():
            durations = item["department_durations"]
            hours = {label: durations.get(label, 0) / 3600000 for label in department_labels}
            work_hours_display = ", ".join(f"{label} {hours[label]:.2f}h" for label in department_labels)
            total_ms = sum(durations.get(label, 0) for label in department_labels)
            item.update(
                {
                    "work_hours_display": work_hours_display,
                    "responsible_departments": ", ".join(department_labels),
                    "total_duration_ms": total_ms,
                    "total_hours_formula": f"{total_ms / 3600000:.2f}h",
                }
            )
            result.append(item)
        result.sort(
            key=lambda row: (
                _safe_int(row.get("serial_completed_at_ms"), 0),
                _text(row.get("work_order_no")),
                _text(row.get("product_code")),
                _normalize_serial(row.get("serial_number")),
            )
        )
        return result

    def _query_completed_export_rows(start_ms: int, end_ms: int, refresh_mes: bool) -> List[Dict[str, Any]]:
        settings = get_mes_remote_settings()
        snapshot_dir = refresh_mes_snapshot(settings, force=refresh_mes, logger=logger)

        def _lookup_completed_work_order(serial_number: str, product_code: str = "") -> str:
            lookup_summary, _lookup_source, _inferred_context = _get_serial_lookup_summary(
                serial_number,
                product_code=product_code,
                allow_kingdee=True,
            )
            return _text(lookup_summary.get("work_order_no")) if lookup_summary else ""

        raw_rows = build_completed_work_hour_rows(
            snapshot_dir,
            start_ms=start_ms,
            end_ms=end_ms,
            work_order_lookup=_lookup_completed_work_order,
        )
        return _summarize_completed_export_rows(raw_rows)

    @app.route('/api/mes/work-hours/completed-summary', methods=['GET'])
    @app.route('/api/kingdee/work-hours/completed-summary', methods=['GET'])
    @login_required
    def api_kingdee_work_hours_completed_summary():
        start_ms, end_ms, start_date, end_date, error_response = _parse_completed_range_from_request()
        if error_response is not None:
            return error_response, 400
        refresh_mes = _as_bool(request.args.get("refreshMes"), False)
        try:
            rows = _query_completed_export_rows(start_ms, end_ms, refresh_mes)
            return jsonify(
                {
                    "success": True,
                    "start_date": start_date,
                    "end_date": end_date,
                    "row_count": len(rows),
                    "rows": rows,
                }
            )
        except Exception as exc:
            logger.exception("[MES work-hours] Failed to query completed work hours")
            return jsonify({"success": False, "message": f"Query failed: {exc}"}), 500

    @app.route('/api/mes/work-hours/completed-export', methods=['GET'])
    @app.route('/api/kingdee/work-hours/completed-export', methods=['GET'])
    @login_required
    def api_kingdee_work_hours_completed_export():
        start_ms, end_ms, start_date, end_date, error_response = _parse_completed_range_from_request()
        if error_response is not None:
            return error_response, 400
        refresh_mes = _as_bool(request.args.get("refreshMes"), False)

        try:
            rows = _query_completed_export_rows(start_ms, end_ms, refresh_mes)

            from openpyxl import Workbook
            from openpyxl.styles import Font

            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Work Hours"
            headers = [
                "Work Order No",
                "Product Code",
                "Serial No",
                "Completed Qty",
                "Work Hours",
                "Actual Total Hours",
            ]
            sheet.append(headers)
            for cell in sheet[1]:
                cell.font = Font(bold=True)

            for row in rows:
                sheet.append(
                    [
                        row.get("work_order_no", ""),
                        row.get("product_code", ""),
                        row.get("serial_number", ""),
                        row.get("completed_quantity", 0),
                        row.get("work_hours_display", ""),
                        row.get("total_hours_formula", ""),
                    ]
                )

            for column_cells in sheet.columns:
                column_letter = column_cells[0].column_letter
                max_length = max(len(str(cell.value or "")) for cell in column_cells)
                sheet.column_dimensions[column_letter].width = min(max(max_length + 2, 12), 48)

            output = BytesIO()
            workbook.save(output)
            output.seek(0)
            filename = f"work-hours-{start_date or 'last-month'}-{end_date or 'today'}.xlsx"
            return Response(
                output.getvalue(),
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "X-Export-Row-Count": str(len(rows)),
                },
            )
        except Exception as exc:
            logger.exception("[MES work-hours] Failed to export completed work hours")
            return jsonify({"success": False, "message": f"Export failed: {exc}"}), 500
