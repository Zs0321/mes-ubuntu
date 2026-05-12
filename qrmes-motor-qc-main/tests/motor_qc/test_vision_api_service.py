from unittest.mock import patch

import pytest

from app_web.motor_qc.services.vision_api import get_vision_service
from app_web.motor_qc.services.qwen_vision import QwenVisionAPI


def test_get_vision_service_uses_secret_manager_qwen_key(monkeypatch):
    monkeypatch.setenv("MOTOR_QC_VISION_PROVIDER", "qwen")
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    class _Secrets:
        @staticmethod
        def get_api_key(service):
            if service in ("qwen", "dashscope"):
                return "sk-test-qwen"
            return ""

    with patch("app_web.motor_qc.services.vision_api.SecretManager", _Secrets):
        service = get_vision_service()

    assert service.__class__.__name__ == "QwenVisionAPI"
    assert service.api_key == "sk-test-qwen"


def test_get_vision_service_qwen_without_key_raises(monkeypatch):
    monkeypatch.setenv("MOTOR_QC_VISION_PROVIDER", "qwen")
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    class _Secrets:
        @staticmethod
        def get_api_key(service):
            return ""

    with patch("app_web.motor_qc.services.vision_api.SecretManager", _Secrets):
        with pytest.raises(ValueError, match="Qwen API key"):
            get_vision_service()


def test_get_vision_service_local_provider_allows_empty_key(monkeypatch):
    monkeypatch.setenv("MOTOR_QC_VISION_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_QWEN_BASE_URL", "http://127.0.0.1:1234")
    monkeypatch.setenv("LOCAL_QWEN_MODEL", "qwen/qwen3-vl-30b")
    monkeypatch.delenv("LOCAL_QWEN_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_VISION_API_KEY", raising=False)

    service = get_vision_service()

    assert service.__class__.__name__ == "QwenVisionAPI"
    assert service.provider == "local_qwen"
    assert service.api_key == ""
    assert service.model == "qwen/qwen3-vl-30b"
    assert service.endpoint == "http://127.0.0.1:1234/v1/chat/completions"


def test_qwen_vision_normalizes_base_url_for_chat_endpoint():
    api = QwenVisionAPI(
        {
            "api_key": "sk-test",
            "model": "qwen3-vl-flash",
            "base_url": "http://172.16.20.201:1234/chat/completions",
        }
    )
    assert api.endpoint == "http://172.16.20.201:1234/v1/chat/completions"
