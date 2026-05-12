from pathlib import Path
from tempfile import NamedTemporaryFile

from app_web.motor_qc.services.inspection_service import InspectionService


class _ConfigManagerStub:
    projects_config_dir = Path(".")

    @staticmethod
    def get_project_config(_project_code):
        return {
            "productTypes": [
                {
                    "typeName": "油泵电机总成",
                    "processSteps": [
                        {
                            "name": "后端盖打胶",
                            "attachmentType": "photo",
                        }
                    ],
                }
            ]
        }


class _VisionStub:
    def __init__(self, *, status: str, defects=None, analysis: str, confidence: float, model: str):
        self._status = status
        self._defects = list(defects or [])
        self._analysis = analysis
        self._confidence = confidence
        self.model = model

    def analyze_image(self, image_path: str, prompt: str, usage_context=None):
        _ = image_path, prompt, usage_context
        return {
            "status": self._status,
            "defects": list(self._defects),
            "analysis": self._analysis,
            "confidence": self._confidence,
        }


def _make_temp_photo() -> str:
    with NamedTemporaryFile(suffix=".jpg", delete=False) as fp:
        fp.write(b"\xff\xd8\xff\xd9")
        return fp.name


def test_perform_inspection_accepts_mode_kwargs_online():
    service = InspectionService(
        vision_service=_VisionStub(
            status="pass",
            defects=[],
            analysis="ok",
            confidence=0.95,
            model="qwen3-vl-flash",
        ),
        config_manager=_ConfigManagerStub(),
    )

    photo_path = _make_temp_photo()
    try:
        result = service.perform_inspection(
            project_code="柳工3.5T双12叉车",
            process_step="后端盖打胶",
            photo_path=photo_path,
            inspector_id="u1001",
            serial_number="test222333",
            product_type="油泵电机总成",
            vision_model="qwen3-vl-flash",
            vision_mode="online",
            local_vision_model="qwen/qwen3-vl-30b",
            local_vision_base_url="http://127.0.0.1:1234/v1",
            local_vision_api_key="",
            dual_primary="online",
            persist=False,
        )
    finally:
        Path(photo_path).unlink(missing_ok=True)

    assert result["status"] == "pass"
    assert result["mode"] == "online"
    assert result["provider"] == "online"


def test_perform_inspection_dual_mode_returns_comparison():
    online = _VisionStub(
        status="fail",
        defects=["螺钉缺失"],
        analysis="online fail",
        confidence=0.8,
        model="qwen3-vl-flash",
    )
    local = _VisionStub(
        status="pass",
        defects=[],
        analysis="local pass",
        confidence=0.9,
        model="qwen/qwen3-vl-30b",
    )
    service = InspectionService(vision_service=online, config_manager=_ConfigManagerStub())
    service._build_local_vision_service = lambda *args, **kwargs: local  # type: ignore[attr-defined]

    photo_path = _make_temp_photo()
    try:
        result = service.perform_inspection(
            project_code="柳工3.5T双12叉车",
            process_step="后端盖打胶",
            photo_path=photo_path,
            inspector_id="u1001",
            serial_number="test222333",
            product_type="油泵电机总成",
            vision_mode="dual",
            vision_model="qwen3-vl-flash",
            local_vision_model="qwen/qwen3-vl-30b",
            local_vision_base_url="http://127.0.0.1:1234/v1",
            local_vision_api_key="",
            dual_primary="local",
            persist=False,
        )
    finally:
        Path(photo_path).unlink(missing_ok=True)

    assert result["mode"] == "dual"
    assert result["provider"] == "local"
    assert result["comparison"]["primary"] == "local"
    assert result["comparison"]["status_match"] is False
    assert "online" in result["model_outputs"]
    assert "local" in result["model_outputs"]
