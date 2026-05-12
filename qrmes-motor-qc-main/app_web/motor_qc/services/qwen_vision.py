"""千问 Vision API 实现（DashScope OpenAI-compatible）"""

import base64
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .vision_api import VisionAPIInterface, VisionAnalysisResult
from .token_usage_logger import log_ai_token_usage

logger = logging.getLogger(__name__)


class QwenVisionAPI(VisionAPIInterface):
    def __init__(self, config: Dict[str, Any]):
        cfg = config or {}
        api_key = str(cfg.get("api_key") or "").strip()
        allow_empty_api_key = bool(cfg.get("allow_empty_api_key", False))
        if not api_key and not allow_empty_api_key:
            raise ValueError("Qwen API key is required")

        self.api_key = api_key
        self.provider = str(cfg.get("provider") or "qwen").strip().lower() or "qwen"
        # 默认切到 qwen3-vl-flash；仍可由上层配置覆盖
        self.model = str(cfg.get("model", "qwen3-vl-flash") or "qwen3-vl-flash").strip()
        base_url = str(cfg.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1") or "").strip()
        normalized_base = self._normalize_base_url(base_url)
        self.endpoint = f"{normalized_base}/chat/completions"
        self.timeout = int(cfg.get("timeout", 90))

    def analyze_process_photos(
        self,
        process_name: str,
        photos: List[bytes],
        reference_images: List[bytes],
        rules: Dict[str, Any]
    ) -> VisionAnalysisResult:
        if not photos:
            return VisionAnalysisResult(
                status="ng",
                confidence=0.0,
                issues=["未提供待检测照片"],
                summary="未提供待检测照片",
                raw_response={},
            )

        prompt = self._build_prompt(process_name, rules or {})
        result = self._call_qwen(prompt, photos[0])
        return VisionAnalysisResult(
            status=result.get("status", "ng"),
            confidence=float(result.get("confidence", 0.0)),
            issues=[str(x) for x in (result.get("defects") or [])],
            summary=str(result.get("analysis") or ""),
            raw_response=result.get("raw_response", {}),
        )

    def analyze_image(
        self,
        image_path: str,
        prompt: str,
        usage_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with open(Path(image_path), "rb") as f:
            image_bytes = f.read()
        return self._call_qwen(
            prompt,
            image_bytes,
            image_path=image_path,
            usage_context=usage_context,
        )

    def _call_qwen(
        self,
        prompt: str,
        image_bytes: bytes,
        image_path: str = "",
        usage_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        start_ts = time.time()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"{prompt}\n\n"
                                "请仅返回 JSON 对象，格式："
                                "{\"analysis\":\"分析结果\",\"defects\":[\"缺陷1\"],\"status\":\"pass|fail|ng\",\"confidence\":0.0}"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ],
            "temperature": 0.1,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.post(
            self.endpoint,
            headers=headers,
            data=json.dumps(payload),
            timeout=self.timeout,
        )
        latency_ms = int((time.time() - start_ts) * 1000)
        if response.status_code >= 400:
            log_ai_token_usage(
                provider=self.provider,
                model=self.model,
                usage=None,
                image_path=image_path,
                usage_context=usage_context,
                latency_ms=latency_ms,
                success=False,
                error_message=f"HTTP {response.status_code}",
            )
            raise RuntimeError(f"Qwen API error {response.status_code}: {response.text[:400]}")

        body = response.json()
        usage = body.get("usage") if isinstance(body, dict) else {}
        log_ai_token_usage(
            provider=self.provider,
            model=self.model,
            usage=usage if isinstance(usage, dict) else {},
            image_path=image_path,
            usage_context=usage_context,
            latency_ms=latency_ms,
            success=True,
            error_message="",
        )

        content = self._extract_content_text(body)
        parsed = self._parse_json_text(content)

        defects = parsed.get("defects", [])
        if not isinstance(defects, list):
            defects = [str(defects)]

        status = str(parsed.get("status", "")).strip().lower()
        if status not in ("pass", "fail", "ng"):
            status = "fail" if defects else "pass"

        confidence = 0.0
        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        return {
            "analysis": str(parsed.get("analysis") or content or ""),
            "defects": [str(x) for x in defects],
            "status": status,
            "confidence": confidence,
            "raw_response": body,
        }

    def _extract_content_text(self, body: Dict[str, Any]) -> str:
        choices = body.get("choices") or []
        if not choices:
            return ""
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            fragments: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        fragments.append(str(text))
            return "\n".join(fragments)
        return str(content)

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        text = str(base_url or "").strip().rstrip("/")
        if text.endswith("/chat/completions"):
            text = text[: -len("/chat/completions")]
        if text.endswith("/models"):
            text = text[: -len("/models")]
        if "/v1" in text.split("?")[0]:
            return text.rstrip("/")
        return f"{text}/v1".rstrip("/")

    def _parse_json_text(self, text: str) -> Dict[str, Any]:
        raw = (text or "").strip()
        if not raw:
            return {}
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw.replace("json", "", 1).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, flags=re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            logger.warning("Qwen response is not valid JSON: %s", raw[:200])
            return {"analysis": raw, "defects": [], "status": "ng", "confidence": 0.0}

    def _build_prompt(self, process_name: str, rules: Dict[str, Any]) -> str:
        check_items = rules.get("check_items", []) if isinstance(rules, dict) else []
        pass_criteria = rules.get("pass_criteria", "") if isinstance(rules, dict) else ""
        check_text = "\n".join([f"- {item}" for item in check_items]) if check_items else "- 无"
        return (
            "你是电机装配质检专家。请检查工序照片并给出结论。\n"
            f"工序名称：{process_name}\n"
            f"检查项：\n{check_text}\n"
            f"合格标准：{pass_criteria or '按工艺标准判断'}"
        )
