"""Test Vision API factory"""
from motor_qc.services.vision_api import VisionAPIFactory
from qrmes_shared_core.config import config as MOTOR_QC_CONFIG

def test_factory():
    # Test Claude provider
    api = VisionAPIFactory.create("claude", MOTOR_QC_CONFIG["claude"])
    print(f"Created Claude API: {type(api)}")

    # Test invalid provider
    try:
        VisionAPIFactory.create("invalid", {})
        print("ERROR: Should have raised ValueError")
    except ValueError as e:
        print(f"Correctly raised ValueError: {e}")

if __name__ == "__main__":
    test_factory()
