from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import re

try:  # pragma: no cover - package import for local tests
    from app_web import project_config_manager as _project_config_manager  # type: ignore
except ImportError:  # pragma: no cover - NAS test env runs from app_web cwd
    import project_config_manager as _project_config_manager  # type: ignore

try:  # pragma: no cover
    from app_web.project_name_utils import resolve_project_config_stem
except ImportError:  # pragma: no cover
    try:
        from qrmes_shared_core.project_name_utils import resolve_project_config_stem  # type: ignore
    except ImportError:  # pragma: no cover
        resolve_project_config_stem = None  # type: ignore

try:  # pragma: no cover
    from app_web.qc_api_routes import normalize_step_key as _normalize_step_key
except Exception:  # pragma: no cover
    try:
        from qc_api_routes import normalize_step_key as _normalize_step_key  # type: ignore
    except Exception:  # pragma: no cover
        _normalize_step_key = None  # type: ignore

try:  # pragma: no cover
    from app_web.records_query import compute_material_status
except ImportError:  # pragma: no cover
    from records_query import compute_material_status  # type: ignore

try:  # pragma: no cover
    from app_web.photo_index import DEFAULT_DB_PATH as PHOTO_INDEX_DB_PATH
    from app_web.photo_index import scan_and_update as scan_photo_index
except ImportError:  # pragma: no cover
    from photo_index import DEFAULT_DB_PATH as PHOTO_INDEX_DB_PATH  # type: ignore
    from photo_index import scan_and_update as scan_photo_index  # type: ignore

try:  # pragma: no cover
    from app_web.config import config as app_config
    from app_web.data_dir_utils import resolve_data_dir
except ImportError:  # pragma: no cover
    from qrmes_shared_core.config import config as app_config  # type: ignore
    from qrmes_shared_core.data_dir_utils import resolve_data_dir  # type: ignore


def normalize_step_key(value: Any) -> str:
    if callable(globals().get("_normalize_step_key")):
        return str(_normalize_step_key(value))
    text = str(value or "").strip().lower()
    text = re.sub(r"[\s._-]+", "", text)
    return text


def normalize_serial_rule_value(value: Any) -> str:
    return re.sub(r"[-_\s]+", "", str(value or "").strip())


def strip_directory_suffix(value: str) -> str:
    text = str(value or "").strip()
    if "_" not in text:
        return text
    head, tail = text.rsplit("_", 1)
    if head and re.fullmatch(r"[A-Za-z0-9-]{4,}", tail or ""):
        return head.strip()
    return text


def build_motor_qc_project_code_candidates(data_manager: Any, project_name: str) -> List[str]:
    candidates: List[str] = []
    seen = set()

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        candidates.append(text)

    raw_name = str(project_name or "").strip()
    stripped_name = strip_directory_suffix(raw_name)
    add(raw_name)
    add(stripped_name)

    getter = getattr(data_manager, "get_project_config", None)
    if not callable(getter):
        return candidates

    config = None
    for candidate in list(candidates):
        try:
            config = getter(candidate)
        except Exception:
            config = None
        if isinstance(config, dict) and config:
            break

    if isinstance(config, dict):
        add(config.get("projectCode"))
        add(config.get("projectName"))

    return candidates


def get_default_quality_rule_severities() -> Dict[str, str]:
    getter = getattr(_project_config_manager, "get_default_quality_rule_severities", None)
    if callable(getter):
        return dict(getter() or {})
    return {
        "recordRequired": "block",
        "materialComplete": "block",
        "photoCoverage": "review",
        "qcPassRequired": "block",
        "hilReportRequired": "ignore",
        "bemfReportRequired": "ignore",
    }


def normalize_quality_workbench_config(config: Any, *, sanitize_invalid: bool = False) -> None:
    normalizer = getattr(_project_config_manager, "normalize_quality_workbench_config", None)
    if callable(normalizer):
        normalizer(config, sanitize_invalid=sanitize_invalid)
        return

    if not isinstance(config, dict):
        return
    defaults = get_default_quality_rule_severities()
    quality_config = config.get("qualityWorkbench")
    if not isinstance(quality_config, dict):
        quality_config = {}
        config["qualityWorkbench"] = quality_config
    quality_config["enabled"] = bool(quality_config.get("enabled", True))
    rules = quality_config.get("defaultRules")
    normalized_rules: Dict[str, str] = {}
    if isinstance(rules, dict):
        for key, default in defaults.items():
            value = str(rules.get(key, default) or default).strip().lower()
            normalized_rules[key] = value if value in {"block", "review", "ignore"} else default
    else:
        normalized_rules = dict(defaults)
    quality_config["defaultRules"] = normalized_rules


def normalize_product_type_quality_rules(
    product_type: Any,
    *,
    default_rules: Optional[Dict[str, str]] = None,
    sanitize_invalid: bool = False,
) -> None:
    normalizer = getattr(_project_config_manager, "normalize_product_type_quality_rules", None)
    if callable(normalizer):
        normalizer(product_type, default_rules=default_rules, sanitize_invalid=sanitize_invalid)
        return

    if not isinstance(product_type, dict):
        return
    defaults = dict(default_rules or get_default_quality_rule_severities())
    rules = product_type.get("qualityRules")
    normalized_rules: Dict[str, str] = {}
    if isinstance(rules, dict):
        for key, default in defaults.items():
            value = str(rules.get(key, default) or default).strip().lower()
            normalized_rules[key] = value if value in {"block", "review", "ignore"} else default
    else:
        normalized_rules = dict(defaults)
    product_type["qualityRules"] = normalized_rules


QUALITY_CONCLUSION_LABELS = {
    "pass": "可出货",
    "review": "待质量评审",
    "block": "不可出货",
}

SHIPMENT_PROCESS_PATTERNS = (
    "%出厂%",
    "%出货%",
    "%发运%",
)


class QualityWorkbenchError(Exception):
    """Base quality workbench error."""


class QualityWorkbenchRecordNotFoundError(QualityWorkbenchError):
    """Raised when the requested serial number has no product record."""


class QualityWorkbenchProcessNotFoundError(QualityWorkbenchError):
    """Raised when the requested process is not configured for the product."""


class QualityWorkbenchService:
    """Aggregate product quality evidence into a shipment-readiness conclusion."""

    def __init__(
        self,
        *,
        data_manager: Any,
        get_h2_db_manager: Callable[[], Any],
        init_h2_service: Optional[Callable[[], Any]] = None,
        qc_report_builder: Optional[Callable[..., Dict[str, Any]]] = None,
        qc_process_detail_builder: Optional[Callable[..., Dict[str, Any]]] = None,
        test_report_service: Optional[Any] = None,
    ):
        self.data_manager = data_manager
        self.get_h2_db_manager = get_h2_db_manager
        self.init_h2_service = init_h2_service
        self.qc_report_builder = qc_report_builder or self._default_qc_report_builder
        self.qc_process_detail_builder = qc_process_detail_builder
        self.test_report_service = test_report_service

    def get_quality_workbench(self, serial_number: str) -> Dict[str, Any]:
        serial = str(serial_number or "").strip()
        serial_rule_context = self._resolve_serial_rule_context(serial)
        resolved = self._resolve_serial_reference(serial, serial_rule_context=serial_rule_context)
        effective_serial = str(resolved.get("serial") or serial).strip()
        record = resolved.get("record")
        inferred_context = resolved.get("context") if not record else None
        raw_project_name = str(
            (serial_rule_context or {}).get("project_name")
            or (record or {}).get("project_name")
            or (inferred_context or {}).get("project_name")
            or ""
        ).strip()
        project_name = self._resolve_project_name(raw_project_name)

        config = (serial_rule_context or {}).get("config") if isinstance((serial_rule_context or {}).get("config"), dict) else self._get_project_config(project_name)
        raw_product_type = str(
            (serial_rule_context or {}).get("product_type")
            or (record or {}).get("product_type")
            or (inferred_context or {}).get("product_type")
            or ""
        ).strip()
        product_type = self._resolve_product_type_name(config, raw_product_type)
        workbench_config, default_rules = self._resolve_quality_workbench_config(config)
        product_type_config = self._resolve_product_type_config(config, product_type, default_rules)
        effective_rules = dict(product_type_config.get("qualityRules") or default_rules)
        if not workbench_config.get("enabled", True):
            effective_rules = {key: "ignore" for key in effective_rules.keys()}

        material_status = self._build_material_status(record, product_type_config)
        process_status = self._build_process_status(effective_serial, project_name, product_type, product_type_config)
        test_reports = self._build_test_report_status(effective_serial)
        checks = self._build_checks(
            record=record,
            rules=effective_rules,
            material_status=material_status,
            process_status=process_status,
            test_reports=test_reports,
        )
        quality_conclusion = self._build_quality_conclusion(checks)
        shipment_tracking = self._build_shipment_tracking(effective_serial)

        associations: Dict[str, Any] = {}
        if inferred_context:
            associations["contextSource"] = inferred_context.get("source") or "photoIndex"
        if serial_rule_context:
            associations["matchedSerialRulePrefix"] = serial_rule_context.get("prefix") or ""
            associations["matchedSerialRuleProject"] = serial_rule_context.get("project_name") or ""
            associations["matchedSerialRuleProductType"] = serial_rule_context.get("product_type") or ""
        if effective_serial and effective_serial != serial:
            associations["requestedSerial"] = serial
            associations["resolvedSerial"] = effective_serial
            associations["serialResolutionReason"] = resolved.get("reason") or "similarCandidate"
        similar_candidates = resolved.get("similar_candidates") or []
        if similar_candidates:
            associations["similarCandidates"] = similar_candidates

        return {
            "serialNumber": effective_serial or serial,
            "requestedSerialNumber": serial,
            "projectName": project_name,
            "productType": product_type,
            "qualityWorkbench": workbench_config,
            "qualityConclusion": quality_conclusion,
            "baseRecord": self._build_base_record(record),
            "materialStatus": material_status,
            "processStatus": process_status,
            "testReports": test_reports,
            "checks": checks,
            "associations": associations,
            "shipmentTracking": shipment_tracking,
        }

    def get_daily_shipment_stats(
        self,
        target_date: Optional[str] = None,
        *,
        trend_days: int = 7,
        limit: int = 80,
    ) -> Dict[str, Any]:
        selected_date = self._normalize_stats_date(target_date)
        today_date = datetime.now().strftime("%Y-%m-%d")
        trend_window = max(1, min(int(trend_days or 7), 31))
        row_limit = max(1, min(int(limit or 80), 300))
        db_path = Path(PHOTO_INDEX_DB_PATH)

        if not db_path.exists():
            return {
                "selectedDate": selected_date,
                "todayDate": today_date,
                "selectedDateCount": 0,
                "todayCount": 0,
                "recentShipments": [],
                "modelBreakdown": [],
                "trend": self._build_trend_points(selected_date, trend_window, {}),
                "matchedPatterns": [pattern.strip("%") for pattern in SHIPMENT_PROCESS_PATTERNS],
            }

        where_clause = self._shipment_where_clause()
        trend_start_date = (
            datetime.strptime(selected_date, "%Y-%m-%d") - timedelta(days=trend_window - 1)
        ).strftime("%Y-%m-%d")

        recent_shipments: List[Dict[str, Any]] = []
        model_breakdown: List[Dict[str, Any]] = []
        trend_counts: Dict[str, int] = {}
        selected_count = 0
        today_count = 0

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            shipment_rows = conn.execute(
                f"""
                WITH filtered AS (
                    SELECT
                        serial_number,
                        project_name,
                        product_name,
                        process_step,
                        mtime_sec
                    FROM photo_file_index
                    WHERE COALESCE(serial_number, '') != ''
                      AND ({where_clause})
                      AND strftime('%Y-%m-%d', mtime_sec, 'unixepoch', 'localtime') = ?
                ),
                latest AS (
                    SELECT
                        serial_number,
                        MAX(mtime_sec) AS latest_mtime,
                        COUNT(*) AS photo_count
                    FROM filtered
                    GROUP BY serial_number
                )
                SELECT
                    latest.serial_number,
                    MAX(filtered.project_name) AS project_name,
                    MAX(filtered.product_name) AS product_name,
                    MAX(filtered.process_step) AS process_step,
                    latest.latest_mtime,
                    latest.photo_count
                FROM latest
                JOIN filtered
                  ON filtered.serial_number = latest.serial_number
                 AND filtered.mtime_sec = latest.latest_mtime
                GROUP BY latest.serial_number, latest.latest_mtime, latest.photo_count
                ORDER BY latest.latest_mtime DESC
                LIMIT ?
                """,
                [*SHIPMENT_PROCESS_PATTERNS, selected_date, row_limit],
            ).fetchall()

            model_rows = conn.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(TRIM(project_name), ''), '') AS project_name,
                    COALESCE(NULLIF(TRIM(product_name), ''), '') AS product_name,
                    COUNT(DISTINCT serial_number) AS shipment_count
                FROM photo_file_index
                WHERE COALESCE(serial_number, '') != ''
                  AND ({where_clause})
                  AND strftime('%Y-%m-%d', mtime_sec, 'unixepoch', 'localtime') = ?
                GROUP BY
                    COALESCE(NULLIF(TRIM(project_name), ''), ''),
                    COALESCE(NULLIF(TRIM(product_name), ''), '')
                ORDER BY shipment_count DESC, project_name ASC, product_name ASC
                LIMIT 20
                """,
                [*SHIPMENT_PROCESS_PATTERNS, selected_date],
            ).fetchall()

            trend_rows = conn.execute(
                f"""
                SELECT
                    strftime('%Y-%m-%d', mtime_sec, 'unixepoch', 'localtime') AS work_date,
                    COUNT(DISTINCT serial_number) AS shipment_count
                FROM photo_file_index
                WHERE COALESCE(serial_number, '') != ''
                  AND ({where_clause})
                  AND strftime('%Y-%m-%d', mtime_sec, 'unixepoch', 'localtime') BETWEEN ? AND ?
                GROUP BY work_date
                ORDER BY work_date ASC
                """,
                [*SHIPMENT_PROCESS_PATTERNS, trend_start_date, selected_date],
            ).fetchall()

            selected_row = conn.execute(
                f"""
                SELECT COUNT(DISTINCT serial_number) AS shipment_count
                FROM photo_file_index
                WHERE COALESCE(serial_number, '') != ''
                  AND ({where_clause})
                  AND strftime('%Y-%m-%d', mtime_sec, 'unixepoch', 'localtime') = ?
                """,
                [*SHIPMENT_PROCESS_PATTERNS, selected_date],
            ).fetchone()
            today_row = conn.execute(
                f"""
                SELECT COUNT(DISTINCT serial_number) AS shipment_count
                FROM photo_file_index
                WHERE COALESCE(serial_number, '') != ''
                  AND ({where_clause})
                  AND strftime('%Y-%m-%d', mtime_sec, 'unixepoch', 'localtime') = ?
                """,
                [*SHIPMENT_PROCESS_PATTERNS, today_date],
            ).fetchone()
            conn.close()

            selected_count = int((selected_row["shipment_count"] if selected_row is not None else 0) or 0)
            today_count = int((today_row["shipment_count"] if today_row is not None else 0) or 0)
            trend_counts = {
                str(row["work_date"] or ""): int(row["shipment_count"] or 0)
                for row in trend_rows
                if str(row["work_date"] or "").strip()
            }
            recent_shipments = [
                {
                    "serialNumber": str(row["serial_number"] or "").strip(),
                    "projectName": str(row["project_name"] or "").strip(),
                    "productType": str(row["product_name"] or "").strip(),
                    "processStep": str(row["process_step"] or "").strip(),
                    "photoCount": int(row["photo_count"] or 0),
                    "latestPhotoTime": int(row["latest_mtime"] or 0),
                    "latestPhotoTimeFormatted": self._format_unix_local_time(row["latest_mtime"]),
                }
                for row in shipment_rows
                if str(row["serial_number"] or "").strip()
            ]
            model_breakdown = [
                {
                    "projectName": str(row["project_name"] or "").strip(),
                    "productType": str(row["product_name"] or "").strip(),
                    "count": int(row["shipment_count"] or 0),
                }
                for row in model_rows
                if int(row["shipment_count"] or 0) > 0
            ]
        except Exception:
            return {
                "selectedDate": selected_date,
                "todayDate": today_date,
                "selectedDateCount": 0,
                "todayCount": 0,
                "recentShipments": [],
                "modelBreakdown": [],
                "trend": self._build_trend_points(selected_date, trend_window, {}),
                "matchedPatterns": [pattern.strip("%") for pattern in SHIPMENT_PROCESS_PATTERNS],
            }

        return {
            "selectedDate": selected_date,
            "todayDate": today_date,
            "selectedDateCount": selected_count,
            "todayCount": today_count,
            "recentShipments": recent_shipments,
            "modelBreakdown": model_breakdown,
            "trend": self._build_trend_points(selected_date, trend_window, trend_counts),
            "matchedPatterns": [pattern.strip("%") for pattern in SHIPMENT_PROCESS_PATTERNS],
        }

    def get_process_detail(self, serial_number: str, process_name: str) -> Dict[str, Any]:
        serial = str(serial_number or "").strip()
        requested_process = str(process_name or "").strip()
        if not serial or not requested_process:
            raise QualityWorkbenchProcessNotFoundError(requested_process or serial)

        serial_rule_context = self._resolve_serial_rule_context(serial)
        resolved = self._resolve_serial_reference(serial, serial_rule_context=serial_rule_context)
        effective_serial = str(resolved.get("serial") or serial).strip()
        record = resolved.get("record")
        inferred_context = resolved.get("context") if not record else None
        if not record and not inferred_context and not serial_rule_context:
            raise QualityWorkbenchRecordNotFoundError(serial)

        raw_project_name = str(
            (serial_rule_context or {}).get("project_name")
            or (record or {}).get("project_name")
            or (inferred_context or {}).get("project_name")
            or ""
        ).strip()
        project_name = self._resolve_project_name(raw_project_name)
        config = (serial_rule_context or {}).get("config") if isinstance((serial_rule_context or {}).get("config"), dict) else self._get_project_config(project_name)
        raw_product_type = str(
            (serial_rule_context or {}).get("product_type")
            or (record or {}).get("product_type")
            or (inferred_context or {}).get("product_type")
            or ""
        ).strip()
        product_type = self._resolve_product_type_name(config, raw_product_type)
        _, default_rules = self._resolve_quality_workbench_config(config)
        product_type_config = self._resolve_product_type_config(config, product_type, default_rules)
        steps = self._sort_steps(product_type_config.get("processSteps") or [])
        matched_step = self._find_step(steps, requested_process)
        payload = self.qc_report_builder(
            product_serial=effective_serial,
            project_name=project_name,
            product_type=product_type,
            steps=steps,
        ) or {}
        results = payload.get("results") or []
        result_row = self._find_process_result(results, requested_process)
        if matched_step is None and isinstance(result_row, dict):
            matched_step = {
                "name": str(result_row.get("process") or requested_process).strip(),
                "order": int(result_row.get("order") or 0),
                "photoRequired": bool(result_row.get("photo_required", True)),
            }
        if matched_step is None:
            raise QualityWorkbenchProcessNotFoundError(requested_process)
        extra_detail = {}
        if callable(self.qc_process_detail_builder):
            extra_detail = self.qc_process_detail_builder(
                product_serial=effective_serial,
                project_name=project_name,
                product_type=product_type,
                process_name=requested_process,
                steps=steps,
                summary_row=result_row,
            ) or {}
        detail = self._build_process_detail_from_result(
            requested_process=requested_process,
            step=matched_step,
            result_row=result_row,
            extra_detail=extra_detail if isinstance(extra_detail, dict) else None,
        )

        return {
            "serialNumber": effective_serial or serial,
            "requestedSerialNumber": serial,
            "projectName": project_name,
            "productType": product_type,
            "processDetail": detail,
        }

    def _resolve_serial_reference(self, serial_number: str, serial_rule_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        serial = str(serial_number or "").strip()
        if not serial:
            return {
                "serial": "",
                "record": None,
                "context": None,
                "reason": "empty",
                "similar_candidates": [],
            }

        record = self._get_record(serial)
        if record:
            return {
                "serial": serial,
                "record": record,
                "context": None,
                "reason": "exactRecord",
                "similar_candidates": [],
            }

        context = self._infer_record_context(serial)
        if context:
            return {
                "serial": serial,
                "record": None,
                "context": context,
                "reason": "exactPhotoContext",
                "similar_candidates": [],
            }

        if serial_rule_context:
            prefixed_candidates = self._find_prefixed_serial_candidates(
                prefix=str(serial_rule_context.get("prefix") or "").strip(),
                project_name=str(serial_rule_context.get("project_name") or "").strip(),
                product_type=str(serial_rule_context.get("product_type") or "").strip(),
            )
            return self._resolve_candidate_reference(
                requested_serial=serial,
                candidates=prefixed_candidates,
                default_reason="serialRulePrefixCandidate",
                fallback_context={
                    "project_name": str(serial_rule_context.get("project_name") or "").strip(),
                    "product_type": str(serial_rule_context.get("product_type") or "").strip(),
                    "source": "serialRule",
                },
                fallback_reason="serialRuleOnly",
            )

        similar_candidates = self._find_similar_serial_candidates(serial)
        return self._resolve_candidate_reference(
            requested_serial=serial,
            candidates=similar_candidates,
            default_reason="similarCandidate",
            fallback_reason="notFound",
        )

    def _resolve_candidate_reference(
        self,
        *,
        requested_serial: str,
        candidates: List[Dict[str, Any]],
        default_reason: str,
        fallback_context: Optional[Dict[str, Any]] = None,
        fallback_reason: str = "notFound",
    ) -> Dict[str, Any]:
        serial = str(requested_serial or "").strip()
        for candidate in candidates:
            candidate_serial = str(candidate.get("serialNumber") or "").strip()
            if not candidate_serial:
                continue
            candidate_record = self._get_record(candidate_serial)
            candidate_context = self._infer_record_context(candidate_serial) if not candidate_record else None
            if candidate_record or candidate_context:
                return {
                    "serial": candidate_serial,
                    "record": candidate_record,
                    "context": candidate_context,
                    "reason": candidate.get("matchReason") or default_reason,
                    "similar_candidates": candidates,
                }

        return {
            "serial": serial,
            "record": None,
            "context": fallback_context,
            "reason": fallback_reason,
            "similar_candidates": candidates,
        }

    def _resolve_serial_rule_context(self, serial_number: str) -> Optional[Dict[str, Any]]:
        serial = str(serial_number or "").strip()
        if not serial or self.data_manager is None:
            return None

        get_projects = getattr(self.data_manager, "get_projects", None)
        projects = get_projects() if callable(get_projects) else []
        best_match: Optional[Dict[str, Any]] = None

        for project_name in projects or []:
            config = self._get_project_config(str(project_name or "").strip())
            if not isinstance(config, dict):
                continue
            for product_type in (config.get("productTypes") or []):
                if not isinstance(product_type, dict):
                    continue
                type_name = str(product_type.get("typeName") or "").strip()
                if not type_name:
                    continue
                raw_rules = product_type.get(
                    "serialRules",
                    product_type.get("serial_rules", product_type.get("serialPrefixes", product_type.get("serial_prefixes"))),
                )
                rules = raw_rules if isinstance(raw_rules, list) else []
                normalized_serial = normalize_serial_rule_value(serial)
                for raw_prefix in rules:
                    prefix = str(raw_prefix or "").strip()
                    normalized_prefix = normalize_serial_rule_value(prefix)
                    if not normalized_prefix:
                        continue
                    if not normalized_serial.lower().startswith(normalized_prefix.lower()):
                        continue
                    match = {
                        "project_name": str(config.get("projectName") or project_name).strip() or str(project_name or "").strip(),
                        "product_type": type_name,
                        "prefix": prefix,
                        "length": len(normalized_prefix),
                        "config": config,
                    }
                    if best_match is None or int(match["length"]) > int(best_match.get("length") or 0):
                        best_match = match
        return best_match

    def _find_prefixed_serial_candidates(
        self,
        *,
        prefix: str,
        project_name: str = "",
        product_type: str = "",
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        serial_prefix = str(prefix or "").strip()
        normalized_prefix = normalize_serial_rule_value(serial_prefix)
        if not normalized_prefix:
            return []

        expected_project = self._name_key(project_name)
        expected_product = self._name_key(product_type)
        candidates: Dict[str, Dict[str, Any]] = {}

        def merge_candidate(serial_value: str, payload: Dict[str, Any]) -> None:
            key = str(serial_value or "").strip()
            if not key:
                return
            existing = candidates.get(key)
            candidates[key] = self._merge_serial_candidate(
                existing,
                payload,
                strategy="latest_time",
            )

        record_db_path = self._product_record_db_path()
        for payload in self._query_serial_candidates(
            db_path=record_db_path,
            query="""
                SELECT product_serial, project_name, product_type, MAX(scan_time) AS latest_time
                FROM product_records
                WHERE product_serial LIKE ?
                GROUP BY product_serial, project_name, product_type
                ORDER BY latest_time DESC
                LIMIT ?
            """,
            params=(f"{normalized_prefix}%", max(limit, 5)),
            source="productRecord",
            serial_key="product_serial",
            project_key="project_name",
            product_key="product_type",
            latest_time_key="latest_time",
            expected_project=expected_project,
            expected_product=expected_product,
            project_resolver=lambda value: value,
            match_reason="serialRulePrefix",
        ):
            merge_candidate(str(payload.get("serialNumber") or ""), payload)

        photo_index_db = Path(PHOTO_INDEX_DB_PATH)
        for payload in self._query_serial_candidates(
            db_path=photo_index_db,
            query="""
                SELECT serial_number, MAX(project_name) AS project_name, MAX(product_name) AS product_name, MAX(mtime_sec) AS latest_time
                FROM photo_file_index
                WHERE serial_number LIKE ?
                GROUP BY serial_number
                ORDER BY latest_time DESC
                LIMIT ?
            """,
            params=(f"{normalized_prefix}%", max(limit, 5)),
            source="photoIndex",
            serial_key="serial_number",
            project_key="project_name",
            product_key="product_name",
            latest_time_key="latest_time",
            expected_project=expected_project,
            expected_product=expected_product,
            project_resolver=self._resolve_project_name,
            match_reason="serialRulePrefix",
        ):
            merge_candidate(str(payload.get("serialNumber") or ""), payload)

        return self._sort_serial_candidates(candidates, strategy="latest_time", limit=limit)

    def _get_record(self, serial_number: str) -> Optional[Dict[str, Any]]:
        if not serial_number:
            return None
        manager = self.get_h2_db_manager() if self.get_h2_db_manager else None
        if manager is None and self.init_h2_service:
            self.init_h2_service()
            manager = self.get_h2_db_manager() if self.get_h2_db_manager else None
        if manager is None:
            return None
        return manager.get_record(serial_number)

    def _infer_record_context(self, serial_number: str) -> Optional[Dict[str, Any]]:
        if not serial_number:
            return None

        context = self._lookup_context_from_photo_index(serial_number)
        if context:
            return context

        self._refresh_photo_index_for_serial(serial_number)
        return self._lookup_context_from_photo_index(serial_number)

    def _find_similar_serial_candidates(self, serial_number: str, limit: int = 8) -> List[Dict[str, Any]]:
        serial = str(serial_number or "").strip()
        if not serial:
            return []

        patterns = self._build_serial_search_patterns(serial)
        candidates: Dict[str, Dict[str, Any]] = {}

        def merge_candidate(serial_value: str, payload: Dict[str, Any]) -> None:
            key = str(serial_value or "").strip()
            if not key:
                return
            existing = candidates.get(key)
            candidates[key] = self._merge_serial_candidate(
                existing,
                payload,
                strategy="match_weight_then_latest_time",
            )

        record_db_path = self._product_record_db_path()
        for index, (pattern, reason) in enumerate(patterns):
            for payload in self._query_serial_candidates(
                db_path=record_db_path,
                query="""
                    SELECT
                        product_serial,
                        project_name,
                        product_type,
                        MAX(scan_time) AS latest_time
                    FROM product_records
                    WHERE product_serial LIKE ?
                    GROUP BY product_serial, project_name, product_type
                    ORDER BY latest_time DESC
                    LIMIT ?
                """,
                params=(pattern, max(limit, 5)),
                source="productRecord",
                serial_key="product_serial",
                project_key="project_name",
                product_key="product_type",
                latest_time_key="latest_time",
                match_reason=reason,
                match_weight=100 - index,
            ):
                merge_candidate(str(payload.get("serialNumber") or ""), payload)

        photo_index_db = Path(PHOTO_INDEX_DB_PATH)
        for index, (pattern, reason) in enumerate(patterns):
            for payload in self._query_serial_candidates(
                db_path=photo_index_db,
                query="""
                    SELECT
                        serial_number,
                        MAX(project_name) AS project_name,
                        MAX(product_name) AS product_name,
                        MAX(mtime_sec) AS latest_time
                    FROM photo_file_index
                    WHERE serial_number LIKE ?
                    GROUP BY serial_number
                    ORDER BY latest_time DESC
                    LIMIT ?
                """,
                params=(pattern, max(limit, 5)),
                source="photoIndex",
                serial_key="serial_number",
                project_key="project_name",
                product_key="product_name",
                latest_time_key="latest_time",
                match_reason=reason,
                match_weight=80 - index,
            ):
                merge_candidate(str(payload.get("serialNumber") or ""), payload)

        return self._sort_serial_candidates(candidates, strategy="match_weight_then_latest_time", limit=limit)

    @staticmethod
    def _merge_serial_candidate(
        existing: Optional[Dict[str, Any]],
        incoming: Optional[Dict[str, Any]],
        *,
        strategy: str,
    ) -> Dict[str, Any]:
        payload = dict(incoming or {})
        if not payload:
            return dict(existing or {})
        if not existing:
            return payload

        current = dict(existing)
        current_latest = int(current.get("latestTime") or 0)
        incoming_latest = int(payload.get("latestTime") or 0)

        if strategy == "latest_time":
            return payload if incoming_latest > current_latest else current

        if strategy == "match_weight_then_latest_time":
            current_weight = int(current.get("matchWeight") or 0)
            incoming_weight = int(payload.get("matchWeight") or 0)
            if incoming_weight > current_weight:
                return payload
            if incoming_weight < current_weight:
                return current
            if incoming_latest > current_latest:
                merged = dict(current)
                merged.update(payload)
                return merged
            return current

        raise ValueError(f"unsupported merge strategy: {strategy}")

    @staticmethod
    def _sort_serial_candidates(
        candidates: Dict[str, Dict[str, Any]] | List[Dict[str, Any]],
        *,
        strategy: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        values = list(candidates.values()) if isinstance(candidates, dict) else list(candidates or [])

        if strategy == "latest_time":
            ordered = sorted(values, key=lambda item: int((item or {}).get("latestTime") or 0), reverse=True)
            return ordered[:limit]

        if strategy == "match_weight_then_latest_time":
            ordered = sorted(
                values,
                key=lambda item: (
                    int((item or {}).get("matchWeight") or 0),
                    int((item or {}).get("latestTime") or 0),
                ),
                reverse=True,
            )
            return ordered[:limit]

        raise ValueError(f"unsupported sort strategy: {strategy}")

    def _build_serial_search_patterns(self, serial_number: str) -> List[tuple[str, str]]:
        serial = str(serial_number or "").strip()
        parts = [part for part in serial.split("-") if part]
        patterns: List[tuple[str, str]] = []
        seen = set()

        def add(prefix: str, reason: str) -> None:
            normalized = str(prefix or "").strip()
            if not normalized:
                return
            pattern = normalized if normalized.endswith("%") else f"{normalized}%"
            if pattern in seen:
                return
            seen.add(pattern)
            patterns.append((pattern, reason))

        add(serial, "serialPrefix")
        if len(parts) >= 5:
            add("-".join(parts[:5]) + "-", "variantFamily")
        if len(parts) >= 4:
            add("-".join(parts[:4]) + "-", "modelFamily")
        if len(parts) >= 3:
            add("-".join(parts[:3]) + "-", "seriesFamily")
        return patterns

    def _product_record_db_path(self) -> Path:
        data_root = resolve_data_dir(
            nas_local_base_path=getattr(app_config, "nas_local_base_path", None),
            repo_root=Path(__file__).resolve().parent.parent,
        )
        return data_root / "record" / "product_records.db"

    @staticmethod
    def _query_sqlite(db_path: Path, query: str, params: tuple[Any, ...] | list[Any], *, fetch: str = "all") -> Any:
        with closing(sqlite3.connect(str(db_path))) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            if fetch == "one":
                return cursor.fetchone()
            return cursor.fetchall()

    def _query_serial_candidates(
        self,
        *,
        db_path: Path,
        query: str,
        params: tuple[Any, ...] | list[Any],
        source: str,
        serial_key: str,
        project_key: str,
        product_key: str,
        latest_time_key: str,
        expected_project: str = "",
        expected_product: str = "",
        project_resolver: Optional[Callable[[str], str]] = None,
        match_reason: str,
        match_weight: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not db_path.exists():
            return []

        resolver = project_resolver or (lambda value: value)

        try:
            rows = self._query_sqlite(db_path, query, params, fetch="all")
        except Exception:
            return []

        candidates: List[Dict[str, Any]] = []
        for row in rows:
            row_project = str(row[project_key] or "").strip()
            row_product = str(row[product_key] or "").strip()
            if expected_project and self._name_key(resolver(row_project)) != expected_project:
                continue
            if expected_product and self._name_key(row_product) != expected_product:
                continue

            candidate_serial = str(row[serial_key] or "").strip()
            if not candidate_serial:
                continue

            payload = {
                "serialNumber": candidate_serial,
                "projectName": row_project,
                "productType": row_product,
                "latestTime": int(row[latest_time_key] or 0),
                "latestTimeFormatted": self._format_unix_local_time(row[latest_time_key]),
                "source": source,
                "matchReason": match_reason,
            }
            if match_weight is not None:
                payload["matchWeight"] = match_weight
            candidates.append(payload)
        return candidates

    def _lookup_context_from_photo_index(self, serial_number: str) -> Optional[Dict[str, Any]]:
        db_path = Path(PHOTO_INDEX_DB_PATH)
        if not db_path.exists():
            return None

        try:
            row = self._query_sqlite(
                db_path,
                """
                SELECT
                  project_name,
                  product_name,
                  COUNT(*) AS photo_count,
                  MAX(mtime_sec) AS latest_mtime
                FROM photo_file_index
                WHERE serial_number = ?
                  AND COALESCE(project_name, '') != ''
                  AND COALESCE(product_name, '') != ''
                GROUP BY project_name, product_name
                ORDER BY photo_count DESC, latest_mtime DESC
                LIMIT 1
                """,
                (serial_number,),
                fetch="one",
            )
        except Exception:
            return None

        if row is None:
            return None

        project_name = str(row["project_name"] or "").strip()
        product_type = str(row["product_name"] or "").strip()
        if not project_name or not product_type:
            return None

        return {
            "project_name": project_name,
            "product_type": product_type,
            "source": "photoIndex",
            "photo_count": int(row["photo_count"] or 0),
        }

    def _refresh_photo_index_for_serial(self, serial_number: str) -> None:
        search_pattern = f"*/*/{serial_number}"
        for base_path in self._candidate_picture_roots():
            try:
                scan_photo_index(
                    base_path=base_path,
                    search_pattern=search_pattern,
                    days=None,
                    limit_hint=None,
                    db_path=Path(PHOTO_INDEX_DB_PATH),
                )
            except Exception:
                continue

    def _candidate_picture_roots(self) -> List[Path]:
        candidates: List[Path] = []
        data_root = resolve_data_dir(
            nas_local_base_path=getattr(app_config, "nas_local_base_path", None),
            repo_root=Path(__file__).resolve().parent.parent,
        )
        for raw in (
            data_root / "picture",
            Path(__file__).parent / "picture",
            Path("/volume2/MES/test/app_web/picture"),
        ):
            resolved = raw.resolve() if raw.exists() else raw
            if raw.exists() and resolved not in candidates:
                candidates.append(resolved)
        return candidates

    def _build_shipment_tracking(self, serial_number: str) -> Dict[str, Any]:
        serial = str(serial_number or "").strip()
        if not serial:
            return {
                "hasShipmentPhoto": False,
                "photoCount": 0,
                "latestProcessStep": "",
                "latestPhotoTime": None,
                "latestPhotoTimeFormatted": "",
                "countedDate": "",
            }

        db_path = Path(PHOTO_INDEX_DB_PATH)
        if not db_path.exists():
            return {
                "hasShipmentPhoto": False,
                "photoCount": 0,
                "latestProcessStep": "",
                "latestPhotoTime": None,
                "latestPhotoTimeFormatted": "",
                "countedDate": "",
            }

        row = None
        try:
            row = self._query_sqlite(
                db_path,
                f"""
                SELECT
                    MAX(mtime_sec) AS latest_mtime,
                    COUNT(*) AS photo_count,
                    MAX(process_step) AS process_step
                FROM photo_file_index
                WHERE serial_number = ?
                  AND ({self._shipment_where_clause()})
                """,
                [serial, *SHIPMENT_PROCESS_PATTERNS],
                fetch="one",
            )
        except Exception:
            row = None

        latest_mtime = int((row["latest_mtime"] if row is not None else 0) or 0)
        photo_count = int((row["photo_count"] if row is not None else 0) or 0)
        return {
            "hasShipmentPhoto": photo_count > 0,
            "photoCount": photo_count,
            "latestProcessStep": str((row["process_step"] if row is not None else "") or "").strip(),
            "latestPhotoTime": latest_mtime if latest_mtime > 0 else None,
            "latestPhotoTimeFormatted": self._format_unix_local_time(latest_mtime),
            "countedDate": self._format_unix_local_date(latest_mtime),
        }

    def _get_project_config(self, project_name: str) -> Optional[Dict[str, Any]]:
        if not project_name or self.data_manager is None:
            return None
        getter = getattr(self.data_manager, "get_project_config", None)
        if not callable(getter):
            return None

        config = getter(project_name)
        if config:
            return config

        stripped = self._strip_directory_suffix(project_name)
        if stripped and stripped != project_name:
            config = getter(stripped)
            if config:
                return config
        return None

    def _resolve_project_name(self, project_name: str) -> str:
        text = str(project_name or "").strip()
        if not text:
            return ""

        getter = getattr(self.data_manager, "get_projects", None)
        candidates = getter() if callable(getter) else []
        if candidates and callable(resolve_project_config_stem):
            resolved = resolve_project_config_stem(text, candidates or [])
            if resolved:
                return str(resolved).strip()
        return self._strip_directory_suffix(text)

    def _resolve_product_type_name(self, config: Optional[Dict[str, Any]], product_type: str) -> str:
        text = str(product_type or "").strip()
        if not text:
            return ""
        if not isinstance(config, dict):
            return self._strip_directory_suffix(text)

        product_types = [
            str(item.get("typeName") or "").strip()
            for item in (config.get("productTypes") or [])
            if isinstance(item, dict) and str(item.get("typeName") or "").strip()
        ]
        if text in product_types:
            return text

        stripped = self._strip_directory_suffix(text)
        if stripped in product_types:
            return stripped

        target_key = self._name_key(text)
        for candidate in product_types:
            if self._name_key(candidate) == target_key:
                return candidate

        stripped_key = self._name_key(stripped)
        for candidate in product_types:
            if self._name_key(candidate) == stripped_key:
                return candidate

        return stripped

    def _strip_directory_suffix(self, value: str) -> str:
        return strip_directory_suffix(value)

    def _name_key(self, value: str) -> str:
        return re.sub(r"[\s_-]+", "", str(value or "").strip()).casefold()

    def _resolve_quality_workbench_config(self, config: Optional[Dict[str, Any]]) -> tuple[Dict[str, Any], Dict[str, str]]:
        defaults = get_default_quality_rule_severities()
        if not isinstance(config, dict):
            return {"enabled": True, "defaultRules": defaults}, defaults

        runtime_config = dict(config)
        normalize_quality_workbench_config(runtime_config, sanitize_invalid=True)
        quality_config = runtime_config.get("qualityWorkbench") or {}
        default_rules = dict(quality_config.get("defaultRules") or defaults)
        return quality_config, default_rules

    @staticmethod
    def _step_order_value(step: Dict[str, Any]) -> int:
        try:
            value = int((step or {}).get("order") or 0)
        except (TypeError, ValueError):
            value = 0
        return value if value > 0 else 10 ** 9

    @classmethod
    def _sort_steps(cls, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = [dict(step) for step in (steps or []) if isinstance(step, dict)]
        return sorted(
            normalized,
            key=lambda step: (cls._step_order_value(step), str(step.get("name") or "").strip()),
        )

    def _resolve_product_type_config(
        self,
        config: Optional[Dict[str, Any]],
        product_type: str,
        default_rules: Dict[str, str],
    ) -> Dict[str, Any]:
        if not isinstance(config, dict):
            return {"typeName": product_type, "materials": [], "processSteps": [], "qualityRules": dict(default_rules)}

        product_types = config.get("productTypes") or []
        selected: Optional[Dict[str, Any]] = None
        for item in product_types:
            if isinstance(item, dict) and str(item.get("typeName") or "").strip() == product_type:
                selected = dict(item)
                break
        if not selected:
            selected = {"typeName": product_type, "materials": [], "processSteps": []}

        normalize_product_type_quality_rules(selected, default_rules=default_rules, sanitize_invalid=True)
        selected["processSteps"] = self._sort_steps(selected.get("processSteps") or [])
        return selected

    def _build_base_record(self, record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not record:
            return {
                "exists": False,
                "latestScanTime": None,
                "latestScanTimeFormatted": "",
                "operator": "",
                "status": "missing",
            }

        return {
            "exists": True,
            "latestScanTime": record.get("scan_time"),
            "latestScanTimeFormatted": record.get("scan_time_formatted") or "",
            "operator": record.get("operator") or "",
            "status": "present",
        }

    def _build_material_status(
        self,
        record: Optional[Dict[str, Any]],
        product_type_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        required_materials: List[str] = []
        for item in product_type_config.get("materials") or []:
            if not isinstance(item, dict):
                continue
            if item.get("required", True) is False:
                continue
            name = str(item.get("name") or item.get("materialName") or "").strip()
            if name:
                required_materials.append(name)

        status = compute_material_status(
            required_materials,
            (record or {}).get("materials"),
            (record or {}).get("raw_data"),
        )
        return {
            "requiredTotal": status["required_total"],
            "recordedCount": status["recorded_count"],
            "missingCount": status["missing_count"],
            "missingMaterials": status["missing_materials"],
            "complete": status["complete"],
            "hasRequirements": status["has_requirements"],
        }

    def _build_process_status(
        self,
        serial_number: str,
        project_name: str,
        product_type: str,
        product_type_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        steps = self._sort_steps(product_type_config.get("processSteps") or [])
        required_photo_processes = [
            str(step.get("name") or "").strip()
            for step in steps
            if str(step.get("name") or "").strip() and bool(step.get("photoRequired", True))
        ]

        payload = self.qc_report_builder(
            product_serial=serial_number,
            project_name=project_name,
            product_type=product_type,
            steps=steps,
        ) or {}
        results = payload.get("results") or []
        missing_photo_processes = [str(item).strip() for item in (payload.get("missing_processes") or []) if str(item).strip()]
        non_pass_processes = []
        for result in results:
            if not isinstance(result, dict):
                continue
            result.setdefault("detailAvailable", bool(str(result.get("process") or "").strip()))
            status = str(result.get("status") or "").strip().lower()
            if status in {"fail", "ng"}:
                non_pass_processes.append(
                    {
                        "process": result.get("process") or "",
                        "status": status,
                        "summary": result.get("summary") or result.get("effective_summary") or "",
                    }
                )

        sorted_results = sorted(
            [result for result in results if isinstance(result, dict)],
            key=lambda result: (
                self._step_order_value({"order": result.get("order")}),
                str(result.get("process") or "").strip(),
            ),
        )

        return {
            "totalProcesses": int(payload.get("total_processes") or len(steps)),
            "requiredPhotoProcesses": len(required_photo_processes),
            "requiredPhotoProcessNames": required_photo_processes,
            "missingPhotoProcesses": missing_photo_processes,
            "missingPhotoCount": len(missing_photo_processes),
            "overallStatus": payload.get("overall_status") or "pass",
            "inspectedProcesses": int(payload.get("inspected_processes") or 0),
            "nonPassProcesses": non_pass_processes,
            "results": sorted_results,
        }

    def _find_step(self, steps: List[Dict[str, Any]], requested_process: str) -> Optional[Dict[str, Any]]:
        requested_key = normalize_step_key(requested_process)
        for step in steps:
            step_name = str(step.get("name") or "").strip()
            if step_name and normalize_step_key(step_name) == requested_key:
                return step
        return None

    def _find_process_result(self, results: List[Dict[str, Any]], requested_process: str) -> Optional[Dict[str, Any]]:
        requested_key = normalize_step_key(requested_process)
        for item in results:
            if not isinstance(item, dict):
                continue
            process_name = str(item.get("process") or "").strip()
            if process_name and normalize_step_key(process_name) == requested_key:
                return item
        return None

    def _build_process_detail_from_result(
        self,
        *,
        requested_process: str,
        step: Dict[str, Any],
        result_row: Optional[Dict[str, Any]],
        extra_detail: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        row = result_row or {}
        defects = row.get("defects") or []
        extra = extra_detail or {}
        photo_count = int(
            extra.get("photoCount")
            or row.get("photo_count")
            or row.get("photoCount")
            or 0
        )
        has_photo = bool(extra.get("hasPhoto")) or bool(row.get("has_photo")) or photo_count > 0
        status = str(row.get("status") or row.get("effective_status") or "").strip().lower() or "pending"

        return {
            "process": str(row.get("process") or step.get("name") or requested_process).strip(),
            "order": int(row.get("order") or step.get("order") or 0),
            "photoRequired": bool(row.get("photo_required", step.get("photoRequired", True))),
            "hasPhoto": has_photo,
            "photoCount": photo_count,
            "status": status,
            "aiStatus": row.get("ai_status") or row.get("aiStatus"),
            "aiSummary": row.get("ai_summary") or row.get("aiSummary") or "",
            "humanStatus": row.get("human_status") or row.get("humanStatus"),
            "humanSummary": row.get("human_summary") or row.get("humanSummary") or "",
            "effectiveSummary": row.get("effective_summary") or row.get("summary") or row.get("effectiveSummary") or "",
            "defectCount": int(row.get("defect_count") or row.get("defectCount") or len(defects)),
            "defects": defects,
            "photos": list(extra.get("photos") or row.get("photos") or []),
            "latestInspectionTime": (
                row.get("latest_inspection_time_formatted")
                or row.get("latestInspectionTime")
                or row.get("latest_inspection_time")
                or ""
            ),
        }

    def _build_test_report_status(self, serial_number: str) -> Dict[str, Dict[str, Any]]:
        summary: Dict[str, Dict[str, Any]] = {
            "HIL": {"present": False, "count": 0, "latest": None},
            "BEMF": {"present": False, "count": 0, "latest": None},
        }
        if not self.test_report_service or not hasattr(self.test_report_service, "get_latest_reports_by_serial"):
            return summary

        raw_summary = self.test_report_service.get_latest_reports_by_serial(serial_number) or {}
        for report_type, value in raw_summary.items():
            key = str(report_type or "").strip().upper()
            if not key:
                continue
            entry = value if isinstance(value, dict) else {}
            summary[key] = {
                "present": bool(entry.get("present")),
                "count": int(entry.get("count") or 0),
                "latest": entry.get("latest"),
            }
        return summary

    def _build_checks(
        self,
        *,
        record: Optional[Dict[str, Any]],
        rules: Dict[str, str],
        material_status: Dict[str, Any],
        process_status: Dict[str, Any],
        test_reports: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        def add_check(key: str, passed: bool, summary: str, details: Optional[List[str]] = None) -> Dict[str, Any]:
            return {
                "key": key,
                "severity": rules.get(key, "ignore"),
                "passed": passed,
                "summary": summary,
                "details": details or [],
            }

        checks = [
            add_check(
                "recordRequired",
                bool(record),
                "产品记录存在" if record else "未找到产品记录",
            ),
            add_check(
                "materialComplete",
                (not material_status.get("hasRequirements")) or bool(material_status.get("complete")),
                "物料记录完整"
                if (not material_status.get("hasRequirements")) or material_status.get("complete")
                else f"缺少 {material_status.get('missingCount', 0)} 个必需物料",
                material_status.get("missingMaterials") or [],
            ),
            add_check(
                "photoCoverage",
                len(process_status.get("missingPhotoProcesses") or []) == 0,
                "必需工序照片完整"
                if len(process_status.get("missingPhotoProcesses") or []) == 0
                else f"缺少 {len(process_status.get('missingPhotoProcesses') or [])} 个必需工序照片",
                process_status.get("missingPhotoProcesses") or [],
            ),
            add_check(
                "qcPassRequired",
                len(process_status.get("nonPassProcesses") or []) == 0,
                "QC 检查通过"
                if len(process_status.get("nonPassProcesses") or []) == 0
                else f"存在 {len(process_status.get('nonPassProcesses') or [])} 个工序 QC 非 pass",
                [item.get("process") or "" for item in (process_status.get("nonPassProcesses") or []) if item.get("process")],
            ),
            add_check(
                "hilReportRequired",
                bool((test_reports.get("HIL") or {}).get("present")),
                "已关联 HIL 测试报告" if (test_reports.get("HIL") or {}).get("present") else "未关联 HIL 测试报告",
            ),
            add_check(
                "bemfReportRequired",
                bool((test_reports.get("BEMF") or {}).get("present")),
                "已关联反电势测试报告" if (test_reports.get("BEMF") or {}).get("present") else "未关联反电势测试报告",
            ),
        ]
        return checks

    def _build_quality_conclusion(self, checks: List[Dict[str, Any]]) -> Dict[str, Any]:
        blocking = [check for check in checks if check.get("severity") == "block" and check.get("passed") is False]
        review = [check for check in checks if check.get("severity") == "review" and check.get("passed") is False]

        if blocking:
            level = "block"
            triggered = blocking + review
        elif review:
            level = "review"
            triggered = review
        else:
            level = "pass"
            triggered = []

        summary = "所有已启用质量规则均通过"
        if triggered:
            summary = "；".join(str(item.get("summary") or "").strip() for item in triggered if str(item.get("summary") or "").strip())

        return {
            "level": level,
            "label": QUALITY_CONCLUSION_LABELS[level],
            "shipmentReady": level == "pass",
            "summary": summary,
            "triggeredRules": [
                {
                    "key": item.get("key"),
                    "severity": item.get("severity"),
                    "summary": item.get("summary"),
                    "details": item.get("details") or [],
                }
                for item in triggered
            ],
        }

    def _shipment_where_clause(self) -> str:
        return " OR ".join(["process_step LIKE ?"] * len(SHIPMENT_PROCESS_PATTERNS))

    def _normalize_stats_date(self, value: Optional[str]) -> str:
        text = str(value or "").strip()
        if text:
            try:
                return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d")
            except Exception:
                pass
        return datetime.now().strftime("%Y-%m-%d")

    def _build_trend_points(self, selected_date: str, trend_days: int, counts: Dict[str, int]) -> List[Dict[str, Any]]:
        anchor = datetime.strptime(selected_date, "%Y-%m-%d")
        points: List[Dict[str, Any]] = []
        for offset in range(trend_days - 1, -1, -1):
            current_date = (anchor - timedelta(days=offset)).strftime("%Y-%m-%d")
            points.append({"date": current_date, "count": int(counts.get(current_date, 0))})
        return points

    def _format_unix_local_time(self, value: Any) -> str:
        try:
            timestamp = int(value or 0)
        except Exception:
            timestamp = 0
        if timestamp <= 0:
            return ""
        if timestamp > 10_000_000_000:
            timestamp = int(timestamp / 1000)
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

    def _format_unix_local_date(self, value: Any) -> str:
        try:
            timestamp = int(value or 0)
        except Exception:
            timestamp = 0
        if timestamp <= 0:
            return ""
        if timestamp > 10_000_000_000:
            timestamp = int(timestamp / 1000)
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")

    @staticmethod
    def _default_qc_report_builder(**_: Any) -> Dict[str, Any]:
        return {
            "overall_status": "pass",
            "total_processes": 0,
            "inspected_processes": 0,
            "missing_processes": [],
            "results": [],
        }
