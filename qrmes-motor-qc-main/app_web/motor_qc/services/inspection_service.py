from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from ..models import InspectionRecord, db
from .vision_api import get_vision_service
from pathlib import Path
import inspect
import logging
import os
import re

logger = logging.getLogger(__name__)


def _runtime_config_get(key: str, default: Any = "") -> Any:
    try:
        from qrmes_shared_core.config import config as runtime_config
        return runtime_config.get(key, default)
    except Exception:
        return default


class _FallbackVisionService:
    """AI 依赖缺失时的降级实现，保证接口可用且不会抛 500。"""

    def __init__(self, reason: str):
        self.reason = reason

    def analyze_image(
        self,
        image_path: str,
        prompt: str,
        usage_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "analysis": f"AI服务不可用，已降级为人工复核: {self.reason}",
            "defects": [],
            "status": "ng",
            "confidence": 0.0
        }


class InspectionService:
    def __init__(self, vision_service=None, config_manager=None):
        if vision_service is not None:
            self.vision_service = vision_service
        else:
            try:
                self.vision_service = get_vision_service()
            except Exception as exc:
                logger.error("Vision service initialization failed: %s", exc)
                self.vision_service = _FallbackVisionService(str(exc))
        self.config_manager = config_manager

        # Lazy import to avoid circular dependency
        if self.config_manager is None:
            from qrmes_shared_core.project_config_manager import ProjectConfigManager
            from qrmes_shared_core.config import config
            data_dir = Path(config.nas_local_base_path)
            self.config_manager = ProjectConfigManager(data_dir)

    def perform_inspection(
        self,
        project_code: str,
        process_step: str,
        photo_path: str,
        inspector_id: str,
        serial_number: str = "",
        product_type: str = "",
        prompt_override: str = "",
        process_context: Optional[Dict[str, Any]] = None,
        online_provider: str = "qwen",
        online_vision_base_url: str = "",
        online_vision_api_key: str = "",
        vision_model: str = "",
        vision_mode: str = "online",
        secondary_online_model: str = "",
        secondary_online_base_url: str = "",
        secondary_online_api_key: str = "",
        local_vision_model: str = "",
        local_vision_base_url: str = "",
        local_vision_api_key: str = "",
        dual_primary: str = "online",
        *,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Perform inspection based on process step type"""

        # 1. Get attachment type from config
        attachment_type = self._get_attachment_type(project_code, process_step, product_type)

        logger.info(f"Process '{process_step}' attachment type: {attachment_type}")

        # 2. Handle based on type (both => route by actual file extension)
        file_ext = Path(photo_path).suffix.lower()

        if attachment_type == "both":
            if file_ext == ".pdf":
                return self._record_pdf_inspection(
                    project_code, process_step, photo_path, inspector_id, persist=persist
                )
            if file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif']:
                return self._perform_vision_inspection(
                    project_code,
                    process_step,
                    photo_path,
                    inspector_id,
                    serial_number=serial_number,
                    product_type=product_type,
                    prompt_override=prompt_override,
                    process_context=process_context,
                    online_provider=online_provider,
                    online_vision_base_url=online_vision_base_url,
                    online_vision_api_key=online_vision_api_key,
                    vision_model=vision_model,
                    vision_mode=vision_mode,
                    secondary_online_model=secondary_online_model,
                    secondary_online_base_url=secondary_online_base_url,
                    secondary_online_api_key=secondary_online_api_key,
                    local_vision_model=local_vision_model,
                    local_vision_base_url=local_vision_base_url,
                    local_vision_api_key=local_vision_api_key,
                    dual_primary=dual_primary,
                    persist=persist,
                )
            raise ValueError(f"Unsupported file type for 'both': {file_ext}")

        # 3. Validate file type for single-typed steps
        self._validate_file_type(photo_path, attachment_type)

        # 4. Handle based on type
        if attachment_type == "pdf":
            return self._record_pdf_inspection(
                project_code, process_step, photo_path, inspector_id, persist=persist
            )
        elif attachment_type == "photo":
            return self._perform_vision_inspection(
                project_code,
                process_step,
                photo_path,
                inspector_id,
                serial_number=serial_number,
                product_type=product_type,
                prompt_override=prompt_override,
                process_context=process_context,
                online_provider=online_provider,
                online_vision_base_url=online_vision_base_url,
                online_vision_api_key=online_vision_api_key,
                vision_model=vision_model,
                vision_mode=vision_mode,
                secondary_online_model=secondary_online_model,
                secondary_online_base_url=secondary_online_base_url,
                secondary_online_api_key=secondary_online_api_key,
                local_vision_model=local_vision_model,
                local_vision_base_url=local_vision_base_url,
                local_vision_api_key=local_vision_api_key,
                dual_primary=dual_primary,
                persist=persist,
            )
        else:
            # Unknown type - default to photo
            logger.warning(f"Unknown attachment type: {attachment_type}, defaulting to photo")
            return self._perform_vision_inspection(
                project_code,
                process_step,
                photo_path,
                inspector_id,
                serial_number=serial_number,
                product_type=product_type,
                prompt_override=prompt_override,
                process_context=process_context,
                online_provider=online_provider,
                online_vision_base_url=online_vision_base_url,
                online_vision_api_key=online_vision_api_key,
                vision_model=vision_model,
                vision_mode=vision_mode,
                secondary_online_model=secondary_online_model,
                secondary_online_base_url=secondary_online_base_url,
                secondary_online_api_key=secondary_online_api_key,
                local_vision_model=local_vision_model,
                local_vision_base_url=local_vision_base_url,
                local_vision_api_key=local_vision_api_key,
                dual_primary=dual_primary,
                persist=persist,
            )

    def _validate_file_type(self, file_path: str, expected_type: str):
        """Validate file type matches expected attachment type"""
        file_ext = Path(file_path).suffix.lower()

        if expected_type == "photo":
            if file_ext not in ['.jpg', '.jpeg', '.png', '.bmp', '.gif']:
                raise ValueError(f"Expected photo file, got {file_ext}")
        elif expected_type == "pdf":
            if file_ext != '.pdf':
                raise ValueError(f"Expected PDF file, got {file_ext}")
        # "both" type accepts any

    @staticmethod
    def _normalize_name(value: str) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[\s._-]+", "", text)
        text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
        return text

    def _load_project_config(self, project_code: str) -> Optional[Dict[str, Any]]:
        """优先按项目名称读取，失败后按 projectCode 字段回查。"""
        try:
            project_config = self.config_manager.get_project_config(project_code)
            if project_config:
                return project_config

            projects_dir = self.config_manager.projects_config_dir
            if projects_dir.exists():
                for config_file in projects_dir.glob("*.json"):
                    try:
                        config = self.config_manager.get_project_config(config_file.stem)
                        if config and str(config.get("projectCode") or "").strip() == str(project_code or "").strip():
                            return config
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Error loading project config: {e}")
        return None

    def get_process_step_config(self, project_code: str, process_step: str, product_type: str = "") -> Dict[str, Any]:
        """获取工序配置，优先按产品类型精确匹配，不存在则回退到同名工序。"""
        project_config = self._load_project_config(project_code)
        if not project_config:
            return {}

        process_key = self._normalize_name(process_step)
        product_key = self._normalize_name(product_type)
        if not process_key:
            return {}

        matched_steps: List[Tuple[str, Dict[str, Any]]] = []
        for pt in project_config.get("productTypes", []) or []:
            type_name = str((pt or {}).get("typeName") or "")
            for step in (pt or {}).get("processSteps", []) or []:
                if not isinstance(step, dict):
                    continue
                if self._normalize_name(step.get("name") or "") == process_key:
                    matched_steps.append((type_name, step))

        if matched_steps and product_key:
            for type_name, step in matched_steps:
                if self._normalize_name(type_name) == product_key:
                    return dict(step)

        if matched_steps:
            return dict(matched_steps[0][1])

        # 兼容旧结构
        for step in project_config.get("processAttributes", []) or []:
            if not isinstance(step, dict):
                continue
            if self._normalize_name(step.get("name") or "") == process_key:
                return dict(step)

        return {}

    def _get_attachment_type(self, project_code: str, process_step: str, product_type: str = "") -> str:
        """Get attachment type from project config"""
        try:
            process_config = self.get_process_step_config(project_code, process_step, product_type)
            if process_config:
                attachment_type = str(process_config.get("attachmentType") or "photo").strip().lower()
                if attachment_type in ("photo", "pdf", "both"):
                    return attachment_type
            logger.warning(f"Process step not found in config: project={project_code} step={process_step}")
            return "photo"
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return "photo"  # Default on error

    @staticmethod
    def _split_context_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            rows = value
        else:
            rows = re.split(r"[,，;；\n]+", str(value or ""))
        return [str(item).strip() for item in rows if str(item).strip()]

    def _build_vision_prompt(
        self,
        project_code: str,
        process_step: str,
        product_type: str = "",
        prompt_override: str = "",
        process_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        override = str(prompt_override or "").strip()
        if override:
            return override

        step_config = self.get_process_step_config(project_code, process_step, product_type) or {}
        context = process_context if isinstance(process_context, dict) else {}

        check_items: List[str] = []
        sub_checks = step_config.get("subChecks")
        if isinstance(sub_checks, list):
            for item in sub_checks:
                if isinstance(item, dict):
                    text = str(item.get("name") or item.get("key") or "").strip()
                else:
                    text = str(item or "").strip()
                if text:
                    check_items.append(text)

        rules = step_config.get("rules") if isinstance(step_config.get("rules"), dict) else {}
        rule_checks = rules.get("check_items") if isinstance(rules, dict) else []
        if isinstance(rule_checks, list):
            for item in rule_checks:
                text = str(item or "").strip()
                if text:
                    check_items.append(text)
        pass_criteria = str(rules.get("pass_criteria") or "").strip()

        expected_screw_count = context.get("expected_screw_count")
        if expected_screw_count in (None, "", 0):
            expected_screw_count = (
                step_config.get("expectedScrewCount")
                or step_config.get("expected_screw_count")
                or 0
            )
        try:
            expected_screw_count = int(expected_screw_count or 0)
        except (TypeError, ValueError):
            expected_screw_count = 0

        special_processes = self._split_context_list(
            context.get("special_processes")
            or step_config.get("specialProcesses")
            or step_config.get("special_processes")
        )
        special_parts = self._split_context_list(
            context.get("special_parts")
            or step_config.get("specialParts")
            or step_config.get("special_parts")
        )
        extra_focus = self._split_context_list(
            context.get("extra_focus")
            or step_config.get("extraFocus")
            or step_config.get("extra_focus")
        )
        pre_prompt = str(
            context.get("pre_prompt")
            or step_config.get("prePrompt")
            or step_config.get("pre_prompt")
            or ""
        ).strip()

        lines = [
            "你是电机装配质检专家，请结合工艺要求给出严格结论。",
            f"项目：{project_code}",
            f"工序：{process_step}",
        ]
        if product_type:
            lines.append(f"产品类型：{product_type}")
        if expected_screw_count > 0:
            lines.append(f"螺钉数量要求：应安装 {expected_screw_count} 个，并判断漏装/错装/未到位。")
        if special_processes:
            lines.append(f"特殊工艺：{'、'.join(special_processes)}")
        if special_parts:
            lines.append(f"关键零部件：{'、'.join(special_parts)}")
        if extra_focus:
            lines.append(f"额外关注点：{'、'.join(extra_focus)}")
        if check_items:
            unique_items = list(dict.fromkeys(check_items))
            lines.append(f"必检项：{'、'.join(unique_items)}")
        if pass_criteria:
            lines.append(f"合格标准：{pass_criteria}")
        if pre_prompt:
            lines.append(f"补充要求：{pre_prompt}")
        lines.append("请输出：结论(pass/fail/ng)、问题清单、简短原因。")
        return "\n".join(lines)

    def _record_pdf_inspection(
        self,
        project_code: str,
        process_step: str,
        pdf_path: str,
        inspector_id: str,
        *,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Record PDF inspection without Vision API analysis"""
        record_id = None
        if persist:
            record = InspectionRecord(
                project_code=project_code,
                process_step=process_step,
                photo_path=pdf_path,
                inspector_id=inspector_id,
                inspection_result="PDF文档已上传",
                defects_found=[],
                status="pass",
                inspected_at=datetime.utcnow()
            )

            db.session.add(record)
            db.session.commit()
            record_id = record.id
            logger.info(f"PDF inspection recorded: {record_id}")

        return {
            "status": "pass",
            "record_id": record_id,
            "defects": [],
            "analysis": "PDF文档已上传，无需质量分析",
            "confidence": 1.0
        }

    def _perform_vision_inspection(
        self,
        project_code: str,
        process_step: str,
        photo_path: str,
        inspector_id: str,
        serial_number: str = "",
        product_type: str = "",
        prompt_override: str = "",
        process_context: Optional[Dict[str, Any]] = None,
        online_provider: str = "qwen",
        online_vision_base_url: str = "",
        online_vision_api_key: str = "",
        vision_model: str = "",
        vision_mode: str = "online",
        secondary_online_model: str = "",
        secondary_online_base_url: str = "",
        secondary_online_api_key: str = "",
        local_vision_model: str = "",
        local_vision_base_url: str = "",
        local_vision_api_key: str = "",
        dual_primary: str = "online",
        *,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Perform vision API inspection with online/local/dual mode compatibility."""
        requested_model = str(vision_model or _runtime_config_get("qc_global_vision_model", "") or "").strip()
        requested_mode = self._normalize_mode(vision_mode or _runtime_config_get("qc_global_vision_mode", "online"))
        requested_online_provider = str(online_provider or "qwen").strip().lower() or "qwen"
        requested_online_base_url = str(online_vision_base_url or _runtime_config_get("qc_global_online_base_url", "") or "").strip()
        requested_online_api_key = str(
            online_vision_api_key
            or _runtime_config_get("qc_global_online_api_key", "")
            or _runtime_config_get("qwen_api_key", "")
            or _runtime_config_get("dashscope_api_key", "")
            or ""
        ).strip()
        requested_secondary_online_model = str(
            secondary_online_model or _runtime_config_get("qc_global_secondary_online_model", "") or ""
        ).strip()
        requested_secondary_online_base_url = str(
            secondary_online_base_url or _runtime_config_get("qc_global_secondary_online_base_url", "") or ""
        ).strip()
        requested_secondary_online_api_key = str(
            secondary_online_api_key or _runtime_config_get("qc_global_secondary_online_api_key", "") or ""
        ).strip()
        requested_local_model = str(local_vision_model or _runtime_config_get("qc_global_local_vision_model", "") or "").strip()
        requested_local_base_url = str(local_vision_base_url or _runtime_config_get("qc_global_local_base_url", "") or "").strip()
        requested_local_api_key = str(local_vision_api_key or _runtime_config_get("qc_global_local_api_key", "") or "").strip()
        requested_dual_primary = self._normalize_dual_primary(
            dual_primary or _runtime_config_get("qc_global_dual_primary", "online")
        )

        prompt = self._build_vision_prompt(
            project_code=project_code,
            process_step=process_step,
            product_type=product_type,
            prompt_override=prompt_override,
            process_context=process_context,
        )
        usage_context = self._build_usage_context(
            project_code=project_code,
            process_step=process_step,
            photo_path=photo_path,
            serial_number=serial_number,
            product_type=product_type,
            process_context=process_context,
        )

        def _run_vision(vision_service, provider_name: str, preferred_model: str) -> Dict[str, Any]:
            model_label = str(preferred_model or "").strip() or str(getattr(vision_service, "model", "") or "").strip()
            if model_label and vision_service.__class__.__name__ == "QwenVisionAPI":
                current_model = str(getattr(vision_service, "model", "") or "").strip()
                if current_model != model_label:
                    setattr(vision_service, "model", model_label)
                    logger.info(
                        "[InspectionService] 覆盖Qwen模型: %s -> %s (provider=%s project=%s process=%s)",
                        current_model or "<empty>",
                        model_label,
                        provider_name,
                        project_code,
                        process_step,
                    )

            try:
                if self._supports_usage_context(vision_service):
                    vision_result = vision_service.analyze_image(
                        image_path=photo_path,
                        prompt=prompt,
                        usage_context=usage_context,
                    )
                else:
                    vision_result = vision_service.analyze_image(
                        image_path=photo_path,
                        prompt=prompt,
                    )
            except Exception as exc:
                logger.error("Vision API inspection failed (provider=%s): %s", provider_name, exc)
                vision_result = {
                    "analysis": f"AI分析失败，需要人工复核: {exc}",
                    "defects": [],
                    "status": "ng",
                    "confidence": 0.0
                }

            defects_raw = vision_result.get("defects", [])
            if not isinstance(defects_raw, list):
                defects_raw = []

            defect_messages: List[str] = []
            for defect in defects_raw:
                if isinstance(defect, str):
                    defect_messages.append(defect)
                elif isinstance(defect, dict):
                    message = str(defect.get("description") or defect.get("type") or "").strip()
                    if message:
                        defect_messages.append(message)

            qc_status = (vision_result.get("status") or "").strip().lower()
            if qc_status not in ("pass", "fail", "ng"):
                qc_status = "fail" if defect_messages else "pass"

            confidence = 0.0
            try:
                confidence = float(vision_result.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0

            return {
                "status": qc_status,
                "defects": defect_messages,
                "analysis": str(vision_result.get("analysis", "") or ""),
                "confidence": confidence,
                "provider": provider_name,
                "model": model_label,
            }

        def _resolve_online_target(prefer_secondary: bool = False) -> Tuple[str, str, str, str, str]:
            if prefer_secondary or requested_online_provider in ("qwen_secondary", "secondary_online"):
                return (
                    "qwen_secondary",
                    "secondary_online",
                    requested_secondary_online_model or "qwen3.5-plus",
                    requested_secondary_online_base_url,
                    requested_secondary_online_api_key,
                )
            return (
                "qwen",
                "online",
                requested_model,
                requested_online_base_url,
                requested_online_api_key,
            )

        primary_result: Dict[str, Any]
        model_outputs: Dict[str, Any] = {}
        comparison: Dict[str, Any] = {}

        if requested_mode == "local":
            local_service = self._build_local_vision_service(
                model=requested_local_model or requested_model,
                base_url=requested_local_base_url,
                api_key=requested_local_api_key,
            )
            primary_result = _run_vision(local_service, "local", requested_local_model or requested_model)
            model_outputs["local"] = primary_result
        elif requested_mode == "dual":
            local_service = self._build_local_vision_service(
                model=requested_local_model or requested_model,
                base_url=requested_local_base_url,
                api_key=requested_local_api_key,
            )
            online_service_provider, online_label, online_model, online_base_url, online_api_key = _resolve_online_target()
            online_service = self._build_online_vision_service(
                model=online_model,
                base_url=online_base_url,
                api_key=online_api_key,
                provider=online_service_provider,
            )
            with ThreadPoolExecutor(max_workers=2) as executor:
                online_future = executor.submit(_run_vision, online_service, online_label, online_model)
                local_future = executor.submit(
                    _run_vision,
                    local_service,
                    "local",
                    requested_local_model or requested_model,
                )
                online_result = online_future.result()
                local_result = local_future.result()

            model_outputs = {"online": online_result, "local": local_result}
            primary_key = requested_dual_primary
            secondary_key = "local" if primary_key == "online" else "online"
            primary_result = model_outputs.get(primary_key, online_result)
            secondary_result = model_outputs.get(secondary_key, local_result)

            primary_defects = {str(item).strip() for item in (primary_result.get("defects") or []) if str(item).strip()}
            secondary_defects = {str(item).strip() for item in (secondary_result.get("defects") or []) if str(item).strip()}
            union = primary_defects | secondary_defects
            overlap = (len(primary_defects & secondary_defects) / len(union)) if union else 1.0
            comparison = {
                "primary": primary_key,
                "secondary": secondary_key,
                "primary_status": str(primary_result.get("status") or ""),
                "secondary_status": str(secondary_result.get("status") or ""),
                "status_match": str(primary_result.get("status") or "") == str(secondary_result.get("status") or ""),
                "defect_overlap": round(overlap, 4),
            }
        elif requested_mode == "dual_online":
            prefer_secondary = requested_dual_primary == "secondary_online" and requested_online_provider not in ("qwen", "online")
            online_service_provider, online_label, online_model, online_base_url, online_api_key = _resolve_online_target(
                prefer_secondary=prefer_secondary
            )
            online_service = self._build_online_vision_service(
                model=online_model,
                base_url=online_base_url,
                api_key=online_api_key,
                provider=online_service_provider,
            )
            primary_result = _run_vision(online_service, online_label, online_model)
            model_outputs[online_label] = primary_result
        else:
            online_service_provider, online_label, online_model, online_base_url, online_api_key = _resolve_online_target()
            online_service = self._build_online_vision_service(
                model=online_model,
                base_url=online_base_url,
                api_key=online_api_key,
                provider=online_service_provider,
            )
            primary_result = _run_vision(online_service, online_label, online_model)
            model_outputs[online_label] = primary_result

        defects = list(primary_result.get("defects") or [])
        qc_status = str(primary_result.get("status") or "ng")
        analysis = str(primary_result.get("analysis") or "")
        confidence = float(primary_result.get("confidence") or 0.0)
        provider_name = str(primary_result.get("provider") or ("local" if requested_mode == "local" else "online"))
        model_name = str(primary_result.get("model") or "")

        record_id = None
        if persist:
            record = InspectionRecord(
                project_code=project_code,
                process_step=process_step,
                photo_path=photo_path,
                inspector_id=inspector_id,
                inspection_result=analysis,
                defects_found=defects,
                status=qc_status,
                inspected_at=datetime.utcnow()
            )

            db.session.add(record)
            db.session.commit()
            record_id = record.id
            logger.info(f"Vision inspection completed: {record_id}")

        return {
            "status": qc_status,
            "record_id": record_id,
            "defects": defects,
            "analysis": analysis,
            "confidence": confidence,
            "mode": requested_mode,
            "provider": provider_name,
            "model": model_name,
            "model_outputs": model_outputs,
            "comparison": comparison,
        }

    @staticmethod
    def _normalize_mode(value: str) -> str:
        text = str(value or "").strip().lower()
        return text if text in ("online", "local", "dual", "dual_online") else "online"

    @staticmethod
    def _normalize_dual_primary(value: str) -> str:
        text = str(value or "").strip().lower()
        return text if text in ("online", "local", "secondary_online") else "online"

    def _build_online_vision_service(self, model: str, base_url: str, api_key: str, provider: str = "qwen"):
        from .qwen_vision import QwenVisionAPI

        resolved_model = str(
            model
            or (os.getenv("SECONDARY_QWEN_MODEL") if provider == "qwen_secondary" else "")
            or (_runtime_config_get("qc_global_secondary_online_model", "") if provider == "qwen_secondary" else "")
            or os.getenv("QWEN_MODEL")
            or _runtime_config_get("qc_global_vision_model", "")
            or "qwen3-vl-flash"
        ).strip()
        resolved_base_url = str(
            base_url
            or (os.getenv("SECONDARY_QWEN_BASE_URL") if provider == "qwen_secondary" else "")
            or (_runtime_config_get("qc_global_secondary_online_base_url", "") if provider == "qwen_secondary" else "")
            or os.getenv("QWEN_BASE_URL")
            or _runtime_config_get("qc_global_online_base_url", "")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).strip()
        resolved_api_key = str(
            api_key
            or (os.getenv("SECONDARY_QWEN_API_KEY") if provider == "qwen_secondary" else "")
            or (os.getenv("SECONDARY_DASHSCOPE_API_KEY") if provider == "qwen_secondary" else "")
            or (_runtime_config_get("qc_global_secondary_online_api_key", "") if provider == "qwen_secondary" else "")
            or os.getenv("QWEN_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or _runtime_config_get("qc_global_online_api_key", "")
            or _runtime_config_get("qwen_api_key", "")
            or _runtime_config_get("dashscope_api_key", "")
            or ""
        ).strip()
        try:
            timeout_seconds = int(os.getenv("QWEN_TIMEOUT", "90"))
        except (TypeError, ValueError):
            timeout_seconds = 90

        return QwenVisionAPI({
            "api_key": resolved_api_key,
            "provider": provider,
            "model": resolved_model,
            "base_url": resolved_base_url,
            "timeout": timeout_seconds,
        })

    def _build_local_vision_service(self, model: str, base_url: str, api_key: str):
        from .qwen_vision import QwenVisionAPI

        resolved_model = str(
            model
            or os.getenv("LOCAL_QWEN_MODEL")
            or os.getenv("LOCAL_VISION_MODEL")
            or _runtime_config_get("qc_global_local_vision_model", "")
            or "qwen/qwen3-vl-30b"
        ).strip()
        resolved_base_url = str(
            base_url
            or os.getenv("LOCAL_QWEN_BASE_URL")
            or os.getenv("LOCAL_VISION_BASE_URL")
            or _runtime_config_get("qc_global_local_base_url", "")
            or "http://127.0.0.1:1234/v1"
        ).strip()
        resolved_api_key = str(
            api_key
            or os.getenv("LOCAL_QWEN_API_KEY")
            or os.getenv("LOCAL_VISION_API_KEY")
            or _runtime_config_get("qc_global_local_api_key", "")
            or ""
        ).strip()
        try:
            timeout_seconds = int(os.getenv("LOCAL_QWEN_TIMEOUT", os.getenv("QWEN_TIMEOUT", "90")))
        except (TypeError, ValueError):
            timeout_seconds = 90

        return QwenVisionAPI({
            "api_key": resolved_api_key,
            "allow_empty_api_key": True,
            "provider": "local_qwen",
            "model": resolved_model,
            "base_url": resolved_base_url,
            "timeout": timeout_seconds,
        })

    @staticmethod
    def _extract_serial_from_photo_path(photo_path: str) -> str:
        path_obj = Path(str(photo_path or ""))
        parts_lower = [str(part).lower() for part in path_obj.parts]
        looks_like_task_center_upload = ("uploads" in parts_lower and "motor_qc" in parts_lower)
        parent_name = str(path_obj.parent.name or "").strip()
        if (
            parent_name
            and not looks_like_task_center_upload
            and parent_name.lower() not in {"tmp", "temp", "uploads", "motor_qc"}
        ):
            return parent_name

        stem = path_obj.stem
        if stem.startswith("qc__"):
            parts = stem.split("__", 3)
            if len(parts) >= 2:
                return str(parts[1] or "").strip()

        legacy_temp = re.match(r"^qc_([^_]+)_\d+_.+$", stem)
        if legacy_temp:
            return str(legacy_temp.group(1) or "").strip()

        ts_prefixed = re.match(r"^\d{8}_\d{6}_(.+)$", stem)
        candidate = ts_prefixed.group(1) if ts_prefixed else stem
        common = re.match(r"^([^_]+)_.+$", candidate)
        if common:
            return str(common.group(1) or "").strip()
        return ""

    def _build_usage_context(
        self,
        *,
        project_code: str,
        process_step: str,
        photo_path: str,
        serial_number: str,
        product_type: str,
        process_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        context: Dict[str, Any] = {
            "project_code": str(project_code or "").strip(),
            "process_step": str(process_step or "").strip(),
            "product_type": str(product_type or "").strip(),
        }
        serial_text = str(serial_number or "").strip()
        if not serial_text:
            serial_text = self._extract_serial_from_photo_path(photo_path)
        if serial_text:
            context["serial_number"] = serial_text

        extra = process_context if isinstance(process_context, dict) else {}
        if extra:
            source = str(extra.get("source") or "").strip()
            station_id = str(extra.get("station_id") or extra.get("stationId") or "").strip()
            upload_mode = str(extra.get("upload_mode") or extra.get("uploadMode") or "").strip()
            if source:
                context["source"] = source
            if station_id:
                context["station_id"] = station_id
            if upload_mode:
                context["upload_mode"] = upload_mode
        return context

    def _supports_usage_context(self, vision_service=None) -> bool:
        """Probe analyze_image signature to avoid double-calling on TypeError fallback."""
        target_service = vision_service or self.vision_service
        analyze_fn = getattr(target_service, "analyze_image", None)
        if not callable(analyze_fn):
            return False
        try:
            signature = inspect.signature(analyze_fn)
        except (TypeError, ValueError):
            return False
        return "usage_context" in signature.parameters
