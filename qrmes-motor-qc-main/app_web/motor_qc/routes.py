"""Motor QC routes - 页面和API路由"""
from collections import defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import time
from threading import Lock
from typing import Dict, List, Union
from urllib.parse import quote, unquote
from urllib.parse import urlparse

from flask import Response, render_template, request, jsonify, session, abort, stream_with_context, send_file
from .config import MotorProjectManager
from .models import (
    MotorQCDatabase,
    InspectionRecord,
    QCProcessTask,
    QCTaskPhoto,
    QCTaskDetailItem,
    QCExperienceBucket,
    QCExperienceRule,
    QCFeedbackRecord,
    QCRulePromotion,
    build_bucket_key,
    db,
)
from qrmes_shared_core.config import config
from qrmes_shared_core.data_dir_utils import resolve_data_dir
from . import motor_qc_bp
from qrmes_shared_core.permission_guard import require_permission_value, get_current_local_user
from sqlalchemy import desc, func, or_, case

logger = logging.getLogger(__name__)
STREAM_NONCE_SESSION_KEY = "motor_qc_stream_nonce_map"
STREAM_NONCE_TTL_SECONDS = 300
STREAM_CONSUMED_NONCE_EXPIRY: Dict[str, int] = {}
INSPECT_STREAM_ACTIVE_TTL_SECONDS = int(os.getenv("MOTOR_QC_INSPECT_STREAM_ACTIVE_TTL", "600"))
INSPECT_STREAM_COOLDOWN_SECONDS = int(os.getenv("MOTOR_QC_INSPECT_STREAM_COOLDOWN", "20"))
INSPECT_STREAM_ACTIVE_KEYS: Dict[str, int] = {}
INSPECT_STREAM_COOLDOWN_UNTIL: Dict[str, int] = {}
INSPECT_STREAM_GUARD_LOCK = Lock()

# 初始化项目管理器
def _get_data_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return resolve_data_dir(
        nas_local_base_path=getattr(config, "nas_local_base_path", None),
        repo_root=repo_root,
        logger=logger,
    )


DATA_DIR = _get_data_dir()
motor_project_manager = MotorProjectManager(DATA_DIR)

# 初始化数据库
motor_qc_db = MotorQCDatabase(DATA_DIR / "motor_qc.db")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif"}
COOLING_TYPES = {"OIL", "WATER", "AIR", "NATURAL"}
BUCKET_SCOPE_LEVELS = {"global", "cooling", "platform", "model", "unknown"}

_COOLING_TYPE_KEYWORDS = {
    "OIL": ("油冷", "oil"),
    "WATER": ("水冷", "water"),
    "AIR": ("风冷", "air"),
    "NATURAL": ("自然冷却", "自然冷", "natural"),
}


def _normalize_cooling_type(value: str) -> str:
    raw = (value or "").strip().upper()
    if raw in COOLING_TYPES:
        return raw
    lowered = (value or "").strip().lower()
    for cooling_type, keywords in _COOLING_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in lowered:
                return cooling_type
    return ""


def _extract_stator_platform_from_text(*values: str) -> str:
    for value in values:
        match = re.search(r"(TZ\d{3})", (value or "").upper())
        if match:
            return match.group(1)
    return ""


def _extract_cooling_type_from_text(*values: str) -> str:
    for value in values:
        cooling_type = _normalize_cooling_type(value or "")
        if cooling_type:
            return cooling_type
    return ""


def _safe_load_project(project_id: str) -> Dict:
    if not project_id:
        return {}
    try:
        return motor_project_manager.load_project(project_id) or {}
    except Exception:
        return {}


def _build_project_id_aliases(project_id: str) -> List[str]:
    """构建项目ID别名集合，兼容 project_code / project_id / project_name 混用历史数据。"""
    raw = (project_id or "").strip()
    if not raw:
        return []

    aliases = set()

    def _add(value: str):
        text = (value or "").strip()
        if text:
            aliases.add(text)

    _add(raw)
    project = _safe_load_project(raw)
    if project:
        _add(project.get("project_id") or "")
        _add(project.get("project_code") or "")
        _add(project.get("name") or "")

    # 反向按“名称/编码等值”补齐别名，解决旧数据中 project_id=项目名 的情况
    raw_key = _normalize_step_key(raw)

    try:
        for item in motor_project_manager.list_projects():
            if not isinstance(item, dict):
                continue
            candidates = [
                str(item.get("project_id") or "").strip(),
                str(item.get("project_code") or "").strip(),
                str(item.get("name") or "").strip(),
            ]
            keys = {_normalize_step_key(x) for x in candidates if x}
            if raw_key and raw_key in keys:
                for c in candidates:
                    _add(c)
    except Exception:
        pass

    return sorted(aliases)


def _resolve_experience_context(data: Dict) -> Dict[str, str]:
    project_id = (data.get("project_id") or data.get("projectId") or "").strip()
    serial_number = (data.get("serial_number") or data.get("serial") or "").strip()
    product_type = (data.get("product_type") or data.get("productType") or "").strip()
    model_code = (data.get("model_code") or data.get("modelCode") or "").strip()
    stator_platform = (data.get("stator_platform") or data.get("statorPlatform") or "").strip().upper()
    cooling_type = _normalize_cooling_type(data.get("cooling_type") or data.get("coolingType") or "")

    project = _safe_load_project(project_id)
    project_name = (project.get("name") or project.get("projectName") or "").strip()

    if not stator_platform:
        stator_platform = _extract_stator_platform_from_text(serial_number, model_code, product_type, project_name)

    if not cooling_type:
        cooling_type = _extract_cooling_type_from_text(product_type, model_code, project_name)

    return {
        "project_id": project_id,
        "serial_number": serial_number,
        "product_type": product_type,
        "model_code": model_code,
        "stator_platform": stator_platform,
        "cooling_type": cooling_type,
    }


def _query_single_bucket(scope_level: str, stator_platform: str, cooling_type: str, model_code: str) -> QCExperienceBucket:
    query = db.session.query(QCExperienceBucket).filter_by(scope_level=scope_level, is_active=True)
    if scope_level == "model":
        query = query.filter(
            QCExperienceBucket.model_code == model_code,
            QCExperienceBucket.stator_platform == stator_platform,
            QCExperienceBucket.cooling_type == cooling_type,
        )
    elif scope_level == "platform":
        query = query.filter(
            QCExperienceBucket.stator_platform == stator_platform,
            QCExperienceBucket.cooling_type == cooling_type,
            QCExperienceBucket.model_code.is_(None),
        )
    elif scope_level == "cooling":
        query = query.filter(
            QCExperienceBucket.cooling_type == cooling_type,
            QCExperienceBucket.stator_platform.is_(None),
            QCExperienceBucket.model_code.is_(None),
        )
    else:
        # global 允许 cooling_type 为空或与上下文一致，优先精确 cooling
        query = query.filter(
            QCExperienceBucket.stator_platform.is_(None),
            QCExperienceBucket.model_code.is_(None),
        )
        if cooling_type:
            query = query.filter(
                or_(
                    QCExperienceBucket.cooling_type == cooling_type,
                    QCExperienceBucket.cooling_type.is_(None),
                )
            )
            rows = query.order_by(desc(QCExperienceBucket.cooling_type), desc(QCExperienceBucket.updated_at)).all()
            return rows[0] if rows else None
        query = query.filter(QCExperienceBucket.cooling_type.is_(None))
    return query.order_by(desc(QCExperienceBucket.updated_at)).first()


def _find_best_experience_bucket(model_code: str, stator_platform: str, cooling_type: str):
    if model_code and stator_platform and cooling_type:
        bucket = _query_single_bucket("model", stator_platform, cooling_type, model_code)
        if bucket:
            return bucket, ["model", "platform", "cooling", "global"]
    if stator_platform and cooling_type:
        bucket = _query_single_bucket("platform", stator_platform, cooling_type, model_code)
        if bucket:
            return bucket, ["platform", "cooling", "global"]
    if cooling_type:
        bucket = _query_single_bucket("cooling", stator_platform, cooling_type, model_code)
        if bucket:
            return bucket, ["cooling", "global"]
    bucket = _query_single_bucket("global", stator_platform, cooling_type, model_code)
    return bucket, ["global"]


def _get_or_create_bucket(scope_level: str, stator_platform: str, cooling_type: str, model_code: str) -> QCExperienceBucket:
    normalized_scope = (scope_level or "").strip().lower()
    normalized_platform = (stator_platform or "").strip().upper()
    normalized_cooling = _normalize_cooling_type(cooling_type)
    normalized_model = (model_code or "").strip()

    bucket_key = build_bucket_key(
        normalized_scope,
        normalized_platform,
        normalized_cooling,
        normalized_model,
    )
    bucket = db.session.query(QCExperienceBucket).filter_by(bucket_key=bucket_key).first()
    if bucket:
        if not bucket.is_active:
            bucket.is_active = True
        return bucket

    if normalized_scope in {"global", "unknown"}:
        normalized_platform = ""
        normalized_cooling = ""
        normalized_model = ""
    elif normalized_scope == "cooling":
        normalized_platform = ""
        normalized_model = ""
    elif normalized_scope == "platform":
        normalized_model = ""

    bucket = QCExperienceBucket(
        scope_level=normalized_scope,
        bucket_key=bucket_key,
        stator_platform=normalized_platform or None,
        cooling_type=normalized_cooling or None,
        model_code=normalized_model or None,
        is_active=True,
    )
    db.session.add(bucket)
    db.session.flush()
    return bucket


def _split_folder_display_name(folder_name: str) -> str:
    if not folder_name:
        return ""
    if "_" not in folder_name:
        return folder_name
    prefix, suffix = folder_name.rsplit("_", 1)
    if prefix and suffix and re.fullmatch(r"[A-Za-z0-9.\-]+", suffix):
        return prefix
    return folder_name


def _normalize_name_key(value: str) -> str:
    if value is None:
        return ""
    normalized = str(value).strip().lower()
    normalized = re.sub(r"[\s._-]+", "", normalized)
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)
    normalized = normalized.replace("_", "")
    return normalized


def _folder_matches_name(folder_name: str, expected_name: str) -> bool:
    folder_key = _normalize_name_key(folder_name)
    expected_key = _normalize_name_key(expected_name)
    if not folder_key or not expected_key:
        return False
    if folder_key == expected_key:
        return True
    # 兼容目录格式: {name}_{projectCode/model}
    return folder_key.startswith(expected_key)


def _normalize_step_key(value: str) -> str:
    if value is None:
        return ""
    normalized = str(value).strip().lower()
    normalized = re.sub(r"[\s_-]+", "", normalized)
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)
    return normalized


def _normalize_product_type_key(value: str) -> str:
    return _normalize_name_key(value or "")


def _map_product_type_to_config(project: Dict, raw_product_type: str) -> str:
    """将照片目录推断出的产品类型映射到项目配置中的标准类型名称。"""
    normalized_raw = (raw_product_type or "").strip()
    if not normalized_raw:
        return ""

    configured_types: List[str] = []
    for step in (project.get("processes") or []):
        if not isinstance(step, dict):
            continue
        step_type = (step.get("product_type") or "").strip()
        if step_type:
            configured_types.append(step_type)

    if not configured_types:
        return normalized_raw

    unique_types = list(dict.fromkeys(configured_types))
    if normalized_raw in unique_types:
        return normalized_raw

    raw_key = _normalize_product_type_key(normalized_raw)
    if not raw_key:
        return normalized_raw

    # 优先精确 key 匹配
    for configured in unique_types:
        if _normalize_product_type_key(configured) == raw_key:
            return configured

    # 次优：包含关系匹配（解决“油泵转子总成” vs “油泵电机转子总成”）
    contains_candidates: List[str] = []
    for configured in unique_types:
        configured_key = _normalize_product_type_key(configured)
        if not configured_key:
            continue
        if raw_key in configured_key or configured_key in raw_key:
            contains_candidates.append(configured)

    if len(contains_candidates) == 1:
        return contains_candidates[0]
    if len(contains_candidates) > 1:
        # 选择 key 长度差最小的候选，尽量避免误选
        contains_candidates.sort(
            key=lambda item: abs(len(_normalize_product_type_key(item)) - len(raw_key))
        )
        return contains_candidates[0]

    # 最后兜底：相似度映射（用于“油泵转子总成” -> “油泵电机转子总成”）
    best_type = ""
    best_score = 0.0
    for configured in unique_types:
        configured_key = _normalize_product_type_key(configured)
        if not configured_key:
            continue
        score = SequenceMatcher(None, raw_key, configured_key).ratio()
        if score > best_score:
            best_score = score
            best_type = configured

    if best_type and best_score >= 0.70:
        return best_type

    return normalized_raw


def _extract_process_from_filename(file_name: str, product_serial: str) -> str:
    stem = Path(file_name).stem
    prefix = f"{product_serial}_"
    if not stem.startswith(prefix):
        return ""
    remainder = stem[len(prefix):]
    if "_" not in remainder:
        return remainder

    parts = remainder.split("_")
    if len(parts) >= 4 and parts[-1].isdigit() and parts[-2].isdigit() and parts[-3].isdigit():
        if len(parts[-3]) == 8 and len(parts[-2]) == 6:
            return "_".join(parts[:-3])
    if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
        if len(parts[-2]) == 8 and len(parts[-1]) == 6:
            return "_".join(parts[:-2])
    if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) == 14:
        return "_".join(parts[:-1])

    return remainder.rsplit("_", 1)[0]


def _get_project_photo_dirs(project: Dict) -> List[Path]:
    photos_root = DATA_DIR / "picture"
    if not photos_root.exists():
        return []

    project_name = (
        project.get("name")
        or project.get("projectName")
        or project.get("project_id")
        or ""
    ).strip()
    if not project_name:
        return []

    dirs: List[Path] = []
    for project_dir in photos_root.iterdir():
        if not project_dir.is_dir():
            continue
        display_name = _split_folder_display_name(project_dir.name)
        if (
            _folder_matches_name(project_dir.name, project_name)
            or _folder_matches_name(display_name, project_name)
        ):
            dirs.append(project_dir)
    return dirs


def _collect_project_motors(project: Dict, product_type: str = "") -> List[Dict]:
    serial_stats: Dict[str, Dict] = {}
    normalized_product_type = (product_type or "").strip()

    for project_dir in _get_project_photo_dirs(project):
        for product_dir in project_dir.iterdir():
            if not product_dir.is_dir():
                continue

            product_display = _split_folder_display_name(product_dir.name)
            if normalized_product_type:
                if not (
                    _folder_matches_name(product_display, normalized_product_type)
                    or _folder_matches_name(product_dir.name, normalized_product_type)
                ):
                    continue

            for serial_dir in product_dir.iterdir():
                if not serial_dir.is_dir():
                    continue

                serial = serial_dir.name
                stats = serial_stats.setdefault(serial, {
                    "serial_number": serial,
                    "total_photos": 0,
                    "completed_processes": 0,
                    "processes": set(),
                    "product_types": set(),
                    "last_photo_time": None,
                })
                stats["product_types"].add(product_display or product_dir.name)

                for photo_file in serial_dir.iterdir():
                    if photo_file.suffix.lower() not in IMAGE_EXTENSIONS:
                        continue
                    stats["total_photos"] += 1

                    process_name = _extract_process_from_filename(photo_file.name, serial)
                    process_key = _normalize_step_key(process_name)
                    if process_key:
                        stats["processes"].add(process_key)

                    try:
                        ts = datetime.fromtimestamp(photo_file.stat().st_mtime)
                        if stats["last_photo_time"] is None or ts > stats["last_photo_time"]:
                            stats["last_photo_time"] = ts
                    except OSError:
                        continue

    motors: List[Dict] = []
    for item in serial_stats.values():
        motors.append({
            "serial_number": item["serial_number"],
            "total_photos": item["total_photos"],
            "completed_processes": len(item["processes"]),
            "product_types": sorted(item["product_types"]),
            "last_photo_time": item["last_photo_time"].isoformat() if item["last_photo_time"] else None,
        })

    motors.sort(key=lambda x: x["last_photo_time"] or "", reverse=True)
    return motors


def _collect_serial_photos_by_process(
    project: Dict,
    serial_number: str,
    product_type: str = ""
) -> Dict[str, List[Path]]:
    photos_by_process: Dict[str, List[Path]] = defaultdict(list)
    normalized_product_type = (product_type or "").strip()

    for project_dir in _get_project_photo_dirs(project):
        for product_dir in project_dir.iterdir():
            if not product_dir.is_dir():
                continue

            product_display = _split_folder_display_name(product_dir.name)
            if normalized_product_type:
                if not (
                    _folder_matches_name(product_display, normalized_product_type)
                    or _folder_matches_name(product_dir.name, normalized_product_type)
                ):
                    continue

            serial_dir = product_dir / serial_number
            if not serial_dir.exists() or not serial_dir.is_dir():
                continue

            for photo_file in serial_dir.iterdir():
                if photo_file.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                process_name = _extract_process_from_filename(photo_file.name, serial_number)
                process_key = _normalize_step_key(process_name)
                if not process_key:
                    continue
                photos_by_process[process_key].append(photo_file)

    for key in photos_by_process:
        photos_by_process[key].sort(key=lambda p: p.stat().st_mtime)
    return photos_by_process


def _collect_serial_product_type_stats(project: Dict, serial_number: str) -> Dict[str, int]:
    """统计某序列号在各产品类型目录中的照片数量"""
    stats: Dict[str, int] = {}

    for project_dir in _get_project_photo_dirs(project):
        for product_dir in project_dir.iterdir():
            if not product_dir.is_dir():
                continue

            serial_dir = product_dir / serial_number
            if not serial_dir.exists() or not serial_dir.is_dir():
                continue

            product_display = _split_folder_display_name(product_dir.name) or product_dir.name
            image_count = 0
            for photo_file in serial_dir.iterdir():
                if photo_file.suffix.lower() in IMAGE_EXTENSIONS:
                    image_count += 1
            stats[product_display] = stats.get(product_display, 0) + image_count

    return stats


def _infer_product_type_by_process_overlap(
    project: Dict,
    serial_number: str,
    type_stats: Dict[str, int],
) -> str:
    """当产品类型候选计数接近时，按工序照片与配置工序的重合度推断类型。"""
    if not type_stats:
        return ""

    photos_by_process = _collect_serial_photos_by_process(project, serial_number, "")
    photo_keys = set(photos_by_process.keys())
    if not photo_keys:
        return ""

    config_type_photo_counts: Dict[str, int] = {}
    for raw_type, count in type_stats.items():
        mapped = _map_product_type_to_config(project, raw_type)
        if not mapped:
            continue
        current = config_type_photo_counts.get(mapped, 0)
        if count > current:
            config_type_photo_counts[mapped] = count

    best_type = ""
    best_score = (0, 0, 0.0)  # overlap, photo_count, coverage_ratio
    for config_type, photo_count in config_type_photo_counts.items():
        configured_steps = _build_configured_steps(project, config_type)
        step_keys = {
            _normalize_step_key((step.get("name") or "").strip())
            for step in configured_steps
            if isinstance(step, dict)
        }
        step_keys.discard("")
        if not step_keys:
            continue

        overlap = len(photo_keys.intersection(step_keys))
        if overlap <= 0:
            continue

        coverage_ratio = overlap / max(len(step_keys), 1)
        score = (overlap, photo_count, coverage_ratio)
        if score > best_score:
            best_score = score
            best_type = config_type

    return best_type


def _resolve_effective_product_type(project: Dict, serial_number: str, requested_product_type: str = "") -> str:
    """当未显式选择产品类型时，按序列号照片目录自动推断产品类型"""
    normalized_requested = (requested_product_type or "").strip()
    if normalized_requested:
        return _map_product_type_to_config(project, normalized_requested)

    if not serial_number:
        return ""

    stats = _collect_serial_product_type_stats(project, serial_number)
    if not stats:
        return ""

    if len(stats) == 1:
        return _map_product_type_to_config(project, next(iter(stats.keys())))

    ranked = sorted(stats.items(), key=lambda item: item[1], reverse=True)
    if len(ranked) >= 2 and ranked[0][1] > ranked[1][1]:
        return _map_product_type_to_config(project, ranked[0][0])

    overlap_inferred = _infer_product_type_by_process_overlap(project, serial_number, stats)
    if overlap_inferred:
        return overlap_inferred

    return ""


def _build_configured_steps(project: Dict, product_type: str = "") -> List[Dict]:
    """按产品类型过滤并按工序名去重，避免跨产品类型出现重复工序"""
    normalized_type = (product_type or "").strip()
    configured_steps = sorted(
        [p for p in (project.get("processes") or []) if isinstance(p, dict) and p.get("name")],
        key=lambda x: int(x.get("order") or 0)
    )

    if normalized_type:
        configured_steps = [
            p for p in configured_steps
            if (p.get("product_type") or "").strip() in ("", normalized_type)
        ]

    selected_by_key: Dict[str, Dict] = {}
    selected_score: Dict[str, tuple] = {}

    for idx, step in enumerate(configured_steps):
        step_name = (step.get("name") or "").strip()
        step_key = _normalize_step_key(step_name)
        if not step_key:
            continue

        step_type = (step.get("product_type") or "").strip()
        order_value = int(step.get("order") or 0)
        if normalized_type:
            if step_type == normalized_type:
                type_rank = 0
            elif not step_type:
                type_rank = 1
            else:
                type_rank = 2
        else:
            type_rank = 0

        score = (type_rank, order_value, idx)
        if step_key not in selected_by_key or score < selected_score[step_key]:
            selected_by_key[step_key] = step
            selected_score[step_key] = score

    deduplicated = list(selected_by_key.values())
    deduplicated.sort(key=lambda x: int(x.get("order") or 0))
    return deduplicated


def _load_project_or_404(project_id: str) -> Dict:
    project = motor_project_manager.load_project(project_id)
    if not project:
        for alias in _build_project_id_aliases(project_id):
            project = _safe_load_project(alias)
            if project:
                break
    if not project:
        abort(404)
    return project


def _is_path_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _build_photo_view_url(photo_path: Path) -> str:
    try:
        relative_path = photo_path.resolve().relative_to(DATA_DIR.resolve())
        safe_path = str(relative_path).replace(os.sep, "/")
    except Exception:
        logger.warning("[motor-qc] skip photo url outside DATA_DIR: %s", photo_path)
        return ""
    return f"/motor-qc/api/photos/view?path={quote(safe_path)}"


def _build_process_photo_items(process_photos: List[Path]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for photo_path in process_photos:
        items.append({
            "name": photo_path.name,
            "url": _build_photo_view_url(photo_path),
        })
    return items


def _seed_project_tasks_from_existing_photos(
    project_id: str,
    *,
    serial_filter: str = "",
    process_filter: str = "",
    product_type_filter: str = "",
    max_photos: int = 8000,
) -> Dict[str, int]:
    """从历史照片回填QC任务（仅当前项目）。"""
    project = motor_project_manager.load_project(project_id)
    if not project:
        return {"seeded_tasks": 0, "seeded_photos": 0}

    normalized_serial = (serial_filter or "").strip()
    normalized_process = _normalize_step_key(process_filter or "")
    normalized_product_type = (product_type_filter or "").strip()

    task_service = QCTaskService()
    seeded_photos = 0
    seeded_tasks = 0
    seen_task_keys = set()

    for project_dir in _get_project_photo_dirs(project):
        for product_dir in project_dir.iterdir():
            if not product_dir.is_dir():
                continue

            product_display = _split_folder_display_name(product_dir.name) or product_dir.name
            mapped_product_type = _map_product_type_to_config(project, product_display)

            if normalized_product_type:
                if not (
                    _folder_matches_name(product_display, normalized_product_type)
                    or _folder_matches_name(product_dir.name, normalized_product_type)
                    or _folder_matches_name(mapped_product_type, normalized_product_type)
                ):
                    continue

            step_name_map = {
                _normalize_step_key((step.get("name") or "").strip()): (step.get("name") or "").strip()
                for step in _build_configured_steps(project, mapped_product_type)
                if isinstance(step, dict)
            }

            for serial_dir in product_dir.iterdir():
                if not serial_dir.is_dir():
                    continue
                serial = serial_dir.name
                if normalized_serial and serial != normalized_serial:
                    continue

                for photo_file in serial_dir.iterdir():
                    if photo_file.suffix.lower() not in IMAGE_EXTENSIONS:
                        continue

                    raw_process = _extract_process_from_filename(photo_file.name, serial)
                    step_key = _normalize_step_key(raw_process)
                    if not step_key:
                        continue
                    if normalized_process and step_key != normalized_process:
                        continue

                    process_name = step_name_map.get(step_key) or raw_process or step_key
                    try:
                        task = task_service.upsert_task_for_photo(
                            project_id=project_id,
                            serial_number=serial,
                            process_name=process_name,
                            photo_path=str(photo_file),
                            product_type=mapped_product_type or product_display,
                            auto_commit=False,
                            reset_status=False,
                        )
                        seeded_photos += 1
                        if task and task.task_key and task.task_key not in seen_task_keys:
                            seen_task_keys.add(task.task_key)
                            seeded_tasks += 1
                    except Exception:
                        db.session.rollback()
                        logger.exception(
                            "[task-seed] upsert failed project=%s serial=%s process=%s file=%s",
                            project_id,
                            serial,
                            process_name,
                            photo_file,
                        )

                    if seeded_photos >= max_photos:
                        db.session.commit()
                        return {"seeded_tasks": seeded_tasks, "seeded_photos": seeded_photos}

    db.session.commit()
    return {"seeded_tasks": seeded_tasks, "seeded_photos": seeded_photos}


def _task_overdue_level(updated_at: datetime) -> str:
    if not updated_at:
        return "none"
    elapsed_minutes = (datetime.utcnow() - updated_at).total_seconds() / 60.0
    if elapsed_minutes >= 30:
        return "danger"
    if elapsed_minutes >= 10:
        return "warning"
    return "none"


def _dt_to_iso(value):
    if not value:
        return None
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def _parse_task_filter_date(date_text: str, field_name: str):
    text = (date_text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field_name} 日期格式错误，应为 YYYY-MM-DD") from exc


def _apply_task_date_filters(query, start_dt, end_dt):
    if start_dt is not None:
        query = query.filter(QCProcessTask.updated_at >= start_dt)
    if end_dt is not None:
        # 结束日期按“当日 23:59:59”理解，转成 < 次日 00:00:00
        query = query.filter(QCProcessTask.updated_at < (end_dt + timedelta(days=1)))
    return query


def _serialize_qc_task(task: QCProcessTask, with_children: bool = False) -> Dict:
    payload = task.to_dict()
    payload["overdue_level"] = _task_overdue_level(task.updated_at)
    if not with_children:
        return payload

    photos = (
        db.session.query(QCTaskPhoto)
        .filter(QCTaskPhoto.task_id == task.id)
        .order_by(desc(QCTaskPhoto.captured_at), desc(QCTaskPhoto.id))
        .all()
    )
    detail_items = (
        db.session.query(QCTaskDetailItem)
        .filter(QCTaskDetailItem.task_id == task.id)
        .order_by(QCTaskDetailItem.id.asc())
        .all()
    )
    photo_rows = []
    photo_by_id = {}
    for item in photos:
        row = item.to_dict()
        if row.get("photo_path"):
            row["view_url"] = _build_photo_view_url(Path(row["photo_path"]))
        else:
            row["view_url"] = ""
        photo_rows.append(row)
        photo_by_id[item.id] = row

    detail_rows = []
    detail_summary_map = {}
    best_result = payload.get("best_result_json") or {}
    details_from_summary = best_result.get("details") or []
    if isinstance(details_from_summary, list):
        for row in details_from_summary:
            if not isinstance(row, dict):
                continue
            detail_key = normalize_detail_key(str(row.get("detail_key") or ""))
            if not detail_key:
                continue
            reason = str(row.get("best_reason") or row.get("reason") or "").strip()
            if reason:
                detail_summary_map[detail_key] = reason
    confirmed_detail_count = 0
    for item in detail_items:
        row = item.to_dict()
        best_photo = photo_by_id.get(item.best_photo_id)
        row["best_photo_url"] = (best_photo or {}).get("view_url", "")
        row["best_photo_name"] = (best_photo or {}).get("photo_name", "")
        detail_key = normalize_detail_key(str(row.get("detail_key") or ""))
        ai_reason = detail_summary_map.get(detail_key, "")
        if not ai_reason and best_photo:
            analysis_json = (best_photo or {}).get("analysis_json") or {}
            if isinstance(analysis_json, dict):
                ai_reason = str(analysis_json.get("analysis") or analysis_json.get("summary") or "").strip()
        if not ai_reason:
            for photo_row in photo_rows:
                analysis_json = (photo_row or {}).get("analysis_json") or {}
                if not isinstance(analysis_json, dict):
                    continue
                ai_reason = str(analysis_json.get("analysis") or analysis_json.get("summary") or "").strip()
                if ai_reason:
                    break
        if not ai_reason:
            ai_reason = str(best_result.get("primary_reason") or best_result.get("summary") or "").strip()
        row["ai_reason"] = ai_reason
        if (row.get("confirmed_status") or "").strip():
            confirmed_detail_count += 1
        detail_rows.append(row)

    payload["photos"] = photo_rows
    payload["detail_items"] = detail_rows
    payload["detail_total"] = len(detail_rows)
    payload["detail_confirmed"] = confirmed_detail_count
    return payload


def _resolve_inspector_id() -> str:
    inspector_id = None
    try:
        user = get_current_local_user()
        if user:
            inspector_id = user.synology_username
    except Exception:
        inspector_id = None

    if not inspector_id:
        inspector_id = session.get("username") or session.get("user_id") or "unknown"
    return inspector_id


def _issue_stream_nonce(project_id: str) -> str:
    nonce_map = session.get(STREAM_NONCE_SESSION_KEY)
    if not isinstance(nonce_map, dict):
        nonce_map = {}
    nonce = secrets.token_urlsafe(24)
    binding = _build_stream_nonce_binding()
    STREAM_CONSUMED_NONCE_EXPIRY.pop(nonce, None)
    nonce_map[str(project_id)] = {
        "nonce": nonce,
        "issued_at": int(time.time()),
        "binding": binding,
    }
    session[STREAM_NONCE_SESSION_KEY] = nonce_map
    session.modified = True
    return nonce


def _cleanup_consumed_nonce_cache(now_ts: int) -> None:
    expired = [token for token, expiry in STREAM_CONSUMED_NONCE_EXPIRY.items() if int(expiry or 0) <= now_ts]
    for token in expired:
        STREAM_CONSUMED_NONCE_EXPIRY.pop(token, None)


def _build_inspect_stream_guard_key(project_id: str, serial_number: str, product_type: str = "") -> str:
    project_key = str(project_id or "").strip().lower()
    serial_key = str(serial_number or "").strip().lower()
    type_key = str(product_type or "").strip().lower()
    return f"{project_key}|{serial_key}|{type_key}"


def _cleanup_inspect_stream_guard_cache(now_ts: int) -> None:
    active_expired = [
        key
        for key, start_ts in INSPECT_STREAM_ACTIVE_KEYS.items()
        if int(start_ts or 0) <= 0 or (now_ts - int(start_ts or 0)) > INSPECT_STREAM_ACTIVE_TTL_SECONDS
    ]
    for key in active_expired:
        INSPECT_STREAM_ACTIVE_KEYS.pop(key, None)

    cooldown_expired = [key for key, expiry in INSPECT_STREAM_COOLDOWN_UNTIL.items() if int(expiry or 0) <= now_ts]
    for key in cooldown_expired:
        INSPECT_STREAM_COOLDOWN_UNTIL.pop(key, None)


def _acquire_inspect_stream_guard(guard_key: str) -> Dict[str, Union[int, str, bool]]:
    now = int(time.time())
    with INSPECT_STREAM_GUARD_LOCK:
        _cleanup_inspect_stream_guard_cache(now)

        active_since = int(INSPECT_STREAM_ACTIVE_KEYS.get(guard_key, 0) or 0)
        if active_since:
            retry_after = max(1, INSPECT_STREAM_ACTIVE_TTL_SECONDS - max(0, now - active_since))
            return {"ok": False, "reason": "active", "retry_after": retry_after}

        cooldown_until = int(INSPECT_STREAM_COOLDOWN_UNTIL.get(guard_key, 0) or 0)
        if cooldown_until > now:
            retry_after = max(1, cooldown_until - now)
            return {"ok": False, "reason": "cooldown", "retry_after": retry_after}

        INSPECT_STREAM_ACTIVE_KEYS[guard_key] = now
        return {"ok": True, "reason": "", "retry_after": 0}


def _release_inspect_stream_guard(guard_key: str, *, apply_cooldown: bool = True) -> None:
    now = int(time.time())
    with INSPECT_STREAM_GUARD_LOCK:
        INSPECT_STREAM_ACTIVE_KEYS.pop(guard_key, None)
        if apply_cooldown and INSPECT_STREAM_COOLDOWN_SECONDS > 0:
            INSPECT_STREAM_COOLDOWN_UNTIL[guard_key] = now + INSPECT_STREAM_COOLDOWN_SECONDS


def _build_stream_nonce_binding() -> str:
    """构建 nonce 会话绑定指纹，降低 token 跨上下文重放风险。"""
    user_id = str(session.get("user_id") or "")
    username = str(session.get("username") or "")
    user_agent = str(request.headers.get("User-Agent") or "")
    raw = f"{user_id}|{username}|{user_agent}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_stream_nonce(project_id: str, nonce: str, *, consume: bool = False) -> bool:
    if not nonce:
        return False
    now = int(time.time())
    _cleanup_consumed_nonce_cache(now)
    if int(STREAM_CONSUMED_NONCE_EXPIRY.get(nonce, 0) or 0) > now:
        return False

    nonce_map = session.get(STREAM_NONCE_SESSION_KEY)
    if not isinstance(nonce_map, dict):
        return False
    payload = nonce_map.get(str(project_id))
    if not payload:
        return False

    if not isinstance(payload, dict):
        return False
    expected = str(payload.get("nonce") or "")
    issued_at = int(payload.get("issued_at") or 0)
    expected_binding = str(payload.get("binding") or "")
    if not expected_binding:
        return False
    current_binding = _build_stream_nonce_binding()
    if not hmac.compare_digest(expected_binding, current_binding):
        return False

    if issued_at and (now - issued_at > STREAM_NONCE_TTL_SECONDS):
        nonce_map.pop(str(project_id), None)
        session[STREAM_NONCE_SESSION_KEY] = nonce_map
        session.modified = True
        return False

    matched = hmac.compare_digest(str(expected), str(nonce))
    if matched and consume:
        STREAM_CONSUMED_NONCE_EXPIRY[str(nonce)] = now + STREAM_NONCE_TTL_SECONDS
        nonce_map.pop(str(project_id), None)
        session[STREAM_NONCE_SESSION_KEY] = nonce_map
        session.modified = True
    return matched


def _is_request_same_origin() -> bool:
    expected_origin = f"{request.scheme}://{request.host}"

    origin = (request.headers.get("Origin") or "").strip()
    if origin:
        if origin.rstrip("/") != expected_origin.rstrip("/"):
            return False

    referer = (request.headers.get("Referer") or "").strip()
    if referer:
        parsed = urlparse(referer)
        if not parsed.scheme or not parsed.netloc:
            return False
        referer_origin = f"{parsed.scheme}://{parsed.netloc}"
        if referer_origin.rstrip("/") != expected_origin.rstrip("/"):
            return False

    # 至少需要一个来源头，避免“只带 Cookie+nonce 的盲调用”。
    return bool(origin or referer)


def _is_inspect_stream_referer_valid(project_id: str) -> bool:
    """限制 SSE 调用来源页面，降低站内误触发/滥用风险。"""
    referer = (request.headers.get("Referer") or "").strip()
    if not referer:
        # 部分浏览器/代理会剥离 Referer；此时仅靠 nonce 放行。
        return True

    parsed = urlparse(referer)
    if not parsed.path:
        return False

    normalized_path = unquote(parsed.path).rstrip("/")
    expected_path = f"/motor-qc/inspect/{project_id}".rstrip("/")
    return normalized_path == expected_path

@motor_qc_bp.route('/')
@require_permission_value('web:run_qc')
def index():
    """项目列表页"""
    return render_template('motor_qc/index.html')


@motor_qc_bp.route('/inspect/<project_id>')
@require_permission_value('web:run_qc')
def inspect_project(project_id):
    """项目质检详情页"""
    project = _load_project_or_404(project_id)
    inspect_stream_nonce = _issue_stream_nonce(project_id)
    return render_template(
        'motor_qc/inspect.html',
        project_id=project_id,
        inspect_stream_nonce=inspect_stream_nonce,
    )


@motor_qc_bp.route('/tasks/<project_id>')
@require_permission_value('web:run_qc')
def inspect_tasks(project_id):
    """QC任务中心页（异步任务处理）"""
    project = _load_project_or_404(project_id)
    return render_template(
        'motor_qc/tasks.html',
        project_id=project_id,
        project_name=(project.get("name") or project_id),
        project_optional=False,
    )


@motor_qc_bp.route('/tasks')
@require_permission_value('web:run_qc')
def inspect_tasks_without_project():
    """QC任务中心页（边缘工位入口：启动时不指定项目）。"""
    requested_project_id = str(request.args.get("project_id") or "").strip()
    project_name = ""
    if requested_project_id:
        project = _safe_load_project(requested_project_id)
        if project:
            requested_project_id = str(project.get("project_id") or requested_project_id).strip()
            project_name = str(project.get("name") or requested_project_id).strip()
    return render_template(
        'motor_qc/tasks.html',
        project_id=requested_project_id,
        project_name=project_name,
        project_optional=True,
    )


@motor_qc_bp.route('/review/<project_id>')
@require_permission_value('web:run_qc')
def manual_review_page(project_id):
    """人工确认页（聚焦识别对/错与人工复核）。"""
    project = _load_project_or_404(project_id)
    return render_template(
        'motor_qc/review.html',
        project_id=project_id,
        project_name=(project.get("name") or project_id),
    )


@motor_qc_bp.route('/storage-check/<project_id>')
@require_permission_value('web:run_qc')
def storage_check_page(project_id):
    """QC 存储自检页（按序列号核对任务/照片落库状态）"""
    project = _load_project_or_404(project_id)
    return render_template(
        'motor_qc/storage_check.html',
        project_id=project_id,
        project_name=(project.get("name") or project_id),
    )


@motor_qc_bp.route('/api/health')
def health():
    """健康检查"""
    return jsonify({"status": "ok", "module": "motor_qc"})

@motor_qc_bp.route('/api/projects', methods=['GET'])
@require_permission_value('web:run_qc')
def list_projects():
    """获取所有电机项目"""
    projects = motor_project_manager.list_projects()
    return jsonify({"projects": projects})

@motor_qc_bp.route('/api/projects/<project_id>', methods=['GET'])
@require_permission_value('web:run_qc')
def get_project(project_id):
    """获取项目配置"""
    project = motor_project_manager.load_project(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project)


@motor_qc_bp.route('/api/projects/<project_id>/motors', methods=['GET'])
@require_permission_value('web:run_qc')
def list_project_motors(project_id):
    """列出项目下可质检的产品序列号"""
    project = _load_project_or_404(project_id)
    product_type = (request.args.get("productType") or "").strip()
    motors = _collect_project_motors(project, product_type)
    return jsonify({
        "success": True,
        "project_id": project_id,
        "total": len(motors),
        "motors": motors,
    })


@motor_qc_bp.route('/api/tasks/<int:task_id>', methods=['GET'])
@require_permission_value('web:run_qc')
def get_qc_task(task_id):
    task = db.session.query(QCProcessTask).filter_by(id=task_id).first()
    if not task:
        return jsonify({"success": False, "error": "任务不存在"}), 404
    return jsonify({
        "success": True,
        "task": _serialize_qc_task(task, with_children=True),
    })


@motor_qc_bp.route('/api/projects/<project_id>/tasks', methods=['GET'])
@require_permission_value('web:run_qc')
def list_project_tasks(project_id):
    status = (request.args.get("status") or "").strip().lower()
    serial = (request.args.get("serial") or "").strip()
    process_name = (request.args.get("process") or "").strip()
    product_type = (request.args.get("productType") or "").strip()
    date_from_text = (request.args.get("dateFrom") or "").strip()
    date_to_text = (request.args.get("dateTo") or "").strip()
    include_children = str(request.args.get("include_children") or "").strip().lower() in ("1", "true", "yes")
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = min(200, max(1, request.args.get("per_page", 50, type=int) or 50))

    try:
        date_from = _parse_task_filter_date(date_from_text, "dateFrom")
        date_to = _parse_task_filter_date(date_to_text, "dateTo")
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    if date_from and date_to and date_from > date_to:
        return jsonify({"success": False, "error": "dateFrom 不能晚于 dateTo"}), 400

    project_aliases = _build_project_id_aliases(project_id)
    if not project_aliases:
        project_aliases = [project_id]

    query = db.session.query(QCProcessTask).filter(QCProcessTask.project_id.in_(project_aliases))
    stats_query = db.session.query(QCProcessTask).filter(QCProcessTask.project_id.in_(project_aliases))
    if status:
        query = query.filter(QCProcessTask.status == status)
    if serial:
        query = query.filter(QCProcessTask.serial_number == serial)
        stats_query = stats_query.filter(QCProcessTask.serial_number == serial)
    if process_name:
        query = query.filter(QCProcessTask.process_name == process_name)
        stats_query = stats_query.filter(QCProcessTask.process_name == process_name)
    if product_type:
        query = query.filter(QCProcessTask.product_type == product_type)
        stats_query = stats_query.filter(QCProcessTask.product_type == product_type)
    query = _apply_task_date_filters(query, date_from, date_to)
    stats_query = _apply_task_date_filters(stats_query, date_from, date_to)

    total = query.count()

    seed_if_empty = str(request.args.get("seed_if_empty") or "1").strip().lower() in ("1", "true", "yes")
    seeded_payload = {"seeded_tasks": 0, "seeded_photos": 0}
    should_seed = total == 0 and seed_if_empty and not status
    if total == 0 and seed_if_empty and status:
        logger.info(
            "[task-seed] skip because status filter is active: project=%s status=%s",
            project_id,
            status,
        )
    if should_seed:
        try:
            seeded_payload = _seed_project_tasks_from_existing_photos(
                project_id,
                serial_filter=serial,
                process_filter=process_name,
                product_type_filter=product_type,
            )
        except Exception:
            db.session.rollback()
            logger.exception("[task-seed] failed project=%s", project_id)
        query = db.session.query(QCProcessTask).filter(QCProcessTask.project_id.in_(project_aliases))
        stats_query = db.session.query(QCProcessTask).filter(QCProcessTask.project_id.in_(project_aliases))
        if status:
            query = query.filter(QCProcessTask.status == status)
        if serial:
            query = query.filter(QCProcessTask.serial_number == serial)
            stats_query = stats_query.filter(QCProcessTask.serial_number == serial)
        if process_name:
            query = query.filter(QCProcessTask.process_name == process_name)
            stats_query = stats_query.filter(QCProcessTask.process_name == process_name)
        if product_type:
            query = query.filter(QCProcessTask.product_type == product_type)
            stats_query = stats_query.filter(QCProcessTask.product_type == product_type)
        query = _apply_task_date_filters(query, date_from, date_to)
        stats_query = _apply_task_date_filters(stats_query, date_from, date_to)
        total = query.count()
    tasks = (
        query.order_by(desc(QCProcessTask.updated_at), desc(QCProcessTask.id))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    status_counts = (
        stats_query
        .with_entities(QCProcessTask.status, func.count(QCProcessTask.id))
        .group_by(QCProcessTask.status)
        .all()
    )
    counts_payload = {str(item[0] or "pending"): int(item[1] or 0) for item in status_counts}

    return jsonify({
        "success": True,
        "project_id": project_id,
        "total": total,
        "page": page,
        "per_page": per_page,
        "seeded_tasks": int(seeded_payload.get("seeded_tasks") or 0),
        "seeded_photos": int(seeded_payload.get("seeded_photos") or 0),
        "status_counts": counts_payload,
        "tasks": [_serialize_qc_task(task, with_children=include_children) for task in tasks],
    })


@motor_qc_bp.route('/api/projects/<project_id>/task-options', methods=['GET'])
@require_permission_value('web:run_qc')
def list_project_task_options(project_id):
    """返回任务筛选候选项（支持输入+下拉建议）。"""
    status = (request.args.get("status") or "").strip().lower()
    serial = (request.args.get("serial") or "").strip()
    process_name = (request.args.get("process") or "").strip()
    product_type = (request.args.get("productType") or "").strip()
    date_from_text = (request.args.get("dateFrom") or "").strip()
    date_to_text = (request.args.get("dateTo") or "").strip()
    q_serial = (request.args.get("q_serial") or "").strip()
    q_process = (request.args.get("q_process") or "").strip()
    q_product_type = (request.args.get("q_product_type") or "").strip()
    limit = min(300, max(20, request.args.get("limit", 120, type=int) or 120))

    try:
        date_from = _parse_task_filter_date(date_from_text, "dateFrom")
        date_to = _parse_task_filter_date(date_to_text, "dateTo")
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    if date_from and date_to and date_from > date_to:
        return jsonify({"success": False, "error": "dateFrom 不能晚于 dateTo"}), 400

    project_aliases = _build_project_id_aliases(project_id)
    if not project_aliases:
        project_aliases = [project_id]

    def _distinct_values(field_name: str, keyword: str = "") -> List[str]:
        field = getattr(QCProcessTask, field_name)
        query = (
            db.session.query(
                field.label("value"),
                func.max(QCProcessTask.updated_at).label("latest_at"),
            )
            .filter(QCProcessTask.project_id.in_(project_aliases))
            .filter(field.isnot(None))
            .filter(field != "")
        )

        if status:
            query = query.filter(QCProcessTask.status == status)
        if field_name != "serial_number" and serial:
            query = query.filter(QCProcessTask.serial_number == serial)
        if field_name != "process_name" and process_name:
            query = query.filter(QCProcessTask.process_name == process_name)
        if field_name != "product_type" and product_type:
            query = query.filter(QCProcessTask.product_type == product_type)
        if date_from is not None:
            query = query.filter(QCProcessTask.updated_at >= date_from)
        if date_to is not None:
            query = query.filter(QCProcessTask.updated_at < (date_to + timedelta(days=1)))
        if keyword:
            query = query.filter(field.like(f"%{keyword}%"))

        rows = (
            query.group_by(field)
            .order_by(desc(func.max(QCProcessTask.updated_at)))
            .limit(limit)
            .all()
        )
        return [str(item[0]) for item in rows if item and item[0] is not None]

    return jsonify({
        "success": True,
        "project_id": project_id,
        "serial_numbers": _distinct_values("serial_number", q_serial),
        "process_names": _distinct_values("process_name", q_process),
        "product_types": _distinct_values("product_type", q_product_type),
    })


@motor_qc_bp.route('/api/projects/<project_id>/storage-check', methods=['GET'])
@require_permission_value('web:run_qc')
def api_project_storage_check(project_id):
    """存储自检：按项目/序列号核对任务、照片、分析结果落库状态。"""
    serial = (request.args.get("serial") or "").strip()
    process_name = (request.args.get("process") or "").strip()
    status = (request.args.get("status") or "").strip().lower()
    limit = min(500, max(20, request.args.get("limit", 200, type=int) or 200))

    project_aliases = _build_project_id_aliases(project_id) or [project_id]

    task_query = db.session.query(QCProcessTask).filter(QCProcessTask.project_id.in_(project_aliases))
    if serial:
        task_query = task_query.filter(QCProcessTask.serial_number == serial)
    if process_name:
        task_query = task_query.filter(QCProcessTask.process_name.like(f"%{process_name}%"))
    if status:
        task_query = task_query.filter(QCProcessTask.status == status)

    total_tasks = task_query.count()

    # 统计照片层面“已分析/未分析”
    photo_stats_query = (
        db.session.query(
            func.count(QCTaskPhoto.id).label("photo_total"),
            func.coalesce(
                func.sum(
                    case(
                        (QCTaskPhoto.analyzed_at.isnot(None), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("photo_analyzed"),
            func.max(QCTaskPhoto.analyzed_at).label("last_analyzed_at"),
            func.max(QCTaskPhoto.captured_at).label("last_photo_at"),
        )
        .join(QCProcessTask, QCTaskPhoto.task_id == QCProcessTask.id)
        .filter(QCProcessTask.project_id.in_(project_aliases))
    )
    if serial:
        photo_stats_query = photo_stats_query.filter(QCProcessTask.serial_number == serial)
    if process_name:
        photo_stats_query = photo_stats_query.filter(QCProcessTask.process_name.like(f"%{process_name}%"))
    if status:
        photo_stats_query = photo_stats_query.filter(QCProcessTask.status == status)

    photo_stats = photo_stats_query.first()
    photo_total = int((photo_stats.photo_total if photo_stats else 0) or 0)
    photo_analyzed = int((photo_stats.photo_analyzed if photo_stats else 0) or 0)
    photo_pending = max(photo_total - photo_analyzed, 0)

    status_counts_rows = (
        task_query.with_entities(QCProcessTask.status, func.count(QCProcessTask.id))
        .group_by(QCProcessTask.status)
        .all()
    )
    status_counts = {str(item[0] or "pending"): int(item[1] or 0) for item in status_counts_rows}

    tasks = (
        task_query
        .order_by(desc(QCProcessTask.updated_at), desc(QCProcessTask.id))
        .limit(limit)
        .all()
    )

    task_ids = [int(task.id) for task in tasks]
    per_task_photo_stats = {}
    if task_ids:
        per_task_rows = (
            db.session.query(
                QCTaskPhoto.task_id.label("task_id"),
                func.count(QCTaskPhoto.id).label("photo_total"),
                func.coalesce(
                    func.sum(
                        case(
                            (QCTaskPhoto.analyzed_at.isnot(None), 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("photo_analyzed"),
                func.max(QCTaskPhoto.analyzed_at).label("last_analyzed_at"),
                func.max(QCTaskPhoto.captured_at).label("last_photo_at"),
            )
            .filter(QCTaskPhoto.task_id.in_(task_ids))
            .group_by(QCTaskPhoto.task_id)
            .all()
        )
        per_task_photo_stats = {
            int(item.task_id): {
                "photo_total": int(item.photo_total or 0),
                "photo_analyzed": int(item.photo_analyzed or 0),
                "photo_pending": max(int(item.photo_total or 0) - int(item.photo_analyzed or 0), 0),
                "last_analyzed_at": _dt_to_iso(item.last_analyzed_at),
                "last_photo_at": _dt_to_iso(item.last_photo_at),
            }
            for item in per_task_rows
        }

    task_rows = []
    for task in tasks:
        stats = per_task_photo_stats.get(int(task.id), {})
        task_rows.append({
            "task_id": int(task.id),
            "project_id": task.project_id,
            "serial_number": task.serial_number,
            "process_name": task.process_name,
            "product_type": task.product_type,
            "status": task.status,
            "photo_total": int(stats.get("photo_total", task.photo_count or 0)),
            "photo_analyzed": int(stats.get("photo_analyzed", 0)),
            "photo_pending": int(stats.get("photo_pending", 0)),
            "last_analyzed_at": stats.get("last_analyzed_at") or _dt_to_iso(task.last_analyzed_at),
            "last_photo_at": stats.get("last_photo_at"),
            "updated_at": _dt_to_iso(task.updated_at),
        })

    return jsonify({
        "success": True,
        "project_id": project_id,
        "project_aliases": project_aliases,
        "filters": {
            "serial": serial,
            "process": process_name,
            "status": status,
        },
        "summary": {
            "task_total": int(total_tasks),
            "photo_total": int(photo_total),
            "photo_analyzed": int(photo_analyzed),
            "photo_pending": int(photo_pending),
            "last_analyzed_at": _dt_to_iso(photo_stats.last_analyzed_at if photo_stats else None),
            "last_photo_at": _dt_to_iso(photo_stats.last_photo_at if photo_stats else None),
            "status_counts": status_counts,
        },
        "rows": task_rows,
    })


def _normalize_confirm_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in ("pass", "ok", "qualified", "合格"):
        return "pass"
    if normalized in ("fail", "ng", "不合格", "失败"):
        return "fail"
    if normalized in ("pending", "todo", "待确认", "未检测"):
        return "pending"
    return ""


@motor_qc_bp.route('/api/tasks/<int:task_id>/confirm', methods=['POST'])
@require_permission_value('web:run_qc')
def confirm_qc_task(task_id):
    """任务中心人工确认：更新细节确认并回写经验记录。"""
    task = db.session.query(QCProcessTask).filter_by(id=task_id).first()
    if not task:
        return jsonify({"success": False, "error": "任务不存在"}), 404

    data = request.get_json(silent=True) or {}
    detail_updates = data.get("details") or data.get("detail_confirmations") or []
    if not isinstance(detail_updates, list):
        return jsonify({"success": False, "error": "details 必须为数组"}), 400

    detail_items = (
        db.session.query(QCTaskDetailItem)
        .filter(QCTaskDetailItem.task_id == task.id)
        .order_by(QCTaskDetailItem.id.asc())
        .all()
    )
    detail_by_key = {item.detail_key: item for item in detail_items}

    inspector_id = _resolve_inspector_id()
    touched = 0
    for row in detail_updates:
        if not isinstance(row, dict):
            continue
        detail_key = normalize_detail_key(str(row.get("detail_key") or ""))
        if not detail_key or detail_key not in detail_by_key:
            continue
        confirmed_status = _normalize_confirm_status(row.get("confirmed_status"))
        if not confirmed_status:
            return jsonify({"success": False, "error": f"无效 confirmed_status: {row.get('confirmed_status')}"}), 400

        item = detail_by_key[detail_key]
        item.confirmed_status = confirmed_status
        item.confirmed_by = inspector_id
        item.confirmed_at = datetime.utcnow()
        item.updated_at = datetime.utcnow()
        touched += 1

    if detail_updates and touched == 0:
        return jsonify({"success": False, "error": "未匹配到可更新的细节项"}), 400

    required_items = [item for item in detail_items if (item.source or "").strip().lower() == "config"]
    if not required_items:
        required_items = detail_items

    def _is_confirmed(item: QCTaskDetailItem) -> bool:
        return _normalize_confirm_status(item.confirmed_status or "") in ("pass", "fail")

    all_confirmed = bool(required_items) and all(_is_confirmed(item) for item in required_items)
    task.status = "confirmed" if all_confirmed else "review"
    task.updated_at = datetime.utcnow()

    ai_result = _normalize_confirm_status((task.best_result_json or {}).get("overall_status") or "") or "pending"
    explicit_human_result = _normalize_confirm_status(data.get("human_result") or "")
    if explicit_human_result:
        human_result = explicit_human_result
    else:
        effective_statuses = [
            _normalize_confirm_status(item.confirmed_status or item.best_status or "")
            for item in detail_items
        ]
        if any(status == "fail" for status in effective_statuses):
            human_result = "fail"
        elif effective_statuses and all(status == "pass" for status in effective_statuses):
            human_result = "pass"
        else:
            human_result = "pending"

    defect_tags = []
    image_refs = []
    for item in detail_items:
        effective = _normalize_confirm_status(item.confirmed_status or item.best_status or "")
        if effective != "fail":
            continue
        if item.detail_label:
            defect_tags.append(item.detail_label)
        if item.best_photo and item.best_photo.photo_path:
            image_refs.append(item.best_photo.photo_path)

    feedback_payload = {
        "project_id": task.project_id,
        "serial_number": task.serial_number,
        "process_name": task.process_name,
        "product_type": task.product_type or "",
        "model_code": str(data.get("model_code") or ""),
        "scope_level": data.get("scope_level") or "platform",
        "ai_result": ai_result,
        "human_result": human_result,
        "defect_tags": list(dict.fromkeys(defect_tags)),
        "image_refs": list(dict.fromkeys(image_refs)),
        "notes": str(data.get("notes") or "").strip() or None,
    }

    context = _resolve_experience_context(feedback_payload)
    scope_level = _resolve_feedback_scope(feedback_payload.get("scope_level") or "", context)
    bucket = _get_or_create_bucket(
        scope_level=scope_level,
        stator_platform=context.get("stator_platform") or "",
        cooling_type=context.get("cooling_type") or "",
        model_code=context.get("model_code") or "",
    )

    record = QCFeedbackRecord(
        bucket_id=bucket.id,
        rule_id=None,
        project_id=feedback_payload["project_id"],
        serial_number=feedback_payload["serial_number"],
        process_name=feedback_payload["process_name"],
        ai_result=feedback_payload["ai_result"],
        human_result=feedback_payload["human_result"],
        defect_tags=feedback_payload["defect_tags"],
        image_refs=feedback_payload["image_refs"],
        notes=feedback_payload["notes"],
        created_by=inspector_id,
    )
    db.session.add(record)
    db.session.commit()

    return jsonify({
        "success": True,
        "task": _serialize_qc_task(task, with_children=True),
        "feedback_record": record.to_dict(),
    })


def _resolve_feedback_scope(requested_scope: str, context: Dict[str, str]) -> str:
    scope = (requested_scope or "platform").strip().lower()
    if scope not in BUCKET_SCOPE_LEVELS:
        scope = "platform"

    if scope == "model" and context.get("model_code"):
        return "model"
    if scope == "platform" and context.get("stator_platform") and context.get("cooling_type"):
        return "platform"
    if context.get("cooling_type"):
        return "cooling"
    return "unknown"


@motor_qc_bp.route('/api/experience/context', methods=['GET'])
@require_permission_value('web:run_qc')
def get_experience_context():
    """获取当前产品命中的经验上下文和规则来源。"""
    context = _resolve_experience_context(request.args.to_dict(flat=True))
    bucket, fallback_chain = _find_best_experience_bucket(
        model_code=context.get("model_code") or "",
        stator_platform=context.get("stator_platform") or "",
        cooling_type=context.get("cooling_type") or "",
    )

    rules = []
    if bucket:
        rules = (
            db.session.query(QCExperienceRule)
            .filter_by(bucket_id=bucket.id, is_active=True)
            .order_by(desc(QCExperienceRule.confidence), desc(QCExperienceRule.updated_at))
            .all()
        )

    return jsonify({
        "success": True,
        "context": context,
        "selected_bucket": bucket.to_dict() if bucket else None,
        "fallback_chain": fallback_chain,
        "rules": [rule.to_dict() for rule in rules],
    })


@motor_qc_bp.route('/api/feedback/confirm', methods=['POST'])
@require_permission_value('web:run_qc')
def confirm_qc_feedback():
    """提交人工确认/改判结果，并回写到经验桶。"""
    data = request.get_json(silent=True) or {}

    required_fields = ("project_id", "serial_number", "process_name", "human_result")
    missing = [f for f in required_fields if not str(data.get(f, "")).strip()]
    if missing:
        return jsonify({"success": False, "error": f"缺少必填字段: {', '.join(missing)}"}), 400

    context = _resolve_experience_context(data)
    scope_level = _resolve_feedback_scope(data.get("scope_level") or "", context)

    bucket = _get_or_create_bucket(
        scope_level=scope_level,
        stator_platform=context.get("stator_platform") or "",
        cooling_type=context.get("cooling_type") or "",
        model_code=context.get("model_code") or "",
    )

    defect_tags = data.get("defect_tags") or []
    if not isinstance(defect_tags, list):
        defect_tags = [str(defect_tags)]

    image_refs = data.get("image_refs") or []
    if not isinstance(image_refs, list):
        image_refs = [image_refs]

    ai_result = str(data.get("ai_result", "")).strip() or None
    human_result = str(data.get("human_result", "")).strip()
    rule_id = data.get("rule_id")
    if rule_id is not None:
        try:
            rule_id = int(rule_id)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "rule_id 必须为整数"}), 400

    record = QCFeedbackRecord(
        bucket_id=bucket.id,
        rule_id=rule_id,
        project_id=str(data.get("project_id")).strip(),
        serial_number=str(data.get("serial_number")).strip(),
        process_name=str(data.get("process_name")).strip(),
        ai_result=ai_result,
        human_result=human_result,
        defect_tags=defect_tags,
        image_refs=image_refs,
        notes=str(data.get("notes", "")).strip() or None,
        created_by=_resolve_inspector_id(),
    )
    db.session.add(record)

    if rule_id:
        rule = db.session.query(QCExperienceRule).filter_by(id=rule_id).first()
        if rule:
            if record.is_corrected():
                rule.corrected_count += 1
            else:
                rule.confirmed_count += 1

    db.session.commit()

    return jsonify({
        "success": True,
        "bucket": bucket.to_dict(),
        "record": record.to_dict(),
    }), 201


@motor_qc_bp.route('/api/experience/promote', methods=['POST'])
@require_permission_value('web:run_qc')
def promote_experience_rules():
    """将经验从低层级提升到更高层（platform -> cooling/global）。"""
    data = request.get_json(silent=True) or {}
    from_bucket_id = data.get("from_bucket_id")
    to_scope = str(data.get("to_scope", "")).strip().lower()
    approved_by = str(data.get("approved_by") or _resolve_inspector_id()).strip()
    reason = str(data.get("reason", "")).strip() or None
    try:
        min_samples = int(data.get("min_samples") or 30)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "min_samples 必须为整数"}), 400
    try:
        min_quality = float(data.get("min_quality") or 0.95)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "min_quality 必须为数字"}), 400
    if min_samples <= 0:
        return jsonify({"success": False, "error": "min_samples 必须大于 0"}), 400
    if min_quality < 0 or min_quality > 1:
        return jsonify({"success": False, "error": "min_quality 必须在 0~1 之间"}), 400

    if not from_bucket_id:
        return jsonify({"success": False, "error": "缺少 from_bucket_id"}), 400
    try:
        from_bucket_id = int(from_bucket_id)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "from_bucket_id 必须为整数"}), 400

    if to_scope not in {"cooling", "global"}:
        return jsonify({"success": False, "error": "to_scope 仅支持 cooling/global"}), 400

    from_bucket = db.session.query(QCExperienceBucket).filter_by(id=from_bucket_id).first()
    if not from_bucket:
        return jsonify({"success": False, "error": "来源经验桶不存在"}), 404
    if (from_bucket.scope_level or "").strip().lower() == "unknown":
        return jsonify({"success": False, "error": "unknown 经验桶不允许升级，请先补齐平台/冷却方式"}), 400

    feedback_rows = db.session.query(QCFeedbackRecord).filter_by(bucket_id=from_bucket_id).all()
    sample_count = len(feedback_rows)
    corrected_count = sum(1 for row in feedback_rows if row.is_corrected())
    quality_score = (sample_count - corrected_count) / sample_count if sample_count else 0.0

    if sample_count < min_samples:
        return jsonify({
            "success": False,
            "error": f"样本不足，当前 {sample_count}，要求至少 {min_samples}",
        }), 400
    if quality_score < min_quality:
        return jsonify({
            "success": False,
            "error": f"质量分不足，当前 {quality_score:.3f}，要求至少 {min_quality:.3f}",
        }), 400

    if to_scope == "cooling":
        if not from_bucket.cooling_type:
            return jsonify({"success": False, "error": "来源经验桶缺少 cooling_type，无法升级到 cooling"}), 400
        to_bucket = _get_or_create_bucket(
            scope_level="cooling",
            stator_platform="",
            cooling_type=from_bucket.cooling_type or "",
            model_code="",
        )
    else:
        to_bucket = _get_or_create_bucket(
            scope_level="global",
            stator_platform="",
            cooling_type="",
            model_code="",
        )

    source_rules = (
        db.session.query(QCExperienceRule)
        .filter_by(bucket_id=from_bucket.id, is_active=True)
        .all()
    )
    cloned_rules = 0
    updated_rules = 0
    for source_rule in source_rules:
        existing_rows = (
            db.session.query(QCExperienceRule)
            .filter_by(
                bucket_id=to_bucket.id,
                process_name=source_rule.process_name,
                rule_type=source_rule.rule_type,
                is_active=True,
            )
            .order_by(desc(QCExperienceRule.updated_at), desc(QCExperienceRule.id))
            .all()
        )
        canonical = existing_rows[0] if existing_rows else None
        for duplicate in existing_rows[1:]:
            duplicate.is_active = False

        if canonical:
            canonical.rule_payload = source_rule.rule_payload or {}
            canonical.confidence = source_rule.confidence
            canonical.version = max(canonical.version or 1, source_rule.version or 1) + 1
            canonical.effective_from = datetime.utcnow()
            canonical.is_active = True
            updated_rules += 1
            continue

        cloned_rule = QCExperienceRule(
            bucket_id=to_bucket.id,
            process_name=source_rule.process_name,
            rule_type=source_rule.rule_type,
            rule_payload=source_rule.rule_payload or {},
            confidence=source_rule.confidence,
            confirmed_count=0,
            corrected_count=0,
            version=max(source_rule.version or 1, 1) + 1,
            effective_from=datetime.utcnow(),
            is_active=True,
        )
        db.session.add(cloned_rule)
        cloned_rules += 1

    promotion = QCRulePromotion(
        from_bucket_id=from_bucket.id,
        to_bucket_id=to_bucket.id,
        reason=reason,
        sample_count=sample_count,
        quality_score=quality_score,
        approved_by=approved_by or "unknown",
    )
    db.session.add(promotion)
    db.session.commit()

    return jsonify({
        "success": True,
        "promotion": promotion.to_dict(),
        "from_bucket": from_bucket.to_dict(),
        "to_bucket": to_bucket.to_dict(),
        "cloned_rules": cloned_rules,
        "updated_rules": updated_rules,
    })


@motor_qc_bp.route('/api/experience/stats', methods=['GET'])
@require_permission_value('web:run_qc')
def get_experience_stats():
    """经验桶统计视图（反馈量、纠正率、质量分）。"""
    buckets = db.session.query(QCExperienceBucket).order_by(desc(QCExperienceBucket.updated_at)).all()

    bucket_stats = []
    total_feedback = 0
    for bucket in buckets:
        rows = db.session.query(QCFeedbackRecord).filter_by(bucket_id=bucket.id).all()
        feedback_count = len(rows)
        corrected_count = sum(1 for row in rows if row.is_corrected())
        quality_score = (feedback_count - corrected_count) / feedback_count if feedback_count else 0.0
        total_feedback += feedback_count
        bucket_stats.append({
            **bucket.to_dict(),
            "feedback_count": feedback_count,
            "corrected_count": corrected_count,
            "quality_score": round(quality_score, 4),
        })

    bucket_stats.sort(key=lambda item: (item["feedback_count"], item["id"]), reverse=True)

    return jsonify({
        "success": True,
        "total_buckets": len(buckets),
        "total_feedback": total_feedback,
        "buckets": bucket_stats,
    })


@motor_qc_bp.route('/api/projects', methods=['POST'])
@require_permission_value('web:run_qc')
def create_project():
    """创建新项目"""
    data = request.json
    try:
        project = motor_project_manager.create_project(data)
        return jsonify(project), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

# Inspection Service API
from .services.inspection_service import InspectionService

@motor_qc_bp.route('/api/inspect', methods=['POST'])
@require_permission_value('web:run_qc')
def perform_inspection():
    """Perform single inspection"""
    data = request.get_json() or {}
    if not data.get('project_code') or not data.get('process_step') or not data.get('photo_path'):
        return jsonify({"error": "Missing required fields"}), 400

    inspector_id = _resolve_inspector_id()
    product_type = str(
        data.get("product_type")
        or data.get("productType")
        or ""
    ).strip()
    prompt_override = str(
        data.get("prompt_override")
        or data.get("promptOverride")
        or data.get("pre_prompt")
        or ""
    ).strip()
    process_context = data.get("process_context")
    if not isinstance(process_context, dict):
        process_context = {}

    service = InspectionService()
    try:
        result = service.perform_inspection(
            project_code=data['project_code'],
            process_step=data['process_step'],
            photo_path=data['photo_path'],
            inspector_id=inspector_id,
            product_type=product_type,
            prompt_override=prompt_override,
            process_context=process_context,
        )
    except Exception as exc:
        return jsonify({"error": f"Inspection failed: {exc}"}), 500

    return jsonify(result), 200


@motor_qc_bp.route('/api/projects/<project_id>/inspect/<serial_number>', methods=['POST'])
@require_permission_value('web:run_qc')
def inspect_motor_by_serial(project_id, serial_number):
    """按序列号执行全工序质检"""
    project = _load_project_or_404(project_id)
    payload = request.get_json(silent=True) or {}
    selected_processes = payload.get("processes") or []
    requested_product_type = (payload.get("product_type") or "").strip()
    product_type = _resolve_effective_product_type(project, serial_number, requested_product_type)

    selected_keys = set()
    if isinstance(selected_processes, list):
        for item in selected_processes:
            key = _normalize_step_key(item)
            if key:
                selected_keys.add(key)

    configured_steps = _build_configured_steps(project, product_type)
    if selected_keys:
        configured_steps = [p for p in configured_steps if _normalize_step_key(p.get("name")) in selected_keys]

    if not configured_steps:
        return jsonify({"success": False, "error": "未找到可检测工序配置"}), 404

    photos_by_process = _collect_serial_photos_by_process(project, serial_number, product_type)
    inspector_id = _resolve_inspector_id()
    service = InspectionService()

    project_code = (
        project.get("name")
        or project.get("projectName")
        or project.get("project_code")
        or project_id
    )

    results = []
    missing_processes = []
    inspected_processes = 0

    for step in configured_steps:
        step_name = step.get("name", "")
        step_key = _normalize_step_key(step_name)
        process_photos = photos_by_process.get(step_key, [])
        required_photo = bool(step.get("photoRequired", True))

        if not process_photos:
            if required_photo:
                missing_processes.append(step_name)
            results.append({
                "process": step_name,
                "order": int(step.get("order") or 0),
                "status": "pending",
                "photo_count": 0,
                "summary": "未找到该工序照片",
                "defect_count": 0,
                "defects": [],
                "photos": [],
            })
            continue

        inspected_processes += 1
        latest_photo = process_photos[-1]
        latest_photo_url = _build_photo_view_url(latest_photo)
        process_photo_items = _build_process_photo_items(process_photos)
        try:
            inspect_result = service.perform_inspection(
                project_code=project_code,
                process_step=step_name,
                photo_path=str(latest_photo),
                inspector_id=inspector_id,
                product_type=product_type,
            )
            defects = inspect_result.get("defects", [])
            if not isinstance(defects, list):
                defects = []
            status = (inspect_result.get("status") or "").strip().lower()
            if status not in ("pass", "fail", "ng"):
                status = "fail" if defects else "pass"
            summary = inspect_result.get("analysis") or inspect_result.get("summary") or ""
            confidence = inspect_result.get("confidence", 0.0)
        except Exception as exc:
            status = "ng"
            defects = []
            summary = f"质检执行失败: {exc}"
            confidence = 0.0

        results.append({
            "process": step_name,
            "order": int(step.get("order") or 0),
            "status": status,
            "photo_count": len(process_photos),
            "latest_photo": latest_photo.name,
            "latest_photo_url": latest_photo_url,
            "photos": process_photo_items,
            "summary": summary,
            "defect_count": len(defects),
            "defects": defects,
            "confidence": confidence,
        })

    statuses = [r["status"] for r in results if r["status"] in ("pass", "fail", "ng")]
    if "fail" in statuses:
        overall_status = "fail"
    elif missing_processes or "ng" in statuses:
        overall_status = "ng"
    elif statuses:
        overall_status = "pass"
    else:
        overall_status = "pending"

    return jsonify({
        "success": True,
        "project_id": project_id,
        "serial_number": serial_number,
        "product_type": product_type,
        "overall_status": overall_status,
        "total_processes": len(configured_steps),
        "inspected_processes": inspected_processes,
        "missing_processes": missing_processes,
        "results": results,
    })


@motor_qc_bp.route('/api/projects/<project_id>/inspect-stream/<serial_number>', methods=['GET'])
@require_permission_value('web:run_qc')
def inspect_motor_by_serial_stream(project_id, serial_number):
    """按序列号执行全工序质检（SSE 实时进度）"""
    stream_nonce = (request.args.get("nonce") or "").strip()
    if not _validate_stream_nonce(project_id, stream_nonce, consume=False):
        logger.warning(
            "[inspect-stream] blocked by nonce validation: project=%s serial=%s user=%s",
            project_id,
            serial_number,
            session.get("user_id") or session.get("username") or "unknown",
        )
        return jsonify({"success": False, "error": "无效请求令牌，请刷新页面后重试"}), 403

    if not _is_request_same_origin():
        logger.warning(
            "[inspect-stream] blocked by same-origin check: project=%s serial=%s origin=%s referer=%s",
            project_id,
            serial_number,
            request.headers.get("Origin"),
            request.headers.get("Referer"),
        )
        return jsonify({"success": False, "error": "非法请求来源"}), 403
    if not _is_inspect_stream_referer_valid(project_id):
        logger.warning(
            "[inspect-stream] blocked by referer path check: project=%s serial=%s referer=%s",
            project_id,
            serial_number,
            request.headers.get("Referer"),
        )
        return jsonify({"success": False, "error": "非法页面来源"}), 403

    # 在来源校验通过后再消费 nonce，避免无效来源请求消耗令牌。
    if not _validate_stream_nonce(project_id, stream_nonce, consume=True):
        logger.warning(
            "[inspect-stream] blocked by nonce consume: project=%s serial=%s user=%s",
            project_id,
            serial_number,
            session.get("user_id") or session.get("username") or "unknown",
        )
        return jsonify({"success": False, "error": "请求令牌已失效，请刷新页面后重试"}), 403

    project = _load_project_or_404(project_id)
    next_stream_nonce = _issue_stream_nonce(project_id)
    requested_product_type = (request.args.get("productType") or "").strip()
    product_type = _resolve_effective_product_type(project, serial_number, requested_product_type)
    guard_key = _build_inspect_stream_guard_key(project_id, serial_number, product_type)
    guard_state = _acquire_inspect_stream_guard(guard_key)
    if not bool(guard_state.get("ok")):
        reason = str(guard_state.get("reason") or "")
        retry_after = int(guard_state.get("retry_after") or 1)
        if reason == "active":
            logger.warning(
                "[inspect-stream] blocked by active guard: project=%s serial=%s retry_after=%s",
                project_id,
                serial_number,
                retry_after,
            )
            resp = jsonify({
                "success": False,
                "error": "该序列号正在识别中，请勿重复触发",
                "retry_after": retry_after,
            })
            resp.status_code = 409
            resp.headers["Retry-After"] = str(retry_after)
            return resp

        logger.warning(
            "[inspect-stream] blocked by cooldown guard: project=%s serial=%s retry_after=%s",
            project_id,
            serial_number,
            retry_after,
        )
        resp = jsonify({
            "success": False,
            "error": "识别刚完成，请稍后再试",
            "retry_after": retry_after,
        })
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    configured_steps = _build_configured_steps(project, product_type)

    if not configured_steps:
        _release_inspect_stream_guard(guard_key, apply_cooldown=False)
        return jsonify({"success": False, "error": "未找到可检测工序配置"}), 404

    try:
        photos_by_process = _collect_serial_photos_by_process(project, serial_number, product_type)
        inspector_id = _resolve_inspector_id()
        service = InspectionService()

        project_code = (
            project.get("name")
            or project.get("projectName")
            or project.get("project_code")
            or project_id
        )

        total_steps = len(configured_steps)

        def _event(event_name: str, payload: Dict) -> str:
            body = {"event": event_name, **(payload or {})}
            return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"

        @stream_with_context
        def generate():
            results = []
            missing_processes = []
            inspected_processes = 0

            try:
                yield _event("start", {
                    "project_id": project_id,
                    "serial_number": serial_number,
                    "product_type": product_type,
                    "total_steps": total_steps,
                    "next_nonce": next_stream_nonce,
                })

                for index, step in enumerate(configured_steps, start=1):
                    step_name = step.get("name", "")
                    step_key = _normalize_step_key(step_name)
                    process_photos = photos_by_process.get(step_key, [])
                    required_photo = bool(step.get("photoRequired", True))

                    yield _event("progress", {
                        "index": index,
                        "total_steps": total_steps,
                        "process": step_name,
                        "progress_percent": int(((index - 1) / total_steps) * 100) if total_steps else 0,
                    })

                    if not process_photos:
                        if required_photo:
                            missing_processes.append(step_name)
                        result_item = {
                            "process": step_name,
                            "order": int(step.get("order") or 0),
                            "status": "pending",
                            "photo_count": 0,
                            "latest_photo": "",
                            "latest_photo_url": "",
                            "summary": "未找到该工序照片",
                            "defect_count": 0,
                            "defects": [],
                            "photos": [],
                        }
                        results.append(result_item)
                        yield _event("step_result", {
                            "index": index,
                            "total_steps": total_steps,
                            "result": result_item,
                            "progress_percent": int((index / total_steps) * 100) if total_steps else 100,
                        })
                        continue

                    inspected_processes += 1
                    latest_photo = process_photos[-1]
                    latest_photo_url = _build_photo_view_url(latest_photo)
                    process_photo_items = _build_process_photo_items(process_photos)

                    try:
                        inspect_result = service.perform_inspection(
                            project_code=project_code,
                            process_step=step_name,
                            photo_path=str(latest_photo),
                            inspector_id=inspector_id,
                            product_type=product_type,
                            persist=False,
                        )
                        defects = inspect_result.get("defects", [])
                        if not isinstance(defects, list):
                            defects = []
                        status = (inspect_result.get("status") or "").strip().lower()
                        if status not in ("pass", "fail", "ng"):
                            status = "fail" if defects else "pass"
                        summary = inspect_result.get("analysis") or inspect_result.get("summary") or ""
                        confidence = inspect_result.get("confidence", 0.0)
                    except Exception as exc:
                        status = "ng"
                        defects = []
                        summary = f"质检执行失败: {exc}"
                        confidence = 0.0

                    result_item = {
                        "process": step_name,
                        "order": int(step.get("order") or 0),
                        "status": status,
                        "photo_count": len(process_photos),
                        "latest_photo": latest_photo.name,
                        "latest_photo_url": latest_photo_url,
                        "photos": process_photo_items,
                        "summary": summary,
                        "defect_count": len(defects),
                        "defects": defects,
                        "confidence": confidence,
                    }
                    results.append(result_item)
                    yield _event("step_result", {
                        "index": index,
                        "total_steps": total_steps,
                        "result": result_item,
                        "progress_percent": int((index / total_steps) * 100) if total_steps else 100,
                    })

                statuses = [r["status"] for r in results if r["status"] in ("pass", "fail", "ng")]
                if "fail" in statuses:
                    overall_status = "fail"
                elif missing_processes or "ng" in statuses:
                    overall_status = "ng"
                elif statuses:
                    overall_status = "pass"
                else:
                    overall_status = "pending"

                payload = {
                    "success": True,
                    "project_id": project_id,
                    "serial_number": serial_number,
                    "product_type": product_type,
                    "overall_status": overall_status,
                    "total_processes": len(configured_steps),
                    "inspected_processes": inspected_processes,
                    "missing_processes": missing_processes,
                    "results": results,
                }
                yield _event("done", {"payload": payload, "progress_percent": 100})
            finally:
                _release_inspect_stream_guard(guard_key, apply_cooldown=True)

        return Response(generate(), mimetype='text/event-stream')
    except Exception:
        _release_inspect_stream_guard(guard_key, apply_cooldown=False)
        raise


@motor_qc_bp.route('/api/projects/<project_id>/report/<serial_number>', methods=['GET'])
@require_permission_value('web:run_qc')
def get_motor_report(project_id, serial_number):
    """按序列号查看当前质检状态（不触发重新分析）"""
    project = _load_project_or_404(project_id)
    requested_product_type = (request.args.get("productType") or "").strip()
    product_type = _resolve_effective_product_type(project, serial_number, requested_product_type)
    configured_steps = _build_configured_steps(project, product_type)

    photos_by_process = _collect_serial_photos_by_process(project, serial_number, product_type)
    project_code_candidates = [
        project.get("name") or "",
        project.get("projectName") or "",
        project.get("project_code") or "",
        project_id,
    ]
    project_code_candidates = [x for x in project_code_candidates if x]

    results = []
    missing_processes = []
    inspected_processes = 0

    for step in configured_steps:
        step_name = step.get("name", "")
        step_key = _normalize_step_key(step_name)
        process_photos = photos_by_process.get(step_key, [])
        required_photo = bool(step.get("photoRequired", True))

        latest_record = None
        if process_photos:
            inspected_processes += 1
            latest_record = (
                db.session.query(InspectionRecord)
                .filter(InspectionRecord.project_code.in_(project_code_candidates))
                .filter(InspectionRecord.process_step == step_name)
                .filter(InspectionRecord.photo_path.like(f"%/{serial_number}/%"))
                .order_by(desc(InspectionRecord.inspected_at))
                .first()
            )
        elif required_photo:
            missing_processes.append(step_name)

        if latest_record:
            defects = latest_record.defects_found or []
            status = "fail" if defects else "pass"
            summary = latest_record.inspection_result or ""
        elif process_photos:
            defects = []
            status = "ng"
            summary = "已上传照片，待执行质检分析"
        else:
            defects = []
            status = "pending"
            summary = "未找到该工序照片"

        results.append({
            "process": step_name,
            "order": int(step.get("order") or 0),
            "status": status,
            "photo_count": len(process_photos),
            "latest_photo": process_photos[-1].name if process_photos else "",
            "latest_photo_url": _build_photo_view_url(process_photos[-1]) if process_photos else "",
            "photos": _build_process_photo_items(process_photos),
            "summary": summary,
            "defect_count": len(defects),
            "defects": defects,
        })

    statuses = [r["status"] for r in results if r["status"] in ("pass", "fail", "ng")]
    if "fail" in statuses:
        overall_status = "fail"
    elif missing_processes or "ng" in statuses:
        overall_status = "ng"
    elif statuses:
        overall_status = "pass"
    else:
        overall_status = "pending"

    return jsonify({
        "success": True,
        "project_id": project_id,
        "serial_number": serial_number,
        "product_type": product_type,
        "overall_status": overall_status,
        "total_processes": len(configured_steps),
        "inspected_processes": inspected_processes,
        "missing_processes": missing_processes,
        "results": results,
    })

# Photo Service API
from .services.photo_service import PhotoService
from .services.task_service import QCTaskService, normalize_detail_key


@motor_qc_bp.route('/api/photos/view', methods=['GET'])
@require_permission_value('web:run_qc')
def view_photo():
    """查看工序分析使用的原图"""
    path_arg = (request.args.get("path") or "").strip()
    if not path_arg:
        return jsonify({"error": "缺少 path 参数"}), 400

    candidate = Path(unquote(path_arg))
    if not candidate.is_absolute():
        candidate = (DATA_DIR / candidate).resolve()
    else:
        candidate = candidate.resolve()

    allowed_roots = [
        (DATA_DIR / "picture").resolve(),
        (DATA_DIR / "uploads").resolve(),
    ]
    if not any(_is_path_within(candidate, root) for root in allowed_roots):
        return jsonify({"error": "无权访问该文件"}), 403

    if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
        return jsonify({"error": "仅支持查看图片文件"}), 400
    if not candidate.exists() or not candidate.is_file():
        return jsonify({"error": "文件不存在"}), 404

    return send_file(str(candidate))


@motor_qc_bp.route('/api/photos/upload', methods=['POST'])
@require_permission_value('web:run_qc')
def upload_photo():
    """Upload inspection photo"""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    project_code = request.form.get('project_code')
    process_step = request.form.get('process_step')
    if not project_code or not process_step:
        return jsonify({"error": "Missing project_code or process_step"}), 400

    service = PhotoService(base_path=DATA_DIR / "uploads" / "motor_qc")
    result = service.save_photo(
        file=file,
        project_code=project_code,
        process_step=process_step,
        filename=file.filename
    )

    serial_number = (
        request.form.get("serial_number")
        or request.form.get("productSerial")
        or request.form.get("product_serial")
        or request.form.get("serial")
        or ""
    ).strip()
    if not serial_number and file and file.filename:
        serial_number = Path(file.filename).stem.split("_")[0].strip()
    if not serial_number:
        serial_number = "UNKNOWN"

    product_type = (
        request.form.get("product_type")
        or request.form.get("productType")
        or ""
    ).strip()

    try:
        task_service = QCTaskService()
        task = task_service.upsert_task_for_photo(
            project_id=project_code,
            serial_number=serial_number,
            process_name=process_step,
            photo_path=result.get("photo_path", ""),
            product_type=product_type,
        )
        result["task_id"] = task.id
        result["task_status"] = task.status
    except Exception as exc:
        logger.error("Failed to enqueue QC process task after upload: %s", exc, exc_info=True)
        return jsonify({
            "success": False,
            "error": f"照片已上传但任务入队失败: {exc}",
            "photo_path": result.get("photo_path"),
        }), 500

    return jsonify(result), 200

# Batch Inspection Service API
from .services.batch_inspection_service import BatchInspectionService

@motor_qc_bp.route('/api/inspect/batch', methods=['POST'])
@require_permission_value('web:run_qc')
def batch_inspection():
    """Batch inspection with SSE progress updates"""
    data = request.get_json()

    service = BatchInspectionService()

    def generate():
        for update in service.process_batch(
            project_code=data['project_code'],
            photos=data['photos'],
            inspector_id=data['inspector_id']
        ):
            yield f"data: {json.dumps(update)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream'
    )

# Report Service API
from .services.report_service import ReportService

@motor_qc_bp.route('/api/reports/defects/<project_code>', methods=['GET'])
@require_permission_value('web:run_qc')
def get_defect_report(project_code):
    """Get defect statistics report"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    service = ReportService()
    stats = service.get_defect_statistics(
        project_code=project_code,
        start_date=start_date,
        end_date=end_date
    )

    return jsonify(stats), 200

@motor_qc_bp.route('/api/reports/process-steps/<project_code>', methods=['GET'])
@require_permission_value('web:run_qc')
def get_process_step_report(project_code):
    """Get process step report"""
    service = ReportService()
    report = service.get_process_step_report(project_code)

    return jsonify(report), 200
