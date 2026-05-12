"""Vision API 统一接口"""
from abc import ABC, abstractmethod
import os
from typing import List, Dict, Any
from dataclasses import dataclass

try:
    from app_web.config.secrets import SecretManager
except Exception:  # pragma: no cover - 兼容目录内直接运行
    try:
        from config.secrets import SecretManager  # type: ignore
    except Exception:
        SecretManager = None

@dataclass
class VisionAnalysisResult:
    """统一的分析结果格式"""
    status: str  # "pass" | "fail" | "ng"
    confidence: float  # 0.0 - 1.0
    issues: List[str]
    summary: str
    raw_response: Dict[str, Any]

class VisionAPIInterface(ABC):
    """Vision API 统一接口"""

    @abstractmethod
    def analyze_process_photos(
        self,
        process_name: str,
        photos: List[bytes],
        reference_images: List[bytes],
        rules: Dict[str, Any]
    ) -> VisionAnalysisResult:
        """分析工序照片"""
        pass

class VisionAPIFactory:
    """Vision API 工厂类"""

    @staticmethod
    def create(provider: str, config: Dict[str, Any]) -> VisionAPIInterface:
        """根据配置创建 Vision API 实例"""
        if provider == "claude":
            from .claude_vision import ClaudeVisionAPI
            return ClaudeVisionAPI(config)
        elif provider == "qwen":
            from .qwen_vision import QwenVisionAPI
            return QwenVisionAPI(config)
        elif provider in ("local", "local_qwen"):
            from .qwen_vision import QwenVisionAPI
            cfg = dict(config or {})
            cfg.setdefault("allow_empty_api_key", True)
            cfg.setdefault("provider", "local_qwen")
            return QwenVisionAPI(cfg)
        else:
            raise ValueError(f"Unsupported provider: {provider}")


def get_vision_service() -> VisionAPIInterface:
    """获取配置的 Vision API 服务实例"""
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

    def _resolve_local_base_url() -> str:
        return (
            os.getenv("LOCAL_QWEN_BASE_URL")
            or os.getenv("LOCAL_VISION_BASE_URL")
            or "http://127.0.0.1:1234/v1"
        ).strip()

    def _resolve_local_model() -> str:
        return (
            os.getenv("LOCAL_QWEN_MODEL")
            or os.getenv("LOCAL_VISION_MODEL")
            or os.getenv("QWEN_LOCAL_MODEL")
            or "qwen/qwen3-vl-30b"
        ).strip()

    provider = (os.getenv("MOTOR_QC_VISION_PROVIDER") or "").strip().lower()
    qwen_key = (
        os.getenv("QWEN_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or _get_secret_api_key("qwen", "dashscope")
        or ""
    ).strip()
    local_key = (
        os.getenv("LOCAL_QWEN_API_KEY")
        or os.getenv("LOCAL_VISION_API_KEY")
        or _get_secret_api_key("qwen_local", "local_qwen")
        or ""
    ).strip()
    claude_key = (
        os.getenv("ANTHROPIC_API_KEY")
        or _get_secret_api_key("anthropic", "claude")
        or ""
    ).strip()

    if not provider:
        if qwen_key:
            provider = "qwen"
        elif claude_key:
            provider = "claude"
        else:
            provider = "qwen"

    if provider in ("local", "local_qwen"):
        from .qwen_vision import QwenVisionAPI
        return QwenVisionAPI({
            "api_key": local_key,
            "allow_empty_api_key": True,
            "provider": "local_qwen",
            "model": _resolve_local_model(),
            "base_url": _resolve_local_base_url(),
            "timeout": int(os.getenv("LOCAL_QWEN_TIMEOUT", os.getenv("QWEN_TIMEOUT", "90"))),
        })

    if provider == "qwen":
        if not qwen_key:
            raise ValueError("Qwen API key 未配置（请设置 QWEN_API_KEY/DASHSCOPE_API_KEY 或 qwen_api_key）")
        from .qwen_vision import QwenVisionAPI
        return QwenVisionAPI({
            "api_key": qwen_key,
            # 默认切到 qwen3-vl-flash；仍可通过 QWEN_MODEL 覆盖
            "model": os.getenv("QWEN_MODEL", "qwen3-vl-flash"),
            "base_url": os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            "timeout": int(os.getenv("QWEN_TIMEOUT", "90")),
            "provider": "qwen",
        })

    if not claude_key:
        raise ValueError("Claude API key 未配置（请设置 ANTHROPIC_API_KEY 或 anthropic_api_key）")
    from .claude_vision import ClaudeVisionAPI
    return ClaudeVisionAPI({
        "api_key": claude_key,
        "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
    })
