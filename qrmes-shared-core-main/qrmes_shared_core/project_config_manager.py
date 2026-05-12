"""
项目配置管理模块
管理物料属性和工序属性配置
支持版本管理和配置文件结构化存储
"""

import json
import logging
import shutil
import copy
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid
import re
from project_name_utils import normalize_project_name, project_name_key

logger = logging.getLogger(__name__)

ALLOWED_QR_RULE_TYPES = {"motor", "pcb"}
ALLOWED_PROJECT_STATUSES = {"active", "inactive"}

PROJECT_DB_REQUIRED_COLUMNS = {
    "projects": {
        "qc_policy_json": "TEXT",
        "quality_workbench_json": "TEXT",
        "default_rules_json": "TEXT",
        "project_status": "TEXT NOT NULL DEFAULT 'active'",
        "is_archived": "INTEGER NOT NULL DEFAULT 0",
        "archived_at": "TEXT",
        "archived_by": "TEXT",
    },
}

PROJECT_CONFIG_DB_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL UNIQUE,
    project_name TEXT NOT NULL,
    project_code TEXT,
    schema_version TEXT,
    version INTEGER,
    last_modified INTEGER,
    created_at TEXT,
    updated_at TEXT,
    created_by TEXT,
    description TEXT,
    qc_policy_json TEXT,
    quality_workbench_json TEXT,
    default_rules_json TEXT,
    project_status TEXT NOT NULL DEFAULT 'active',
    is_archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by TEXT,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS product_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_index INTEGER NOT NULL,
    type_name TEXT NOT NULL,
    model_number TEXT,
    force_version_check INTEGER NOT NULL DEFAULT 0,
    quality_rules_json TEXT,
    raw_json TEXT NOT NULL,
    UNIQUE(project_id, source_index)
);

CREATE TABLE IF NOT EXISTS serial_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_type_id INTEGER NOT NULL REFERENCES product_types(id) ON DELETE CASCADE,
    source_index INTEGER NOT NULL,
    rule_prefix TEXT NOT NULL,
    normalized_prefix TEXT NOT NULL,
    UNIQUE(product_type_id, source_index)
);

CREATE INDEX IF NOT EXISTS idx_serial_rules_prefix ON serial_rules(normalized_prefix);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_type_id INTEGER NOT NULL REFERENCES product_types(id) ON DELETE CASCADE,
    source_index INTEGER NOT NULL,
    name TEXT NOT NULL,
    part_number TEXT,
    qr_rule_type TEXT,
    expected_version TEXT,
    raw_json TEXT NOT NULL,
    UNIQUE(product_type_id, source_index)
);

CREATE TABLE IF NOT EXISTS process_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_type_id INTEGER NOT NULL REFERENCES product_types(id) ON DELETE CASCADE,
    source_index INTEGER NOT NULL,
    process_uid TEXT,
    name TEXT NOT NULL,
    description TEXT,
    step_order INTEGER,
    estimated_duration INTEGER,
    required INTEGER NOT NULL DEFAULT 0,
    photo_required INTEGER NOT NULL DEFAULT 0,
    attachment_type TEXT,
    expected_screw_count INTEGER,
    special_processes TEXT,
    special_parts TEXT,
    extra_focus TEXT,
    pre_prompt TEXT,
    responsible_departments_json TEXT,
    sub_checks_json TEXT,
    raw_json TEXT NOT NULL,
    UNIQUE(product_type_id, source_index)
);
"""


def _normalize_detail_key(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[\s._-]+", "_", text)
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    return text.strip("_")


def _normalize_sub_check_aliases(raw_aliases: Any) -> List[str]:
    aliases: List[str] = []
    if raw_aliases is None:
        return aliases

    if isinstance(raw_aliases, str):
        parts = re.split(r"[\n,;，；]+", raw_aliases)
        aliases = [part.strip() for part in parts if part.strip()]
    elif isinstance(raw_aliases, list):
        aliases = [str(item).strip() for item in raw_aliases if str(item).strip()]
    else:
        aliases = [str(raw_aliases).strip()] if str(raw_aliases).strip() else []

    deduped: List[str] = []
    seen_keys = set()
    for alias in aliases:
        alias_key = _normalize_detail_key(alias)
        if not alias_key or alias_key in seen_keys:
            continue
        seen_keys.add(alias_key)
        deduped.append(alias)
    return deduped


def normalize_sub_checks(raw_sub_checks: Any) -> List[Dict[str, Any]]:
    rows: List[Any]
    if raw_sub_checks is None:
        rows = []
    elif isinstance(raw_sub_checks, list):
        rows = raw_sub_checks
    elif isinstance(raw_sub_checks, str):
        text = raw_sub_checks.strip()
        if not text:
            rows = []
        else:
            try:
                parsed = json.loads(text)
                rows = parsed if isinstance(parsed, list) else [text]
            except Exception:
                rows = [item.strip() for item in re.split(r"[\n,;，；]+", text) if item.strip()]
    else:
        rows = [raw_sub_checks]

    normalized: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        if isinstance(row, str):
            label = row.strip()
            key = _normalize_detail_key(label)
            aliases: List[str] = []
            required = True
        elif isinstance(row, dict):
            label = str(
                row.get("name")
                or row.get("label")
                or row.get("detailLabel")
                or row.get("detail_label")
                or row.get("key")
                or ""
            ).strip()
            key = str(row.get("key") or "").strip() or _normalize_detail_key(label)
            aliases = _normalize_sub_check_aliases(row.get("aliases"))
            required = bool(row.get("required", True))
        else:
            label = str(row).strip()
            key = _normalize_detail_key(label)
            aliases = []
            required = True

        if not label:
            continue
        if not key:
            key = _normalize_detail_key(label)
        if not key or key in seen:
            continue
        seen.add(key)

        normalized.append({
            "key": key,
            "name": label,
            "required": required,
            "aliases": aliases,
        })

    return normalized


def _json_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _extract_project_quality_fields(config: Dict[str, Any]) -> Dict[str, Any]:
    quality_workbench = config.get("qualityWorkbench")
    default_rules = config.get("defaultRules")
    if default_rules is None and isinstance(quality_workbench, dict):
        default_rules = quality_workbench.get("defaultRules")
    return {
        "qcPolicy": copy.deepcopy(config.get("qcPolicy")),
        "qualityWorkbench": copy.deepcopy(quality_workbench),
        "defaultRules": copy.deepcopy(default_rules),
    }


DEFAULT_RELEASE_RULES: Dict[str, str] = {
    "recordRequired": "block",
    "materialComplete": "block",
    "photoCoverage": "review",
    "qcPassRequired": "block",
    "hilReportRequired": "ignore",
    "bemfReportRequired": "ignore",
}


def _build_default_release_rules() -> Dict[str, str]:
    return copy.deepcopy(DEFAULT_RELEASE_RULES)


def _build_default_quality_workbench() -> Dict[str, Any]:
    return {
        "enabled": True,
        "defaultRules": _build_default_release_rules(),
    }


def _ensure_project_quality_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(config, dict):
        return config

    quality_workbench = config.get("qualityWorkbench")
    if not isinstance(quality_workbench, dict):
        quality_workbench = _build_default_quality_workbench()
        config["qualityWorkbench"] = quality_workbench

    default_rules = config.get("defaultRules")
    if not isinstance(default_rules, dict):
        default_rules = quality_workbench.get("defaultRules")
    if not isinstance(default_rules, dict):
        default_rules = _build_default_release_rules()

    quality_workbench["enabled"] = bool(quality_workbench.get("enabled", True))
    quality_workbench["defaultRules"] = copy.deepcopy(default_rules)
    config["defaultRules"] = copy.deepcopy(default_rules)
    return config


def _ensure_product_type_quality_defaults(product_type: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(product_type, dict):
        return product_type
    if not isinstance(product_type.get("qualityRules"), dict):
        product_type["qualityRules"] = _build_default_release_rules()
    return product_type


def _ensure_config_creation_quality_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(config, dict):
        return config
    _ensure_project_quality_defaults(config)
    product_types = config.get("productTypes")
    if isinstance(product_types, list):
        for product_type in product_types:
            _ensure_product_type_quality_defaults(product_type)
    return config


def _normalize_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return int(default)
    if number < 0:
        return int(default)
    return number


def _normalize_text_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_responsible_departments(value: Any) -> List[str]:
    if value is None:
        return []

    rows: List[str]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                rows = [str(item).strip() for item in parsed if str(item).strip()]
            elif isinstance(parsed, str):
                rows = [item.strip() for item in re.split(r"[\n,;，；]+", parsed) if item.strip()]
            else:
                rows = [item.strip() for item in re.split(r"[\n,;，；]+", text) if item.strip()]
        except Exception:
            rows = [item.strip() for item in re.split(r"[\n,;，；]+", text) if item.strip()]
    elif isinstance(value, list):
        rows = [str(item).strip() for item in value if str(item).strip()]
    else:
        rows = [str(value).strip()] if str(value).strip() else []

    deduped: List[str] = []
    seen = set()
    for name in rows:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(name)
    return deduped


def normalize_serial_rules(value: Any) -> List[str]:
    """Normalize optional serial prefix rules for product type matching."""
    if value is None:
        return []

    rows: List[str] = []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, str):
                        candidate = item.strip()
                        if candidate:
                            rows.append(candidate)
                    elif isinstance(item, dict):
                        candidate = str(
                            item.get("prefix")
                            or item.get("value")
                            or item.get("rule")
                            or item.get("serialPrefix")
                            or ""
                        ).strip()
                        if candidate:
                            rows.append(candidate)
            else:
                rows = [item.strip() for item in re.split(r"[\n,;，；]+", text) if item.strip()]
        except Exception:
            rows = [item.strip() for item in re.split(r"[\n,;，；]+", text) if item.strip()]
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                candidate = item.strip()
            elif isinstance(item, dict):
                candidate = str(
                    item.get("prefix")
                    or item.get("value")
                    or item.get("rule")
                    or item.get("serialPrefix")
                    or ""
                ).strip()
            else:
                candidate = str(item).strip()
            if candidate:
                rows.append(candidate)
    else:
        candidate = str(value).strip()
        if candidate:
            rows.append(candidate)

    deduped: List[str] = []
    seen = set()
    for prefix in rows:
        key = prefix.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(prefix)
    return deduped


def _normalize_bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0

    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def normalize_qr_rule_type(value: Any) -> str:
    text = _normalize_text_value(value).lower()
    return text or "motor"


def normalize_expected_version(value: Any) -> str:
    return _normalize_text_value(value).upper()


def normalize_material_versioning(material: Any) -> None:
    if not isinstance(material, dict):
        return

    material["qrRuleType"] = normalize_qr_rule_type(
        material.get("qrRuleType", material.get("qr_rule_type", "motor"))
    )
    material["expectedVersion"] = normalize_expected_version(
        material.get("expectedVersion", material.get("expected_version", ""))
    )
    material.pop("qr_rule_type", None)
    material.pop("expected_version", None)


def normalize_product_type_versioning(product_type: Any) -> None:
    if not isinstance(product_type, dict):
        return

    product_type["forceVersionCheck"] = _normalize_bool_value(
        product_type.get("forceVersionCheck", product_type.get("force_version_check", False)),
        default=False,
    )
    product_type.pop("force_version_check", None)

    materials = product_type.get("materials")
    if isinstance(materials, list):
        for material in materials:
            normalize_material_versioning(material)


def sanitize_product_type_versioning_for_runtime(product_type: Any) -> None:
    """Compat-only sanitization for legacy/hand-edited configs on read paths.

    Save paths stay strict and rely on validate_config_structure() to reject
    invalid combinations. Runtime paths should not propagate impossible
    combinations that would block all scans on the client.
    """
    if not isinstance(product_type, dict):
        return

    normalize_product_type_versioning(product_type)

    type_name = _normalize_text_value(product_type.get("typeName")) or "未知产品类型"
    materials = product_type.get("materials")
    if not isinstance(materials, list):
        return

    has_force_check_violation = False
    for material in materials:
        if not isinstance(material, dict):
            continue

        qr_rule_type = str(material.get("qrRuleType", "motor")).strip().lower() or "motor"
        expected_version = str(material.get("expectedVersion", "") or "").strip().upper()

        if qr_rule_type != "pcb" and expected_version:
            logger.warning(
                "[版本规则兼容] 产品类型 %s 物料 %s 使用 %s 规则却配置了版本号，读取时已清空版本号",
                type_name,
                material.get("name", "未知物料"),
                qr_rule_type,
            )
            material["expectedVersion"] = ""
            expected_version = ""

        if bool(product_type.get("forceVersionCheck", False)):
            if qr_rule_type != "pcb" or not expected_version:
                has_force_check_violation = True

    if has_force_check_violation:
        logger.warning(
            "[版本规则兼容] 产品类型 %s 的强制版本检查配置不完整，读取时已自动关闭强制检查",
            type_name,
        )
        product_type["forceVersionCheck"] = False


def normalize_process_prompt_profile(step: Any) -> None:
    """Normalize optional process prompt fields for forward/backward compatibility."""
    if not isinstance(step, dict):
        return

    expected_screw_count = step.get("expectedScrewCount", step.get("expected_screw_count", 0))
    step["expectedScrewCount"] = _normalize_non_negative_int(expected_screw_count, default=0)
    step["specialProcesses"] = _normalize_text_value(
        step.get("specialProcesses", step.get("special_processes", ""))
    )
    step["specialParts"] = _normalize_text_value(
        step.get("specialParts", step.get("special_parts", ""))
    )
    step["extraFocus"] = _normalize_text_value(
        step.get("extraFocus", step.get("extra_focus", ""))
    )
    step["prePrompt"] = _normalize_text_value(
        step.get("prePrompt", step.get("pre_prompt", ""))
    )
    step["responsibleDepartments"] = _normalize_responsible_departments(
        step.get("responsibleDepartments", step.get("responsible_departments"))
    )


class ProjectConfigManager:
    """项目配置管理器 - 支持版本管理和结构化存储"""
    
    def __init__(self, config_base_path: Path):
        self.config_base_path = Path(config_base_path)
        self.projects_config_dir = self.config_base_path / "projects"
        self.projects_file = self.config_base_path / "projects.json"
        self.project_db_file = self.projects_config_dir / "project_configs.db"
        self.versions_dir = self.config_base_path / "versions"
        self.backups_dir = self.config_base_path / "backups"
        
        # 确保目录存在
        self.projects_config_dir.mkdir(parents=True, exist_ok=True)
        self.config_base_path.mkdir(parents=True, exist_ok=True)
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def _connect_project_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.project_db_file)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(PROJECT_CONFIG_DB_SCHEMA)
        for table_name, columns in PROJECT_DB_REQUIRED_COLUMNS.items():
            existing = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            }
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    conn.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    )
        return conn

    def _find_project_row_in_db(self, project_name: str) -> Optional[sqlite3.Row]:
        if not self.project_db_file.exists():
            return None

        target_key = self._project_name_key(project_name)
        conn = None
        try:
            conn = self._connect_project_db()
            rows = conn.execute(
                """
                SELECT id, source_file, project_name, raw_json,
                       qc_policy_json, quality_workbench_json, default_rules_json,
                       project_status, is_archived, archived_at, archived_by
                FROM projects
                """
            ).fetchall()
            for row in rows:
                row_project_key = self._project_name_key(row["project_name"])
                row_source_key = self._project_name_key(Path(row["source_file"]).stem)
                if target_key in {row_project_key, row_source_key}:
                    return row
            return None
        except Exception as e:
            logger.warning(f"Database project lookup failed: {e}")
            return None
        finally:
            if conn is not None:
                conn.close()

    def _list_project_rows_from_db(self) -> List[sqlite3.Row]:
        if not self.project_db_file.exists():
            return []

        conn = None
        try:
            conn = self._connect_project_db()
            return conn.execute(
                """
                SELECT id, source_file, project_name, project_code, schema_version, updated_at,
                       project_status, is_archived, archived_at, archived_by
                FROM projects
                ORDER BY COALESCE(updated_at, ''), project_name
                """
            ).fetchall()
        except Exception as e:
            logger.warning(f"List project configs from database failed: {e}")
            return []
        finally:
            if conn is not None:
                conn.close()

    def _database_has_project_records(self) -> bool:
        return len(self._list_project_rows_from_db()) > 0

    def list_projects(self, include_archived: bool = False, include_inactive: bool = False) -> List[str]:
        rows = self._list_project_rows_from_db()
        names = []
        for row in rows:
            if not row["project_name"]:
                continue
            if not include_archived and bool(row["is_archived"]):
                continue
            status = str(row["project_status"] or "active").strip().lower() or "active"
            if not include_inactive and status != "active":
                continue
            names.append(self._normalize_project_name(row["project_name"]))
        return list(dict.fromkeys([name for name in names if name]))

    def list_project_details(
        self,
        include_archived: bool = True,
        include_inactive: bool = True,
    ) -> List[Dict[str, Any]]:
        rows = self._list_project_rows_from_db()
        details: List[Dict[str, Any]] = []
        for row in rows:
            status = str(row["project_status"] or "active").strip().lower() or "active"
            is_archived = bool(row["is_archived"])
            if not include_archived and is_archived:
                continue
            if not include_inactive and status != "active":
                continue
            details.append({
                "projectName": self._normalize_project_name(row["project_name"] or ""),
                "projectCode": row["project_code"] or "",
                "schemaVersion": row["schema_version"] or "1.0",
                "updatedAt": row["updated_at"] or "",
                "projectStatus": status,
                "isArchived": is_archived,
                "archivedAt": row["archived_at"] or "",
                "archivedBy": row["archived_by"] or "",
            })
        return details

    def _load_project_config_from_db(self, project_name: str) -> Optional[Dict[str, Any]]:
        row = self._find_project_row_in_db(project_name)
        if row is None:
            return None
        conn = None
        try:
            conn = self._connect_project_db()
            config = json.loads(row["raw_json"])
            if "qcPolicy" not in config and row["qc_policy_json"]:
                config["qcPolicy"] = json.loads(row["qc_policy_json"])
            if "qualityWorkbench" not in config and row["quality_workbench_json"]:
                config["qualityWorkbench"] = json.loads(row["quality_workbench_json"])
            if "defaultRules" not in config and row["default_rules_json"]:
                config["defaultRules"] = json.loads(row["default_rules_json"])
            if "projectStatus" not in config:
                config["projectStatus"] = str(row["project_status"] or "active").strip().lower() or "active"
            if "isArchived" not in config:
                config["isArchived"] = bool(row["is_archived"])
            if "archivedAt" not in config and row["archived_at"]:
                config["archivedAt"] = row["archived_at"]
            if "archivedBy" not in config and row["archived_by"]:
                config["archivedBy"] = row["archived_by"]
            if (
                isinstance(config.get("qualityWorkbench"), dict)
                and "defaultRules" not in config["qualityWorkbench"]
                and config.get("defaultRules") is not None
            ):
                config["qualityWorkbench"]["defaultRules"] = copy.deepcopy(config["defaultRules"])

            product_type_rows = conn.execute(
                """
                SELECT source_index, type_name, model_number, force_version_check, quality_rules_json
                FROM product_types
                WHERE project_id = ?
                ORDER BY source_index
                """,
                (row["id"],),
            ).fetchall()
            rows_by_index = {int(item["source_index"]): item for item in product_type_rows}
            rows_by_name = {
                self._normalize_project_name(item["type_name"] or ""): item
                for item in product_type_rows
                if item["type_name"]
            }
            for index, product_type in enumerate(config.get("productTypes") or []):
                if not isinstance(product_type, dict):
                    continue
                db_row = rows_by_index.get(index)
                if db_row is None:
                    db_row = rows_by_name.get(self._normalize_project_name(product_type.get("typeName") or ""))
                if db_row is None:
                    continue
                if db_row["model_number"] and not product_type.get("modelNumber"):
                    product_type["modelNumber"] = db_row["model_number"]
                product_type["forceVersionCheck"] = bool(db_row["force_version_check"])
                if db_row["quality_rules_json"]:
                    try:
                        product_type["qualityRules"] = json.loads(db_row["quality_rules_json"])
                    except Exception:
                        logger.warning(
                            "Deserialize product type quality rules failed: %s / %s",
                            row["project_name"],
                            product_type.get("typeName") or db_row["type_name"],
                        )
            logger.info(f"Read project config from database: {row['project_name']}")
            return config
        except Exception as e:
            logger.warning(f"Deserialize project config from database failed: {e}")
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _upsert_project_config_db(self, source_file: str, config: Dict[str, Any]) -> None:
        conn = None
        try:
            conn = self._connect_project_db()
            target_key = self._project_name_key(config.get("projectName") or Path(source_file).stem)

            existing_rows = conn.execute(
                "SELECT id, source_file, project_name FROM projects"
            ).fetchall()
            existing_ids = []
            for row in existing_rows:
                row_keys = {
                    self._project_name_key(row["project_name"]),
                    self._project_name_key(Path(row["source_file"]).stem),
                }
                if target_key in row_keys or row["source_file"] == source_file:
                    existing_ids.append(row["id"])

            for project_id in existing_ids:
                conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

            project_quality_fields = _extract_project_quality_fields(config)
            cur = conn.execute(
                """
                INSERT INTO projects(
                    source_file, project_name, project_code, schema_version, version, last_modified,
                    created_at, updated_at, created_by, description,
                    qc_policy_json, quality_workbench_json, default_rules_json,
                    project_status, is_archived, archived_at, archived_by, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_file,
                    config.get("projectName") or Path(source_file).stem,
                    config.get("projectCode"),
                    config.get("schemaVersion"),
                    config.get("version"),
                    config.get("lastModified"),
                    config.get("createdAt"),
                    config.get("updatedAt"),
                    config.get("createdBy"),
                    config.get("description"),
                    _json_or_none(project_quality_fields.get("qcPolicy")),
                    _json_or_none(project_quality_fields.get("qualityWorkbench")),
                    _json_or_none(project_quality_fields.get("defaultRules")),
                    self._normalize_project_status(config.get("projectStatus")),
                    1 if bool(config.get("isArchived")) else 0,
                    _normalize_text_value(config.get("archivedAt")) or None,
                    _normalize_text_value(config.get("archivedBy")) or None,
                    json.dumps(config, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            project_id = cur.lastrowid

            for product_index, product_type in enumerate(config.get("productTypes") or []):
                cur = conn.execute(
                    """
                    INSERT INTO product_types(
                        project_id, source_index, type_name, model_number,
                        force_version_check, quality_rules_json, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        product_index,
                        product_type.get("typeName") or f"product_type_{product_index + 1}",
                        product_type.get("modelNumber"),
                        1 if product_type.get("forceVersionCheck") else 0,
                        json.dumps(product_type.get("qualityRules") or {}, ensure_ascii=False, separators=(",", ":")),
                        json.dumps(product_type, ensure_ascii=False, separators=(",", ":")),
                    ),
                )
                product_type_id = cur.lastrowid

                for rule_index, rule in enumerate(product_type.get("serialRules") or []):
                    rule_text = str(rule).strip()
                    if not rule_text:
                        continue
                    conn.execute(
                        """
                        INSERT INTO serial_rules(product_type_id, source_index, rule_prefix, normalized_prefix)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            product_type_id,
                            rule_index,
                            rule_text,
                            re.sub(r"[-_\s]+", "", rule_text).lower(),
                        ),
                    )

                for material_index, material in enumerate(product_type.get("materials") or []):
                    conn.execute(
                        """
                        INSERT INTO materials(
                            product_type_id, source_index, name, part_number,
                            qr_rule_type, expected_version, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            product_type_id,
                            material_index,
                            material.get("name") or f"material_{material_index + 1}",
                            material.get("partNumber"),
                            material.get("qrRuleType"),
                            material.get("expectedVersion"),
                            json.dumps(material, ensure_ascii=False, separators=(",", ":")),
                        ),
                    )

                for step_index, step in enumerate(product_type.get("processSteps") or []):
                    conn.execute(
                        """
                        INSERT INTO process_steps(
                            product_type_id, source_index, process_uid, name, description, step_order,
                            estimated_duration, required, photo_required, attachment_type,
                            expected_screw_count, special_processes, special_parts, extra_focus,
                            pre_prompt, responsible_departments_json, sub_checks_json, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            product_type_id,
                            step_index,
                            step.get("id"),
                            step.get("name") or f"step_{step_index + 1}",
                            step.get("description"),
                            step.get("order"),
                            step.get("estimatedDuration"),
                            1 if step.get("required") else 0,
                            1 if step.get("photoRequired") else 0,
                            step.get("attachmentType"),
                            step.get("expectedScrewCount"),
                            step.get("specialProcesses"),
                            step.get("specialParts"),
                            step.get("extraFocus"),
                            step.get("prePrompt"),
                            json.dumps(step.get("responsibleDepartments") or [], ensure_ascii=False, separators=(",", ":")),
                            json.dumps(step.get("subChecks") or [], ensure_ascii=False, separators=(",", ":")),
                            json.dumps(step, ensure_ascii=False, separators=(",", ":")),
                        ),
                    )

            conn.commit()
        except Exception as e:
            if conn is not None:
                conn.rollback()
            logger.warning(f"Sync project config to database failed: {e}")
        finally:
            if conn is not None:
                conn.close()

    def _normalize_project_name(self, project_name: str) -> str:
        return normalize_project_name(project_name)

    def _project_name_key(self, project_name: str) -> str:
        return project_name_key(project_name)

    def _resolve_existing_project_stem(self, project_name: str) -> Optional[str]:
        normalized = self._normalize_project_name(project_name)
        if not normalized:
            return None

        db_row = self._find_project_row_in_db(normalized)
        if db_row is not None:
            source_file = str(db_row["source_file"] or "").strip()
            if source_file:
                return Path(source_file).stem
            if db_row["project_name"]:
                return self._normalize_project_name(db_row["project_name"])

        direct = self.projects_config_dir / f"{normalized}.json"
        if direct.exists():
            return normalized

        target_key = self._project_name_key(normalized)
        matches = []
        for config_file in self.projects_config_dir.glob("*.json"):
            if self._project_name_key(config_file.stem) == target_key:
                matches.append(config_file)

        if matches:
            latest = max(matches, key=lambda f: f.stat().st_mtime)
            return latest.stem
        return normalized
    
    def create_default_project_config(self, project_name: str, project_code: str = "") -> Dict[str, Any]:
        """创建默认项目配置结构（Schema 2.1结构）"""
        default_config = {
            "projectName": project_name,
            "projectCode": project_code,
            "schemaVersion": "2.1",
            "version": 1,
            "lastModified": int(datetime.now().timestamp() * 1000),
            "createdAt": datetime.now().isoformat(),
            "updatedAt": datetime.now().isoformat(),
            "createdBy": "system",
            "description": f"{project_name}项目配置",
            "projectStatus": "active",
            "isArchived": False,
            "productTypes": [],
            "processSteps": [],
            "metadata": {
                "configFormat": "v2.0",
                "supportedFeatures": ["productTypes", "processSteps", "versionControl"],
                "lastBackup": None,
                "totalVersions": 1,
            }
        }
        return _ensure_config_creation_quality_defaults(default_config)

    def get_project_config(self, project_name: str, auto_upgrade: bool = True) -> Optional[Dict[str, Any]]:
        """获取项目配置（支持自动升级到最新schema版本）
        
        Args:
            project_name: 项目名称
            auto_upgrade: 是否自动升级配置到最新版本（默认True）
        """
        try:
            resolved_stem = self._resolve_existing_project_stem(project_name)
            if not resolved_stem:
                logger.warning("项目配置读取失败：项目名为空")
                return None

            db_config = self._load_project_config_from_db(resolved_stem)
            if db_config is None and project_name and project_name != resolved_stem:
                db_config = self._load_project_config_from_db(project_name)
            if isinstance(db_config, dict):
                logger.info(f"从项目配置数据库读取配置: {resolved_stem}")
                config = db_config
                if auto_upgrade:
                    config = self._upgrade_config_to_latest(config, resolved_stem)

                if isinstance(config.get("productTypes"), list):
                    for product_type in config["productTypes"]:
                        sanitize_product_type_versioning_for_runtime(product_type)

                return config

            logger.warning(f"Project config not found in database: {resolved_stem}")
            return None
        except Exception as e:
            logger.error(f"读取项目配置失败: {e}")
            return None
    
    def _upgrade_config_to_latest(self, config: Dict[str, Any], project_name: str) -> Dict[str, Any]:
        """将配置升级到最新版本（2.1）
        
        Args:
            config: 原始配置
            project_name: 项目名称
            
        Returns:
            升级后的配置
        """
        current_version = config.get("schemaVersion", "1.0")
        
        # 如果已是最新版本，直接返回
        if current_version == "2.1":
            return config
        
        logger.info(f"[配置升级] 项目 {project_name} 从版本 {current_version} 升级到 2.1")
        
        # 升级到2.1：添加projectCode和modelNumber字段
        if "projectCode" not in config:
            config["projectCode"] = ""  # 默认为空
            logger.info(f"[配置升级] 添加 projectCode 字段")
        
        # 为每个产品类型添加modelNumber
        if "productTypes" in config:
            for product_type in config["productTypes"]:
                if "modelNumber" not in product_type:
                    product_type["modelNumber"] = ""  # 默认为空
                    logger.info(f"[配置升级] 为产品类型 {product_type.get('typeName')} 添加 modelNumber 字段")
                has_canonical_serial_rules = "serialRules" in product_type
                serial_rules_raw = product_type.get("serialRules")
                if not has_canonical_serial_rules:
                    serial_rules_raw = product_type.get(
                        "serial_rules",
                        product_type.get("serialPrefixes", product_type.get("serial_prefixes"))
                    )
                product_type["serialRules"] = normalize_serial_rules(serial_rules_raw)
                product_type.pop("serial_rules", None)
                product_type.pop("serialPrefixes", None)
                product_type.pop("serial_prefixes", None)
                normalize_product_type_versioning(product_type)
        
        # 更新schema版本
        config["schemaVersion"] = "2.1"
        config["updatedAt"] = datetime.now().isoformat()
        config["projectStatus"] = self._normalize_project_status(config.get("projectStatus"))
        config["isArchived"] = bool(config.get("isArchived", False))
        
        # 保存升级后的配置
        try:
            self.save_project_config(project_name, config)
            logger.info(f"[配置升级] 项目 {project_name} 已保存升级后的配置")
        except Exception as e:
            logger.warning(f"[配置升级] 保存升级配置失败: {e}")
        
        return config
    
    def save_project_config(self, project_name: str, config: Dict[str, Any]) -> bool:
        """保存项目配置（支持版本管理）"""
        try:
            resolved_stem = self._resolve_existing_project_stem(project_name)
            if not resolved_stem:
                logger.error("保存项目配置失败：项目名为空")
                return False

            config = dict(config or {})
            config["projectName"] = resolved_stem
            
            # 如果配置文件已存在，先备份
            existing_config = self.get_project_config(resolved_stem, auto_upgrade=False)
            if existing_config:
                self.save_config_version(resolved_stem, dict(existing_config))
                for key, value in _extract_project_quality_fields(existing_config).items():
                    if key not in config and value is not None:
                        config[key] = copy.deepcopy(value)
            
            # 确保有 schemaVersion 字段
            if "schemaVersion" not in config:
                # 检测并设置版本
                detected_version = self.detect_config_version(config)
                config["schemaVersion"] = detected_version
                logger.info(f"自动设置 schemaVersion 为: {detected_version}")
            
            # 更新版本信息（同时支持version和configVersion字段，确保移动端兼容）
            if "version" not in config:
                config["version"] = 1
            else:
                config["version"] = config["version"] + 1
            
            # 保持configVersion字段用于向后兼容
            config["configVersion"] = config["version"]
            
            # 更新时间戳
            config["updatedAt"] = datetime.now().isoformat()
            config["projectStatus"] = self._normalize_project_status(config.get("projectStatus"))
            config["isArchived"] = bool(config.get("isArchived", False))
            if config["isArchived"]:
                config["archivedAt"] = _normalize_text_value(config.get("archivedAt")) or datetime.now().isoformat()
                config["archivedBy"] = _normalize_text_value(config.get("archivedBy"))
            else:
                config["archivedAt"] = ""
                config["archivedBy"] = ""

            # 规范化：新版本配置中 processSteps 隶属某个 productType 时，productType 字段可由父级推导。
            # 允许旧/外部工具写入“缺少 productType”的配置，保存时自动补齐以保持兼容性。
            if config.get("schemaVersion") in ["2.0", "2.1"] and isinstance(config.get("productTypes"), list):
                for pt in config["productTypes"]:
                    if not isinstance(pt, dict):
                        continue
                    has_canonical_serial_rules = "serialRules" in pt
                    serial_rules_raw = pt.get("serialRules")
                    if not has_canonical_serial_rules:
                        serial_rules_raw = pt.get(
                            "serial_rules",
                            pt.get("serialPrefixes", pt.get("serial_prefixes"))
                        )
                    pt["serialRules"] = normalize_serial_rules(serial_rules_raw)
                    pt.pop("serial_rules", None)
                    pt.pop("serialPrefixes", None)
                    pt.pop("serial_prefixes", None)
                    normalize_product_type_versioning(pt)
                    type_name = pt.get("typeName")
                    steps = pt.get("processSteps", [])
                    if not isinstance(steps, list):
                        continue
                    for step in steps:
                        if not isinstance(step, dict):
                            continue
                        if type_name and not step.get("productType"):
                            step["productType"] = type_name
                        # 向后兼容：缺省 attachmentType 视为 photo
                        step.setdefault("attachmentType", "photo")
                        raw_sub_checks = step.get("subChecks")
                        if raw_sub_checks is None and "subchecks" in step:
                            raw_sub_checks = step.get("subchecks")
                        step["subChecks"] = normalize_sub_checks(raw_sub_checks)
                        step.pop("subchecks", None)
                        normalize_process_prompt_profile(step)
            elif isinstance(config.get("processAttributes"), list):
                for step in config.get("processAttributes", []):
                    if not isinstance(step, dict):
                        continue
                    raw_sub_checks = step.get("subChecks")
                    if raw_sub_checks is None and "subchecks" in step:
                        raw_sub_checks = step.get("subchecks")
                    step["subChecks"] = normalize_sub_checks(raw_sub_checks)
                    step.pop("subchecks", None)
                    normalize_process_prompt_profile(step)
            
            # 验证配置结构
            if not self.validate_config_structure(config):
                logger.error(f"配置结构验证失败: {project_name}")
                return False
            
            # 保存版本历史
            self.save_config_version(resolved_stem, config.copy())
            
            # 保存当前配置
            self._upsert_project_config_db(f"{resolved_stem}.json", config)
            
            logger.info(f"保存项目配置: {resolved_stem} (版本: {config['configVersion']})")
            return True
        except Exception as e:
            logger.error(f"保存项目配置失败: {e}")
            return False
    
    def create_project_config(self, project_name: str) -> bool:
        """创建新项目配置"""
        try:
            normalized_name = self._normalize_project_name(project_name)
            if not normalized_name:
                logger.warning("项目名称为空")
                return False

            if self.get_project_config(normalized_name) is not None:
                logger.warning(f"项目配置已存在: {normalized_name}")
                return False
            
            default_config = self.create_default_project_config(normalized_name)
            return self.save_project_config(normalized_name, default_config)
        except Exception as e:
            logger.error(f"创建项目配置失败: {e}")
            return False
    
    def delete_project_config(self, project_name: str) -> bool:
        """Delete project config from database."""
        normalized_name = self._normalize_project_name(project_name)
        if not normalized_name:
            logger.warning("Delete project config failed: empty project name")
            return False

        row = self._find_project_row_in_db(normalized_name)
        if row is None:
            logger.warning(f"Delete project config skipped, not found in DB: {normalized_name}")
            return False

        conn = None
        try:
            conn = self._connect_project_db()
            conn.execute("DELETE FROM projects WHERE id = ?", (row["id"],))
            conn.commit()
            logger.info(f"Deleted project config from database: {normalized_name}")
            return True
        except Exception as e:
            if conn is not None:
                conn.rollback()
            logger.error(f"Delete project config failed: {e}")
            return False
        finally:
            if conn is not None:
                conn.close()

    def _normalize_project_status(self, value: Any) -> str:
        status = str(value or "active").strip().lower() or "active"
        if status not in ALLOWED_PROJECT_STATUSES:
            return "active"
        return status

    def update_project_lifecycle(
        self,
        project_name: str,
        *,
        status: Optional[str] = None,
        is_archived: Optional[bool] = None,
        actor: str = "",
    ) -> bool:
        config = self.get_project_config(project_name, auto_upgrade=False)
        if not config:
            logger.warning(f"Update project lifecycle failed, config missing: {project_name}")
            return False

        if status is not None:
            config["projectStatus"] = self._normalize_project_status(status)

        if is_archived is not None:
            config["isArchived"] = bool(is_archived)
            if config["isArchived"]:
                config["archivedAt"] = datetime.now().isoformat()
                config["archivedBy"] = actor or config.get("archivedBy", "")
            else:
                config["archivedAt"] = ""
                config["archivedBy"] = ""

        return self.save_project_config(project_name, config)

    def apply_batch_project_configuration(
        self,
        project_names: List[str],
        *,
        source_project_name: str = "",
        status: Optional[str] = None,
        is_archived: Optional[bool] = None,
        actor: str = "",
    ) -> Dict[str, Any]:
        normalized_targets = list(dict.fromkeys([
            self._normalize_project_name(name) for name in (project_names or []) if self._normalize_project_name(name)
        ]))
        if not normalized_targets:
            return {"success": False, "message": "未选择目标项目", "updated": 0, "failed": []}

        source_config = None
        normalized_source = self._normalize_project_name(source_project_name)
        if normalized_source:
            source_config = self.get_project_config(normalized_source, auto_upgrade=False)
            if not source_config:
                return {
                    "success": False,
                    "message": f"源项目配置不存在: {normalized_source}",
                    "updated": 0,
                    "failed": normalized_targets,
                }

        updated = 0
        failed: List[str] = []

        for project_name in normalized_targets:
            try:
                config = self.get_project_config(project_name, auto_upgrade=False)
                if not config:
                    failed.append(project_name)
                    continue

                if source_config:
                    preserved_name = project_name
                    preserved_code = config.get("projectCode", "")
                    preserved_status = config.get("projectStatus", "active")
                    preserved_archived = bool(config.get("isArchived", False))
                    preserved_archived_at = config.get("archivedAt", "")
                    preserved_archived_by = config.get("archivedBy", "")
                    preserved_created_at = config.get("createdAt", "")
                    preserved_created_by = config.get("createdBy", "")

                    config = copy.deepcopy(source_config)
                    config["projectName"] = preserved_name
                    config["projectCode"] = preserved_code
                    config["createdAt"] = preserved_created_at
                    config["createdBy"] = preserved_created_by
                    config["projectStatus"] = preserved_status
                    config["isArchived"] = preserved_archived
                    config["archivedAt"] = preserved_archived_at
                    config["archivedBy"] = preserved_archived_by
                    config["updatedAt"] = datetime.now().isoformat()

                if status is not None:
                    config["projectStatus"] = self._normalize_project_status(status)
                if is_archived is not None:
                    config["isArchived"] = bool(is_archived)
                    if config["isArchived"]:
                        config["archivedAt"] = datetime.now().isoformat()
                        config["archivedBy"] = actor or config.get("archivedBy", "")
                    else:
                        config["archivedAt"] = ""
                        config["archivedBy"] = ""

                if not self.save_project_config(project_name, config):
                    failed.append(project_name)
                    continue

                updated += 1
            except Exception:
                logger.exception("Batch project configuration failed for %s", project_name)
                failed.append(project_name)

        return {
            "success": updated > 0 and not failed,
            "message": f"批量配置完成，成功 {updated} 个，失败 {len(failed)} 个",
            "updated": updated,
            "failed": failed,
        }

    def get_process_attributes(self, project_name: str) -> List[Dict[str, Any]]:
        """获取项目的工序属性配置"""
        try:
            config = self.get_project_config(project_name)
            if config and "processAttributes" in config:
                # 按order字段排序
                processes = config["processAttributes"]
                processes.sort(key=lambda x: x.get("order", 0))
                for process in processes:
                    if isinstance(process, dict):
                        process["subChecks"] = normalize_sub_checks(
                            process.get("subChecks", process.get("subchecks"))
                        )
                        process.pop("subchecks", None)
                        normalize_process_prompt_profile(process)
                return processes
            return []
        except Exception as e:
            logger.error(f"获取工序属性失败: {e}")
            return []
    
    def get_material_attributes(self, project_name: str) -> List[Dict[str, Any]]:
        """获取项目的物料属性配置"""
        try:
            config = self.get_project_config(project_name)
            if config and "materialAttributes" in config:
                return config["materialAttributes"]
            return []
        except Exception as e:
            logger.error(f"获取物料属性失败: {e}")
            return []
    
    def add_process_attribute(self, project_name: str, process_config: Dict[str, Any]) -> bool:
        """添加工序属性"""
        try:
            config = self.get_project_config(project_name)
            if not config:
                logger.error(f"项目配置不存在: {project_name}")
                return False
            
            if "processAttributes" not in config:
                config["processAttributes"] = []
            
            # 生成唯一ID
            if "id" not in process_config:
                process_config["id"] = f"process_{uuid.uuid4().hex[:8]}"
            
            # 设置默认值
            process_config.setdefault("required", True)
            process_config.setdefault("photoRequired", True)
            process_config.setdefault("estimatedDuration", 300)
            normalize_process_prompt_profile(process_config)
            
            # 设置排序顺序
            if "order" not in process_config:
                max_order = max([p.get("order", 0) for p in config["processAttributes"]], default=0)
                process_config["order"] = max_order + 1
            
            config["processAttributes"].append(process_config)
            return self.save_project_config(project_name, config)
            
        except Exception as e:
            logger.error(f"添加工序属性失败: {e}")
            return False
    
    def update_process_attribute(self, project_name: str, process_id: str, updates: Dict[str, Any]) -> bool:
        """更新工序属性"""
        try:
            config = self.get_project_config(project_name)
            if not config or "processAttributes" not in config:
                return False
            
            for process in config["processAttributes"]:
                if process.get("id") == process_id:
                    process.update(updates)
                    normalize_process_prompt_profile(process)
                    return self.save_project_config(project_name, config)
            
            logger.warning(f"工序属性不存在: {process_id}")
            return False
            
        except Exception as e:
            logger.error(f"更新工序属性失败: {e}")
            return False
    
    def delete_process_attribute(self, project_name: str, process_id: str) -> bool:
        """删除工序属性"""
        try:
            config = self.get_project_config(project_name)
            if not config or "processAttributes" not in config:
                return False
            
            original_count = len(config["processAttributes"])
            config["processAttributes"] = [
                p for p in config["processAttributes"] 
                if p.get("id") != process_id
            ]
            
            if len(config["processAttributes"]) < original_count:
                return self.save_project_config(project_name, config)
            else:
                logger.warning(f"工序属性不存在: {process_id}")
                return False
                
        except Exception as e:
            logger.error(f"删除工序属性失败: {e}")
            return False
    
    def reorder_process_attributes(self, project_name: str, process_orders: List[Dict[str, Any]]) -> bool:
        """重新排序工序属性"""
        try:
            config = self.get_project_config(project_name)
            if not config or "processAttributes" not in config:
                return False
            
            # 更新排序
            for order_info in process_orders:
                process_id = order_info.get("id")
                new_order = order_info.get("order")
                
                for process in config["processAttributes"]:
                    if process.get("id") == process_id:
                        process["order"] = new_order
                        break
            
            return self.save_project_config(project_name, config)
            
        except Exception as e:
            logger.error(f"重新排序工序属性失败: {e}")
            return False
    
    def add_material_attribute(self, project_name: str, material_config: Dict[str, Any]) -> bool:
        """添加物料属性"""
        try:
            config = self.get_project_config(project_name)
            if not config:
                logger.error(f"项目配置不存在: {project_name}")
                return False
            
            if "materialAttributes" not in config:
                config["materialAttributes"] = []
            
            # 生成唯一ID
            if "id" not in material_config:
                material_config["id"] = f"material_{uuid.uuid4().hex[:8]}"
            
            # 设置默认值
            material_config.setdefault("type", "component")
            material_config.setdefault("required", True)
            material_config.setdefault("qrCodeFormat", "CODE128")
            
            config["materialAttributes"].append(material_config)
            return self.save_project_config(project_name, config)
            
        except Exception as e:
            logger.error(f"添加物料属性失败: {e}")
            return False
    
    def validate_config_structure(self, config: Dict[str, Any]) -> bool:
        """验证配置文件结构（支持新旧版本）"""
        try:
            # 必需字段
            required_fields = ["projectName"]
            for field in required_fields:
                if field not in config:
                    logger.error(f"配置文件缺少必需字段: {field}")
                    return False
            
            # 检测配置版本
            schema_version = config.get("schemaVersion", "1.0")
            
            if schema_version in ["2.0", "2.1"]:
                # 验证新版本结构（基于产品类型的工序）
                if "productTypes" in config:
                    if not isinstance(config["productTypes"], list):
                        logger.error("productTypes必须是列表类型")
                        return False
                    
                    for product_type in config["productTypes"]:
                        if not isinstance(product_type, dict):
                            logger.error("产品类型必须是字典类型")
                            return False
                        
                        if "typeName" not in product_type:
                            logger.error("产品类型缺少typeName字段")
                            return False

                        if "serialRules" in product_type:
                            if not isinstance(product_type["serialRules"], list):
                                logger.error("serialRules必须是列表类型")
                                return False
                            for serial_rule in product_type["serialRules"]:
                                if not str(serial_rule or "").strip():
                                    logger.error("serialRules项不能为空")
                                    return False

                        if "forceVersionCheck" in product_type and not isinstance(product_type["forceVersionCheck"], bool):
                            logger.error("forceVersionCheck必须是布尔类型")
                            return False
                        
                        force_version_check = bool(product_type.get("forceVersionCheck", False))

                        # 验证物料列表
                        if "materials" in product_type:
                            if not isinstance(product_type["materials"], list):
                                logger.error("materials必须是列表类型")
                                return False
                            
                            for material in product_type["materials"]:
                                if not isinstance(material, dict):
                                    logger.error("物料必须是字典类型")
                                    return False
                                
                                if "name" not in material or "partNumber" not in material:
                                    logger.error("物料缺少必需字段")
                                    return False

                                qr_rule_type = material.get("qrRuleType", "motor")
                                if not isinstance(qr_rule_type, str) or not qr_rule_type.strip():
                                    logger.error("物料qrRuleType不能为空")
                                    return False
                                if qr_rule_type.lower() not in ALLOWED_QR_RULE_TYPES:
                                    logger.error("物料qrRuleType不支持")
                                    return False

                                expected_version = material.get("expectedVersion", "")
                                if expected_version is not None and not isinstance(expected_version, str):
                                    logger.error("物料expectedVersion必须是字符串")
                                    return False
                                expected_version = str(expected_version or "").strip()

                                if qr_rule_type.lower() == "motor" and expected_version:
                                    logger.error("电机二维码规则暂不支持版本号配置")
                                    return False

                                if force_version_check:
                                    if qr_rule_type.lower() != "pcb":
                                        logger.error("启用强制版本检查时，所有物料必须使用PCB二维码规则")
                                        return False
                                    if not expected_version:
                                        logger.error("启用强制版本检查时，所有物料都必须配置版本号")
                                        return False
                        
                        # 验证工序列表
                        if "processSteps" in product_type:
                            if not isinstance(product_type["processSteps"], list):
                                logger.error("processSteps必须是列表类型")
                                return False
                            
                            for process in product_type["processSteps"]:
                                if not isinstance(process, dict):
                                    logger.error("工序必须是字典类型")
                                    return False
                                
                                if "name" not in process:
                                    logger.error("工序缺少name字段")
                                    return False

                                if "subChecks" in process:
                                    if not isinstance(process["subChecks"], list):
                                        logger.error("subChecks必须是列表类型")
                                        return False
                                    for sub_check in process["subChecks"]:
                                        if not isinstance(sub_check, dict):
                                            logger.error("subChecks项必须是字典类型")
                                            return False
                                        if not str(sub_check.get("name") or "").strip():
                                            logger.error("subChecks项缺少name字段")
                                            return False
                                        if "aliases" in sub_check and not isinstance(sub_check["aliases"], list):
                                            logger.error("subChecks.aliases必须是列表类型")
                                            return False
            else:
                # 验证旧版本结构（向后兼容）
                if "processAttributes" in config:
                    for process in config["processAttributes"]:
                        if not isinstance(process, dict):
                            logger.error("工序属性必须是字典类型")
                            return False
                        
                        if "name" not in process:
                            logger.error("工序属性缺少name字段")
                            return False

                        if "subChecks" in process:
                            if not isinstance(process["subChecks"], list):
                                logger.error("processAttributes.subChecks必须是列表类型")
                                return False
                            for sub_check in process["subChecks"]:
                                if not isinstance(sub_check, dict):
                                    logger.error("processAttributes.subChecks项必须是字典类型")
                                    return False
                                if not str(sub_check.get("name") or "").strip():
                                    logger.error("processAttributes.subChecks项缺少name字段")
                                    return False
                
                if "materialAttributes" in config:
                    for material in config["materialAttributes"]:
                        if not isinstance(material, dict):
                            logger.error("物料属性必须是字典类型")
                            return False
                        
                        if "name" not in material:
                            logger.error("物料属性缺少name字段")
                            return False
            
            return True
            
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return False
    
    def create_config_backup(self, project_name: str) -> bool:
        """创建配置文件备份"""
        try:
            resolved_stem = self._resolve_existing_project_stem(project_name)
            if not resolved_stem:
                return False

            config_file = self.projects_config_dir / f"{resolved_stem}.json"
            if not config_file.exists():
                logger.warning(f"配置文件不存在，无法备份: {resolved_stem}")
                return False
            
            # 创建备份文件名（包含时间戳）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"{resolved_stem}_{timestamp}.json"
            backup_file = self.backups_dir / backup_filename
            
            # 复制文件
            shutil.copy2(config_file, backup_file)
            logger.info(f"创建配置备份: {backup_filename}")
            
            # 清理旧备份（保留最近10个）
            self._cleanup_old_backups(resolved_stem)
            
            return True
        except Exception as e:
            logger.error(f"创建配置备份失败: {e}")
            return False
    
    def _cleanup_old_backups(self, project_name: str, keep_count: int = 10):
        """清理旧的备份文件"""
        try:
            # 获取该项目的所有备份文件
            backup_pattern = f"{project_name}_*.json"
            backup_files = list(self.backups_dir.glob(backup_pattern))
            
            # 按修改时间排序（最新的在前）
            backup_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            # 删除超出保留数量的备份
            for backup_file in backup_files[keep_count:]:
                backup_file.unlink()
                logger.info(f"删除旧备份: {backup_file.name}")
                
        except Exception as e:
            logger.error(f"清理旧备份失败: {e}")
    
    def save_config_version(self, project_name: str, config: Dict[str, Any]) -> bool:
        """保存配置版本到版本历史"""
        try:
            # 确保配置有版本号
            if "configVersion" not in config:
                config["configVersion"] = 1
            
            version_num = config["configVersion"]
            version_filename = f"{project_name}_v{version_num}.json"
            version_file = self.versions_dir / version_filename
            
            # 保存版本文件
            with open(version_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"保存配置版本: {version_filename}")
            return True
            
        except Exception as e:
            logger.error(f"保存配置版本失败: {e}")
            return False
    
    def get_config_versions(self, project_name: str) -> List[Dict[str, Any]]:
        """获取项目配置的所有版本"""
        try:
            version_pattern = f"{project_name}_v*.json"
            version_files = list(self.versions_dir.glob(version_pattern))
            
            versions = []
            for version_file in version_files:
                try:
                    with open(version_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        versions.append({
                            "version": config.get("configVersion", 1),
                            "updatedAt": config.get("updatedAt"),
                            "filename": version_file.name,
                            "config": config
                        })
                except Exception as e:
                    logger.warning(f"读取版本文件失败: {version_file.name}, {e}")
            
            # 按版本号排序
            versions.sort(key=lambda v: v["version"], reverse=True)
            return versions
            
        except Exception as e:
            logger.error(f"获取配置版本失败: {e}")
            return []
    
    def restore_config_version(self, project_name: str, version_num: int) -> bool:
        """恢复指定版本的配置"""
        try:
            version_filename = f"{project_name}_v{version_num}.json"
            version_file = self.versions_dir / version_filename
            
            if not version_file.exists():
                logger.error(f"版本文件不存在: {version_filename}")
                return False
            
            # 先备份当前配置
            self.create_config_backup(project_name)
            
            # 读取版本配置
            with open(version_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 更新版本号和时间戳
            config["configVersion"] = config.get("configVersion", version_num) + 1
            config["updatedAt"] = datetime.now().isoformat()
            config["restoredFrom"] = version_num
            
            # 保存为当前配置
            return self.save_project_config(project_name, config)
            
        except Exception as e:
            logger.error(f"恢复配置版本失败: {e}")
            return False
    
    def export_project_config(self, project_name: str, export_path: Path) -> bool:
        """导出项目配置到指定路径"""
        try:
            config = self.get_project_config(project_name)
            if not config:
                logger.error(f"项目配置不存在: {project_name}")
                return False
            
            # 确保导出目录存在
            export_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 添加导出元数据
            export_data = {
                "exportedAt": datetime.now().isoformat(),
                "exportedBy": "ProjectConfigManager",
                "originalProject": project_name,
                "config": config
            }
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"导出项目配置: {project_name} -> {export_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出项目配置失败: {e}")
            return False
    
    def import_project_config(self, import_path: Path, target_project_name: str = None) -> bool:
        """从文件导入项目配置"""
        try:
            if not import_path.exists():
                logger.error(f"导入文件不存在: {import_path}")
                return False
            
            with open(import_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # 检查是否是导出格式
            if "config" in import_data:
                config = import_data["config"]
                original_project = import_data.get("originalProject")
                logger.info(f"导入配置来源: {original_project}")
            else:
                # 直接的配置文件
                config = import_data
            
            # 验证配置结构
            if not self.validate_config_structure(config):
                logger.error("导入的配置文件结构无效")
                return False
            
            # 确定目标项目名称
            project_name = target_project_name or config.get("projectName")
            if not project_name:
                logger.error("无法确定目标项目名称")
                return False
            
            # 更新配置信息
            config["projectName"] = project_name
            config["importedAt"] = datetime.now().isoformat()
            config["importedFrom"] = str(import_path)
            
            # 如果目标项目已存在，先备份
            if self.get_project_config(project_name):
                self.create_config_backup(project_name)
            
            # 保存导入的配置
            return self.save_project_config(project_name, config)
            
        except Exception as e:
            logger.error(f"导入项目配置失败: {e}")
            return False
    
    def add_process_to_product_type(
        self, 
        project_name: str, 
        product_type_name: str,
        process_config: Dict[str, Any]
    ) -> bool:
        """为指定产品类型添加工序
        
        Args:
            project_name: 项目名称
            product_type_name: 产品类型名称
            process_config: 工序配置字典
            
        Returns:
            bool: 添加成功返回True，否则返回False
        """
        try:
            config = self.get_project_config(project_name)
            if not config:
                logger.error(f"项目配置不存在: {project_name}")
                return False
            
            # 查找产品类型
            target_product_type = None
            for product_type in config.get("productTypes", []):
                if product_type.get("typeName") == product_type_name:
                    target_product_type = product_type
                    break
            
            if not target_product_type:
                logger.error(f"产品类型不存在: {product_type_name}")
                return False
            
            # 确保产品类型有processSteps字段
            if "processSteps" not in target_product_type:
                target_product_type["processSteps"] = []

            process_config = dict(process_config or {})
            
            # 生成唯一ID
            if "id" not in process_config:
                process_config["id"] = f"process_{uuid.uuid4().hex[:8]}"
            
            # 设置产品类型关联
            process_config["productType"] = product_type_name
            
            # 设置默认值
            process_config.setdefault("required", True)
            process_config.setdefault("photoRequired", True)
            process_config.setdefault("estimatedDuration", 300)
            process_config.setdefault("description", "")
            process_config["subChecks"] = normalize_sub_checks(
                process_config.get("subChecks", process_config.get("subchecks"))
            )
            process_config.pop("subchecks", None)
            normalize_process_prompt_profile(process_config)
            
            # 设置排序顺序
            if "order" not in process_config:
                max_order = max(
                    [p.get("order", 0) for p in target_product_type["processSteps"]], 
                    default=0
                )
                process_config["order"] = max_order + 1
            
            # 添加工序
            target_product_type["processSteps"].append(process_config)
            
            # 保存配置
            success = self.save_project_config(project_name, config)
            if success:
                logger.info(f"成功添加工序 {process_config.get('name')} 到产品类型 {product_type_name}")
            return success
            
        except Exception as e:
            logger.error(f"添加工序到产品类型失败: {e}", exc_info=True)
            return False
    
    def get_product_type_processes(
        self,
        project_name: str,
        product_type_name: str
    ) -> List[Dict[str, Any]]:
        """获取指定产品类型的工序列表
        
        Args:
            project_name: 项目名称
            product_type_name: 产品类型名称
            
        Returns:
            List[Dict[str, Any]]: 工序列表，按order排序
        """
        try:
            config = self.get_project_config(project_name)
            if not config:
                logger.error(f"项目配置不存在: {project_name}")
                return []
            
            # 查找产品类型
            for product_type in config.get("productTypes", []):
                if product_type.get("typeName") == product_type_name:
                    processes = product_type.get("processSteps", [])
                    # 按order字段排序
                    processes.sort(key=lambda x: x.get("order", 0))
                    for process in processes:
                        if isinstance(process, dict):
                            process["subChecks"] = normalize_sub_checks(
                                process.get("subChecks", process.get("subchecks"))
                            )
                            process.pop("subchecks", None)
                            normalize_process_prompt_profile(process)
                    return processes
            
            logger.warning(f"产品类型不存在: {product_type_name}")
            return []
            
        except Exception as e:
            logger.error(f"获取产品类型工序失败: {e}", exc_info=True)
            return []

    def sync_process_department_membership(
        self,
        project_name: str,
        product_type_name: str,
        department_name: str,
        process_ids: List[str]
    ) -> bool:
        """按责任部门批量同步产品类型下的工序归属。

        兼容策略：
        - 底层仍写回到每个工序的 responsibleDepartments；
        - 被选中的工序补上该部门；
        - 未选中的工序移除该部门；
        - 其它部门归属保持不变。
        """
        try:
            config = self.get_project_config(project_name)
            if not config:
                logger.error(f"项目配置不存在: {project_name}")
                return False

            normalized_department = _normalize_text_value(department_name)
            if not normalized_department:
                logger.error("责任部门不能为空")
                return False

            target_product_type = None
            for product_type in config.get("productTypes", []):
                if product_type.get("typeName") == product_type_name:
                    target_product_type = product_type
                    break

            if not target_product_type:
                logger.error(f"产品类型不存在: {product_type_name}")
                return False

            steps = target_product_type.get("processSteps", [])
            if not isinstance(steps, list):
                logger.error(f"产品类型 {product_type_name} 的工序列表格式无效")
                return False

            selected_ids = {
                str(process_id).strip()
                for process_id in (process_ids or [])
                if str(process_id).strip()
            }
            normalized_department_key = normalized_department.lower()

            for process in steps:
                if not isinstance(process, dict):
                    continue

                process_id = str(process.get("id") or "").strip()
                current_departments = _normalize_responsible_departments(
                    process.get("responsibleDepartments", process.get("responsible_departments"))
                )

                merged_departments: List[str] = []
                seen_keys = set()
                for current_department in current_departments:
                    current_key = current_department.lower()
                    if current_key == normalized_department_key:
                        continue
                    if current_key in seen_keys:
                        continue
                    seen_keys.add(current_key)
                    merged_departments.append(current_department)

                if process_id and process_id in selected_ids:
                    merged_departments.append(normalized_department)

                process["responsibleDepartments"] = merged_departments
                normalize_process_prompt_profile(process)

            return self.save_project_config(project_name, config)

        except Exception as e:
            logger.error(f"批量同步责任部门归属失败: {e}", exc_info=True)
            return False
    
    def update_process_in_product_type(
        self,
        project_name: str,
        product_type_name: str,
        process_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """更新产品类型中的工序
        
        Args:
            project_name: 项目名称
            product_type_name: 产品类型名称
            process_id: 工序ID
            updates: 更新的字段字典
            
        Returns:
            bool: 更新成功返回True，否则返回False
        """
        try:
            config = self.get_project_config(project_name)
            if not config:
                logger.error(f"项目配置不存在: {project_name}")
                return False
            
            # 查找产品类型
            target_product_type = None
            for product_type in config.get("productTypes", []):
                if product_type.get("typeName") == product_type_name:
                    target_product_type = product_type
                    break
            
            if not target_product_type:
                logger.error(f"产品类型不存在: {product_type_name}")
                return False
            
            # 查找并更新工序
            process_found = False
            for process in target_product_type.get("processSteps", []):
                if process.get("id") == process_id:
                    # 不允许修改id和productType
                    updates_copy = updates.copy()
                    updates_copy.pop("id", None)
                    updates_copy.pop("productType", None)
                    if "subchecks" in updates_copy and "subChecks" not in updates_copy:
                        updates_copy["subChecks"] = updates_copy.pop("subchecks")
                    if "subChecks" in updates_copy:
                        updates_copy["subChecks"] = normalize_sub_checks(updates_copy.get("subChecks"))
                    
                    process.update(updates_copy)
                    normalize_process_prompt_profile(process)
                    process_found = True
                    break
            
            if not process_found:
                logger.warning(f"工序不存在: {process_id}")
                return False
            
            # 保存配置
            success = self.save_project_config(project_name, config)
            if success:
                logger.info(f"成功更新工序 {process_id} 在产品类型 {product_type_name}")
            return success
            
        except Exception as e:
            logger.error(f"更新产品类型工序失败: {e}", exc_info=True)
            return False
    
    def delete_process_from_product_type(
        self,
        project_name: str,
        product_type_name: str,
        process_id: str
    ) -> bool:
        """从产品类型中删除工序
        
        Args:
            project_name: 项目名称
            product_type_name: 产品类型名称
            process_id: 工序ID
            
        Returns:
            bool: 删除成功返回True，否则返回False
        """
        try:
            config = self.get_project_config(project_name)
            if not config:
                logger.error(f"项目配置不存在: {project_name}")
                return False
            
            # 查找产品类型
            target_product_type = None
            for product_type in config.get("productTypes", []):
                if product_type.get("typeName") == product_type_name:
                    target_product_type = product_type
                    break
            
            if not target_product_type:
                logger.error(f"产品类型不存在: {product_type_name}")
                return False
            
            # 删除工序
            original_count = len(target_product_type.get("processSteps", []))
            target_product_type["processSteps"] = [
                p for p in target_product_type.get("processSteps", [])
                if p.get("id") != process_id
            ]
            
            if len(target_product_type["processSteps"]) >= original_count:
                logger.warning(f"工序不存在: {process_id}")
                return False
            
            # 保存配置
            success = self.save_project_config(project_name, config)
            if success:
                logger.info(f"成功删除工序 {process_id} 从产品类型 {product_type_name}")
            return success
            
        except Exception as e:
            logger.error(f"删除产品类型工序失败: {e}", exc_info=True)
            return False
    
    def reorder_processes_in_product_type(
        self,
        project_name: str,
        product_type_name: str,
        process_orders: List[Dict[str, Any]]
    ) -> bool:
        """重新排序产品类型中的工序
        
        Args:
            project_name: 项目名称
            product_type_name: 产品类型名称
            process_orders: 工序排序列表，格式: [{"id": "process_001", "order": 1}, ...]
            
        Returns:
            bool: 排序成功返回True，否则返回False
        """
        try:
            config = self.get_project_config(project_name)
            if not config:
                logger.error(f"项目配置不存在: {project_name}")
                return False
            
            # 查找产品类型
            target_product_type = None
            for product_type in config.get("productTypes", []):
                if product_type.get("typeName") == product_type_name:
                    target_product_type = product_type
                    break
            
            if not target_product_type:
                logger.error(f"产品类型不存在: {product_type_name}")
                return False
            
            # 更新排序
            for order_info in process_orders:
                process_id = order_info.get("id")
                new_order = order_info.get("order")
                
                for process in target_product_type.get("processSteps", []):
                    if process.get("id") == process_id:
                        process["order"] = new_order
                        break
            
            # 保存配置
            success = self.save_project_config(project_name, config)
            if success:
                logger.info(f"成功重新排序产品类型 {product_type_name} 的工序")
            return success
            
        except Exception as e:
            logger.error(f"重新排序产品类型工序失败: {e}", exc_info=True)
            return False
    
    def remove_product_type(
        self,
        project_name: str,
        product_type_name: str
    ) -> bool:
        """删除产品类型（级联删除关联的工序）
        
        Args:
            project_name: 项目名称
            product_type_name: 产品类型名称
            
        Returns:
            bool: 删除成功返回True，否则返回False
        """
        try:
            config = self.get_project_config(project_name)
            if not config:
                logger.error(f"项目配置不存在: {project_name}")
                return False
            
            # 查找并删除产品类型
            original_count = len(config.get("productTypes", []))
            deleted_processes_count = 0
            
            # 记录被删除的工序数量
            for product_type in config.get("productTypes", []):
                if product_type.get("typeName") == product_type_name:
                    deleted_processes_count = len(product_type.get("processSteps", []))
                    break
            
            # 删除产品类型（包括其下的所有工序）
            config["productTypes"] = [
                pt for pt in config.get("productTypes", [])
                if pt.get("typeName") != product_type_name
            ]
            
            if len(config["productTypes"]) >= original_count:
                logger.warning(f"产品类型不存在: {product_type_name}")
                return False
            
            # 保存配置
            success = self.save_project_config(project_name, config)
            if success:
                logger.info(
                    f"成功删除产品类型 {product_type_name} "
                    f"及其关联的 {deleted_processes_count} 个工序"
                )
            return success
            
        except Exception as e:
            logger.error(f"删除产品类型失败: {e}", exc_info=True)
            return False

    def copy_product_type_between_projects(
        self,
        source_project_name: str,
        source_product_type_name: str,
        target_project_name: str,
        target_product_type_name: str,
    ) -> bool:
        """复制一个产品类型配置到目标项目，并使用新的产品类型名称保存。"""
        try:
            source_project_name = self._normalize_project_name(source_project_name)
            target_project_name = self._normalize_project_name(target_project_name)
            source_product_type_name = _normalize_text_value(source_product_type_name)
            target_product_type_name = _normalize_text_value(target_product_type_name)

            if not source_project_name or not target_project_name:
                logger.error("复制产品类型失败：源项目或目标项目为空")
                return False
            if not source_product_type_name or not target_product_type_name:
                logger.error("复制产品类型失败：源产品类型或目标产品类型为空")
                return False

            source_config = self.get_project_config(source_project_name)
            if not source_config:
                logger.error(f"复制产品类型失败：源项目配置不存在 {source_project_name}")
                return False

            target_config = self.get_project_config(target_project_name)
            if not target_config:
                logger.error(f"复制产品类型失败：目标项目配置不存在 {target_project_name}")
                return False

            source_product_type = None
            for product_type in source_config.get("productTypes", []):
                if product_type.get("typeName") == source_product_type_name:
                    source_product_type = product_type
                    break

            if not source_product_type:
                logger.error(
                    "复制产品类型失败：源产品类型不存在 %s/%s",
                    source_project_name,
                    source_product_type_name,
                )
                return False

            target_product_types = target_config.setdefault("productTypes", [])
            for product_type in target_product_types:
                if product_type.get("typeName") == target_product_type_name:
                    logger.error(
                        "复制产品类型失败：目标项目已存在同名产品类型 %s/%s",
                        target_project_name,
                        target_product_type_name,
                    )
                    return False

            copied_product_type = copy.deepcopy(source_product_type)
            copied_product_type["typeName"] = target_product_type_name
            copied_product_type["modelNumber"] = _normalize_text_value(
                copied_product_type.get("modelNumber", "")
            )
            copied_product_type["serialRules"] = normalize_serial_rules(
                copied_product_type.get("serialRules")
            )

            materials = copied_product_type.get("materials")
            if not isinstance(materials, list):
                materials = []
            copied_product_type["materials"] = copy.deepcopy(materials)
            for material in copied_product_type["materials"]:
                normalize_material_versioning(material)

            normalized_processes = []
            for index, process in enumerate(copied_product_type.get("processSteps", []) or [], start=1):
                if not isinstance(process, dict):
                    continue
                process_copy = copy.deepcopy(process)
                process_copy["id"] = f"process_{uuid.uuid4().hex[:8]}"
                process_copy["productType"] = target_product_type_name
                process_copy.setdefault("order", index)
                process_copy["subChecks"] = normalize_sub_checks(
                    process_copy.get("subChecks", process_copy.get("subchecks"))
                )
                process_copy.pop("subchecks", None)
                normalize_process_prompt_profile(process_copy)
                normalized_processes.append(process_copy)
            copied_product_type["processSteps"] = normalized_processes

            _ensure_product_type_quality_defaults(copied_product_type)
            normalize_product_type_versioning(copied_product_type)
            target_product_types.append(copied_product_type)

            success = self.save_project_config(target_project_name, target_config)
            if success:
                logger.info(
                    "成功复制产品类型 %s/%s -> %s/%s",
                    source_project_name,
                    source_product_type_name,
                    target_project_name,
                    target_product_type_name,
                )
            return success

        except Exception as e:
            logger.error(f"复制产品类型失败: {e}", exc_info=True)
            return False
    
    def detect_config_version(self, config: Dict[str, Any]) -> str:
        """检测配置文件的版本
        
        Returns:
            "2.0" - 新版本（工序在产品类型下，包含 schemaVersion=2.1 的情况）
            "1.0" - 旧版本（工序在顶层）
        """
        schema_version = config.get("schemaVersion")

        # 混合态/旧字段优先：顶层存在工序字段时，优先视为旧版本以触发迁移清理。
        if config.get("processSteps") or config.get("processAttributes"):
            return "1.0"

        # 明确标记的版本
        if schema_version in ["1.0"]:
            return "1.0"
        if schema_version in ["2.0", "2.1"]:
            return "2.0"

        # 否则根据结构判断：productTypes 中存在 processSteps 视为新版本
        if "productTypes" in config:
            for product_type in config["productTypes"]:
                if "processSteps" in product_type and len(product_type["processSteps"]) > 0:
                    return "2.0"

        return "1.0"
    
    def migrate_legacy_config(self, project_name: str, auto_backup: bool = True) -> Dict[str, Any]:
        """迁移旧版本配置到新结构
        
        Args:
            project_name: 项目名称
            auto_backup: 是否自动备份原配置
            
        Returns:
            包含迁移结果的字典:
            {
                "success": bool,
                "message": str,
                "migrated": bool,  # 是否执行了迁移
                "backup_file": str,  # 备份文件路径（如果创建了备份）
                "errors": List[str],  # 错误列表
                "warnings": List[str],  # 警告列表
                "stats": {
                    "total_processes": int,
                    "migrated_processes": int,
                    "product_types": int
                }
            }
        """
        result = {
            "success": False,
            "message": "",
            "migrated": False,
            "backup_file": None,
            "errors": [],
            "warnings": [],
            "stats": {
                "total_processes": 0,
                "migrated_processes": 0,
                "product_types": 0
            }
        }
        
        try:
            logger.info(f"开始迁移配置: {project_name}")
            
            # 1. 加载配置
            config = self.get_project_config(project_name)
            if not config:
                result["errors"].append(f"项目配置不存在: {project_name}")
                result["message"] = "配置文件不存在"
                return result
            
            # 2. 检测版本
            current_version = self.detect_config_version(config)
            logger.info(f"检测到配置版本: {current_version}")
            
            if current_version == "2.0":
                result["success"] = True
                result["message"] = "配置已是最新版本，无需迁移"
                logger.info(f"配置已是最新版本: {project_name}")
                return result
            
            # 3. 创建备份
            if auto_backup:
                backup_success = self.create_config_backup(project_name)
                if backup_success:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_filename = f"{project_name}_{timestamp}.json"
                    result["backup_file"] = str(self.backups_dir / backup_filename)
                    logger.info(f"创建配置备份: {backup_filename}")
                else:
                    result["warnings"].append("备份创建失败，但继续迁移")
            
            # 4. 执行迁移
            logger.info("开始数据迁移...")
            
            # 收集旧版本的工序数据
            legacy_processes = []
            
            # 从顶层processSteps收集
            if "processSteps" in config:
                legacy_processes.extend(config.get("processSteps", []))
                result["stats"]["total_processes"] += len(config.get("processSteps", []))
            
            # 从processAttributes收集（旧版本字段名）
            if "processAttributes" in config:
                legacy_processes.extend(config.get("processAttributes", []))
                result["stats"]["total_processes"] += len(config.get("processAttributes", []))
            
            logger.info(f"找到 {len(legacy_processes)} 个待迁移的工序")
            
            # 确保有productTypes
            if "productTypes" not in config or not config["productTypes"]:
                result["warnings"].append("配置中没有产品类型，创建默认产品类型")
                config["productTypes"] = [
                    {
                        "typeName": "默认产品类型",
                        "materials": [],
                        "processSteps": []
                    }
                ]
            
            result["stats"]["product_types"] = len(config["productTypes"])
            
            # 迁移策略：
            # 如果工序有productType字段，分配到对应的产品类型
            # 否则，分配到第一个产品类型
            migrated_count = 0
            
            for process in legacy_processes:
                # 确保工序有必需字段
                if "id" not in process:
                    process["id"] = f"process_{uuid.uuid4().hex[:8]}"
                    result["warnings"].append(f"工序 {process.get('name', 'unknown')} 缺少ID，已自动生成")
                
                if "order" not in process:
                    process["order"] = migrated_count + 1
                
                # 设置默认值
                process.setdefault("required", True)
                process.setdefault("photoRequired", True)
                process.setdefault("estimatedDuration", 300)
                process.setdefault("description", "")
                
                # 确定目标产品类型
                target_product_type = None
                process_product_type = process.get("productType")
                
                if process_product_type:
                    # 查找匹配的产品类型
                    for pt in config["productTypes"]:
                        if pt["typeName"] == process_product_type:
                            target_product_type = pt
                            break
                    
                    if not target_product_type:
                        result["warnings"].append(
                            f"工序 {process.get('name')} 指定的产品类型 {process_product_type} 不存在，"
                            f"将分配到第一个产品类型"
                        )
                
                # 如果没有找到匹配的产品类型，使用第一个
                if not target_product_type:
                    target_product_type = config["productTypes"][0]
                    process["productType"] = target_product_type["typeName"]
                
                # 确保产品类型有processSteps字段
                if "processSteps" not in target_product_type:
                    target_product_type["processSteps"] = []
                
                # 检查是否已存在相同ID的工序
                existing_ids = [p.get("id") for p in target_product_type["processSteps"]]
                if process["id"] not in existing_ids:
                    target_product_type["processSteps"].append(process)
                    migrated_count += 1
                else:
                    result["warnings"].append(
                        f"工序 {process.get('name')} (ID: {process['id']}) 已存在，跳过"
                    )
            
            result["stats"]["migrated_processes"] = migrated_count
            logger.info(f"成功迁移 {migrated_count} 个工序")
            
            # 5. 清理旧字段
            config.pop("processSteps", None)
            config.pop("processAttributes", None)
            
            # 6. 更新版本信息
            config["schemaVersion"] = "2.0"
            config["version"] = config.get("version", 1) + 1
            config["lastModified"] = int(datetime.now().timestamp() * 1000)
            config["migratedAt"] = datetime.now().isoformat()
            config["migratedFrom"] = current_version
            
            # 7. 验证迁移后的配置
            if not self.validate_config_structure(config):
                result["errors"].append("迁移后的配置结构验证失败")
                result["message"] = "配置验证失败"
                logger.error("迁移后的配置结构验证失败")
                
                # 尝试恢复备份
                if result["backup_file"]:
                    logger.info("尝试从备份恢复...")
                    # 这里不实际恢复，只是记录
                    result["warnings"].append("配置验证失败，请手动从备份恢复")
                
                return result
            
            # 8. 保存迁移后的配置
            save_success = self.save_project_config(project_name, config)
            
            if save_success:
                result["success"] = True
                result["migrated"] = True
                result["message"] = f"成功迁移 {migrated_count} 个工序到 {result['stats']['product_types']} 个产品类型"
                logger.info(f"配置迁移完成: {project_name}")
            else:
                result["errors"].append("保存迁移后的配置失败")
                result["message"] = "保存配置失败"
                logger.error("保存迁移后的配置失败")
            
            return result
            
        except Exception as e:
            logger.error(f"配置迁移失败: {e}", exc_info=True)
            result["errors"].append(f"迁移过程发生异常: {str(e)}")
            result["message"] = f"迁移失败: {str(e)}"
            return result
    
    def validate_migration(self, project_name: str) -> Dict[str, Any]:
        """验证迁移后的配置完整性
        
        Returns:
            验证结果字典:
            {
                "valid": bool,
                "errors": List[str],
                "warnings": List[str],
                "stats": {
                    "product_types": int,
                    "total_processes": int,
                    "processes_with_product_type": int
                }
            }
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "stats": {
                "product_types": 0,
                "total_processes": 0,
                "processes_with_product_type": 0
            }
        }
        
        try:
            config = self.get_project_config(project_name)
            if not config:
                validation_result["valid"] = False
                validation_result["errors"].append("配置文件不存在")
                return validation_result
            
            # 检查版本
            schema_version = config.get("schemaVersion", "1.0")
            if schema_version != "2.0":
                validation_result["warnings"].append(f"配置版本为 {schema_version}，不是最新版本 2.0")
            
            # 检查产品类型
            if "productTypes" not in config:
                validation_result["valid"] = False
                validation_result["errors"].append("配置缺少 productTypes 字段")
                return validation_result
            
            validation_result["stats"]["product_types"] = len(config["productTypes"])
            
            # 检查每个产品类型的工序
            for product_type in config["productTypes"]:
                if "processSteps" not in product_type:
                    validation_result["warnings"].append(
                        f"产品类型 {product_type.get('typeName')} 缺少 processSteps 字段"
                    )
                    continue
                
                for process in product_type["processSteps"]:
                    validation_result["stats"]["total_processes"] += 1
                    
                    # 检查必需字段
                    if "id" not in process:
                        validation_result["errors"].append(
                            f"工序 {process.get('name', 'unknown')} 缺少 id 字段"
                        )
                        validation_result["valid"] = False
                    
                    if "name" not in process:
                        validation_result["errors"].append(
                            f"工序 {process.get('id', 'unknown')} 缺少 name 字段"
                        )
                        validation_result["valid"] = False
                    
                    # 检查productType字段
                    if "productType" in process:
                        validation_result["stats"]["processes_with_product_type"] += 1
                        
                        # 验证productType是否匹配
                        if process["productType"] != product_type["typeName"]:
                            validation_result["warnings"].append(
                                f"工序 {process.get('name')} 的 productType 字段 "
                                f"({process['productType']}) 与所属产品类型 "
                                f"({product_type['typeName']}) 不匹配"
                            )
                    else:
                        validation_result["warnings"].append(
                            f"工序 {process.get('name')} 缺少 productType 字段"
                        )
            
            # 检查是否还有旧字段
            if "processSteps" in config and len(config.get("processSteps", [])) > 0:
                validation_result["warnings"].append(
                    f"配置中仍存在顶层 processSteps 字段，包含 {len(config['processSteps'])} 个工序"
                )
            
            if "processAttributes" in config and len(config.get("processAttributes", [])) > 0:
                validation_result["warnings"].append(
                    f"配置中仍存在 processAttributes 字段，包含 {len(config['processAttributes'])} 个工序"
                )
            
            logger.info(f"配置验证完成: {project_name}, 有效: {validation_result['valid']}")
            return validation_result
            
        except Exception as e:
            logger.error(f"配置验证失败: {e}", exc_info=True)
            validation_result["valid"] = False
            validation_result["errors"].append(f"验证过程发生异常: {str(e)}")
            return validation_result
