# tests/motor_qc/test_phase2_integration.py
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from app_web.project_config_manager import ProjectConfigManager
from app_web.motor_qc.services.inspection_service import InspectionService
from app_web.motor_qc.services.batch_inspection_service import BatchInspectionService


def test_full_workflow_with_process_types(db_session, mock_vision_service, tmp_path):
    """Test complete workflow with photo and PDF processes at service layer"""
    # Setup project config
    config_manager = ProjectConfigManager(tmp_path)
    config = {
        "projectName": "IntegrationTest",
        "projectCode": "INT001",
        "productTypes": [{
            "typeName": "Motor",
            "processSteps": [
                {
                    "id": "p1",
                    "name": "焊接",
                    "attachmentType": "photo"
                },
                {
                    "id": "p2",
                    "name": "质量报告",
                    "attachmentType": "pdf"
                }
            ]
        }]
    }
    config_manager.save_project_config("IntegrationTest", config)

    # Create service with config manager
    service = InspectionService(
        vision_service=mock_vision_service,
        config_manager=config_manager
    )

    # 1. Inspect photo process
    result1 = service.perform_inspection(
        project_code='INT001',
        process_step='焊接',
        photo_path='/test/weld.jpg',
        inspector_id='user123'
    )

    assert result1['status'] == 'fail'
    assert mock_vision_service.analyze_image.called
    assert 'defects' in result1

    # 2. Inspect PDF process
    mock_vision_service.reset_mock()
    result2 = service.perform_inspection(
        project_code='INT001',
        process_step='质量报告',
        photo_path='/test/report.pdf',
        inspector_id='user123'
    )

    assert result2['status'] == 'pass'
    assert not mock_vision_service.analyze_image.called  # Should NOT call Vision API
    assert result2['defects'] == []
    assert 'PDF' in result2['analysis']

    # 3. Test batch inspection with mixed types
    batch_service = BatchInspectionService(config_manager=config_manager)
    batch_service.inspection_service.vision_service = mock_vision_service
    mock_vision_service.reset_mock()

    photos = [
        {"path": "/test/photo1.jpg", "process_step": "焊接"},
        {"path": "/test/report.pdf", "process_step": "质量报告"}
    ]

    results = list(batch_service.process_batch(
        project_code="INT001",
        photos=photos,
        inspector_id="user123"
    ))

    assert len(results) == 2
    assert all(r["status"] == "completed" for r in results)  # wrapper status
    # Vision API should only be called once (for photo)
    assert mock_vision_service.analyze_image.call_count == 1
