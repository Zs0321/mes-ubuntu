"""QC API route registration extracted from mesapp.py.

This module intentionally keeps route behavior aligned with mesapp.py
while reducing mesapp.py size.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import jsonify, request
from qc_api_runtime_routes import register_qc_runtime_routes


def register_qc_api_routes(app, deps: Dict[str, Any]) -> None:
    """Register QC-related routes on the Flask app.

    Required deps keys:
    - login_required
    - require_permission
    - logger
    - config
    - data_manager
    - motor_qc_db
    - init_h2_service
    - get_h2_db_manager
    - data_dir
    """

    login_required = deps["login_required"]
    require_permission = deps["require_permission"]
    logger = deps["logger"]
    config = deps["config"]
    DataManager = deps["data_manager"]
    motor_qc_db = deps["motor_qc_db"]
    init_h2_service = deps["init_h2_service"]
    get_h2_db_manager = deps["get_h2_db_manager"]

    data_dir = deps["data_dir"]
    QUALITY_RELEASE_RULE_DEFAULTS: Dict[str, str] = {
        "recordRequired": "block",
        "materialComplete": "block",
        "photoCoverage": "review",
        "qcPassRequired": "block",
        "hilReportRequired": "ignore",
        "bemfReportRequired": "ignore",
    }
    QUALITY_RELEASE_RULE_LEVELS: Tuple[str, ...] = ("ignore", "review", "block")

    def _normalize_step_key(value: str) -> str:
        if value is None:
            return ''
        normalized = str(value).strip().lower()
        normalized = re.sub(r'[\s_-]+', '', normalized)
        normalized = re.sub(r'[^\w\u4e00-\u9fff]+', '', normalized)
        return normalized

    def _sanitize_folder_component(value: str) -> str:
        text = str(value or '').strip()
        if not text:
            return ''
        text = re.sub(r'[\\/*?:"<>|.]', '_', text)
        return text.strip().strip('.')

    def _folder_matches_name(folder_name: str, target_name: str) -> bool:
        folder = str(folder_name or '').strip()
        target = str(target_name or '').strip()
        if not target:
            return True
        if not folder:
            return False
        if folder == target:
            return True

        folder_prefix_first = folder.split('_', 1)[0] if '_' in folder else folder
        folder_prefix_last = folder.rsplit('_', 1)[0] if '_' in folder else folder

        folder_candidates = {
            folder,
            folder_prefix_first,
            folder_prefix_last,
        }
        target_candidates = {
            target,
            DataManager._normalize_project_name(target),
            _sanitize_folder_component(target),
        }

        folder_keys = {_normalize_step_key(item) for item in folder_candidates if item}
        target_keys = {_normalize_step_key(item) for item in target_candidates if item}
        if folder_keys.intersection(target_keys):
            return True

        sanitized_target = _sanitize_folder_component(target)
        if sanitized_target and folder.startswith(f"{sanitized_target}_"):
            return True
        if folder.startswith(f"{target}_"):
            return True
        return False

    def _extract_process_from_filename(file_name: str, product_serial: str) -> str:
        stem = Path(file_name).stem
        prefix = f"{product_serial}_"
        if not stem.startswith(prefix):
            return ''
        remainder = stem[len(prefix):]
        if '_' not in remainder:
            return remainder

        parts = remainder.split('_')
        if len(parts) >= 4 and parts[-1].isdigit() and parts[-2].isdigit() and parts[-3].isdigit():
            if len(parts[-3]) == 8 and len(parts[-2]) == 6:
                return '_'.join(parts[:-3])
        if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
            if len(parts[-2]) == 8 and len(parts[-1]) == 6:
                return '_'.join(parts[:-2])
        if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) == 14:
            return '_'.join(parts[:-1])
        return remainder.rsplit('_', 1)[0]

    def _collect_serial_photo_files(project_name: str, product_type: str, product_serial: str) -> List[Path]:
        photos_root = Path(app.config.get('PHOTOS_DIR', str(data_dir / 'picture')))
        if not photos_root.exists():
            return []

        normalized_project = DataManager._normalize_project_name(project_name or '')
        normalized_type = (product_type or '').strip()
        files: List[Path] = []

        for project_dir in photos_root.iterdir():
            if not project_dir.is_dir():
                continue
            if normalized_project:
                if not _folder_matches_name(project_dir.name, normalized_project):
                    continue
            for product_dir in project_dir.iterdir():
                if not product_dir.is_dir():
                    continue
                if normalized_type:
                    if not _folder_matches_name(product_dir.name, normalized_type):
                        continue
                serial_dir = product_dir / product_serial
                if not serial_dir.exists() or not serial_dir.is_dir():
                    continue
                for pattern in ('*.jpg', '*.jpeg', '*.png', '*.bmp', '*.gif'):
                    files.extend(serial_dir.glob(pattern))

        logger.info("[照片扫描] project=%s type=%s serial=%s count=%s", project_name, product_type, product_serial, len(files))
        return files

    def _normalize_qc_status(value: Any) -> Optional[str]:
        raw = str(value or "").strip().lower()
        if raw in ("pass", "fail", "ng"):
            return raw
        if raw in ("ok", "success", "passed"):
            return "pass"
        if raw in ("not_pass", "notpass", "failed", "reject"):
            return "fail"
        return None

    def _normalize_defect_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                pass
            return [text]
        return [str(value).strip()] if str(value).strip() else []

    def _normalize_quality_release_rules(value: Any) -> Dict[str, str]:
        current = value if isinstance(value, dict) else {}
        normalized: Dict[str, str] = {}
        for key, default_value in QUALITY_RELEASE_RULE_DEFAULTS.items():
            level = str(current.get(key, default_value) or default_value).strip().lower()
            if level not in QUALITY_RELEASE_RULE_LEVELS:
                level = default_value
            normalized[key] = level
        return normalized

    def _get_quality_release_rules_from_project(project_name: str) -> Dict[str, Any]:
        project_config = DataManager.get_project_config(project_name) or {}
        quality_workbench = project_config.get("qualityWorkbench")
        if not isinstance(quality_workbench, dict):
            quality_workbench = {}

        default_rules = quality_workbench.get("defaultRules")
        if not isinstance(default_rules, dict):
            default_rules = project_config.get("defaultRules")

        return {
            "enabled": bool(quality_workbench.get("enabled", True)),
            "defaultRules": _normalize_quality_release_rules(default_rules),
        }

    def _get_product_type_quality_release_rules(
        project_name: str,
        product_type_name: str,
    ) -> Optional[Dict[str, Any]]:
        project_config = DataManager.get_project_config(project_name) or {}
        product_types = project_config.get("productTypes") or []
        current = _get_quality_release_rules_from_project(project_name)
        project_defaults = current.get("defaultRules") or dict(QUALITY_RELEASE_RULE_DEFAULTS)
        for product_type in product_types:
            if not isinstance(product_type, dict):
                continue
            if str(product_type.get("typeName") or "").strip() != str(product_type_name or "").strip():
                continue
            raw_rules = product_type.get("qualityRules")
            if not isinstance(raw_rules, dict):
                raw_rules = {}
            return {
                "enabled": bool(current.get("enabled", True)),
                "defaultRules": dict(project_defaults),
                "qualityRules": _normalize_quality_release_rules(raw_rules),
                "productTypeName": str(product_type.get("typeName") or product_type_name or "").strip(),
            }
        return None

    def _build_qc_defect_payload(defects: List[str]) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        for defect in defects:
            payload.append({
                "type": "defect",
                "severity": "major",
                "description": str(defect),
                "location": "",
                "confidence": 0.7,
            })
        return payload

    def _get_project_process_steps(project_name: str, product_type: str) -> List[Dict[str, Any]]:
        project_config = DataManager.get_project_config(project_name)
        if not project_config:
            return []

        product_types = project_config.get('productTypes') or []
        target = None
        if product_type:
            for pt in product_types:
                if (pt or {}).get('typeName') == product_type:
                    target = pt
                    break
        if target is None and product_types:
            target = product_types[0]
        if not target:
            return []

        steps = target.get('processSteps') or []
        normalized_steps = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            if not step.get('name'):
                continue
            normalized_steps.append({
                'name': step.get('name'),
                'order': int(step.get('order') or 0),
                'required': bool(step.get('required', True)),
                'photoRequired': bool(step.get('photoRequired', True)),
                'attachmentType': step.get('attachmentType', 'photo'),
                'subChecks': step.get('subChecks') or step.get('subchecks') or [],
            })
        normalized_steps.sort(key=lambda x: x.get('order', 0))
        return normalized_steps

    QWEN_MODEL_FALLBACK: Tuple[str, ...] = (
        "qwen3-vl-flash",
        "qwen3.5-plus",
        "qwen-vl-max-latest",
        "qwen-vl-max",
        "qwen-vl-plus",
        "qwen-max-latest",
        "qwen-plus-latest",
    )
    LOCAL_MODEL_FALLBACK: Tuple[str, ...] = (
        "qwen/qwen3-vl-30b",
        "qwen/qwen3-vl-8b",
    )
    QC_VISION_MODE_CHOICES: Tuple[str, ...] = ("online", "local", "dual", "dual_online")

    def _resolve_qwen_api_key() -> str:
        return (
            os.getenv("QWEN_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or str(config.get("qc_global_online_api_key", "") or "")
            or str(config.get("qwen_api_key", "") or "")
            or str(config.get("dashscope_api_key", "") or "")
        ).strip()

    def _resolve_qwen_base_url() -> str:
        return (
            os.getenv("QWEN_BASE_URL")
            or str(config.get("qc_global_online_base_url", "") or "")
            or str(config.get("qwen_base_url", "") or "")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).strip().rstrip("/")

    def _resolve_secondary_qwen_api_key() -> str:
        return (
            os.getenv("SECONDARY_QWEN_API_KEY")
            or os.getenv("SECONDARY_DASHSCOPE_API_KEY")
            or str(config.get("qc_global_secondary_online_api_key", "") or "")
        ).strip()

    def _resolve_secondary_qwen_base_url() -> str:
        return (
            os.getenv("SECONDARY_QWEN_BASE_URL")
            or str(config.get("qc_global_secondary_online_base_url", "") or "")
            or _resolve_qwen_base_url()
        ).strip().rstrip("/")

    def _resolve_local_qwen_api_key() -> str:
        return (
            os.getenv("LOCAL_QWEN_API_KEY")
            or os.getenv("LOCAL_VISION_API_KEY")
            or str(config.get("qc_global_local_api_key", "") or "")
        ).strip()

    def _normalize_openai_base_url(base_url: str, default_base: str) -> str:
        text = str(base_url or "").strip().rstrip("/")
        if not text:
            text = str(default_base or "").strip().rstrip("/")
        if text.endswith("/chat/completions"):
            text = text[: -len("/chat/completions")]
        if text.endswith("/models"):
            text = text[: -len("/models")]
        if text.endswith("/v1"):
            return text
        if "/v1/" in f"{text}/":
            return text.rstrip("/")
        return f"{text}/v1".rstrip("/")

    def _resolve_local_qwen_base_url() -> str:
        configured = (
            os.getenv("LOCAL_QWEN_BASE_URL")
            or os.getenv("LOCAL_VISION_BASE_URL")
            or str(config.get("qc_global_local_base_url", "") or "")
            or "http://127.0.0.1:1234/v1"
        )
        return _normalize_openai_base_url(configured, "http://127.0.0.1:1234/v1")

    def _resolve_local_qwen_model() -> str:
        configured = str(config.get("qc_global_local_vision_model", "") or "").strip()
        if configured:
            return configured
        return str(
            os.getenv("LOCAL_QWEN_MODEL")
            or os.getenv("LOCAL_VISION_MODEL")
            or "qwen/qwen3-vl-30b"
        ).strip()

    def _get_global_qc_secondary_online_model() -> str:
        configured = str(config.get("qc_global_secondary_online_model", "") or "").strip()
        if configured:
            return configured
        return str(os.getenv("SECONDARY_QWEN_MODEL", "qwen3.5-plus") or "qwen3.5-plus").strip()

    def _normalize_qc_vision_mode(value: Any, default: str = "online") -> str:
        text = str(value or "").strip().lower()
        if text in QC_VISION_MODE_CHOICES:
            return text
        return default

    def _normalize_dual_primary(value: Any, default: str = "online") -> str:
        text = str(value or "").strip().lower()
        if text in ("online", "local", "secondary_online"):
            return text
        return default

    def _get_global_qc_vision_mode() -> str:
        configured = _normalize_qc_vision_mode(config.get("qc_global_vision_mode", ""), default="")
        if configured:
            return configured
        return _normalize_qc_vision_mode(os.getenv("QC_GLOBAL_VISION_MODE", "online"), default="online")

    def _get_global_qc_vision_model() -> str:
        configured = str(config.get("qc_global_vision_model", "") or "").strip()
        if configured:
            return configured
        return str(os.getenv("QWEN_MODEL", "qwen3-vl-flash") or "qwen3-vl-flash").strip()

    def _get_global_qc_dual_primary() -> str:
        configured = _normalize_dual_primary(config.get("qc_global_dual_primary", ""), default="")
        if configured:
            return configured
        return _normalize_dual_primary(os.getenv("QC_GLOBAL_DUAL_PRIMARY", "online"), default="online")

    def _extract_qwen_model_ids(payload: Any) -> List[str]:
        if not isinstance(payload, dict):
            return []
        rows = payload.get("data")
        if not isinstance(rows, list):
            return []
        ids: List[str] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            candidate = item.get("id") or item.get("model") or item.get("name")
            model_id = str(candidate or "").strip()
            if model_id:
                ids.append(model_id)
        deduped: List[str] = []
        seen = set()
        for model_id in ids:
            if model_id in seen:
                continue
            seen.add(model_id)
            deduped.append(model_id)
        return deduped

    def _sort_qwen_models(models: List[str]) -> List[str]:
        priority = {
            "qwen3-vl-flash": 0,
            "qwen3.5-plus": 1,
            "qwen-vl-max-latest": 2,
            "qwen-vl-max": 3,
            "qwen-vl-plus": 4,
            "qwen-max-latest": 5,
            "qwen-plus-latest": 6,
        }
        return sorted(models, key=lambda x: (priority.get(x, 999), x.lower()))

    def _load_remote_qwen_available_models(api_key: str, base_url: str) -> Tuple[List[str], str, str]:
        normalized_base_url = _normalize_openai_base_url(base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")
        if not api_key:
            return list(QWEN_MODEL_FALLBACK), "fallback", "未检测到 QWEN_API_KEY/DASHSCOPE_API_KEY，已使用内置模型列表"

        endpoint = f"{normalized_base_url}/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(endpoint, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                charset = getattr(resp.headers, "get_content_charset", lambda: None)() or "utf-8"
                body = resp.read().decode(charset, errors="ignore")
                payload = json.loads(body)
            remote_models = _extract_qwen_model_ids(payload)
            if remote_models:
                merged_models = _sort_qwen_models(list(set(remote_models) | set(QWEN_MODEL_FALLBACK)))
                warning = ""
                if len(merged_models) > len(remote_models):
                    warning = f"在线列表仅返回 {len(remote_models)} 个模型，已自动补全内置候选"
                return merged_models, "remote", warning
            return list(QWEN_MODEL_FALLBACK), "fallback", "在线模型列表为空，已切换为内置候选模型"
        except Exception as exc:
            logger.warning("[qc-models] 在线拉取模型失败: %s", exc)
            return list(QWEN_MODEL_FALLBACK), "fallback", f"在线模型服务暂不可达，当前使用内置候选模型: {exc}"

    def _load_qwen_available_models() -> Tuple[List[str], str, str]:
        return _load_remote_qwen_available_models(
            _resolve_qwen_api_key(),
            _resolve_qwen_base_url(),
        )

    def _load_secondary_qwen_available_models() -> Tuple[List[str], str, str]:
        return _load_remote_qwen_available_models(
            _resolve_secondary_qwen_api_key(),
            _resolve_secondary_qwen_base_url(),
        )

    def _load_local_available_models() -> Tuple[List[str], str, str]:
        base_url = _resolve_local_qwen_base_url()
        api_key = _resolve_local_qwen_api_key()
        endpoint = f"{base_url}/models"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(endpoint, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                charset = getattr(resp.headers, "get_content_charset", lambda: None)() or "utf-8"
                body = resp.read().decode(charset, errors="ignore")
                payload = json.loads(body)
            model_ids = _extract_qwen_model_ids(payload)
            if model_ids:
                merged = _sort_qwen_models(list(set(model_ids) | set(LOCAL_MODEL_FALLBACK)))
                warning = ""
                if len(merged) > len(model_ids):
                    warning = f"本地模型列表返回 {len(model_ids)} 个，已补全内置候选"
                return merged, "remote", warning
            return list(LOCAL_MODEL_FALLBACK), "fallback", "本地模型列表为空，已切换为内置候选模型"
        except Exception as exc:
            logger.warning("[qc-models] 本地模型列表拉取失败: %s", exc)
            return list(LOCAL_MODEL_FALLBACK), "fallback", f"本地模型服务暂不可达，当前使用内置候选模型: {exc}"

    def _get_qc_policy_from_project(project_name: str) -> Dict[str, Any]:
        default_policy = {
            "qc_enabled": True,
            "enforcement_mode": "warn",
            "check_previous_photos": True,
            "realtime_qc_enabled": True,
            "vision_mode": _get_global_qc_vision_mode(),
            "vision_model": _get_global_qc_vision_model(),
            "online_base_url": _resolve_qwen_base_url(),
            "secondary_online_model": _get_global_qc_secondary_online_model(),
            "secondary_online_base_url": _normalize_openai_base_url(
                _resolve_secondary_qwen_base_url(),
                _resolve_qwen_base_url(),
            ),
            "secondary_online_api_key": _resolve_secondary_qwen_api_key(),
            "local_vision_model": _resolve_local_qwen_model(),
            "local_vision_base_url": _resolve_local_qwen_base_url(),
            "dual_primary": _get_global_qc_dual_primary(),
            "confidence_threshold": 0.8,
        }
        project_config = DataManager.get_project_config(project_name)
        if not project_config:
            return default_policy

        raw = project_config.get('qcPolicy') or project_config.get('qc_policy') or {}
        if not isinstance(raw, dict):
            return default_policy

        policy = dict(default_policy)
        policy["qc_enabled"] = _as_bool(raw.get("qc_enabled", raw.get("qcEnabled")), policy["qc_enabled"])
        policy["enforcement_mode"] = str(raw.get("enforcement_mode", raw.get("enforcementMode", policy["enforcement_mode"]))).lower()
        policy["check_previous_photos"] = _as_bool(
            raw.get("check_previous_photos", raw.get("checkPreviousPhotos")),
            policy["check_previous_photos"],
        )
        policy["realtime_qc_enabled"] = _as_bool(
            raw.get("realtime_qc_enabled", raw.get("realtimeQcEnabled")),
            policy["realtime_qc_enabled"],
        )
        policy["vision_mode"] = _get_global_qc_vision_mode()
        policy["vision_model"] = _get_global_qc_vision_model()
        policy["online_base_url"] = _resolve_qwen_base_url()
        policy["secondary_online_model"] = _get_global_qc_secondary_online_model()
        policy["secondary_online_base_url"] = _normalize_openai_base_url(
            _resolve_secondary_qwen_base_url(),
            _resolve_qwen_base_url(),
        )
        policy["secondary_online_api_key"] = _resolve_secondary_qwen_api_key()
        policy["local_vision_model"] = _resolve_local_qwen_model()
        policy["local_vision_base_url"] = _resolve_local_qwen_base_url()
        policy["dual_primary"] = _get_global_qc_dual_primary()
        try:
            policy["confidence_threshold"] = float(
                raw.get("confidence_threshold", raw.get("confidenceThreshold", policy["confidence_threshold"]))
            )
        except (TypeError, ValueError):
            pass
        return policy

    def _resolve_project_identity(project_name: str, project_code: str) -> Tuple[str, str]:
        normalized_name = DataManager._normalize_project_name(project_name or "")
        normalized_code = str(project_code or "").strip()

        if normalized_name:
            if not normalized_code:
                try:
                    config_data = DataManager.get_project_config(normalized_name) or {}
                except Exception:
                    config_data = {}
                if isinstance(config_data, dict):
                    normalized_code = str(config_data.get("projectCode") or "").strip()
            return normalized_name, normalized_code

        if not normalized_code:
            return "", ""

        resolved_name = ""
        try:
            for item in DataManager.get_projects_with_details():
                if not isinstance(item, dict):
                    continue
                item_name = DataManager._normalize_project_name(item.get("projectName") or "")
                item_code = str(item.get("projectCode") or "").strip()
                if not item_name:
                    continue
                if item_code and item_code == normalized_code:
                    resolved_name = item_name
                    break
                if DataManager._project_name_key(item_name) == DataManager._project_name_key(normalized_code):
                    resolved_name = item_name
                    break
        except Exception as exc:
            logger.warning("[project-resolve] projectCode 映射项目名失败 code=%s err=%s", normalized_code, exc)

        if not resolved_name:
            resolved_name = DataManager._normalize_project_name(normalized_code)
        return resolved_name, normalized_code

    @app.route('/api/qc/config/<project_name>', methods=['GET'])
    @login_required
    def api_qc_get_config(project_name: str):
        """获取 QC 策略配置（移动端兼容）"""
        policy = _get_qc_policy_from_project(project_name)
        return jsonify({
            "success": True,
            "data": policy
        })

    @app.route('/api/qc/config/<project_name>', methods=['PUT'])
    @login_required
    @require_permission('web:manage_projects')
    def api_qc_update_config(project_name: str):
        """更新项目级 QC 策略配置（Web 管理端）"""
        project_config = DataManager.get_project_config(project_name)
        if not project_config:
            return jsonify({"success": False, "message": "项目配置不存在"}), 404

        payload = request.get_json(silent=True) or {}
        if isinstance(payload.get("data"), dict):
            payload = payload.get("data") or {}

        current = _get_qc_policy_from_project(project_name)
        enforcement_mode = str(
            payload.get("enforcement_mode", payload.get("enforcementMode", current.get("enforcement_mode", "warn")))
        ).strip().lower()
        if enforcement_mode not in ("warn", "block"):
            enforcement_mode = "warn"

        try:
            confidence_threshold = float(
                payload.get(
                    "confidence_threshold",
                    payload.get("confidenceThreshold", current.get("confidence_threshold", 0.8)),
                )
            )
        except (TypeError, ValueError):
            confidence_threshold = float(current.get("confidence_threshold", 0.8))
        confidence_threshold = max(0.0, min(1.0, confidence_threshold))

        new_policy = {
            "qc_enabled": _as_bool(payload.get("qc_enabled", payload.get("qcEnabled")), bool(current.get("qc_enabled", True))),
            "enforcement_mode": enforcement_mode,
            "check_previous_photos": _as_bool(
                payload.get("check_previous_photos", payload.get("checkPreviousPhotos")),
                bool(current.get("check_previous_photos", True)),
            ),
            "realtime_qc_enabled": _as_bool(
                payload.get("realtime_qc_enabled", payload.get("realtimeQcEnabled")),
                bool(current.get("realtime_qc_enabled", True)),
            ),
            "vision_mode": _get_global_qc_vision_mode(),
            "vision_model": _get_global_qc_vision_model(),
            "local_vision_model": _resolve_local_qwen_model(),
            "local_vision_base_url": _resolve_local_qwen_base_url(),
            "dual_primary": _get_global_qc_dual_primary(),
            "confidence_threshold": confidence_threshold,
        }

        project_config["qcPolicy"] = new_policy
        if not DataManager.save_project_config(project_name, project_config):
            return jsonify({"success": False, "message": "保存项目配置失败"}), 500

        return jsonify({
            "success": True,
            "message": "QC策略已保存",
            "data": new_policy,
        })

    @app.route('/api/qc/release-rules/<project_name>', methods=['GET'])
    @login_required
    def api_qc_get_release_rules(project_name: str):
        project_config = DataManager.get_project_config(project_name)
        if not project_config:
            return jsonify({"success": False, "message": "项目配置不存在"}), 404
        return jsonify({
            "success": True,
            "data": _get_quality_release_rules_from_project(project_name),
        })

    @app.route('/api/qc/release-rules/<project_name>', methods=['PUT'])
    @login_required
    @require_permission('web:manage_projects')
    def api_qc_update_release_rules(project_name: str):
        project_config = DataManager.get_project_config(project_name)
        if not project_config:
            return jsonify({"success": False, "message": "项目配置不存在"}), 404

        payload = request.get_json(silent=True) or {}
        if isinstance(payload.get("data"), dict):
            payload = payload.get("data") or {}

        current = _get_quality_release_rules_from_project(project_name)
        enabled = _as_bool(payload.get("enabled"), bool(current.get("enabled", True)))
        normalized_rules = _normalize_quality_release_rules(payload.get("defaultRules"))

        quality_workbench = project_config.get("qualityWorkbench")
        if not isinstance(quality_workbench, dict):
            quality_workbench = {}

        quality_workbench["enabled"] = enabled
        quality_workbench["defaultRules"] = normalized_rules
        project_config["qualityWorkbench"] = quality_workbench
        project_config["defaultRules"] = dict(normalized_rules)

        if not DataManager.save_project_config(project_name, project_config):
            return jsonify({"success": False, "message": "保存质量放行规则失败"}), 500

        return jsonify({
            "success": True,
            "message": "质量放行规则已保存",
            "data": {
                "enabled": enabled,
                "defaultRules": normalized_rules,
            },
        })

    @app.route('/api/qc/release-rules/<project_name>/product-types/<path:product_type_name>', methods=['GET'])
    @login_required
    def api_qc_get_product_type_release_rules(project_name: str, product_type_name: str):
        payload = _get_product_type_quality_release_rules(project_name, product_type_name)
        if not payload:
            return jsonify({"success": False, "message": "产品类型不存在"}), 404
        return jsonify({
            "success": True,
            "data": payload,
        })

    @app.route('/api/qc/release-rules/<project_name>/product-types/<path:product_type_name>', methods=['PUT'])
    @login_required
    @require_permission('web:manage_projects')
    def api_qc_update_product_type_release_rules(project_name: str, product_type_name: str):
        project_config = DataManager.get_project_config(project_name)
        if not project_config:
            return jsonify({"success": False, "message": "项目配置不存在"}), 404

        payload = request.get_json(silent=True) or {}
        if isinstance(payload.get("data"), dict):
            payload = payload.get("data") or {}

        normalized_rules = _normalize_quality_release_rules(payload.get("qualityRules"))
        product_types = project_config.get("productTypes") or []
        target_product_type = None
        for product_type in product_types:
            if not isinstance(product_type, dict):
                continue
            if str(product_type.get("typeName") or "").strip() == str(product_type_name or "").strip():
                target_product_type = product_type
                break

        if target_product_type is None:
            return jsonify({"success": False, "message": "产品类型不存在"}), 404

        target_product_type["qualityRules"] = dict(normalized_rules)
        if not DataManager.save_project_config(project_name, project_config):
            return jsonify({"success": False, "message": "保存产品类型质量放行规则失败"}), 500

        return jsonify({
            "success": True,
            "message": "产品类型质量放行规则已保存",
            "data": {
                "enabled": bool((_get_quality_release_rules_from_project(project_name) or {}).get("enabled", True)),
                "qualityRules": normalized_rules,
                "productTypeName": str(target_product_type.get("typeName") or product_type_name or "").strip(),
            },
        })

    @app.route('/api/qc/models', methods=['GET'])
    @login_required
    @require_permission('web:system_settings')
    def api_qc_available_models():
        """获取可用模型列表（支持 online/local/all）。"""
        provider = str(request.args.get("provider") or "online").strip().lower()

        if provider in ("online", "qwen"):
            models, source, warning = _load_qwen_available_models()
            data = {
                "provider": "online",
                "models": [{"id": model_id, "label": model_id} for model_id in models],
                "source": source,
                "warning": warning,
                "api_key_configured": bool(_resolve_qwen_api_key()),
                "default_model": _get_global_qc_vision_model(),
                "base_url": _resolve_qwen_base_url(),
            }
            return jsonify({"success": True, "data": data})

        if provider in ("local", "local_qwen"):
            models, source, warning = _load_local_available_models()
            data = {
                "provider": "local",
                "models": [{"id": model_id, "label": model_id} for model_id in models],
                "source": source,
                "warning": warning,
                "api_key_configured": bool(_resolve_local_qwen_api_key()),
                "default_model": _resolve_local_qwen_model(),
                "base_url": _resolve_local_qwen_base_url(),
            }
            return jsonify({"success": True, "data": data})

        if provider in ("secondary_online", "secondary_qwen", "qwen_secondary"):
            models, source, warning = _load_secondary_qwen_available_models()
            data = {
                "provider": "secondary_online",
                "models": [{"id": model_id, "label": model_id} for model_id in models],
                "source": source,
                "warning": warning,
                "api_key_configured": bool(_resolve_secondary_qwen_api_key()),
                "default_model": _get_global_qc_secondary_online_model(),
                "base_url": _normalize_openai_base_url(
                    _resolve_secondary_qwen_base_url(),
                    _resolve_qwen_base_url(),
                ),
            }
            return jsonify({"success": True, "data": data})

        if provider == "all":
            online_models, online_source, online_warning = _load_qwen_available_models()
            secondary_online_models, secondary_online_source, secondary_online_warning = _load_secondary_qwen_available_models()
            local_models, local_source, local_warning = _load_local_available_models()
            data = {
                "provider": "all",
                "online": {
                    "models": [{"id": model_id, "label": model_id} for model_id in online_models],
                    "source": online_source,
                    "warning": online_warning,
                    "api_key_configured": bool(_resolve_qwen_api_key()),
                    "default_model": _get_global_qc_vision_model(),
                    "base_url": _resolve_qwen_base_url(),
                },
                "secondary_online": {
                    "models": [{"id": model_id, "label": model_id} for model_id in secondary_online_models],
                    "source": secondary_online_source,
                    "warning": secondary_online_warning,
                    "api_key_configured": bool(_resolve_secondary_qwen_api_key()),
                    "default_model": _get_global_qc_secondary_online_model(),
                    "base_url": _normalize_openai_base_url(
                        _resolve_secondary_qwen_base_url(),
                        _resolve_qwen_base_url(),
                    ),
                },
                "local": {
                    "models": [{"id": model_id, "label": model_id} for model_id in local_models],
                    "source": local_source,
                    "warning": local_warning,
                    "api_key_configured": bool(_resolve_local_qwen_api_key()),
                    "default_model": _resolve_local_qwen_model(),
                    "base_url": _resolve_local_qwen_base_url(),
                },
            }
            return jsonify({"success": True, "data": data})

        return jsonify({"success": False, "message": "provider 仅支持 online/local/secondary_online/all"}), 400

    @app.route('/api/settings/qc-global', methods=['GET'])
    @login_required
    @require_permission('web:system_settings')
    def api_get_qc_global_settings():
        """获取全局 QC 模型设置。"""
        online_models, online_source, online_warning = _load_qwen_available_models()
        secondary_online_models, secondary_online_source, secondary_online_warning = _load_secondary_qwen_available_models()
        local_models, local_source, local_warning = _load_local_available_models()
        return jsonify({
            "success": True,
            "data": {
                "vision_model": _get_global_qc_vision_model(),
                "models": [{"id": model_id, "label": model_id} for model_id in online_models],
                "source": online_source,
                "warning": online_warning,
                "api_key_configured": bool(_resolve_qwen_api_key()),
                "vision_mode": _get_global_qc_vision_mode(),
                "dual_primary": _get_global_qc_dual_primary(),
                "online_base_url": _resolve_qwen_base_url(),
                "online": {
                    "model": _get_global_qc_vision_model(),
                    "base_url": _resolve_qwen_base_url(),
                    "models": [{"id": model_id, "label": model_id} for model_id in online_models],
                    "source": online_source,
                    "warning": online_warning,
                    "api_key_configured": bool(_resolve_qwen_api_key()),
                },
                "secondary_online": {
                    "model": _get_global_qc_secondary_online_model(),
                    "base_url": _normalize_openai_base_url(
                        _resolve_secondary_qwen_base_url(),
                        _resolve_qwen_base_url(),
                    ),
                    "models": [{"id": model_id, "label": model_id} for model_id in secondary_online_models],
                    "source": secondary_online_source,
                    "warning": secondary_online_warning,
                    "api_key_configured": bool(_resolve_secondary_qwen_api_key()),
                },
                "local": {
                    "model": _resolve_local_qwen_model(),
                    "base_url": _resolve_local_qwen_base_url(),
                    "models": [{"id": model_id, "label": model_id} for model_id in local_models],
                    "source": local_source,
                    "warning": local_warning,
                    "api_key_configured": bool(_resolve_local_qwen_api_key()),
                },
            }
        })

    @app.route('/api/settings/qc-global', methods=['PUT'])
    @login_required
    @require_permission('web:system_settings')
    def api_update_qc_global_settings():
        """更新全局 QC 模型设置。"""
        payload = request.get_json(silent=True) or {}
        if isinstance(payload.get("data"), dict):
            payload = payload.get("data") or {}

        def _payload_value(*keys: str, default: Any = None) -> Any:
            for key in keys:
                if key in payload:
                    return payload.get(key)
            return default

        vision_mode = _normalize_qc_vision_mode(
            _payload_value("vision_mode", "visionMode", default=_get_global_qc_vision_mode()),
            default="online",
        )
        vision_model = str(
            _payload_value(
                "vision_model",
                "visionModel",
                "online_model",
                "onlineModel",
                default=_get_global_qc_vision_model(),
            )
            or ""
        ).strip()
        online_base_url = _normalize_openai_base_url(
            _payload_value(
                "online_base_url",
                "onlineBaseUrl",
                default=_resolve_qwen_base_url(),
            )
            or "",
            _resolve_qwen_base_url(),
        )
        online_api_key = str(
            _payload_value(
                "online_api_key",
                "onlineApiKey",
                default=_resolve_qwen_api_key(),
            )
            or ""
        ).strip()
        local_model = str(
            _payload_value(
                "local_vision_model",
                "localVisionModel",
                "local_model",
                "localModel",
                default=_resolve_local_qwen_model(),
            )
            or ""
        ).strip()
        local_base_url = _normalize_openai_base_url(
            _payload_value(
                "local_vision_base_url",
                "localVisionBaseUrl",
                "local_base_url",
                "localBaseUrl",
                default=_resolve_local_qwen_base_url(),
            )
            or "",
            _resolve_local_qwen_base_url(),
        )
        local_api_key = str(
            _payload_value(
                "local_vision_api_key",
                "localVisionApiKey",
                "local_api_key",
                "localApiKey",
                default=_resolve_local_qwen_api_key(),
            )
            or ""
        ).strip()
        secondary_online_model = str(
            _payload_value(
                "secondary_online_model",
                "secondaryOnlineModel",
                "secondary_model",
                "secondaryModel",
                default=_get_global_qc_secondary_online_model(),
            )
            or ""
        ).strip()
        secondary_online_base_url = _normalize_openai_base_url(
            _payload_value(
                "secondary_online_base_url",
                "secondaryOnlineBaseUrl",
                "secondary_base_url",
                "secondaryBaseUrl",
                default=_resolve_secondary_qwen_base_url(),
            )
            or "",
            _resolve_qwen_base_url(),
        )
        secondary_online_api_key = str(
            _payload_value(
                "secondary_online_api_key",
                "secondaryOnlineApiKey",
                "secondary_api_key",
                "secondaryApiKey",
                default=_resolve_secondary_qwen_api_key(),
            )
            or ""
        ).strip()
        dual_primary = _normalize_dual_primary(
            _payload_value("dual_primary", "dualPrimary", default=_get_global_qc_dual_primary()),
            default="online",
        )

        if not vision_model and vision_mode in ("online", "dual", "dual_online"):
            return jsonify({"success": False, "message": "缺少 vision_model"}), 400
        if vision_mode in ("local", "dual") and not local_model:
            return jsonify({"success": False, "message": "本地模式需配置 local_vision_model"}), 400
        if vision_mode == "dual_online" and not secondary_online_model:
            return jsonify({"success": False, "message": "双在线模式需配置 secondary_online_model"}), 400
        if vision_mode == "dual_online" and not secondary_online_api_key:
            return jsonify({"success": False, "message": "双在线模式需配置第二在线模型 API Key"}), 400

        updates = {
            "qc_global_vision_model": vision_model,
            "qc_global_vision_mode": vision_mode,
            "qc_global_online_base_url": online_base_url,
            "qc_global_online_api_key": online_api_key,
            "qc_global_secondary_online_model": secondary_online_model,
            "qc_global_secondary_online_base_url": secondary_online_base_url,
            "qc_global_secondary_online_api_key": secondary_online_api_key,
            "qc_global_local_vision_model": local_model,
            "qc_global_local_base_url": local_base_url,
            "qc_global_local_api_key": local_api_key,
            "qc_global_dual_primary": dual_primary,
        }
        if not config.update(updates):
            return jsonify({"success": False, "message": "保存全局模型配置失败"}), 500

        return jsonify({
            "success": True,
            "message": "全局QC模型已保存",
            "data": {
                "vision_model": vision_model,
                "vision_mode": vision_mode,
                "online_base_url": online_base_url,
                "secondary_online_model": secondary_online_model,
                "secondary_online_base_url": secondary_online_base_url,
                "local_vision_model": local_model,
                "local_vision_base_url": local_base_url,
                "dual_primary": dual_primary,
            }
        })

    register_qc_runtime_routes(
        app,
        {
            "login_required": login_required,
            "logger": logger,
            "motor_qc_db": motor_qc_db,
            "init_h2_service": init_h2_service,
            "get_h2_db_manager": get_h2_db_manager,
            "get_qc_policy_from_project": _get_qc_policy_from_project,
            "resolve_project_identity": _resolve_project_identity,
            "normalize_qc_vision_mode": _normalize_qc_vision_mode,
            "normalize_dual_primary": _normalize_dual_primary,
            "normalize_openai_base_url": _normalize_openai_base_url,
            "resolve_qwen_base_url": _resolve_qwen_base_url,
            "resolve_qwen_api_key": _resolve_qwen_api_key,
            "resolve_secondary_qwen_base_url": _resolve_secondary_qwen_base_url,
            "resolve_secondary_qwen_api_key": _resolve_secondary_qwen_api_key,
            "resolve_local_qwen_base_url": _resolve_local_qwen_base_url,
            "resolve_local_qwen_api_key": _resolve_local_qwen_api_key,
            "get_project_process_steps": _get_project_process_steps,
            "collect_serial_photo_files": _collect_serial_photo_files,
            "normalize_step_key": _normalize_step_key,
            "extract_process_from_filename": _extract_process_from_filename,
            "normalize_qc_status": _normalize_qc_status,
            "normalize_defect_list": _normalize_defect_list,
            "build_qc_defect_payload": _build_qc_defect_payload,
        },
    )


def _as_bool(value: Any, default: bool) -> bool:
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
