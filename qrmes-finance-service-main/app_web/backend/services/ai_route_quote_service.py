from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

try:
    from app_web.config import config as app_config
except Exception:  # pragma: no cover
    from qrmes_shared_core.config import config as app_config  # type: ignore

try:
    from app_web.config.secrets import SecretManager
except Exception:  # pragma: no cover
    try:
        from config.secrets import SecretManager  # type: ignore
    except Exception:  # pragma: no cover
        SecretManager = None  # type: ignore

logger = logging.getLogger(__name__)


def _get_secret_api_key(*service_names: str) -> str:
    if SecretManager is None:
        return ""
    for name in service_names:
        try:
            key = (SecretManager.get_api_key(name) or "").strip()
        except Exception:
            key = ""
        if key:
            return key
    return ""


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


def _read_int_env(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None, config_key: str | None = None) -> int:
    configured = ""
    if config_key:
        try:
            configured = str(app_config.get(config_key, "") or "").strip()
        except Exception:
            configured = ""
    raw = str(os.getenv(name, "") or configured or "").strip()
    try:
        value = int(raw) if raw else int(default)
    except (TypeError, ValueError):
        value = int(default)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


class AIRouteQuoteService:
    SKILL_NAME = "mes_ubuntu/changjiang-bom-pricing"
    SOURCE_NAME = "AI+skills(script-first)"
    MAX_SKILL_SUMMARY_CHARS = 280
    INFERENCE_CONFIDENCE_THRESHOLD = 0.60
    WEIGHT_INFERENCE_CONFIDENCE_THRESHOLD = 0.60
    WEIGHT_SENSITIVE_KEYWORDS = (
        "轴承", "油泵", "换热器", "过滤器", "滤芯", "导电环", "连接器", "插头", "插座",
        "接线座组件", "接线盒组件", "端子座组件", "接线座", "接线盒", "端子座", "线束",
        "法兰", "轴法兰", "堵头", "橡胶堵头", "弹簧", "波形弹簧", "透气阀", "密封圈",
        "油封", "密封垫", "O型圈", "o型圈", "螺母", "螺钉", "螺栓", "螺杆",
    )

    def __init__(self, *, skill_root: Path | None = None):
        self.api_key = self._resolve_api_key()
        self.base_url = self._resolve_base_url()
        self.model = self._resolve_model()
        self.skill_root = skill_root or Path(__file__).resolve().parents[3] / "changjiang-bom-pricing"
        self._skill_knowledge_bundle: str | None = None
        self.timeout = _read_int_env("PRICING_QWEN_TIMEOUT", 90, minimum=15, maximum=300, config_key="pricing_qwen_timeout")
        self.timeout_retry_count = _read_int_env("PRICING_QWEN_TIMEOUT_RETRY", 1, minimum=0, maximum=3, config_key="pricing_qwen_timeout_retry")
        self.max_workers = _read_int_env("PRICING_AI_MAX_WORKERS", 2, minimum=1, maximum=4, config_key="pricing_ai_max_workers")
        self.endpoint = f"{_normalize_openai_base_url(self.base_url, 'https://dashscope.aliyuncs.com/compatible-mode/v1')}/chat/completions"

    @property
    def is_ready(self) -> bool:
        return bool(self.api_key)

    def prepare_staged_pricing_input(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._plan_second_stage_input(item)

    def plan_script_usage(self, plan_input: dict[str, Any]) -> dict[str, Any]:
        registry = [str(name).strip() for name in (plan_input.get("registry") or []) if str(name).strip()]
        default_scripts = list(registry)
        if not self.is_ready:
            return {
                "selected_scripts": default_scripts,
                "reason": "未配置 AI 接口 key，已回退到默认脚本白名单。",
                "source": "heuristic",
            }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return JSON only with keys scripts and reason. "
                        "scripts must be an array chosen only from the whitelist."
                    ),
                },
                {"role": "user", "content": self._build_script_plan_prompt(plan_input)},
            ],
            "temperature": 0.0,
            "max_tokens": 180,
            "response_format": {"type": "json_object"},
            "enable_thinking": False,
        }
        body = self._invoke_json_api(payload, "Qwen script planner")
        content = self._extract_content_text(body)
        parsed = self._try_parse_json_text(content)
        if not parsed:
            parsed = self._try_parse_json_text(self._extract_reasoning_text(body))
        selected = [str(name).strip() for name in (parsed.get("scripts") or []) if str(name).strip() in registry]
        if not selected:
            selected = default_scripts
        return {
            "selected_scripts": selected,
            "reason": str(parsed.get("reason") or "").strip() or "未提供额外特殊任务约束，已按默认脚本白名单执行。",
            "source": "qwen-script-planner",
        }

    def estimate_item(self, item: dict[str, Any]) -> dict[str, Any]:
        if not self.is_ready:
            return {
                "ready": False,
                "unit_price": 0.0,
                "confidence": 0.0,
                "reasoning": "未配置 AI 接口 key，无法生成 AI 报价。",
                "process_guess": "",
                "material_guess": "",
                "source": self.SOURCE_NAME,
            }

        staged = self._plan_second_stage_input(item)
        pricing_item = dict(staged.get("pricing_item") or item or {})
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": self._build_user_payload(pricing_item)},
            ],
            "temperature": 0.1,
            "max_tokens": 400,
            "response_format": {"type": "json_object"},
            "enable_thinking": False,
        }
        body = self._invoke_json_api(payload, "Qwen pricing API")
        content = self._extract_content_text(body)
        parsed = self._try_parse_json_text(content)
        if not parsed:
            parsed = self._try_parse_json_text(self._extract_reasoning_text(body))
        if not parsed and content:
            logger.warning("AI route response did not contain valid JSON content: %s", content[:200])

        reasoning = str(parsed.get("reasoning") or "").strip()
        inference_note = str(staged.get("inference_note") or "").strip()
        if inference_note:
            reasoning = f"{inference_note} {reasoning}".strip()

        existing_process_guess = self._prompt_safe_text(item.get("ai_inferred_process_reference", ""))
        existing_material_guess = self._prompt_safe_text(item.get("ai_inferred_material_reference", ""))
        existing_weight_reference = self._to_number(item.get("ai_inferred_weight_reference"))
        existing_confidence = self._to_number(item.get("ai_inference_confidence"))
        staged_inference_used = bool(staged.get("used") or item.get("ai_second_stage_used") or item.get("ai_preinferred_for_skills"))
        inferred_weight_kg = self._to_number(staged.get("estimated_weight_kg"))
        if inferred_weight_kg <= 0:
            inferred_weight_kg = existing_weight_reference
        inference_confidence = self._to_number(staged.get("confidence"))
        if inference_confidence <= 0:
            inference_confidence = existing_confidence

        staged_process_guess = self._prompt_safe_text(staged.get("process_guess") or "")
        staged_material_guess = self._prompt_safe_text(staged.get("material_guess") or "")
        parsed_process_guess = self._prompt_safe_text(parsed.get("process_guess") or "")
        parsed_material_guess = self._prompt_safe_text(parsed.get("material_guess") or "")
        final_process_guess = parsed_process_guess or staged_process_guess or existing_process_guess
        final_material_guess = parsed_material_guess or staged_material_guess or existing_material_guess

        override_notes: list[str] = []
        if parsed_process_guess and staged_process_guess and parsed_process_guess != staged_process_guess:
            override_notes.append(f"第二轮AI工艺判断覆盖第一轮预推断：{staged_process_guess} -> {parsed_process_guess}")
        if parsed_material_guess and staged_material_guess and parsed_material_guess != staged_material_guess:
            override_notes.append(f"第二轮AI材质判断覆盖第一轮预推断：{staged_material_guess} -> {parsed_material_guess}")
        override_note = "；".join(override_notes)
        if override_note:
            reasoning = f"{override_note}。 {reasoning}".strip()

        return {
            "ready": True,
            "unit_price": self._to_number(parsed.get("unit_price")),
            "confidence": self._to_number(parsed.get("confidence")),
            "reasoning": reasoning,
            "process_guess": final_process_guess,
            "material_guess": final_material_guess,
            "estimated_weight_kg": inferred_weight_kg,
            "inference_confidence": inference_confidence,
            "staged_inference_used": staged_inference_used,
            "second_stage_override_used": bool(override_notes),
            "second_stage_override_note": override_note,
            "source": self.SOURCE_NAME,
            "raw_response": body,
        }
    def _invoke_json_api(self, payload: dict[str, Any], error_prefix: str) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        response = self._post_with_timeout_retry(headers=headers, payload=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"{error_prefix} error {response.status_code}: {response.text[:300]}")
        return response.json()

    def _post_with_timeout_retry(self, *, headers: dict[str, str], payload: dict[str, Any]) -> requests.Response:
        attempts = self.timeout_retry_count + 1
        last_error: requests.exceptions.Timeout | None = None
        for attempt in range(1, attempts + 1):
            try:
                return requests.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.exceptions.Timeout as exc:
                last_error = exc
                if attempt >= attempts:
                    raise
                logger.warning(
                    "AI route pricing timeout, retrying once: attempt=%s/%s timeout=%ss endpoint=%s",
                    attempt,
                    attempts,
                    self.timeout,
                    self.endpoint,
                )
                time.sleep(0.2)
        if last_error is not None:  # pragma: no cover
            raise last_error
        raise RuntimeError("Qwen pricing request did not return a response")
    def _build_system_prompt(self) -> str:
        return (
            "You are a motor, e-drive, and e-control BOM line-item pricing assistant. "
            "Return JSON only with keys unit_price, confidence, reasoning, process_guess, material_guess. "
            "unit_price must be a single-piece CNY number. "
            "reasoning, process_guess, and material_guess must be written in Simplified Chinese. "
            "Use skills and script results first when they are available. "
            "If the script price is missing, infer material, process, and category from item name, spec, code, and estimated weight. "
            "Default domain is motor electromagnetic or electrical assemblies rather than generic machining parts. "
            "When words such as stator, rotor, winding, impregnation, slot insertion, baking, enameled wire, flat copper wire, copper wire, silicon steel lamination, core, magnet, terminal box, terminal seat, harness, connector, slip ring, end cover, bearing, oil pump, filter, or seal appear, prioritize motor or electrical assembly interpretation over generic machining interpretation. "
            "Strong semantic component words must outrank pure dimensional cues such as OD, ID, diameter, phi, L, width, and length. "
            "For example, an item described as stator assembly or impregnation stator should be understood as a stator winding or impregnation assembly, not as a generic steel machining part. "
            "Only choose generic shaft, sleeve, forging, or structural-steel interpretations when there is no meaningful motor-domain evidence. "
            "When staged AI inferred references are provided, treat them as high-confidence candidate hints for this pricing round. "
            "For standard parts or piece-priced items, you may quote without weight. "
            "If a motor-domain category price band is provided, keep the one-piece estimate inside that range unless there is a strong contradiction. "
            "Do not use Excel purchase price, Kingdee purchase price, or target price as AI pricing anchors. "
            "When identifiers are sufficient, prefer a best-effort non-zero estimate over returning 0."
        )

    def _build_inference_system_prompt(self) -> str:
        return (
            "You are a motor BOM material and process inference assistant. "
            "Return JSON only with keys confidence, reasoning, process_guess, material_guess, estimated_weight_kg. "
            "All text fields must be in Simplified Chinese. "
            "Infer the most likely material, process, and single-piece weight from item name, spec, code, known fields, skills or script context, and the motor-domain category bands. "
            "Always assume the item belongs to a motor, e-drive, or e-control supply chain unless there is very strong contrary evidence. "
            "If semantic words indicate motor electromagnetic assemblies such as stator, rotor, winding, impregnation, slot insertion, baking, enameled wire, flat copper wire, copper wire, silicon steel lamination, core, magnet, terminal box, terminal seat, harness, connector, or slip ring, those semantic words must outrank pure dimensional words like OD, ID, phi, or L. "
            "For example, stator assembly or impregnation stator should infer stator winding or impregnation related process and motor-electromagnetic materials, not generic 45 steel machining. "
            "Do not drift toward generic shaft, sleeve, forging, or structural steel interpretations unless the motor-domain semantic evidence is weak. "
            "Do not output prices in this step. "
            "Only infer weight when the part is strongly weight-sensitive or weight is missing. "
            "Confidence must be a number between 0 and 1."
        )


    @staticmethod
    def _build_script_plan_prompt(plan_input: dict[str, Any]) -> str:
        registry = [str(name).strip() for name in (plan_input.get("registry") or []) if str(name).strip()]
        production_mode = str(plan_input.get("production_mode") or "sample").strip()
        annual_volume = int(AIRouteQuoteService._to_number(plan_input.get("annual_volume")))
        item_count = int(AIRouteQuoteService._to_number(plan_input.get("item_count")))
        need_gap = "yes" if bool(plan_input.get("need_gap", True)) else "no"
        need_format = "yes" if bool(plan_input.get("need_format", True)) else "no"
        need_volume = "yes" if bool(plan_input.get("need_volume", False)) else "no"
        workflow_hint = str(plan_input.get("workflow_hint") or "").strip()
        return (
            f"Whitelist: {', '.join(registry)}. "
            f"Mode: {production_mode}. Volume: {annual_volume}. Items: {item_count}. "
            f"Need line pricing: yes. Need gap review: {need_gap}. "
            f"Need formatted workbook: {need_format}. Need mass pricing: {need_volume}. "
            f"Skill workflow hint: {workflow_hint or 'price_bom mandatory; gap/format/volume on demand.'}"
        )

    def _build_user_payload(self, item: dict[str, Any]) -> str:
        code = self._prompt_safe_text(item.get("code", "")) or "编码未知"
        name = self._prompt_safe_text(item.get("name", "")) or "未知物料"
        spec = self._prompt_safe_text(item.get("spec", "")) or "规格未知"
        material = self._prompt_safe_text(item.get("material", "")) or "材质未知"
        process = self._prompt_safe_text(item.get("process", "")) or "工艺未知"
        qty = max(self._to_number(item.get("qty")), 1.0)
        weight_kg = self._to_number(item.get("weight_kg"))
        weight_g = round(weight_kg * 1000) if weight_kg > 0 else 0
        context = item.get("ai_skill_context") or {}

        parts = [
            f"编码:{code}",
            f"名称:{name}",
            f"规格:{spec}",
            f"材质:{material}",
            f"工艺:{process}",
            f"数量:{qty:.4g}",
        ]
        if weight_g > 0:
            parts.append(f"重量:{weight_g}克")

        estimated_note = self._prompt_safe_text(item.get("ai_estimated_weight_note", ""))
        if estimated_note:
            parts.append(f"估重提示:{estimated_note}")

        inferred_material = self._prompt_safe_text(item.get("ai_inferred_material_reference", ""))
        if inferred_material:
            parts.append(f"AI推断材质参考:{inferred_material}")
        inferred_process = self._prompt_safe_text(item.get("ai_inferred_process_reference", ""))
        if inferred_process:
            parts.append(f"AI推断工艺参考:{inferred_process}")
        inferred_weight = self._to_number(item.get("ai_inferred_weight_reference"))
        if inferred_weight > 0:
            parts.append(f"AI推断重量参考:{inferred_weight:.4f}kg")
        inference_confidence = self._to_number(item.get("ai_inference_confidence"))
        if inference_confidence > 0:
            parts.append(f"AI推断参考置信度:{inference_confidence:.2f}")

        if self._to_number(context.get("rule_unit_price")) > 0:
            parts.append(f"规则单价{self._to_number(context.get('rule_unit_price')):.2f}元")
        if self._to_number(context.get("material_cost")) > 0:
            parts.append(f"材料{self._to_number(context.get('material_cost')):.2f}元")
        if self._to_number(context.get("process_cost")) > 0:
            parts.append(f"工艺{self._to_number(context.get('process_cost')):.2f}元")
        if self._to_number(context.get("volume_baseline_unit_price")) > 0:
            parts.append(
                "量产"
                f"{self._to_number(context.get('volume_baseline_unit_price')):.2f}/"
                f"{self._to_number(context.get('volume_conservative_unit_price')):.2f}/"
                f"{self._to_number(context.get('volume_aggressive_unit_price')):.2f}"
            )

        price_band = item.get("name_spec_price_band") or {}
        if price_band:
            parts.append(
                f"Name-spec price band:{self._prompt_safe_text(price_band.get('category'))} "
                f"{self._to_number(price_band.get('low')):.2f}-{self._to_number(price_band.get('high')):.2f} CNY/piece"
            )
        weight_band = item.get("name_spec_weight_band") or {}
        if weight_band:
            parts.append(
                f"Name-spec weight band:{self._prompt_safe_text(weight_band.get('category'))} "
                f"{self._to_number(weight_band.get('low')):.4f}-{self._to_number(weight_band.get('high')):.4f}kg"
            )
        parts.append(self._build_motor_domain_hint(item))
        script_summary = self._build_script_context_summary(context)
        if script_summary:
            parts.append(f"Script context:{script_summary}")
        parts.append("script-first optimized single-piece pricing JSON")
        return " ".join(part for part in parts if part)

    @classmethod
    def _build_motor_domain_hint(cls, item: dict[str, Any]) -> str:
        combined = " ".join(
            cls._prompt_safe_text(item.get(field, ""))
            for field in ("name", "spec", "code", "material", "process")
        ).lower()
        strong_map = (
            ("motor stator/rotor or winding assembly", ("stator", "rotor", "winding", "impregnation", "slot", "enameled", "copper wire", "silicon steel", "core")),
            ("motor terminal or harness assembly", ("terminal", "terminal box", "terminal seat", "connector", "plug", "socket", "harness")),
            ("motor rotating/support accessory", ("slip ring", "bearing", "flange", "end cover", "pump", "filter", "seal", "breather")),
        )
        hits = []
        for label, keywords in strong_map:
            if any(keyword in combined for keyword in keywords):
                hits.append(label)
        if hits:
            return "Motor-domain strong semantic hits: " + " / ".join(hits) + ". Prioritize motor or e-control component interpretation over pure size-based generic machining."
        return "Motor-domain default assumption: prioritize motor or e-control component interpretation unless semantic evidence is truly weak."

    def _build_inference_user_payload(self, item: dict[str, Any]) -> str:
        code = self._prompt_safe_text(item.get("code", "")) or "编码未知"
        name = self._prompt_safe_text(item.get("name", "")) or "未知物料"
        spec = self._prompt_safe_text(item.get("spec", "")) or "规格未知"
        material = self._prompt_safe_text(item.get("material", "")) or "材质未知"
        process = self._prompt_safe_text(item.get("process", "")) or "工艺未知"
        qty = max(self._to_number(item.get("qty")), 1.0)
        weight_kg = self._to_number(item.get("weight_kg"))
        context = item.get("ai_skill_context") or {}

        parts = [
            f"编码:{code}",
            f"名称:{name}",
            f"规格:{spec}",
            f"材质:{material}",
            f"工艺:{process}",
            f"数量:{qty:.4g}",
        ]
        if weight_kg > 0:
            parts.append(f"Original weight:{weight_kg:.4f}kg")
        estimated_note = self._prompt_safe_text(item.get("ai_estimated_weight_note", ""))
        if estimated_note:
            parts.append(f"Estimated-weight note:{estimated_note}")

        price_band = item.get("name_spec_price_band") or {}
        if price_band:
            parts.append(
                f"Name-spec price band:{self._prompt_safe_text(price_band.get('category'))} "
                f"{self._to_number(price_band.get('low')):.2f}-{self._to_number(price_band.get('high')):.2f} CNY/piece"
            )
        weight_band = item.get("name_spec_weight_band") or {}
        if weight_band:
            parts.append(
                f"Name-spec weight band:{self._prompt_safe_text(weight_band.get('category'))} "
                f"{self._to_number(weight_band.get('low')):.4f}-{self._to_number(weight_band.get('high')):.4f}kg"
            )
        parts.append(self._build_motor_domain_hint(item))
        script_summary = self._build_script_context_summary(context)
        if script_summary:
            parts.append(f"Script context:{script_summary}")
        parts.append("Infer material, process, and required weight first. Do not output price in this step.")
        return " ".join(part for part in parts if part)
        parts.append("Infer material, process, and required weight first. Do not output price in this step.")
        return " ".join(part for part in parts if part)

    def _plan_second_stage_input(self, item: dict[str, Any]) -> dict[str, Any]:
        pricing_item = dict(item or {})
        current_process = self._prompt_safe_text(pricing_item.get("process"))
        process_original = self._prompt_safe_text(pricing_item.get("process_original"))
        process_inference_note = self._prompt_safe_text(pricing_item.get("process_inference_note"))
        process_inferred = bool(pricing_item.get("process_inferred"))
        generic_inferred_process = process_inferred and not process_original and bool(process_inference_note)
        missing_process = (not current_process) or generic_inferred_process
        missing_material = not self._prompt_safe_text(pricing_item.get("material"))
        missing_weight = self._to_number(pricing_item.get("weight_kg")) <= 0 or bool(
            self._prompt_safe_text(pricing_item.get("ai_estimated_weight_note"))
        )
        weight_sensitive = self._is_weight_sensitive_item(pricing_item)
        should_reinfer_process = missing_process or self._should_override_existing_process(pricing_item)

        if not (should_reinfer_process or missing_material or (missing_weight and weight_sensitive)):
            return {
                "pricing_item": pricing_item,
                "used": False,
                "confidence": 0.0,
                "inference_note": "",
                "process_guess": "",
                "material_guess": "",
                "estimated_weight_kg": 0.0,
            }

        inferred = self._infer_missing_fields(pricing_item)
        confidence = self._to_number(inferred.get("confidence"))
        process_guess = self._prompt_safe_text(inferred.get("process_guess"))
        material_guess = self._prompt_safe_text(inferred.get("material_guess"))
        estimated_weight_kg = self._to_number(inferred.get("estimated_weight_kg"))

        used_parts: list[str] = []
        process_override_allowed = process_guess and confidence >= self.INFERENCE_CONFIDENCE_THRESHOLD and (
            missing_process or self._should_override_existing_process(pricing_item, process_guess)
        )
        if process_override_allowed:
            pricing_item["process"] = process_guess
            pricing_item["ai_inferred_process_reference"] = process_guess
            pricing_item["process_inferred"] = True
            pricing_item["process_inference_note"] = f"AI inferred process override: {process_guess}"
            used_parts.append(f"process={process_guess}")
        if missing_material and material_guess and confidence >= self.INFERENCE_CONFIDENCE_THRESHOLD:
            pricing_item["material"] = material_guess
            pricing_item["ai_inferred_material_reference"] = material_guess
            used_parts.append(f"material={material_guess}")
        if missing_weight and weight_sensitive and estimated_weight_kg > 0 and confidence >= self.WEIGHT_INFERENCE_CONFIDENCE_THRESHOLD:
            pricing_item["weight_kg"] = estimated_weight_kg
            pricing_item["ai_inferred_weight_reference"] = estimated_weight_kg
            used_parts.append(f"weight={estimated_weight_kg:.4f}kg")

        used = bool(used_parts)
        if used:
            pricing_item["ai_inference_confidence"] = confidence

        return {
            "pricing_item": pricing_item,
            "used": used,
            "confidence": confidence,
            "process_guess": process_guess,
            "material_guess": material_guess,
            "estimated_weight_kg": estimated_weight_kg,
            "inference_note": (
                f"AI staged override applied: {', ' .join(used_parts)} (confidence {confidence:.2f})."
                if used
                else ""
            ),
        }

    @classmethod
    def _should_override_existing_process(cls, item: dict[str, Any], process_guess: str = "") -> bool:
        current_process = cls._prompt_safe_text(item.get("process") or item.get("process_original") or "")
        guess = cls._prompt_safe_text(process_guess or "")
        if cls._is_motor_core_component(item):
            if not current_process:
                return True
            if not guess:
                return True
        if not current_process:
            return False
        normalized_current = current_process.lower()
        normalized_guess = guess.lower()
        generic_processes = {
            "冲压", "机加工", "机械加工", "压铸", "铸造", "注塑", "焊接", "拉伸", "冷镦", "磨削", "装配",
            "钣金", "车削", "热处理", "表面处理", "绕线",
        }
        if current_process in generic_processes:
            return True if not guess else normalized_current not in normalized_guess or len(guess) > len(current_process)
        if not guess:
            return False
        if normalized_current == normalized_guess:
            return False
        if normalized_current in normalized_guess and len(guess) >= len(current_process) + 4:
            return True
        return False

    @classmethod
    def _is_motor_core_component(cls, item: dict[str, Any]) -> bool:
        text = " ".join(
            cls._prompt_safe_text(item.get(key, ""))
            for key in ("name", "spec", "code", "material", "process")
        ).lower()
        core_keywords = (
            "定子", "转子", "铁芯", "机壳", "端盖", "电机轴", "接线盒", "接线板", "线束", "定子组件", "转子组件",
        )
        return any(keyword.lower() in text for keyword in core_keywords)

    def _infer_missing_fields(self, item: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._build_inference_system_prompt()},
                {"role": "user", "content": self._build_inference_user_payload(item)},
            ],
            "temperature": 0.0,
            "max_tokens": 280,
            "response_format": {"type": "json_object"},
            "enable_thinking": False,
        }
        body = self._invoke_json_api(payload, "Qwen inference API")
        content = self._extract_content_text(body)
        parsed = self._try_parse_json_text(content)
        if not parsed:
            parsed = self._try_parse_json_text(self._extract_reasoning_text(body))
        return {
            "confidence": self._to_number(parsed.get("confidence")),
            "reasoning": str(parsed.get("reasoning") or "").strip(),
            "process_guess": str(parsed.get("process_guess") or "").strip(),
            "material_guess": str(parsed.get("material_guess") or "").strip(),
            "estimated_weight_kg": self._to_number(parsed.get("estimated_weight_kg")),
        }

    @classmethod
    def _is_weight_sensitive_item(cls, item: dict[str, Any]) -> bool:
        text = " ".join(
            cls._prompt_safe_text(item.get(key, ""))
            for key in ("name", "spec", "code", "material")
        ).lower()
        return any(keyword.lower() in text for keyword in cls.WEIGHT_SENSITIVE_KEYWORDS)

    def _load_skill_knowledge_bundle(self) -> str:
        if self._skill_knowledge_bundle is not None:
            return self._skill_knowledge_bundle

        skill_text = self._read_skill_text(self.skill_root / "SKILL.md")
        rule_text = self._read_skill_text(self.skill_root / "references" / "material-and-process-rules.md")

        parts: list[str] = []
        if skill_text:
            highlights = self._extract_matches(
                skill_text,
                ("价格区间", "重量区间", "两阶段", "先推断", "高置信度", "量产"),
                limit=8,
            )
            if highlights:
                parts.append("技能规则：" + "；".join(highlights))
        if rule_text:
            mappings = self._extract_mapping_lines(rule_text, limit=5)
            if mappings:
                parts.append("材质映射：" + "；".join(mappings))
            formulas = self._extract_matches(
                rule_text,
                ("元/kg", "元/件", "数量", "估重", "在线参考"),
                limit=6,
            )
            if formulas:
                parts.append("计价规则：" + "；".join(formulas))

        summary = "。".join(part.strip("。") for part in parts if part).strip()
        if len(summary) > self.MAX_SKILL_SUMMARY_CHARS:
            summary = summary[: self.MAX_SKILL_SUMMARY_CHARS].rstrip() + "…"
        self._skill_knowledge_bundle = summary or "优先参考 skills 脚本结果。"
        return self._skill_knowledge_bundle

    def load_skill_workflow_hint(self) -> str:
        skill_text = self._read_skill_text(self.skill_root / "SKILL.md")
        if not skill_text:
            return "price_bom mandatory; gap/format/volume on demand."

        match = re.search(
            r"### Script Planning Rule(?P<body>.*?)(?:\n### |\n## |\Z)",
            skill_text,
            flags=re.S,
        )
        if not match:
            match = re.search(
                r"## Script Planning Rule(?P<body>.*?)(?:\n## |\Z)",
                skill_text,
                flags=re.S,
            )
        if not match:
            return "price_bom mandatory; gap/format/volume on demand."

        body = match.group("body")
        lines: list[str] = []
        for raw_line in body.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip(" -\t")
            if not line:
                continue
            if ".py" in line or "必跑" in line or "先跑" in line or "需要" in line or "production_mode=mass" in line:
                lines.append(line.replace("`", ""))
            if len(lines) >= 6:
                break
        summary = "；".join(lines).strip()
        if len(summary) > 280:
            summary = summary[:280].rstrip() + "…"
        return summary or "price_bom mandatory; gap/format/volume on demand."
    @staticmethod
    def _build_script_context_summary(context: dict[str, Any]) -> str:
        parts: list[str] = []
        script_registry = context.get("script_registry") or []
        if script_registry:
            parts.append("已执行:" + "/".join(str(name) for name in script_registry[:4]))
        rule_unit = AIRouteQuoteService._to_number(context.get("rule_unit_price"))
        if rule_unit > 0:
            parts.append(f"规则单价{rule_unit:.2f}元")
        material_cost = AIRouteQuoteService._to_number(context.get("material_cost"))
        if material_cost > 0:
            parts.append(f"材料成本{material_cost:.2f}元")
        process_cost = AIRouteQuoteService._to_number(context.get("process_cost"))
        if process_cost > 0:
            parts.append(f"工艺成本{process_cost:.2f}元")
        if AIRouteQuoteService._to_number(context.get("volume_baseline_unit_price")) > 0:
            parts.append(
                "量产三档"
                f"{AIRouteQuoteService._to_number(context.get('volume_baseline_unit_price')):.2f}/"
                f"{AIRouteQuoteService._to_number(context.get('volume_conservative_unit_price')):.2f}/"
                f"{AIRouteQuoteService._to_number(context.get('volume_aggressive_unit_price')):.2f}"
            )
        return "；".join(parts) if parts else "脚本结果缺失"

    @staticmethod
    def _read_skill_text(path: Path) -> str:
        if not path.exists() or not path.is_file():
            return ""
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
            try:
                return path.read_text(encoding=encoding).strip()
            except UnicodeDecodeError:
                continue
        return ""

    @staticmethod
    def _extract_mapping_lines(text: str, *, limit: int) -> list[str]:
        lines: list[str] = []
        for raw_line in str(text or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip(" -\t")
            if "->" not in line:
                continue
            lines.append(line.replace("`", ""))
            if len(lines) >= limit:
                break
        return lines

    @staticmethod
    def _extract_matches(text: str, keywords: tuple[str, ...], *, limit: int) -> list[str]:
        lines: list[str] = []
        for raw_line in str(text or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip(" -\t")
            if any(keyword in line for keyword in keywords):
                lines.append(line.replace("`", ""))
            if len(lines) >= limit:
                break
        return lines

    @staticmethod
    def _prompt_safe_text(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = text.replace("\r", " ").replace("\n", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _resolve_api_key() -> str:
        return (
            os.getenv("PRICING_AI_API_KEY")
            or str(app_config.get("pricing_ai_api_key", "") or "")
            or os.getenv("QWEN_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or str(app_config.get("qc_global_online_api_key", "") or "")
            or str(app_config.get("qwen_api_key", "") or "")
            or str(app_config.get("dashscope_api_key", "") or "")
            or _get_secret_api_key("qwen", "dashscope")
        ).strip()

    @staticmethod
    def _resolve_base_url() -> str:
        return (
            os.getenv("PRICING_AI_BASE_URL")
            or str(app_config.get("pricing_ai_base_url", "") or "")
            or os.getenv("QWEN_BASE_URL")
            or str(app_config.get("qc_global_online_base_url", "") or "")
            or str(app_config.get("qwen_base_url", "") or "")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).strip()

    @staticmethod
    def _resolve_model() -> str:
        return (
            os.getenv("PRICING_AI_MODEL")
            or str(app_config.get("pricing_ai_model", "") or "")
            or os.getenv("PRICING_QWEN_MODEL")
            or str(app_config.get("pricing_qwen_model", "") or "")
            or os.getenv("SECONDARY_QWEN_MODEL")
            or str(app_config.get("qc_global_secondary_online_model", "") or "")
            or os.getenv("QWEN_MODEL")
            or str(app_config.get("qc_global_vision_model", "") or "")
            or "qwen3.5-plus"
        ).strip()

    @staticmethod
    def _extract_content_text(body: dict[str, Any]) -> str:
        choices = body.get("choices") or []
        if not choices:
            return ""
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            fragments: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    fragments.append(str(item["text"]))
            return "\n".join(fragments)
        return str(content)

    @staticmethod
    def _extract_reasoning_text(body: dict[str, Any]) -> str:
        choices = body.get("choices") or []
        if not choices:
            return ""
        message = (choices[0] or {}).get("message") or {}
        return str(message.get("reasoning_content") or "").strip()

    @staticmethod
    def _try_parse_json_text(text: str) -> dict[str, Any]:
        raw = (text or "").strip()
        if not raw:
            return {}
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw.replace("json", "", 1).strip()
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, flags=re.S)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    return parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    pass
            return {}

    @staticmethod
    def _to_number(value: Any) -> float:
        if value is None or value == "":
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", "")
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else 0.0
