"""Read-only MES work-hour reporting from remote MES SQLite snapshots."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from qrmes_shared_core.config import config
from qrmes_shared_core.data_dir_utils import resolve_data_dir


MILLISECONDS_PER_HOUR = 3600000
PRODUCTION_COMPLETION_BONUS_MS = 5 * 60 * 1000
COUNTABLE_DEPARTMENT_KEYWORDS = ("生产", "测试", "实验室", "仓库")
DEPARTMENT_DISPLAY_ORDER = ("生产", "测试", "实验室", "仓库")
CANONICAL_DEPARTMENT_GROUPS = (
    ("智能制造部-生产", ("生产",)),
    ("测试和实验室", ("测试", "实验室")),
    ("项目推进部-仓库", ("仓库",)),
)
# Values are read from the user-provided preassembly sheet. Range values such
# as 8-12min are treated as the upper bound until the standard is clarified.
PREASSEMBLY_TIME_RULES = (
    # 电机预装各工序所需时间
    {"label": "电机-柳工双12行驶", "keywords": ("柳工", "双12", "行驶", "电机"), "duration_minutes": 15 + 12 * 60 + 10 + 4 * 60 + 40 + 10},
    {"label": "电机-柳工双12油泵", "keywords": ("柳工", "双12", "油泵", "电机"), "duration_minutes": 10 + 12 * 60 + 10 + 4 * 60 + 40 + 10},
    {"label": "电机-柳工双15行驶", "keywords": ("柳工", "双15", "行驶", "电机"), "duration_minutes": 15 + 12 * 60 + 10 + 4 * 60 + 40 + 10},
    {"label": "电机-柳工双15油泵", "keywords": ("柳工", "双15", "油泵", "电机"), "duration_minutes": 10 + 12 * 60 + 10 + 4 * 60 + 40 + 10},
    {"label": "电机-徐工5T行驶", "keywords": ("徐工", "5T", "行驶", "电机"), "duration_minutes": 15 + 12 * 60 + 10 + 4 * 60 + 10},
    {"label": "电机-徐工5T油泵", "keywords": ("徐工", "5T", "油泵", "电机"), "duration_minutes": 15 + 12 * 60 + 10 + 4 * 60 + 10},
    {"label": "电机-徐工7T行驶", "keywords": ("徐工", "7T", "行驶", "电机"), "duration_minutes": 15 + 12 * 60 + 10 + 4 * 60 + 10},
    {"label": "电机-徐工7T油泵", "keywords": ("徐工", "7T", "油泵", "电机"), "duration_minutes": 15 + 12 * 60 + 10 + 4 * 60 + 10},
    {"label": "电机-三一230双电机", "keywords": ("三一", "230", "双电机"), "duration_minutes": 20 + 12 * 60 + 10 + 4 * 60 + 15 + 10},
    {"label": "电机-三一310单电机", "keywords": ("三一", "310", "单电机"), "duration_minutes": 25 + 12 * 60 + 10 + 4 * 60 + 15 + 10},
    {"label": "电机-三一310双电机", "keywords": ("三一", "310", "双电机"), "duration_minutes": 25 + 12 * 60 + 10 + 4 * 60 + 15 + 10},
    {"label": "电机-三一5T", "keywords": ("三一", "5T", "电机"), "duration_minutes": 18 + 12 * 60 + 10 + 4 * 60 + 15 + 10},
    {"label": "电机-380油冷", "keywords": ("380", "油冷", "电机"), "duration_minutes": 25 + 12 * 60 + 10 + 4 * 60 + 15 + 10},
    # 电控预装各工序所需时间
    {"label": "电控-三一行驶", "keywords": ("三一", "行", "电控"), "duration_minutes": 12 + 10 + 15 + 8 + 15 + 10},
    {"label": "电控-柳工9-10", "keywords": ("柳工", "9", "10", "电控"), "duration_minutes": 12 + 10 + 15 + 8 + 15 + 10},
    {"label": "电控-徐工3.0-3.8", "keywords": ("徐工", "3", "电控"), "duration_minutes": 12 + 10 + 15 + 8 + 15 + 10},
    {"label": "电控-柳工2.7", "keywords": ("柳工", "2.7", "电控"), "duration_minutes": 12 + 10 + 15 + 8 + 15 + 10},
    {"label": "电控-柳工3-4", "keywords": ("柳工", "3", "4", "电控"), "duration_minutes": 12 + 10 + 15 + 8 + 15 + 10},
    {"label": "电控-徐工6-7行驶", "keywords": ("徐工", "6", "7", "行", "电控"), "duration_minutes": 12 + 10 + 15 + 8 + 15 + 10},
    {"label": "电控-柳工4-5", "keywords": ("柳工", "4", "5", "电控"), "duration_minutes": 12 + 10 + 15 + 8 + 15 + 10},
    {"label": "电控-徐工4-5行驶", "keywords": ("徐工", "4", "5", "行", "电控"), "duration_minutes": 12 + 10 + 15 + 8 + 15 + 10},
    {"label": "电控-雷沃50马力", "keywords": ("雷沃", "50", "电控"), "duration_minutes": 12 + 10 + 15 + 8 + 15 + 10},
    {"label": "电控-徐工6-7油泵", "keywords": ("徐工", "6", "7", "油泵", "电控"), "duration_minutes": 12 + 10 + 15 + 8 + 15 + 10},
    {"label": "电控-徐工4-5油泵", "keywords": ("徐工", "4", "5", "油泵", "电控"), "duration_minutes": 12 + 10 + 15 + 8 + 15 + 10},
)


@dataclass(frozen=True)
class MesRemoteSettings:
    enabled: bool
    host: str
    port: int
    username: str
    password: str
    root: str
    snapshot_dir: Path
    snapshot_ttl_seconds: int


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _parse_departments(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        rows = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            rows = parsed if isinstance(parsed, list) else [text]
        except Exception:
            rows = [part.strip() for part in text.replace("，", ",").split(",")]
    result: List[str] = []
    seen = set()
    for row in rows:
        item = _text(row)
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def is_countable_department(department: str) -> bool:
    name = _text(department)
    if not name:
        return False
    if "质量" in name:
        return False
    return any(keyword in name for keyword in COUNTABLE_DEPARTMENT_KEYWORDS)


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve_product_records_db(snapshot_dir: Path) -> Path:
    default_path = snapshot_dir / "product_records.db"
    if default_path.exists():
        return default_path
    nested_path = snapshot_dir / "record" / "product_records.db"
    return nested_path


def _resolve_project_configs_db(snapshot_dir: Path) -> Path:
    default_path = snapshot_dir / "project_configs.db"
    if default_path.exists():
        return default_path
    nested_path = snapshot_dir / "projects" / "project_configs.db"
    return nested_path


def _resolve_unified_db(snapshot_dir: Path) -> Path:
    return snapshot_dir / "unified.db"


def get_mes_live_data_dir() -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    return resolve_data_dir(
        nas_local_base_path=config.get("nas_local_base_path"),
        repo_root=repo_root,
        logger=None,
        create=True,
    )


def _has_mes_live_data(snapshot_dir: Path) -> bool:
    return (
        _resolve_project_configs_db(snapshot_dir).exists()
        and _resolve_product_records_db(snapshot_dir).exists()
        and _resolve_unified_db(snapshot_dir).exists()
    )


def resolve_mes_workhour_source_dir(
    settings: MesRemoteSettings,
    *,
    force_refresh: bool = False,
    logger=None,
) -> Path:
    live_dir = get_mes_live_data_dir()
    if _has_mes_live_data(live_dir):
        if logger:
            logger.info("[MES工时] 使用本地实时数据目录: %s", live_dir)
        return live_dir
    if logger:
        logger.info("[MES工时] 本地实时数据不完整，回退只读快照: %s", settings.snapshot_dir)
    return refresh_mes_snapshot(settings, force=force_refresh, logger=logger)


def get_mes_remote_settings(snapshot_base: Optional[Path] = None) -> MesRemoteSettings:
    default_snapshot = Path(__file__).resolve().parent / "tmp" / "mes_remote_snapshot"
    return MesRemoteSettings(
        enabled=bool(config.get("mes_remote_ssh_enabled", True)),
        host=_text(config.get("mes_remote_ssh_host", "172.16.30.10")),
        port=_safe_int(config.get("mes_remote_ssh_port", 9909), 9909),
        username=_text(config.get("mes_remote_ssh_username", "liudunke")),
        password=_text(config.get("mes_remote_ssh_password", "")),
        root=_text(config.get("mes_remote_root", "/volume2/MES/QRMES")) or "/volume2/MES/QRMES",
        snapshot_dir=snapshot_base or Path(config.get("mes_remote_snapshot_dir", default_snapshot)),
        snapshot_ttl_seconds=max(0, _safe_int(config.get("mes_remote_snapshot_ttl_seconds", 300), 300)),
    )


def refresh_mes_snapshot(settings: MesRemoteSettings, *, force: bool = False, logger=None) -> Path:
    """Copy remote SQLite files to a local cache via SFTP. Remote access is read-only."""
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    targets = {
        "project_configs.db": f"{settings.root}/projects/project_configs.db",
        "product_records.db": f"{settings.root}/record/product_records.db",
        "unified.db": f"{settings.root}/unified.db",
    }
    required_local_files = tuple(targets.keys())

    def _has_local_snapshot() -> bool:
        return all((settings.snapshot_dir / local_name).exists() for local_name in required_local_files)

    if not force and settings.snapshot_ttl_seconds > 0:
        fresh = True
        now = time.time()
        for local_name in targets:
            local_path = settings.snapshot_dir / local_name
            if not local_path.exists() or (now - local_path.stat().st_mtime) > settings.snapshot_ttl_seconds:
                fresh = False
                break
        if fresh:
            return settings.snapshot_dir

    if not settings.enabled:
        return settings.snapshot_dir
    if not settings.password:
        if logger:
            logger.warning("[MES只读快照] 缺少远端 SSH 密码，回退使用本地快照目录：%s", settings.snapshot_dir)
        if _has_local_snapshot():
            return settings.snapshot_dir
        return settings.snapshot_dir

    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=settings.host,
            port=settings.port,
            username=settings.username,
            password=settings.password,
            timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )
        sftp = client.open_sftp()
        try:
            for local_name, remote_path in targets.items():
                local_path = settings.snapshot_dir / local_name
                if logger:
                    logger.info("[MES只读快照] SFTP get %s -> %s", remote_path, local_path)
                # Windows may deny rename/delete in app-managed directories when a
                # previous SQLite handle or scanner briefly holds the file. Write
                # directly to the target; this endpoint is read-only with respect
                # to the remote MES source, and a failed transfer simply raises.
                sftp.get(remote_path, str(local_path))
        finally:
            sftp.close()
    except Exception:
        if _has_local_snapshot():
            if logger:
                logger.warning("[MES只读快照] 刷新失败，回退使用本地已有快照：%s", settings.snapshot_dir, exc_info=True)
            return settings.snapshot_dir
        raise
    finally:
        client.close()

    return settings.snapshot_dir


def _load_product_records(snapshot_dir: Path) -> List[Dict[str, Any]]:
    db_path = _resolve_product_records_db(snapshot_dir)
    if not db_path.exists():
        return []
    with _connect_readonly(db_path) as conn:
        rows = conn.execute(
            """
            SELECT product_serial, product_type, project_name, scan_time
            FROM product_records
            ORDER BY scan_time DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _load_product_configs(snapshot_dir: Path) -> Dict[tuple, Dict[str, Any]]:
    db_path = _resolve_project_configs_db(snapshot_dir)
    if not db_path.exists():
        return {}
    configs: Dict[tuple, Dict[str, Any]] = {}
    with _connect_readonly(db_path) as conn:
        product_rows = conn.execute(
            """
            SELECT p.project_name, p.project_code, pt.id AS product_type_id, pt.type_name, pt.model_number
            FROM product_types pt
            JOIN projects p ON p.id = pt.project_id
            """
        ).fetchall()
        for row in product_rows:
            item = dict(row)
            step_rows = conn.execute(
                """
                SELECT step_order, name, description, responsible_departments_json
                FROM process_steps
                WHERE product_type_id = ?
                ORDER BY COALESCE(step_order, source_index), source_index
                """,
                (item["product_type_id"],),
            ).fetchall()
            steps = []
            departments: List[str] = []
            seen_departments = set()
            for step in step_rows:
                step_item = dict(step)
                step_departments = _parse_departments(step_item.get("responsible_departments_json"))
                step_item["responsible_departments"] = step_departments
                steps.append(step_item)
                for department in step_departments:
                    key = department.casefold()
                    if key not in seen_departments:
                        seen_departments.add(key)
                        departments.append(department)
            item["steps"] = steps
            item["responsible_departments"] = departments
            configs[(item.get("project_name"), item.get("type_name"))] = item
    return configs


def _load_photos_by_serial(snapshot_dir: Path) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    db_path = _resolve_unified_db(snapshot_dir)
    if not db_path.exists():
        return {}
    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    with _connect_readonly(db_path) as conn:
        rows = conn.execute(
            """
            SELECT product_serial, process_step, file_name, captured_by, captured_at, uploaded_at
            FROM process_photos
            ORDER BY COALESCE(uploaded_at, captured_at), id
            """
        ).fetchall()
    for row in rows:
        item = dict(row)
        serial = _text(item.get("product_serial"))
        step_name = _text(item.get("process_step"))
        if not serial or not step_name:
            continue
        grouped.setdefault(serial, {}).setdefault(step_name, []).append(item)
    return grouped


def _load_scan_events_by_serial(snapshot_dir: Path) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    db_path = _resolve_unified_db(snapshot_dir)
    if not db_path.exists():
        return {}
    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    with _connect_readonly(db_path) as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "process_scan_events" not in tables:
            return {}
        rows = conn.execute(
            """
            SELECT product_serial, process_step, operator, scan_time, photo_uploaded_at,
                   photo_file_name, capture_session_id, event_source
            FROM process_scan_events
            ORDER BY photo_uploaded_at, id
            """
        ).fetchall()
    for row in rows:
        item = dict(row)
        serial = _text(item.get("product_serial"))
        step_name = _text(item.get("process_step"))
        if not serial or not step_name:
            continue
        grouped.setdefault(serial, {}).setdefault(step_name, []).append(item)
    return grouped


def _find_suffix_match(mapping: Dict[str, Any], serial: str) -> Optional[str]:
    target = _text(serial)
    if not target:
        return None
    if target in mapping:
        return target
    matches = [key for key in mapping if key.endswith(target) or target.endswith(key)]
    if not matches:
        return None
    # Prefer the most specific suffix match so short Kingdee serials like
    # `T310...` resolve to the full MES serial instead of a trivial key such
    # as `1` that merely shares the last character.
    matches.sort(key=len, reverse=True)
    return matches[0]


def _department_sort_key(name: str) -> tuple[int, str]:
    department = _text(name)
    for index, keyword in enumerate(DEPARTMENT_DISPLAY_ORDER):
        if keyword in department:
            return index, department
    return len(DEPARTMENT_DISPLAY_ORDER), department


def _canonical_department_name(name: str) -> str:
    department = _text(name)
    for label, keywords in CANONICAL_DEPARTMENT_GROUPS:
        if any(keyword in department for keyword in keywords):
            return label
    return department


def _preassembly_duration_ms(product_context: Optional[Dict[str, Any]]) -> int:
    if not product_context:
        return 0
    spec_text = " ".join(
        _text(product_context.get(key))
        for key in ("kingdee_spec_model", "spec_model", "specification_model")
    )
    if product_context.get("require_kingdee_spec_model") and not spec_text:
        return 0
    text = spec_text or " ".join(
        _text(product_context.get(key))
        for key in ("project_name", "type_name", "product_type", "model_number")
    )
    if not text:
        return 0
    for rule in PREASSEMBLY_TIME_RULES:
        keywords = tuple(rule.get("keywords") or ())
        if keywords and all(keyword in text for keyword in keywords):
            return _safe_int(rule.get("duration_minutes"), 0) * 60 * 1000
    return 0


def _apply_preassembly_duration(
    summaries: List[Dict[str, Any]],
    product_context: Optional[Dict[str, Any]],
) -> None:
    preassembly_ms = _preassembly_duration_ms(product_context)
    if preassembly_ms <= 0:
        return
    for item in summaries:
        if _canonical_department_name(_text(item.get("responsible_department"))) != "智能制造部-生产":
            continue
        if not item.get("completed"):
            continue
        duration_ms = _safe_int(item.get("duration_ms"), 0)
        item["base_duration_ms"] = duration_ms
        item["preassembly_duration_ms"] = preassembly_ms
        item["duration_ms"] = duration_ms + preassembly_ms
        return


def _apply_production_completion_bonus(summaries: List[Dict[str, Any]]) -> None:
    for item in summaries:
        if _canonical_department_name(_text(item.get("responsible_department"))) != "智能制造部-生产":
            continue
        if not item.get("completed"):
            continue
        duration_ms = _safe_int(item.get("duration_ms"), 0)
        item["production_completion_bonus_ms"] = PRODUCTION_COMPLETION_BONUS_MS
        item["duration_ms"] = duration_ms + PRODUCTION_COMPLETION_BONUS_MS
        return


def _photo_timestamp(row: Dict[str, Any]) -> Optional[int]:
    for key in ("uploaded_at", "captured_at"):
        value = row.get(key)
        try:
            if value is None or str(value).strip() == "":
                continue
            return int(float(value))
        except Exception:
            continue
    return None


def _scan_event_uploaded_at(row: Dict[str, Any]) -> Optional[int]:
    value = row.get("photo_uploaded_at")
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(float(value))
    except Exception:
        return None


def _scan_event_scan_time(row: Dict[str, Any]) -> Optional[int]:
    value = row.get("scan_time")
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(float(value))
    except Exception:
        return None


def summarize_serial_departments(
    expected_steps: Sequence[Dict[str, Any]],
    photos_by_step: Dict[str, List[Dict[str, Any]]],
    scan_events_by_step: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    product_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    department_map: Dict[str, List[Dict[str, Any]]] = {}
    for step in expected_steps:
        for department in step.get("responsible_departments") or []:
            if not is_countable_department(department):
                continue
            department_map.setdefault(department, []).append(step)

    summaries: List[Dict[str, Any]] = []
    for department, steps in department_map.items():
        steps = sorted(steps, key=lambda row: _safe_int(row.get("step_order"), 0))
        expected_names = [_text(step.get("name")) for step in steps if _text(step.get("name"))]
        completed_names = [name for name in expected_names if name in photos_by_step]
        missing_names = [name for name in expected_names if name not in photos_by_step]
        completed = bool(expected_names) and not missing_names

        if completed:
            step_photo_times: Dict[str, List[int]] = {}
            step_events: Dict[str, List[Dict[str, Any]]] = {}
            all_steps_have_events = True
            for name in expected_names:
                photo_rows = photos_by_step.get(name) or []
                photo_times = [_photo_timestamp(row) for row in photo_rows]
                photo_times = [item for item in photo_times if item is not None]
                if photo_times:
                    step_photo_times[name] = photo_times
                events = list((scan_events_by_step or {}).get(name) or [])
                valid_events = [
                    row for row in events
                    if _scan_event_scan_time(row) is not None and _scan_event_uploaded_at(row) is not None
                ]
                if valid_events:
                    step_events[name] = valid_events
                else:
                    all_steps_have_events = False

            first_times = []
            last_times = []
            duration_ms = 0
            step_duration_rows = []
            previous_step_end = None
            used_previous_upload_fallback = False
            can_use_stepwise_duration = True

            for name in expected_names:
                latest_event = None
                if step_events.get(name):
                    latest_event = max(
                        step_events.get(name) or [],
                        key=lambda row: _safe_int(_scan_event_uploaded_at(row), 0),
                    )
                timestamps = step_photo_times.get(name) or []

                if latest_event is not None:
                    step_start = _scan_event_scan_time(latest_event)
                    step_end = _scan_event_uploaded_at(latest_event)
                    operator = latest_event.get("operator") or ""
                elif timestamps and previous_step_end is not None:
                    step_start = previous_step_end
                    step_end = max(timestamps)
                    operator = ""
                    used_previous_upload_fallback = True
                else:
                    can_use_stepwise_duration = False
                    break

                if step_start is None or step_end is None:
                    can_use_stepwise_duration = False
                    break

                step_duration = max(0, step_end - step_start)
                duration_ms += step_duration
                first_times.append(step_start)
                last_times.append(step_end)
                step_duration_rows.append(
                    {
                        "process_step": name,
                        "operator": operator,
                        "scan_time": step_start,
                        "uploaded_at": step_end,
                        "duration_ms": step_duration,
                    }
                )
                previous_step_end = step_end

            if can_use_stepwise_duration and step_duration_rows:
                first_uploaded_at = min(first_times) if first_times else None
                last_uploaded_at = max(last_times) if last_times else None
                calculation_mode = "process_previous_upload_fallback" if used_previous_upload_fallback else "process_scan_sum"
            else:
                first_times = []
                last_times = []
                for name in expected_names:
                    timestamps = step_photo_times.get(name) or []
                    if timestamps:
                        first_times.append(min(timestamps))
                        last_times.append(max(timestamps))
                first_uploaded_at = min(first_times) if first_times else None
                last_uploaded_at = max(last_times) if last_times else None
                duration_ms = (
                    max(0, last_uploaded_at - first_uploaded_at)
                    if first_uploaded_at is not None and last_uploaded_at is not None
                    else None
                )
                step_duration_rows = []
                calculation_mode = "department_span_fallback"
        else:
            first_uploaded_at = None
            last_uploaded_at = None
            duration_ms = None
            step_duration_rows = []
            calculation_mode = "incomplete"

        summaries.append(
            {
                "responsible_department": department,
                "expected_processes": expected_names,
                "completed_processes": completed_names,
                "missing_processes": missing_names,
                "expected_process_count": len(expected_names),
                "completed_process_count": len(completed_names),
                "completed": completed,
                "completed_quantity": 1 if completed else 0,
                "first_uploaded_at": first_uploaded_at,
                "last_uploaded_at": last_uploaded_at,
                "duration_ms": duration_ms,
                "calculation_mode": calculation_mode,
                "step_duration_rows": step_duration_rows,
            }
        )

    summaries.sort(key=lambda row: row.get("responsible_department") or "")
    _apply_preassembly_duration(summaries, product_context)
    _apply_production_completion_bonus(summaries)
    return summaries


def build_department_hour_summaries_for_serials(
    snapshot_dir: Path,
    serial_numbers: Sequence[str],
    *,
    require_all_departments_complete: bool = True,
    preassembly_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Aggregate completed MES-side department hours for a serial set.

    Remote MES data remains read-only. A serial only contributes when all
    countable departments are complete by default, matching the export rule.
    Product summary views can set ``require_all_departments_complete=False`` to
    show each department's completed hours independently.
    """
    product_records = _load_product_records(snapshot_dir)
    configs = _load_product_configs(snapshot_dir)
    photos_by_serial = _load_photos_by_serial(snapshot_dir)
    scan_events_by_serial = _load_scan_events_by_serial(snapshot_dir)

    records_by_serial: Dict[str, Dict[str, Any]] = {}
    for record in product_records:
        serial = _text(record.get("product_serial"))
        if not serial:
            continue
        existing = records_by_serial.get(serial)
        if existing is None or _safe_int(record.get("scan_time"), 0) > _safe_int(existing.get("scan_time"), 0):
            records_by_serial[serial] = record

    department_durations: Dict[str, int] = {}
    completed_serial_department_durations: Dict[str, int] = {}
    matched_serial_count = 0
    completed_serial_count = 0
    completed_serials: List[str] = []
    missing_serials: List[str] = []
    completed_department_count = 0

    for raw_serial in serial_numbers:
        serial = _text(raw_serial)
        if not serial:
            continue
        record_key = _find_suffix_match(records_by_serial, serial)
        if not record_key:
            missing_serials.append(serial)
            continue
        record = records_by_serial[record_key]
        config_item = configs.get((record.get("project_name"), record.get("product_type")))
        if not config_item:
            missing_serials.append(serial)
            continue
        photo_key = _find_suffix_match(photos_by_serial, record_key) or _find_suffix_match(photos_by_serial, serial)
        if not photo_key:
            missing_serials.append(serial)
            continue

        matched_serial_count += 1
        product_context = dict(config_item)
        if preassembly_context:
            product_context.update(preassembly_context)

        department_summaries = summarize_serial_departments(
            config_item.get("steps") or [],
            photos_by_serial.get(photo_key) or {},
            scan_events_by_serial.get(photo_key) or scan_events_by_serial.get(record_key) or scan_events_by_serial.get(serial) or {},
            product_context,
        )
        if not department_summaries:
            continue

        serial_is_complete = not any(not item.get("completed") for item in department_summaries)
        if require_all_departments_complete and not serial_is_complete:
            continue

        if serial_is_complete:
            completed_serial_count += 1
            completed_serials.append(serial)

        for item in department_summaries:
            if not item.get("completed"):
                continue
            department = _canonical_department_name(_text(item.get("responsible_department")))
            duration_ms = _safe_int(item.get("duration_ms"), 0)
            if not department:
                continue
            completed_department_count += 1
            department_durations[department] = department_durations.get(department, 0) + duration_ms
            if serial_is_complete:
                completed_serial_department_durations[department] = (
                    completed_serial_department_durations.get(department, 0) + duration_ms
                )

    department_rows = [
        {
            "responsible_department": department,
            "duration_ms": department_durations.get(department, 0),
            "duration_hours": round(department_durations.get(department, 0) / MILLISECONDS_PER_HOUR, 2),
        }
        for department, _keywords in CANONICAL_DEPARTMENT_GROUPS
    ]
    realtime_total_duration_ms = sum(row["duration_ms"] for row in department_rows)
    total_duration_ms = sum(completed_serial_department_durations.get(row["responsible_department"], 0) for row in department_rows)
    if completed_department_count > 0:
        display = "，".join(
            f"{row['responsible_department']} {row['duration_hours']:.2f}h"
            for row in department_rows
        )
    else:
        display = "-"

    if completed_serial_count > 0:
        total_formula_display = f"{total_duration_ms / MILLISECONDS_PER_HOUR:.2f}h"
    else:
        total_formula_display = "-"
    return {
        "department_rows": department_rows,
        "department_work_hours_display": display,
        "department_total_duration_ms": total_duration_ms,
        "department_realtime_total_duration_ms": realtime_total_duration_ms,
        "department_total_formula_display": total_formula_display,
        "matched_serial_count": matched_serial_count,
        "completed_serial_count": completed_serial_count,
        "completed_department_count": completed_department_count,
        "completed_serials": completed_serials,
        "missing_serials": missing_serials[:20],
    }


def build_completed_work_hour_rows(
    snapshot_dir: Path,
    *,
    start_ms: int,
    end_ms: int,
    work_order_lookup: Optional[Callable[..., str]] = None,
) -> List[Dict[str, Any]]:
    product_records = _load_product_records(snapshot_dir)
    configs = _load_product_configs(snapshot_dir)
    photos_by_serial = _load_photos_by_serial(snapshot_dir)
    scan_events_by_serial = _load_scan_events_by_serial(snapshot_dir)

    work_order_cache: Dict[str, str] = {}
    rows: List[Dict[str, Any]] = []
    for record in product_records:
        serial = _text(record.get("product_serial"))
        if not serial:
            continue
        config_item = configs.get((record.get("project_name"), record.get("product_type")))
        if not config_item:
            continue
        department_summaries = summarize_serial_departments(
            config_item.get("steps") or [],
            photos_by_serial.get(serial) or {},
            scan_events_by_serial.get(serial) or {},
            config_item,
        )
        if not department_summaries or any(not item.get("completed") for item in department_summaries):
            continue
        serial_completed_at = max(int(item.get("last_uploaded_at") or 0) for item in department_summaries)
        if serial_completed_at < start_ms or serial_completed_at > end_ms:
            continue

        product_code = _text(record.get("product_code")) or _text(record.get("model_number")) or _text(config_item.get("model_number"))
        cache_key = f"{serial}\n{product_code}"
        resolved_product_code = product_code
        if cache_key not in work_order_cache:
            if work_order_lookup:
                try:
                    lookup_result = work_order_lookup(serial, product_code)
                except TypeError:
                    lookup_result = work_order_lookup(serial)
                if isinstance(lookup_result, dict):
                    work_order_cache[cache_key] = _text(lookup_result.get("work_order_no"))
                    resolved_product_code = _text(lookup_result.get("product_code")) or product_code
                else:
                    work_order_cache[cache_key] = _text(lookup_result)
            else:
                work_order_cache[cache_key] = ""
        total_duration_ms = sum(int(item.get("duration_ms") or 0) for item in department_summaries)
        for item in department_summaries:
            rows.append(
                {
                    "work_order_no": work_order_cache.get(cache_key, ""),
                    "product_code": resolved_product_code,
                    "serial_number": serial,
                    "completed_quantity": 1,
                    "department_duration_ms": int(item.get("duration_ms") or 0),
                    "responsible_department": item.get("responsible_department") or "",
                    "serial_total_duration_ms": total_duration_ms,
                    "serial_completed_at_ms": serial_completed_at,
                    "project_name": record.get("project_name") or "",
                    "product_type": record.get("product_type") or "",
                }
            )

    rows.sort(
        key=lambda row: (
            int(row.get("serial_completed_at_ms") or 0),
            row.get("work_order_no") or "",
            row.get("serial_number") or "",
            row.get("responsible_department") or "",
        )
    )
    return rows


def default_last_month_range(now: Optional[datetime] = None) -> tuple[int, int]:
    current = now or datetime.now()
    end = current.replace(hour=23, minute=59, second=59, microsecond=999000)
    start = (current - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)
