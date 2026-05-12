from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP_WEB_ROOT = ROOT / "app_web"
for candidate in (ROOT, APP_WEB_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app_web.backend.services.ai_route_quote_service import AIRouteQuoteService


class _StubAIRouteQuoteService(AIRouteQuoteService):
    def __init__(self):
        pass


class AIRouteProcessOverrideTests(unittest.TestCase):
    def test_high_confidence_process_inference_overrides_generic_original_process_for_skills_input(self):
        service = _StubAIRouteQuoteService()
        service.INFERENCE_CONFIDENCE_THRESHOLD = AIRouteQuoteService.INFERENCE_CONFIDENCE_THRESHOLD
        service.WEIGHT_INFERENCE_CONFIDENCE_THRESHOLD = AIRouteQuoteService.WEIGHT_INFERENCE_CONFIDENCE_THRESHOLD
        service._infer_missing_fields = lambda item: {
            "confidence": 0.95,
            "reasoning": "",
            "process_guess": "硅钢片冲压与叠压固化",
            "material_guess": "",
            "estimated_weight_kg": 0.0,
        }

        result = service._plan_second_stage_input({
            "name": "定子铁芯",
            "spec": "OD180mm，L90mm，V+1",
            "material": "35W300",
            "process": "冲压",
            "process_original": "冲压",
            "weight_kg": 7.37,
        })

        self.assertTrue(result["used"])
        self.assertEqual(result["pricing_item"]["process"], "硅钢片冲压与叠压固化")
        self.assertEqual(result["pricing_item"]["ai_inferred_process_reference"], "硅钢片冲压与叠压固化")

    def test_low_confidence_process_inference_does_not_override_original_process(self):
        service = _StubAIRouteQuoteService()
        service.INFERENCE_CONFIDENCE_THRESHOLD = AIRouteQuoteService.INFERENCE_CONFIDENCE_THRESHOLD
        service.WEIGHT_INFERENCE_CONFIDENCE_THRESHOLD = AIRouteQuoteService.WEIGHT_INFERENCE_CONFIDENCE_THRESHOLD
        service._infer_missing_fields = lambda item: {
            "confidence": 0.4,
            "reasoning": "",
            "process_guess": "硅钢片冲压与叠压固化",
            "material_guess": "",
            "estimated_weight_kg": 0.0,
        }

        result = service._plan_second_stage_input({
            "name": "定子铁芯",
            "spec": "OD180mm，L90mm，V+1",
            "material": "35W300",
            "process": "冲压",
            "process_original": "冲压",
            "weight_kg": 7.37,
        })

        self.assertFalse(result["used"])
        self.assertEqual(result["pricing_item"]["process"], "冲压")

    def test_motor_core_component_without_process_still_forces_ai_process_review(self):
        service = _StubAIRouteQuoteService()
        self.assertTrue(service._is_motor_core_component({
            "name": "定子组件",
            "spec": "OD180mm，L90mm浸漆定子组件",
            "material": "漆包线（铜）",
            "process": "",
        }))

    def test_motor_core_component_with_specific_existing_process_still_rechecks_process(self):
        service = _StubAIRouteQuoteService()
        service.INFERENCE_CONFIDENCE_THRESHOLD = AIRouteQuoteService.INFERENCE_CONFIDENCE_THRESHOLD
        service.WEIGHT_INFERENCE_CONFIDENCE_THRESHOLD = AIRouteQuoteService.WEIGHT_INFERENCE_CONFIDENCE_THRESHOLD
        service._infer_missing_fields = lambda item: {
            "confidence": 0.93,
            "reasoning": "",
            "process_guess": "定子绕线、嵌线、整形、绑扎、浸漆、烘干",
            "material_guess": "",
            "estimated_weight_kg": 0.0,
        }

        result = service._plan_second_stage_input({
            "name": "定子组件",
            "spec": "OD180mm，L90mm浸漆定子组件",
            "material": "漆包线（铜）",
            "process": "绕线",
            "process_original": "绕线",
            "weight_kg": 2.07,
        })

        self.assertTrue(result["used"])
        self.assertEqual(result["pricing_item"]["process"], "定子绕线、嵌线、整形、绑扎、浸漆、烘干")


if __name__ == "__main__":
    unittest.main()
